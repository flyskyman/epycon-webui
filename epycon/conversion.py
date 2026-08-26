"""共享转换核心：CLI (``python -m epycon``) 与 GUI (app_gui) 共用的单一实现。

此前两端各自维护平行的转换代码并已漂移出多个标注定位缺陷（墙钟偏移映射、
int 截断亚秒、字段名漂移、x32 时间戳误读等），故收敛到本模块。
任何转换语义的修改只允许发生在这里。
"""
import dataclasses
import logging
import os
from datetime import datetime, timedelta, timezone
from glob import iglob

from epycon.config.byteschema import MASTER_FILENAME, LOG_PATTERN
from epycon.core._formatting import _tocsv
from epycon.core.helpers import get_channel_mappings
from epycon.iou import (
    LogParser,
    EntryPlanter,
    CSVPlanter,
    HDFPlanter,
    mount_channels,
)
from epycon.iou.parsers import _PARSE_ERRORS, _readmaster
from epycon.utils.person import Tokenize

# 标注 CSV 的两种表头（绝对时间 / 相对时间），由 _tocsv 生成以保持单一来源；
# 用于识别 #21 改名前的旧标注文件，整行精确匹配，避免误删首列恰好同名的波形 CSV
_ENTRY_CSV_HEADERS = {_tocsv([], ref_timestamp=r).splitlines()[0] for r in (None, 0)}


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


def read_datalog_headers(datalogs, version, logger=None):
    """读 list_datalogs 结果里每个 DFile 的头，返回可读者的 (path, id, header, num_samples)。

    截断/不可读的 DFile（NAS 同步瞬态、残缺拷贝）是 study 的正常输入：这里是其
    「判定 + 排除 + 警告」的唯一实现（issue #40/#41）。reconcile_entries 与 convert_study
    都只消费本函数，坏文件在改判索引与波形/逐文件标注输出中被排除的是同一集合；
    只捕获解析器的预期异常，编程错误照常抛出。
    """
    readable = []
    for datalog_path, datalog_id in datalogs:
        try:
            with LogParser(datalog_path, version=version, samplesize=1024) as parser:
                header = parser.get_header()
                num_samples = parser.num_samples
        except _PARSE_ERRORS as exc:
            (logger or logging.getLogger(__name__)).warning(
                f"   ⚠️ {datalog_id}: header unreadable ({exc!r}), excluded")
            continue
        readable.append((datalog_path, datalog_id, header, num_samples))
    return readable


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


def record_date(timestamp, utc_offset_sec=None):
    """RecordDate 属性：采集机墙钟的 ISO 串。

    WorkMate 的 epoch 是墙钟按采集机 OS 时区解释的结果（issue #36：849 个 study 实测，
    一批机器为 US Central、另一批为 UTC+8），只有按该偏移格式化才还原操作者看到的
    时刻；偏移由 entries.log 头的 ASCII 墙钟推得（readentries_utc_offset）。没有偏移信息
    （无 entries.log、x32、合成夹具）时按分析机本地时间格式化——即此前的行为。
    """
    if not timestamp:
        return ""
    if utc_offset_sec is None:
        return datetime.fromtimestamp(timestamp).isoformat()
    return datetime.fromtimestamp(timestamp, timezone(timedelta(seconds=utc_offset_sec))).isoformat()


