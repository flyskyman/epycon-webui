import os
import json
from epycon.iou.parsers import LogParser
from epycon.core._dataclasses import Channels


def get_mappings(parser, cfg):
    header = parser.get_header()
    if header is None:
        return None, None

    if cfg["data"]["leads"] == "computed":
        if isinstance(header.channels, Channels):
            mappings = header.channels.computed_mappings
        else:
            mappings = {f"ch{i}": [i] for i in range(header.num_channels)}
    else:
        if isinstance(header.channels, Channels):
            mappings = header.channels.raw_mappings
        else:
            mappings = {f"ch{i}": [i] for i in range(header.num_channels)}

    if cfg["data"]["channels"]:
        mappings = {k: v for k, v in mappings.items() if k in cfg["data"]["channels"]}

    return header, mappings


def analyze_patient_diff(base_dir, patient_id, cfg):
    patient_dir = os.path.join(base_dir, patient_id)
    log_files = sorted([f for f in os.listdir(patient_dir) if f.endswith('.log') and f.startswith('0')])
    if not log_files:
        print(f"未找到日志文件: {patient_dir}")
        return

    base_file = log_files[0]
    base_path = os.path.join(patient_dir, base_file)

    with LogParser(base_path, version=cfg["global_settings"]["workmate_version"], samplesize=1024) as parser:
        base_header, base_mappings = get_mappings(parser, cfg)

    if base_mappings is None:
        print(f"无法读取基准文件: {base_file}")
        return

    print(f"患者: {patient_id}")
    print(f"基准文件: {base_file}")
    print(f"基准输出通道数: {len(base_mappings)}")
    print("-" * 80)

    for log_file in log_files[1:]:
        log_path = os.path.join(patient_dir, log_file)
        with LogParser(log_path, version=cfg["global_settings"]["workmate_version"], samplesize=1024) as parser:
            _, mappings = get_mappings(parser, cfg)

        if mappings is None:
            print(f"  {log_file}: 无法读取")
            continue

        base_only = sorted(set(base_mappings.keys()) - set(mappings.keys()))
        other_only = sorted(set(mappings.keys()) - set(base_mappings.keys()))

        if not base_only and not other_only:
            print(f"  {log_file}: 映射一致")
            continue

        print(f"  {log_file}:")
        if base_only:
            print(f"    基准多出的通道 ({len(base_only)}):")
            for name in base_only:
                print(f"      {name}: {base_mappings[name]}")
        if other_only:
            print(f"    当前文件多出的通道 ({len(other_only)}):")
            for name in other_only:
                print(f"      {name}: {mappings[name]}")


if __name__ == "__main__":
    with open(r"test_backup_config.json", "r", encoding="utf-8") as f:
        cfg = json.load(f)

    base_dir = cfg["paths"]["input_folder"].replace("/", "\\")
    patient_id = "LOG_DHR51337676_0000067d"

    analyze_patient_diff(base_dir, patient_id, cfg)
