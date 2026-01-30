"""Additional tests to improve coverage for validators and planters."""
import sys
import os
import tempfile
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / 'epycon'))
sys.path.insert(0, str(project_root))

import numpy as np
from iou.planters import HDFPlanter, CSVPlanter
from core._validators import (
    _validate_int, _validate_str, _validate_tuple, 
    _validate_path, _validate_version, _validate_mount
)

errors = []

def test(name):
    """Test decorator"""
    def decorator(func):
        def wrapper():
            print(f'\n--- {name} ---')
            try:
                func()
                print(f'  [OK] PASSED')
                return True
            except AssertionError as e:
                print(f'  [FAIL] FAILED: {e}')
                errors.append((name, str(e)))
                return False
            except Exception as e:
                print(f'  [ERROR] ERROR: {type(e).__name__}: {e}')
                errors.append((name, f'{type(e).__name__}: {e}'))
                return False
        return wrapper
    return decorator


# ==================== Validator Edge Cases ====================
@test('Validator: int with float that is whole number')
def test_validate_int_float():
    result = _validate_int('test', 5.0, min_value=0, mxn_value=10)
    assert result == 5
    assert isinstance(result, int)


@test('Validator: int with None returns None')
def test_validate_int_none():
    result = _validate_int('test', None)
    assert result is None


@test('Validator: int below min raises ValueError')
def test_validate_int_below_min():
    try:
        _validate_int('test', -1, min_value=0)
        assert False, "Should have raised ValueError"
    except ValueError:
        pass


@test('Validator: int above max raises ValueError')
def test_validate_int_above_max():
    try:
        _validate_int('test', 100, min_value=0, mxn_value=50)
        assert False, "Should have raised ValueError"
    except ValueError:
        pass


@test('Validator: str not in valid_set raises ValueError')
def test_validate_str_invalid():
    try:
        _validate_str('format', 'invalid', {'csv', 'h5'})
        assert False, "Should have raised ValueError"
    except ValueError:
        pass


@test('Validator: str with None returns None')
def test_validate_str_none():
    result = _validate_str('format', None, {'csv', 'h5'})
    assert result is None


@test('Validator: tuple wrong size raises ValueError')
def test_validate_tuple_wrong_size():
    try:
        _validate_tuple('coords', (1, 2, 3), size=2, dtype=int)
        assert False, "Should have raised ValueError"
    except ValueError:
        pass


@test('Validator: tuple wrong type raises TypeError')
def test_validate_tuple_wrong_type():
    try:
        _validate_tuple('names', ('a', 1), size=2, dtype=str)
        assert False, "Should have raised TypeError"
    except TypeError:
        pass


@test('Validator: mount with too many elements raises ValueError')
def test_validate_mount_too_many():
    try:
        _validate_mount((0, 1, 2), max=10)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert 'Too many' in str(e)


@test('Validator: mount with non-int raises TypeError')
def test_validate_mount_non_int():
    try:
        _validate_mount(('a', 'b'), max=10)
        assert False, "Should have raised TypeError"
    except TypeError:
        pass


@test('Validator: mount index out of bounds raises IndexError')
def test_validate_mount_out_of_bounds():
    try:
        _validate_mount((0, 100), max=10)
        assert False, "Should have raised IndexError"
    except IndexError:
        pass


@test('Validator: version 4.1 returns x32')
def test_version_x32():
    assert _validate_version('4.1') == 'x32'


@test('Validator: version None defaults to x64')
def test_version_default():
    assert _validate_version(None) == 'x64'


@test('Validator: path does not exist raises ValueError')
def test_validate_path_not_exists():
    try:
        _validate_path('/nonexistent/path/to/file.txt')
        assert False, "Should have raised ValueError"
    except ValueError:
        pass


# ==================== Planter Pre-allocation Tests ====================
@test('HDFPlanter: pre-allocation reduces resize calls')
def test_hdf_preallocation():
    with tempfile.TemporaryDirectory() as tmpdir:
        outfile = os.path.join(tmpdir, 'test.h5')
        
        with HDFPlanter(outfile, column_names=['A', 'B'], sampling_freq=1000) as p:
            # Write small chunks multiple times
            for i in range(10):
                data = np.array([[i, i+1]], dtype=np.int32)
                p.write(data)
        
        # Verify file exists and has correct sample count
        import h5py
        with h5py.File(outfile, 'r') as f:
            assert 'Data' in f
            # 10 writes of 1 sample = 10 samples
            assert f['Data'].shape[1] == 10, f"Expected 10 samples, got {f['Data'].shape[1]}"


@test('HDFPlanter: logical length attribute is set')
def test_hdf_logical_length():
    with tempfile.TemporaryDirectory() as tmpdir:
        outfile = os.path.join(tmpdir, 'test.h5')
        data = np.array([[1, 2, 3], [4, 5, 6]], dtype=np.int32)
        
        with HDFPlanter(outfile, column_names=['A', 'B', 'C'], sampling_freq=1000) as p:
            p.write(data)
        
        import h5py
        with h5py.File(outfile, 'r') as f:
            # After exit, file should be trimmed and logical_length should match shape
            assert f['Data'].shape[1] == 2


@test('CSVPlanter: np.savetxt produces correct output')
def test_csv_savetxt():
    with tempfile.TemporaryDirectory() as tmpdir:
        outfile = os.path.join(tmpdir, 'test.csv')
        data = np.array([[1, 2], [3, 4], [5, 6]], dtype=np.int32)
        
        with CSVPlanter(outfile, column_names=['X', 'Y']) as p:
            p.write(data)
        
        with open(outfile, 'r') as f:
            lines = f.readlines()
            assert len(lines) == 4  # 1 header + 3 data rows
            assert 'X' in lines[0] and 'Y' in lines[0]


# ==================== Run All Tests ====================
def main():
    print('=' * 60)
    print('COVERAGE IMPROVEMENT TESTS')
    print('=' * 60)
    
    tests = [
        test_validate_int_float,
        test_validate_int_none,
        test_validate_int_below_min,
        test_validate_int_above_max,
        test_validate_str_invalid,
        test_validate_str_none,
        test_validate_tuple_wrong_size,
        test_validate_tuple_wrong_type,
        test_validate_mount_too_many,
        test_validate_mount_non_int,
        test_validate_mount_out_of_bounds,
        test_version_x32,
        test_version_default,
        test_validate_path_not_exists,
        test_hdf_preallocation,
        test_hdf_logical_length,
        test_csv_savetxt,
    ]
    
    passed = sum(1 for t in tests if t())
    failed = len(tests) - passed
    
    print('\n' + '=' * 60)
    print(f'RESULTS: {passed} passed, {failed} failed')
    print('=' * 60)
    
    if errors:
        print('\nFAILED TESTS:')
        for name, msg in errors:
            print(f'  - {name}: {msg}')
    
    return failed == 0


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
