"""api_ecg.py 测试套件

覆盖两层：
1. 纯函数：numpy 类型转换、Min-Max 降采样、计算导联配对、HDF5 结构探测
2. Flask Blueprint 端点：open_local / metadata / data / annotations / cleanup

HDF5 fixture 用项目自己的 HDFPlanter 生成，等价于一次
"转换输出 -> ECG 查看器" 的集成验证。
"""
import base64
import io
import os

import numpy as np
import pytest
import h5py
from flask import Flask

from epycon import api_ecg
from epycon.api_ecg import (
    ecg_api,
    FILE_CACHE,
    _convert_numpy_types,
    minmax_downsample,
    _build_computed_leads,
    _get_dataset_path,
    _get_annotations_path,
    _extract_annotations,
    apply_notch_filter,
    apply_lowpass_filter,
    apply_highpass_filter,
)
from epycon.iou.planters import HDFPlanter

FS = 1000
N_SAMPLES = 2000
CH_NAMES = ["I", "II", "V1"]


# ========================= fixtures =========================

@pytest.fixture(autouse=True)
def clean_file_cache():
    """隔离测试间的全局文件缓存"""
    FILE_CACHE.clear()
    yield
    FILE_CACHE.clear()


@pytest.fixture
def client():
    app = Flask(__name__)
    app.register_blueprint(ecg_api)
    app.config["TESTING"] = True
    return app.test_client()


@pytest.fixture
def planter_h5(tmp_path):
    """用 HDFPlanter 生成的真实格式 HDF5（Data/Info/Marks）"""
    path = str(tmp_path / "study_test.h5")
    data = (np.arange(N_SAMPLES * len(CH_NAMES), dtype=np.int32)
            .reshape(N_SAMPLES, len(CH_NAMES)) % 1000)
    with HDFPlanter(
        f_path=path,
        column_names=CH_NAMES,
        sampling_freq=FS,
        factor=1000,
        units="uV",
        attributes={"SubjectID": "P001", "StudyID": "study01"},
    ) as planter:
        planter.write(data)
        planter.add_marks(
            positions=[100, 500],
            groups=["NOTE", "EVENT"],
            messages=["hello", ""],
        )
    return path


def _open_local(client, path):
    resp = client.post("/api/ecg/open_local", json={"path": path})
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


# ========================= 纯函数 =========================

class TestConvertNumpyTypes:
    def test_scalars_and_arrays(self):
        result = _convert_numpy_types({
            "i": np.int32(5),
            "f": np.float64(2.5),
            "b": np.bool_(True),
            "arr": np.array([1, 2, 3]),
            "bytes": b"abc",
            "nested": [np.int64(7), {"x": np.float32(1.5)}],
        })
        assert result["i"] == 5 and isinstance(result["i"], int)
        assert result["f"] == 2.5 and isinstance(result["f"], float)
        assert result["b"] is True
        assert result["arr"] == [1, 2, 3]
        assert result["bytes"] == "abc"
        assert result["nested"][0] == 7
        assert result["nested"][1]["x"] == 1.5

    def test_passthrough_native(self):
        assert _convert_numpy_types({"s": "x", "n": 1}) == {"s": "x", "n": 1}


class TestMinmaxDownsample:
    def test_factor_one_is_identity(self):
        data = np.arange(20, dtype=float).reshape(10, 2)
        assert minmax_downsample(data, 1) is data

    def test_shape_and_extremes_preserved(self):
        data = np.zeros((100, 2))
        data[37, 0] = 999.0   # 窗口内的尖峰必须保留
        data[61, 1] = -888.0
        out = minmax_downsample(data, 10)
        assert out.shape == (20, 2)  # 100/10 窗口 * 2 (min+max)
        assert 999.0 in out[:, 0]
        assert -888.0 in out[:, 1]

    def test_remainder_window(self):
        data = np.arange(25, dtype=float).reshape(25, 1)
        out = minmax_downsample(data, 10)
        # 2 个完整窗口 * 2 + 余数窗口的 min/max
        assert out.shape == (6, 1)
        assert out[-1, 0] == 24.0

    def test_input_smaller_than_window(self):
        data = np.arange(10, dtype=float).reshape(5, 2)
        out = minmax_downsample(data, 10)
        assert out.shape == (2, 2)
        np.testing.assert_array_equal(out[0], data.min(axis=0))
        np.testing.assert_array_equal(out[1], data.max(axis=0))


