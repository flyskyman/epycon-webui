import os
import tempfile
import pytest
import numpy as np
from unittest.mock import patch, MagicMock
from epycon.iou.planters import CSVPlanter, HDFPlanter


class TestCSVPlanter:
    """Test CSVPlanter functionality."""

    def test_csv_planter_init(self):
        """Test CSVPlanter initialization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, 'test.csv')
            planter = CSVPlanter(csv_path, column_names=['CH1', 'CH2'])
            assert planter.column_names == ['CH1', 'CH2']
            assert planter.delimiter == ','

    def test_csv_planter_write(self):
        """Test CSVPlanter write method."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, 'test.csv')
            planter = CSVPlanter(csv_path, column_names=['CH1', 'CH2'])
            
            # Mock chunk data
            chunk = MagicMock()
            chunk.data = np.array([[1.0, 2.0], [3.0, 4.0]])
            chunk.timestamps = np.array([1000, 1001])
            
            with planter:
                planter.write(chunk.data)
            
            # Check file was created and has content
            assert os.path.exists(csv_path)
            with open(csv_path, 'r') as f:
                content = f.read()
                assert 'CH1' in content
                assert 'CH2' in content

    def test_csv_planter_delimiter(self):
        """Test CSVPlanter delimiter property."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, 'test.csv')
            planter = CSVPlanter(csv_path, column_names=['CH1'], delimiter=';')
            assert planter._delimiter == ';'
            # Test backward compatibility
            assert planter.delimiter == ';'


class TestHDFPlanter:
    """Test HDFPlanter functionality."""

    def test_hdf_planter_init(self):
        """Test HDFPlanter initialization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            h5_path = os.path.join(tmpdir, 'test.h5')
            planter = HDFPlanter(
                h5_path, 
                column_names=['CH1', 'CH2'], 
                sampling_freq=2000,
                attributes={'subject_id': 'test'}
            )
            assert planter.column_names == ['CH1', 'CH2']
            assert planter.sampling_freq == 2000

    def test_hdf_planter_write(self):
        """Test HDFPlanter write method."""
        with tempfile.TemporaryDirectory() as tmpdir:
            h5_path = os.path.join(tmpdir, 'test.h5')
            planter = HDFPlanter(
                h5_path, 
                column_names=['CH1', 'CH2'], 
                sampling_freq=2000
            )
            
            # Mock chunk data
            chunk = MagicMock()
            chunk.data = np.array([[1.0, 2.0], [3.0, 4.0]])
            chunk.timestamps = np.array([1000, 1001])
            
            with planter:
                planter.write(chunk.data)
            
            # Check file was created
            assert os.path.exists(h5_path)
            
            # Verify HDF5 content
            import h5py
            with h5py.File(h5_path, 'r') as f:
                assert 'Data' in f
                assert f['Data'].shape == (2, 2)  # channels x samples  # type: ignore
                assert 'Fs' in f.attrs
                assert f.attrs['Fs'] == 2000

    def test_hdf_planter_append_mode(self):
        """Test HDFPlanter append mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            h5_path = os.path.join(tmpdir, 'test.h5')
            
            # First write
            planter1 = HDFPlanter(
                h5_path, 
                column_names=['CH1'], 
                sampling_freq=2000,
                append=True
            )
            chunk1 = MagicMock()
            chunk1.data = np.array([[1.0], [2.0]])
            chunk1.timestamps = np.array([1000, 1001])
            
            with planter1:
                planter1.write(chunk1.data)
            
            # Second write (append)
            planter2 = HDFPlanter(
                h5_path, 
                column_names=['CH1'], 
                sampling_freq=2000,
                append=True
            )
            chunk2 = MagicMock()
            chunk2.data = np.array([[3.0], [4.0]])
            chunk2.timestamps = np.array([1002, 1003])
            
            with planter2:
                planter2.write(chunk2.data)
            
            # Verify combined data
            import h5py
            with h5py.File(h5_path, 'r') as f:
                assert f['Data'].shape == (1, 4)  # 1 channel, 4 samples

    def test_hdf_planter_add_marks(self):
        """Test HDFPlanter add_marks method."""
        with tempfile.TemporaryDirectory() as tmpdir:
            h5_path = os.path.join(tmpdir, 'test.h5')
            planter = HDFPlanter(
                h5_path, 
                column_names=['CH1'], 
                sampling_freq=2000
            )
            
            with planter:
                planter.add_marks(
                    positions=[100, 200],
                    groups=['event1', 'event2'],
                    messages=['start', 'end']
                )
            
            # Verify marks
            import h5py
            with h5py.File(h5_path, 'r') as f:
                assert 'Marks' in f
                marks = f['Marks']
                assert len(marks) == 2  # type: ignore
