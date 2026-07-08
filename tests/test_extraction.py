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


class TestLoadSegments:
    def test_realdata_twelve_sorted(self):
        from epycon.extraction import load_segments
        segs = load_segments(str(REAL), VER)
        assert len(segs) == 12
        assert [s["id"] for s in segs] == sorted(s["id"] for s in segs)
        assert segs[0]["id"] == "00000000"

    def test_seg0_header_fields(self):
        from epycon.extraction import load_segments
        s0 = load_segments(str(REAL), VER)[0]
        assert s0["fs"] == 2000
        assert s0["resolution"] == 78
        assert s0["ts"] == pytest.approx(1764297784.403, abs=1e-3)
        assert s0["ns"] > 20000
        assert s0["dur"] == pytest.approx(s0["ns"] / 2000)


class TestConsistency:
    def test_realdata_passes(self):
        from epycon.extraction import load_segments, check_consistency
        segs = load_segments(str(REAL), VER)
        entries = check_consistency(str(REAL), segs, VER)
        assert len(entries) == 12

    def test_study01_fails(self):
        from epycon.extraction import load_segments, check_consistency
        segs = load_segments(str(STUDY01), "4.3.2")
        with pytest.raises(ExtractionError, match="00000001"):
            check_consistency(str(STUDY01), segs, "4.3.2")

    def test_missing_entries_raises(self, tmp_path):
        from epycon.extraction import check_consistency
        with pytest.raises(ExtractionError, match="entries"):
            check_consistency(str(tmp_path), [], VER)


class TestLocateAndWindow:
    def test_locate_hits_segment5(self):
        from epycon.extraction import load_segments, locate_segment
        segs = load_segments(str(REAL), VER)
        zero = segs[0]["ts"]
        seg = locate_segment(segs, zero + 4035.0)  # 1:07:15
        assert seg["id"] == "00000005"

    def test_locate_gap_returns_none(self):
        from epycon.extraction import load_segments, locate_segment
        segs = load_segments(str(REAL), VER)
        zero = segs[0]["ts"]
        assert locate_segment(segs, zero + 4032.0) is None  # 1:07:12，段5起点前

    def test_window_full_within_segment(self):
        from epycon.extraction import _window_samples
        seg = {"fs": 2000, "ns": 21011}
        s0, s1, mb, ma = _window_samples(seg, 2.658, 2.0, 2.0)
        assert (s0, s1) == (1316, 9316)
        assert s1 - s0 == 8000
        assert mb == 0.0 and ma == 0.0

    def test_window_clipped_at_start(self):
        from epycon.extraction import _window_samples
        seg = {"fs": 2000, "ns": 21011}
        s0, s1, mb, ma = _window_samples(seg, 0.658, 2.0, 2.0)
        assert s0 == 0
        assert mb == pytest.approx(1.342, abs=1e-6)
