# 按时间戳提取指定导联波形 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 提供 `epycon/extraction.py` 核心纯函数 `extract_window(...)` + 薄 CLI `epycon/cli/extract.py`，从原始 `.log` 分段目录按 WorkMate 走时钟流逝时刻提取指定导联 ±窗口的原始波形，供科学测量与 agent 调用。

**Architecture:** 整合现有零件（`list_datalogs` 枚举、`LogParser` 切片、`get_channel_mappings` 导联映射、`readentries` 标注、epoch 纯相减定位公式），新增仅四小块：段定位、窗口裁剪、栏杆检测、entries↔log 一致性硬校验。不改现有 `python -m epycon` 主流程（零回归）。

**Tech Stack:** Python 3, numpy, h5py（间接）, pytest, flake8。

## Global Constraints

- WorkMate 版本经 `_validate_version` 映射：`'4.1'`→x32；`'4.2'/'4.3'/'4.3.2'`→x64。**版本显式传入，缺省取 config `workmate_version`，无自动探测**。
- 全程 **epoch 纯相减，零时区**：`target_epoch = min(.log header.timestamp) + 流逝秒`。
- 段归属一律 **半开区间 `[ts, ts+dur)`**（避免段终点 off-by-one）。
- `center_sample = round(offset_sec * fs)`（round 取最近采样点，非 int 截断）。
- 默认单位 **µV** = `raw_int × resolution / 1000`（float64）；`--raw-counts` 出整数。
- 双极极性 **`u- − u+`**（现状，KNOWN_ISSUES #16），与 `_mount_channels` 的 `source[0]−source[1]` 一致，tests 钉死。
- `raw_int` 必须 **Python int / int64，严禁强转 int32**（栏杆值 `-2147483649` 越 int32 界）。
- 栏杆值集合（含 ε=0 精确匹配）：`{2147483647, -2147483648, -2147483649}`。
- `n` 一律取实际返回数组 `array.shape[0]`，禁用 `LogParser.num_samples`。
- 导联名 **精确匹配**，失败即报错列出可用名，不做模糊匹配。
- 失败一律抛 `ExtractionError`（fail-closed），CLI 捕获转 stderr JSON。
- flake8 必须 0 告警；全套 pytest 保持全绿。

**测试数据事实（realdata，version 4.3.2→x64）：**
- 12 段 `.log` + entries.log；fs=2000，resolution=78，88 数据列。
- 零点 epoch `1764297784.403`（段 `00000000` 起点）。
- 段 `00000000`: ns≈21020, dur≈10.510s。段 `00000005`: 起点 elapsed 4032.342s, ns≈21011, dur≈10.5055s。
- V6（及 V2–V5）栏杆：raw_int 恒为 `-2147483649`。
- `study01` 合成夹具：entry `fid=00000001` epoch 落在 `00000000` 区间 → 一致性校验必报错。

---

### Task 1: 时间解析 `parse_elapsed`

**Files:**
- Create: `epycon/extraction.py`
- Test: `tests/test_extraction.py`

**Interfaces:**
- Produces: `parse_elapsed(text: str) -> float`（`'H:MM:SS[.sss]'` 流逝时刻 → 秒，字面解析不吸附）；`class ExtractionError(ValueError)`。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_extraction.py
from pathlib import Path

import numpy as np
import pytest

from epycon.extraction import parse_elapsed, ExtractionError

ROOT = Path(__file__).parent.parent
REAL = ROOT / "examples" / "data" / "realdata"
STUDY01 = ROOT / "examples" / "data" / "study01"
VER = "4.3.2"


class TestParseElapsed:
    def test_whole_seconds(self):
        assert parse_elapsed("1:07:15") == 4035.0

    def test_subsecond(self):
        assert parse_elapsed("0:00:00.500") == pytest.approx(0.5)

    def test_two_digit_hours(self):
        assert parse_elapsed("10:00:00") == 36000.0

    def test_malformed_raises(self):
        with pytest.raises(ExtractionError):
            parse_elapsed("1:07")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_extraction.py::TestParseElapsed -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'epycon.extraction'`

- [ ] **Step 3: Write minimal implementation**

```python
# epycon/extraction.py
"""按 WorkMate 流逝时刻从原始 .log 分段提取指定导联 ±窗口的原始波形。

设计文档：docs/superpowers/specs/2026-07-08-timestamp-lead-extraction-design.md
全程 epoch 纯相减、零时区；段归属半开 [ts, ts+dur)；fail-closed。
"""


