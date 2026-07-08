# tests/test_cli_extract.py
# CLI 端到端测试均驱动 realdata（本地临床数据，gitignored 不入库）；
# 缺失时可见跳过。CLI 的错误路径逻辑另由 epycon 层纯测试覆盖。
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
REAL = ROOT / "examples" / "data" / "realdata"


def _run(args):
    return subprocess.run(
        [sys.executable, "-m", "epycon.cli.extract", *args],
        capture_output=True, text=True, cwd=str(ROOT))


@pytest.mark.skipif(
    not REAL.exists(),
    reason="realdata 为本地临床数据（gitignored，不入库）；CLI 集成测试仅本地运行")
class TestCliExtract:
    def test_ok_json_stdout(self):
        r = _run(["--study", str(REAL), "--at", "1:07:15",
                  "--leads", "II,V6", "--window", "2", "--version", "4.3.2"])
        assert r.returncode == 0
        out = json.loads(r.stdout)
        assert out["log"] == "00000005"
        by = {ld["name"]: ld for ld in out["leads"]}
        assert by["II"]["status"] == "ok"
        assert by["V6"]["status"] == "rejected"

    def test_gap_error_stderr(self):
        r = _run(["--study", str(REAL), "--at", "1:07:12",
                  "--leads", "II", "--version", "4.3.2"])
        assert r.returncode == 2
        err = json.loads(r.stderr)
        assert "error" in err

    def test_out_npz(self, tmp_path):
        import numpy as np
        out_path = tmp_path / "w.npz"
        r = _run(["--study", str(REAL), "--at", "1:07:15", "--leads", "II",
                  "--window", "2", "--version", "4.3.2", "--out", str(out_path)])
        assert r.returncode == 0
        assert out_path.exists()
        data = np.load(out_path)
        assert "II" in data
        assert data["II"].shape[0] == 8000

    def test_out_unwritable_returns_structured_error(self, tmp_path):
        # 父目录不存在 → 写入失败须转结构化错误 JSON + exit 2，而非 traceback
        bad = tmp_path / "no_such_dir" / "w.npz"
        r = _run(["--study", str(REAL), "--at", "1:07:15", "--leads", "II",
                  "--window", "2", "--version", "4.3.2", "--out", str(bad)])
        assert r.returncode == 2
        assert "error" in json.loads(r.stderr)
