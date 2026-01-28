import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock
from epycon.iou.parsers import LogParser


class TestLogParser:
    """Test LogParser functionality."""

    def test_log_parser_init(self):
        """Test LogParser initialization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, 'test.log')
            with open(log_path, 'wb') as f:
                f.write(b'fake log data')
            
            parser = LogParser(log_path, version='4.3.2')
            # Check that diary is set correctly for x64 version
            from epycon.iou.parsers import WMx64LogSchema
            assert parser.diary == WMx64LogSchema

    @patch('epycon.iou.parsers._readmaster')
    @patch('epycon.iou.parsers.Header')
    def test_log_parser_get_header(self, mock_header_class, mock_readmaster):
        """Test LogParser get_header method."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, 'test.log')
            with open(log_path, 'wb') as f:
                f.write(b'fake log data')
            
            # Mock header
            mock_header = MagicMock()
            mock_header.amp.sampling_freq = 2000
            mock_header.num_channels = 4
            mock_header_class.return_value = mock_header
            
            parser = LogParser(log_path, version='4.3.2')
            parser._header = mock_header  # Simulate header being set
            header = parser.get_header()
            
            assert header == mock_header

    def test_log_parser_iteration(self):
        """Test LogParser iteration setup (simplified)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, 'test.log')
            with open(log_path, 'wb') as f:
                f.write(b'fake log data')
            
            parser = LogParser(log_path, version='4.3.2')
            # Test that parser is properly initialized as an iterator
            assert hasattr(parser, '__next__')
            assert hasattr(parser, '__iter__')

    def test_log_parser_context_manager(self):
        """Test LogParser context manager interface (simplified)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, 'test.log')
            with open(log_path, 'wb') as f:
                f.write(b'fake log data')
            
            parser = LogParser(log_path, version='4.3.2')
            # Test that parser has context manager methods
            assert hasattr(parser, '__enter__')
            assert hasattr(parser, '__exit__')