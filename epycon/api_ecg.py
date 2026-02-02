"""
ECG 数据查看器 API 模块
提供 HDF5 心电图数据的读取、流式传输和标注处理功能
"""
import os
import uuid
import base64
import tempfile
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify, send_file
import numpy as np

try:
    import h5py
    H5PY_AVAILABLE = True
except ImportError:
    H5PY_AVAILABLE = False

try:
    from scipy import signal as scipy_signal
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

logger = logging.getLogger("ecg_api")

# 创建 Blueprint
ecg_api = Blueprint('ecg_api', __name__, url_prefix='/api/ecg')

# 临时文件存储
TEMP_DIR = os.path.join(tempfile.gettempdir(), 'epycon_ecg_viewer')
os.makedirs(TEMP_DIR, exist_ok=True)

# 文件信息缓存
FILE_CACHE = {}  # file_id -> {path, metadata, ...}


def _convert_numpy_types(obj):
    """
    递归转换 numpy 类型为 Python 原生类型，确保 JSON 序列化兼容
    """
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, (np.integer, np.int64, np.int32)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float64, np.float32)):
        return float(obj)
    elif isinstance(obj, np.bool_):
        return bool(obj)
    elif isinstance(obj, bytes):
        return obj.decode('utf-8', errors='replace')
    elif isinstance(obj, dict):
        return {k: _convert_numpy_types(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_convert_numpy_types(v) for v in obj]
    return obj


def apply_notch_filter(data, fs, freq=50.0, q=35.0, method='zero_phase', enhanced=False):
    """
    应用陷波滤波器去除特定频率干扰。
    
    模式说明:
    1. 标准模式 (enhanced=False):
       - 仅去除基频 (如 50Hz)
       - 仅运行一次滤波器 (Standard Scipy)
       
    2. ActiveNotch™ 增强模式 (enhanced=True):
       - 去除基频及 2/3 次谐波 (50, 100, 150 Hz)
       - 双重级联 (Double Cascade)，加深衰减深度
    
    Args:
        data: 输入数据
        fs: 采样频率
        freq: 基频 (Hz)
        q: 品质因子 (默认 35.0)
        method: 'zero_phase' (filtfilt) 或 'causal' (lfilter)
        enhanced: 是否开启增强模式 (默认 False)
    """
    if not SCIPY_AVAILABLE:
        logger.warning("scipy 不可用，跳过滤波")
        return data, False
    
    # 统计信息用于调试
    std_before = np.std(data)
    
    # 根据模式决定处理的频率列表
    if enhanced:
        harmonics = [1, 2, 3] # 增强模式：基频 + 2/3次谐波
    else:
        harmonics = [1]       # 标准模式：仅基频
    
    current_data = data
    
    for k in harmonics:
        target_freq = freq * k
        if target_freq >= fs / 2:
            continue # 超过奈奎斯特频率
            
        # 设计单级陷波滤波器
        b, a = scipy_signal.iirnotch(target_freq, q, fs)
        
        # 应用滤波器
        if method == 'causal':
            # 因果滤波 (lfilter)
            if len(current_data.shape) == 1:
                zi = scipy_signal.lfilter_zi(b, a)
                current_data, _ = scipy_signal.lfilter(b, a, current_data, zi=zi*current_data[0])
                
                # [增强模式] 第二次级联
                if enhanced:
                    zi = scipy_signal.lfilter_zi(b, a)
                    current_data, _ = scipy_signal.lfilter(b, a, current_data, zi=zi*current_data[0])
            else:
                filtered = np.zeros_like(current_data)
                for ch in range(current_data.shape[1]):
                    zi = scipy_signal.lfilter_zi(b, a)
                    temp, _ = scipy_signal.lfilter(b, a, current_data[:, ch], zi=zi*current_data[0, ch])
                    
                    # [增强模式] 第二次级联
                    if enhanced:
                        zi = scipy_signal.lfilter_zi(b, a)
                        temp, _ = scipy_signal.lfilter(b, a, temp, zi=zi*temp[0])
                        
                    filtered[:, ch] = temp
                current_data = filtered
        else:
            # 零相位滤波 (filtfilt)
            if len(current_data.shape) == 1:
                current_data = scipy_signal.filtfilt(b, a, current_data)
                # [增强模式] 第二次级联
                if enhanced:
                    current_data = scipy_signal.filtfilt(b, a, current_data)
            else:
                filtered = np.zeros_like(current_data)
                for ch in range(current_data.shape[1]):
                    temp = scipy_signal.filtfilt(b, a, current_data[:, ch])
                    # [增强模式] 第二次级联
                    if enhanced:
                        temp = scipy_signal.filtfilt(b, a, temp)
                    filtered[:, ch] = temp
                current_data = filtered
    
    std_after = np.std(current_data)
    mode_str = "ActiveNotch™ Enhanced" if enhanced else "Standard Scipy"
    logger.info(f"{mode_str} 完成 ({method}): Freq={freq}Hz, Harmonics={harmonics}, fs={fs}Hz")
    
    return current_data, True


def apply_lowpass_filter(data, fs, cutoff=35.0, order=None, method='zero_phase'):
    """
    应用 Butterworth 低通滤波器平滑信号（滤除高频噪声/肌电干扰）
    
    Args:
        data: 输入数据
        fs: 采样频率 (Hz)
        cutoff: 截止频率 (Hz)，默认 35Hz（临床常见）
        order: 滤波器阶数，若为 None 则根据 method 自动选择
               - causal: 默认 1阶 (模拟临床设备缓慢滚降)
               - zero_phase: 默认 2阶 (等效4阶，避免过度平滑)
    """
    if not SCIPY_AVAILABLE:
        return data
    
    # 自动选择阶数
    if order is None:
        if method == 'causal':
            order = 1  # Causal: 1阶滤波器滚降最平缓 (-6dB/oct)，配合强力 ActiveNotch 使用
        else:
            order = 1  # Zero-phase: 1阶 + filtfilt = 有效2阶
    
    # 归一化频率 (Nyquist 频率的一半)
    nyq = 0.5 * fs
    normal_cutoff = cutoff / nyq
    if normal_cutoff >= 1.0:
        return data
        
    # 设计滤波器
    b, a = scipy_signal.butter(order, normal_cutoff, btype='low', analog=False)
    
    # 应用滤波器
    if method == 'causal':
        # 因果滤波 (lfilter)
        if len(data.shape) == 1:
            zi = scipy_signal.lfilter_zi(b, a)
            filtered, _ = scipy_signal.lfilter(b, a, data, zi=zi*data[0])
        else:
            filtered = np.zeros_like(data)
            for ch in range(data.shape[1]):
                zi = scipy_signal.lfilter_zi(b, a)
                filtered[:, ch], _ = scipy_signal.lfilter(b, a, data[:, ch], zi=zi*data[0, ch])
    else:
        # 零相位滤波 (filtfilt)
        if len(data.shape) == 1:
            filtered = scipy_signal.filtfilt(b, a, data)
        else:
            filtered = np.zeros_like(data)
            for ch in range(data.shape[1]):
                filtered[:, ch] = scipy_signal.filtfilt(b, a, data[:, ch])
            
    return filtered


def apply_highpass_filter(data, fs, cutoff=0.5, order=None, method='zero_phase'):
    """
    应用 Butterworth 高通滤波器去除基线漂移
    """
    if not SCIPY_AVAILABLE:
        return data

    # 自动选择阶数
    if order is None:
        # 高通滤波通常可以直接用 1 阶或 2 阶
        order = 1 if method == 'causal' else 2
    
    # 归一化频率
    nyq = 0.5 * fs
    normal_cutoff = cutoff / nyq
    if normal_cutoff <= 0 or normal_cutoff >= 1.0:
        return data
        
    # 设计滤波器
    b, a = scipy_signal.butter(order, normal_cutoff, btype='high', analog=False)
    
    # 应用滤波器
    if method == 'causal':
        # 因果滤波 (lfilter)
        if len(data.shape) == 1:
            zi = scipy_signal.lfilter_zi(b, a)
            filtered, _ = scipy_signal.lfilter(b, a, data, zi=zi*data[0])
        else:
            filtered = np.zeros_like(data)
            for ch in range(data.shape[1]):
                zi = scipy_signal.lfilter_zi(b, a)
                filtered[:, ch], _ = scipy_signal.lfilter(b, a, data[:, ch], zi=zi*data[0, ch])
    else:
        # 零相位滤波 (filtfilt) (双向)
        if len(data.shape) == 1:
            filtered = scipy_signal.filtfilt(b, a, data)
        else:
            filtered = np.zeros_like(data)
            for ch in range(data.shape[1]):
                filtered[:, ch] = scipy_signal.filtfilt(b, a, data[:, ch])
            
    return filtered


def minmax_downsample(data, factor):
    """
    Min-Max 降采样：保留每个降采样窗口内的最小值和最大值
    避免简单跳采导致的峰值丢失问题
    
    Args:
        data: 2D numpy array, shape (samples, channels)
        factor: 降采样因子
    
    Returns:
        降采样后的数据，采样点数约为原来的 2/factor (保留 min 和 max)
    """
    if factor <= 1:
        return data
    
    n_samples, n_channels = data.shape
    n_windows = n_samples // factor
    remainder = n_samples % factor
    
    if n_windows == 0:
        # 不足一个窗口，直接返回 min/max
        mins = data.min(axis=0, keepdims=True)
        maxs = data.max(axis=0, keepdims=True)
        return np.vstack([mins, maxs])
    
    # 处理完整窗口
    truncated = data[:n_windows * factor, :]
    # 重塑为 (n_windows, factor, n_channels)
    reshaped = truncated.reshape(n_windows, factor, n_channels)
    
    # 在每个窗口内找最小和最大值
    mins = reshaped.min(axis=1)  # (n_windows, n_channels)
    maxs = reshaped.max(axis=1)  # (n_windows, n_channels)
    
    # 交错排列 min 和 max，保持波形形态
    # 结果 shape: (n_windows * 2, n_channels)
    result = np.empty((n_windows * 2, n_channels), dtype=data.dtype)
    result[0::2] = mins
    result[1::2] = maxs
    
    # 处理余数部分（确保覆盖完整时间范围）
    if remainder > 0:
        remainder_data = data[n_windows * factor:, :]
        remainder_min = remainder_data.min(axis=0, keepdims=True)
        remainder_max = remainder_data.max(axis=0, keepdims=True)
        result = np.vstack([result, remainder_min, remainder_max])
    
    return result


def _build_computed_leads(metadata):
    """
    自动识别 u+X 和 u-X 电极配对，生成计算导联映射。
    例如: u+HRA, u-HRA -> HRA (差分计算)
    
    Args:
        metadata: 包含 channel_names 的元数据字典
    
    Returns:
        修改后的 metadata，包含以下新字段：
        - computed_leads: 配对导联列表 [{name, plus_idx, minus_idx}, ...]
        - is_computed_mode: 是否为计算导联模式
        - display_channel_names: 用于显示的通道名列表
        - display_num_channels: 显示通道数量
    """
    import re
    
    names = metadata.get('channel_names', [])
    if not names:
        metadata['computed_leads'] = []
        metadata['is_computed_mode'] = False
        metadata['display_channel_names'] = names
        metadata['display_num_channels'] = len(names)
        return metadata
    
    # 匹配 u+XXX 和 u-XXX 模式
    plus_pattern = re.compile(r'^u\+(.+)$')
    minus_pattern = re.compile(r'^u-(.+)$')
    
    plus_electrodes = {}   # {lead_name: channel_index}
    minus_electrodes = {}  # {lead_name: channel_index}
    other_channels = []    # 非配对通道的索引
    
    for i, name in enumerate(names):
        plus_match = plus_pattern.match(name)
        minus_match = minus_pattern.match(name)
        
        if plus_match:
            plus_electrodes[plus_match.group(1)] = i
        elif minus_match:
            minus_electrodes[minus_match.group(1)] = i
        else:
            other_channels.append(i)
    
    # 找出可以配对的导联
    computed_leads = []
    for lead_name, plus_idx in plus_electrodes.items():
        if lead_name in minus_electrodes:
            computed_leads.append({
                'name': lead_name,
                'plus_idx': plus_idx,
                'minus_idx': minus_electrodes[lead_name]
            })
    
    # 如果有配对的导联，启用计算模式
    if computed_leads:
        logger.info(f"检测到 {len(computed_leads)} 个计算导联: {[l['name'] for l in computed_leads]}")
        
        metadata['computed_leads'] = computed_leads
        metadata['is_computed_mode'] = True
        
        # 生成显示用的通道名列表
        display_names = [l['name'] for l in computed_leads]
        display_names.extend([names[i] for i in other_channels])
        
        metadata['display_channel_names'] = display_names
        metadata['display_num_channels'] = len(display_names)
        
        # 保存 other_channels 索引以便数据读取时使用
        metadata['other_channel_indices'] = other_channels
    else:
        metadata['computed_leads'] = []
        metadata['is_computed_mode'] = False
        metadata['display_channel_names'] = names
        metadata['display_num_channels'] = len(names)
        metadata['other_channel_indices'] = list(range(len(names)))
    
    return metadata


def _get_dataset_path(h5file):
    """
    自动检测 HDF5 文件中的主数据集路径
    支持多种常见结构: /data, /signals, /ecg, 根目录数据集等
    """
    candidates = ['data', 'signals', 'ecg', 'Data', 'Signals', 'ECG', 'waveforms']
    
    # 首先检查常见路径
    for name in candidates:
        if name in h5file:
            obj = h5file[name]
            if isinstance(obj, h5py.Dataset):
                return name
            elif isinstance(obj, h5py.Group):
                # 检查组内是否有数据集
                for key in obj.keys():
                    if isinstance(obj[key], h5py.Dataset):
                        return f"{name}/{key}"
    
    # 遍历所有对象找到第一个二维数据集
    def find_dataset(group, prefix=''):
        for key in group.keys():
            path = f"{prefix}/{key}" if prefix else key
            obj = group[key]
            if isinstance(obj, h5py.Dataset):
                if len(obj.shape) == 2:  # 二维数据 (samples, channels) 或 (channels, samples)
                    return path
            elif isinstance(obj, h5py.Group):
                result = find_dataset(obj, path)
                if result:
                    return result
        return None
    
    return find_dataset(h5file)


def _get_annotations_path(h5file):
    """自动检测标注数据集路径"""
    candidates = ['annotations', 'marks', 'entries', 'events', 'Annotations', 'Marks', 'Events']
    
    for name in candidates:
        if name in h5file:
            return name
    
    # 递归搜索
    def find_annotations(group, prefix=''):
        for key in group.keys():
            path = f"{prefix}/{key}" if prefix else key
            obj = group[key]
            if isinstance(obj, h5py.Dataset):
                # 标注通常是一维或结构化数组
                if 'annot' in key.lower() or 'mark' in key.lower() or 'event' in key.lower():
                    return path
            elif isinstance(obj, h5py.Group):
                if 'annot' in key.lower() or 'mark' in key.lower():
                    return path
                result = find_annotations(obj, path)
                if result:
                    return result
        return None
    
    return find_annotations(h5file)


def _extract_metadata(h5file, data_path):
    """从 HDF5 文件中提取元数据"""
    metadata = {
        'sampling_freq': 250,  # 默认值
        'num_channels': 0,
        'num_samples': 0,
        'duration_seconds': 0,
        'channel_names': [],
        'channel_sources': [],  # RAW 或 computed
        'units': 'mV',
        'data_orientation': 'samples_first',
        # 研究/患者信息
        'study_id': '',
        'log_id': '',
        'patient_name': '',
        'patient_id': '',
        'record_date': '',
        'generated_by': '',
        'attributes': {}
    }
    
    # 从根属性读取
    for attr_name in h5file.attrs:
        try:
            val = h5file.attrs[attr_name]
            if isinstance(val, bytes):
                val = val.decode('utf-8', errors='replace')
            elif isinstance(val, np.ndarray):
                val = val.tolist()
            metadata['attributes'][attr_name] = val
            
            attr_lower = attr_name.lower()
            
            # 识别采样率
            if attr_lower in ['sampling_freq', 'sampling_frequency', 'fs', 'sample_rate', 'samplerate']:
                if isinstance(val, (list, tuple)) and len(val) > 0:
                    metadata['sampling_freq'] = float(val[0])
                else:
                    metadata['sampling_freq'] = float(val)
            # 识别研究/患者信息
            elif attr_lower in ['studyid', 'study_id']:
                metadata['study_id'] = str(val) if not isinstance(val, str) else val
            elif attr_lower in ['logid', 'log_id']:
                metadata['log_id'] = str(val) if not isinstance(val, str) else val
            elif attr_lower in ['patientname', 'patient_name', 'name', 'subjectname', 'subject_name']:
                metadata['patient_name'] = str(val) if not isinstance(val, str) else val
            elif attr_lower in ['patientid', 'patient_id', 'subjectid', 'subject_id']:
                metadata['patient_id'] = str(val) if not isinstance(val, str) else val
            elif attr_lower in ['recorddate', 'record_date', 'date']:
                metadata['record_date'] = str(val) if not isinstance(val, str) else val
            elif attr_lower in ['generatedby', 'generated_by', 'creator']:
                metadata['generated_by'] = str(val) if not isinstance(val, str) else val
        except Exception:
            pass
    
    # 从数据集读取形状信息
    if data_path and data_path in h5file:
        dataset = h5file[data_path]
        shape = dataset.shape
        
        # 判断数据方向
        if len(shape) == 2:
            if shape[0] > shape[1]:
                metadata['num_samples'] = shape[0]
                metadata['num_channels'] = shape[1]
                metadata['data_orientation'] = 'samples_first'
            else:
                metadata['num_samples'] = shape[1]
                metadata['num_channels'] = shape[0]
                metadata['data_orientation'] = 'channels_first'
        elif len(shape) == 1:
            metadata['num_samples'] = shape[0]
            metadata['num_channels'] = 1
        
        # 从数据集属性读取
        for attr_name in dataset.attrs:
            try:
                val = dataset.attrs[attr_name]
                if isinstance(val, bytes):
                    val = val.decode('utf-8', errors='replace')
                elif isinstance(val, np.ndarray):
                    val = val.tolist()
                    
                if attr_name.lower() in ['channel_names', 'channels', 'labels']:
                    if isinstance(val, list):
                        metadata['channel_names'] = val
                    elif isinstance(val, str):
                        metadata['channel_names'] = val.split(',')
                elif attr_name.lower() in ['sampling_freq', 'sampling_frequency', 'fs']:
                    metadata['sampling_freq'] = float(val)
                elif attr_name.lower() == 'units':
                    metadata['units'] = val
            except Exception:
                pass
    
    # 尝试从 Info 数据集获取通道名和数据源（Epycon 格式）
    if not metadata['channel_names'] and 'Info' in h5file:
        try:
            info = h5file['Info']
            if isinstance(info, h5py.Dataset):
                info_data = info[:]
                if info_data.dtype.names:
                    names = []
                    sources = []
                    for row in info_data:
                        # 通道名
                        if 'ChannelName' in info_data.dtype.names:
                            name = row['ChannelName']
                            if isinstance(name, bytes):
                                name = name.decode('utf-8', errors='replace')
                            names.append(name.strip())
                        # 数据源 (RAW/computed)
                        if 'DatacacheName' in info_data.dtype.names:
                            source = row['DatacacheName']
                            if isinstance(source, bytes):
                                source = source.decode('utf-8', errors='replace')
                            sources.append(source.strip())
                    if names:
                        metadata['channel_names'] = names
                    if sources:
                        metadata['channel_sources'] = sources
        except Exception as e:
            logger.warning(f"读取 Info 数据集失败: {e}")
    
    # 尝试从 ChannelSettings 数据集获取通道名（备选）
    if not metadata['channel_names']:
        channel_settings_paths = ['ChannelSettings', 'channelsettings', 'channel_settings']
        for cs_path in channel_settings_paths:
            if cs_path in h5file:
                try:
                    cs = h5file[cs_path]
                    if isinstance(cs, h5py.Dataset):
                        cs_data = cs[:]
                        if cs_data.dtype.names and 'Channel' in cs_data.dtype.names:
                            names = []
                            for row in cs_data:
                                name = row['Channel']
                                if isinstance(name, bytes):
                                    name = name.decode('utf-8', errors='replace')
                                names.append(name.strip())
                            metadata['channel_names'] = names
                            break
                except Exception as e:
                    logger.warning(f"读取 ChannelSettings 失败: {e}")
    
    # 生成默认通道名
    if not metadata['channel_names'] and metadata['num_channels'] > 0:
        metadata['channel_names'] = [f"Ch{i+1}" for i in range(metadata['num_channels'])]
    
    # 计算时长
    if metadata['num_samples'] > 0 and metadata['sampling_freq'] > 0:
        metadata['duration_seconds'] = metadata['num_samples'] / metadata['sampling_freq']
    
    # 自动识别 u+/u- 电极配对，生成计算导联
    metadata = _build_computed_leads(metadata)
    
    # 转换所有 numpy 类型为 Python 原生类型
    return _convert_numpy_types(metadata)


def _extract_npy_metadata(data, filename):
    """从 NumPy 数组中提取元数据"""
    metadata = {
        'sampling_freq': 250,  # NPY 文件无法获取采样率，使用默认值
        'num_channels': 0,
        'num_samples': 0,
        'duration_seconds': 0,
        'channel_names': [],
        'units': 'mV',
        'data_orientation': 'samples_first',
        'attributes': {'source_file': filename, 'format': 'numpy'}
    }
    
    shape = data.shape
    
    if len(shape) == 2:
        if shape[0] > shape[1]:
            # (samples, channels)
            metadata['num_samples'] = shape[0]
            metadata['num_channels'] = shape[1]
            metadata['data_orientation'] = 'samples_first'
        else:
            # (channels, samples)
            metadata['num_samples'] = shape[1]
            metadata['num_channels'] = shape[0]
            metadata['data_orientation'] = 'channels_first'
    elif len(shape) == 1:
        metadata['num_samples'] = shape[0]
        metadata['num_channels'] = 1
    
    # 生成默认通道名
    if metadata['num_channels'] > 0:
        metadata['channel_names'] = [f"Ch{i+1}" for i in range(metadata['num_channels'])]
    
    # 计算时长
    if metadata['num_samples'] > 0 and metadata['sampling_freq'] > 0:
        metadata['duration_seconds'] = metadata['num_samples'] / metadata['sampling_freq']
    
    return _convert_numpy_types(metadata)


def _extract_annotations(h5file, annot_path):
    """提取标注数据"""
    annotations = []
    
    if not annot_path or annot_path not in h5file:
        return annotations
    
    obj = h5file[annot_path]
    
    if isinstance(obj, h5py.Dataset):
        try:
            data = obj[:]
            
            # 处理结构化数组
            if data.dtype.names:
                logger.info(f"标注数据集字段: {data.dtype.names}")
                for i, row in enumerate(data):
                    annot = {'index': i}
                    for name in data.dtype.names:
                        val = row[name]
                        if isinstance(val, bytes):
                            val = val.decode('utf-8', errors='replace')
                        elif isinstance(val, np.ndarray):
                            val = val.tolist()
                        annot[name] = val
                    
                    # 兼容 Epycon 的 Marks 格式：使用 SampleLeft 和 SampleRight 的中点
                    if 'SampleLeft' in annot:
                        left = annot['SampleLeft']
                        right = annot.get('SampleRight', left)  # 如果没有 SampleRight，使用 SampleLeft
                        annot['sample'] = (left + right) // 2  # 使用中点
                    if 'Group' in annot:
                        annot['group'] = annot['Group']
                    if 'Info' in annot:
                        annot['message'] = annot['Info']
                        # label 优先使用 Info 内容，如果 Info 为空或只有数字则使用 Group
                        info_val = annot['Info'].strip() if isinstance(annot['Info'], str) else str(annot['Info'])
                        if info_val and info_val not in ('0', '1', ''):
                            annot['label'] = info_val
                        else:
                            annot['label'] = annot.get('Group', 'Mark')
                    
                    annotations.append(annot)
            else:
                # 简单数组，可能是采样点索引
                for i, val in enumerate(data):
                    annotations.append({
                        'index': i,
                        'sample': int(val),
                        'label': f'Mark {i+1}'
                    })
        except Exception as e:
            logger.warning(f"读取标注失败: {e}")
    
    elif isinstance(obj, h5py.Group):
        # 标注组，可能包含多个数据集
        try:
            samples = obj.get('samples', obj.get('position', obj.get('time', None)))
            labels = obj.get('labels', obj.get('type', obj.get('group', None)))
            messages = obj.get('message', obj.get('text', obj.get('description', None)))
            
            if samples is not None:
                samples_data = samples[:]
                labels_data = labels[:] if labels else ['' for _ in samples_data]
                messages_data = messages[:] if messages else ['' for _ in samples_data]
                
                for i, (s, l, m) in enumerate(zip(samples_data, labels_data, messages_data)):
                    if isinstance(l, bytes):
                        l = l.decode('utf-8', errors='replace')
                    if isinstance(m, bytes):
                        m = m.decode('utf-8', errors='replace')
                    annotations.append({
                        'index': i,
                        'sample': int(s),
                        'label': str(l),
                        'message': str(m)
                    })
        except Exception as e:
            logger.warning(f"读取标注组失败: {e}")
    
    # 转换所有 numpy 类型
    return _convert_numpy_types(annotations)


@ecg_api.route('/check', methods=['GET'])
def check_availability():
    """检查 API 可用性和依赖状态"""
    return jsonify({
        'available': True,
        'h5py_available': H5PY_AVAILABLE,
        'temp_dir': TEMP_DIR,
        'cached_files': len(FILE_CACHE)
    })


@ecg_api.route('/browse', methods=['GET'])
def browse_file():
    """
    打开系统原生文件选择对话框
    返回选择的文件路径
    为避免 macOS 上的线程崩溃问题，通过 subprocess 调用独立脚本执行 GUI 操作
    """
    try:
        import subprocess
        import sys
        
        # 定位辅助脚本路径
        script_path = os.path.join(os.path.dirname(__file__), 'gui_file_dialog.py')
        
        # 调用子进程
        result = subprocess.run(
            [sys.executable, script_path], 
            capture_output=True, 
            text=True,
            timeout=60 # 防止卡死
        )
        
        if result.returncode == 0:
            file_path = result.stdout.strip()
            if file_path:
                return jsonify({'path': file_path})
            else:
                return jsonify({'path': None}) # 用户取消
        else:
            logger.error(f"子进程 GUI 错误: {result.stderr}")
            return jsonify({'path': None, 'error': "Dialog process failed"})
            
    except Exception as e:
        logger.error(f"文件选择失败: {e}")
        return jsonify({'path': None, 'error': str(e)})


@ecg_api.route('/open_local', methods=['POST'])
def open_local_file():
    """
    直接打开本地文件路径（无需上传）
    """
    if not H5PY_AVAILABLE:
        return jsonify({'error': 'h5py 未安装'}), 500
        
    data = request.get_json()
    if not data or 'path' not in data:
        return jsonify({'error': '未提供文件路径'}), 400
        
    file_path = data['path']
    if not os.path.exists(file_path):
        return jsonify({'error': '文件不存在'}), 404
        
    # 扩展名检查
    ext = os.path.splitext(file_path)[1].lower()
    supported_h5 = ['.h5', '.hdf5', '.he5', '.hdf']
    supported_npy = ['.npy', '.npz']
    
    if ext not in supported_h5 + supported_npy:
        return jsonify({'error': f'不支持的文件格式: {ext}'}), 400
        
    try:
        file_id = f"local_{os.path.basename(file_path)}_{str(uuid.uuid4())[:6]}"
        
        # 根据文件类型处理
        if ext in supported_npy:
             # 处理 NumPy 文件
            if ext == '.npy':
                import numpy as np
                data = np.load(file_path, mmap_mode='r') # 使用 mmap 避免全量加载
            else:  # .npz
                import numpy as np
                npz_file = np.load(file_path)
                key = list(npz_file.keys())[0]
                data = npz_file[key]
            
            metadata = _extract_npy_metadata(data, os.path.basename(file_path))
            annotations = []
            data_path = None
            annot_path = None
            file_type = 'npy'
        else:
            # HDF5
            with h5py.File(file_path, 'r') as h5f:
                data_path = _get_dataset_path(h5f)
                annot_path = _get_annotations_path(h5f)
                metadata = _extract_metadata(h5f, data_path)
                annotations = _extract_annotations(h5f, annot_path)
            file_type = 'hdf5'
            
        # 缓存文件信息（标记为 local，清理时不删除文件）
        FILE_CACHE[file_id] = {
            'path': file_path,
            'is_local': True, 
            'filename': os.path.basename(file_path),
            'file_type': file_type,
            'data_path': data_path,
            'annot_path': annot_path,
            'metadata': metadata,
            'annotations': annotations,
            'upload_time': datetime.now().isoformat()
        }
        
        logger.info(f"本地文件已打开: {file_id} -> {file_path}")
        
        return jsonify({
            'file_id': file_id,
            'filename': os.path.basename(file_path),
            'metadata': metadata,
            'num_annotations': len(annotations),
            'source': 'local_disk'
        })

    except Exception as e:
        logger.error(f"打开本地文件失败: {e}")
        return jsonify({'error': str(e)}), 500

def upload_file():
    """
    上传 HDF5 文件
    返回 file_id 用于后续操作
    """
    if not H5PY_AVAILABLE:
        return jsonify({'error': 'h5py 未安装'}), 500
    
    if 'file' not in request.files:
        return jsonify({'error': '未找到文件'}), 400
    
    file = request.files['file']
    if not file.filename:
        return jsonify({'error': '文件名为空'}), 400
    
    # 检查扩展名
    ext = os.path.splitext(file.filename)[1].lower()
    supported_h5 = ['.h5', '.hdf5', '.he5', '.hdf']
    supported_npy = ['.npy', '.npz']
    
    if ext not in supported_h5 + supported_npy:
        return jsonify({'error': f'不支持的文件格式: {ext}'}), 400
    
    # 生成唯一 ID
    file_id = str(uuid.uuid4())[:8]
    
    # 保存文件
    save_path = os.path.join(TEMP_DIR, f"{file_id}_{file.filename}")
    file.save(save_path)
    
    try:
        # 根据文件类型处理
        if ext in supported_npy:
            # 处理 NumPy 文件
            if ext == '.npy':
                data = np.load(save_path)
            else:  # .npz
                npz_file = np.load(save_path)
                # 获取第一个数组
                key = list(npz_file.keys())[0]
                data = npz_file[key]
            
            # 提取元数据
            metadata = _extract_npy_metadata(data, file.filename)
            annotations = []
            data_path = None
            annot_path = None
            file_type = 'npy'
        else:
            # 处理 HDF5 文件
            if not H5PY_AVAILABLE:
                os.remove(save_path)
                return jsonify({'error': 'h5py 未安装'}), 500
            
            with h5py.File(save_path, 'r') as h5f:
                data_path = _get_dataset_path(h5f)
                annot_path = _get_annotations_path(h5f)
                
                if not data_path:
                    os.remove(save_path)
                    return jsonify({'error': '未找到有效的数据集'}), 400
                
                metadata = _extract_metadata(h5f, data_path)
                annotations = _extract_annotations(h5f, annot_path)
            file_type = 'hdf5'
        
        # 缓存文件信息
        FILE_CACHE[file_id] = {
            'path': save_path,
            'filename': file.filename,
            'file_type': file_type,
            'data_path': data_path,
            'annot_path': annot_path,
            'metadata': metadata,
            'annotations': annotations,
            'upload_time': datetime.now().isoformat()
        }
        
        logger.info(f"文件上传成功: {file_id} -> {file.filename}")
        
        return jsonify({
            'file_id': file_id,
            'filename': file.filename,
            'metadata': metadata,
            'num_annotations': len(annotations)
        })
    
    except Exception as e:
        if os.path.exists(save_path):
            os.remove(save_path)
        logger.error(f"文件处理失败: {e}")
        return jsonify({'error': f'文件处理失败: {str(e)}'}), 500


@ecg_api.route('/metadata/<file_id>', methods=['GET'])
def get_metadata(file_id):
    """获取文件元数据"""
    if file_id not in FILE_CACHE:
        return jsonify({'error': '文件不存在或已过期'}), 404
    
    info = FILE_CACHE[file_id]
    return jsonify({
        'file_id': file_id,
        'filename': info['filename'],
        'metadata': info['metadata'],
        'num_annotations': len(info['annotations'])
    })


@ecg_api.route('/data/<file_id>', methods=['GET'])
def get_data(file_id):
    """
    获取指定范围的波形数据
    
    Query params:
    - start: 起始时间（秒），默认 0
    - end: 结束时间（秒），默认 10
    - channels: 通道索引列表，逗号分隔，默认全部
    - downsample: 降采样因子，默认 1（不降采样）
    """
    if file_id not in FILE_CACHE:
        return jsonify({'error': '文件不存在或已过期'}), 404
    
    info = FILE_CACHE[file_id]
    metadata = info['metadata']
    fs = metadata['sampling_freq']
    file_type = info.get('file_type', 'hdf5')
    
    # 解析参数
    start_sec = float(request.args.get('start', 0))
    end_sec = float(request.args.get('end', 10))
    channels_str = request.args.get('channels', '')
    downsample = int(request.args.get('downsample', 1))
    notch_freq = request.args.get('notch', None)  # 陷波滤波频率，如 "50" 或 "60"
    lp_cutoff = request.args.get('lp', None)     # 低通滤波截止频率，如 "35"
    hp_cutoff = request.args.get('hp', None)     # 高通滤波截止频率，如 "0.5"
    filter_method = request.args.get('filter_method', 'zero_phase') # 'zero_phase' (default/Epycon) or 'causal' (Workmate)
    
    # 通道级滤波参数 (JSON 格式，如 {"0": {"lp": "100", "hp": "30"}})
    channel_filters_str = request.args.get('channel_filters', None)
    channel_filters = {}
    if channel_filters_str:
        try:
            import json
            channel_filters = json.loads(channel_filters_str)
            logger.info(f"接收到通道级滤波参数: {channel_filters}")
        except Exception as e:
            logger.warning(f"解析 channel_filters 失败: {e}")
    
    # 转换为采样点索引
    start_idx = max(0, int(start_sec * fs))
    end_idx = min(metadata['num_samples'], int(end_sec * fs))
    
    # 检查是否为计算导联模式
    is_computed_mode = metadata.get('is_computed_mode', False)
    computed_leads = metadata.get('computed_leads', [])
    other_channel_indices = metadata.get('other_channel_indices', [])
    display_channel_names = metadata.get('display_channel_names', metadata['channel_names'])
    
    # 解析请求的通道（这里的 channels 是 display 通道索引）
    if channels_str:
        display_channels = [int(c) for c in channels_str.split(',') if c.strip()]
    else:
        display_channels = list(range(metadata.get('display_num_channels', metadata['num_channels'])))
    
    try:
        if file_type == 'npy':
            # 读取 NumPy 文件（需要读取所有原始通道以便计算差分）
            ext = os.path.splitext(info['filename'])[1].lower()
            if ext == '.npz':
                npz_file = np.load(info['path'])
                key = list(npz_file.keys())[0]
                full_data = npz_file[key]
            else:
                full_data = np.load(info['path'])
            
            # 根据数据方向切片（读取所有通道，先读取完整数据再降采样）
            if metadata['data_orientation'] == 'samples_first':
                if len(full_data.shape) == 1:
                    raw_data_full = full_data[start_idx:end_idx].reshape(-1, 1)
                else:
                    raw_data_full = full_data[start_idx:end_idx, :]
            else:
                raw_data_full = full_data[:, start_idx:end_idx].T
            
            # ★ 先滤波（使用原始采样率），再降采样 ★
            # Notch 滤波（必须在降采样前）
            if notch_freq:
                try:
                    freq = float(notch_freq)
                    raw_data_full, applied = apply_notch_filter(raw_data_full, fs, freq=freq, method=filter_method)
                    if applied:
                        logger.info(f"[NPY预降采样] 已应用 {freq}Hz 陷波滤波 ({filter_method})")
                except Exception as e:
                    logger.warning(f"[NPY预降采样] 陷波滤波失败: {e}")
            
            # 使用 Min-Max 降采样保留峰值
            raw_data = minmax_downsample(raw_data_full, downsample)
        else:
            # 读取 HDF5 文件（读取所有原始通道以便计算差分）
            if not H5PY_AVAILABLE:
                return jsonify({'error': 'h5py 未安装'}), 500
            
            with h5py.File(info['path'], 'r') as h5f:
                dataset = h5f[info['data_path']]
                
                # 先读取完整数据
                if metadata['data_orientation'] == 'samples_first':
                    raw_data_full = dataset[start_idx:end_idx, :]
                else:
                    raw_data_full = dataset[:, start_idx:end_idx].T
                
                # ★ 先滤波（使用原始采样率），再降采样 ★
                # Notch 滤波（必须在降采样前，否则 50Hz 信号会被 MinMax 破坏）
                if notch_freq:
                    try:
                        freq = float(notch_freq)
                        raw_data_full, applied = apply_notch_filter(
                            raw_data_full, 
                            fs, 
                            freq=freq, 
                            method=filter_method,
                            enhanced=enhanced_notch  # 传递增强标志
                        )
                        if applied:
                            mode = "ActiveNotch™" if enhanced_notch else "Standard"
                            logger.info(f"[预降采样] 已应用 {freq}Hz 陷波滤波 ({mode}, {filter_method})")
                    except Exception as e:
                        logger.warning(f"[预降采样] 陷波滤波失败: {e}")
                
                # 使用 Min-Max 降采样保留峰值
                raw_data = minmax_downsample(raw_data_full, downsample)
        
        # 如果是计算导联模式，进行差分计算
        if is_computed_mode and computed_leads:
            num_samples = raw_data.shape[0]
            output_data = np.zeros((num_samples, len(display_channels)), dtype=np.float32)
            output_channel_names = []
            
            for out_idx, disp_ch in enumerate(display_channels):
                if disp_ch < len(computed_leads):
                    # 计算导联：差分计算 (u+ - u-)
                    lead = computed_leads[disp_ch]
                    plus_data = raw_data[:, lead['plus_idx']]
                    minus_data = raw_data[:, lead['minus_idx']]
                    output_data[:, out_idx] = plus_data - minus_data
                    output_channel_names.append(lead['name'])
                else:
                    # 非计算导联：直接使用原始数据
                    other_idx = disp_ch - len(computed_leads)
                    if other_idx < len(other_channel_indices):
                        raw_ch_idx = other_channel_indices[other_idx]
                        output_data[:, out_idx] = raw_data[:, raw_ch_idx]
                        output_channel_names.append(display_channel_names[disp_ch])
                    else:
                        logger.warning(f"通道索引越界: {disp_ch}")
                        output_channel_names.append(f"Ch{disp_ch + 1}")
            # Notch 滤波已在降采样前应用，此处无需重复
            
            
            # 应用低通滤波
            if lp_cutoff:
                try:
                    cutoff = float(lp_cutoff)
                    output_data = apply_lowpass_filter(output_data, fs, cutoff=cutoff, method=filter_method)
                    logger.info(f"已应用 {cutoff}Hz 低通滤波 ({filter_method})")
                except Exception as e:
                    logger.warning(f"低通滤波失败: {e}")
            
            # 应用高通滤波
            if hp_cutoff:
                try:
                    cutoff = float(hp_cutoff)
                    output_data = apply_highpass_filter(output_data, fs, cutoff=cutoff, method=filter_method)
                    logger.info(f"已应用 {cutoff}Hz 高通滤波 ({filter_method})")
                except Exception as e:
                    logger.warning(f"高通滤波失败: {e}")
            
            data_list = output_data.tolist()
        else:
            # 非计算模式：直接返回请求的通道
            data = raw_data[:, display_channels] if len(raw_data.shape) > 1 else raw_data
            
            # Notch 滤波已在降采样前应用，此处无需重复


            # 收集哪些通道有独立滤波设置（用于跳过全局滤波）
            channels_with_local_filter = set()
            if channel_filters:
                for ch_idx_str in channel_filters.keys():
                    try:
                        ch_idx = int(ch_idx_str)
                        if ch_idx in display_channels:
                            channels_with_local_filter.add(display_channels.index(ch_idx))
                    except:
                        pass
            
            # 应用全局低通滤波（跳过有独立设置的通道）
            if lp_cutoff:
                try:
                    cutoff = float(lp_cutoff)
                    if len(data.shape) > 1:
                        for col_idx in range(data.shape[1]):
                            if col_idx not in channels_with_local_filter:
                                data[:, col_idx] = apply_lowpass_filter(data[:, col_idx], fs, cutoff=cutoff, method=filter_method)
                        logger.info(f"已应用 {cutoff}Hz 全局低通滤波 ({filter_method}) (跳过 {len(channels_with_local_filter)} 个独立配置通道)")
                    else:
                        if not channels_with_local_filter:
                            data = apply_lowpass_filter(data, fs, cutoff=cutoff, method=filter_method)
                            logger.info(f"已应用 {cutoff}Hz 低通滤波 ({filter_method})")
                except Exception as e:
                    logger.warning(f"低通滤波失败: {e}")
            
            # 应用全局高通滤波（跳过有独立设置的通道）
            if hp_cutoff:
                try:
                    cutoff = float(hp_cutoff)
                    if len(data.shape) > 1:
                        for col_idx in range(data.shape[1]):
                            if col_idx not in channels_with_local_filter:
                                data[:, col_idx] = apply_highpass_filter(data[:, col_idx], fs, cutoff=cutoff, method=filter_method)
                        logger.info(f"已应用 {cutoff}Hz 全局高通滤波 ({filter_method}) (跳过 {len(channels_with_local_filter)} 个独立配置通道)")
                    else:
                        if not channels_with_local_filter:
                            data = apply_highpass_filter(data, fs, cutoff=cutoff, method=filter_method)
                            logger.info(f"已应用 {cutoff}Hz 高通滤波 ({filter_method})")
                except Exception as e:
                    logger.warning(f"高通滤波失败: {e}")
            
            # 应用通道级滤波（覆盖全局滤波）
            if channel_filters and SCIPY_AVAILABLE:
                for ch_idx_str, filter_settings in channel_filters.items():
                    try:
                        # 找到该通道在 display_channels 中的位置
                        ch_idx = int(ch_idx_str)
                        if ch_idx in display_channels:
                            data_col_idx = display_channels.index(ch_idx)
                            ch_lp = filter_settings.get('lp')
                            ch_hp = filter_settings.get('hp')
                            ch_name = display_channel_names[ch_idx] if ch_idx < len(display_channel_names) else f"Ch{ch_idx}"
                            
                            # 提取单通道数据
                            if len(data.shape) > 1:
                                ch_data = data[:, data_col_idx].copy()
                            else:
                                ch_data = data.copy()
                            
                            # 应用通道级低通
                            if ch_lp:
                                ch_data = apply_lowpass_filter(ch_data.reshape(-1), fs, cutoff=float(ch_lp), method=filter_method)
                            
                            # 应用通道级高通
                            if ch_hp:
                                ch_data = apply_highpass_filter(ch_data.reshape(-1), fs, cutoff=float(ch_hp), method=filter_method)
                            
                            # 写回
                            if len(data.shape) > 1:
                                data[:, data_col_idx] = ch_data.reshape(-1)
                            else:
                                data = ch_data
                            
                            logger.info(f"通道 {ch_name}: LP={ch_lp or '∞'}, HP={ch_hp or 'DC'}")
                    except Exception as e:
                        logger.warning(f"通道级滤波失败 (ch {ch_idx_str}): {e}")
            
            data_list = data.tolist()
            output_channel_names = [display_channel_names[c] for c in display_channels if c < len(display_channel_names)]
        
        # 生成时间轴
        actual_samples = len(data_list)
        time_axis = [start_sec + (i * downsample / fs) for i in range(actual_samples)]
        
        return jsonify({
            'file_id': file_id,
            'start_sec': start_sec,
            'end_sec': end_sec,
            'channels': display_channels,
            'channel_names': output_channel_names,
            'downsample': downsample,
            'num_samples': actual_samples,
            'time': time_axis,
            'data': data_list,
            'is_computed_mode': is_computed_mode
        })
    
    except Exception as e:
        logger.error(f"数据读取失败: {e}")
        return jsonify({'error': f'数据读取失败: {str(e)}'}), 500


@ecg_api.route('/annotations/<file_id>', methods=['GET'])
def get_annotations(file_id):
    """
    获取标注数据
    
    Query params:
    - start: 起始时间（秒），默认全部
    - end: 结束时间（秒），默认全部
    - type: 标注类型筛选
    """
    if file_id not in FILE_CACHE:
        return jsonify({'error': '文件不存在或已过期'}), 404
    
    info = FILE_CACHE[file_id]
    metadata = info['metadata']
    annotations = info['annotations']
    fs = metadata['sampling_freq']
    
    # 解析参数
    notch_freq = request.args.get('notch')
    enhanced_notch = request.args.get('enhanced_notch') == 'true'  # 解析增强标志
    lp_cutoff = request.args.get('lp')
    hp_cutoff = request.args.get('hp')
    
    # 筛选
    result = []
    for annot in annotations:
        # 计算时间
        sample = annot.get('sample', annot.get('position', 0))
        time_sec = sample / fs if fs > 0 else 0
        
        # 时间范围筛选
        if start_sec is not None and time_sec < float(start_sec):
            continue
        if end_sec is not None and time_sec > float(end_sec):
            continue
        
        # 类型筛选
        if annot_type and annot.get('label', '') != annot_type:
            continue
        
        result.append({
            **annot,
            'time_sec': time_sec
        })
    
    return jsonify({
        'file_id': file_id,
        'annotations': result,
        'total': len(result)
    })


@ecg_api.route('/cleanup/<file_id>', methods=['DELETE'])
def cleanup_file(file_id):
    """清理临时文件"""
    if file_id not in FILE_CACHE:
        return jsonify({'message': '文件不存在'}), 200
    
    info = FILE_CACHE.pop(file_id)
    
    try:
        # 只有在非本地文件（即上传的临时文件）时才物理删除
        if not info.get('is_local', False) and os.path.exists(info['path']):
            os.remove(info['path'])
            
        logger.info(f"文件已清理: {file_id}")
        return jsonify({'message': '文件已清理'})
    except Exception as e:
        logger.warning(f"文件清理失败: {e}")
        return jsonify({'warning': f'文件清理失败: {str(e)}'}), 200


@ecg_api.route('/cleanup-all', methods=['DELETE'])
def cleanup_all():
    """清理所有临时文件"""
    count = 0
    for file_id in list(FILE_CACHE.keys()):
        info = FILE_CACHE.pop(file_id)
        try:
            if os.path.exists(info['path']):
                os.remove(info['path'])
                count += 1
        except Exception:
            pass
    
    logger.info(f"已清理 {count} 个临时文件")
    return jsonify({'message': f'已清理 {count} 个文件'})

@ecg_api.route('/export_image', methods=['POST'])
def export_image():
    """接收前端图片的 base64 数据，保存为临时文件并返回下载 URL"""
    try:
        data = request.json
        image_data = data.get('image_data', '')
        filename = data.get('filename', 'ecg_export.png')
        
        logger.info(f"收到导出请求，文件名: {filename}")
        
        # 解析 base64 数据
        if ',' in image_data:
            image_data = image_data.split(',')[1]
        
        image_bytes = base64.b64decode(image_data)
        
        # 保存到临时文件
        temp_id = str(uuid.uuid4())
        temp_path = os.path.join(TEMP_DIR, f'{temp_id}.png')
        
        logger.info(f"准备保存到: {temp_path}")
        
        with open(temp_path, 'wb') as f:
            f.write(image_bytes)
        
        logger.info(f"图片已保存: {temp_path}, 大小: {len(image_bytes)} bytes, 文件存在: {os.path.exists(temp_path)}")
        
        download_url = f'/api/ecg/download_image/{temp_id}?filename={filename}'
        logger.info(f"返回下载URL: {download_url}")
        
        return jsonify({
            'download_url': download_url
        })
    
    except Exception as e:
        logger.error(f"导出图片失败: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@ecg_api.route('/download_image/<temp_id>', methods=['GET'])
def download_image(temp_id):
    """下载临时图片文件"""
    try:
        filename = request.args.get('filename', 'ecg_export.png')
        temp_path = os.path.join(TEMP_DIR, f'{temp_id}.png')
        
        logger.info(f"下载请求: temp_id={temp_id}, filename={filename}, path={temp_path}")
        
        if not os.path.exists(temp_path):
            logger.error(f"文件不存在: {temp_path}")
            return jsonify({'error': '文件不存在'}), 404
        
        logger.info(f"开始发送文件: {temp_path}, 大小: {os.path.getsize(temp_path)} bytes")
        
        # 下载后删除临时文件
        def cleanup():
            try:
                os.remove(temp_path)
                logger.info(f"临时文件已删除: {temp_path}")
            except Exception as e:
                logger.warning(f"删除临时文件失败: {e}")
        
        response = send_file(
            temp_path,
            as_attachment=True,
            download_name=filename,
            mimetype='image/png'
        )
        
        # 显式设置 Content-Disposition 确保浏览器下载
        response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        logger.info(f"响应头已设置: Content-Disposition=attachment; filename=\"{filename}\"")
        
        # 在响应完成后清理
        response.call_on_close(cleanup)
        
        return response
    
    except Exception as e:
        logger.error(f"下载图片失败: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500
