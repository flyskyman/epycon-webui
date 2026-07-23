"""/api/workmate/scan 测试套件

覆盖两层：
1. 纯函数 _scan_workmate_root：递归发现、隐藏/系统目录剪枝、深度/大小/数量上限
2. Flask 端点：root 校验（缺失/相对路径/不存在/盘符根）、prefs 回落、b64 往返

entries.log/MASTER fixture 用 struct 按 x64 版式合成（head 36 + N*220，
姓名 0x02/64B、ID 0x43/16B），与前端 JS 解析器约定一致。
"""
import base64
import os
import struct

import pytest

from app_gui import app, _scan_workmate_root

HEAD64 = 36
LINE64 = 220


def make_entries_log(rows):
    """按 x64 版式合成 entries.log。rows: [(gid, ts_ms, text), ...]"""
    buf = bytearray(HEAD64)
    for gid, ts, text in rows:
        line = bytearray(LINE64)
        struct.pack_into('<H', line, 0, gid)
        struct.pack_into('<Q', line, 10, ts)
        raw = text.encode('latin-1')[:175]
        line[18:18 + len(raw)] = raw
        buf += line
    return bytes(buf)


def make_master(name, pid):
    buf = bytearray(512)
    raw_name = name.encode('latin-1')[:63]
    buf[0x02:0x02 + len(raw_name)] = raw_name
    raw_pid = pid.encode('latin-1')[:15]
    buf[0x43:0x43 + len(raw_pid)] = raw_pid
    return bytes(buf)


@pytest.fixture
def data_root(tmp_path):
    """两个有效 study + 各类干扰项的目录树"""
    ts0 = 1747000000000  # 2025-05 前后的毫秒时间戳
    full = tmp_path / "PAT001" / "2026-05-12"
    full.mkdir(parents=True)
    (full / "entries.log").write_bytes(make_entries_log([
        (3, ts0, "Baseline note"),
        (2, ts0 + 5000, "AF induced"),
    ]))
    (full / "MASTER").write_bytes(make_master("DOE^JOHN", "P001"))

    bare = tmp_path / "PAT002"
    bare.mkdir()
    (bare / "entries.log").write_bytes(make_entries_log([(6, ts0, "Pace 600ms")]))

    # 干扰项：隐藏目录、系统目录、无关文件——都不得被读取
    hidden = tmp_path / ".hidden"
    hidden.mkdir()
    (hidden / "entries.log").write_bytes(make_entries_log([(3, ts0, "ghost")]))
    pycache = tmp_path / "__pycache__"
    pycache.mkdir()
    (pycache / "entries.log").write_bytes(b"junk")
    (tmp_path / ".DS_Store").write_bytes(b"\x00" * 16)
    (tmp_path / "noise.txt").write_text("not a log")
    return tmp_path


@pytest.fixture
def client():
    app.config["TESTING"] = True
    return app.test_client()


# ========================= 纯函数 =========================

class TestScanRoot:
    def test_discovers_nested_studies(self, data_root):
        res = _scan_workmate_root(str(data_root))
        rels = sorted(s["rel_path"] for s in res["studies"])
        assert rels == ["PAT001/2026-05-12", "PAT002"]
        assert res["truncated"] is False

    def test_hidden_and_system_dirs_pruned(self, data_root):
        res = _scan_workmate_root(str(data_root))
        for s in res["studies"]:
            assert ".hidden" not in s["rel_path"]
            assert "__pycache__" not in s["rel_path"]

    def test_b64_bytes_roundtrip(self, data_root):
        res = _scan_workmate_root(str(data_root))
        s = next(x for x in res["studies"] if x["rel_path"] == "PAT001/2026-05-12")
        raw = base64.b64decode(s["entries"]["b64"])
        assert raw == (data_root / "PAT001" / "2026-05-12" / "entries.log").read_bytes()
        assert s["entries"]["size"] == len(raw)
        master = base64.b64decode(s["master"]["b64"])
        assert master[0x02:0x02 + 8] == b"DOE^JOHN"

    def test_missing_master_is_null(self, data_root):
        s = next(x for x in _scan_workmate_root(str(data_root))["studies"]
                 if x["rel_path"] == "PAT002")
        assert s["master"] is None

    def test_case_insensitive_filenames(self, tmp_path):
        d = tmp_path / "s1"
        d.mkdir()
        (d / "ENTRIES.LOG").write_bytes(make_entries_log([(3, 1, "x")]))
        res = _scan_workmate_root(str(tmp_path))
        assert len(res["studies"]) == 1

    def test_oversized_entries_skipped(self, tmp_path):
        d = tmp_path / "big"
        d.mkdir()
        (d / "entries.log").write_bytes(b"\x00" * (2 * 1024 * 1024))
        res = _scan_workmate_root(str(tmp_path), max_file_mb=1)
        assert res["studies"] == []
        assert any(k["reason"] == "too_large" for k in res["skipped"])

    def test_depth_limit_pruned(self, tmp_path):
        deep = tmp_path / "a" / "b" / "c"
        deep.mkdir(parents=True)
        (deep / "entries.log").write_bytes(make_entries_log([(3, 1, "deep")]))
        res = _scan_workmate_root(str(tmp_path), max_depth=2)
        assert res["studies"] == []
        assert any(k["reason"] == "depth_limit" for k in res["skipped"])

    def test_max_studies_truncates(self, data_root):
        res = _scan_workmate_root(str(data_root), max_studies=1)
        assert len(res["studies"]) <= 1
        assert res["truncated"] is True

    def test_paths_use_forward_slashes(self, data_root):
        res = _scan_workmate_root(str(data_root))
        assert "\\" not in res["root"]
        for s in res["studies"]:
            assert "\\" not in s["abs_path"] and "\\" not in s["rel_path"]


# ========================= API 端点 =========================

class TestScanEndpoint:
    def test_missing_root_no_prefs(self, client, monkeypatch, tmp_path):
        import app_gui
        monkeypatch.setattr(app_gui, "PREFS_FILE", str(tmp_path / "no_prefs.json"))
        resp = client.post("/api/workmate/scan", json={})
        assert resp.status_code == 400

    def test_relative_root_rejected(self, client):
        resp = client.post("/api/workmate/scan", json={"root": "examples/data"})
        assert resp.status_code == 400

    def test_nonexistent_root_rejected(self, client, tmp_path):
        resp = client.post("/api/workmate/scan",
                           json={"root": str(tmp_path / "nope")})
        assert resp.status_code == 400

    def test_filesystem_root_rejected(self, client):
        fs_root = os.path.abspath(os.sep)
        resp = client.post("/api/workmate/scan", json={"root": fs_root})
        assert resp.status_code == 400
        assert "根目录" in resp.get_json()["message"]

    def test_scan_ok(self, client, data_root):
        resp = client.post("/api/workmate/scan", json={"root": str(data_root)})
        assert resp.status_code == 200, resp.get_json()
        body = resp.get_json()
        assert body["status"] == "ok"
        assert len(body["studies"]) == 2
        assert "elapsed_ms" in body

    def test_prefs_fallback(self, client, monkeypatch, tmp_path, data_root):
        import json as _json
        import app_gui
        prefs = tmp_path / "prefs.json"
        prefs.write_text(_json.dumps({"workmate_scan_root": str(data_root)}),
                         encoding="utf-8")
        monkeypatch.setattr(app_gui, "PREFS_FILE", str(prefs))
        resp = client.post("/api/workmate/scan", json={})
        assert resp.status_code == 200, resp.get_json()
        assert len(resp.get_json()["studies"]) == 2
