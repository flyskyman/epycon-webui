"""共享转换核心：CLI (``python -m epycon``) 与 GUI (app_gui) 共用的单一实现。

此前两端各自维护平行的转换代码并已漂移出多个标注定位缺陷（墙钟偏移映射、
int 截断亚秒、字段名漂移、x32 时间戳误读等），故收敛到本模块。
任何转换语义的修改只允许发生在这里。
"""
import os
from datetime import datetime
from glob import iglob

from epycon.config.byteschema import MASTER_FILENAME, LOG_PATTERN
from epycon.core.helpers import get_channel_mappings
from epycon.iou import (
    LogParser,
    EntryPlanter,
    CSVPlanter,
    HDFPlanter,
    mount_channels,
)
from epycon.iou.parsers import _readmaster
from epycon.utils.person import Tokenize


def strip_log_suffix(name):
    """去掉 .log 后缀。不用 rstrip('.log')——那是字符集语义，会误伤 l/o/g 结尾的名字。"""
    return name[:-4] if name.endswith(".log") else name


def list_datalogs(study_path, valid_datalogs=None):
    """列出 study 目录内符合过滤条件的 (datalog_path, datalog_id)，按文件名排序。"""
    result = []
    for datalog_path in sorted(iglob(os.path.join(study_path, LOG_PATTERN))):
        datalog_id = strip_log_suffix(os.path.basename(datalog_path))
        if valid_datalogs and datalog_id not in valid_datalogs:
            continue
        result.append((datalog_path, datalog_id))
    return result


def resolve_subject(study_path, cfg, logger=None):
    """读取 MASTER 并按配置匿名化，返回 (subject_id, subject_name)。"""
    try:
        master_info = _readmaster(os.path.join(study_path, MASTER_FILENAME))
    except (IOError, FileNotFoundError):
        if logger:
            logger.warning(f"Could not find MASTER file in {study_path}. Subject info will be empty.")
        master_info = {"id": "", "name": ""}

    if cfg["global_settings"].get("pseudonymize", False):
        tokenizer = Tokenize(8, {})
        subject_id = tokenizer()
        if logger:
            logger.info(f"Pseudonymized subject: {master_info['id']} -> {subject_id}")
        return subject_id, ""
    return master_info["id"], master_info["name"]


def entries_to_marks(entries, datalog_id, file_start_sec, fs, file_sample_count,
                     base_offset=0, logger=None):
    """把 fid 归属于该日志的 entries 换算为采样点标注 (position, group, message)。

    定位规则（两条转换路径的唯一权威实现）：
    - 归属以 fid 为准（与文件名匹配），不用时间窗猜测
    - 有符号偏移：早于文件起点为负，由下界拒绝；保留亚秒精度
    - round 取最近采样点：大数量级 epoch 时间戳相减存在浮点误差，
      int() 截断会系统性偏移一个采样点
    """
    marks = []
    for entry in entries:
        if str(entry.fid) != str(datalog_id):
            continue
        offset_sec = float(entry.timestamp) - float(file_start_sec)
        local_pos = round(offset_sec * fs)
        if 0 <= local_pos < file_sample_count:
            marks.append((base_offset + local_pos, entry.group, entry.message))
        elif logger:
            file_duration = file_sample_count / fs if fs > 0 else 0
            logger.warning(
                f"   ⚠️ {datalog_id}: Entry '{entry.message}' at {offset_sec}s "
                f"outside file range [0, {file_duration}s], skipped.")
    return marks


def _planter_kwargs(cfg):
    """HDFPlanter 的压缩参数（GUI 配置可带 compression；CLI 配置缺省为 None）。"""
    return {
        "compression": cfg["data"].get("compression"),
        "compression_opts": cfg["data"].get("compression_opts"),
    }


