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


class TestRawAndRail:
    def test_raw_int_dtype_and_length(self):
        from epycon.extraction import load_segments, read_raw_window
        segs = load_segments(str(REAL), VER)
        seg = [s for s in segs if s["id"] == "00000005"][0]
        raw = read_raw_window(seg, 1316, 9316, VER)
        assert raw.dtype == np.int64
        assert raw.shape[0] == 8000

    def test_v6_column_railed(self):
        from epycon.extraction import load_segments, read_raw_window, is_railed
        segs = load_segments(str(REAL), VER)
        seg = [s for s in segs if s["id"] == "00000005"][0]
        names = seg["header"].get_chnames()
        v6_ref = seg["header"].channels.content[names.index("V6")].reference
        raw = read_raw_window(seg, 1316, 9316, VER)
        col = raw[:, v6_ref]
        assert bool(np.all(col == -2147483649))
        assert is_railed(col) is True

    def test_connected_column_not_railed(self):
        from epycon.extraction import load_segments, read_raw_window, is_railed
        segs = load_segments(str(REAL), VER)
        seg = [s for s in segs if s["id"] == "00000005"][0]
        raw = read_raw_window(seg, 1316, 9316, VER)
        # II 的 reference = 1（连接导联，真实信号）
        assert is_railed(raw[:, 1]) is False


class TestLeadResolve:
    def test_surface_lead_single_source(self):
        from epycon.extraction import load_segments, resolve_lead_sources
        seg = load_segments(str(REAL), VER)[0]
        out = resolve_lead_sources(seg["header"], ["V6"], False)
        assert out[0][0] == "V6"
        assert len(out[0][1]) == 1

    def test_bipolar_sign_is_uminus_minus_uplus(self):
        from epycon.extraction import (
            load_segments, resolve_lead_sources, read_raw_window, _lead_signal)
        seg = [s for s in load_segments(str(REAL), VER) if s["id"] == "00000005"][0]
        raw = read_raw_window(seg, 1316, 9316, VER)
        # 手算 u- - u+：从 header 取 CS 3-4 的两源 reference
        content = seg["header"].channels.content
        names = [c.name for c in content]
        ref_uplus = content[names.index("u+CS 3-4")].reference
        ref_uminus = content[names.index("u-CS 3-4")].reference
        expected = raw[:, ref_uminus] - raw[:, ref_uplus]
        sources = resolve_lead_sources(seg["header"], ["CS 3-4"], False)[0][1]
        got = _lead_signal(raw, sources)
        assert np.array_equal(got, expected)

    def test_unknown_lead_raises_with_available(self):
        from epycon.extraction import load_segments, resolve_lead_sources
        seg = load_segments(str(REAL), VER)[0]
        with pytest.raises(ExtractionError, match="NOPE"):
            resolve_lead_sources(seg["header"], ["NOPE"], False)

    def test_raw_unipolar_exposes_uplus_uminus(self):
        from epycon.extraction import load_segments, resolve_lead_sources
        seg = load_segments(str(REAL), VER)[0]
        out = resolve_lead_sources(seg["header"], ["u+CS 3-4"], True)
        assert out[0][0] == "u+CS 3-4"

    def test_exact_match_no_fuzzy_on_dirty_name(self):
        # 头中存在含 \x00 的脏名（如 '8\x00 3-4'）；请求去空/清洗版 '8 3-4'
        # 必须精确匹配失败报错，绝不模糊命中（第 7 节脏名精确匹配约定）
        from epycon.extraction import load_segments, resolve_lead_sources
        seg = load_segments(str(REAL), VER)[0]
        with pytest.raises(ExtractionError):
            resolve_lead_sources(seg["header"], ["8 3-4"], True)


class TestExtractWindow:
    def test_connected_and_railed_mix(self):
        from epycon.extraction import extract_window
        r = extract_window(str(REAL), at_elapsed="1:07:15",
                           leads=["II", "V6"], window=2.0, version=VER)
        assert r["log"] == "00000005"
        assert r["units"] == "uV"
        assert r["fs"] == 2000
        by = {ld["name"]: ld for ld in r["leads"]}
        assert by["II"]["status"] == "ok"
        assert by["II"]["n"] == 8000
        assert by["V6"]["status"] == "rejected"
        assert r["returned_window"]["clipped"] is False

    def test_gap_rejects(self):
        from epycon.extraction import extract_window
        with pytest.raises(ExtractionError, match="空档"):
            extract_window(str(REAL), at_elapsed="1:07:12",
                           leads=["II"], window=2.0, version=VER)

    def test_clip_reports_missing(self):
        from epycon.extraction import extract_window
        r = extract_window(str(REAL), at_elapsed="1:07:13",
                           leads=["II"], window=2.0, version=VER)
        assert r["returned_window"]["clipped"] is True
        assert r["returned_window"]["missing_s"] == pytest.approx(1.342, abs=1e-3)
        # 裁剪后样本数 = 未裁前 8000 − 缺失 2684 = 5316，且与实际返回一致
        assert r["leads"][0]["n"] == 5316

    def test_raw_counts_units(self):
        from epycon.extraction import extract_window
        r = extract_window(str(REAL), at_elapsed="1:07:15",
                           leads=["II"], window=2.0, raw_counts=True, version=VER)
        assert r["units"] == "counts"
        assert all(isinstance(x, int) for x in r["leads"][0]["samples"][:5])

    def test_conflicting_targets_raise(self):
        from epycon.extraction import extract_window
        with pytest.raises(ExtractionError, match="互斥"):
            extract_window(str(REAL), at_elapsed="1:07:15",
                           at_epoch=1764301819.403, leads=["II"], version=VER)

    def test_epoch_target_path(self):
        from epycon.extraction import extract_window
        r = extract_window(str(REAL), at_epoch=1764301819.403,
                           leads=["II"], window=2.0, version=VER)
        assert r["log"] == "00000005"
        assert r["leads"][0]["n"] == 8000

    def test_before_after_override(self):
        from epycon.extraction import extract_window
        # 段内偏移 2.658s，[1.658, 4.658] → (1.0+2.0)*2000 = 6000，区别于对称 window=2 的 8000
        r = extract_window(str(REAL), at_elapsed="1:07:15", leads=["II"],
                           before=1.0, after=2.0, version=VER)
        assert r["leads"][0]["n"] == 6000
        assert r["returned_window"]["clipped"] is False

    def test_far_gap_rejects(self):
        from epycon.extraction import extract_window
        # 0:31:00 = 1860s，落在 seg0(止~10.5s) 与 seg1(起 1872.9s) 间的分钟级空档
        with pytest.raises(ExtractionError, match="空档"):
            extract_window(str(REAL), at_elapsed="0:31:00",
                           leads=["II"], version=VER)

    def test_default_version_from_config(self, monkeypatch):
        from epycon.extraction import extract_window
        # 不传 version → _default_version 取 config 的 4.3.2；realdata 正是该版本。
        # 清掉 EPYCON_CONFIG，确保落到包内默认 config（否则用户环境可能指向别的 config）。
        monkeypatch.delenv("EPYCON_CONFIG", raising=False)
        r = extract_window(str(REAL), at_elapsed="1:07:15", leads=["II"])
        assert r["version"] == "4.3.2"
        assert r["log"] == "00000005"
