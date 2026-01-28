import os
import tempfile
import time
from datetime import datetime

import pytest

from epycon.core import helpers


def test_deep_override_success():
    cfg = {"a": {"b": {"c": 1}}}
    res = helpers.deep_override(cfg, ["a", "b", "c"], 5)
    assert res["a"]["b"]["c"] == 5


def test_deep_override_keyerror():
    cfg = {"a": {"b": {"c": 1}}}
    with pytest.raises(KeyError):
        helpers.deep_override(cfg, ["a", "x", "y"], 2)


def test_difftimestamp():
    t0 = time.time()
    t1 = t0 + 2.5
    assert abs(helpers.difftimestamp([t0, t1]) - 2.5) < 0.01


def test_safe_string_replacement():
    s = "a,b;c/d\\:e"
    out = helpers.safe_string(s, safe_char="_")
    assert "," not in out and ";" not in out and "/" not in out and \
        "\\" not in out and ":" not in out


def test_pretty_json_roundtrip():
    d = {"k": [1, 2, 3], "msg": "hello"}
    s = helpers.pretty_json(d)
    # ensure it's valid JSON and contains keys
    assert '"k"' in s and '"msg"' in s
    # loads back to same structure
    import json
    assert json.loads(s) == d


def test_default_log_path():
    """Test default_log_path function."""
    log_path = helpers.default_log_path()
    assert isinstance(log_path, str)
    assert log_path.endswith("epycon.log")
    # Path should exist or be creatable
    log_dir = os.path.dirname(log_path)
    assert os.path.exists(log_dir) or log_dir == ""