class TestBuildComputedLeads:
    def test_pairs_detected(self):
        meta = _build_computed_leads({"channel_names": ["u+HRA", "u-HRA", "ECG"]})
        assert meta["is_computed_mode"] is True
        assert meta["computed_leads"] == [
            {"name": "HRA", "plus_idx": 0, "minus_idx": 1}
        ]
        assert meta["display_channel_names"] == ["HRA", "ECG"]
        assert meta["display_num_channels"] == 2
        assert meta["other_channel_indices"] == [2]

    def test_no_pairs(self):
        meta = _build_computed_leads({"channel_names": ["I", "II"]})
        assert meta["is_computed_mode"] is False
        assert meta["display_channel_names"] == ["I", "II"]
        assert meta["other_channel_indices"] == [0, 1]

    def test_unmatched_plus_only(self):
        meta = _build_computed_leads({"channel_names": ["u+HRA", "I"]})
        assert meta["is_computed_mode"] is False

    def test_empty(self):
        meta = _build_computed_leads({"channel_names": []})
        assert meta["is_computed_mode"] is False
        assert meta["computed_leads"] == []


class TestH5Discovery:
    def test_dataset_path_common_name(self, tmp_path):
        path = tmp_path / "a.h5"
        with h5py.File(path, "w") as f:
            f.create_dataset("data", data=np.zeros((10, 2)))
        with h5py.File(path, "r") as f:
            assert _get_dataset_path(f) == "data"

    def test_dataset_path_fallback_2d_search(self, tmp_path):
        path = tmp_path / "b.h5"
        with h5py.File(path, "w") as f:
            grp = f.create_group("weird")
            grp.create_dataset("payload", data=np.zeros((10, 2)))
        with h5py.File(path, "r") as f:
            assert _get_dataset_path(f) == "weird/payload"

    def test_dataset_path_none(self, tmp_path):
        path = tmp_path / "c.h5"
        with h5py.File(path, "w") as f:
            f.create_dataset("oneD", data=np.zeros(10))
        with h5py.File(path, "r") as f:
            assert _get_dataset_path(f) is None

    def test_annotations_path_marks(self, planter_h5):
        with h5py.File(planter_h5, "r") as f:
            assert _get_annotations_path(f) == "Marks"

    def test_extract_annotations_from_marks(self, planter_h5):
        with h5py.File(planter_h5, "r") as f:
            annots = _extract_annotations(f, "Marks")
        assert len(annots) == 2
        first, second = annots
        assert first["sample"] == 100
        assert first["label"] == "hello"      # Info 非空时优先
        assert second["sample"] == 500
        assert second["label"] == "EVENT"     # Info 为空时回落到 Group


class TestFiltersWithoutScipy:
    """SCIPY_AVAILABLE=False 时所有滤波必须原样直通"""

    def test_notch_passthrough(self, monkeypatch):
        monkeypatch.setattr(api_ecg, "SCIPY_AVAILABLE", False)
        data = np.random.default_rng(0).normal(size=(100, 2))
        out, applied = apply_notch_filter(data, FS)
        assert applied is False
        np.testing.assert_array_equal(out, data)

    def test_lowpass_highpass_passthrough(self, monkeypatch):
        monkeypatch.setattr(api_ecg, "SCIPY_AVAILABLE", False)
        data = np.random.default_rng(1).normal(size=(100, 2))
        np.testing.assert_array_equal(apply_lowpass_filter(data, FS), data)
        np.testing.assert_array_equal(apply_highpass_filter(data, FS), data)


class TestFiltersWithScipy:
    """需要 scipy；未安装时自动跳过"""

    def test_notch_attenuates_50hz(self):
        pytest.importorskip("scipy")
        t = np.arange(FS * 2) / FS
        sine50 = np.sin(2 * np.pi * 50 * t).reshape(-1, 1)
        out, applied = apply_notch_filter(sine50.copy(), FS, freq=50.0)
        assert applied is True
        assert np.std(out) < 0.3 * np.std(sine50)

    def test_lowpass_attenuates_high_freq(self):
        pytest.importorskip("scipy")
        t = np.arange(FS * 2) / FS
        sine200 = np.sin(2 * np.pi * 200 * t).reshape(-1, 1)
        out = apply_lowpass_filter(sine200.copy(), FS, cutoff=20.0)
        assert np.std(out) < 0.5 * np.std(sine200)


# ========================= API 端点 =========================

