#!/usr/bin/env python3
"""
调试 readentries 问题
"""

import sys
sys.path.insert(0, 'c:\\Projects\\epycon')

from epycon.iou.parsers import readbin, _validate_version
from epycon.config.byteschema import WMx32EntriesSchema
import struct
from datetime import datetime

# 手动执行 readentries 的步骤
f_path = 'examples/data/study01/entries.log'
version = '4.3.2'

print("步骤 1: 读取文件")
barray = readbin(f_path)
print(f"  文件大小: {len(barray)} bytes")

print("\n步骤 2: 获取 schema")
version_type = _validate_version(version)
print(f"  Version type: {version_type}")
if version_type == 'x32':
    diary = WMx32EntriesSchema
    print(f"  使用 WMx32 schema")
elif version_type == 'x64':
    from epycon.config.byteschema import WMx64EntriesSchema
    diary = WMx64EntriesSchema
    print(f"  使用 WMx64 schema")
else:
    print(f"  ERROR: 不支持的版本类型 {version_type}")
    sys.exit(1)

print("\n步骤 3: 验证字节大小")
print(f"  diary.header[1]: {diary.header[1]} (0x{diary.header[1]:X})")
print(f"  diary.line_size: {diary.line_size} (0x{diary.line_size:X})")
remainder = (len(barray) - diary.header[1]) % diary.line_size
print(f"  (len - header[1]) % line_size = {remainder}")
if remainder != 0:
    print(f"  ERROR: 字节大小不符!")
    sys.exit(1)
print(f"  ✅ 验证通过")

print("\n步骤 4: 提取 header timestamp")
fmt, factor = diary.timestamp_fmt
print(f"  fmt: {fmt}, factor: {factor}")
header_start, header_end = diary.header_timestamp
print(f"  header_timestamp range: {header_start}-{header_end}")
header_bytes = barray[header_start:header_end]
print(f"  header_bytes: {header_bytes.hex()}")
header_timestamp = struct.unpack(fmt, header_bytes)[0]
print(f"  header_timestamp (raw): {header_timestamp}")
header_timestamp = header_timestamp // factor
print(f"  header_timestamp (after factor): {header_timestamp}")

print("\n步骤 5: 验证 timestamp")
try:
    header_date = datetime.fromtimestamp(header_timestamp)
    print(f"  header_date: {header_date}")
    print(f"  ✅ Timestamp 有效")
except ValueError as err:
    print(f"  ERROR: 无效的 timestamp - {err}")
    sys.exit(1)

print("\n步骤 6: 读取条目")
entries = []
for pointer in range(diary.header[1], len(barray), diary.line_size):
    print(f"  Entry at offset {pointer} (0x{pointer:X}):")
    
    # entry type
    start_byte, end_byte = diary.entry_type
    group = struct.unpack("<H", barray[pointer + start_byte:pointer + end_byte])[0]
    print(f"    group: {group}")
    
    # datalog file uid
    start_byte, end_byte = diary.datalog_id
    datalog_uid = struct.unpack("<L", barray[pointer + start_byte:pointer + end_byte])[0]
    datalog_uid = f"{datalog_uid:08x}"
    print(f"    datalog_uid: {datalog_uid}")
    
    # timestamp
    start_byte, end_byte = diary.timestamp
    timestamp = struct.unpack(fmt, barray[pointer + start_byte:pointer + end_byte])[0] / factor
    print(f"    timestamp: {timestamp}")
    
    # message
    start_byte, end_byte = diary.text
    text_bytes = barray[pointer + start_byte:pointer + end_byte]
    null_pos = text_bytes.find(b'\x00')
    if null_pos >= 0:
        text_bytes = text_bytes[:null_pos]
    message = text_bytes.decode('latin-1', errors='replace')
    message = "".join(c for c in message if c.isprintable() or c in ' \t')
    print(f"    message: {message}")
    
    entries.append((group, datalog_uid, timestamp, message))

print(f"\n✅ 读取完成: {len(entries)} 条条目")