class ExtractionError(ValueError):
    """时间定位 / 一致性 / 导联查找的显式失败（fail-closed，绝不静默兜底）。"""


def parse_elapsed(text):
    """'H:MM:SS[.sss]' 流逝时刻 → 秒（字面解析，不吸附到最近段）。"""
    parts = text.strip().split(":")
    if len(parts) != 3:
        raise ExtractionError(f"时间格式须为 H:MM:SS[.sss]，得到 {text!r}")
    try:
        h, m, s = int(parts[0]), int(parts[1]), float(parts[2])
    except ValueError:
        raise ExtractionError(f"时间格式须为 H:MM:SS[.sss]，得到 {text!r}")
    return h * 3600 + m * 60 + s
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_extraction.py::TestParseElapsed -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add epycon/extraction.py tests/test_extraction.py
git commit -m "feat(extract): parse_elapsed 流逝时刻字面解析"
```

---

### Task 2: 段枚举与头读取 `load_segments`

**Files:**
- Modify: `epycon/extraction.py`
- Test: `tests/test_extraction.py`

**Interfaces:**
- Consumes: `ExtractionError`；`epycon.conversion.list_datalogs`；`epycon.iou.LogParser`。
- Produces: `load_segments(study_dir: str, version: str) -> list[dict]`，每段 dict 键：`id:str, path:str, ts:float, fs:int, ns:int, dur:float, resolution:int, header`。按 `ts` 升序。

- [ ] **Step 1: Write the failing test**

```python
class TestLoadSegments:
    def test_realdata_twelve_sorted(self):
        from epycon.extraction import load_segments
        segs = load_segments(str(REAL), VER)
        assert len(segs) == 12
        assert [s["id"] for s in segs] == sorted(s["id"] for s in segs)
        assert segs[0]["id"] == "00000000"

    def test_seg0_header_fields(self):
        from epycon.extraction import load_segments
        s0 = load_segments(str(REAL), VER)[0]
        assert s0["fs"] == 2000
        assert s0["resolution"] == 78
        assert s0["ts"] == pytest.approx(1764297784.403, abs=1e-3)
        assert s0["ns"] > 20000
        assert s0["dur"] == pytest.approx(s0["ns"] / 2000)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_extraction.py::TestLoadSegments -v`
Expected: FAIL — `ImportError: cannot import name 'load_segments'`

- [ ] **Step 3: Write minimal implementation**

追加到 `epycon/extraction.py`（顶部 import 区）：

```python
from epycon.conversion import list_datalogs
from epycon.iou import LogParser
```

追加函数：

```python
def load_segments(study_dir, version):
    """枚举目录 .log，读每段头 → 按 ts 升序的段列表。零点 = segs[0]['ts']。"""
    segs = []
    for path, seg_id in list_datalogs(study_dir):
        with LogParser(path, version=version, samplesize=1024) as parser:
            header = parser.get_header()
            ns = parser.num_samples
        fs = header.amp.sampling_freq
        segs.append({
            "id": seg_id,
            "path": path,
            "ts": float(header.timestamp),
            "fs": fs,
            "ns": ns,
            "dur": ns / fs if fs else 0.0,
            "resolution": header.amp.resolution,
            "header": header,
        })
    segs.sort(key=lambda s: s["ts"])
    return segs
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_extraction.py::TestLoadSegments -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add epycon/extraction.py tests/test_extraction.py
git commit -m "feat(extract): load_segments 枚举+读头，按 ts 排序"
```

---

### Task 3: 一致性硬校验 `check_consistency`

**Files:**
- Modify: `epycon/extraction.py`
- Test: `tests/test_extraction.py`

**Interfaces:**
- Consumes: `load_segments` 的段列表；`epycon.iou.readentries`；`epycon.config.byteschema.ENTRIES_FILENAME`。
- Produces: `check_consistency(study_dir: str, segments: list[dict], version: str) -> list`（返回 entries；任一违背抛 `ExtractionError`）。校验：entries.log 存在；每条 `entry.fid` 对上某段 `id`；`entry.timestamp ∈ [seg.ts, seg.ts+dur)`。

- [ ] **Step 1: Write the failing test**

```python
class TestConsistency:
    def test_realdata_passes(self):
        from epycon.extraction import load_segments, check_consistency
        segs = load_segments(str(REAL), VER)
        entries = check_consistency(str(REAL), segs, VER)
        assert len(entries) == 12

    def test_study01_fails(self):
        from epycon.extraction import load_segments, check_consistency
        segs = load_segments(str(STUDY01), "4.3.2")
        with pytest.raises(ExtractionError, match="00000001"):
            check_consistency(str(STUDY01), segs, "4.3.2")

    def test_missing_entries_raises(self, tmp_path):
        from epycon.extraction import check_consistency
        with pytest.raises(ExtractionError, match="entries"):
            check_consistency(str(tmp_path), [], VER)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_extraction.py::TestConsistency -v`
Expected: FAIL — `ImportError: cannot import name 'check_consistency'`

- [ ] **Step 3: Write minimal implementation**

追加 import：

```python
import os

