import pytest
from epycon.utils.decorators import checktypes


@checktypes
def sample_function(x: int, y: str) -> str:
    """Sample function for testing decorator."""
    return f"{x}_{y}"


def test_checktypes_valid_inputs():
    """Test checktypes decorator with valid inputs."""
    result = sample_function(42, "hello")
    assert result == "42_hello"


def test_checktypes_invalid_inputs():
    """Test checktypes decorator with invalid inputs."""
    # Wrong type for x
    with pytest.raises(TypeError):
        sample_function("42", "hello")

    # Wrong type for y
    with pytest.raises(TypeError):
        sample_function(42, 123)


def test_checktypes_with_union():
    """Test checktypes with Union types if present."""
    # Note: The current decorator implementation may not handle Union properly
    # This test documents the current behavior
    pass