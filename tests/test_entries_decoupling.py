"""波形与 entries 解耦（GitHub issue #11）。

单个坏 entry（未初始化哨兵时间戳 2^64/1000 s）曾让 `_tocsv` 的
`datetime.fromtimestamp` 抛 ValueError，CLI 在 convert_study 之前崩溃，
输出目录 0 字节。波形转换不依赖 entries，不得被连坐。
"""
import logging
import os
import shutil
import sys
from pathlib import Path
from unittest.mock import patch

from epycon.__main__ import main as entry_point
from epycon.config.byteschema import WMx64EntriesSchema

ROOT = Path(__file__).parent.parent
STUDY = ROOT / "examples" / "data" / "study01"


def _poison_first_entry_timestamp(entries_log):
    """把首条 entry 的 8 字节 ms 时间戳置为 0xFF..FF（realdata 实测的哨兵值）。"""
    raw = bytearray(entries_log.read_bytes())
    start = WMx64EntriesSchema.header[1] + WMx64EntriesSchema.timestamp[0]
    end = WMx64EntriesSchema.header[1] + WMx64EntriesSchema.timestamp[1]
    raw[start:end] = b"\xff" * (end - start)
    entries_log.write_bytes(bytes(raw))


def test_bad_entry_does_not_block_waveform(tmp_path, caplog):
    src = tmp_path / "in" / "study01"
    shutil.copytree(STUDY, src)
    _poison_first_entry_timestamp(src / "entries.log")
    out = tmp_path / "out"
    study_out = out / "study01"
    study_out.mkdir(parents=True)
    # 上次运行残留的汇总不得在本次失败后幸存（Codex review P2）
    (study_out / "entries_summary.csv").write_text("stale\n", encoding="utf-8")

    env = {
        "EPYCON_CONFIG": str(ROOT / "epycon" / "config" / "config.json"),
        "EPYCON_JSONSCHEMA": str(ROOT / "epycon" / "config" / "schema.json"),
    }
    argv = ["epycon", "-i", str(src.parent), "-o", str(out),
            "-fmt", "h5", "-e", "True", "-efmt", "csv"]
    with patch.dict(os.environ, env), patch.object(sys, "argv", argv), \
            caplog.at_level(logging.ERROR):
        entry_point()

    for fid in ("00000000", "00000001"):
        assert (study_out / f"{fid}.h5").stat().st_size > 0
    # 汇总标注确实失败了：不产出文件，且以 ERROR 显式暴露，不静默
    assert not (study_out / "entries_summary.csv").exists()
    assert any("entries_summary" in r.message and r.levelno >= logging.ERROR
               for r in caplog.records)