from epycon.config.byteschema import ENTRIES_FILENAME
from epycon.iou import readentries
```

追加函数：

```python
def check_consistency(study_dir, segments, version):
    """fail-closed 校验：entries.log 必需；每条 entry 的 fid 对上段、
    epoch 落在该段半开区间。返回 entries。任一违背抛 ExtractionError。"""
    entries_path = os.path.join(study_dir, ENTRIES_FILENAME)
    if not os.path.exists(entries_path):
        raise ExtractionError(f"缺少 {ENTRIES_FILENAME}，无法校验一致性: {study_dir}")
    entries = readentries(f_path=entries_path, version=version)
    by_id = {s["id"]: s for s in segments}
    for entry in entries:
        seg = by_id.get(str(entry.fid))
        if seg is None:
            raise ExtractionError(f"entry fid={entry.fid} 无对应 .log 段")
        ts = float(entry.timestamp)
        if not (seg["ts"] <= ts < seg["ts"] + seg["dur"]):
            raise ExtractionError(
                f"entry fid={entry.fid} epoch={ts} 落在段 {seg['id']} 区间 "
                f"[{seg['ts']}, {seg['ts'] + seg['dur']}) 之外")
    return entries
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_extraction.py::TestConsistency -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add epycon/extraction.py tests/test_extraction.py
git commit -m "feat(extract): check_consistency entries<->log 硬校验"
```

---

### Task 4: 段定位与窗口裁剪 `locate_segment` + `_window_samples`

**Files:**
- Modify: `epycon/extraction.py`
- Test: `tests/test_extraction.py`

**Interfaces:**
- Consumes: 段列表。
- Produces:
  - `locate_segment(segments, target_epoch: float) -> dict | None`（半开 `[ts, ts+dur)`）。
  - `_window_samples(seg: dict, offset_sec: float, before: float, after: float) -> tuple[int, int, float, float]` 返回 `(start_sample, end_sample, missing_before_s, missing_after_s)`，`end` 为排他上界，已裁剪到 `[0, ns]`。

- [ ] **Step 1: Write the failing test**

```python
class TestLocateAndWindow:
    def test_locate_hits_segment5(self):
        from epycon.extraction import load_segments, locate_segment
        segs = load_segments(str(REAL), VER)
        zero = segs[0]["ts"]
        seg = locate_segment(segs, zero + 4035.0)  # 1:07:15
        assert seg["id"] == "00000005"

    def test_locate_gap_returns_none(self):
        from epycon.extraction import load_segments, locate_segment
        segs = load_segments(str(REAL), VER)
        zero = segs[0]["ts"]
        assert locate_segment(segs, zero + 4032.0) is None  # 1:07:12，段5起点前

    def test_window_full_within_segment(self):
        from epycon.extraction import _window_samples
        seg = {"fs": 2000, "ns": 21011}
        s0, s1, mb, ma = _window_samples(seg, 2.658, 2.0, 2.0)
        assert (s0, s1) == (1316, 9316)
        assert s1 - s0 == 8000
        assert mb == 0.0 and ma == 0.0

    def test_window_clipped_at_start(self):
        from epycon.extraction import _window_samples
        seg = {"fs": 2000, "ns": 21011}
        s0, s1, mb, ma = _window_samples(seg, 0.658, 2.0, 2.0)
        assert s0 == 0
        assert mb == pytest.approx(1.342, abs=1e-6)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_extraction.py::TestLocateAndWindow -v`
Expected: FAIL — `ImportError: cannot import name 'locate_segment'`

- [ ] **Step 3: Write minimal implementation**

```python
def locate_segment(segments, target_epoch):
    """返回覆盖 target_epoch 的段（半开 [ts, ts+dur)），无则 None。"""
    for seg in segments:
        if seg["ts"] <= target_epoch < seg["ts"] + seg["dur"]:
            return seg
    return None


