import numpy as np
import pytest
import h5py

from epycon.iou.planters import CSVPlanter, HDFPlanter


def test_csvplanter_write(tmp_path):
    p = tmp_path / "out.csv"
    data = np.array([[1, 2], [3, 4]])

    with CSVPlanter(str(p), column_names=["a", "b"]) as planter:
        planter.write(data)

    content = p.read_text(encoding="utf-8").strip().splitlines()
    assert content[0].strip() == "a,b"
    # data lines should be present
    assert any("1" in line and "2" in line for line in content[1:])


def test_hdfplanter_write(tmp_path):
    p = tmp_path / "out.h5"
    data = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32)

    with HDFPlanter(str(p), column_names=["ch1", "ch2"], sampling_freq=250, units="uV") as planter:
        planter.write(data)

    # verify HDF file contains expected datasets
    with h5py.File(str(p), "r") as f:
        assert "Data" in f
        assert "Info" in f
        assert "ChannelSettings" in f


def test_hdfplanter_add_marks_with_int_group(tmp_path):
    """未知 annotation group 在解析层是整数 0，add_marks 不得崩溃"""
    p = tmp_path / "out.h5"
    data = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32)

    with HDFPlanter(str(p), column_names=["ch1", "ch2"], sampling_freq=250, units="uV") as planter:
        planter.write(data)
        planter.add_marks(positions=[1, 2], groups=[0, "NOTE"], messages=["unknown group", "known"])

    with h5py.File(str(p), "r") as f:
        groups = [r["Group"].decode() for r in f["Marks"][:]]
        assert groups == ["0", "NOTE"]


def test_hdfplanter_add_marks_keeps_sample_zero(tmp_path):
    """位置 0 是合法的首采样点标注，不得被钳到 1；负数钳到 0"""
    p = tmp_path / "out.h5"
    data = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32)

    with HDFPlanter(str(p), column_names=["ch1", "ch2"], sampling_freq=250, units="uV") as planter:
        planter.write(data)
        planter.add_marks(positions=[0, -5], groups=["NOTE", "NOTE"], messages=["at start", "negative"])

    with h5py.File(str(p), "r") as f:
        positions = [int(r["SampleLeft"]) for r in f["Marks"][:]]
        assert positions == [0, 0]


# ========================= CSV / HDF5 缩放一致性 =========================

@pytest.mark.parametrize("dtype", [np.int32, np.int64, np.float32, np.float64])
def test_csv_and_hdf5_scale_identically_across_dtypes(tmp_path, dtype):
    """同一输入、同一 factor，CSV 与 HDF5 数值必须一致（KNOWN_ISSUES #27）。

    HDFPlanter 曾写作 `if not issubdtype(dtype, float32): astype(float32) / factor`——
    float32 输入**静默跳过缩放**，却仍按 units 声明标注。整数输入恰好走除法分支，
    才让 conversion 的真实路径一直是对的；float32 一进来两个格式就差 factor 倍。
    """
    data = np.array([[78000, 156000]], dtype=dtype)

    csv_path = tmp_path / f"o_{np.dtype(dtype).name}.csv"
    with CSVPlanter(str(csv_path), column_names=["I", "II"],
                    factor=1000, units="uV") as p:
        p.write(data)

    h5_path = tmp_path / f"o_{np.dtype(dtype).name}.h5"
    with HDFPlanter(str(h5_path), column_names=["I", "II"], sampling_freq=2000,
                    factor=1000, units="uV") as p:
        p.write(data)

    csv_lines = csv_path.read_text(encoding="utf-8").strip().splitlines()
    csv_vals = [float(v) for v in csv_lines[1].split(",")]
    with h5py.File(str(h5_path), "r") as f:
        h5_vals = [float(v) for v in np.asarray(f["Data"][:]).reshape(-1)]

    assert csv_vals == pytest.approx([78.0, 156.0])
    assert csv_vals == pytest.approx(h5_vals)
    assert csv_lines[0] == "I(uV),II(uV)"


def test_csvplanter_without_factor_is_unchanged(tmp_path):
    """不传 factor 的既有直接调用方行为必须不变（默认 factor=1、表头无单位后缀）。"""
    p = tmp_path / "legacy.csv"
    with CSVPlanter(str(p), column_names=["a", "b"]) as planter:
        planter.write(np.array([[78000, 156000]], dtype=np.int32))
    lines = p.read_text(encoding="utf-8").strip().splitlines()
    assert lines[0] == "a,b"
    assert lines[1].startswith("78000")