def _convert_merged(group_files, group_channel_count, multi_group, study_id, out_dir,
                    cfg, entries, base_attributes, logger):
    """合并模式：一组同通道数的日志写入单个 HDF5，标注按合并时间轴落位。"""
    first_mappings = group_files[0]['mappings']
    merged_column_names = list(first_mappings.keys())
    first_timestamp = group_files[0]['timestamp']

    hdf_attributes = {
        **base_attributes,
        "datalog_ids": ",".join([d['id'] for d in group_files]),
        "Timestamp": first_timestamp,
        "RecordDate": datetime.fromtimestamp(first_timestamp).isoformat() if first_timestamp else "",
        "merged": True,
        "num_files": len(group_files),
        "sampling_freq": group_files[0]['header'].amp.sampling_freq,
        "num_channels": len(merged_column_names),
    }

    if multi_group:
        merged_output_path = os.path.join(out_dir, f"{study_id}_merged_{group_channel_count}ch.h5")
    else:
        merged_output_path = os.path.join(out_dir, f"{study_id}_merged.h5")

    is_first_file = True
    total_samples = 0
    accumulated_marks = []

    for idx, dlog_info in enumerate(group_files):
        datalog_path = dlog_info['path']
        datalog_id = dlog_info['id']
        header = dlog_info['header']
        fs = header.amp.sampling_freq
        file_start_sec = float(header.timestamp)

        if logger:
            logger.info(f"Merging {datalog_id} ({idx + 1}/{len(group_files)})")

        # 写入本文件前，记录其在合并时间轴上的样本偏移
        file_offset_samples = total_samples

        with LogParser(
            datalog_path,
            version=cfg["global_settings"]["workmate_version"],
            samplesize=cfg["global_settings"]["processing"]["chunk_size"],
        ) as parser:
            with HDFPlanter(
                merged_output_path,
                column_names=merged_column_names,
                sampling_freq=fs,
                factor=1000,
                units="uV",
                attributes=hdf_attributes if is_first_file else {},
                append=not is_first_file,
                **_planter_kwargs(cfg),
            ) as planter:
                file_sample_count = 0
                for chunk in parser:
                    chunk = mount_channels(chunk, dlog_info['mappings'])
                    planter.write(chunk)
                    file_sample_count += chunk.shape[0]
                    total_samples += chunk.shape[0]
                is_first_file = False

        if cfg["data"]["pin_entries"] and entries:
            accumulated_marks.extend(entries_to_marks(
                entries, datalog_id, file_start_sec, fs, file_sample_count,
                base_offset=file_offset_samples, logger=logger,
            ))

    if accumulated_marks and cfg["data"]["pin_entries"]:
        positions, groups, messages = zip(*accumulated_marks)
        with HDFPlanter(
            merged_output_path,
            column_names=merged_column_names,
            append=True,
        ) as marks_planter:
            marks_planter.add_marks(
                positions=list(positions),
                groups=list(groups),
                messages=list(messages),
            )
        if logger:
            logger.info(f"   ✅ Total {len(accumulated_marks)} entries injected into merged file")

    if logger:
        logger.info(f"Merged {len(group_files)} files into {merged_output_path} ({total_samples} total samples)")
    return len(group_files)


def _convert_single(datalog_path, datalog_id, study_id, out_dir, cfg, entries,
                    entryplanter, base_attributes, logger):
    """常规模式：单个日志输出 CSV/HDF5，并按配置嵌入标注、导出标注文件。"""
    output_fmt = cfg["data"]["output_format"]

    with LogParser(
        datalog_path,
        version=cfg["global_settings"]["workmate_version"],
        samplesize=cfg["global_settings"]["processing"]["chunk_size"],
    ) as parser:
        header = parser.get_header()
        ref_timestamp = header.timestamp
        fs = header.amp.sampling_freq

        mappings = get_channel_mappings(header, cfg)
        if cfg["data"]["channels"]:
            valid_channels = set(cfg["data"]["channels"])
            mappings = {key: value for key, value in mappings.items() if key in valid_channels}
        column_names = list(mappings.keys())

        if output_fmt == "csv":
            DataPlanter = CSVPlanter
        elif output_fmt == "h5":
            DataPlanter = HDFPlanter
        else:
            raise ValueError(f"Unsupported output format: {output_fmt}")

        full_output_path = os.path.join(out_dir, datalog_id + "." + output_fmt)

        hdf_attributes = {
            **base_attributes,
            "LogID": datalog_id,
            "sampling_freq": fs,
            "num_channels": len(column_names),
            "Timestamp": ref_timestamp,
            "RecordDate": datetime.fromtimestamp(ref_timestamp).isoformat() if ref_timestamp else "",
        }

        planter_kwargs = _planter_kwargs(cfg) if output_fmt == "h5" else {}
        with DataPlanter(
            f_path=full_output_path,
            column_names=column_names,
            sampling_freq=fs,
            factor=1000,
            units="uV",
            attributes=hdf_attributes if output_fmt == "h5" else {},
            **planter_kwargs,
        ) as planter:
            num_samples_written = 0
            for chunk in parser:
                chunk = mount_channels(chunk, mappings)
                planter.write(chunk)
                num_samples_written += chunk.shape[0]

            if cfg["data"]["pin_entries"] and entries and hasattr(planter, "add_marks"):
                valid_marks = entries_to_marks(
                    entries, datalog_id, ref_timestamp, fs, num_samples_written,
                    logger=logger,
                )
                if valid_marks:
                    positions, groups, messages = zip(*valid_marks)
                    planter.add_marks(
                        positions=list(positions),
                        groups=list(groups),
                        messages=list(messages),
                    )
                    if logger:
                        logger.info(f"   ✅ Injected {len(valid_marks)} entries for {datalog_id}")
                elif logger:
                    logger.info(f"   ℹ️ No valid entries to inject for {datalog_id}")

    # 按文件导出标注（csv/sel）
    if cfg["entries"]["convert"] and entries:
        criteria = {
            "fids": [datalog_id],
            "groups": cfg["entries"]["filter_annotation_type"],
        }
        file_fmt = cfg["entries"]["output_format"]
        try:
            if file_fmt == "csv":
                entryplanter.savecsv(
                    os.path.join(out_dir, datalog_id + "." + file_fmt),
                    criteria=criteria,
                    ref_timestamp=ref_timestamp,
                )
            elif file_fmt == "sel":
                entryplanter.savesel(
                    os.path.join(out_dir, datalog_id + "." + file_fmt),
                    ref_timestamp,
                    fs,
                    column_names,
                    criteria=criteria,
                )
        except Exception as e:
            if logger:
                logger.error(f"   ❌ Error exporting entry file for {datalog_id}: {e}")
    return 1


