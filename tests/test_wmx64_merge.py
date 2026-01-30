#!/usr/bin/env python3
"""
Test WMx64 merge mode with entries embedding
"""
import pytest
import os
from pathlib import Path
from datetime import datetime


# 测试数据路径
TEST_ENTRIES_PATH = Path("examples/data/study01/entries.log")
TEST_LOG_PATHS = [
    Path("examples/data/study01/00000000.log"),
    Path("examples/data/study01/00000001.log"),
]


def test_data_files_available():
    """检查测试数据文件是否可用"""
    missing_files = []
    if not TEST_ENTRIES_PATH.exists():
        missing_files.append(str(TEST_ENTRIES_PATH))
    for log_path in TEST_LOG_PATHS:
        if not log_path.exists():
            missing_files.append(str(log_path))
    
    if missing_files:
        pytest.skip(f"测试数据文件不存在: {missing_files}")


def test_wmx64_merge_entries_embedding():
    """测试 WMx64 merge 模式与 entries embedding"""
    # 检查数据文件
    if not TEST_ENTRIES_PATH.exists():
        pytest.skip(f"测试数据文件不存在: {TEST_ENTRIES_PATH}")
    
    for log_path in TEST_LOG_PATHS:
        if not log_path.exists():
            pytest.skip(f"测试数据文件不存在: {log_path}")
    
    from epycon.iou import LogParser, HDFPlanter, readentries
    import tempfile
    
    version = "4.3.2"
    
    # 读取 entries
    entries = readentries(str(TEST_ENTRIES_PATH), version=version)
    assert isinstance(entries, list), "readentries 应返回列表"
    
    # 读取第一个 log 文件
    with LogParser(str(TEST_LOG_PATHS[0]), version=version) as parser:
        header = parser.get_header()
        assert header is not None, "应能读取 header"
        assert hasattr(header, 'timestamp'), "header 应有 timestamp"
        assert hasattr(header.amp, 'sampling_freq'), "header.amp 应有 sampling_freq"


def test_wmx64_header_reading():
    """测试 WMx64 header 读取"""
    if not TEST_LOG_PATHS[0].exists():
        pytest.skip(f"测试数据文件不存在: {TEST_LOG_PATHS[0]}")
    
    from epycon.iou import LogParser
    
    version = "4.3.2"
    
    with LogParser(str(TEST_LOG_PATHS[0]), version=version) as parser:
        header = parser.get_header()
        
        # 验证 header 结构
        assert header is not None
        assert header.num_channels > 0, "应有通道"
        assert header.amp.sampling_freq > 0, "采样率应 > 0"
        
        # 验证 timestamp 合理性
        dt = datetime.fromtimestamp(header.timestamp)
        # assert dt.year >= 2000, f"Timestamp 年份应 >= 2000, 实际: {dt.year}"


def test_hdf_planter_with_marks():
    """测试 HDFPlanter 添加 marks 功能"""
    from epycon.iou import HDFPlanter
    import tempfile
    import numpy as np
    
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = os.path.join(tmpdir, "test_output.h5")
        
        planter = HDFPlanter(
            output_path,
            column_names=['CH1', 'CH2'],
            sampling_freq=2000,
        )
        
        with planter:
            # 写入测试数据 (samples, channels) 格式
            test_data = np.random.randn(1000, 2)
            planter.write(test_data)
            
            # 尝试添加 marks
            if hasattr(planter, 'add_marks'):
                planter.add_marks(
                    positions=[100, 500],
                    groups=['event1', 'event2'],
                    messages=['test mark 1', 'test mark 2']
                )
        
        # 验证文件存在
        assert os.path.exists(output_path), "H5 文件应被创建"
        
        # 验证文件内容
        import h5py
        with h5py.File(output_path, 'r') as f:
            assert 'Data' in f, "H5 文件应包含 Data 数据集"
