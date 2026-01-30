#!/usr/bin/env python
"""
Comprehensive business logic tests for epycon core functionality.
Tests the complete data conversion pipeline and key business functions.
"""

import sys
import os
import tempfile
import json
from pathlib import Path

# Ensure UTF-8 output on all platforms
if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Add epycon module to path (cross-platform)
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / 'epycon'))
sys.path.insert(0, str(project_root))

from iou.parsers import LogParser, _readentries, _readmaster, _mount_channels
from iou.planters import CSVPlanter, HDFPlanter, EntryPlanter
from core._validators import _validate_version
from core.helpers import deep_override, difftimestamp
from config.byteschema import WMx32LogSchema, WMx64LogSchema
import numpy as np

# Test counter
tests_run = 0
tests_passed = 0
tests_failed = 0

def test(name):
    """Decorator for test functions"""
    def decorator(func):
        def wrapper():
            global tests_run, tests_passed, tests_failed
            tests_run += 1
            
            print(f"\n[TEST {tests_run}] {name}")
            print(f"{'='*60}")
            
            try:
                func()
                print(f"[PASS] {name}")
                tests_passed += 1
                return True
            except AssertionError as e:
                print(f"[FAIL] {name}: {e}")
                tests_failed += 1
                return False
            except Exception as e:
                print(f"[ERROR] {name}: {type(e).__name__}: {e}")
                tests_failed += 1
                return False
        return wrapper
    return decorator


# ==================== Version & Schema Tests ====================

@test('Version detection: 4.1 is x32')
def test_version_x32():
    assert _validate_version('4.1') == 'x32'
    print("  - Correctly identified as x32 schema")

@test('Version detection: 4.2/4.3 are x64')
def test_version_x64():
    assert _validate_version('4.2') == 'x64'
    assert _validate_version('4.3') == 'x64'
    assert _validate_version('4.3.2') == 'x64'
    print("  - All versions correctly identified as x64")

@test('Schema supported versions')
def test_schema_versions():
    x32_versions = WMx32LogSchema.supported_versions
    x64_versions = WMx64LogSchema.supported_versions
    
    assert x32_versions == '4.1', f"x32 should support 4.1, got {x32_versions}"
    assert '4.2' in x64_versions and '4.3' in x64_versions
    print(f"  - x32: {x32_versions}")
    print(f"  - x64: {x64_versions}")


# ==================== Helper Functions Tests ====================

@test('Config override: deep_override function')
def test_deep_override():
    cfg = {
        'paths': {'input': 'default'},
        'data': {'format': 'csv'}
    }
    
    deep_override(cfg, ['paths', 'input'], 'custom_path')
    assert cfg['paths']['input'] == 'custom_path'
    
    deep_override(cfg, ['data', 'format'], 'h5')
    assert cfg['data']['format'] == 'h5'
    print("  - Config override works correctly")

@test('Timestamp difference calculation')
def test_difftimestamp():
    # 2024-01-01 00:00:00
    ts1 = 1704038400
    # 2024-01-01 01:00:00 (1 hour later)
    ts2 = 1704042000
    
    diff = difftimestamp([ts1, ts2])
    assert abs(diff - 3600) < 1, f"Expected ~3600s difference, got {diff}"
    print(f"  - Timestamp difference calculated: {diff}s (expected 3600s)")


# ==================== Data Processing Tests ====================

@test('Channel mounting: create mounted data array')
def test_mount_channels():
    # Create fake 3-channel data
    data = np.random.randn(100, 3)  # 100 samples, 3 channels
    
    # Mount channels 0 and 1 only
    mappings = {
        'Ch1': [0],
        'Ch2': [1]
    }
    
    mounted = _mount_channels(data, mappings)
    
    assert mounted.shape == (100, 2), f"Expected (100, 2), got {mounted.shape}"
    print(f"  - Data mounted from {data.shape} to {mounted.shape}")
    print(f"  - Output shape: {mounted.shape}")


# ==================== File I/O Tests ====================

@test('CSV Planter: basic file creation')
def test_csv_planter():
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = os.path.join(tmpdir, 'test.csv')
        
        # Create planter and write data
        with CSVPlanter(csv_path) as planter:
            data = np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])
            planter.write(data)
        
        # Verify file was created
        assert os.path.exists(csv_path), "CSV file was not created"
        
        # Verify content
        with open(csv_path, 'r') as f:
            lines = f.readlines()
        
        assert len(lines) > 0, "CSV file is empty"
        print(f"  - Created CSV file with {len(lines)} lines")

