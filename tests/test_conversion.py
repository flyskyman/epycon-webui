"""epycon.conversion 共享转换核心测试

覆盖：标注定位的唯一权威实现 entries_to_marks、convert_study 直调，
以及 GUI 路径 (app_gui.execute_epycon_conversion) 与 CLI 路径的等价性——
两端此前各自维护平行实现并漂移出多个定位 bug，等价性测试防止再次分叉。
"""
import json
from pathlib import Path

import h5py
import pytest

from epycon.conversion import convert_study, entries_to_marks, strip_log_suffix
from epycon.iou import readentries

ROOT = Path(__file__).parent.parent
STUDY = ROOT / "examples" / "data" / "study01"


class FakeEntry:
    def __init__(self, fid, timestamp, group="NOTE", message="m"):
        self.fid = fid
        self.timestamp = timestamp
        self.group = group
        self.message = message


def _base_cfg(input_folder, output_folder, merge=True):
    cfg = json.loads((ROOT / "epycon" / "config" / "config.json").read_text(encoding="utf-8"))
    cfg["paths"]["input_folder"] = str(input_folder)
    cfg["paths"]["output_folder"] = str(output_folder)
    cfg["paths"]["studies"] = ["study01"]
    cfg["data"]["merge_logs"] = merge
    return cfg


# ========================= entries_to_marks =========================

class TestEntriesToMarks:
    FS = 1000

    def test_fid_mismatch_skipped(self):
        entries = [FakeEntry("00000001", 100.5)]
        assert entries_to_marks(entries, "00000000", 100.0, self.FS, 5000) == []

    def test_negative_offset_rejected(self):
        entries = [FakeEntry("a", 99.5)]
        assert entries_to_marks(entries, "a", 100.0, self.FS, 5000) == []

    def test_position_at_or_beyond_end_rejected(self):
        entries = [FakeEntry("a", 105.0)]  # 正好 5000，超出 [0, 5000)
        assert entries_to_marks(entries, "a", 100.0, self.FS, 5000) == []

    def test_subsecond_rounding_not_truncation(self):
        # 大数量级 epoch 相减的浮点误差：0.050 -> 0.0499999...，int() 会偏一个采样点
        entries = [FakeEntry("a", 1769608092.303)]
        marks = entries_to_marks(entries, "a", 1769608092.253, self.FS, 1024)
        assert [m[0] for m in marks] == [50]

    def test_base_offset_applied(self):
        entries = [FakeEntry("a", 100.5)]
        marks = entries_to_marks(entries, "a", 100.0, self.FS, 5000, base_offset=1024)
        assert [m[0] for m in marks] == [1524]


def test_strip_log_suffix():
    assert strip_log_suffix("00000000.log") == "00000000"
    assert strip_log_suffix("00000000") == "00000000"
    # rstrip(".log") 的字符集语义会把它剥成 "0000000"——本函数必须保留
    assert strip_log_suffix("0000000g.log") == "0000000g"


# ========================= convert_study 直调 =========================

class TestConvertStudy:
    @pytest.fixture
    def entries(self):
        return readentries(f_path=str(STUDY / "entries.log"), version="4.3.2")

    def test_merge_marks_position(self, tmp_path, entries):
        cfg = _base_cfg(STUDY.parent, tmp_path, merge=True)
        n = convert_study(str(STUDY), "study01", str(tmp_path), cfg, entries)
        assert n == 2
        with h5py.File(tmp_path / "study01_merged.h5", "r") as f:
            assert max(f["Data"].shape) == 2048
            positions = [int(r["SampleLeft"]) for r in f["Marks"][:]]
            assert positions == [1074]  # 1024 文件偏移 + 50 亚秒偏移

    def test_normal_mode_marks_position(self, tmp_path, entries):
        cfg = _base_cfg(STUDY.parent, tmp_path, merge=False)
        cfg["entries"]["convert"] = False
        n = convert_study(str(STUDY), "study01", str(tmp_path), cfg, entries)
        assert n == 2
        with h5py.File(tmp_path / "00000001.h5", "r") as f:
            positions = [int(r["SampleLeft"]) for r in f["Marks"][:]]
            assert positions == [50]
        with h5py.File(tmp_path / "00000000.h5", "r") as f:
            assert "Marks" not in f  # fid 都指向 00000001

    @pytest.mark.parametrize("merge", [True, False])
    def test_units_label_is_uv(self, tmp_path, entries, merge):
        """输出单位必须标 uV：量纲链 raw × resolution(78 nV/LSb) / factor(1000) = uV。

        曾误标 mV（KNOWN_ISSUES #19），差 1000×。
        """
        cfg = _base_cfg(STUDY.parent, tmp_path, merge=merge)
        convert_study(str(STUDY), "study01", str(tmp_path), cfg, entries)
        out = tmp_path / ("study01_merged.h5" if merge else "00000000.h5")
        with h5py.File(out, "r") as f:
            units = {row["Units"].decode() if isinstance(row["Units"], bytes)
                     else row["Units"] for row in f["Info"][:]}
        assert units == {"uV"}


# ========================= GUI 路径等价性 =========================

class TestGuiConversionEquivalence:
    """GUI 的 execute_epycon_conversion 必须与 CLI 共享核心产生一致结果"""

    @pytest.fixture
    def app_gui_module(self):
        pytest.importorskip("tkinter")
        import app_gui
        return app_gui

    def _gui_cfg(self, tmp_path, merge):
        return {
            "paths": {
                "input_folder": str(STUDY.parent),
                "output_folder": str(tmp_path),
                "studies": ["study01"],
            },
            "data": {
                "output_format": "h5",
                "merge_logs": merge,
                "pin_entries": True,
                "leads": "original",
                "data_files": [],
                "channels": [],
                "custom_channels": {},
            },
            "entries": {
                "convert": False,
                "output_format": "csv",
                "summary_csv": False,
                "filter_annotation_type": [],
            },
            "global_settings": {
                "workmate_version": "4.3.2",
                "processing": {"chunk_size": 1024},
            },
        }

    def test_gui_merge_matches_cli(self, tmp_path, app_gui_module):
        ok, logs = app_gui_module.execute_epycon_conversion(self._gui_cfg(tmp_path, merge=True))
        assert ok, logs
        merged = tmp_path / "study01" / "study01_merged.h5"
        assert merged.exists()
        with h5py.File(merged, "r") as f:
            assert max(f["Data"].shape) == 2048
            positions = [int(r["SampleLeft"]) for r in f["Marks"][:]]
            assert positions == [1074]  # 与 CLI 路径完全一致

    def test_gui_normal_mode_embeds_marks(self, tmp_path, app_gui_module):
        """回归：旧 GUI 实现因 e.msg 字段名错误，单文件模式标注嵌入必崩"""
        ok, logs = app_gui_module.execute_epycon_conversion(self._gui_cfg(tmp_path, merge=False))
        assert ok, logs
        with h5py.File(tmp_path / "study01" / "00000001.h5", "r") as f:
            positions = [int(r["SampleLeft"]) for r in f["Marks"][:]]
            assert positions == [50]
