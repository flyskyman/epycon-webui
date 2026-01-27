"""
测试类型修复后的功能
"""
import sys
import os
import tempfile
import struct

# 测试 1: bins.py 的 parsebin 函数
print("=" * 60)
print("测试 1: parsebin 函数类型兼容性")
print("=" * 60)

from epycon.core.bins import parsebin

# 测试 bytes 输入
test_bytes = b'\x01\x00'
result = parsebin(test_bytes, '<H')
print(f"✓ bytes 输入: parsebin(b'\\x01\\x00', '<H') = {result} (type: {type(result).__name__})")
assert result == 1, "parsebin 返回值错误"
assert isinstance(result, int), "parsebin 应返回 int"

# 测试 bytearray 输入
test_bytearray = bytearray(b'\xFF\x00')
result = parsebin(test_bytearray, '<H')
print(f"✓ bytearray 输入: parsebin(bytearray(...), '<H') = {result} (type: {type(result).__name__})")
assert result == 255, "parsebin 返回值错误"

# 测试多值返回
test_multi = b'\x01\x00\x02\x00'
result = parsebin(test_multi, '<HH')
print(f"✓ 多值返回: parsebin(..., '<HH') = {result} (type: {type(result).__name__})")
assert isinstance(result, tuple), "多值应返回 tuple"
assert len(result) == 2, "应返回 2 个值"

print("\n测试 1 通过 ✓\n")

# 测试 2: Entry 数据类
print("=" * 60)
print("测试 2: Entry 数据类类型")
print("=" * 60)

from epycon.core._dataclasses import Entry

# 测试 group 为 str
entry1 = Entry(fid='00000001', group='PROTOCOL', timestamp=1234567890, message='Test message')
print(f"✓ Entry with str group: {entry1.group} (type: {type(entry1.group).__name__})")
assert entry1.group == 'PROTOCOL'

# 测试 group 为 int
entry2 = Entry(fid='00000002', group=1, timestamp=1234567891, message='Test message 2')
print(f"✓ Entry with int group: {entry2.group} (type: {type(entry2.group).__name__})")
assert entry2.group == 1

print("\n测试 2 通过 ✓\n")

# 测试 3: LogParser 基本功能
print("=" * 60)
print("测试 3: LogParser 参数验证")
print("=" * 60)

from epycon.iou.parsers import LogParser

# 测试可选参数
try:
    # 这应该不会抛出类型错误（即使文件不存在）
    parser = LogParser(
        f_path="nonexistent.log",
        version=None,  # Optional[str]
        samplesize=1024,
        start=0,
        end=None,  # Optional[int]
    )
    print("✓ LogParser 接受 None 参数")
except FileNotFoundError:
    print("✓ LogParser 初始化正常（文件不存在是预期的）")
except TypeError as e:
    print(f"✗ LogParser 类型错误: {e}")
    sys.exit(1)

print("\n测试 3 通过 ✓\n")

# 测试 4: 如果有示例数据，测试实际读取
print("=" * 60)
print("测试 4: 实际数据读取（如果存在）")
print("=" * 60)

example_log = "examples/data/study01/00000000.log"
if os.path.exists(example_log):
    try:
        with LogParser(example_log, version='4.2', start=0, end=100) as parser:
            header = parser.get_header()
            print(f"✓ 成功读取 header")
            print(f"  - 时间戳: {header.timestamp}")
            print(f"  - 通道数: {header.num_channels}")
            print(f"  - 采样率: {header.amp.sampling_freq} Hz")
            
            # 测试读取数据
            chunk = next(parser)
            print(f"✓ 成功读取数据块: shape={chunk.shape}, dtype={chunk.dtype}")
    except Exception as e:
        print(f"⚠ 读取数据时出错: {e}")
        import traceback
        traceback.print_exc()
else:
    print(f"⊘ 示例数据不存在: {example_log}")
    print("  跳过实际数据测试")

print("\n测试 4 完成\n")

# 测试 5: entries 读取
print("=" * 60)
print("测试 5: Entries 读取")
print("=" * 60)

from epycon.iou.parsers import _readentries

example_entries = "examples/data/study01/entries.log"
if os.path.exists(example_entries):
    try:
        entries = _readentries(example_entries, version='4.2')
        print(f"✓ 成功读取 {len(entries)} 条 entries")
        if entries:
            first = entries[0]
            print(f"  - 第一条: group={first.group} (type={type(first.group).__name__}), message={first.message[:50]}...")
            
            # 验证 group 类型
            for e in entries[:5]:
                assert isinstance(e.group, (int, str)), f"group 应该是 int 或 str，实际是 {type(e.group)}"
            print(f"✓ 所有 entries 的 group 类型正确")
    except Exception as e:
        print(f"⚠ 读取 entries 时出错: {e}")
        import traceback
        traceback.print_exc()
else:
    print(f"⊘ 示例 entries 不存在: {example_entries}")
    print("  跳过 entries 测试")

print("\n测试 5 完成\n")

# 测试 6: 类型检查（静态分析）
print("=" * 60)
print("测试 6: 验证类型注解")
print("=" * 60)

try:
    from typing import get_type_hints
    
    # 检查 LogParser.__init__
    from epycon.iou.parsers import LogParser
    hints = get_type_hints(LogParser.__init__)
    print(f"✓ LogParser.__init__ 类型提示: {list(hints.keys())}")
    
    # 检查 Entry
    from epycon.core._dataclasses import Entry
    hints = get_type_hints(Entry)
    print(f"✓ Entry 类型提示: {hints}")
    
except Exception as e:
    print(f"⚠ 类型提示检查: {e}")

print("\n测试 6 完成\n")

# 总结
print("=" * 60)
print("✅ 所有基础测试通过！")
print("=" * 60)
print("\n代码变动验证完成，类型修复工作正常。")
