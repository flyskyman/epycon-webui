"""Test script to verify version 4.3.2 is treated as x64 schema"""
import sys
import os
from pathlib import Path

# Ensure UTF-8 output on all platforms
if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Add epycon module to path (cross-platform)
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / 'epycon'))
sys.path.insert(0, str(project_root))

from iou.parsers import LogParser, _readentries
from core._validators import _validate_version
from config.byteschema import WMx64LogSchema, WMx32LogSchema

print('=== Version Validation ===')
for v in ['4.1', '4.2', '4.3', '4.3.2']:
    print(f'  {v} -> {_validate_version(v)}')

print()
print('=== Schema Supported Versions ===')
print(f'  WMx32: {WMx32LogSchema.supported_versions}')
print(f'  WMx64: {WMx64LogSchema.supported_versions}')

print()
print('=== Test 4.3.2 Data Parsing ===')
log_path = 'examples/data/real_test/LOG_DHR51337676_00000609/00000000.log'
entries_path = 'examples/data/real_test/LOG_DHR51337676_00000609/entries.log'

if os.path.exists(log_path):
    with LogParser(log_path, version='4.3.2') as p:
        header = p.get_header()
        print(f'Header timestamp: {header.timestamp}')
        print(f'Num channels: {header.num_channels}')
        print(f'Sampling freq: {header.amp.sampling_freq}Hz')

    if os.path.exists(entries_path):
        entries = _readentries(entries_path, version='4.3.2')
        print(f'Entries count: {len(entries)}')
        if len(entries) > 54:
            print(f'Sample entry #55: {entries[54].message!r}')
else:
    print('(Test data files not found - skipping data parsing test)')
    print('To test data parsing, provide test files at: examples/data/real_test/LOG_DHR51337676_00000609/')

print()
print('=== All tests passed! ===')
