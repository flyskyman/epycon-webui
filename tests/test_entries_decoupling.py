"""波形与 entries 解耦（GitHub issue #11 / #19）。

单个坏 entry（未初始化哨兵时间戳 2^64/1000 s）曾让 `_tocsv` 的
`datetime.fromtimestamp` 抛 ValueError，CLI 在 convert_study 之前崩溃，
输出目录 0 字节。波形转换不依赖 entries，不得被连坐；entries 侧失败必须
显式（ERROR + 堆栈）、不留上次运行的残留文件、也绝不能反过来删掉波形。
"""
import json
import logging
import os
import shutil
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from epycon.__main__ import main as entry_point
from epycon.config.byteschema import WMx64EntriesSchema
from epycon.conversion import convert_study
from epycon.iou import readentries

ROOT = Path(__file__).parent.parent
STUDY = ROOT / "examples" / "data" / "study01"


def _poison_first_entry(entries_log):
    """把首条 entry 改成 realdata 实测的哨兵：fid=00000000、8 字节 ms 时间戳 0xFF..FF。"""
    raw = bytearray(entries_log.read_bytes())
    base = WMx64EntriesSchema.header[1]
    fid_lo, fid_hi = WMx64EntriesSchema.datalog_id
    raw[base + fid_lo:base + fid_hi] = b"\x00" * (fid_hi - fid_lo)
    ts_lo, ts_hi = WMx64EntriesSchema.timestamp
    raw[base + ts_lo:base + ts_hi] = b"\xff" * (ts_hi - ts_lo)
    entries_log.write_bytes(bytes(raw))


def _copy_study(tmp_path):
    src = tmp_path / "in" / "study01"
    shutil.copytree(STUDY, src)
    return src


def _normal_cfg(data_fmt="h5", entries_fmt="csv"):
    cfg = json.loads((ROOT / "epycon" / "config" / "config.json").read_text(encoding="utf-8"))
    cfg["data"]["merge_logs"] = False
    cfg["data"]["output_format"] = data_fmt
    # 默认 sel 走 _tosel，不经 fromtimestamp，哨兵不触发；测试显式用 csv
    cfg["entries"]["output_format"] = entries_fmt
    return cfg


def _run_cli(src, out):
    env = {
        "EPYCON_CONFIG": str(ROOT / "epycon" / "config" / "config.json"),
        "EPYCON_JSONSCHEMA": str(ROOT / "epycon" / "config" / "schema.json"),
    }
    argv = ["epycon", "-i", str(src.parent), "-o", str(out),
            "-fmt", "h5", "-e", "True", "-efmt", "csv"]
    with patch.dict(os.environ, env), patch.object(sys, "argv", argv):
        entry_point()


def _assert_waveforms_written(study_out, ext="h5"):
    for fid in ("00000000", "00000001"):
        assert (study_out / f"{fid}.{ext}").stat().st_size > 0


def _errors(caplog):
    return [r.message for r in caplog.records if r.levelno >= logging.ERROR]


def test_bad_entry_does_not_block_waveform(tmp_path, caplog):
    src = _copy_study(tmp_path)
    _poison_first_entry(src / "entries.log")
    out = tmp_path / "out"
    study_out = out / "study01"
    study_out.mkdir(parents=True)
    # 上次运行残留的汇总不得在本次失败后幸存（Codex review P2）
    (study_out / "entries_summary.csv").write_text("stale\n", encoding="utf-8")

    with caplog.at_level(logging.ERROR):
        _run_cli(src, out)

    _assert_waveforms_written(study_out)
    # 汇总标注确实失败了：不产出文件，且以 ERROR 显式暴露，不静默
    assert not (study_out / "entries_summary.csv").exists()
    assert any("entries_summary" in m for m in _errors(caplog))


