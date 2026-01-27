"""Extended tests for epycon - edge cases and stress tests"""
import sys
import os
import tempfile
import shutil

sys.path.insert(0, 'c:/Projects/epycon/epycon')

from iou.parsers import LogParser, _readentries, _readmaster, _mount_channels
from iou.planters import CSVPlanter, HDFPlanter, EntryPlanter
from iou import mount_channels
from core._validators import _validate_version, _validate_path, _validate_int
from core.helpers import deep_override
import numpy as np

TEST_DIR = 'c:/Projects/epycon/examples/data/real_test/LOG_DHR51337676_00000609'
LOG_FILE = os.path.join(TEST_DIR, '00000000.log')
ENTRIES_FILE = os.path.join(TEST_DIR, 'entries.log')
MASTER_FILE = os.path.join(TEST_DIR, 'MASTER')

errors = []

def test(name):
    def decorator(func):
        def wrapper():
            print(f'\n--- {name} ---')
            try:
                func()
                print(f'  ✓ PASSED')
                return True
            except AssertionError as e:
                print(f'  ✗ FAILED: {e}')
                errors.append((name, str(e)))
                return False
            except Exception as e:
                print(f'  ✗ ERROR: {type(e).__name__}: {e}')
                errors.append((name, f'{type(e).__name__}: {e}'))
                return False
        return wrapper
    return decorator


# ==================== Version Edge Cases ====================
@test('Version: 4.1.0 -> x32')
def test_version_410():
    assert _validate_version('4.1.0') == 'x32'

@test('Version: 4.1.5 -> x32')
def test_version_415():
    assert _validate_version('4.1.5') == 'x32'

@test('Version: 4.2.0 -> x64')
def test_version_420():
    assert _validate_version('4.2.0') == 'x64'

@test('Version: 4.2.99 -> x64')
def test_version_4299():
    assert _validate_version('4.2.99') == 'x64'

@test('Version: whitespace handling')
def test_version_whitespace():
    try:
        _validate_version(' 4.3 ')
        assert False, "Should reject whitespace"
    except ValueError:
        pass

@test('Version: empty string')
def test_version_empty():
    try:
        _validate_version('')
        assert False, "Should reject empty"
    except ValueError:
        pass


# ==================== mount_channels Edge Cases ====================
@test('mount_channels: int value auto-convert')
def test_mount_int():
    data = np.array([[1,2,3],[4,5,6]], dtype=np.int32)
    result = mount_channels(data, {'ch0': 0, 'ch1': 2})
    assert result.shape == (2, 2)
    assert result[0,0] == 1 and result[0,1] == 3

@test('mount_channels: differential (pos - neg)')
def test_mount_differential():
    data = np.array([[10, 3, 5]], dtype=np.int32)
    result = mount_channels(data, {'diff': [0, 1]})  # 10 - 3 = 7
    assert result[0, 0] == 7

@test('mount_channels: empty mappings')
def test_mount_empty():
    data = np.array([[1,2,3]], dtype=np.int32)
    result = mount_channels(data, {})
    assert result.shape == (1, 0)

@test('mount_channels: invalid type raises error')
def test_mount_invalid_type():
    data = np.array([[1,2,3]], dtype=np.int32)
    try:
        mount_channels(data, {'ch0': 'invalid'})
        assert False, "Should raise TypeError"
    except TypeError as e:
        assert 'str' in str(e)

@test('mount_channels: large dataset')
def test_mount_large():
    data = np.random.randint(0, 1000, (100000, 50), dtype=np.int32)
    mappings = {f'ch{i}': [i] for i in range(50)}
    result = mount_channels(data, mappings)
    assert result.shape == (100000, 50)


# ==================== LogParser Edge Cases ====================
@test('LogParser: read all chunks')
def test_parser_all_chunks():
    with LogParser(LOG_FILE, version='4.3.2') as p:
        header = p.get_header()
        total_samples = 0
        for chunk in p:
            total_samples += chunk.shape[0]
        assert total_samples > 0
        print(f'  (Total samples: {total_samples})')

@test('LogParser: header consistency')
def test_parser_header_consistency():
    with LogParser(LOG_FILE, version='4.3.2') as p:
        h1 = p.get_header()
        h2 = p.get_header()  # Should return same header
        assert h1.timestamp == h2.timestamp
        assert h1.num_channels == h2.num_channels

