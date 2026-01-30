#!/usr/bin/env python3
"""
<<<<<<< HEAD
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
=======
测试 readentries 功能
"""
import pytest
import os
import sys
from pathlib import Path

# 测试数据路径
TEST_DATA_PATH = Path("examples/data/study01/entries.log")


def test_readentries_schema_validation():
    """测试 readentries schema 验证逻辑"""
    if not TEST_DATA_PATH.exists():
        pytest.skip(f"测试数据文件不存在: {TEST_DATA_PATH}")
    
    from epycon.iou.parsers import readbin, _validate_version
    from epycon.config.byteschema import WMx32EntriesSchema
    import struct
    from datetime import datetime
    
    f_path = str(TEST_DATA_PATH)
    version = '4.3.2'
    
    # 步骤 1: 读取文件
    barray = readbin(f_path)
    assert len(barray) > 0, "文件应有内容"
    
    # 步骤 2: 获取 schema
    version_type = _validate_version(version)
    assert version_type in ['x32', 'x64'], f"版本类型应为 x32 或 x64, 实际: {version_type}"
    
    if version_type == 'x32':
        diary = WMx32EntriesSchema
    else:
        from epycon.config.byteschema import WMx64EntriesSchema
        diary = WMx64EntriesSchema
    
    # 步骤 3: 验证字节大小
    remainder = (len(barray) - diary.header[1]) % diary.line_size
    assert remainder == 0, f"字节大小不符: remainder={remainder}"
    
    # 步骤 4: 提取 header timestamp
    fmt, factor = diary.timestamp_fmt
    header_start, header_end = diary.header_timestamp
    header_bytes = barray[header_start:header_end]
    header_timestamp = struct.unpack(fmt, header_bytes)[0]
    header_timestamp = header_timestamp // factor
    
    # 步骤 5: 验证 timestamp
    header_date = datetime.fromtimestamp(header_timestamp)
    assert header_date.year >= 2000, f"Timestamp 年份应 >= 2000, 实际: {header_date.year}"


def test_readentries_entry_parsing():
    """测试 readentries 条目解析"""
    if not TEST_DATA_PATH.exists():
        pytest.skip(f"测试数据文件不存在: {TEST_DATA_PATH}")
    
    from epycon.iou import readentries
    
    version = '4.3.2'
    entries = readentries(str(TEST_DATA_PATH), version=version)
    
    # 验证返回的条目
    assert isinstance(entries, list), "readentries 应返回列表"
    
    # 如果有条目，验证其结构
    if len(entries) > 0:
        entry = entries[0]
        assert hasattr(entry, 'timestamp'), "条目应有 timestamp 属性"
        assert hasattr(entry, 'group'), "条目应有 group 属性"
>>>>>>> b8695bb (修复：恢复测试套件及核心功能（CI 已验证）)
