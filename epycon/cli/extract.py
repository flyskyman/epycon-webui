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


def _meta_without_samples(result):
    meta = {k: v for k, v in result.items() if k != "leads"}
    meta["leads"] = [{k: v for k, v in ld.items() if k != "samples"}
                     for ld in result["leads"]]
    return meta


def _save_npz(path, result):
    arrays = {ld["name"]: np.asarray(ld["samples"])
              for ld in result["leads"] if ld["status"] == "ok"}
    meta = _meta_without_samples(result)
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
        meta = _meta_without_samples(result)
        meta["out"] = args.out
        print(json.dumps(meta, ensure_ascii=False))
    else:
        print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
