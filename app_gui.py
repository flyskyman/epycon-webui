import os
import sys
import threading
import time
import webbrowser
import logging
import io
import tkinter as tk
from tkinter import filedialog, messagebox
from flask import Flask, request, jsonify, send_file, send_from_directory, make_response, render_template_string
from werkzeug.utils import secure_filename
from flask_cors import CORS
import base64
import glob
import json
from glob import iglob
import dataclasses
import struct
import csv
import tempfile
import shutil
from datetime import datetime, timezone
import socket
import atexit
import signal
import uuid
import concurrent.futures
import subprocess

# ========================================================
# 🛡️ 运行时环境
# ========================================================
current_dir = os.path.dirname(os.path.abspath(__file__))
candidates = [current_dir, os.path.join(current_dir, "epycon")]
for path in candidates:
    if os.path.exists(path) and path not in sys.path:
        sys.path.insert(0, path)

def resource_path(relative_path):
    """ 获取资源文件的绝对路径，兼容开发环境与 PyInstaller 打包环境 """
    try:
        base_path = sys._MEIPASS  # type: ignore
    except Exception:
        # 核心修复：使用脚本所在目录 current_dir，而不是运行时的 CWD
        base_path = current_dir
    return os.path.join(base_path, relative_path)

# ========================================================
# 🔒 单实例检查和端口管理
# ========================================================
LOCK_FILE = None

def check_single_instance():
    """检查是否已有实例在运行"""
    global LOCK_FILE
    lock_path = os.path.join(tempfile.gettempdir(), 'epycon_gui.lock')
    current_pid = os.getpid()
    is_subprocess = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
    
    try:
        # 尝试创建锁文件
        if os.path.exists(lock_path):
            # 检查锁文件中的 PID 是否还在运行
            try:
                with open(lock_path, 'r') as f:
                    lock_data = f.read().strip().split(',')
                    old_pid = int(lock_data[0])
                    lock_parent_pid = int(lock_data[1]) if len(lock_data) > 1 else None
                
                # 如果当前进程是 Reloader 的子进程，且父进程 PID 相同，则允许
                if is_subprocess and lock_parent_pid is not None:
                    parent_pid = os.getppid() if hasattr(os, 'getppid') else None
                    if parent_pid == lock_parent_pid:
                        # 这是同一个 Reloader 启动的子进程，允许继续
                        return True
                
                # 检查进程是否存在
                if os.name == 'nt':
                    try:
                        import psutil
                        # 检查 old_pid 和锁文件中的父进程是否都还活着
                        if psutil.pid_exists(old_pid):
                            print(f"⚠️ 检测到另一个实例正在运行 (PID: {old_pid})")
                            print("请先关闭其他实例，或等待几秒后重试。")
                            return False
                    except ImportError:
                        # 如果没有 psutil，使用简单的时间检查
                        file_age = time.time() - os.path.getmtime(lock_path)
                        if file_age < 60:  # 如果锁文件在 1 分钟内创建，认为还在使用
                            # 但如果我们是子进程且父 PID 相同，则允许
                            if not (is_subprocess and lock_parent_pid is not None):
                                print(f"⚠️ 检测到锁文件 (创建于 {int(file_age)} 秒前)")
                                print("如果确认没有其他实例运行，请手动删除锁文件：")
                                print(f"   {lock_path}")
                                return False
            except (ValueError, IOError):
                pass
            
            # 如果进程不存在，删除旧锁文件
            try:
                os.remove(lock_path)
            except Exception:
                pass
        
        # 如果这是 Reloader 的子进程，不要重新创建锁文件
        if is_subprocess:
            return True
        
        # 创建新锁文件（记录父进程 PID 用于 Reloader 识别）
        parent_pid = os.getpid()  # 在主进程中，自己就是"父"
        LOCK_FILE = open(lock_path, 'w')
        LOCK_FILE.write(f"{parent_pid},{parent_pid}")  # 格式: current_pid, parent_pid
        LOCK_FILE.flush()
        
        # Windows 上尝试加锁
        if os.name == 'nt':
            import msvcrt
            try:
                msvcrt.locking(LOCK_FILE.fileno(), msvcrt.LK_NBLCK, 1)
            except Exception:
                pass
        
        return True
    except Exception as e:
        print(f"单实例检查失败: {e}")
        return True  # 出错时允许继续运行

