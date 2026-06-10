#!/usr/bin/env python3
"""
Generate WMx64 entries.log with timestamps matching the log files
"""
import struct
import time
from datetime import datetime

# Log file timestamps (in milliseconds)
log_ts1_ms = 1769608079246  # 2026-01-28 21:47:59.246000
log_ts2_ms = 1769608092253  # 2026-01-28 21:48:12.253000

# Convert to seconds for entry timestamps (WMx64 uses milliseconds in entries too)
# Create 2 entries at different times within the log range
entries_data = []

# Entry 1: 100ms into first file
entry1_ts_ms = log_ts1_ms + 100
# Entry 2: in second file
entry2_ts_ms = log_ts2_ms + 50

# WMx64 entries schema from byteschema.py:
# header = 0x00, 0x24
# header_timestamp = 0x02, 0x0A
# entry_type = 0x0, 0x2
# datalog_id = 0x2, 0x6
# timestamp = 0xA, 0x12
# text = 0x12, 0xC2
# line_size = 0xDC

def create_entry(entry_type=2, datalog_id=1, timestamp_ms=0, text=""):
    """Create a WMx64 entries line"""
    line = bytearray(0xDC)  # line_size for WMx64
    
    # entry_type at offset 0x0 (2 bytes)
    line[0x0:0x2] = struct.pack('<H', entry_type)
    
    # datalog_id at offset 0x2 (4 bytes)
    line[0x2:0x6] = struct.pack('<L', datalog_id)
    
    # timestamp at offset 0xA (8 bytes, uint64 milliseconds)
    line[0xA:0x12] = struct.pack('<Q', timestamp_ms)
    
    # text at offset 0x12, max 0xC2-0x12 = 0xB0 = 176 bytes
    text_bytes = text.encode('utf-8', errors='ignore')[:0xB0]
    line[0x12:0x12+len(text_bytes)] = text_bytes
    
    return line

# Create header (24 bytes = 0x24)
header = bytearray(0x24)
header[0x02:0x0A] = struct.pack('<Q', log_ts1_ms)  # header_timestamp

# Create entries
entry1 = create_entry(entry_type=2, datalog_id=1, timestamp_ms=entry1_ts_ms, text="Test Entry 1")
entry2 = create_entry(entry_type=2, datalog_id=1, timestamp_ms=entry2_ts_ms, text="Test Entry 2")

# Write entries file
entries_path = "examples/data/study01/entries.log"
with open(entries_path, 'wb') as f:
    f.write(header)
    f.write(entry1)
    f.write(entry2)

print(f"Generated entries.log with {2} entries:")
print(f"  Entry 1: {datetime.fromtimestamp(entry1_ts_ms/1000)}")
print(f"  Entry 2: {datetime.fromtimestamp(entry2_ts_ms/1000)}")

# Verify by reading back
entries = []
with open(entries_path, 'rb') as f:
    header_data = f.read(0x24)
    while True:
        line = f.read(0xDC)
        if len(line) < 0xDC:
            break
        ts = struct.unpack('<Q', line[0xA:0x12])[0]
        text = line[0x12:0x12+0xB0].rstrip(b'\x00').decode('utf-8', errors='ignore')
        entries.append((ts, text))

print(f"\nVerification - read {len(entries)} entries:")
for ts, text in entries:
    print(f"  {datetime.fromtimestamp(ts/1000)}: {text}")
