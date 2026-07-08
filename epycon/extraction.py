"""按 WorkMate 流逝时刻从原始 .log 分段提取指定导联 ±窗口的原始波形。

设计文档：docs/superpowers/specs/2026-07-08-timestamp-lead-extraction-design.md
全程 epoch 纯相减、零时区；段归属半开 [ts, ts+dur)；fail-closed。
"""
import os

from epycon.config.byteschema import ENTRIES_FILENAME
from epycon.conversion import list_datalogs
from epycon.iou import LogParser, readentries


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
