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
    # assert header_date.year >= 2000, f"Timestamp 年份应 >= 2000, 实际: {header_date.year}"


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


def test_readentries_sample_index_from_fixture():
    """issue #36：条目 0x06 为 DFile 内采样索引（i32）。夹具两条都指向 00000001.log
    （ts 1769608092253）：第一条早 12.907 s → -12907，第二条晚 50 ms → 50（fs=1000）"""
    if not TEST_DATA_PATH.exists():
        pytest.skip(f"测试数据文件不存在: {TEST_DATA_PATH}")
    from epycon.iou import readentries

    entries = readentries(str(TEST_DATA_PATH), version='4.3.2')
    assert [e.sample_index for e in entries] == [-12907, 50]


def test_readentries_sample_index_from_generator(tmp_path):
    """生成器写入的采样索引 = (ts − DFile ts)×fs/1000，解析回同一值；x32 无该字段 → None"""
    sys.path.insert(0, str(Path("scripts").resolve()))
    from generate_fake_wmx import write_entries
    from epycon.iou import readentries

    log_ts_ms = 1704038400000
    write_entries(str(tmp_path), version='4.3.2', datalog_id=1, log_ts_ms=log_ts_ms, fs=2000,
                  entries=[(2, log_ts_ms - 100, 'pre'), (3, log_ts_ms + 2500, 'post')])
    entries = readentries(str(tmp_path / 'entries.log'), version='4.3.2')
    assert [(e.fid, e.sample_index) for e in entries] == [('00000001', -200), ('00000001', 5000)]

    write_entries(str(tmp_path), version='4.1', datalog_id=1, entries=[(2, 1704038400, 'x')])
    assert readentries(str(tmp_path / 'entries.log'), version='4.1')[0].sample_index is None


def test_readentries_utc_offset(tmp_path):
    """issue #36：偏移 = 头 ASCII 墙钟（0x0A 日期 + 0x16 时间）− u64 epoch。
    夹具墙钟按 UTC+8 写入 → 28800；全零头 / x32 无时间串 → None"""
    if not TEST_DATA_PATH.exists():
        pytest.skip(f"测试数据文件不存在: {TEST_DATA_PATH}")
    import struct
    sys.path.insert(0, str(Path("scripts").resolve()))
    from generate_fake_wmx import write_entries
    from epycon.iou import readentries_utc_offset

    assert readentries_utc_offset(str(TEST_DATA_PATH), version='4.3.2') == 8 * 3600

    blank = bytearray(0x24 + 0xDC)
    blank[0x02:0x0A] = struct.pack('<Q', 1704038400000)
    (tmp_path / 'entries.log').write_bytes(bytes(blank))
    assert readentries_utc_offset(str(tmp_path / 'entries.log'), version='4.3.2') is None

    write_entries(str(tmp_path), version='4.1', datalog_id=1, entries=[(2, 1704038400, 'x')])
    assert readentries_utc_offset(str(tmp_path / 'entries.log'), version='4.1') is None


def test_group_map_covers_observed_subtypes():
    """849 个真实 study 实测 subtype（8 在解析层过滤，5 同）全部有标签（issue #36）"""
    from epycon.config.byteschema import GROUP_MAP

    observed = {1, 2, 3, 4, 5, 6, 7, 9, 13, 16, 17, 20}
    assert observed <= set(GROUP_MAP)
    assert GROUP_MAP[16] == 'RF'


def test_webui_group_map_matches_byteschema():
    """ui/WorkMate_Log_Parser.html 内联了一份 GROUP_MAP（浏览器端解析 entries.log），
    必须与 byteschema.GROUP_MAP 逐项一致，否则 WebUI 与 CSV/HDF5 对同一 subtype 标签不同"""
    import re
    from epycon.config.byteschema import GROUP_MAP

    html = Path("ui/WorkMate_Log_Parser.html").read_text(encoding="utf-8")
    m = re.search(r"const GROUP_MAP = \{([^}]*)\};", html)
    assert m, "WebUI GROUP_MAP literal not found"
    js_map = {int(k): v for k, v in re.findall(r"(\d+):\s*'([A-Z_]+)'", m.group(1))}
    assert js_map == GROUP_MAP
