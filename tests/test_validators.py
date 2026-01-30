import pytest
from epycon.core._validators import _validate_int, _validate_str


def test_validate_int_valid_inputs():
    """Test _validate_int with valid inputs."""
    assert _validate_int("test", 5, min_value=0, mxn_value=10) == 5
    assert _validate_int("test", 5.0, min_value=0, mxn_value=10) == 5
    assert _validate_int("test", None, min_value=0, mxn_value=10) is None


def test_validate_int_invalid_inputs():
    """Test _validate_int with invalid inputs."""
    # Non-integer
    with pytest.raises(ValueError, match="expected to be an"):
        _validate_int("test", "not_a_number", min_value=0)

    # Float with decimal
    with pytest.raises(ValueError, match="expected to be an"):
        _validate_int("test", 5.5, min_value=0)

    # Below minimum
    with pytest.raises(ValueError, match="expected to be an"):
        _validate_int("test", -1, min_value=0)

    # Above maximum
    with pytest.raises(ValueError, match="expected to be an"):
        _validate_int("test", 15, min_value=0, mxn_value=10)


def test_validate_str_valid_inputs():
    """Test _validate_str with valid inputs."""
    valid_set = {".csv", ".h5"}
    assert _validate_str("test", ".csv", valid_set=valid_set) == ".csv"
    assert _validate_str("test", None, valid_set=valid_set) is None


def test_validate_str_invalid_inputs():
    """Test _validate_str with invalid inputs."""
    valid_set = {".csv", ".h5"}

    # Non-string
    with pytest.raises(ValueError, match="expected to be from"):
        _validate_str("test", 123, valid_set=valid_set)

    # Not in valid set
    with pytest.raises(ValueError, match="expected to be from"):
        _validate_str("test", ".txt", valid_set=valid_set)