def reattribute_entries(entries, datalog_index, logger=None):
    """DFile 索引字段与 (时间戳, 采样索引) 矛盾时改判归属（issue #36）。

    849 个真实 study 里有 24 条（全是起搏协议行）0x02 指向的 DFile 与时间戳相差几十秒到
    几十分钟，而 时间戳+采样索引 一致地落在另一个 DFile 内，且那个 DFile 里没有同文本
    副本——按 fid 归属即丢失。两个独立字段一致优先于单个字段；只在唯一命中时改判。
    datalog_index: {fid: (start_sec, fs, num_samples)}；无 sample_index 的条目原样返回。
    """
    out = []
    for entry in entries:
        sidx = getattr(entry, "sample_index", None)
        own = datalog_index.get(str(entry.fid))
        if sidx is None or own is None or abs(round((entry.timestamp - own[0]) * own[1]) - sidx) <= 1:
            out.append(entry)
            continue
        hits = [fid for fid, (start, fs, n) in datalog_index.items()
                if 0 <= sidx < n and abs(round((entry.timestamp - start) * fs) - sidx) <= 1]
        if len(hits) != 1:
            out.append(entry)
            continue
        if logger:
            logger.warning(f"   ⚠️ Entry '{entry.message}' fid {entry.fid} → {hits[0]}: "
                           f"timestamp+sample_index agree on the other file (issue #36)")
        out.append(dataclasses.replace(entry, fid=hits[0]))
    return out


def reconcile_entries(study_path, entries, version, logger=None):
    """读完 entries.log 后立即调用：按 study 里**全部** DFile 头做 reattribute_entries。

    放在 convert_study 之外是因为 CLI/GUI 在转换前就已导出 entries_summary.csv，
    改判必须先于一切导出；索引取全部日志而非 data.data_files 过滤后的子集，否则被
    过滤掉的 fid 查不到"自身"就无法判定矛盾。
    """
    if not entries:
        return entries
    datalog_index = {
        datalog_id: (float(header.timestamp), header.amp.sampling_freq, num_samples)
        for _, datalog_id, header, num_samples
        in read_datalog_headers(list_datalogs(study_path), version, logger)
    }
    return reattribute_entries(entries, datalog_index, logger)


def entries_to_marks(entries, datalog_id, file_start_sec, fs, file_sample_count,
                     base_offset=0, logger=None):
    """把 fid 归属于该日志的 entries 换算为采样点标注 (position, group, message)。

    定位规则（两条转换路径的唯一权威实现）：
    - 归属以 fid 为准（与文件名匹配），不用时间窗猜测
    - 有符号偏移：早于文件起点为负，由下界拒绝；保留亚秒精度
    - round 取最近采样点：大数量级 epoch 时间戳相减存在浮点误差，
      int() 截断会系统性偏移一个采样点
    - entries.log 自带的 DFile 内采样索引（entry.sample_index）只作交叉校验：
      849 个真实 study 上与时间戳定位 ≤1 样本一致，偏差更大即告警（issue #36）
    """
    marks = []
    for entry in entries:
        if str(entry.fid) != str(datalog_id):
            continue
        offset_sec = float(entry.timestamp) - float(file_start_sec)
        local_pos = round(offset_sec * fs)
        if 0 <= local_pos < file_sample_count:
            marks.append((base_offset + local_pos, entry.group, entry.message))
            sample_index = getattr(entry, "sample_index", None)
            if logger and sample_index is not None and abs(sample_index - local_pos) > 1:
                logger.warning(
                    f"   ⚠️ {datalog_id}: Entry '{entry.message}' sample_index={sample_index} "
                    f"disagrees with timestamp position {local_pos} (issue #36)")
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
                    cfg, entries, base_attributes, logger, utc_offset_sec=None):
    """合并模式：一组同通道数的日志写入单个 HDF5，标注按合并时间轴落位。"""
    first_mappings = group_files[0]['mappings']
    merged_column_names = list(first_mappings.keys())
    first_timestamp = group_files[0]['timestamp']

    hdf_attributes = {
        **base_attributes,
        "datalog_ids": ",".join([d['id'] for d in group_files]),
        "Timestamp": first_timestamp,
        "RecordDate": record_date(first_timestamp, utc_offset_sec),
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
                    entryplanter, base_attributes, logger, utc_offset_sec=None):
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
            "RecordDate": record_date(ref_timestamp, utc_offset_sec),
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

    # 按文件导出标注（csv/sel）。波形已落盘：标注侧任何失败（清残留/导出）只显式
    # 报错，不回滚波形、不中断后续文件（issue #19）。先清上次运行的残留——导出被
    # 跳过或失败都不得留下旧标注冒充本次产物。
    if cfg["entries"]["convert"]:
        file_fmt = cfg["entries"]["output_format"]
        # 标注 CSV 命名 <fid>_entries.csv，与波形 CSV（<fid>.csv）区分——此前 csv+csv 时
        # 标注直接覆盖刚写好的波形（issue #21）。.sel 保持 <fid>.sel：SignalPlant 按文件名配对
        suffix = "_entries.csv" if file_fmt == "csv" else "." + file_fmt
        entry_path = os.path.join(out_dir, datalog_id + suffix)
        try:
            if os.path.exists(entry_path):
                os.remove(entry_path)
            # #21 改名前标注也叫 <fid>.csv，与旧波形 CSV 同名：首行整行匹配 _tocsv 表头
            # 才是标注，只删标注，旧波形 CSV 留着
            legacy = os.path.join(out_dir, datalog_id + ".csv")
            if legacy != full_output_path and os.path.exists(legacy):
                with open(legacy, encoding="utf-8") as f:
                    is_annotation = f.readline().rstrip("\r\n") in _ENTRY_CSV_HEADERS
                if is_annotation:
                    os.remove(legacy)
            if entries:
                criteria = {
                    "fids": [datalog_id],
                    "groups": cfg["entries"]["filter_annotation_type"],
                }
                if file_fmt == "csv":
                    entryplanter.savecsv(
                        entry_path, criteria=criteria, ref_timestamp=ref_timestamp,
                    )
                elif file_fmt == "sel":
                    entryplanter.savesel(
                        entry_path, ref_timestamp, fs, column_names, criteria=criteria,
                    )
        except Exception:
            (logger or logging.getLogger(__name__)).exception(
                f"   ❌ Entry export failed for {datalog_id}, waveform kept")
    return 1


