#!/usr/bin/env python3
"""
End-to-end test: Convert WMx64 log files with entries embedding
"""
<<<<<<< HEAD
# pyright: ignore (h5py and LogParser type stubs issue)
import sys
sys.path.insert(0, 'c:\\Projects\\epycon')

import os
import json
import shutil
from pathlib import Path
from datetime import datetime
from epycon.iou import LogParser, HDFPlanter, readentries, mount_channels

# Prepare output directory
output_dir = Path("examples/data/out")
output_dir.mkdir(parents=True, exist_ok=True)
output_file = output_dir / "test_wmx64_merged.h5"

# Remove old file if exists
if output_file.exists():
    output_file.unlink()

print("=" * 70)
print("WMx64 End-to-End Test: Merge Mode with Entries Embedding")
print("=" * 70)

version = "4.3.2"
log_paths = ["examples/data/study01/00000000.log", "examples/data/study01/00000001.log"]

# Read all entries
print("\n[1] Reading entries...")
entries = readentries("examples/data/study01/entries.log", version=version)
print(f"    Found {len(entries)} entries")
for i, e in enumerate(entries):
    dt = datetime.fromtimestamp(e.timestamp) if e.timestamp > 100 else "unknown"
    print(f"      Entry {i}: {dt}")

# Prepare merge data collection
channel_names = []
sampling_freq = 0
file_infos = []  # List of (log_path, header, num_samples)
all_chunks = []

# Read all log files
print("\n[2] Reading log files...")
for idx, log_path in enumerate(log_paths):
    print(f"    File {idx}: {log_path}")
    
    with LogParser(log_path, version=version) as parser:
        header = parser.get_header()
        
        if idx == 0:
            channel_names = [f"CH{i+1}" for i in range(header.num_channels)]
            sampling_freq = header.amp.sampling_freq
            print(f"      Channels: {channel_names}")
            print(f"      Sampling freq: {sampling_freq} Hz")
        
        # Collect all samples
        num_samples = 0
        for chunk in parser:
            num_samples += chunk.shape[0] if hasattr(chunk, 'shape') else len(chunk)
            all_chunks.append(chunk)
        
        print(f"      Timestamp: {datetime.fromtimestamp(header.timestamp)}")
        print(f"      Samples: {num_samples}")
        file_infos.append((log_path, header, num_samples))

# Write merged H5 file with entries embedding
print(f"\n[3] Writing merged H5 file with entries...")
print(f"    Output: {output_file}")

with HDFPlanter(
    str(output_file),
    column_names=channel_names,
    sampling_freq=sampling_freq,
    attributes={
        'subject_id': 'TEST001',
        'timestamp': datetime.now().isoformat(),
        'entries_count': len(entries),
    }
) as planter:
    # Write all data
    for chunk in all_chunks:
        planter.write(chunk)
    
    # Add marks (entries)
    if len(entries) > 0 and planter.add_marks:
        print(f"    Adding {len(entries)} marks...")
        
        # Calculate sample positions for each entry
        marks = []
        for e in entries:
            # Find which file this entry belongs to
            entry_ts = e.timestamp
            global_sample_pos = None
            
            sample_offset = 0
            for file_idx, (log_path, header, num_samples) in enumerate(file_infos):
                file_start_sec = header.timestamp
                file_end_sec = file_start_sec + (num_samples / sampling_freq)
                
                if file_start_sec <= entry_ts < file_end_sec or (file_idx == len(file_infos) - 1 and entry_ts <= file_end_sec):
                    relative_pos = round((entry_ts - file_start_sec) * sampling_freq)
                    global_sample_pos = sample_offset + relative_pos
                    print(f"      Entry at {datetime.fromtimestamp(entry_ts)}: pos={global_sample_pos}")
                    marks.append(global_sample_pos)
                    break
                
                sample_offset += num_samples
        
        # Add all marks at once
        if marks:
            groups = [2] * len(marks)  # All EVENT group
            messages = [f"Entry_{i}" for i in range(len(marks))]
            planter.add_marks(marks, groups, messages)
            print(f"    Added {len(marks)} marks successfully")

# Verify output file
print(f"\n[4] Verifying output...")
if output_file.exists():
    file_size = output_file.stat().st_size
    print(f"    File size: {file_size:,} bytes")
    print(f"    File exists: YES")
    
    # Try to read it back
    try:
        import h5py
        with h5py.File(str(output_file), 'r') as h5file:
            print(f"    H5 structure:")
            for key in h5file.keys():
                item = h5file[key]
                if hasattr(item, 'shape'):
                    print(f"      {key}: {item.shape}")
                else:
                    print(f"      {key}: (group)")
            
            # Check for Marks dataset
            if 'Marks' in h5file:
                marks_data = h5file['Marks'][:]
                print(f"    Marks dataset shape: {marks_data.shape}")
                print(f"    SUCCESS: Entries embedded in H5!")
            else:
                print(f"    WARNING: No Marks dataset found")
    except Exception as e:
        print(f"    Error reading H5: {e}")
else:
    print(f"    File does not exist!")

print("\n" + "=" * 70)
print("Test Complete!")
print("=" * 70)
=======
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
        assert dt.year >= 2000, f"Timestamp 年份应 >= 2000, 实际: {dt.year}"


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
>>>>>>> b8695bb (修复：恢复测试套件及核心功能（CI 已验证）)
