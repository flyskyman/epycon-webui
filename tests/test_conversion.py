"""epycon.conversion 共享转换核心测试

覆盖：标注定位的唯一权威实现 entries_to_marks、convert_study 直调，
以及 GUI 路径 (app_gui.execute_epycon_conversion) 与 CLI 路径的等价性——
两端此前各自维护平行实现并漂移出多个定位 bug，等价性测试防止再次分叉。
"""
import json
import logging
import os
import shutil
import sys
from pathlib import Path
from unittest.mock import patch

import h5py
import pytest

from epycon.__main__ import main as entry_point
from epycon.conversion import (
    convert_study, entries_to_marks, reattribute_entries, reconcile_entries, record_date,
    strip_log_suffix,
)
from epycon.core._dataclasses import Entry
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

    def test_sample_index_cross_check_warns_but_keeps_timestamp_position(self, caplog):
        # issue #36：0x06 采样索引只交叉校验，偏差 >1 样本告警，定位仍以时间戳为准
        import logging
        logger = logging.getLogger("test_marks")
        entry = FakeEntry("a", 100.5)
        entry.sample_index = 400
        with caplog.at_level(logging.WARNING, logger="test_marks"):
            marks = entries_to_marks([entry], "a", 100.0, self.FS, 5000, logger=logger)
        assert [m[0] for m in marks] == [500]
        assert "sample_index=400" in caplog.text

    def test_sample_index_within_one_sample_is_silent(self, caplog):
        import logging
        logger = logging.getLogger("test_marks")
        entry = FakeEntry("a", 100.5)
        entry.sample_index = 499
        with caplog.at_level(logging.WARNING, logger="test_marks"):
            marks = entries_to_marks([entry], "a", 100.0, self.FS, 5000, logger=logger)
        assert [m[0] for m in marks] == [500]
        assert caplog.text == ""


def test_reattribute_entries_by_timestamp_and_sample_index():
    """issue #36：fid 指向的文件与时间戳矛盾、而时间戳+采样索引唯一落在另一文件 → 改判；
    fid 自洽 / 无唯一命中 / 无 sample_index（GUI FakeEntry）→ 原样"""
    index = {"00000000": (100.0, 1000, 5000), "00000001": (200.0, 1000, 5000)}
    stale = Entry(fid="00000000", group="PACE", timestamp=200.05, message="S1=500", sample_index=50)
    ok = Entry(fid="00000001", group="PACE", timestamp=200.05, message="x", sample_index=50)
    nohit = Entry(fid="00000000", group="PACE", timestamp=300.05, message="y", sample_index=50)
    fake = FakeEntry("00000000", 200.05)
    out = reattribute_entries([stale, ok, nohit, fake], index)
    assert [e.fid for e in out] == ["00000001", "00000001", "00000000", "00000000"]
    assert out[0].message == "S1=500" and out[0].sample_index == 50


def test_reconcile_entries_indexes_every_study_log():
    """索引取 study 全部 DFile（不受 data.data_files 过滤影响）：夹具里 fid 指 00000000、
    时间戳+采样索引落在 00000001 → 改判"""
    stale = Entry(fid="00000000", group="PACE", timestamp=1769608092.303, message="S1=500", sample_index=50)
    out = reconcile_entries(str(STUDY), [stale], "4.3.2")
    assert out[0].fid == "00000001"
    assert reconcile_entries(str(STUDY), [], "4.3.2") == []


def test_reconcile_entries_skips_unreadable_dfile(tmp_path, caplog):
    """一个无关 DFile 截断（NAS 同步瞬态/残缺拷贝）只丢它自己的索引项，其余改判照常，且记 warning"""
    import logging
    import shutil
    study = tmp_path / "study01"
    shutil.copytree(STUDY, study)
    (study / "00000002.log").write_bytes((study / "00000000.log").read_bytes()[:100])
    stale = Entry(fid="00000000", group="PACE", timestamp=1769608092.303, message="S1=500", sample_index=50)
    logger = logging.getLogger("test_reconcile")
    with caplog.at_level(logging.WARNING, logger="test_reconcile"):
        out = reconcile_entries(str(study), [stale], "4.3.2", logger)
    assert out[0].fid == "00000001"
    assert "00000002: header unreadable" in caplog.text