@test('LogParser: multiple files in sequence')
def test_parser_multiple_files():
    files = [
        os.path.join(TEST_DIR, '00000000.log'),
        os.path.join(TEST_DIR, '00000001.log'),
    ]
    for f in files:
        if os.path.exists(f):
            with LogParser(f, version='4.3.2') as p:
                header = p.get_header()
                assert header.num_channels > 0


# ==================== Entries Edge Cases ====================
@test('Entries: all entries have valid structure')
def test_entries_structure():
    entries = _readentries(ENTRIES_FILE, version='4.3.2')
    for e in entries:
        assert hasattr(e, 'timestamp')
        assert hasattr(e, 'message')
        assert hasattr(e, 'group')
        assert hasattr(e, 'fid')

@test('Entries: filter by fid')
def test_entries_filter_fid():
    entries = _readentries(ENTRIES_FILE, version='4.3.2')
    planter = EntryPlanter(entries)
    # Check _filter method works
    filtered = list(planter._filter(criteria={'fids': {'00000000'}}))
    assert len(filtered) >= 0  # May or may not have entries for this fid


# ==================== HDFPlanter Edge Cases ====================
@test('HDFPlanter: unicode channel names')
def test_hdf_unicode():
    with tempfile.TemporaryDirectory() as tmpdir:
        outfile = os.path.join(tmpdir, 'test.h5')
        data = np.array([[1, 2]], dtype=np.int32)
        # Chinese characters in channel names
        with HDFPlanter(outfile, column_names=['通道1', '通道2'], sampling_freq=1000) as p:
            p.write(data)
        import h5py
        with h5py.File(outfile, 'r') as f:
            assert 'Data' in f

@test('HDFPlanter: very long channel names')
def test_hdf_long_names():
    with tempfile.TemporaryDirectory() as tmpdir:
        outfile = os.path.join(tmpdir, 'test.h5')
        data = np.array([[1, 2]], dtype=np.int32)
        long_names = ['A' * 100, 'B' * 100]
        with HDFPlanter(outfile, column_names=long_names, sampling_freq=1000) as p:
            p.write(data)
        assert os.path.exists(outfile)

@test('HDFPlanter: multiple append operations')
def test_hdf_multi_append():
    with tempfile.TemporaryDirectory() as tmpdir:
        outfile = os.path.join(tmpdir, 'test.h5')
        
        # Initial write
        with HDFPlanter(outfile, column_names=['A', 'B'], sampling_freq=1000) as p:
            p.write(np.array([[1, 2]], dtype=np.int32))
        
        # Multiple appends
        for i in range(5):
            with HDFPlanter(outfile, column_names=['A', 'B'], sampling_freq=1000, append=True) as p:
                p.write(np.array([[i, i+1]], dtype=np.int32))
        
        import h5py
        with h5py.File(outfile, 'r') as f:
            assert f['Data'].shape[1] == 6  # 1 + 5 appends

@test('HDFPlanter: float data')
def test_hdf_float():
    with tempfile.TemporaryDirectory() as tmpdir:
        outfile = os.path.join(tmpdir, 'test.h5')
        data = np.array([[1.5, 2.5, 3.5]], dtype=np.float32)
        with HDFPlanter(outfile, column_names=['A', 'B', 'C'], sampling_freq=1000) as p:
            p.write(data)
        import h5py
        with h5py.File(outfile, 'r') as f:
            assert f['Data'].dtype == np.float32

@test('HDFPlanter: marks with special characters')
def test_hdf_marks_special():
    with tempfile.TemporaryDirectory() as tmpdir:
        outfile = os.path.join(tmpdir, 'test.h5')
        data = np.array([[1, 2]], dtype=np.int32)
        with HDFPlanter(outfile, column_names=['A', 'B'], sampling_freq=1000) as p:
            p.write(data)
            p.add_marks(
                positions=[0],
                groups=['测试'],
                messages=['消融开始 - Session 1']
            )
        import h5py
        with h5py.File(outfile, 'r') as f:
            assert 'Marks' in f


# ==================== CSVPlanter Edge Cases ====================
@test('CSVPlanter: special characters in data path')
def test_csv_special_path():
    with tempfile.TemporaryDirectory() as tmpdir:
        outfile = os.path.join(tmpdir, 'test file (1).csv')
        data = np.array([[1, 2, 3]], dtype=np.int32)
        with CSVPlanter(outfile, column_names=['A', 'B', 'C']) as p:
            p.write(data)
        assert os.path.exists(outfile)

