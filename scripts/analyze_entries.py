#!/usr/bin/env python
"""分析 entries.log 文件 - 与 WMx64EntriesSchema 保持一致"""

import struct
from datetime import datetime

# WMx64EntriesSchema 正确的值 (来自 byteschema.py)
HEADER_SIZE = 0x24  # 36 bytes
LINE_SIZE = 0xDC    # 220 bytes
TIMESTAMP_START = 0x0A
TIMESTAMP_END = 0x12
TEXT_START = 0x12   # 18
TEXT_END = 0xC2     # 194 (text is 176 bytes)
TIMESTAMP_FMT = '<Q'
TIMESTAMP_FACTOR = 1000

def analyze_entries(entries_file: str, max_entries: int = 500):
    """分析 entries.log 文件"""
    with open(entries_file, 'rb') as f:
        data = f.read()

    print(f"File: {entries_file}")
    print(f"File size: {len(data)} bytes")
    print()

    # 验证文件大小
    if (len(data) - HEADER_SIZE) % LINE_SIZE != 0:
        print("WARNING: File size does not match expected schema!")
        print(f"  Expected: header({HEADER_SIZE}) + N * line_size({LINE_SIZE})")
        print(f"  Actual remainder: {(len(data) - HEADER_SIZE) % LINE_SIZE}")
        print()

    num_entries = (len(data) - HEADER_SIZE) // LINE_SIZE
    print(f"Total entries: {num_entries}")
    print()

    print(f"=== First {max_entries} entries with non-empty text ===")
    count = 0
    for i in range(num_entries):
        if count >= max_entries:
            break
        entry_start = HEADER_SIZE + i * LINE_SIZE
        entry = data[entry_start:entry_start + LINE_SIZE]
        
        # Entry type (group)
        entry_type = struct.unpack('<H', entry[0x00:0x02])[0]
        
        # Datalog ID
        datalog_id = struct.unpack('<L', entry[0x02:0x06])[0]
        datalog_uid = f"{datalog_id:08x}"
        
        # Timestamp (milliseconds since epoch)
        ts = struct.unpack(TIMESTAMP_FMT, entry[TIMESTAMP_START:TIMESTAMP_END])[0]
        ts_seconds = ts // TIMESTAMP_FACTOR
        try:
            dt = datetime.fromtimestamp(ts_seconds)
        except (OSError, ValueError):
            dt = None
        
        # Text (null-terminated, latin-1 encoded)
        text_raw = entry[TEXT_START:TEXT_END]
        null_pos = text_raw.find(b'\x00')
        if null_pos >= 0:
            text_raw = text_raw[:null_pos]
        text = text_raw.decode('latin-1', errors='replace')
        text = "".join(c for c in text if c.isprintable() or c in ' \t')
        
        if not text.strip():
            continue

        # Filter out 'NOTE' (ID 5) which is hidden in standard PDF report.
        # ID 3 (e.g. '!', 'END!') IS shown in PDF report.
        if entry_type == 5:
            continue

        count += 1
        text_display = text[:60] + '...' if len(text) > 60 else text
        print(f"{count:3d}. [fid={datalog_uid}] type={entry_type:2d} | {dt} | {text_display}")
    
    return num_entries

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        analyze_entries(sys.argv[1])
    else:
        # Default: analyze third patient's entries.log
        analyze_entries(r'c:\backup\LOG_DHR51337676_0000067d\entries.log')
