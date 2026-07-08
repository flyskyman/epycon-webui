"""按 WorkMate 流逝时刻从原始 .log 分段提取指定导联 ±窗口的原始波形。

设计文档：docs/superpowers/specs/2026-07-08-timestamp-lead-extraction-design.md
全程 epoch 纯相减、零时区；段归属半开 [ts, ts+dur)；fail-closed。
"""
from epycon.conversion import list_datalogs
from epycon.iou import LogParser


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
