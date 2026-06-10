#!/usr/bin/env python
"""分析 entries.log 文件的二进制结构 - 最终验证"""

import struct
from datetime import datetime

ENTRIES_FILE = 'c:/Projects/epycon/examples/data/real_test/LOG_DHR51337676_00000609/entries.log'

with open(ENTRIES_FILE, 'rb') as f:
    data = f.read()

print(f"File size: {len(data)} bytes")
print()

# 正确的 schema:
# header = 0x00, 0x20 (32 bytes) ✓
# line_size = 0xDC (220 bytes) - 不是 216!
# 
# Entry 结构 (在 line 内的偏移):
# entry_type   = 0x00, 0x02 (2 bytes) ✓
# datalog_id   = 0x02, 0x06 (4 bytes) - 但解析可能需要调整
# unknown      = 0x06, 0x0E (8 bytes) - 可能是其他元数据
# timestamp    = 0x0E, 0x16 (8 bytes, Q format, 毫秒)
# text         = 0x16, 0xC2 (172 bytes)

HEADER_SIZE = 32
LINE_SIZE = 220  # 0xDC
TEXT_START = 0x16  # 22
TEXT_END = 0xC2    # 194 (so text is 172 bytes)

# 验证 text 结束位置
# line_size = 220, text_end 应该 <= 220
# 0xC2 = 194, 194 < 220 ✓

print("=== Correct schema verification ===")
print(f"HEADER_SIZE = {HEADER_SIZE} (0x{HEADER_SIZE:02x})")
print(f"LINE_SIZE = {LINE_SIZE} (0x{LINE_SIZE:02x})")
print(f"TEXT_START = {TEXT_START} (0x{TEXT_START:02x})")
print(f"TEXT_END = {TEXT_END} (0x{TEXT_END:02x})")
print(f"Text field size = {TEXT_END - TEXT_START} bytes")
print()

# 解析所有条目
num_entries = (len(data) - HEADER_SIZE) // LINE_SIZE
print(f"Total entries: {num_entries}")
print()

print("=== All entries ===")
for i in range(num_entries):
    entry_start = HEADER_SIZE + i * LINE_SIZE
    entry = data[entry_start:entry_start + LINE_SIZE]
    
    entry_type = struct.unpack('<H', entry[0x00:0x02])[0]
    datalog_raw = entry[0x02:0x06]
    datalog_id = struct.unpack('<L', datalog_raw)[0]
    
    # 8-byte timestamp at 0x0E
    ts = struct.unpack('<Q', entry[0x0E:0x16])[0]
    try:
        dt = datetime.fromtimestamp(ts / 1000)
    except:
        dt = None
    
    # Text at 0x16, strip nulls
    text_raw = entry[TEXT_START:TEXT_END]
    text = text_raw.split(b'\x00')[0].decode('latin-1', errors='replace')
    
    # Only show non-empty text
    if text.strip():
        print(f"  {i+1:3d}: type={entry_type:2d}, fid={datalog_id:08x}, dt={dt}, text={text[:50]!r}")

# 检查 datalog_id 字段
print()
print("=== Checking datalog_id field ===")
# datalog_id 格式可能不同，让我仔细看看
for i in range(5):
    entry_start = HEADER_SIZE + i * LINE_SIZE
    entry = data[entry_start:entry_start + LINE_SIZE]
    print(f"Entry {i+1} bytes 0x00-0x16:")
    print(f"  {entry[:22].hex(' ')}")
