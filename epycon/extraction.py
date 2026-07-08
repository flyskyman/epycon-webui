"""按 WorkMate 流逝时刻从原始 .log 分段提取指定导联 ±窗口的原始波形。

设计文档：docs/superpowers/specs/2026-07-08-timestamp-lead-extraction-design.md
全程 epoch 纯相减、零时区；段归属半开 [ts, ts+dur)；fail-closed。
"""
import os
import json
import math
import struct

import numpy as np

# 底层解析器在畸形输入上抛的预期异常——统一转 ExtractionError 走结构化错误，
# 但不含裸 Exception，避免吞掉真正的编程 bug
_PARSE_ERRORS = (struct.error, ValueError, OSError)

from epycon.config.byteschema import ENTRIES_FILENAME
from epycon.conversion import list_datalogs
from epycon.core._validators import _validate_version
from epycon.core.helpers import get_channel_mappings
from epycon.iou import LogParser, mount_channels, readentries

RAIL_VALUES = frozenset({2147483647, -2147483648, -2147483649})


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
    # 字段范围校验：不静默归一化越界值（0:67:15 不可当成 1:07:15）
    if h < 0 or not (0 <= m < 60) or not (0 <= s < 60):
        raise ExtractionError(
            f"时间字段越界（须 h>=0, 0<=m<60, 0<=s<60）：{text!r}")
    return h * 3600 + m * 60 + s


def load_segments(study_dir, version):
    """枚举目录 .log，读每段头 → 按 ts 升序的段列表。零点 = segs[0]['ts']。"""
    segs = []
    for path, seg_id in list_datalogs(study_dir):
        try:
            with LogParser(path, version=version, samplesize=1024) as parser:
                header = parser.get_header()
                ns = parser.num_samples
        except _PARSE_ERRORS as e:
            raise ExtractionError(f"无法解析 .log 段 {seg_id}：{e}")
        fs = header.amp.sampling_freq
        resolution = header.amp.resolution
        # fail-closed：非法头（fs/resolution 为 0）必须报错，不能静默产出 dur=0
        # 隐藏该段、或在 read_raw_window 里除零出 NaN
        if not fs or not resolution:
            raise ExtractionError(
                f"段 {seg_id} 头非法：sampling_freq={fs}, resolution={resolution}")
        segs.append({
            "id": seg_id,
            "path": path,
            "ts": float(header.timestamp),
            "fs": fs,
            "ns": ns,
            "dur": ns / fs,
            "resolution": resolution,
            "header": header,
        })
    segs.sort(key=lambda s: s["ts"])
    return segs


def check_consistency(study_dir, segments, version):
    """fail-closed 校验：entries.log 必需；每条 entry 的 fid 对上段、
    epoch 落在该段半开区间。返回 entries。任一违背抛 ExtractionError。"""
    entries_path = os.path.join(study_dir, ENTRIES_FILENAME)
    if not os.path.exists(entries_path):
        raise ExtractionError(f"缺少 {ENTRIES_FILENAME}，无法校验一致性: {study_dir}")
    try:
        entries = readentries(f_path=entries_path, version=version)
    except _PARSE_ERRORS as e:
        raise ExtractionError(f"无法解析 {ENTRIES_FILENAME}：{e}")
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
    first = col[0]
    if not np.all(col == first):
        return False
    return int(first) in RAIL_VALUES


def resolve_lead_sources(header, requested, raw_unipolar):
    """导联名 → 源通道 reference 元组。computed（默认）自动双极；
    original（--raw-unipolar）出单极。名字精确匹配，缺失即报错。
    fail-closed：源参考必须是落在 [0, num_channels) 的有效列索引——
    inactive 导联的 None、或脏 header 的越界索引都拒绝，避免 numpy
    把 None 当 newaxis、或越界索引抛非 ExtractionError 的 IndexError。"""
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
        cols = mapping[name]
        for col in cols:
            if col is None or not (0 <= col < header.num_channels):
                raise ExtractionError(
                    f"导联 {name!r} 源电极参考无效（{col}），本次未有效记录")
        out.append((name, cols))
    return out


def _lead_signal(raw_int, sources):
    """单源直取；双源 u- − u+。委托已导出的 mount_channels，保持双极合成
    规则与 conversion 单一来源、不漂移（sources 已是有效列索引，见
    resolve_lead_sources 的守卫）。"""
    return mount_channels(raw_int, {"_": sources})[:, 0]


def _default_version():
    """从 config 读默认 workmate_version。任何读取/解析失败都转成
    ExtractionError，使不带 --version 的常见调用仍走 CLI 的结构化错误路径，
    而非漏出 FileNotFoundError/KeyError/JSONDecodeError 变 traceback。"""
    cfg_path = os.environ.get(
        "EPYCON_CONFIG",
        os.path.join(os.path.dirname(__file__), "config", "config.json"))
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            return json.load(f)["global_settings"]["workmate_version"]
    except (OSError, ValueError, KeyError) as e:
        raise ExtractionError(
            f"无法从 config 读取默认 workmate_version（{cfg_path}）：{e}；"
            f"请显式传 --version")


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
                   raw_counts=False, version=None):
    """按流逝时刻/epoch 提取指定导联 ±窗口原始波形。见设计文档第 8 节。
    非 raw_counts 时物理值固定为 µV（= raw_int × resolution / 1000）。"""
    if version is None:
        version = _default_version()
    # 非法版本在 LogParser 里会抛 ValueError；此处提前转 ExtractionError，
    # 让 CLI 走结构化错误而非漏出 traceback
    try:
        _validate_version(version)
    except ValueError as e:
        raise ExtractionError(f"无效 workmate_version {version!r}：{e}")
    if not leads:
        raise ExtractionError("须提供至少一个导联名")
    before = window if before is None else before
    after = window if after is None else after
    if not (math.isfinite(before) and math.isfinite(after)):
        raise ExtractionError(
            f"窗口 before/after 须为有限值（before={before}, after={after}）")
    if before < 0 or after < 0:
        raise ExtractionError(
            f"窗口 before/after 不可为负（before={before}, after={after}）")

    segments = load_segments(study_dir, version)
    if not segments:
        raise ExtractionError(f"{study_dir} 无 .log 段")
    check_consistency(study_dir, segments, version)
    zero = segments[0]["ts"]

    if at_epoch is not None and at_elapsed is not None:
        raise ExtractionError("at_elapsed 与 at_epoch 互斥，不可同时提供")
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
        "units": "counts" if raw_counts else "uV",
        "resolution_nV": res,
        "target": {"elapsed": at_elapsed, "epoch": target,
                   "offset_in_seg_s": offset},
        "requested_window": {"before": before, "after": after},
        "returned_window": {"start_s": s0 / fs, "end_s": s1 / fs,
                            "clipped": bool(miss_b or miss_a),
                            "missing_s": miss_b + miss_a},
        "leads": lead_out,
    }
