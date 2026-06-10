"""业务逻辑测试

自 scripts/test_business_functions.py（自写 runner）移植为 pytest，2026-06-10。
原脚本曾作为 CI 独立步骤运行；合流后 CI 只保留 pytest 入口。
"""
import json
from pathlib import Path

import h5py
import jsonschema
import numpy as np
import pytest

from epycon.core._validators import _validate_version
from epycon.core.helpers import deep_override, difftimestamp
from epycon.config.byteschema import WMx32LogSchema, WMx64LogSchema
from epycon.iou.parsers import _mount_channels
from epycon.iou.planters import CSVPlanter, HDFPlanter

ROOT = Path(__file__).parent.parent


class TestVersionDetection:
    def test_41_is_x32(self):
        assert _validate_version("4.1") == "x32"

    def test_42_43_are_x64(self):
        for v in ("4.2", "4.3", "4.3.2"):
            assert _validate_version(v) == "x64"

    def test_schema_supported_versions(self):
        assert WMx32LogSchema.supported_versions == "4.1"
        assert "4.2" in WMx64LogSchema.supported_versions
        assert "4.3" in WMx64LogSchema.supported_versions


class TestHelpers:
    def test_deep_override(self):
        cfg = {"paths": {"input": "default"}, "data": {"format": "csv"}}
        deep_override(cfg, ["paths", "input"], "custom_path")
        deep_override(cfg, ["data", "format"], "h5")
        assert cfg["paths"]["input"] == "custom_path"
        assert cfg["data"]["format"] == "h5"

    def test_deep_override_unknown_key_raises(self):
        with pytest.raises(KeyError):
            deep_override({"a": {}}, ["a", "nope"], 1)

    def test_difftimestamp_one_hour(self):
        assert difftimestamp([1704038400, 1704042000]) == pytest.approx(3600)


def test_mount_channels_subset():
    data = np.random.default_rng(0).normal(size=(100, 3))
    mounted = _mount_channels(data, {"Ch1": [0], "Ch2": [1]})
    assert mounted.shape == (100, 2)


class TestPlantersBusiness:
    def test_csv_planter_writes_rows(self, tmp_path):
        csv_path = tmp_path / "test.csv"
        with CSVPlanter(str(csv_path)) as planter:
            planter.write(np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]]))
        lines = csv_path.read_text().strip().splitlines()
        assert len(lines) == 4  # header + 3 rows

    def test_hdf_planter_creates_valid_file(self, tmp_path):
        h5_path = tmp_path / "test.h5"
        with HDFPlanter(
            str(h5_path), column_names=["Ch1", "Ch2"], sampling_freq=500,
            attributes={"subject_id": "TEST001"},
        ) as planter:
            planter.write(np.random.default_rng(1).normal(size=(1024, 2)))
        with h5py.File(h5_path, "r") as f:
            assert "Data" in f
            assert max(f["Data"].shape) == 1024

    def test_hdf_planter_append_mode(self, tmp_path):
        h5_path = tmp_path / "merged.h5"
        for batch in range(2):
            with HDFPlanter(
                str(h5_path), column_names=["Ch1", "Ch2"], sampling_freq=500,
                append=batch > 0,
            ) as planter:
                planter.write(np.random.default_rng(batch).normal(size=(512, 2)))
        with h5py.File(h5_path, "r") as f:
            assert max(f["Data"].shape) == 1024  # 512 + 512


def test_full_config_validates_against_schema():
    valid_cfg = {
        "paths": {"input_folder": "test", "output_folder": "out", "studies": []},
        "data": {
            "output_format": "h5", "pin_entries": True, "leads": "original",
            "data_files": [], "channels": [], "custom_channels": {},
            "merge_logs": True,
        },
        "entries": {
            "convert": True, "output_format": "sel", "summary_csv": True,
            "filter_annotation_type": [],
        },
        "global_settings": {
            "workmate_version": "4.3", "pseudonymize": False,
            "processing": {"chunk_size": 1024000},
            "credentials": {"author": "test", "device": "test", "owner": "test"},
        },
    }
    schema = json.loads((ROOT / "config" / "schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(valid_cfg, schema)
