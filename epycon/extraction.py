"""按 WorkMate 流逝时刻从原始 .log 分段提取指定导联 ±窗口的原始波形。

设计文档：docs/superpowers/specs/2026-07-08-timestamp-lead-extraction-design.md
全程 epoch 纯相减、零时区；段归属半开 [ts, ts+dur)；fail-closed。
"""
import os

import numpy as np

from epycon.config.byteschema import ENTRIES_FILENAME
from epycon.conversion import list_datalogs
from epycon.core.helpers import get_channel_mappings
from epycon.iou import LogParser, readentries

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
    return h * 3600 + m * 60 + s


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
    if col.size == 0:
        return False
    first = col[0]
    if not np.all(col == first):
        return False
    return int(first) in RAIL_VALUES


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