def convert_study(study_path, study_id, out_dir, cfg, entries,
                  subject_id="", subject_name="", logger=None,
                  extra_attributes=None):
    """转换单个 study：根据 cfg 选择合并/常规模式。返回处理的文件数。

    Args:
        entries: 标注对象列表（需具备 fid/timestamp/group/message 属性，
                 timestamp 为 unix 秒；CLI 传 readentries 原始结果，
                 GUI 传清洗后的 MutableEntry）
        extra_attributes: 额外并入 HDF5 根属性的字典（如 GUI 的 PatientName）
    """
    valid_datalogs = set(
        strip_log_suffix(f) for f in cfg["data"]["data_files"]
    )
    all_datalogs = list_datalogs(study_path, valid_datalogs)
    if not all_datalogs:
        if logger:
            logger.warning(f"No valid datalog files found in {study_id}")
        return 0

    os.makedirs(out_dir, exist_ok=True)

    base_attributes = {
        "subject_id": subject_id,
        "subject_name": subject_name,
        "study_id": study_id,
    }
    credentials = cfg["global_settings"].get("credentials", {})
    if credentials:
        base_attributes.update({
            "author": credentials.get("author", ""),
            "device": credentials.get("device", ""),
            "owner": credentials.get("owner", ""),
        })
    base_attributes.update(extra_attributes or {})

    merge_mode = cfg["data"].get("merge_logs", False)
    output_fmt = cfg["data"]["output_format"]
    processed = 0

    if merge_mode and output_fmt == "h5":
        # 读取所有文件头，按时间排序并按通道数分组
        from collections import defaultdict

        datalog_info = []
        for datalog_path, datalog_id in all_datalogs:
            with LogParser(
                datalog_path,
                version=cfg["global_settings"]["workmate_version"],
                samplesize=1024,
            ) as parser:
                header = parser.get_header()
                if header is None:
                    if logger:
                        logger.warning(f"⚠️ Cannot read header: {datalog_id}.log, skipping")
                    continue

                file_mappings = get_channel_mappings(header, cfg)
                if cfg["data"]["channels"]:
                    valid_channels = set(cfg["data"]["channels"])
                    file_mappings = {k: v for k, v in file_mappings.items() if k in valid_channels}

                datalog_info.append({
                    'path': datalog_path,
                    'id': datalog_id,
                    'timestamp': header.timestamp,
                    'header': header,
                    'mappings': file_mappings,
                    'num_output_channels': len(file_mappings),
                    'num_samples': parser.num_samples,
                })

        datalog_info.sort(key=lambda x: x['timestamp'])

        channel_groups = defaultdict(list)
        for d in datalog_info:
            channel_groups[d['num_output_channels']].append(d)

        if logger:
            logger.info(f"Merge mode: {len(datalog_info)} files total, {len(channel_groups)} channel group(s)")
            if len(channel_groups) > 1:
                logger.warning("⚠️ Multiple channel counts detected, will create separate merged files:")
                for num_ch, files in channel_groups.items():
                    logger.warning(f"   {num_ch} channels: {len(files)} file(s)")

        for group_channel_count, group_files in channel_groups.items():
            processed += _convert_merged(
                group_files, group_channel_count, len(channel_groups) > 1,
                study_id, out_dir, cfg, entries, base_attributes, logger,
            )
    else:
        entryplanter = EntryPlanter(entries)
        for datalog_path, datalog_id in all_datalogs:
            if logger:
                logger.info(f"Converting {datalog_id}")
            processed += _convert_single(
                datalog_path, datalog_id, study_id, out_dir, cfg, entries,
                entryplanter, base_attributes, logger,
            )

    return processed