def _window_samples(seg, offset_sec, before, after):
    """段内偏移 ±(before/after) → 裁剪后的 [start, end) 样本索引 + 缺失秒数。"""
    fs = seg["fs"]
    ns = seg["ns"]
    start = round((offset_sec - before) * fs)
    end = round((offset_sec + after) * fs)  # 排他上界
    clipped_start = max(0, start)
    clipped_end = min(ns, end)
    missing_before = (clipped_start - start) / fs
    missing_after = (end - clipped_end) / fs
    return clipped_start, clipped_end, missing_before, missing_after
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_extraction.py::TestLocateAndWindow -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add epycon/extraction.py tests/test_extraction.py
git commit -m "feat(extract): locate_segment 半开定位 + 窗口裁剪"
```

---

### Task 5: 原始整数读取与栏杆检测 `read_raw_window` + `is_railed`

**Files:**
- Modify: `epycon/extraction.py`
- Test: `tests/test_extraction.py`

**Interfaces:**
- Consumes: 段 dict；`LogParser(start, end)`。
- Produces:
  - `read_raw_window(seg, start_sample: int, end_sample: int, version: str) -> np.ndarray`，返回 `(N, num_channels)` **int64 原始整数**（`_process_chunk` 缩放值反除 resolution 无损还原）。
  - `RAIL_VALUES = frozenset({2147483647, -2147483648, -2147483649})`。
  - `is_railed(col: np.ndarray) -> bool`（窗口内恒定 **且** 命中栏杆值）。

- [ ] **Step 1: Write the failing test**

```python
class TestRawAndRail:
    def test_raw_int_dtype_and_length(self):
        from epycon.extraction import load_segments, read_raw_window
        segs = load_segments(str(REAL), VER)
        seg = [s for s in segs if s["id"] == "00000005"][0]
        raw = read_raw_window(seg, 1316, 9316, VER)
        assert raw.dtype == np.int64
        assert raw.shape[0] == 8000

    def test_v6_column_railed(self):
        from epycon.extraction import load_segments, read_raw_window, is_railed
        segs = load_segments(str(REAL), VER)
        seg = [s for s in segs if s["id"] == "00000005"][0]
        names = seg["header"].get_chnames()
        v6_ref = seg["header"].channels.content[names.index("V6")].reference
        raw = read_raw_window(seg, 1316, 9316, VER)
        col = raw[:, v6_ref]
        assert bool(np.all(col == -2147483649))
        assert is_railed(col) is True

    def test_connected_column_not_railed(self):
        from epycon.extraction import load_segments, read_raw_window, is_railed
        segs = load_segments(str(REAL), VER)
        seg = [s for s in segs if s["id"] == "00000005"][0]
        raw = read_raw_window(seg, 1316, 9316, VER)
        # II 的 reference = 1（连接导联，真实信号）
        assert is_railed(raw[:, 1]) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_extraction.py::TestRawAndRail -v`
Expected: FAIL — `ImportError: cannot import name 'read_raw_window'`

- [ ] **Step 3: Write minimal implementation**

追加 import：`import numpy as np`

```python
RAIL_VALUES = frozenset({2147483647, -2147483648, -2147483649})


def read_raw_window(seg, start_sample, end_sample, version):
    """读段内 [start, end) 样本 → (N, num_channels) int64 原始整数。

    LogParser 的 _process_chunk 总是 _twos_complement 后 ×resolution；
    这里反除 resolution 无损还原（resolution 为整数、值均为其整数倍，
    上界 (2^31+1)*78 ≈ 1.675e11 < 2^53，float64 精确）。int64 承载栏杆
    值 -2147483649（越 int32 界）。"""
    with LogParser(seg["path"], version=version, samplesize=1024,
                   start=start_sample, end=end_sample) as parser:
        scaled = parser.read()  # (N, num_channels)，已 ×resolution
    res = seg["resolution"]
    return np.rint(np.asarray(scaled, dtype=np.float64) / res).astype(np.int64)


