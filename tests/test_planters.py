import os
import tempfile
import numpy as np
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
