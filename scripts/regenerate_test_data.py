#!/usr/bin/env python3
"""
生成带有匹配时间戳的测试日志和标注（WMx32 格式）
"""

import sys
sys.path.insert(0, 'c:\\Projects\\epycon')

import struct
import json
import time
from datetime import datetime, timezone

# 版本必须是 4.3.2 以使用 WMx64 格式
WORKMATE_VERSION = "4.3.2"  # WMx64
print(f"使用 WorkMate 版本: {WORKMATE_VERSION} (WMx64 格式)")

# 生成新的日志文件，时间戳为当前时间
now = int(time.time())
print(f"使用时间戳: {now} ({datetime.fromtimestamp(now)})")

# 生成日志文件
log_path = "examples/data/study01/00000000.log"

# WMx64 格式: 64-bit header 
# 0x0-0x8: timestamp (uint64, milliseconds)
# 0x8-0xA: num_channels
# 0xA-0xC: sampling_freq (Hz)
# 0xC-0x10: unknown
# ... channels: 32 bytes each
# ... rest: 16-bit samples (channels × samples)

num_channels = 2
sampling_freq = 1000
num_samples = 1024

with open(log_path, 'wb') as f:
    # 0x0-0x2: header
    f.write(b'WX')
    # 0x2-0x4: unknown
    f.write(struct.pack('<H', 0))
    # 0x4-0x6: version
    f.write(struct.pack('<H', 0x0432))  # version 4.3.2
    # 0x6-0x8: num_channels
    f.write(struct.pack('<H', num_channels))
    # 0x8-0xA: sampling_freq
    f.write(struct.pack('<H', sampling_freq))
    # 0xA-0xE: timestamp (uint32)
    f.write(struct.pack('<I', now))
    # 0xE-0x12: amplifier info (just zeros for now)
    f.write(struct.pack('<I', 0))
    
    # Write sample data
    for i in range(num_samples):
        for ch in range(num_channels):
            sample = int(100 * (i % 10) / 10.0)  # Simple pattern
            f.write(struct.pack('<h', sample))

print(f"✅ 生成日志: {log_path} (channels={num_channels}, fs={sampling_freq}, samples={num_samples})")

# 生成 entries.log 文件
# WMx32 格式:
# Header (0x20 = 32 bytes):
#   0x00-0x02: "WX" header
#   0x02-0x06: header_timestamp (uint32, seconds)
#   0x06-0x20: unused
# Each entry (0xD8 = 216 bytes):
#   0x00-0x02: entry_type (uint16)
#   0x02-0x06: datalog_id (uint32)
#   0x06-0x0A: unused
#   0x0A-0x0E: timestamp (uint32, seconds)
#   0x0E-0xC0: message text (0xB2 = 178 bytes)
#   0xC0-0xD8: padding (0x18 = 24 bytes)

entries_data = []

# Entry 1: 100 seconds after log start
entry1_timestamp = now + 100
entry1_msg = b"example entry #1".ljust(0xB2, b'\x00')
entries_data.append({
    'type': 2,
    'datalog_id': 0x00000000,
    'timestamp': entry1_timestamp,
    'message': entry1_msg
})

# Entry 2: 200 seconds after log start (still within range if file is short)
entry2_timestamp = now + 200
entry2_msg = b"example entry #2".ljust(0xB2, b'\x00')
entries_data.append({
    'type': 2,
    'datalog_id': 0x00000000,
    'timestamp': entry2_timestamp,
    'message': entry2_msg
})

entries_path = "examples/data/study01/entries.log"
with open(entries_path, 'wb') as f:
    # Write header (0x20 bytes)
    f.write(b'WX')  # 0x00-0x02: magic
    f.write(struct.pack('<I', now))  # 0x02-0x06: header_timestamp
    f.write(b'\x00' * (0x20 - 6))  # 0x06-0x20: padding (26 bytes)
    
    # Write entries (0xD8 bytes each)
    for entry in entries_data:
        f.write(struct.pack('<H', entry['type']))  # 0x00-0x02: entry_type (2 bytes)
        f.write(struct.pack('<I', entry['datalog_id']))  # 0x02-0x06: datalog_id (4 bytes)
        f.write(b'\x00' * 4)  # 0x06-0x0A: unused (4 bytes)
        f.write(struct.pack('<I', entry['timestamp']))  # 0x0A-0x0E: timestamp (4 bytes)
        f.write(entry['message'])  # 0x0E-0xC0: message (0xB2 = 178 bytes)
        f.write(b'\x00' * (0xD8 - 0xC0))  # 0xC0-0xD8: padding (24 bytes)

print(f"✅ 生成标注: {entries_path} ({len(entries_data)} 条)")

# 验证文件大小
import os
size = os.path.getsize(entries_path)
header = 0x20
line_size = 0xD8
remainder = (size - header) % line_size
print(f"文件大小验证: {size} bytes (header={header}, line_size={line_size}, remainder={remainder})")

print(f"\n日志文件时间范围: {now} - {now + num_samples / sampling_freq:.3f}s")

