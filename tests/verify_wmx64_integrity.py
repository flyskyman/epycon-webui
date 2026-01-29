#!/usr/bin/env python3
"""
Comprehensive WMx64 Data Integrity Verification Report
验证所有生成的数据，确保没有数据丢失
"""
# pyright: ignore (h5py and LogParser type stubs issue)
import sys
sys.path.insert(0, 'c:\\Projects\\epycon')

import h5py
import struct
from datetime import datetime
from pathlib import Path
from epycon.iou import readentries

print("=" * 80)
print("WMx64 DATA INTEGRITY VERIFICATION REPORT")
print("=" * 80)

# Test configuration
test_version = "4.3.2"
log_files = [
    "examples/data/study01/00000000.log",
    "examples/data/study01/00000001.log"
]
entries_file = "examples/data/study01/entries.log"
output_h5 = "examples/data/out/test_wmx64_merged.h5"

print("\n[1] LOG FILE INTEGRITY")
print("-" * 80)

total_log_samples = 0
log_timestamps = []

for log_file in log_files:
    if not Path(log_file).exists():
        print(f"ERROR: {log_file} not found!")
        sys.exit(1)
    
    file_size = Path(log_file).stat().st_size
    
    with open(log_file, 'rb') as f:
        # Read WMx64 header
        ts_ms = struct.unpack('<Q', f.read(8))[0]
        num_channels = struct.unpack('<H', f.read(2))[0]
        fs = 0  # Will read from header at correct offset
        
        # Seek to sampling frequency offset in WMx64 (0x3838)
        f.seek(0x3838)
        fs = struct.unpack('<H', f.read(2))[0]
    
    ts_sec = ts_ms / 1000.0
    dt = datetime.fromtimestamp(ts_sec)
    
    # Calculate number of samples (log file size - header) / (num_channels * sample_size)
    header_size = 0x393C
    data_size = file_size - header_size
    sample_bytes = data_size // (num_channels * 4)
    
    log_timestamps.append((log_file, ts_sec, dt, fs, num_channels, sample_bytes))
    total_log_samples += sample_bytes
    
    print(f"\n{Path(log_file).name}:")
    print(f"  Timestamp: {ts_sec:.3f} ({dt})")
    print(f"  Channels: {num_channels}")
    print(f"  Sampling freq: {fs} Hz")
    print(f"  Samples: {sample_bytes:,}")
    print(f"  Data size: {data_size:,} bytes")

print(f"\nTotal log samples: {total_log_samples:,}")

print("\n[2] ENTRIES FILE INTEGRITY")
print("-" * 80)

if not Path(entries_file).exists():
    print(f"ERROR: {entries_file} not found!")
    sys.exit(1)

# Read entries
entries = readentries(entries_file, version=test_version)
print(f"Total entries: {len(entries)}")

entry_timestamps = []
for i, e in enumerate(entries):
    ts = e.timestamp / 1000.0
    dt = datetime.fromtimestamp(ts)
    entry_timestamps.append(ts)
    print(f"  Entry {i}: {ts:.3f} ({dt})")

# Verify entries are within log time range
print("\n[3] ENTRIES TIME RANGE VALIDATION")
print("-" * 80)

if len(entries) > 0:
    min_entry_ts = min(entry_timestamps)
    max_entry_ts = max(entry_timestamps)
    log_start_ts = log_timestamps[0][1]
    log_end_ts = log_timestamps[-1][1] + (total_log_samples / log_timestamps[-1][3])
    
    print(f"Log time range: {log_start_ts:.3f} - {log_end_ts:.3f}")
    print(f"Entries range: {min_entry_ts:.3f} - {max_entry_ts:.3f}")
    
    if min_entry_ts >= log_start_ts and max_entry_ts <= log_end_ts:
        print("Status: OK - All entries within log time range")
    else:
        print("WARNING: Some entries outside log time range!")

print("\n[4] H5 OUTPUT FILE INTEGRITY")
print("-" * 80)

if not Path(output_h5).exists():
    print(f"ERROR: {output_h5} not found!")
    sys.exit(1)

file_size = Path(output_h5).stat().st_size
print(f"File size: {file_size:,} bytes")

with h5py.File(output_h5, 'r') as h5f:
    print(f"\nDatasets:")
    
    # Check Data dataset
    if 'Data' in h5f:
        data = h5f['Data']
        print(f"  Data: shape={data.shape}, dtype={data.dtype}")
        h5_samples = data.shape[1] if len(data.shape) > 1 else data.shape[0]
        print(f"    Total samples in H5: {h5_samples:,}")
        
        # Verify sample count matches
        if h5_samples == total_log_samples:
            print(f"    Status: OK - Matches log file total ({total_log_samples:,})")
        else:
            print(f"    ERROR: Mismatch! Expected {total_log_samples:,}, got {h5_samples:,}")
    else:
        print("  ERROR: Data dataset not found!")
    
    # Check Marks dataset
    if 'Marks' in h5f:
        marks = h5f['Marks']
        print(f"\n  Marks: shape={marks.shape}, dtype={marks.dtype}")
        marks_data = marks[:]
        print(f"    Number of marks: {len(marks_data)}")
        
        if len(marks_data) == len(entries):
            print(f"    Status: OK - Matches entries count ({len(entries)})")
        else:
            print(f"    WARNING: Expected {len(entries)} marks, got {len(marks_data)}")
        
        # Verify mark positions are within data range
        invalid_marks = 0
        for i, mark in enumerate(marks_data):
            # Marks structure: (SampleLeft, SampleRight, Group, Validity, Channel, Info)
            mark_pos = mark[0]  # SampleLeft
            if mark_pos < 0 or mark_pos >= h5_samples:
                print(f"    ERROR: Mark {i} at invalid position {mark_pos}")
                invalid_marks += 1
        
        if invalid_marks == 0:
            print(f"    All mark positions valid (0 - {h5_samples-1})")
    else:
        print(f"\n  WARNING: Marks dataset not found!")
    
    # Check metadata
    if 'Info' in h5f:
        info = h5f['Info']
        print(f"\n  Info: shape={info.shape}")
        if len(info) > 0:
            print(f"    Subject ID: {info[0][0]}")
            print(f"    Sampling freq: {info[0][2]} Hz")

print("\n[5] DATA INTEGRITY SUMMARY")
print("-" * 80)

checks = [
    ("Log files exist", True),
    ("Entries file exists", True),
    ("Output H5 file exists", True),
    ("All entries within time range", min_entry_ts >= log_start_ts and max_entry_ts <= log_end_ts),
    ("H5 samples match log total", h5_samples == total_log_samples),
    ("H5 marks match entries count", len(marks_data) == len(entries)),
    ("All mark positions valid", invalid_marks == 0),
]

failed = sum(1 for _, status in checks if not status)

for check_name, status in checks:
    status_str = "[PASS]" if status else "[FAIL]"
    print(f"  {status_str} {check_name}")

print("\n" + "=" * 80)
if failed == 0:
    print("RESULT: ALL CHECKS PASSED - NO DATA LOSS DETECTED")
else:
    print(f"RESULT: {failed} CHECK(S) FAILED - REVIEW ABOVE")
print("=" * 80)

sys.exit(0 if failed == 0 else 1)