def is_railed(col):
    """窗口内该列恒定且命中满量程栏杆值 → True（未连接电极）。"""
    if col.size == 0:
        return False
    first = col[0]
    if not np.all(col == first):
        return False
    return int(first) in RAIL_VALUES
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_extraction.py::TestRawAndRail -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add epycon/extraction.py tests/test_extraction.py
git commit -m "feat(extract): read_raw_window 原始整数还原 + is_railed 栏杆检测"
```

---

### Task 6: 导联映射与差分 `resolve_lead_sources` + `_lead_signal`

**Files:**
- Modify: `epycon/extraction.py`
- Test: `tests/test_extraction.py`

**Interfaces:**
- Consumes: 段 `header`；`epycon.core.helpers.get_channel_mappings`。
- Produces:
  - `resolve_lead_sources(header, requested: list[str], raw_unipolar: bool) -> list[tuple[str, tuple]]`（computed 或 original 映射；名字精确匹配，缺失抛 `ExtractionError` 列出可用名）。
  - `_lead_signal(raw_int: np.ndarray, sources: tuple) -> np.ndarray`（单源直取；双源 `source[0]-source[1]` = `u- − u+`）。

- [ ] **Step 1: Write the failing test**

```python
class TestLeadResolve:
    def test_surface_lead_single_source(self):
        from epycon.extraction import load_segments, resolve_lead_sources
        seg = load_segments(str(REAL), VER)[0]
        out = resolve_lead_sources(seg["header"], ["V6"], False)
        assert out[0][0] == "V6"
        assert len(out[0][1]) == 1

    def test_bipolar_sign_is_uminus_minus_uplus(self):
        from epycon.extraction import (
            load_segments, resolve_lead_sources, read_raw_window, _lead_signal)
        seg = [s for s in load_segments(str(REAL), VER) if s["id"] == "00000005"][0]
        raw = read_raw_window(seg, 1316, 9316, VER)
        # 手算 u- - u+：从 header 取 CS 3-4 的两源 reference
        content = seg["header"].channels.content
        names = [c.name for c in content]
        ref_uplus = content[names.index("u+CS 3-4")].reference
        ref_uminus = content[names.index("u-CS 3-4")].reference
        expected = raw[:, ref_uminus] - raw[:, ref_uplus]
        sources = resolve_lead_sources(seg["header"], ["CS 3-4"], False)[0][1]
        got = _lead_signal(raw, sources)
        assert np.array_equal(got, expected)

    def test_unknown_lead_raises_with_available(self):
        from epycon.extraction import load_segments, resolve_lead_sources
        seg = load_segments(str(REAL), VER)[0]
        with pytest.raises(ExtractionError, match="NOPE"):
            resolve_lead_sources(seg["header"], ["NOPE"], False)

    def test_raw_unipolar_exposes_uplus_uminus(self):
        from epycon.extraction import load_segments, resolve_lead_sources
        seg = load_segments(str(REAL), VER)[0]
        out = resolve_lead_sources(seg["header"], ["u+CS 3-4"], True)
        assert out[0][0] == "u+CS 3-4"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_extraction.py::TestLeadResolve -v`
Expected: FAIL — `ImportError: cannot import name 'resolve_lead_sources'`

- [ ] **Step 3: Write minimal implementation**

追加 import：`from epycon.core.helpers import get_channel_mappings`

```python
def resolve_lead_sources(header, requested, raw_unipolar):
    """导联名 → 源通道 reference 元组。computed（默认）自动双极；
    original（--raw-unipolar）出单极。名字精确匹配，缺失即报错。"""
    cfg = {"data": {
        "leads": "original" if raw_unipolar else "computed",
        "custom_channels": {},
    }}
    mapping = get_channel_mappings(header, cfg)
    out = []
    for name in requested:
        if name not in mapping:
            raise ExtractionError(
                f"导联 {name!r} 不在通道表；可用: {sorted(mapping)}")
        out.append((name, mapping[name]))
    return out


def _lead_signal(raw_int, sources):
    """单源直取；双源 source[0]-source[1]（= u- − u+，与 _mount_channels 一致）。"""
    if len(sources) == 1:
        return raw_int[:, sources[0]]
    return raw_int[:, sources[0]] - raw_int[:, sources[1]]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_extraction.py::TestLeadResolve -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add epycon/extraction.py tests/test_extraction.py