def test_unparseable_entries_log_does_not_block_waveform(tmp_path, caplog):
    """#19 第 1 项：readentries 的 ValueError（字节长度不整除）不得连坐波形。"""
    src = _copy_study(tmp_path)
    with open(src / "entries.log", "ab") as f:
        f.write(b"\x00")
    out = tmp_path / "out"
    out.mkdir()

    with caplog.at_level(logging.ERROR):
        _run_cli(src, out)

    _assert_waveforms_written(out / "study01")
    assert any("ENTRIES" in m for m in _errors(caplog))


def test_parse_failure_clears_stale_annotations(tmp_path, caplog):
    """Codex P2：entries.log 解析失败时，旧汇总与旧逐文件标注都不得幸存。"""
    src = _copy_study(tmp_path)
    with open(src / "entries.log", "ab") as f:
        f.write(b"\x00")
    out = tmp_path / "out"
    study_out = out / "study01"
    study_out.mkdir(parents=True)
    stale = [study_out / "entries_summary.csv", study_out / "00000000.csv"]
    for p in stale:
        p.write_text("stale\n", encoding="utf-8")

    with caplog.at_level(logging.ERROR):
        _run_cli(src, out)

    _assert_waveforms_written(study_out)
    assert not any(p.exists() for p in stale)


def test_per_file_export_failure_removes_stale_and_logs_without_logger(tmp_path, caplog):
    """#19 第 2 项：逐文件标注导出失败 → 清残留；logger=None 也要有诊断。"""
    src = _copy_study(tmp_path)
    _poison_first_entry(src / "entries.log")
    entries = readentries(f_path=str(src / "entries.log"), version="4.3.2")
    out = tmp_path / "out"
    out.mkdir()
    (out / "00000000.csv").write_text("stale\n", encoding="utf-8")

    with caplog.at_level(logging.ERROR):
        n = convert_study(str(src), "study01", str(out), _normal_cfg(), entries, logger=None)

    assert n == 2
    _assert_waveforms_written(out)
    assert not (out / "00000000.csv").exists()   # 哨兵 fid=00000000，该文件导出失败
    assert (out / "00000001.csv").exists()       # 好条目的导出不受影响
    assert any("00000000" in m for m in _errors(caplog))


def test_csv_waveform_survives_entry_export_failure(tmp_path, caplog):
    """Codex P1：csv+csv 时标注与波形同名（issue #21），失败清理绝不能删波形。"""
    src = _copy_study(tmp_path)
    _poison_first_entry(src / "entries.log")
    entries = readentries(f_path=str(src / "entries.log"), version="4.3.2")
    out = tmp_path / "out"
    out.mkdir()

    with caplog.at_level(logging.ERROR):
        n = convert_study(str(src), "study01", str(out), _normal_cfg(data_fmt="csv"),
                          entries, logger=None)

    assert n == 2
    wave = out / "00000000.csv"
    assert "(uV)" in wave.read_text(encoding="utf-8").splitlines()[0]   # 仍是波形表头
    assert any("00000000" in m for m in _errors(caplog))


def test_stale_removal_failure_does_not_abort_conversion(tmp_path, caplog, monkeypatch):
    """Codex P2：清残留本身失败（如文件被占用）也只记 ERROR，后续波形照转。"""
    src = _copy_study(tmp_path)
    entries = readentries(f_path=str(src / "entries.log"), version="4.3.2")
    out = tmp_path / "out"
    out.mkdir()
    (out / "00000000.csv").write_text("stale\n", encoding="utf-8")

    def locked(path):
        raise PermissionError(path)
    monkeypatch.setattr(os, "remove", locked)

    with caplog.at_level(logging.ERROR):
        n = convert_study(str(src), "study01", str(out), _normal_cfg(), entries, logger=None)

    assert n == 2
    _assert_waveforms_written(out)
    assert any("00000000" in m for m in _errors(caplog))


def test_gui_export_global_csv_raises_instead_of_none(tmp_path):
    """#19 第 3 项：export_global_csv 不得吞异常返回 None。"""
    pytest.importorskip("tkinter")
    import app_gui
    with pytest.raises(OSError):
        app_gui.export_global_csv([], str(tmp_path / "missing"), "study01")
