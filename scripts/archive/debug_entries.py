#!/usr/bin/env python3
"""
调试标注时间戳
"""
# pyright: ignore (LogParser type stubs issue)
import sys
sys.path.insert(0, 'c:\\Projects\\epycon')

from epycon.iou import readentries, LogParser
import struct
from datetime import datetime

# 读取标注
entries_path = "examples/data/study01/entries.log"
native_entries = readentries(entries_path, version="4.3.2")

print(f"原始标注条数: {len(native_entries)}")
print("\n标注详情:")
for i, e in enumerate(native_entries):
    print(f"  Entry {i}:")
    print(f"    - timestamp (原始): {e.timestamp}")
    print(f"    - timestamp (float): {float(e.timestamp)}")
    print(f"    - timestamp (int): {int(e.timestamp)}")
    print(f"    - group: {e.group}")
    print(f"    - message: {e.message}")

# 读取日志文件头
log_path = "examples/data/study01/00000000.log"
print(f"\n日志文件: {log_path}")
with LogParser(log_path, version="4.3.2") as parser:
    header = parser.get_header()
    print(f"  header.timestamp: {header.timestamp}")
    print(f"  float(header.timestamp): {float(header.timestamp)}")
    
    # 计算文件时间范围
    n_channels = header.num_channels
    fs = header.amp.sampling_freq
    file_size = 1024 * 2 * n_channels + 32  # 假设 1024 samples + 32 byte header
    n_samples = (file_size - 32) // (n_channels * 2)
    file_duration_sec = n_samples / fs
    
    file_start_sec = float(header.timestamp)
    file_end_sec = file_start_sec + file_duration_sec
    print(f"  文件时间范围: {file_start_sec:.2f} - {file_end_sec:.2f} (持续 {file_duration_sec:.2f}s)")

# 测试时间戳处理
print("\n标注时间戳处理:")
from app_gui import to_unix_seconds
for i, e in enumerate(native_entries):
    raw_ts = float(e.timestamp)
    normalized_ts = to_unix_seconds(e.timestamp)
    print(f"  Entry {i}:")
    print(f"    - 原始: {raw_ts}")
    print(f"    - 归一化: {normalized_ts}")
    print(f"    - 在范围内: {file_start_sec <= normalized_ts <= file_end_sec}")
