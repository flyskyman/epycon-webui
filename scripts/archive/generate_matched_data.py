#!/usr/bin/env python3
"""
生成带匹配时间戳的 WMx32 格式测试数据
"""

import sys
sys.path.insert(0, 'c:\\Projects\\epycon')

import struct
import time
from datetime import datetime
from scripts.generate_fake_wmx import generate_wmx

# 使用当前时间戳
now = int(time.time())
print(f"生成时间戳: {now} ({datetime.fromtimestamp(now)})")

# 日志文件路径
log_path = "examples/data/study01/00000000.log"

# 生成足够长的日志（30 秒，30000 个样本）
num_samples = 30000
generate_wmx(
    out_path=log_path,
    version='4.3.2',
    num_channels=2,
    num_samples=num_samples,
    sampling_freq=1000
)
print(f"✅ 生成日志: {log_path} ({num_samples} samples, ~{num_samples/1000}s)")

# 现在修改时间戳为当前时间
with open(log_path, 'r+b') as f:
    f.seek(0x0A)  # Seek to timestamp offset in WMx32
    f.write(struct.pack('<I', now))
print(f"  修改时间戳为: {now}")

# 现在生成匹配的 entries.log
entries_path = "examples/data/study01/entries.log"

# WMx32 entries 格式
# 标注应该在文件的早期（5 秒和 10 秒处）
entries_data = [
    {
        'type': 2,
        'datalog_id': 0x00000000,
        'timestamp': now + 5,  # 5 秒后
        'message': b"example entry #1"
    },
    {
        'type': 2,
        'datalog_id': 0x00000000,
        'timestamp': now + 10,  # 10 秒后
        'message': b"example entry #2"
    }
]

with open(entries_path, 'wb') as f:
    # Write header (0x20 bytes)
    f.write(b'WX')  # 0x00-0x02: magic
    f.write(struct.pack('<I', now))  # 0x02-0x06: header_timestamp
    f.write(b'\x00' * (0x20 - 6))  # 0x06-0x20: padding
    
    # Write entries (0xD8 bytes each)
    for entry in entries_data:
        f.write(struct.pack('<H', entry['type']))  # 0x00-0x02
        f.write(struct.pack('<I', entry['datalog_id']))  # 0x02-0x06
        f.write(b'\x00' * 4)  # 0x06-0x0A: unused
        f.write(struct.pack('<I', entry['timestamp']))  # 0x0A-0x0E
        msg = entry['message'].ljust(0xB2, b'\x00')  # 0x0E-0xC0
        f.write(msg)
        f.write(b'\x00' * (0xD8 - 0xC0))  # 0xC0-0xD8: padding

print(f"✅ 生成标注: {entries_path} ({len(entries_data)} 条)")

# 验证读取
from epycon.iou import readentries
entries = readentries(entries_path, version='4.3.2')
print(f"\n标注验证:")
for i, e in enumerate(entries):
    print(f"  Entry {i}: ts={e.timestamp}, group={e.group}, msg={e.message}")