def check_port_available(port=5050):
    """检查端口是否可用"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(('127.0.0.1', port))
        sock.close()
        return True
    except OSError:
        return False

def _is_our_process(pid):
    """只识别本应用自己的旧实例：打包 exe，或命令行带 app_gui/epycon 的 python。
    识别不了一律返回 False（宁可换端口也不误杀其他程序）。"""
    try:
        import psutil
        p = psutil.Process(pid)
        name = p.name().lower()
        if 'workmatedatacenter' in name:
            return True
        if name.startswith('python'):
            cmdline = ' '.join(p.cmdline()).lower()
            return 'app_gui' in cmdline or 'workmatedatacenter' in cmdline or 'epycon' in cmdline
    except Exception:
        pass
    return False


def kill_port_occupier(port=5050):
    """
    尝试终止占用端口的本应用旧实例（其他程序一律规避，由调用方换端口）。
    返回: (bool, str) -> (是否成功/跳过, 占用者名称)
    """
    import subprocess
    try:
        # 获取当前进程 PID 和父进程 PID
        my_pid = os.getpid()
        ppid = os.getppid()
        
        if os.name == 'nt':
            # Windows 逻辑
            result = subprocess.run(['netstat', '-ano'], capture_output=True, text=True, timeout=5)
            for line in result.stdout.split('\n'):
                if f':{port}' in line and 'LISTENING' in line:
                    parts = line.split()
                    if parts:
                        pid_str = parts[-1]
                        try:
                            target_pid = int(pid_str)
                            # 禁止自杀或杀父（Reloader 环境下常见）
                            if target_pid == my_pid or target_pid == ppid:
                                return False, "Self/Parent"

                            # 只清理可识别的自家旧实例，其他程序一律规避
                            if not _is_our_process(target_pid):
                                print(f"🏷️  端口 {port} 被其他程序占用 (PID: {target_pid})，将规避而非终止。")
                                return False, f"PID {target_pid}"

                            pname = "旧实例"
                            print(f"发现占用者: {pname} (PID: {target_pid})")
                            subprocess.run(['taskkill', '/F', '/PID', str(target_pid)], timeout=5)
                            time.sleep(1.5)
                            return True, pname
                        except Exception: pass
        else:
            # macOS / Linux 逻辑 (使用 lsof)
            try:
                cmd = ['lsof', '-i', f':{port}', '-sTCP:LISTEN', '-n', '-P']
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                lines = [l for l in result.stdout.split('\n') if l.strip()]
                if len(lines) > 1:
                    parts = lines[1].split()
                    pname = parts[0]
                    pid_str = parts[1]
                    try:
                        target_pid = int(pid_str)
                        if target_pid == my_pid or target_pid == ppid:
                            # 端口是被自己或父进程占用的（例如 Flask Reloader 启动中），跳过清理
                            return False, "Self/Parent"
                            
                        # 只清理可识别的自家旧实例，其他程序（含系统服务）一律规避
                        if not _is_our_process(target_pid):
                            print(f"🏷️  端口 {port} 被其他程序 '{pname}' 占用，将规避而非终止。")
                            return False, pname

                        print(f"发现占用者: {pname} (PID: {target_pid})")
                        subprocess.run(['kill', '-9', str(target_pid)], timeout=5)
                        time.sleep(1.5)
                        return True, pname
                    except Exception: pass
            except FileNotFoundError:
                print("⚠️  系统缺少 'lsof' 指令。")
    except Exception as e:
        print(f"清理端口失败: {e}")
    return False, "None"

def cleanup_on_exit():
    """程序退出时的清理工作"""
    global LOCK_FILE
    if LOCK_FILE:
        try:
            LOCK_FILE.close()
            lock_path = os.path.join(tempfile.gettempdir(), 'epycon_gui.lock')
            if os.path.exists(lock_path):
                os.remove(lock_path)
        except Exception:
            pass

# 注册退出清理
atexit.register(cleanup_on_exit)

# ========================================================
# 🔧 强制 UTF-8 写入
# ========================================================
try:
    import builtins
    _real_open = builtins.open
    class UTF8EnforcedOpen:
        def __enter__(self):
            self.original_open = builtins.open
            def new_open(file, mode='r', buffering=-1, encoding=None, errors=None, newline=None, closefd=True, opener=None):
                if 'w' in mode or 'a' in mode:
                    encoding = 'utf-8'
                    errors = 'replace' 
                return self.original_open(file, mode, buffering, encoding, errors, newline, closefd, opener)
            builtins.open = new_open
        def __exit__(self, exc_type, exc_val, exc_tb):
            builtins.open = self.original_open
except ImportError: pass

# ========================================================
# 📦 导入 Epycon
# ========================================================
try:
    from epycon.config.byteschema import ENTRIES_FILENAME, LOG_PATTERN, MASTER_FILENAME
    from epycon.iou import LogParser, EntryPlanter, readentries
    from epycon.iou.parsers import _readmaster
    from epycon.utils.person import Tokenize
except ImportError as e:
    print(f"无法加载 Epycon。\n{e}")
    if __name__ == "__main__":
        sys.exit(1)
    else:
        raise  # 在测试环境中抛出异常供 pytest 捕获

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

# gzip 响应压缩：波形 JSON 可压 2-3 倍。
# 级别取 1：localhost 为主的场景压缩开销必须足够低（实测 level 6 的 CPU 开销
# 会超过本地传输收益），level 1 仍有 ~2x 压缩率
try:
    from flask_compress import Compress
    app.config['COMPRESS_LEVEL'] = 1
    Compress(app)
except ImportError:
    pass  # 未安装时退化为不压缩，功能不受影响

# 注册 ECG API Blueprint
try:
    from epycon.api_ecg import ecg_api
    app.register_blueprint(ecg_api)
    print("✅ ECG API 已加载")
except ImportError as e:
    print(f"⚠️ ECG API 未加载 (可选): {e}")


# ========================================================
# 📝 [核心] 全局日志配置 (同时输出到文件和控制台)
# ========================================================
LOG_PATH = os.path.join(tempfile.gettempdir(), "epycon_gui.log")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_PATH, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("epycon_web")

class MemoryLogHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.logs = []
        self.setLevel(logging.DEBUG)  # 捕获所有级别的日志
    def emit(self, record):
        self.logs.append(self.format(record))

# ========================================================
# 🚀 异步任务管理
# ========================================================
executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
TASKS = {} # taskId -> { 'status': 'running', 'progress': 0, 'logs': [], 'result': None }
# ========================================================
@dataclasses.dataclass
class MutableEntry:
    timestamp: float
    group: str
    message: str
    fid: str = '0'
    duration: float = 0
    color: int = 0

# ========================================================
# ⚖️ [核心] 全自动时间归一化 (Unix Seconds)
# ========================================================
def to_unix_seconds(val):
    try:
        if isinstance(val, datetime):
            return val.replace(tzinfo=timezone.utc).timestamp()
        num = float(val)
        if num > 100_000_000_000_000_000: # FILETIME
            return (num - 116444736000000000) / 10_000_000.0
        if num > 100_000_000_000: # Milliseconds
            return num / 1000.0
        return num
    except Exception:
        return 0.0

# ========================================================
# 🛠️ [核心] entries.log 去壳
# ========================================================
def prepare_standard_entries_file(original_path):
    try:
        with open(original_path, 'rb') as f:
            raw = f.read(256)
        valid_gids = [1, 2, 3, 4, 5, 6, 17]
        target_offset = 0
        gid_128 = struct.unpack_from('<H', raw, 128)[0]
        if gid_128 in valid_gids:
            target_offset = 128
        else:
            for i in range(0, 200, 4):
                gid = struct.unpack_from('<H', raw, i)[0]
                if gid in valid_gids and i+220 < len(raw):
                    if struct.unpack_from('<H', raw, i+220)[0] in valid_gids:
                        target_offset = i
                        break
        # [Phase 2.2] 性能快速路径：标准格式 (offset=36) 无需处理
        if target_offset == 0 or target_offset == 36:
            return original_path
            
        if target_offset > 0:
            temp_dir = tempfile.gettempdir()
            temp_path = os.path.join(temp_dir, f"std_{os.path.basename(original_path)}")
            with open(original_path, 'rb') as src, open(temp_path, 'wb') as dst:
                dst.write(b'\x00' * 36) 
                src.seek(target_offset)
                shutil.copyfileobj(src, dst)
            return temp_path
        return original_path
    except Exception: return original_path

# ========================================================
# 🧹 [终极核心] V68.1 融合版 (Strict ASCII + Semantic SNR)
# ========================================================
def is_semantic_garbage(text):
    """
    语义信噪比检测 (V67.7 核心算法)
    判断字符串是否由大量的 ASCII 符号组成（视觉乱码）。
    例如: "((m(*" 或 "\\;8\\;B" 虽然是 ASCII，但应被剔除。
    """
    if not text: return True
    
    # 统计字符构成
    alpha_num_count = 0  # 字母、数字
    risky_sym_count = 0  # 风险符号 (括号, 斜杠, @, #, etc.)
    safe_sym_count = 0   # 安全符号 (空格, ., -, :)
    
    for char in text:
        if char.isalnum(): 
            alpha_num_count += 1
        elif char in " .-:/": 
            # 这些是时间、数值、日期中常见的安全符号，不计入风险
            safe_sym_count += 1
        else:
            # 风险符号：\ | ( ) [ ] { } < > ? ! @ # $ % ^ & * _ = + ; ' " ` ~
            risky_sym_count += 1
            
    total_len = len(text)
    
    # [逻辑 1] 极短字符串 (1-2字符)
    # 必须是字母数字，或者是明确的白名单单字
    if total_len <= 2:
        # 如果包含风险符号 (如 "m(" ) -> 删
        if risky_sym_count > 0: return True
        
        # 单字母/双字母检查 (白名单机制)
        # 允许纯数字 (如 "1", "12")
        if text.isdigit(): return False
        
        # 允许特定含义的字母组合 (如 "A1", "V2")
        if text.isalnum() and any(c.isdigit() for c in text): return False
        
        # 纯字母检查：只保留常见标记
        # V68.0 的白名单：A, V, P, R, T, S, M, I, W (波形/导联/事件标记)
        if text.isalpha():
            if text.upper() not in ['A', 'V', 'P', 'R', 'T', 'S', 'M', 'I', 'W', 'L', 'B']:
                return True # "e", "q" 等无意义字母视为噪点
        
        return False

    # [逻辑 2] 信噪比失衡 (符号比字多)
    # 例如 "((m(*" -> Risky=4, Alpha=1 -> 删
    # 例如 "\;8\;B" -> Risky=4, Alpha=3 -> 删
    if risky_sym_count >= alpha_num_count and risky_sym_count > 1:
        return True
        
    # [逻辑 3] 稀疏内容检测
    # 如果有效文字极少 (<30%) 且总长度 > 4
    if total_len > 4:
        ratio = alpha_num_count / total_len
        if ratio < 0.3: return True
        
    return False

def clean_entries_content(entries):
    cleaned_list = []
    
    # [RELAXED] 仅过滤核心不可见组 (与前端一致: 5=HIDDEN, 8=UNK)
    # 之前过滤了 SYS/WARN/ERROR 等，导致数据缺失
    GID_BLACKLIST = {'5', '8'} 
    
    for e in entries:
        raw_msg = str(e.message)
        raw_grp = str(e.group)

        # 1. Null 截断
        if '\x00' in raw_msg: raw_msg = raw_msg.split('\x00')[0]
        if '\x00' in raw_grp: raw_grp = raw_grp.split('\x00')[0]

        raw_msg = raw_msg.strip()
        raw_grp = raw_grp.strip()

        # 2. 基础非空校验
        if not raw_msg: continue
        
        if raw_grp in ('UNK', 'HIDDEN'): continue
        
        # 3. [STRICT] 字符编码清洗 (严格匹配前端逻辑)
        # 前端 JS: rawText.replace(/[^\x20-\x7E\t]/g, '').trim()
        # 这意味着只保留 ASCII 可打印字符 (32-126) 和 Tab (9)
        # 所有 Latin-1 字符 (如 °, µ) 都会被丢弃，以确保与网页查看器一致
        raw_msg = ''.join(c for c in raw_msg if 32 <= ord(c) <= 126 or ord(c) == 9)
        
        # 6. 组装
        new_e = MutableEntry(
            timestamp=to_unix_seconds(e.timestamp),
            group=raw_grp,
            message=raw_msg,
            fid=getattr(e, 'fid', '0')
        )
        cleaned_list.append(new_e)

    # [ORDER] 恢复按时间戳排序，以匹配网页查看器的默认行为 (Time Sort)
    # 文件本身可能有物理乱序 (如 NOTE 在末尾但时间较早)，必须排序才能与网页一致
    cleaned_list.sort(key=lambda x: x.timestamp)
    return cleaned_list

# ========================================================
# 📐 辅助工具
# ========================================================
# [REFACTOR] 使用核心库的统一通道映射函数
from epycon.core.helpers import get_channel_mappings

def export_global_csv(entries, target_dir, study_id_for_name):
    try:
        filename = f"{study_id_for_name}_All_Entries_Normalized.csv"
        path = os.path.join(target_dir, filename)
        with open(path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['UnixSeconds', 'Group', 'Message'])
            for e in entries:
                writer.writerow([f"{e.timestamp:.3f}", e.group, e.message])
        return filename
    except Exception: return None

# --- 核心转换逻辑 ---
def execute_epycon_conversion(cfg):
    mem_handler = MemoryLogHandler()
    mem_handler.setFormatter(logging.Formatter('%(message)s')) # 内存日志只记录纯消息
    
    # 获取全局定义的 logger
    conv_logger = logging.getLogger("epycon_web")
    conv_logger.setLevel(logging.DEBUG)  # 确保捕获所有级别
    conv_logger.propagate = False  # 不传播到父 logger，只用我们的处理器
    
    # [MODIFIED] 现在接受 task_id 以更新状态
    task_id = cfg.get("_task_id")
    
    def update_progress(p, log_msg=None):
        if task_id in TASKS:
            TASKS[task_id]['progress'] = p
            if log_msg:
                TASKS[task_id]['logs'].append(log_msg)

    # [FIX] 定义 script_dir 供配置初始化使用
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 确保配置格式正确
    cfg = _prepare_conversion_config(cfg, script_dir)
    input_folder = cfg["paths"]["input_folder"]
    output_folder = cfg["paths"]["output_folder"]
    
    conv_logger.info(f"🔍 最终路径: {input_folder}, exists={os.path.exists(input_folder)}")
    
    if not input_folder or not os.path.exists(input_folder):
        conv_logger.error(f"❌ [v2024] 输入文件夹不存在: {input_folder}")
        update_progress(0, "输入文件夹不存在")
        res_logs = mem_handler.logs
        conv_logger.removeHandler(mem_handler)
        return False, res_logs
    
    utf8_guard = UTF8EnforcedOpen()
    
    try:
        with utf8_guard:
            output_fmt = cfg["data"]["output_format"]
            # 兼容 "00000000" 和 "00000000.log" 两种格式
            valid_datalogs = set(
                f.rstrip(".log") if f.endswith(".log") else f
                for f in cfg["data"]["data_files"]
            )
            
            valid_studies = set(cfg["paths"].get("studies", []))
            study_list = _get_study_list(input_folder, valid_studies)
            
            if not study_list:
                conv_logger.warning("⚠️ 未找到任何有效的学习文件 (study folders)。")
                update_progress(0, "未找到任何学习文件")
                res_logs = mem_handler.logs
                conv_logger.removeHandler(mem_handler)
                return False, res_logs
            
            if valid_studies:
                conv_logger.info(f"📁 已过滤 studies: {len(study_list)} 个符合条件")

            processed_count = 0
            
            # 获取配置选项（merge/credentials 由 epycon.conversion 内部处理）
            pseudonymize = cfg["global_settings"].get("pseudonymize", False)

            total_studies = len(study_list)
            for idx, study_path in enumerate(study_list):
                study_id = os.path.basename(study_path)
                # 计算总进度百分比 (0-100)
                current_p = int((idx / total_studies) * 100)
                update_progress(current_p, f"正在处理 study ({idx+1}/{total_studies}): {study_id}")
                
                logs_in_study = sorted(list(iglob(os.path.join(study_path, LOG_PATTERN))))
                if not logs_in_study: continue

                # [UX] 智能判断：如果输出目录名已经等于 study_id，则不再创建子目录
                if os.path.basename(os.path.normpath(output_folder)) == study_id:
                    study_out_dir = output_folder
                else:
                    study_out_dir = os.path.join(output_folder, study_id)

                try: os.makedirs(study_out_dir, exist_ok=True)
                except Exception: pass
                
                # --- [Step 0] 读取 MASTER 文件并处理匿名化 ---
                try:
                    master_info = _readmaster(os.path.join(study_path, MASTER_FILENAME))
                except (IOError, FileNotFoundError):
                    conv_logger.warning(f"⚠️ 未找到 MASTER 文件: {study_id}")
                    master_info = {"id": "", "name": ""}
                
                if pseudonymize:
                    tokenizer = Tokenize(8, {})
                    subject_id = tokenizer()
                    subject_name = ""
                    if master_info["id"]:
                        conv_logger.info(f"🔒 匿名化: {master_info['id']} -> {subject_id}")
                else:
                    subject_id = master_info["id"]
                    subject_name = master_info["name"]

                # --- [Step 1] 读取并清洗 Entries ---
                all_entries_norm = []
                epath = os.path.join(study_path, ENTRIES_FILENAME)
                need_entries = cfg["entries"]["convert"] or (cfg["data"]["output_format"] == "h5" and cfg["data"]["pin_entries"])
                conv_logger.info(f"📋 Entries 配置: convert={cfg['entries']['convert']}, pin_entries={cfg['data']['pin_entries']}, need_entries={need_entries}")
                
                if need_entries:
                    if os.path.exists(epath):
                        try:
                            conv_logger.info(f"🔎 读取标注: {os.path.basename(epath)}")
                            clean_path = prepare_standard_entries_file(epath) 
                            native_entries = readentries(clean_path, version=cfg["global_settings"]["workmate_version"])
                            conv_logger.info(f"📊 原始标注条数: {len(native_entries)}")
                            
                            all_entries_norm = clean_entries_content(native_entries)
                            
                            if clean_path != epath and os.path.exists(clean_path):
                                try: os.remove(clean_path)
                                except Exception: pass
                                
                            conv_logger.info(f"✅ 归一化标注: {len(all_entries_norm)} 条 (ASCII+SNR双重净化)")
                            
                            # [FIX] 仅当用户启用 export 时才保留这份中间文件
                            if cfg["entries"]["convert"]:
                                export_global_csv(all_entries_norm, study_out_dir, study_id)
                        except Exception as e:
                            import traceback
                            conv_logger.warning(f"⚠️ 读取失败: {e}\n{traceback.format_exc()}")
                    else:
                        conv_logger.info(f"ℹ️ 标注文件不存在: {epath}")
                
                # --- [Step 1.5] 导出汇总 entries CSV (summary_csv) ---
                # [FIX] 仅当 convert=True 时才导出 summary (与 UI 逻辑一致)
                if cfg["entries"]["convert"] and cfg["entries"].get("summary_csv", False) and all_entries_norm:
                    try:
                        summary_path = os.path.join(study_out_dir, "entries_summary.csv")
                        entryplanter = EntryPlanter(all_entries_norm)
                        filter_groups = cfg["entries"].get("filter_annotation_type", [])
                        criteria = {
                            "fids": list(valid_datalogs) if valid_datalogs else [],
                            "groups": filter_groups if filter_groups else [],
                        }
                        entryplanter.savecsv(summary_path, criteria=criteria)
                        conv_logger.info(f"📊 导出汇总标注: entries_summary.csv")
                    except Exception as e:
                        conv_logger.warning(f"⚠️ 汇总 CSV 导出失败: {e}")

                # --- [Step 2] 数据转换：统一调用核心库实现 (epycon.conversion) ---
                # 此前这里维护着与 __main__.py 平行的 merge/normal 实现，
                # 已漂移出多个标注定位缺陷（墙钟偏移映射、int 截断、e.msg 字段名、
                # x32 时间戳误读等），现收敛到 epycon/conversion.py 单一实现
                from epycon.conversion import convert_study

                extra_attrs = {
                    "PatientName": subject_name,
                    "PatientID": subject_id,
                }

                try:
                    n_processed = convert_study(
                        study_path, study_id, study_out_dir, cfg, all_entries_norm,
                        subject_id=subject_id, subject_name=subject_name,
                        logger=conv_logger, extra_attributes=extra_attrs,
                    )
                    processed_count += n_processed
                    if n_processed == 0:
                        conv_logger.warning(f"⚠️ {study_id}: 未找到有效数据文件")
                except Exception as conv_err:
                    import traceback
                    conv_logger.error(f"❌ {study_id} 转换失败: {conv_err}\n{traceback.format_exc()}")
                    continue

            update_progress(100, "✅ 转换圆满完成")
            conv_logger.info(f"✅ 全部完成! 共处理 {processed_count} 个文件")
            res_logs = mem_handler.logs
            conv_logger.removeHandler(mem_handler)
            return True, res_logs
        
    except Exception as e:
        import traceback
        err = traceback.format_exc()
        conv_logger.error(f"❌ 系统错误:\n{err}")
        res_logs = mem_handler.logs
        conv_logger.removeHandler(mem_handler)
        return False, res_logs

# --- Preferences API (Persistence) ---
PREFS_FILE = os.path.join(os.path.expanduser("~"), ".epycon_prefs.json")

@app.route('/api/save-prefs', methods=['POST'])
def save_prefs():
    """保存用户偏好设置 (主要是路径)"""
    try:
        data = request.json
        curr = {}
        if os.path.exists(PREFS_FILE):
            try:
                # [FIX] 处理空文件或无效JSON导致的问题
                if os.path.getsize(PREFS_FILE) > 0:
                    with open(PREFS_FILE, 'r', encoding='utf-8') as f:
                        curr = json.load(f)
            except Exception as read_err:
                print(f"Warning: Failed to read prefs: {read_err}")
                pass
        
        # [FIX] 确保 curr 是字典
        if not isinstance(curr, dict):
            curr = {}

        # 合并请求数据（此前漏了这一步，"保存偏好"一直是写回旧内容的空操作）
        if isinstance(data, dict):
            curr.update(data)

        with open(PREFS_FILE, 'w', encoding='utf-8') as f:
            json.dump(curr, f, indent=2, ensure_ascii=False)
            
        return jsonify({"status": "success"})
    except Exception as e:
        print(f"❌ Error in save_prefs: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/load-prefs', methods=['GET'])
def load_prefs():
    """加载用户偏好设置"""
    if not os.path.exists(PREFS_FILE):
        return jsonify({})
    try:
        # [FIX] 处理空文件
        if os.path.getsize(PREFS_FILE) == 0:
             return jsonify({})

        with open(PREFS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/')
def home():
    """ 访问主页中心 """
    html_path = resource_path('ui/index.html')
    if not os.path.exists(html_path):
        return f"UI 首页缺失，请检查路径: {html_path}", 404
        
    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return render_template_string(content)
    except Exception as e:
        return f"无法加载首页: {e}", 500

@app.route('/ui/<path:filename>')
def serve_ui(filename):
    """
    统一处理 /ui/ 路径下的静态资产。
    包括 HTML（自动注入导航）、JS、CSS 和图像。
    """
    import re
    from flask import make_response, send_from_directory
    
    ui_base = resource_path('ui')
    # 安全性检查：首先清理文件名，防止路径穿越
    filename = secure_filename(filename)
    file_full_path = os.path.join(ui_base, filename)
    
    # 进一步确保路径仍在 ui_base 目录下
    if not os.path.abspath(file_full_path).startswith(os.path.abspath(ui_base)):
        return "非法的文件请求", 403

    if not os.path.exists(file_full_path):
        return f"资产未找到: {filename}", 404
        
    # 处理非 HTML 静态资源 (tailwind.js, vue.js 等)
    if not filename.lower().endswith('.html'):
        return send_from_directory(ui_base, filename)
        
    # 处理子页 HTML (自动注入返回主中心的按钮)
    try:
        print(f"[DEBUG] Serving UI file: {file_full_path}")
        with open(file_full_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        return f"读取文件失败: {e}", 500

    # 仅向非 index.html 的 HTML 文件注入返回导航
    if 'index.html' not in filename.lower():
        nav_injection = """
        <div id="epycon-home-nav" style="position:fixed; top:12px; right:12px; z-index:9999; opacity:0.9;">
            <a href="/" style="background:#0f172a; color:white; padding:8px 16px; border-radius:8px; text-decoration:none; font-size:13px; font-family:sans-serif; font-weight:500; box-shadow:0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -1px rgba(0,0,0,0.06); border:1px solid #334155;">
                ← 返回数据中心
            </a>
        </div>
        """
        # 在 <body> 标签后注入
        body_match = re.search(r'<\s*body[^>]*>', content, re.IGNORECASE | re.DOTALL)
        if body_match:
            end_pos = body_match.end()
            content = content[:end_pos] + nav_injection + content[end_pos:]
        else:
            content = nav_injection + content
            
    response = make_response(content)
    response.headers['Content-Type'] = 'text/html; charset=utf-8'
    # ★ 强制禁用缓存，解决更新不生效的问题
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/vendor/<path:filename>')
def serve_vendor_compatibility(filename):
    """ 
    兼容逻辑：允许根路径下的 index.html 通过相对路径 'vendor/...' 访问资源。
    这使得 HTML 在直接双击打开和通过 Flask 访问时都能找到 CSS/JS。
    """
    return send_from_directory(resource_path('ui/vendor'), filename)

@app.route('/<filename>.html')
def serve_html_compatibility(filename):
    """
    兼容逻辑：允许根路径下的请求重定向到 /ui/ 路径。
    例如请求 /editor.html 会映射到 serve_ui('editor.html')
    """
    return serve_ui(f"{filename}.html")

@app.route('/run-direct', methods=['POST'])
def run_direct():
    # [Phase 2.1] JSON Schema 验证 - 防止无效输入
    from jsonschema import validate, ValidationError
    
    CONFIG_API_SCHEMA = {
        "type": "object",
        "properties": {
            "paths": {
                "type": "object",
                "properties": {
                    "input_folder": {"type": "string"},
                    "output_folder": {"type": "string"},
                    "studies": {"type": "array", "items": {"type": "string"}}
                }
            },
            "data": {
                "type": "object",
                "properties": {
                    "output_format": {"type": "string", "enum": ["h5", "csv"]},
                    "merge_logs": {"type": "boolean"},
                    "pin_entries": {"type": "boolean"},
                    "compression": {"type": ["string", "null"]},
                    "compression_opts": {"type": ["integer", "null"]}
                }
            },
            "entries": {"type": "object"},
            "global_settings": {"type": "object"}
        }
    }
    
    try:
        config_data = request.json or {}
        
        # 验证输入 Schema
        try:
            validate(config_data, CONFIG_API_SCHEMA)
        except ValidationError as ve:
            return jsonify({
                "status": "error", 
                "message": f"配置格式错误: {ve.message}",
                "path": list(ve.path)
            }), 400
        
        task_id = str(uuid.uuid4())
        
        # 初始化任务状态
        TASKS[task_id] = {
            'status': 'running',
            'progress': 0,
            'logs': [],
            'result': None
        }
        
        config_data["_task_id"] = task_id # 注入 taskId
        
        # 异步启动转换
        def background_task():
            try:
                success, logs = execute_epycon_conversion(config_data)
                TASKS[task_id]['status'] = 'completed' if success else 'failed'
                TASKS[task_id]['result'] = {'success': success, 'logs': logs}
            except Exception as e:
                import traceback
                error_msg = f"Task backend error: {str(e)}\n{traceback.format_exc()}"
                TASKS[task_id]['status'] = 'failed'
                TASKS[task_id]['result'] = {'success': False, 'logs': [error_msg]}

        executor.submit(background_task)
        
        return jsonify({"status": "accepted", "task_id": task_id})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/task-status/<task_id>', methods=['GET'])
def get_task_status(task_id):
    task = TASKS.get(task_id)
    if not task:
        return jsonify({"status": "not_found"}), 404
    
    # 提取新日志并清空（防止重复传输）
    new_logs = task['logs']
    task['logs'] = []
    
    return jsonify({
        "status": task['status'],
        "progress": task['progress'],
        "logs": new_logs,
        "result": task['result']
    })

# --- 新增的辅助分拆函数 ---
def _prepare_conversion_config(cfg, script_dir):
    if not isinstance(cfg, dict): cfg = {}
    if "paths" not in cfg or not isinstance(cfg["paths"], dict): cfg["paths"] = {}
    cfg["paths"].setdefault("input_folder", "examples/data")
    cfg["paths"].setdefault("output_folder", "examples/data/out")
    cfg["paths"].setdefault("studies", [])
    
    if "data" not in cfg or not isinstance(cfg["data"], dict): cfg["data"] = {}
    cfg["data"].setdefault("output_format", "h5")
    cfg["data"].setdefault("data_files", [])
    cfg["data"].setdefault("merge_logs", False)
    cfg["data"].setdefault("pin_entries", True)
    cfg["data"].setdefault("compression", None)  # [NEW] 可选: 'lzf', 'gzip'
    cfg["data"].setdefault("compression_opts", None)
    
    if "entries" not in cfg or not isinstance(cfg["entries"], dict): cfg["entries"] = {}
    cfg["entries"].setdefault("convert", False)
    cfg["entries"].setdefault("output_format", "csv")
    
    if "global_settings" not in cfg or not isinstance(cfg["global_settings"], dict): cfg["global_settings"] = {}
    cfg["global_settings"].setdefault("workmate_version", "4.3.2")
    cfg["global_settings"].setdefault("processing", {"chunk_size": 1024})

    # 路径绝对化
    if not os.path.isabs(cfg["paths"]["input_folder"]):
        cfg["paths"]["input_folder"] = os.path.normpath(os.path.join(script_dir, cfg["paths"]["input_folder"]))
    if not os.path.isabs(cfg["paths"]["output_folder"]):
        cfg["paths"]["output_folder"] = os.path.normpath(os.path.join(script_dir, cfg["paths"]["output_folder"]))
    return cfg

def _get_study_list(input_folder, valid_studies):
    direct_logs = list(iglob(os.path.join(input_folder, "*.log")))
    study_list = []
    if direct_logs:
        study_list.append(input_folder)
    else:
        for sub_path in iglob(os.path.join(input_folder, '**')):
            if os.path.isdir(sub_path):
                study_name = os.path.basename(sub_path)
                if valid_studies and study_name not in valid_studies:
                    continue
                # 检查目录内是否存在 log 文件
                if any(iglob(os.path.join(sub_path, LOG_PATTERN))):
                    study_list.append(sub_path)
    return sorted(study_list)

@app.route('/api/select-folder', methods=['GET'])
def api_select_folder():
    """
    选择文件夹，在 macOS 上使用 AppleScript 避开线程安全问题。
    """
    try:
        path = ""
        if sys.platform == 'darwin':
            # macOS AppleScript 逻辑
            cmd = ['osascript', '-e', 'tell application "System Events" to activate',
                   '-e', 'set theFolder to choose folder with prompt "请选择数据路径:"',
                   '-e', 'POSIX path of theFolder']
            import subprocess
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0:
                path = res.stdout.strip()
        else:
            # Windows/Other Tkinter 逻辑
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            path = filedialog.askdirectory()
            root.destroy()
            
        if path:
            path = os.path.normpath(path)
        return jsonify({"path": path})
    except Exception as e:
        return jsonify({"error": str(e), "path": ""})


# --- WorkMate Log Parser 服务器端扫描 ---
# 只返回原始字节（base64），解析统一由前端 JS 完成，避免两套解析器漂移。
# 以下扫描规则与 ui/WorkMate_Log_Parser.html 的 SCAN_RULES 必须逐条一致，
# 否则同一目录在 Flask/file:// 两种模式扫出不同结果——
# tests/test_api_workmate.py::TestScanRulesSync 守卫。
# _gsdata_ 是 GoodSync 的同步状态/历史目录，内含 entries.log 版本副本，
# 扫进来即假阳性 study 并触发伪漂移
_WORKMATE_SKIP_DIRS = {'__pycache__', '$recycle.bin', 'system volume information',
                       '_gsdata_'}
_WORKMATE_HIDDEN_PREFIXES = ('.', '~')
_WORKMATE_TARGET_FILES = ('entries.log', 'master')
_WORKMATE_MAX_DEPTH = 8


def _scan_workmate_root(root, *, max_file_mb=50, max_total_mb=64,
                        max_depth=_WORKMATE_MAX_DEPTH, max_studies=500,
                        time_budget_s=20):
    """递归扫描 root，收集含 entries.log（可选 MASTER）的 study 目录。

    安全边界：只读取文件名精确匹配 entries.log / MASTER（大小写不敏感）的
    文件内容；隐藏目录与系统目录剪枝；深度/数量/单文件/总量/时间任一触顶
    即置 truncated 并停止，超限文件记入 skipped。
    """
    t0 = time.time()
    root = os.path.realpath(root)
    studies, skipped = [], []
    truncated = False
    total_bytes = 0
    max_file = max_file_mb * 1024 * 1024
    max_total = max_total_mb * 1024 * 1024

    def _load_file(path):
        """读取单个文件为 {size, mtime, b64}；超限/失败返回 None 并记录。"""
        nonlocal total_bytes, truncated
        try:
            size = os.path.getsize(path)
        except OSError as e:
            skipped.append({"path": path.replace(os.sep, '/'),
                            "reason": f"read_error: {e}"})
            return None
        if size > max_file:
            skipped.append({"path": path.replace(os.sep, '/'),
                            "reason": "too_large"})
            return None
        if total_bytes + size > max_total:
            truncated = True
            return None
        try:
            with open(path, 'rb') as f:
                raw = f.read()
        except OSError as e:
            skipped.append({"path": path.replace(os.sep, '/'),
                            "reason": f"read_error: {e}"})
            return None
        total_bytes += len(raw)
        return {"size": len(raw),
                "mtime": int(os.path.getmtime(path)),
                "b64": base64.b64encode(raw).decode('ascii')}

    for dirpath, dirs, files in os.walk(root):
        rel = os.path.relpath(dirpath, root)
        depth = 0 if rel == '.' else rel.count(os.sep) + 1
        if depth >= max_depth:
            # 该目录自身的文件仍会采集，只是不再深入子目录——
            # 仅当确有子目录被剪掉时才记录，避免 skipped 语义误导
            if dirs:
                skipped.append({"path": dirpath.replace(os.sep, '/') + "/*",
                                "reason": "depth_limit"})
            dirs[:] = []
        else:
            dirs[:] = [d for d in dirs
                       if not d.startswith(_WORKMATE_HIDDEN_PREFIXES)
                       and d.lower() not in _WORKMATE_SKIP_DIRS]

        if time.time() - t0 > time_budget_s or len(studies) >= max_studies:
            truncated = True
            break

        entries_path = master_path = None
        for fname in files:
            low = fname.lower()
            if low == 'entries.log':
                entries_path = os.path.join(dirpath, fname)
            elif low == 'master':
                master_path = os.path.join(dirpath, fname)
        if not entries_path:
            continue

        entries_blob = _load_file(entries_path)
        if truncated:
            # 总量预算触顶：该 study 未能返回，必须显式入账而非无声消失
            skipped.append({"path": dirpath.replace(os.sep, '/'),
                            "reason": "total_budget"})
            break
        if entries_blob is None:
            continue  # 超限/读取失败已入 skipped，study 整体跳过
        master_blob = _load_file(master_path) if master_path else None
        if truncated:
            skipped.append({"path": dirpath.replace(os.sep, '/'),
                            "reason": "total_budget"})
            break

        studies.append({
            "rel_path": '' if rel == '.' else rel.replace(os.sep, '/'),
            "abs_path": dirpath.replace(os.sep, '/'),
            "entries": entries_blob,
            "master": master_blob,
        })

    return {"root": root.replace(os.sep, '/'), "studies": studies,
            "skipped": skipped, "truncated": truncated}


@app.route('/api/workmate/scan', methods=['POST'])
def api_workmate_scan():
    """WorkMate Log Parser 一键扫描：递归收集 entries.log/MASTER 原始字节。

    请求体 {"root": 绝对路径}；省略 root 时回落到 prefs 里记忆的
    workmate_scan_root（配合 /api/select-folder + /api/save-prefs 使用）。

    安全：该端点返回患者文件原始字节，而本应用全局启用了 CORS——
    必须拒绝非本机页面发起的跨源请求（浏览器对跨源 POST 一定携带
    Origin 头），否则任意网页可借用户浏览器批量读取数据。
    """
    origin = request.headers.get('Origin')
    if origin:
        from urllib.parse import urlparse
        host = urlparse(origin).hostname
        if host not in ('127.0.0.1', 'localhost'):
            return jsonify({"status": "error",
                            "message": "拒绝非本机来源的扫描请求"}), 403

    data = request.get_json(silent=True) or {}
    root = data.get('root') or ''
    if not root:
        try:
            if os.path.exists(PREFS_FILE) and os.path.getsize(PREFS_FILE) > 0:
                with open(PREFS_FILE, 'r', encoding='utf-8') as f:
                    prefs = json.load(f)
                if isinstance(prefs, dict):
                    root = prefs.get('workmate_scan_root') or ''
        except Exception as e:
            logger.warning(f"读取 prefs 失败: {e}")
    if not root:
        return jsonify({"status": "error",
                        "message": "未指定扫描根目录，请先选择数据目录"}), 400
    if not os.path.isabs(root):
        return jsonify({"status": "error",
                        "message": "扫描根目录必须是绝对路径"}), 400
    real = os.path.realpath(root)
    if not os.path.isdir(real):
        return jsonify({"status": "error",
                        "message": f"目录不存在: {root}"}), 400
    if os.path.dirname(real) == real:
        # 盘符根/文件系统根：误选会扫全盘，直接拒绝
        return jsonify({"status": "error",
                        "message": "不能选择盘符根目录，请选择具体的数据目录"}), 400

    t0 = time.time()
    result = _scan_workmate_root(real)
    result["status"] = "ok"
    result["elapsed_ms"] = int((time.time() - t0) * 1000)
    return jsonify(result)


@app.route('/api/shutdown', methods=['POST'])
def api_shutdown():
    """
    关闭 Epycon GUI 的 API 端点
    """
    try:
        response = jsonify({"status": "shutting_down", "message": "程序正在关闭..."})
        
        # 在后台线程中执行关闭
        def shutdown_worker():
            time.sleep(0.5)  # 等待 HTTP 响应发送完毕
            cleanup_on_exit()
            # 使用 os._exit(0) 而非 sys.exit() 是因为：
            # 1. 此时在后台线程中，sys.exit() 只会终止当前线程
            # 2. 需要强制终止整个进程（包括 Flask 主线程）
            # 3. cleanup_on_exit() 已在上方手动调用，atexit 处理器无需再执行
            import os as os_module
            os_module._exit(0)
        
        shutdown_thread = threading.Thread(target=shutdown_worker, daemon=True)
        shutdown_thread.start()
        
        return response
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/restart', methods=['POST'])
def api_restart():
    """
    重启 Flask 服务的 API 端点。
    返回成功后，前端会等待2秒再刷新。
    """
    try:
        import subprocess
        import sys
        
        # 立即返回成功响应
        response = jsonify({"status": "restarting", "message": "服务正在重启，请稍候..."})
        
        # 在后台线程中执行重启（不阻塞当前请求）
        def restart_worker():
            import time
            time.sleep(1)  # 等待 HTTP 响应发送完毕
            
            # 获取当前环境变量并清理 Werkzeug/Reloader 相关的变量，防止 Bad file descriptor 错误
            new_env = os.environ.copy()
            for key in ['WERKZEUG_RUN_MAIN', 'WERKZEUG_SERVER_FD']:
                new_env.pop(key, None)
            
            # 保留 EPYCON_ACTUAL_PORT 让新进程尝试回收旧端口
            # 在后台启动新的 app_gui.py 进程
            subprocess.Popen([sys.executable, 'app_gui.py'], cwd=os.getcwd(), env=new_env)
            
            # 等待新进程启动后，关闭当前进程
            time.sleep(2)
            import os as os_module
            os_module._exit(0)
        
        restart_thread = threading.Thread(target=restart_worker, daemon=True)
        restart_thread.start()
        
        return response
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/preview-channels', methods=['POST'])
def handle_preview_channels():
    # [FEATURE] 动态扫描日志文件的通道列表供前端选择
    try:
        data = request.json
        input_folder = data.get('input_folder', '')
        
        if not input_folder:
             return jsonify({"status": "error", "message": "未指定输入文件夹"}), 400
             
        # [FIX] 容错处理：如果用户选择了具体文件而非目录，自动使用其父目录
        if os.path.isfile(input_folder):
             input_folder = os.path.dirname(input_folder)
        
        if not os.path.exists(input_folder):
            return jsonify({"status": "error", "message": "文件夹路径无效"}), 400
            
        # 搜索第一个有效的 .log 文件 (不递归，只看当前层或第一层 study)
        # 优先看是否是 study folder 结构
        target_log = None
        
        # 1. 直接检查根目录下是否有 log
        logs_in_root = glob.glob(os.path.join(input_folder, LOG_PATTERN))
        
        # [FIX] 优先选择数字命名的主日志文件 (如 00000000.log)，排除 holter.log 等辅助日志
        if logs_in_root:
            numeric_logs = [f for f in logs_in_root if os.path.basename(f).replace('.log','').isdigit()]
            if numeric_logs:
                numeric_logs.sort() # 选最小的，通常是开头
                target_log = numeric_logs[0]
            else:
                target_log = logs_in_root[0]
        else:
            # 2. 检查子目录下是否有 log (取第一个子目录)
            subdirs = [os.path.join(input_folder, d) for d in os.listdir(input_folder) if os.path.isdir(os.path.join(input_folder, d))]
            for d in subdirs:
                logs_in_subdir = glob.glob(os.path.join(d, LOG_PATTERN))
                if logs_in_subdir:
                    target_log = logs_in_subdir[0]
                    break
        
        if not target_log:
            return jsonify({"status": "error", "message": "在路径中未找到任何 .log 文件"}), 404
            
        # 读取 Header 并提取通道
        channel_names = []
        # 使用默认版本读取
        version = "4.3.2" 
        
        try:
            from epycon.iou import LogParser
            with LogParser(target_log, version=version, samplesize=1024) as p:
                header = p.get_header()
                if header and hasattr(header, 'channels'):
                    # 尝试从 Channels 对象或 num_channels 获取
                    # 注意：LogParser 的 header.channels 通常是 Channels 对象或者 dict
                    # [REFACTOR] 使用核心库的统一函数
                    # 创建一个临时 cfg 结构
                    temp_cfg = {"data": {"leads": "computed", "custom_channels": {}}}
                    channel_names = list(get_channel_mappings(header, temp_cfg).keys())
        except Exception as parse_err:
             return jsonify({"status": "error", "message": f"解析日志失败: {str(parse_err)}"}), 500
             
        if not channel_names:
            conv_logger.warning(f"Scan found no channels in {target_log}")
            
        # 排序并返回
        # 尝试按自然顺序排序（如果包含数字）
        return jsonify({
            "status": "success", 
            "channels": channel_names,
            "source_file": os.path.basename(target_log)
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

def open_browser(port=5050):
    """
    打开浏览器访问 Web UI。
    
    注意：本项目仅针对 Google Chrome 进行优化和测试。
    不对其他浏览器（Safari、Firefox、Edge 等）提供兼容性保证。
    """
    try:
        url = f"http://127.0.0.1:{port}/"
        logging.getLogger(__name__).info(f"Opening browser to {url}")
        
        if os.environ.get('NO_BROWSER') == '1':
            print(f"跳过打开浏览器 (NO_BROWSER=1)，请手动访问: {url}")
            return
            
        # 优先使用 Chrome 浏览器
        if sys.platform == 'darwin':
            # macOS: 使用 open 命令指定 Chrome
            import subprocess
            chrome_paths = [
                '/Applications/Google Chrome.app',
                '/Applications/Google Chrome Canary.app',
                '/Applications/Chromium.app'
            ]
            for chrome_path in chrome_paths:
                if os.path.exists(chrome_path):
                    try:
                        subprocess.run(['open', '-a', chrome_path, url], check=True)
                        logging.getLogger(__name__).info(f"Opened with {chrome_path}")
                        return
                    except subprocess.CalledProcessError:
                        continue
            # 如果没找到 Chrome，使用默认浏览器并提示
            print("⚠️  未检测到 Chrome，使用系统默认浏览器。建议安装 Chrome 以获得最佳体验。")
            webbrowser.open(url)
        elif sys.platform == 'win32':
            # Windows: 尝试使用 Chrome
            try:
                chrome = webbrowser.get('chrome')
                chrome.open(url)
                return
            except webbrowser.Error:
                pass
            # 备选
            try:
                chrome = webbrowser.get('google-chrome')
                chrome.open(url)
                return
            except webbrowser.Error:
                pass
            print("⚠️  未检测到 Chrome，使用系统默认浏览器。建议安装 Chrome 以获得最佳体验。")
            webbrowser.open(url)
        else:
            # Linux 或其他平台
            try:
                chrome = webbrowser.get('google-chrome')
                chrome.open(url)
                return
            except webbrowser.Error:
                pass
            try:
                chrome = webbrowser.get('chromium-browser')
                chrome.open(url)
                return
            except webbrowser.Error:
                pass
            print("⚠️  未检测到 Chrome，使用系统默认浏览器。建议安装 Chrome 以获得最佳体验。")
            webbrowser.open(url)
            
    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to open browser: {e}")
        print(f"请手动打开浏览器访问: {url}")


if __name__ == '__main__':
    try:
        # 确保工作目录是项目根目录
        script_dir = os.path.dirname(os.path.abspath(__file__))
        os.chdir(script_dir)
        
        # 识别是否为打包后的 EXE
        is_frozen = getattr(sys, 'frozen', False)
        
        for stream in (sys.stdout, sys.stderr):
            # Use a concrete type check so static analyzers (Pylance) know this
            # object supports `reconfigure`. `io.TextIOWrapper` exposes
            # reconfigure() on Python 3.7+.
            if isinstance(stream, io.TextIOWrapper):
                try:
                    stream.reconfigure(encoding="utf-8", errors="replace")
                except Exception:
                    pass
        
        # 1. 端口管理
        # 识别是否是 Flask Reloader 的子工作进程
        is_worker = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
        
        # 尝试使用环境变量中的端口（通常是重启时传递），否则默认 5050
        env_port = os.environ.get('EPYCON_ACTUAL_PORT')
        preferred_port = int(env_port) if env_port else 5050
        port = preferred_port
        
        # 仅在非 Worker 进程中进行端口探测和冲突清理
        # Worker 进程应当直接信任并使用父进程分配的端口
        if not is_worker:
            if not check_port_available(port):
                # 尝试清理占用者（例如重启时的旧实例）
                success, occupier = kill_port_occupier(port)
                
                # 如果是系统服务，或者清理失败，则搜索新端口
                if not success or not check_port_available(port):
                    msg = f"⚠️  端口 {port} 被占用"
                    if occupier != "None": msg += f" ({occupier})"
                    print(f"{msg}，正在搜索可用端口...")
                    
                    found = False
                    for p in range(5050, 5100): # 从 5050 开始重新搜索
                        if check_port_available(p):
                            port = p
                            found = True
                            print(f"✅ 已选择可用端口: {port}")
                            break
                    if not found:
                        print("❌ 未找到 5050-5100 范围内的可用端口。")
                        input("\n按回车键退出...")
                        sys.exit(1)
        
        # 存入环境变量，供子进程和重启后的实例使用
        os.environ['EPYCON_ACTUAL_PORT'] = str(port)

        # 检查是否是 Flask Reloader 的父进程
        is_reloader_parent = (not is_frozen and not is_worker)
        
        # 单实例检查必须在 Reloader 父进程中执行（防止多个实例启动）
        print("🔍 正在进行启动前检查...")
        if not check_single_instance():
            print("\n❌ 程序已在运行，无法启动新实例。")
            print("提示：如果确认没有其他实例，请删除临时文件：")
            print(f"      {os.path.join(tempfile.gettempdir(), 'epycon_gui.lock')}")
            input("\n按回车键退出...")
            sys.exit(1)
        
        print("✅ 启动检查通过")

        # 如果以 PyInstaller 打包为 EXE 并在 Windows 上运行，最小化控制台窗口
        try:
            if is_frozen and os.name == 'nt':
                import ctypes
                SW_MINIMIZE = 6
                hWnd = ctypes.windll.kernel32.GetConsoleWindow()
                if hWnd:
                    ctypes.windll.user32.ShowWindow(hWnd, SW_MINIMIZE)
        except Exception:
            pass

        print("\n🚀 Epycon GUI (v0.0.5-alpha) 启动中...")
        print("📌 PID:", os.getpid())
        print(f"🌐 访问地址: http://127.0.0.1:{port}/")
        print("💡 提示: 可在页面中点击'退出程序'按钮关闭，或按 Ctrl+C 退出\n")
        
        # 注册信号处理（优雅退出）
        def signal_handler(sig, frame):
            print("\n\n🛑 收到退出信号，正在清理...")
            cleanup_on_exit()
            print("✅ 清理完成，程序已退出")
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        if hasattr(signal, 'SIGTERM'):
            signal.signal(signal.SIGTERM, signal_handler)
        
        # 对于 EXE 版本，禁用 reloader（避免进程管理问题）
        use_reloader = not is_frozen
        
        # 仅在工作进程中打开浏览器，避免 reloader 导致打开两次
        # WERKZEUG_RUN_MAIN='true' 表示这是 Flask 的实际工作进程
        # 启动浏览器逻辑
        # 当 reloader 禁用时，直接启动；当 reloader 启用时，仅在工作进程中启动
        should_open = is_frozen or os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not use_reloader
        
        if should_open:
            threading.Thread(
                target=lambda: (time.sleep(2), open_browser(port)),
                daemon=True
            ).start()
            
        # 启动服务器
        # 修正：默认绑定到 127.0.0.1 以防止局域网外部访问
        # 如果确实需要远程访问，请通过环境变量配置 EPYCON_HOST=0.0.0.0
        host_ip = os.environ.get('EPYCON_HOST', '127.0.0.1')
        app.run(
            host=host_ip,
            port=port,
            debug=not is_frozen, 
            use_reloader=use_reloader,
            threaded=True
        )
    except Exception as e:
        print(f"启动错误: {e}")
        import traceback
        traceback.print_exc()