git commit -m "feat(extract): resolve_lead_sources + _lead_signal（u- - u+ 极性）"
```

---

### Task 7: 编排 `extract_window` 返回结果 dict

**Files:**
- Modify: `epycon/extraction.py`
- Test: `tests/test_extraction.py`

**Interfaces:**
- Consumes: Task 1–6 全部。
- Produces: `extract_window(study_dir, at_elapsed=None, at_epoch=None, leads=None, window=2.0, before=None, after=None, raw_unipolar=False, raw_counts=False, units="uV", version=None) -> dict`，形态见设计文档第 8 节。含 `_default_version()`、`_gap_message()` 私有辅助。

- [ ] **Step 1: Write the failing test**

```python
class TestExtractWindow:
    def test_connected_and_railed_mix(self):
        from epycon.extraction import extract_window
        r = extract_window(str(REAL), at_elapsed="1:07:15",
                           leads=["II", "V6"], window=2.0, version=VER)
        assert r["log"] == "00000005"
        assert r["units"] == "uV"
        assert r["fs"] == 2000
        by = {l["name"]: l for l in r["leads"]}
        assert by["II"]["status"] == "ok"
        assert by["II"]["n"] == 8000
        assert by["V6"]["status"] == "rejected"
        assert r["returned_window"]["clipped"] is False

    def test_gap_rejects(self):
        from epycon.extraction import extract_window
        with pytest.raises(ExtractionError, match="空档"):
            extract_window(str(REAL), at_elapsed="1:07:12",
                           leads=["II"], window=2.0, version=VER)

    def test_clip_reports_missing(self):
        from epycon.extraction import extract_window
        r = extract_window(str(REAL), at_elapsed="1:07:13",
                           leads=["II"], window=2.0, version=VER)
        assert r["returned_window"]["clipped"] is True
        assert r["returned_window"]["missing_s"] == pytest.approx(1.342, abs=1e-3)
        # 裁剪后样本数 = 未裁前 8000 − 缺失 2684 = 5316，且与实际返回一致
        assert r["leads"][0]["n"] == 5316

    def test_raw_counts_units(self):
        from epycon.extraction import extract_window
        r = extract_window(str(REAL), at_elapsed="1:07:15",
                           leads=["II"], window=2.0, raw_counts=True, version=VER)
        assert r["units"] == "counts"
        assert all(isinstance(x, int) for x in r["leads"][0]["samples"][:5])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_extraction.py::TestExtractWindow -v`
Expected: FAIL — `ImportError: cannot import name 'extract_window'`

- [ ] **Step 3: Write minimal implementation**

追加 import：`import json`

```python
def _default_version():
    cfg_path = os.environ.get(
        "EPYCON_CONFIG",
        os.path.join(os.path.dirname(__file__), "config", "config.json"))
    with open(cfg_path, "r", encoding="utf-8") as f:
        return json.load(f)["global_settings"]["workmate_version"]


def _gap_message(segments, target_epoch, zero):
    tel = target_epoch - zero
    prev = [s for s in segments if s["ts"] + s["dur"] <= target_epoch]
    nxt = [s for s in segments if s["ts"] > target_epoch]

    def rng(s):
        a = s["ts"] - zero
        return f"{s['id']} [{a:.3f}, {a + s['dur']:.3f}]s"

    p = rng(prev[-1]) if prev else "—"
    n = rng(nxt[0]) if nxt else "—"
    return f"目标流逝 {tel:.3f}s 落在段间空档，无录制数据。前段: {p}; 后段: {n}"