class TestCheckEndpoint:
    def test_check(self, client):
        resp = client.get("/api/ecg/check")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["available"] is True
        assert body["h5py_available"] is True


class TestOpenLocal:
    def test_missing_path_field(self, client):
        resp = client.post("/api/ecg/open_local", json={})
        assert resp.status_code == 400

    def test_nonexistent_file(self, client, tmp_path):
        resp = client.post(
            "/api/ecg/open_local", json={"path": str(tmp_path / "nope.h5")}
        )
        assert resp.status_code == 404

    def test_unsupported_extension(self, client, tmp_path):
        bad = tmp_path / "data.txt"
        bad.write_text("not ecg")
        resp = client.post("/api/ecg/open_local", json={"path": str(bad)})
        assert resp.status_code == 400

    def test_open_planter_file(self, client, planter_h5):
        body = _open_local(client, planter_h5)
        assert body["source"] == "local_disk"
        assert body["num_annotations"] == 2
        meta = body["metadata"]
        assert meta["num_channels"] == len(CH_NAMES)
        assert meta["num_samples"] == N_SAMPLES
        assert meta["channel_names"] == CH_NAMES
        assert meta["sampling_freq"] == FS
        assert meta["patient_id"] == "P001"
        assert meta["study_id"] == "study01"

    def test_open_npy_file(self, client, tmp_path):
        npy_path = tmp_path / "sig.npy"
        np.save(npy_path, np.zeros((500, 2), dtype=np.float32))
        body = _open_local(client, str(npy_path))
        assert body["metadata"]["num_channels"] == 2
        assert body["metadata"]["num_samples"] == 500


class TestMetadataEndpoint:
    def test_unknown_id(self, client):
        assert client.get("/api/ecg/metadata/zzz").status_code == 404

    def test_known_id(self, client, planter_h5):
        file_id = _open_local(client, planter_h5)["file_id"]
        resp = client.get(f"/api/ecg/metadata/{file_id}")
        assert resp.status_code == 200
        assert resp.get_json()["metadata"]["num_samples"] == N_SAMPLES


