import pytest
from datetime import datetime
from epycon.core._formatting import _tosel
from epycon.core._dataclasses import Entry


def test_tosel_basic():
    """Test _tosel function with basic entries."""
    entries = [
        Entry(timestamp=1000, group="test_group", fid="file1", message="test message 1"),
        Entry(timestamp=1001, group="test_group", fid="file1", message="test message 2"),
    ]

    channel_names = ["CH1", "CH2"]
    result = _tosel(entries, ref_timestamp=1000.0, sampling_freq=1000, channel_names=channel_names, file_name="test.h5")

    # Check that result contains expected content
    assert "test_group" in result
    assert "test message 1" in result
    assert "test message 2" in result
    assert "test.h5" in result

    # Should contain SEL format markers
    assert "SEL_START" in result or "SignalPlant" in result
    assert "SEL_END" in result or "DATA" in result


def test_tosel_with_timestamps():
    """Test _tosel with ref_timestamp."""
    entries = [
        Entry(timestamp=1000, group="group1", fid="f1", message="msg1"),
    ]

    # Test with ref_timestamp
    result_with_ref = _tosel(entries, ref_timestamp=1000.0, sampling_freq=1000,
                           channel_names=["CH1"], file_name="test.h5")
    assert "group1" in result_with_ref
    assert "msg1" in result_with_ref