def extract_window(study_dir, at_elapsed=None, at_epoch=None, leads=None,
                   window=2.0, before=None, after=None, raw_unipolar=False,
                   raw_counts=False, units="uV", version=None):
    """按流逝时刻/epoch 提取指定导联 ±窗口原始波形。见设计文档第 8 节。"""
    if version is None:
        version = _default_version()
    if not leads:
        raise ExtractionError("须提供至少一个导联名")
    before = window if before is None else before
    after = window if after is None else after

    segments = load_segments(study_dir, version)
    if not segments:
        raise ExtractionError(f"{study_dir} 无 .log 段")
    check_consistency(study_dir, segments, version)
    zero = segments[0]["ts"]

    if at_epoch is not None:
        target = float(at_epoch)
    elif at_elapsed is not None:
        target = zero + parse_elapsed(at_elapsed)
    else:
        raise ExtractionError("须提供 at_elapsed 或 at_epoch")

    seg = locate_segment(segments, target)
    if seg is None:
        raise ExtractionError(_gap_message(segments, target, zero))

    offset = target - seg["ts"]
    s0, s1, miss_b, miss_a = _window_samples(seg, offset, before, after)
    if s1 <= s0:
        raise ExtractionError("窗口在该段内无有效样本")

    raw_int = read_raw_window(seg, s0, s1, version)
    sources = resolve_lead_sources(seg["header"], leads, raw_unipolar)
    res = seg["resolution"]
    fs = seg["fs"]

    lead_out = []
    for name, cols in sources:
        if any(is_railed(raw_int[:, c]) for c in cols):
            lead_out.append({"name": name, "status": "rejected",
                             "reason": "通道恒定于满量程，电极未连接"})
            continue
        sig = _lead_signal(raw_int, cols)
        if raw_counts:
            samples = [int(x) for x in sig]
        else:
            samples = (sig.astype(np.float64) * res / 1000.0).tolist()
        lead_out.append({"name": name, "status": "ok",
                         "n": int(sig.shape[0]), "samples": samples})

    return {
        "study": os.path.basename(os.path.normpath(study_dir)),
        "log": seg["id"],
        "version": version,
        "fs": fs,
        "units": "counts" if raw_counts else units,
        "resolution_nV": res,
        "target": {"elapsed": at_elapsed, "epoch": target,
                   "offset_in_seg_s": offset},
        "requested_window": {"before": before, "after": after},
        "returned_window": {"start_s": s0 / fs, "end_s": s1 / fs,
                            "clipped": bool(miss_b or miss_a),
                            "missing_s": miss_b + miss_a},
        "leads": lead_out,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_extraction.py::TestExtractWindow -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add epycon/extraction.py tests/test_extraction.py
git commit -m "feat(extract): extract_window 编排 + 结果 dict"
```

---

### Task 8: 薄 CLI `epycon/cli/extract.py`

**Files:**
- Create: `epycon/cli/extract.py`
- Test: `tests/test_cli_extract.py`

**Interfaces:**
- Consumes: `extract_window`, `ExtractionError`。
- Produces: `python -m epycon.cli.extract` 入口 `main() -> int`；参数 `--study`（必需）、`--at`/`--epoch`（互斥必需其一）、`--leads`（必需，逗号分隔）、`--window`（默认 2.0）、`--before`/`--after`、`--raw-unipolar`、`--raw-counts`、`--version`、`--out`。成功打 JSON 到 stdout（返回 0）；`--out` 时写 `.npz` 并打精简 metadata；`ExtractionError` 转 stderr JSON（返回 2）。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli_extract.py
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
REAL = ROOT / "examples" / "data" / "realdata"


def _run(args):
    return subprocess.run(
        [sys.executable, "-m", "epycon.cli.extract", *args],
        capture_output=True, text=True, cwd=str(ROOT))


class TestCliExtract:
    def test_ok_json_stdout(self):
        r = _run(["--study", str(REAL), "--at", "1:07:15",
                  "--leads", "II,V6", "--window", "2", "--version", "4.3.2"])
        assert r.returncode == 0
        out = json.loads(r.stdout)
        assert out["log"] == "00000005"
        by = {l["name"]: l for l in out["leads"]}
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cli_extract.py -v`
Expected: FAIL — `No module named epycon.cli.extract`

- [ ] **Step 3: Write minimal implementation**

```python
# epycon/cli/extract.py
"""按时间戳提取指定导联波形的 CLI。见设计文档第 9 节。

python -m epycon.cli.extract --study <dir> --at 1:07:15 --leads V6,"CS 3-4" --window 2
"""
import sys
import json
import argparse

import numpy as np

from epycon.extraction import extract_window, ExtractionError


def _build_parser():
    ap = argparse.ArgumentParser(prog="python -m epycon.cli.extract")
    ap.add_argument("--study", required=True)
    tgt = ap.add_mutually_exclusive_group(required=True)
    tgt.add_argument("--at", help="流逝时刻 H:MM:SS[.sss]")
    tgt.add_argument("--epoch", type=float, help="绝对 epoch 秒")
    ap.add_argument("--leads", required=True, help="逗号分隔导联名")
    ap.add_argument("--window", type=float, default=2.0)
    ap.add_argument("--before", type=float)
    ap.add_argument("--after", type=float)
    ap.add_argument("--raw-unipolar", action="store_true")
    ap.add_argument("--raw-counts", action="store_true")
    ap.add_argument("--version")
    ap.add_argument("--out", help="写 .npz 文件而非 stdout 全量")
    return ap


def _save_npz(path, result):
    arrays = {l["name"]: np.asarray(l["samples"])
              for l in result["leads"] if l["status"] == "ok"}
    meta = {k: v for k, v in result.items() if k != "leads"}
    meta["leads"] = [{k: v for k, v in l.items() if k != "samples"}
                     for l in result["leads"]]
    np.savez(path, _meta=json.dumps(meta, ensure_ascii=False), **arrays)


def main(argv=None):
    args = _build_parser().parse_args(argv)
    leads = [x.strip() for x in args.leads.split(",") if x.strip()]
    try:
        result = extract_window(
            args.study, at_elapsed=args.at, at_epoch=args.epoch, leads=leads,
            window=args.window, before=args.before, after=args.after,
            raw_unipolar=args.raw_unipolar, raw_counts=args.raw_counts,
            version=args.version)
    except ExtractionError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 2
    if args.out:
        _save_npz(args.out, result)
        meta = {k: v for k, v in result.items() if k != "leads"}
        meta["leads"] = [{k: v for k, v in l.items() if k != "samples"}
                         for l in result["leads"]]
        meta["out"] = args.out
        print(json.dumps(meta, ensure_ascii=False))
    else:
        print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cli_extract.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add epycon/cli/extract.py tests/test_cli_extract.py
git commit -m "feat(extract): 薄 CLI python -m epycon.cli.extract"
```

---

### Task 9: 全套回归 + flake8 收尾

**Files:**
- 无新增代码；验证全绿。

- [ ] **Step 1: 全套 pytest**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: 原有 + 新增用例全绿（无 fail/error）。若新增 realdata 依赖用例被 skip，检查 realdata 是否入库（应在）。

- [ ] **Step 2: flake8 零告警**

Run: `.venv\Scripts\python.exe -m flake8 epycon/`
Expected: 无输出（0 告警）。若有超长行/未用导入，就地修。

- [ ] **Step 3: 真实端到端手验（连接导联出波、V6 拒绝）**

Run:
```bash
.venv\Scripts\python.exe -m epycon.cli.extract --study examples/data/realdata --at 1:07:15 --leads II,V6 --window 2 --version 4.3.2
```
Expected: JSON，`log=00000005`，II `status=ok n=8000`，V6 `status=rejected`。

- [ ] **Step 4: Commit（若 Step 2 有修复）**

```bash
git add -A
git commit -m "chore(extract): flake8 收尾 + 全套回归通过"
```

---

## Self-Review

**Spec coverage（对照设计文档各节）：**
- 第 4 节时间模型 → Task 1（parse_elapsed）+ Task 4（locate 半开）+ Task 7（zero/target）✓
- 第 5 节一致性硬校验 → Task 3 ✓
- 第 6 节窗口裁剪 → Task 4（_window_samples）+ Task 7（clipped/missing）✓
- 第 7 节导联 computed/original + 极性 + 脏名 + 栏杆 → Task 5（rail）+ Task 6（mapping/sign/name-error）✓
- 第 8 节输出 dict / µV / raw-counts / n=shape[0] → Task 7 ✓
- 第 9 节集成（核心函数 + CLI + 显式版本 + raw_int int64） → Task 5/7/8 ✓
- 第 10 节作用域（仅 .log 分段） → 隐含（load_segments 只读 .log）✓
- 第 12 节验证计划 → Task 4/7 各拒绝/裁剪用例 + Task 9 端到端 ✓

**Placeholder scan：** 无 TBD/TODO；每步含完整代码与确切命令。

**Type consistency：** `load_segments` 段 dict 键（id/path/ts/fs/ns/dur/resolution/header）在 Task 2 定义，Task 3–7 一致引用；`extract_window` 结果 dict 键与设计文档第 8 节一致；`resolve_lead_sources` 返回 `list[(name, cols)]`，Task 6/7 一致。