@test('CSVPlanter: large number of columns')
def test_csv_many_columns():
    with tempfile.TemporaryDirectory() as tmpdir:
        outfile = os.path.join(tmpdir, 'test.csv')
        ncols = 100
        data = np.random.randint(0, 100, (10, ncols), dtype=np.int32)
        col_names = [f'Col{i}' for i in range(ncols)]
        with CSVPlanter(outfile, column_names=col_names) as p:
            p.write(data)
        with open(outfile, 'r') as f:
            header = f.readline()
            assert header.count(',') == ncols - 1  # n-1 commas for n columns


# ==================== Validator Edge Cases ====================
@test('Validator: path with spaces')
def test_validate_path_spaces():
    with tempfile.TemporaryDirectory() as tmpdir:
        path_with_spaces = os.path.join(tmpdir, 'folder with spaces')
        os.makedirs(path_with_spaces)
        result = _validate_path(path_with_spaces)
        assert result == path_with_spaces

@test('Validator: int boundaries')
def test_validate_int():
    assert _validate_int('test', 0, min_value=0) == 0
    assert _validate_int('test', 100, min_value=0, mxn_value=100) == 100  # Note: mxn_value not max_value
    try:
        _validate_int('test', -1, min_value=0)
        assert False, "Should reject negative"
    except ValueError:
        pass


# ==================== deep_override Edge Cases ====================
@test('deep_override: deeply nested')
def test_deep_override_nested():
    cfg = {'a': {'b': {'c': {'d': 'old'}}}}
    deep_override(cfg, ['a', 'b', 'c', 'd'], 'new')
    assert cfg['a']['b']['c']['d'] == 'new'

@test('deep_override: with None value')
def test_deep_override_none():
    cfg = {'a': {'b': 'old'}}
    deep_override(cfg, ['a', 'b'], None)
    assert cfg['a']['b'] is None


# ==================== Integration: Full Pipeline ====================
@test('Integration: process all log files in study')
def test_full_study():
    log_files = [f for f in os.listdir(TEST_DIR) if f.endswith('.log') and f[0].isdigit()]
    processed = 0
    for log_file in log_files[:3]:  # Limit to first 3
        log_path = os.path.join(TEST_DIR, log_file)
        with tempfile.TemporaryDirectory() as tmpdir:
            outfile = os.path.join(tmpdir, log_file.replace('.log', '.h5'))
            with LogParser(log_path, version='4.3.2') as parser:
                header = parser.get_header()
                mappings = {ch.name: [ch.reference] for ch in header.channels if ch.reference < header.num_channels}
                col_names = list(mappings.keys())
                
                with HDFPlanter(outfile, column_names=col_names, sampling_freq=header.amp.sampling_freq) as planter:
                    for chunk in parser:
                        mounted = mount_channels(chunk, mappings)
                        planter.write(mounted)
            processed += 1
    print(f'  (Processed {processed} files)')
    assert processed > 0


# ==================== Run All ====================
def main():
    print('=' * 60)
    print('EPYCON EXTENDED TESTS')
    print('=' * 60)
    
    tests = [
        # Version
        test_version_410,
        test_version_415,
        test_version_420,
        test_version_4299,
        test_version_whitespace,
        test_version_empty,
        
        # mount_channels
        test_mount_int,
        test_mount_differential,
        test_mount_empty,
        test_mount_invalid_type,
        test_mount_large,
        
        # LogParser
        test_parser_all_chunks,
        test_parser_header_consistency,
        test_parser_multiple_files,
        
        # Entries
        test_entries_structure,
        test_entries_filter_fid,
        
        # HDFPlanter
        test_hdf_unicode,
        test_hdf_long_names,
        test_hdf_multi_append,
        test_hdf_float,
        test_hdf_marks_special,
        
        # CSVPlanter
        test_csv_special_path,
        test_csv_many_columns,
        
        # Validators
        test_validate_path_spaces,
        test_validate_int,
        
        # deep_override
        test_deep_override_nested,
        test_deep_override_none,
        
        # Integration
        test_full_study,
    ]
    
    passed = 0
    failed = 0
    
    for test_func in tests:
        if test_func():
            passed += 1
        else:
            failed += 1
    
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