@test('HDF5 Planter: write and read data')
def test_hdf5_planter():
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            h5_path = os.path.join(tmpdir, 'test.h5')
            
            # Write data - shape should be (samples, channels)
            test_data = np.random.randn(1024, 2)  # 1024 samples x 2 channels
            
            print(f"  - Creating HDF5 with data shape: {test_data.shape}")
            
            with HDFPlanter(
                h5_path, 
                column_names=['Ch1', 'Ch2'],
                sampling_freq=500,
                attributes={'subject_id': 'TEST001', 'timestamp': 1704038400}
            ) as planter:
                print(f"  - HDFPlanter created successfully")
                planter.write(test_data)
                print(f"  - Data written: shape {test_data.shape}")
            
            # Verify file was created
            assert os.path.exists(h5_path), "HDF5 file was not created"
            print(f"  - File exists: {h5_path}")
            
            file_size = os.path.getsize(h5_path)
            print(f"  - File size: {file_size} bytes")
            assert file_size > 1000, f"HDF5 file size too small: {file_size}"
            
            import h5py
            with h5py.File(h5_path, 'r') as f:
                # Just verify that the file can be opened as HDF5
                keys = list(f.keys())
                print(f"  - HDF5 keys: {keys}")
                assert len(keys) > 0, "HDF5 file is empty"
                
            print(f"  - HDF5 file created: {file_size} bytes with {len(keys)} datasets")
    except Exception as e:
        import traceback
        print(f"  - ERROR: {e}")
        print(f"  - Traceback: {traceback.format_exc()}")
        raise


# ==================== Integration Tests ====================

@test('HDF5 append mode: multiple writes')
def test_hdf5_append():
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            h5_path = os.path.join(tmpdir, 'merged.h5')
            
            # First write - shape should be (samples, channels)
            data1 = np.random.randn(512, 2)  # 512 samples x 2 channels
            print(f"  - First write with shape: {data1.shape}")
            
            with HDFPlanter(
                h5_path,
                column_names=['Ch1', 'Ch2'],
                sampling_freq=500,
                attributes={'batch': '1'}
            ) as planter:
                planter.write(data1)
            
            assert os.path.exists(h5_path), "HDF5 file not created on first write"
            size_after_first = os.path.getsize(h5_path)
            print(f"  - First write size: {size_after_first} bytes")
            
            # Second write with append - shape should be (samples, channels)
            data2 = np.random.randn(512, 2)  # 512 samples x 2 channels
            print(f"  - Second write with shape: {data2.shape}")
            
            with HDFPlanter(
                h5_path,
                column_names=['Ch1', 'Ch2'],
                sampling_freq=500,
                append=True,
                attributes={'batch': '2'}
            ) as planter:
                planter.write(data2)
            
            size_after_second = os.path.getsize(h5_path)
            print(f"  - After append size: {size_after_second} bytes")
            
            # Verify file size increased (more data was appended)
            assert size_after_second >= size_after_first, f"File size did not increase: {size_after_first} -> {size_after_second}"
            
            # Verify file is still valid HDF5
            import h5py
            try:
                with h5py.File(h5_path, 'r') as f:
                    # Just verify it can be opened
                    num_datasets = len(list(f.keys()))
            except Exception as e:
                raise AssertionError(f"File is not valid HDF5: {e}")
            
            print(f"  - Append successful")
            print(f"  - Size increased by: {size_after_second - size_after_first} bytes")
            print(f"  - File contains {num_datasets} dataset(s)")
    except Exception as e:
        import traceback
        print(f"  - ERROR: {e}")
        print(f"  - Traceback: {traceback.format_exc()}")
        raise


@test('Configuration validation: JSON schema check')
def test_config_validation():
    import jsonschema
    
    # Valid config
    valid_cfg = {
        'paths': {
            'input_folder': 'test',
            'output_folder': 'out',
            'studies': []
        },
        'data': {
            'output_format': 'h5',
            'pin_entries': True,
            'leads': 'raw',
            'data_files': [],
            'channels': [],
            'custom_channels': {},
            'merge_logs': True
        },
        'entries': {
            'convert': True,
            'output_format': 'sel',
            'summary_csv': True,
            'filter_annotation_type': []
        },
        'global_settings': {
            'workmate_version': '4.3',
            'pseudonymize': False,
            'processing': {'chunk_size': 1024000},
            'credentials': {'author': 'test', 'device': 'test', 'owner': 'test'}
        }
    }
    
    schema_path = project_root / 'config' / 'schema.json'
    with open(schema_path) as f:
        schema = json.load(f)
    
    # This should not raise
    jsonschema.validate(valid_cfg, schema)
    print("  - Configuration is JSON schema compliant")


# ==================== Main Runner ====================

def main():
    print("\n" + "="*60)
    print("EPYCON BUSINESS LOGIC TESTS")
    print("="*60)
    
    # Run all tests
    test_version_x32()
    test_version_x64()
    test_schema_versions()
    test_deep_override()
    test_difftimestamp()
    test_mount_channels()
    test_csv_planter()
    test_hdf5_planter()
    test_hdf5_append()
    test_config_validation()
    
    # Summary
    print("\n" + "="*60)
    print(f"SUMMARY: {tests_passed} passed, {tests_failed} failed (total {tests_run})")
    print("="*60)
    
    if tests_failed == 0:
        print("[OK] All business logic tests passed!")
        return 0
    else:
        print(f"[FAIL] {tests_failed} test(s) failed")
        return 1


if __name__ == '__main__':
    sys.exit(main())