def convert_study(study_path, study_id, out_dir, cfg, entries,
                  subject_id="", subject_name="", logger=None,
                  extra_attributes=None, utc_offset_sec=None):
    """转换单个 study：根据 cfg 选择合并/常规模式。返回处理的文件数。

    Args:
        entries: 标注对象列表（需具备 fid/timestamp/group/message 属性，
                 timestamp 为 unix 秒；CLI 传 readentries 原始结果，
                 GUI 传清洗后的 MutableEntry）
        extra_attributes: 额外并入 HDF5 根属性的字典（如 GUI 的 PatientName）
        utc_offset_sec: 采集机 OS 的 UTC 偏移（readentries_utc_offset()），
                 用于 RecordDate 还原墙钟；None 时按分析机本地时间（见 record_date）
    """
    valid_datalogs = set(
        strip_log_suffix(f) for f in cfg["data"]["data_files"]
    )
    all_datalogs = list_datalogs(study_path, valid_datalogs)
    if not all_datalogs:
        if logger:
            logger.warning(f"No valid datalog files found in {study_id}")
        return 0
    # 截断 DFile 的排除与 reconcile_entries 同源（issue #41）；全部不可读是失败，不是
    # "无事可做"——不得留下只有标注 CSV 的输出目录冒充成功
    datalogs = read_datalog_headers(
        all_datalogs, cfg["global_settings"]["workmate_version"], logger)
    if not datalogs:
        raise ValueError(
            f"{study_id}: all {len(all_datalogs)} datalog file(s) unreadable, nothing to convert")

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
        for datalog_path, datalog_id, header, num_samples in datalogs:
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
                'num_samples': num_samples,
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
                utc_offset_sec=utc_offset_sec,
            )
    else:
        entryplanter = EntryPlanter(entries)
        for datalog_path, datalog_id, _header, _num_samples in datalogs:
            if logger:
                logger.info(f"Converting {datalog_id}")
            processed += _convert_single(
                datalog_path, datalog_id, study_id, out_dir, cfg, entries,
                entryplanter, base_attributes, logger,
                utc_offset_sec=utc_offset_sec,
            )

    return processed
