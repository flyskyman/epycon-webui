import pytest
from epycon.utils.person import Tokenize, CzechPersonID


def test_tokenize_basic():
    """Test Tokenize class basic functionality."""
    used_tokens = {}
    tokenizer = Tokenize(num_bytes=4, used_tokens=used_tokens)

    token1 = tokenizer()
    assert len(token1) == 8  # 4 bytes = 8 hex chars
    assert token1 in used_tokens
    assert used_tokens[token1] == {"sid": "", "procedure_date": ""}

    # Generate another token, should be different
    token2 = tokenizer()
    assert token1 != token2
    assert token2 in used_tokens


def test_tokenize_collision_handling():
    """Test Tokenize handles collisions (though very unlikely)."""
    used_tokens = {}
    tokenizer = Tokenize(num_bytes=1, used_tokens=used_tokens)  # Small space for testing

    # Fill up the small token space
    tokens = set()
    for _ in range(100):  # Should cover most of the 256 possible tokens
        token = tokenizer()
        assert token not in tokens  # No duplicates
        tokens.add(token)

    # All tokens should be in used_tokens
    assert len(used_tokens) == len(tokens)


# def test_czech_person_id_validate_sid():
#     """Test CzechPersonID._validate_sid."""
#     # Valid SID (as string)
#     original_sid = "12345678"
#     result = CzechPersonID._validate_sid(original_sid)
#     assert isinstance(result, int)
#     assert result == 12345678


def test_czech_person_id_validate_sex():
    """Test CzechPersonID._validate_sex."""
    # Test basic functionality
    result = CzechPersonID._validate_sex("00000000")
    assert result in ["male", "female", "none"]


def test_czech_person_id_age_not_implemented():
    """Test CzechPersonID.age raises NotImplementedError."""
    with pytest.raises(NotImplementedError):
        CzechPersonID.age(None, None)