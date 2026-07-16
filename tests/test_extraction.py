# tests/test_extraction.py
#
# 分两层：纯逻辑测试（parse_elapsed 范围、_window_samples 裁剪、is_railed、
# resolve_lead_sources 校验、fail-closed 守卫）不依赖数据文件，CI 上照常运行；
# realdata 集成测试断言源自真实临床采集（gitignored、不入库），本地才有——
# 用 real_only 标记，缺失时可见跳过。合成 CI 集成夹具见 KNOWN_ISSUES。
from pathlib import Path

import numpy as np
import pytest

from epycon.extraction import parse_elapsed, ExtractionError

ROOT = Path(__file__).parent.parent
REAL = ROOT / "examples" / "data" / "realdata"
STUDY01 = ROOT / "examples" / "data" / "study01"
VER = "4.3.2"

real_only = pytest.mark.skipif(
    not REAL.exists(),
    reason="realdata 为本地临床数据（gitignored，不入库）；集成测试仅本地运行")


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

    def test_out_of_range_minute_rejected(self):
        # 0:67:15 不可静默归一化成 1:07:15（否则提取到非本意的段）
        with pytest.raises(ExtractionError, match="越界"):
            parse_elapsed("0:67:15")

    def test_out_of_range_second_rejected(self):
        with pytest.raises(ExtractionError, match="越界"):
            parse_elapsed("1:07:60")

    def test_negative_hour_rejected(self):
        with pytest.raises(ExtractionError, match="越界"):
            parse_elapsed("-1:00:00")


@real_only
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
    @real_only
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
    @real_only
    def test_locate_hits_segment5(self):
        from epycon.extraction import load_segments, locate_segment
        segs = load_segments(str(REAL), VER)
        zero = segs[0]["ts"]
        seg = locate_segment(segs, zero + 4035.0)  # 1:07:15
        assert seg["id"] == "00000005"

    @real_only
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


@real_only
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
        # 未连接电极停在 int32 正向满量程。此处原断言 -2147483649 ——
        # 那是 _twos_complement off-by-one 的产物，非文件真值（见
        # tests/test_parsers_extended.py::TestTwosComplementBoundary）
        assert bool(np.all(col == 2147483647))
        assert is_railed(col) is True
        # 修复后不得再出现越界 int32 值
        assert raw.min() >= -2147483648 and raw.max() <= 2147483647

    def test_connected_column_not_railed(self):
        from epycon.extraction import load_segments, read_raw_window, is_railed
        segs = load_segments(str(REAL), VER)
        seg = [s for s in segs if s["id"] == "00000005"][0]
        raw = read_raw_window(seg, 1316, 9316, VER)
        # II 的 reference = 1（连接导联，真实信号）
        assert is_railed(raw[:, 1]) is False


@real_only
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


@real_only
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

    def test_negative_window_raises(self):
        from epycon.extraction import extract_window
        # 负 before/after 会造出不含目标的窗口 → 必须报错，不可静默返回
        with pytest.raises(ExtractionError, match="不可为负"):
            extract_window(str(REAL), at_elapsed="1:07:15", leads=["II"],
                           before=-1.0, after=3.0, version=VER)

    def test_bad_default_config_raises_extraction_error(self, monkeypatch):
        from epycon.extraction import extract_window
        # 不带 version + config 不可读 → 转成 ExtractionError（而非漏出 FileNotFoundError）
        monkeypatch.setenv("EPYCON_CONFIG", str(REAL / "does_not_exist.json"))
        with pytest.raises(ExtractionError, match="workmate_version"):
            extract_window(str(REAL), at_elapsed="1:07:15", leads=["II"])

    def test_invalid_version_raises_extraction_error(self):
        from epycon.extraction import extract_window
        # 非法 --version 须转 ExtractionError（而非 LogParser 的 ValueError 逃逸成 traceback）
        with pytest.raises(ExtractionError, match="workmate_version"):
            extract_window(str(REAL), at_elapsed="1:07:15", leads=["II"],
                           version="bad")


