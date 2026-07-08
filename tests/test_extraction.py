# tests/test_extraction.py
from pathlib import Path

import numpy as np
import pytest

from epycon.extraction import parse_elapsed, ExtractionError

ROOT = Path(__file__).parent.parent
REAL = ROOT / "examples" / "data" / "realdata"
STUDY01 = ROOT / "examples" / "data" / "study01"
VER = "4.3.2"


class TestParseElapsed:
    def test_whole_seconds(self):
        assert parse_elapsed("1:07:15") == 4035.0

    def test_subsecond(self):
        assert parse_elapsed("0:00:00.500") == pytest.approx(0.5)

    def test_two_digit_hours(self):
        assert parse_elapsed("10:00:00") == 36000.0

    def test_malformed_raises(self):
        with pytest.raises(ExtractionError):
            parse_elapsed("1:07")
