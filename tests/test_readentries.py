#!/usr/bin/env python3
"""
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