class TestDataEndpoint:
    def test_unknown_id(self, client):
        assert client.get("/api/ecg/data/zzz").status_code == 404

    def test_full_range(self, client, planter_h5):
        file_id = _open_local(client, planter_h5)["file_id"]
        resp = client.get(f"/api/ecg/data/{file_id}?start=0&end=10")
        assert resp.status_code == 200, resp.get_json()
        body = resp.get_json()
        assert body["num_samples"] == N_SAMPLES
        assert len(body["data"]) == N_SAMPLES
        assert len(body["data"][0]) == len(CH_NAMES)
        assert body["channel_names"] == CH_NAMES
        # time 数组不再下发（前端按 start_sec/downsample/fs 重建）
        assert "time" not in body
        assert body["start_sec"] == 0 and body["downsample"] == 1

    def test_channel_subset(self, client, planter_h5):
        file_id = _open_local(client, planter_h5)["file_id"]
        resp = client.get(f"/api/ecg/data/{file_id}?start=0&end=10&channels=0,2")
        body = resp.get_json()
        assert resp.status_code == 200, body
        assert body["channel_names"] == ["I", "V1"]
        assert len(body["data"][0]) == 2

    def test_downsample(self, client, planter_h5):
        file_id = _open_local(client, planter_h5)["file_id"]
        resp = client.get(f"/api/ecg/data/{file_id}?start=0&end=10&downsample=4")
        body = resp.get_json()
        assert resp.status_code == 200, body
        # Min-Max 降采样: 每 factor 窗口保留 min+max 两点
        assert body["num_samples"] == (N_SAMPLES // 4) * 2

    def test_time_window(self, client, planter_h5):
        file_id = _open_local(client, planter_h5)["file_id"]
        resp = client.get(f"/api/ecg/data/{file_id}?start=0&end=1")
        body = resp.get_json()
        assert resp.status_code == 200, body
        assert body["num_samples"] == FS  # 1 秒 * 1000Hz


class TestAnnotationsEndpoint:
    def test_all(self, client, planter_h5):
        file_id = _open_local(client, planter_h5)["file_id"]
        resp = client.get(f"/api/ecg/annotations/{file_id}")
        body = resp.get_json()
        assert resp.status_code == 200
        assert body["total"] == 2
        samples = [a["sample"] for a in body["annotations"]]
        assert samples == [100, 500]
        assert body["annotations"][0]["time_sec"] == pytest.approx(0.1)

    def test_time_filter(self, client, planter_h5):
        file_id = _open_local(client, planter_h5)["file_id"]
        resp = client.get(f"/api/ecg/annotations/{file_id}?start=0.3")
        body = resp.get_json()
        assert body["total"] == 1
        assert body["annotations"][0]["sample"] == 500


class TestCleanup:
    def test_cleanup_local_keeps_file_on_disk(self, client, planter_h5):
        file_id = _open_local(client, planter_h5)["file_id"]
        resp = client.delete(f"/api/ecg/cleanup/{file_id}")
        assert resp.status_code == 200
        assert os.path.exists(planter_h5)  # is_local 文件不得物理删除
        assert client.get(f"/api/ecg/metadata/{file_id}").status_code == 404

    def test_cleanup_unknown_id_is_ok(self, client):
        assert client.delete("/api/ecg/cleanup/zzz").status_code == 200

    def test_cleanup_all_clears_cache(self, client, planter_h5):
        _open_local(client, planter_h5)
        resp = client.delete("/api/ecg/cleanup-all")
        assert resp.status_code == 200
        assert len(FILE_CACHE) == 0

    def test_cleanup_all_keeps_local_files_on_disk(self, client, planter_h5):
        _open_local(client, planter_h5)
        client.delete("/api/ecg/cleanup-all")
        assert os.path.exists(planter_h5)  # 用户原始数据不得被删除


# ========================= 计算导联模式 =========================

@pytest.fixture
def computed_h5(tmp_path):
    """带 u+/u- 电极对的裸 HDF5（dataset attrs 提供通道名）"""
    path = str(tmp_path / "computed.h5")
    n = 1000
    t = np.arange(n, dtype=np.float32)
    data = np.stack([2 * t, t, np.ones(n, dtype=np.float32)], axis=1)
    with h5py.File(path, "w") as f:
        ds = f.create_dataset("data", data=data)
        ds.attrs["channel_names"] = "u+HRA,u-HRA,ECG"
        ds.attrs["sampling_freq"] = float(FS)
    return path


class TestComputedLeadMode:
    def test_metadata_detects_pairs(self, client, computed_h5):
        meta = _open_local(client, computed_h5)["metadata"]
        assert meta["is_computed_mode"] is True
        assert meta["display_channel_names"] == ["HRA", "ECG"]

    def test_data_returns_difference(self, client, computed_h5):
        file_id = _open_local(client, computed_h5)["file_id"]
        resp = client.get(f"/api/ecg/data/{file_id}?start=0&end=1")
        body = resp.get_json()
        assert resp.status_code == 200, body
        assert body["channel_names"] == ["HRA", "ECG"]
        # HRA = u+HRA - u-HRA = 2t - t = t
        assert body["data"][5][0] == pytest.approx(5.0)
        assert body["data"][5][1] == pytest.approx(1.0)  # ECG 原样直通


# ========================= 滤波端点参数 =========================

class TestDataFilterParams:
    """需要 scipy（已在 requirements 中）"""

    @pytest.fixture
    def baseline(self, client, planter_h5):
        pytest.importorskip("scipy")
        file_id = _open_local(client, planter_h5)["file_id"]
        resp = client.get(f"/api/ecg/data/{file_id}?start=0&end=1")
        return file_id, resp.get_json()["data"]

    def test_global_filters_change_data(self, client, baseline):
        file_id, raw = baseline
        resp = client.get(
            f"/api/ecg/data/{file_id}?start=0&end=1&notch=50&lp=40&hp=0.5"
        )
        body = resp.get_json()
        assert resp.status_code == 200, body
        assert body["data"] != raw

    def test_notch_alone_actually_filters(self, client, baseline):
        """回归：notch 单独生效（曾因 enhanced_notch 未定义在 h5 分支静默失效）"""
        file_id, raw = baseline
        resp = client.get(f"/api/ecg/data/{file_id}?start=0&end=1&notch=50")
        body = resp.get_json()
        assert resp.status_code == 200, body
        assert body["data"] != raw

    def test_enhanced_notch_param_accepted(self, client, baseline):
        file_id, raw = baseline
        resp = client.get(
            f"/api/ecg/data/{file_id}?start=0&end=1&notch=50&enhanced_notch=true"
        )
        assert resp.status_code == 200
        assert resp.get_json()["data"] != raw

    def test_causal_method(self, client, baseline):
        file_id, raw = baseline
        resp = client.get(
            f"/api/ecg/data/{file_id}"
            f"?start=0&end=1&notch=50&lp=40&hp=0.5&filter_method=causal"
        )
        assert resp.status_code == 200
        assert resp.get_json()["data"] != raw

    def test_channel_filters_only_affect_target_channel(self, client, baseline):
        file_id, raw = baseline
        resp = client.get(
            f"/api/ecg/data/{file_id}",
            query_string={
                "start": 0, "end": 1,
                "channel_filters": '{"0": {"lp": "40", "hp": "1"}}',
            },
        )
        body = resp.get_json()
        assert resp.status_code == 200, body

        def col(rows, idx):
            return [r[idx] for r in rows]

        assert col(body["data"], 0) != col(raw, 0)  # 通道 0 被滤波
        assert col(body["data"], 1) == col(raw, 1)  # 通道 1 不受影响


# ========================= NumPy 文件路径 =========================

class TestNumpyFiles:
    def test_npz_roundtrip(self, client, tmp_path):
        path = tmp_path / "sig.npz"
        np.savez(path, arr=np.random.default_rng(2).normal(size=(500, 2)))
        file_id = _open_local(client, str(path))["file_id"]
        resp = client.get(f"/api/ecg/data/{file_id}?start=0&end=10&notch=50")
        body = resp.get_json()
        assert resp.status_code == 200, body
        assert body["num_samples"] == 500

    def test_npy_1d(self, client, tmp_path):
        path = tmp_path / "sig1d.npy"
        np.save(path, np.zeros(300, dtype=np.float32))
        body = _open_local(client, str(path))
        assert body["metadata"]["num_channels"] == 1
        file_id = body["file_id"]
        resp = client.get(f"/api/ecg/data/{file_id}?start=0&end=10")
        assert resp.status_code == 200
        assert resp.get_json()["num_samples"] == 300


# ========================= browse（mock GUI 子进程） =========================

class TestBrowseEndpoint:
    class _FakeResult:
        def __init__(self, returncode, stdout="", stderr=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def test_file_selected(self, client, monkeypatch):
        import subprocess
        monkeypatch.setattr(
            subprocess, "run",
            lambda *a, **k: self._FakeResult(0, stdout="C:/data/x.h5\n"),
        )
        resp = client.get("/api/ecg/browse")
        assert resp.get_json()["path"] == "C:/data/x.h5"

    def test_cancelled(self, client, monkeypatch):
        import subprocess
        monkeypatch.setattr(
            subprocess, "run", lambda *a, **k: self._FakeResult(0, stdout="")
        )
        assert client.get("/api/ecg/browse").get_json()["path"] is None

    def test_dialog_process_failed(self, client, monkeypatch):
        import subprocess
        monkeypatch.setattr(
            subprocess, "run",
            lambda *a, **k: self._FakeResult(1, stderr="boom"),
        )
        body = client.get("/api/ecg/browse").get_json()
        assert body["path"] is None
        assert "error" in body


# ========================= 图片导出 =========================

class TestExportImage:
    def test_export_download_roundtrip(self, client):
        png_bytes = b"\x89PNG-fake-bytes"
        payload = base64.b64encode(png_bytes).decode()
        resp = client.post(
            "/api/ecg/export_image",
            json={
                "image_data": f"data:image/png;base64,{payload}",
                "filename": "wave.png",
            },
        )
        assert resp.status_code == 200, resp.get_json()
        url = resp.get_json()["download_url"]

        download = client.get(url)
        assert download.status_code == 200
        assert download.data == png_bytes
        assert "attachment" in download.headers["Content-Disposition"]
        assert "wave.png" in download.headers["Content-Disposition"]
        download.close()

    def test_download_unknown_id(self, client):
        assert client.get("/api/ecg/download_image/nonexistent").status_code == 404


# ========================= 备选元数据来源 =========================

class TestAlternateMetadataSources:
    def test_channel_names_from_channelsettings(self, tmp_path):
        from epycon.api_ecg import _extract_metadata
        path = tmp_path / "cs.h5"
        cs_dtype = np.dtype([("Channel", "S256"), ("Visible", "<f4")])
        rows = np.array([(b"X1", 1.0), (b"X2", 1.0)], dtype=cs_dtype)
        with h5py.File(path, "w") as f:
            f.create_dataset("data", data=np.zeros((100, 2)))
            f.create_dataset("ChannelSettings", data=rows)
        with h5py.File(path, "r") as f:
            meta = _extract_metadata(f, "data")
        assert meta["channel_names"] == ["X1", "X2"]

    def test_extract_annotations_group_format(self, tmp_path):
        path = tmp_path / "grp.h5"
        with h5py.File(path, "w") as f:
            f.create_dataset("data", data=np.zeros((100, 2)))
            grp = f.create_group("annotations")
            grp.create_dataset("samples", data=[10, 20])
            grp.create_dataset("labels", data=[b"A", b"B"])
            grp.create_dataset("message", data=[b"m1", b"m2"])
        with h5py.File(path, "r") as f:
            annots = _extract_annotations(f, "annotations")
        assert [a["sample"] for a in annots] == [10, 20]
        assert [a["label"] for a in annots] == ["A", "B"]
        assert annots[0]["message"] == "m1"


# ========================= scipy 滤波器补充 =========================

class TestMoreScipyFilters:
    def test_highpass_removes_dc_offset(self):
        pytest.importorskip("scipy")
        t = np.arange(FS * 2) / FS
        sig = (5.0 + np.sin(2 * np.pi * 30 * t)).reshape(-1, 1)
        out = apply_highpass_filter(sig.copy(), FS, cutoff=0.5)
        assert abs(np.mean(out)) < 0.5  # 直流分量被去除

    def test_causal_filters_preserve_shape(self):
        pytest.importorskip("scipy")
        data = np.random.default_rng(3).normal(size=(500, 2))
        out, applied = apply_notch_filter(data.copy(), FS, method="causal")
        assert applied is True and out.shape == data.shape
        out = apply_lowpass_filter(data.copy(), FS, cutoff=40, method="causal")
        assert out.shape == data.shape
        out = apply_highpass_filter(data.copy(), FS, cutoff=0.5, method="causal")
        assert out.shape == data.shape


class TestUploadEndpoint:
    def test_upload_no_file(self, client):
        resp = client.post("/api/ecg/upload", data={})
        assert resp.status_code == 400

    def test_upload_bad_extension(self, client):
        resp = client.post(
            "/api/ecg/upload",
            data={"file": (io.BytesIO(b"junk"), "data.txt")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400

    def test_upload_traversal_filename_stays_in_temp_dir(self, client, planter_h5):
        """恶意文件名不得把保存路径带出 TEMP_DIR"""
        from epycon.api_ecg import TEMP_DIR
        with open(planter_h5, "rb") as f:
            resp = client.post(
                "/api/ecg/upload",
                data={"file": (f, "..\\..\\evil.h5")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 200, resp.get_json()
        file_id = resp.get_json()["file_id"]
        saved_path = os.path.realpath(FILE_CACHE[file_id]["path"])
        assert saved_path.startswith(os.path.realpath(TEMP_DIR) + os.sep)
        client.delete(f"/api/ecg/cleanup/{file_id}")

    def test_upload_unicode_filename(self, client, planter_h5):
        """中文文件名必须被接受"""
        with open(planter_h5, "rb") as f:
            resp = client.post(
                "/api/ecg/upload",
                data={"file": (f, "心电数据.h5")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 200, resp.get_json()
        file_id = resp.get_json()["file_id"]
        client.delete(f"/api/ecg/cleanup/{file_id}")

    def test_upload_h5_roundtrip(self, client, planter_h5):
        with open(planter_h5, "rb") as f:
            resp = client.post(
                "/api/ecg/upload",
                data={"file": (f, "uploaded.h5")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 200, resp.get_json()
        body = resp.get_json()
        file_id = body["file_id"]
        assert body["metadata"]["num_samples"] == N_SAMPLES
        # 上传产生的临时副本，cleanup 时应被物理删除
        temp_path = FILE_CACHE[file_id]["path"]
        assert os.path.exists(temp_path)
        client.delete(f"/api/ecg/cleanup/{file_id}")
        assert not os.path.exists(temp_path)


# ========================= 单位契约 / extraction npz 往返 =========================

class TestUnitsContract:
    """读取侧必须采信文件声明，冲突/无声明返回 unknown（KNOWN_ISSUES #26）。"""

    def _h5(self, tmp_path, name, *, info=None, root=None, gen=None, contract=None):
        p = str(tmp_path / f"{name}.h5")
        with h5py.File(p, "w") as f:
            f.create_dataset("Data", data=np.zeros((2, 10), dtype=np.float32))
            if root:
                f.attrs["units"] = root
            if gen:
                f.attrs["GeneratedBy"] = gen
            if contract is not None:
                f.attrs["EpyconUnitsContract"] = contract
            if info:
                dt = np.dtype([("ChannelName", "S8"), ("DatacacheName", "S8"), ("Units", "S8")])
                f.create_dataset("Info", data=np.array(
                    [(n.encode(), b"RAW", u.encode()) for n, u in info], dtype=dt))
        return p

    def _units(self, path):
        with h5py.File(path, "r") as f:
            return api_ecg._extract_metadata(f, "Data")["units"]

    def test_planter_output_declares_uv(self, planter_h5):
        """真实 HDFPlanter 产物：Info 声明 uV 且带契约标记 -> 采信 uV。"""
        assert self._units(planter_h5) == "uV"

    def test_legacy_epycon_mv_resolved_as_uv(self, tmp_path):
        """#19 前的旧文件：Info 标 mV、无契约标记、实为 µV。"""
        p = self._h5(tmp_path, "legacy", info=[("I", "mV")], gen="Epycon")
        assert self._units(p) == "uV"

    def test_contract_marked_mv_is_honored(self, tmp_path):
        """带契约标记就以声明为准——legacy 规则不得越界误判合法 mV 文件。"""
        p = self._h5(tmp_path, "real_mv", info=[("I", "mV")], gen="Epycon", contract=1)
        assert self._units(p) == "mV"

    def test_third_party_root_attr_is_read(self, tmp_path):
        """root attr 声明此前被完全无视（#26）。"""
        p = self._h5(tmp_path, "root_mv", root="mV", gen="Other")
        assert self._units(p) == "mV"

    def test_conflicting_declarations_return_unknown(self, tmp_path):
        p = self._h5(tmp_path, "conflict", root="mV", info=[("I", "uV")])
        assert self._units(p) == "unknown"

    def test_no_declaration_returns_unknown(self, tmp_path):
        p = self._h5(tmp_path, "bare")
        assert self._units(p) == "unknown"

    def test_mixed_units_preserved_per_channel(self, tmp_path, client):
        """混合单位文件：标量 unknown，但逐通道声明已知，导出不得一律写未知。"""
        path = self._h5(tmp_path, "mixed", info=[("I", "uV"), ("II", "mV")])
        with h5py.File(path, "r") as f:
            md = api_ecg._extract_metadata(f, "Data")
        assert md["units"] == "unknown"          # 标量表达不了混合
        assert md["channel_units"] == ["uV", "mV"]   # 但逐通道保留

        cols = api_ecg._output_units(md, ["I", "II"], [0, 1], False)
        assert cols == ["uV", "mV"]              # 逐列对齐，不丢信息

    def test_homogeneous_units_fill_all_columns(self, tmp_path):
        path = self._h5(tmp_path, "homo", info=[("I", "uV"), ("II", "uV")],
                        gen="Epycon", contract=1)
        with h5py.File(path, "r") as f:
            md = api_ecg._extract_metadata(f, "Data")
        assert api_ecg._output_units(md, ["I", "II"], [0, 1], False) == ["uV", "uV"]

    def test_units_attr_lookup_is_case_insensitive(self, tmp_path):
        """后端大小写无关；前端 h5wasm 亦然，否则同一文件按读取路径漂移。"""
        p = str(tmp_path / "upper.h5")
        with h5py.File(p, "w") as f:
            f.create_dataset("Data", data=np.zeros((2, 10), dtype=np.float32))
            f.attrs["UNITS"] = "mV"
        assert self._units(p) == "mV"

class TestExtractionNpzRoundtrip:
    """extraction 的 .npz 必须能真正进入 WebUI（KNOWN_ISSUES #28）。

    夹具用 _save_npz 的**真实产物**，不手搓 npz——此前 API 无条件取首个成员，
    而 _meta 恰是首成员，导致 JSON 字符串被当波形、通道数为 0。
    """

    def _result(self, units="uV"):
        return {
            "study": "s", "log": "00000000", "version": "4.3.2", "fs": 2000,
            "units": units, "resolution_nV": 78,
            "target": {"elapsed": "2.658", "epoch": 1.0, "offset_in_seg_s": 2.658},
            "requested_window": {"before": 1, "after": 1},
            "returned_window": {"start_s": 1.6, "end_s": 3.6,
                                "clipped": False, "missing_s": 0},
            "leads": [
                {"name": "II", "status": "ok", "n": 4, "samples": [1.0, 2.0, 3.0, 4.0]},
                {"name": "V1", "status": "ok", "n": 4, "samples": [5.0, 6.0, 7.0, 8.0]},
                {"name": "V6", "status": "railed", "reason": "通道恒定于满量程，电极未连接"},
            ],
        }

    @pytest.fixture
    def extraction_npz(self, tmp_path):
        from epycon.cli.extract import _save_npz
        _, actual = _save_npz(str(tmp_path / "extracted"), self._result())
        return actual

    def test_meta_is_not_mistaken_for_waveform(self, extraction_npz):
        data, info = api_ecg.load_npz(np.load(extraction_npz))
        assert data.shape == (4, 2)          # 修复前：_meta 的 0 维字符串
        assert info["channel_names"] == ["II", "V1"]

    def test_declared_units_and_fs_adopted(self, extraction_npz):
        data, info = api_ecg.load_npz(np.load(extraction_npz))
        md = api_ecg._extract_npy_metadata(data, "extracted.npz", info)
        assert md["units"] == "uV"           # 修复前：硬编码 mV，丢弃显式声明
        assert md["sampling_freq"] == 2000   # 修复前：默认 250
        assert md["num_channels"] == 2       # 修复前：0
        assert md["channel_names"] == ["II", "V1"]

    def test_raw_counts_units_preserved(self, tmp_path):
        """raw_counts 模式声明 counts——不可物理定标，不得被当成电压。"""
        from epycon.cli.extract import _save_npz
        _, actual = _save_npz(str(tmp_path / "counts"), self._result(units="counts"))
        data, info = api_ecg.load_npz(np.load(actual))
        md = api_ecg._extract_npy_metadata(data, "counts.npz", info)
        assert md["units"] == "counts"

    def test_bare_npz_without_meta_keeps_legacy_behavior(self, tmp_path):
        """无 _meta 的普通 npz 保持既有语义（取第一个数组），单位 unknown。"""
        p = str(tmp_path / "bare.npz")
        np.savez(p, arr=np.zeros((10, 2), dtype=np.float32))
        data, info = api_ecg.load_npz(np.load(p))
        assert data.shape == (10, 2)
        assert info is None
        md = api_ecg._extract_npy_metadata(data, "bare.npz", info)
        assert md["units"] == "unknown"

    def test_open_local_endpoint_accepts_extraction_npz(self, client, extraction_npz):
        """端到端：真实 extraction 产物经 open_local 进入查看器。"""
        resp = client.post("/api/ecg/open_local", json={"path": extraction_npz})
        assert resp.status_code == 200, resp.get_json()
        md = resp.get_json()["metadata"]
        assert md["num_channels"] == 2
        assert md["units"] == "uV"
        assert md["channel_names"] == ["II", "V1"]


    def test_data_endpoint_returns_waveform_and_units(self, client, extraction_npz):
        """波形端点必须与元数据入口走同一条 load_npz。

        此前 open/upload 已改用 load_npz，但 /data 仍取 keys()[0] —— 于是元数据
        入口返回 200、波形端点却拿到 _meta 的 JSON 字符串并在切片时 500。
        """
        resp = client.post("/api/ecg/open_local", json={"path": extraction_npz})
        assert resp.status_code == 200, resp.get_json()
        file_id = resp.get_json()["file_id"]

        resp = client.get(f"/api/ecg/data/{file_id}?start=0&end=1")
        assert resp.status_code == 200, resp.get_json()
        body = resp.get_json()
        assert body["channel_names"] == ["II", "V1"]
        assert body["num_samples"] > 0
        # 数值与单位声明必须同源地送到前端，否则导出只能写"单位未知"
        assert body["units"] == "uV"
        assert body["data"][0] == pytest.approx([1.0, 5.0])

    def test_data_endpoint_carries_units_for_h5(self, client, planter_h5):
        """后端路径的 /data 也须带 units（#27 入口 B 的前端导出依赖它）。"""
        file_id = _open_local(client, planter_h5)["file_id"]
        resp = client.get(f"/api/ecg/data/{file_id}?start=0&end=1")
        assert resp.status_code == 200, resp.get_json()
        assert resp.get_json()["units"] == "uV"

    def test_upload_endpoint_accepts_extraction_npz(self, client, extraction_npz):
        with open(extraction_npz, "rb") as f:
            resp = client.post(
                "/api/ecg/upload",
                data={"file": (f, "extracted.npz")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 200, resp.get_json()
        md = resp.get_json()["metadata"]
        assert md["num_channels"] == 2
        assert md["units"] == "uV"