class TestLeadSourceValidation:
    def _fake_header(self, name, reference, num_channels=88):
        from types import SimpleNamespace
        from epycon.core._dataclasses import Channel, Channels
        channels = Channels([Channel(name, reference, "ECG", ())], {name: (0,)})
        return SimpleNamespace(channels=channels, num_channels=num_channels)

    def test_none_reference_rejected(self):
        # inactive 导联（reference=None）必须拒绝，避免 raw_int[:, None] 变 newaxis
        from epycon.extraction import resolve_lead_sources
        header = self._fake_header("BAD", None)
        with pytest.raises(ExtractionError, match="无效"):
            resolve_lead_sources(header, ["BAD"], False)

    def test_out_of_range_reference_rejected(self):
        # 越界 reference（脏 header）必须拒绝，避免 IndexError 逃逸
        from epycon.extraction import resolve_lead_sources
        header = self._fake_header("HI", 999, num_channels=88)
        with pytest.raises(ExtractionError, match="无效"):
            resolve_lead_sources(header, ["HI"], False)


class TestRailPure:
    """is_railed 纯逻辑，用合成数组即可测，CI 可跑。"""

    def test_railed_full_scale_constant(self):
        """满量程 = int32 的两个端点。

        原断言用的 -2147483649 **不是合法 int32 值**，而是 `_twos_complement`
        边界 off-by-one 把 +2147483647 翻出来的产物——测试曾把 bug 钉住。
        """
        from epycon.extraction import is_railed
        assert is_railed(np.full(100, 2147483647, dtype=np.int64)) is True    # 正向满量程
        assert is_railed(np.full(100, -2147483648, dtype=np.int64)) is True   # 负向满量程

    def test_impossible_int32_value_is_not_a_rail(self):
        """-2147483649 超出 int32 值域，修复后不可能出现，不该被当作栏杆值。"""
        from epycon.extraction import is_railed
        assert is_railed(np.full(100, -2147483649, dtype=np.int64)) is False

    def test_constant_but_not_rail_value_is_ok(self):
        from epycon.extraction import is_railed
        # 恒定但非满量程（安静的真实通道）不判 railed
        assert is_railed(np.full(100, 5, dtype=np.int64)) is False

    def test_varying_signal_not_railed(self):
        from epycon.extraction import is_railed
        assert is_railed(np.arange(100, dtype=np.int64)) is False


class TestFailClosedGuardsPure:
    """fail-closed 守卫在读任何数据文件之前触发，故用不存在的目录即可测，CI 可跑。"""
    NODIR = str(ROOT / "no_such_study_dir")

    def test_invalid_version_short_circuits(self):
        from epycon.extraction import extract_window
        with pytest.raises(ExtractionError, match="workmate_version"):
            extract_window(self.NODIR, at_elapsed="1:07:15", leads=["II"],
                           version="bad")

    def test_negative_window_short_circuits(self):
        from epycon.extraction import extract_window
        with pytest.raises(ExtractionError, match="不可为负"):
            extract_window(self.NODIR, at_elapsed="1:07:15", leads=["II"],
                           before=-1.0, after=3.0, version=VER)

    def test_empty_leads_short_circuits(self):
        from epycon.extraction import extract_window
        with pytest.raises(ExtractionError, match="导联"):
            extract_window(self.NODIR, at_elapsed="1:07:15", leads=[], version=VER)

    def test_nan_window_short_circuits(self):
        from epycon.extraction import extract_window
        with pytest.raises(ExtractionError, match="有限值"):
            extract_window(self.NODIR, at_elapsed="1:07:15", leads=["II"],
                           window=float("nan"), version=VER)

    def test_inf_before_short_circuits(self):
        from epycon.extraction import extract_window
        with pytest.raises(ExtractionError, match="有限值"):
            extract_window(self.NODIR, at_elapsed="1:07:15", leads=["II"],
                           before=float("inf"), after=1.0, version=VER)

    def test_bad_default_config_short_circuits(self, monkeypatch):
        from epycon.extraction import extract_window
        monkeypatch.setenv("EPYCON_CONFIG", str(ROOT / "no_such_config.json"))
        with pytest.raises(ExtractionError, match="workmate_version"):
            extract_window(self.NODIR, at_elapsed="1:07:15", leads=["II"])


class TestMalformedInputPure:
    """畸形输入文件的解析异常须转 ExtractionError（CLI 走结构化错误），用临时坏文件即可测。"""

    def test_truncated_log_raises_extraction_error(self, tmp_path):
        from epycon.extraction import load_segments
        (tmp_path / "00000000.log").write_bytes(b"bad")
        with pytest.raises(ExtractionError, match="无法解析"):
            load_segments(str(tmp_path), VER)

    def test_corrupt_entries_raises_extraction_error(self, tmp_path):
        from epycon.extraction import check_consistency
        (tmp_path / "entries.log").write_bytes(b"\x00" * 7)  # 长度非法
        with pytest.raises(ExtractionError, match="无法解析"):
            check_consistency(str(tmp_path), [], VER)
