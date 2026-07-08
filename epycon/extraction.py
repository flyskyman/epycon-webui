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