def test_record_date_uses_acquisition_machine_offset():
    """issue #36：epoch 是墙钟按采集机 OS 时区解释的结果，RecordDate 须按该偏移还原墙钟；
    无偏移信息时保持此前的分析机本地时间"""
    from datetime import datetime
    ts = 1769608079.246
    assert record_date(ts, 8 * 3600) == "2026-01-28T21:47:59.246000+08:00"
    assert record_date(ts, -6 * 3600) == "2026-01-28T07:47:59.246000-06:00"
    assert record_date(ts, None) == datetime.fromtimestamp(ts).isoformat()
    assert record_date(0, 8 * 3600) == ""


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

    @pytest.mark.parametrize("merge", [True, False])
    def test_record_date_attribute_carries_offset(self, tmp_path, entries, merge):
        cfg = _base_cfg(STUDY.parent, tmp_path, merge=merge)
        cfg["entries"]["convert"] = False
        convert_study(str(STUDY), "study01", str(tmp_path), cfg, entries, utc_offset_sec=8 * 3600)
        out = tmp_path / ("study01_merged.h5" if merge else "00000000.h5")
        with h5py.File(out, "r") as f:
            assert f.attrs["RecordDate"] == "2026-01-28T21:47:59.246000+08:00"

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

    def test_csv_and_h5_agree_on_values_and_units(self, tmp_path, entries):
        """同一输入的 CSV 与 HDF5 必须数值+单位一致（KNOWN_ISSUES #27 入口 A）。

        此前 CSVPlanter 静默丢弃 factor/units：CSV 写 nV 裸数值、表头无单位，
        与同一次转换的 HDF5（µV）相差 1000×。
        """
        h5_dir, csv_dir = tmp_path / "h5", tmp_path / "csv"
        for out_dir, fmt in ((h5_dir, "h5"), (csv_dir, "csv")):
            cfg = _base_cfg(STUDY.parent, out_dir, merge=False)
            cfg["data"]["output_format"] = fmt
            cfg["entries"]["convert"] = False
            convert_study(str(STUDY), "study01", str(out_dir), cfg, entries)

        with h5py.File(h5_dir / "00000000.h5", "r") as f:
            h5_first_row = f["Data"][:, 0] if f["Data"].shape[0] < f["Data"].shape[1] \
                else f["Data"][0, :]

        lines = (csv_dir / "00000000.csv").read_text(encoding="utf-8").splitlines()
        header, first_row = lines[0], lines[1]

        # 表头必须声明单位
        assert all("(uV)" in col for col in header.split(","))
        # 数值必须与 HDF5 逐列一致
        csv_vals = [float(v) for v in first_row.split(",")]
        assert csv_vals == pytest.approx(list(map(float, h5_first_row)), rel=1e-5)

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


# ========================= 截断 DFile（issue #41） =========================

def _study_with_truncated(tmp_path, *fids):
    """复制夹具到 tmp_path/in/study01 并把指定 DFile 截到 100 字节（issue #41 复现步骤）"""
    study = tmp_path / "in" / "study01"
    shutil.copytree(STUDY, study)
    for fid in fids:
        path = study / f"{fid}.log"
        path.write_bytes(path.read_bytes()[:100])
    return study


class TestTruncatedDFile:
    """截断 DFile 的可读性判定只有一处（read_datalog_headers），reconcile_entries 与
    convert_study 都消费它：部分不可读 → 警告并排除，逐文件标注与波形覆盖同一集合；
    全部不可读 → 显式失败，不留只有 CSV 的输出目录。"""

    @pytest.mark.parametrize("merge", [True, False])
    def test_convert_study_excludes_truncated_dfile(self, tmp_path, merge, caplog):
        study = _study_with_truncated(tmp_path, "00000000")
        out = tmp_path / "out"
        cfg = _base_cfg(study.parent, out, merge=merge)
        cfg["entries"]["output_format"] = "csv"
        entries = readentries(f_path=str(study / "entries.log"), version="4.3.2")
        logger = logging.getLogger("test_truncated")
        with caplog.at_level(logging.WARNING, logger="test_truncated"):
            n = convert_study(str(study), "study01", str(out), cfg, entries, logger=logger)
        assert n == 1
        assert caplog.text.count("00000000: header unreadable") == 1
        if merge:
            with h5py.File(out / "study01_merged.h5", "r") as f:
                assert f.attrs["datalog_ids"] == "00000001"
                assert max(f["Data"].shape) == 1024
        else:
            assert sorted(p.name for p in out.iterdir()) == ["00000001.h5", "00000001_entries.csv"]

    def test_all_dfiles_unreadable_fails_explicitly(self, tmp_path):
        study = _study_with_truncated(tmp_path, "00000000", "00000001")
        out = tmp_path / "out"
        cfg = _base_cfg(study.parent, out, merge=True)
        with pytest.raises(ValueError, match="unreadable"):
            convert_study(str(study), "study01", str(out), cfg, [])
        assert not out.exists()

    def test_cli_writes_waveform_after_summary_csv(self, tmp_path):
        """issue #41 复现：默认配置跑 CLI，此前写完 entries_summary.csv 后 struct.error 整批崩溃，
        输出目录只剩 CSV 没有 .h5"""
        study = _study_with_truncated(tmp_path, "00000000")
        out = tmp_path / "out"
        out.mkdir()
        env = {
            "EPYCON_CONFIG": str(ROOT / "epycon" / "config" / "config.json"),
            "EPYCON_JSONSCHEMA": str(ROOT / "epycon" / "config" / "schema.json"),
        }
        argv = ["epycon", "-i", str(study.parent), "-o", str(out)]
        with patch.dict(os.environ, env), patch.object(sys, "argv", argv):
            entry_point()
        names = {p.name for p in (out / "study01").iterdir()}
        assert "entries_summary.csv" in names
        assert (out / "study01" / "00000001.h5").stat().st_size > 0
        assert not any(name.startswith("00000000") for name in names)


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
