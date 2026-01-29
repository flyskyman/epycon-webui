if __name__ == "__main__":
    import os
    import sys
    import json
    import logging
    import jsonschema

    from epycon.core._validators import _validate_path
    from epycon.core.helpers import default_log_path, deep_override, difftimestamp
    from epycon.cli import batch

    config_path = os.environ.get("EPYCON_CONFIG", os.path.join(os.path.dirname(__file__), 'config', 'config.json'))
    jsonschema_path = os.environ.get("EPYCON_JSONSCHEMA", os.path.join(os.path.dirname(__file__), 'config', 'schema.json'))

    # Instantiate basic logger
    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        filename=default_log_path(),
        filemode="w",
    )
    logger = logging.getLogger(__name__)
    logger.addHandler(handler)
    
    # Parse CLI arguments
    args = batch.parse_arguments()
    
    # Validate custom config path if provided
    if args.custom_config_path:        
        config_path = _validate_path(args.custom_config_path)

       
    # Load JSON configuration
    try:
        with open(config_path, "r") as f:
            cfg = json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    # Override config with custom CLI arguments if provided        
    overrides = {
        "paths.input_folder": args.input_folder,
        "paths.output_folder": args.output_folder,
        "paths.studies": args.studies,
        "data.output_format": args.output_format,
        "data.merge_logs": True if (hasattr(args, 'merge') and args.merge) else None,
        "entries.convert": args.entries,
        "entries.output_format": args.entries_format,
        }
    
    for arg, value in overrides.items():        
        if value is not None:            
            cfg = deep_override(cfg, arg.split("."), value)            


    # Load and validate jsonschema
    try:
        with open(jsonschema_path, "r") as f:
            schema = json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"Config file not found: {jsonschema_path}")
            
    try:
        jsonschema.validate(cfg, schema)
    except jsonschema.ValidationError as e:
        raise ValueError(f"Invalid config: {e}")
    

    # ----------------------- batch conversion ----------------------
    from glob import iglob

    from epycon.config.byteschema import (
        ENTRIES_FILENAME, LOG_PATTERN, MASTER_FILENAME
    )

    from epycon.iou import (
        LogParser,
        EntryPlanter,
        CSVPlanter,
        HDFPlanter,
        readentries,
        mount_channels,
    )

    from epycon.iou.parsers import _readmaster
    from epycon.utils.person import Tokenize
    from datetime import datetime

    def _get_channel_mappings(header, cfg):
        """获取通道映射，正确处理不同的 channels 类型"""
        if hasattr(header.channels, 'add_custom_mount'):
            # ChannelCollection 对象
            header.channels.add_custom_mount(cfg["data"]["custom_channels"], override=False)
            if cfg["data"]["leads"] == "computed":
                return header.channels.computed_mappings
            else:
                return header.channels.raw_mappings
        elif isinstance(header.channels, list) and header.channels:
            # 简单 list，每个元素是 Channel 对象（有 name 和 reference 属性）
            # reference 是实际数据列的索引
            mappings = {}
            for ch in header.channels:
                if hasattr(ch, 'name') and hasattr(ch, 'reference'):
                    # Channel 对象：使用 reference 作为数据列索引
                    # 只包含 reference 在有效范围内的通道
                    if ch.reference < header.num_channels:
                        mappings[ch.name] = [ch.reference]
                elif hasattr(ch, 'name'):
                    # 只有 name 没有 reference，跳过或使用默认
                    pass
                elif isinstance(ch, str):
                    # 字符串通道名，使用索引（legacy 支持）
                    idx = list(header.channels).index(ch)
                    if idx < header.num_channels:
                        mappings[ch] = [idx]
            return mappings if mappings else {f"ch{i}": [i] for i in range(header.num_channels)}
        else:
            # fallback: 使用默认名称
            return {f"ch{i}": [i] for i in range(header.num_channels)} if header.num_channels > 0 else {"ch0": [0]}

    input_folder = _validate_path(cfg["paths"]["input_folder"], name='input folder')
    output_folder = _validate_path(cfg["paths"]["output_folder"], name='output folder')
    valid_studies = set(cfg["paths"]["studies"])
    # Normalize data_files: strip .log extension if present for consistent comparison
    valid_datalogs = set(f.rstrip(".log") if f.endswith(".log") else f for f in cfg["data"]["data_files"])
    output_fmt = cfg["data"]["output_format"]

    for study_path in iglob(os.path.join(input_folder, '**')):
        study_id = os.path.basename(study_path)

        if valid_studies and study_id not in valid_studies:            
            continue
        
        try:
            # make output directory
            os.makedirs(os.path.join(output_folder, study_id), exist_ok=True)
        except OSError as e:
            logger.error(f"Unable to create output folder {study_id} in {output_folder}.")
            continue

        # ----------------------- read MASTER file -----------------------
        try:
            master_info = _readmaster(os.path.join(study_path, MASTER_FILENAME))
        except (IOError, FileNotFoundError):
            logger.warning(f"Could not find MASTER file in {study_id}. Subject info will be empty.")
            master_info = {"id": "", "name": ""}

        # handle pseudonymization
        if cfg["global_settings"].get("pseudonymize", False):
            tokenizer = Tokenize(8, {})
            subject_id = tokenizer()
            subject_name = ""
            logger.info(f"Pseudonymized subject: {master_info['id']} -> {subject_id}")
        else:
            subject_id = master_info["id"]
            subject_name = master_info["name"]
    
        # read entries
        if cfg["entries"]["convert"]:
            try:
                entries = readentries(
                    f_path=os.path.join(study_path, ENTRIES_FILENAME),
                    version=cfg["global_settings"]["workmate_version"],
                    )
            except OSError as e:                
                logger.warning(f"Could not find ENTRIES log file. Annotation export will be skipped.")
                entries = list()
        else:
            entries = list()
        
        entryplanter = EntryPlanter(entries)

        if cfg["entries"]["summary_csv"] and entries:
            # create summary csv containing all annotations
            criteria = {
                "fids": cfg["data"]["data_files"],
                "groups": cfg["entries"]["filter_annotation_type"],
                }
            
            entryplanter.savecsv(
                os.path.join(output_folder, study_id, "entries_summary.csv"),                                
                criteria=criteria,
            )

        # Get merge mode setting
        merge_mode = cfg["data"].get("merge_logs", False)
        
        # Collect all valid datalog paths
        all_datalogs = []
        for datalog_path in iglob(os.path.join(study_path, LOG_PATTERN)):
            datalog_id = os.path.basename(datalog_path).rstrip(".log")
            if valid_datalogs and datalog_id not in valid_datalogs:
                continue
            all_datalogs.append((datalog_path, datalog_id))
        
        if not all_datalogs:
            logger.warning(f"No valid datalog files found in {study_id}")
            continue

        # iterate over datalog files
        logger.info(f"Converting study {study_id}")
        
        if merge_mode and output_fmt == "h5":
            # ===================== MERGE MODE =====================
            # Sort datalogs by timestamp and collect channel info
            from collections import defaultdict
            from epycon.core._dataclasses import Channels
            
            datalog_info = []
            for datalog_path, datalog_id in all_datalogs:
                with LogParser(
                    datalog_path,
                    version=cfg["global_settings"]["workmate_version"],
                    samplesize=1024,
                ) as parser:
                    header = parser.get_header()
                    if header is None:
                        logger.warning(f"⚠️ Cannot read header: {datalog_id}.log, skipping")
                        continue
                    
                    # Get channel mappings for this file
                    file_mappings = _get_channel_mappings(header, cfg)
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
                    })
            
            # Sort by timestamp
            datalog_info.sort(key=lambda x: x['timestamp'])
            
            # Group by channel count to handle heterogeneous data
            channel_groups = defaultdict(list)
            for d in datalog_info:
                channel_groups[d['num_output_channels']].append(d)
            
            logger.info(f"Merge mode: {len(datalog_info)} files total, {len(channel_groups)} channel group(s)")
            
            if len(channel_groups) > 1:
                logger.warning(f"⚠️ Multiple channel counts detected, will create separate merged files:")
                for num_ch, files in channel_groups.items():
                    logger.warning(f"   {num_ch} channels: {len(files)} file(s)")
            
            # Process each channel group separately
            for group_channel_count, group_files in channel_groups.items():
                logger.info(f"\n📦 Processing channel group: {group_channel_count} channels, {len(group_files)} file(s)")
                
                # Use first file's mappings as template for this group
                first_mappings = group_files[0]['mappings']
                merged_column_names = list(first_mappings.keys())
                first_timestamp = group_files[0]['timestamp']
                
                # Build metadata for merged file
                hdf_attributes = {
                    "subject_id": subject_id,
                    "subject_name": subject_name,
                    "study_id": study_id,
                    "datalog_ids": ",".join([d['id'] for d in group_files]),
                    "timestamp": first_timestamp,
                    "datetime": datetime.fromtimestamp(first_timestamp).isoformat() if first_timestamp else "",
                    "merged": True,
                    "num_files": len(group_files),
                }
                
                credentials = cfg["global_settings"].get("credentials", {})
                if credentials:
                    hdf_attributes.update({
                        "author": credentials.get("author", ""),
                        "device": credentials.get("device", ""),
                        "owner": credentials.get("owner", ""),
                    })
                
                # Determine output filename
                if len(channel_groups) > 1:
                    merged_output_path = os.path.join(output_folder, study_id, f"{study_id}_merged_{group_channel_count}ch.h5")
                else:
                    merged_output_path = os.path.join(output_folder, study_id, f"{study_id}_merged.h5")
                
                # Process each file and append to merged output
                is_first_file = True
                total_samples = 0
                group_start_time = group_files[0]['timestamp']
                
                for idx, dlog_info in enumerate(group_files):
                    datalog_path = dlog_info['path']
                    datalog_id = dlog_info['id']
                    header = dlog_info['header']
                    file_mappings = dlog_info['mappings']
                    
                    print(f"Merging {datalog_id} ({idx+1}/{len(group_files)}): ", end="")
                    
                    # Calculate file time range for entries filtering
                    file_start_sec = float(header.timestamp)
                    file_size = os.path.getsize(datalog_path)
                    n_channels = header.num_channels
                    fs = header.amp.sampling_freq
                    
                    if n_channels > 0 and fs > 0:
                        n_samples = (file_size - 32) // (n_channels * 2)
                        file_duration_sec = n_samples / fs
                    else:
                        file_duration_sec = 0
                    file_end_sec = file_start_sec + file_duration_sec
                    
                    # Filter entries by fid (precise match), then validate time range
                    if entries:
                        # Primary filter: match by fid (datalog file ID)
                        file_entries = [e for e in entries if e.fid == datalog_id]
                        
                        # Validate time range and warn if significantly out of range
                        validated_entries = []
                        for e in file_entries:
                            time_diff = abs(e.timestamp - (file_start_sec + file_end_sec) / 2)
                            max_acceptable_diff = file_duration_sec / 2 + 300  # Half duration + 5min tolerance
                            
                            if time_diff <= max_acceptable_diff:
                                validated_entries.append(e)
                            else:
                                logger.warning(f"   ⚠️ Entry timestamp significantly out of range for {datalog_id}: {e.timestamp:.2f} (expected: {file_start_sec:.2f}-{file_end_sec:.2f})")
                        
                        file_entries = validated_entries
                    else:
                        file_entries = []
                    
                    with LogParser(
                        datalog_path,
                        version=cfg["global_settings"]["workmate_version"],
                        samplesize=cfg["global_settings"]["processing"]["chunk_size"],
                    ) as parser:
                        # Update attributes with sampling info from first file
                        if is_first_file:
                            hdf_attributes["sampling_freq"] = header.amp.sampling_freq
                            hdf_attributes["num_channels"] = len(merged_column_names)
                        # Open planter with unified column names for this group
                        with HDFPlanter(
                            merged_output_path,
                            column_names=merged_column_names,
                            sampling_freq=header.amp.sampling_freq,
                            factor=1000,
                            units="mV",
                            attributes=hdf_attributes if is_first_file else {},
                            append=not is_first_file,
                        ) as planter:
                            file_sample_count = 0
                            # Write data chunks
                            for chunk in parser:
                                chunk = mount_channels(chunk, file_mappings)
                                planter.write(chunk)
                                file_sample_count += chunk.shape[0]
                                total_samples += chunk.shape[0]
                            
                            # Inject entries for this specific file
                            if cfg["data"]["pin_entries"] and file_entries and hasattr(planter, "add_marks"):
                                # Calculate global positions for this file's entries
                                global_base = total_samples - file_sample_count
                                file_end_global = global_base + file_sample_count
                                
                                valid_marks = []
                                for e in file_entries:
                                    # Calculate relative position from file start
                                    relative_pos = round((e.timestamp - file_start_sec) * fs)
                                    global_pos = global_base + relative_pos
                                    
                                    # Clamp position to valid range (handles minor timestamp inaccuracies)
                                    if global_pos < global_base:
                                        logger.debug(f"   Entry position {global_pos} < {global_base}, clamping to file start")
                                        global_pos = global_base
                                    elif global_pos >= file_end_global:
                                        logger.debug(f"   Entry position {global_pos} >= {file_end_global}, clamping to file end-1")
                                        global_pos = file_end_global - 1
                                    
                                    valid_marks.append((global_pos, str(e.group), str(e.message)))
                                
                                if valid_marks:
                                    positions, groups, messages = zip(*valid_marks)
                                    planter.add_marks(
                                        positions=list(positions),
                                        groups=list(groups),
                                        messages=list(messages),
                                    )
                                    logger.info(f"   ✅ Injected {len(valid_marks)} entries for {datalog_id}")
                                elif file_entries:
                                    logger.warning(f"   ⚠️ {datalog_id}: {len(file_entries)} entries matched by fid but all had invalid positions")
                            
                            is_first_file = False
                            print("OK")
                
                logger.info(f"Merged {len(group_files)} files into {merged_output_path} ({total_samples} total samples)")
                print(f"DONE (merged {len(group_files)} files)")
        
        else:
            # ===================== NORMAL MODE (per-file) =====================
            for datalog_path, datalog_id in all_datalogs:

                # open parser contex manager
                print(f"Converting {datalog_id}: ", end="")
                with LogParser(
                    datalog_path,
                    version=cfg["global_settings"]["workmate_version"],                
                    samplesize=cfg["global_settings"]["processing"]["chunk_size"],
                ) as parser:
                    # get datalog header
                    header = parser.get_header()
                    ref_timestamp = header.timestamp

                    # create channel mappings
                    mappings = _get_channel_mappings(header, cfg)

                    # filter out channels not specified by user from mappings
                    if cfg["data"]["channels"]:
                        valid_channels = set(cfg["data"]["channels"])
                        mappings = {key: value for key, value in mappings.items() if key in valid_channels}

                    # instantiate planter and write data chunks
                    column_names = list(mappings.keys())

                    if output_fmt == "csv":
                        DataPlanter = CSVPlanter
                    elif output_fmt == "h5":                    
                        DataPlanter = HDFPlanter
                    else:
                        raise ValueError
                    
                    # build metadata attributes for HDF5
                    hdf_attributes = {
                        "subject_id": subject_id,
                        "subject_name": subject_name,
                        "study_id": study_id,
                        "datalog_id": datalog_id,
                        "timestamp": ref_timestamp,
                        "datetime": datetime.fromtimestamp(ref_timestamp).isoformat(),
                        "sampling_freq": header.amp.sampling_freq,
                        "num_channels": header.num_channels,
                    }
                    
                    # add credentials if available
                    credentials = cfg["global_settings"].get("credentials", {})
                    if credentials:
                        hdf_attributes.update({
                            "author": credentials.get("author", ""),
                            "device": credentials.get("device", ""),
                            "owner": credentials.get("owner", ""),
                        })

                    # instantiate planter with coversion factor for HDF of 1000 -> uV to mV
                    with DataPlanter(
                        os.path.join(output_folder, study_id, datalog_id + "." + output_fmt),
                        column_names=column_names,
                        sampling_freq=header.amp.sampling_freq,
                        factor=1000,
                        units="mV",
                        attributes=hdf_attributes,
                    ) as planter:
                        # iterate over chunks of data and write to disk
                        for chunk in parser:                        
                            # compute leads                        
                            chunk = mount_channels(chunk, mappings)                                                
                            planter.write(chunk)

                        # write entries to hdf file
                        if cfg["data"]["pin_entries"] and hasattr(planter, "add_marks"):
                            # convert timestamps -> datetimediff -> samples
                            if entries:
                                try:
                                    groups, positions, messages = zip(
                                        *[(
                                            e.group,
                                            header.amp.sampling_freq*difftimestamp((e.timestamp, ref_timestamp)),
                                            e.message,
                                        ) for e in entries if e.fid == datalog_id
                                        ])
                                    # write marks
                                    planter.add_marks(
                                        positions=positions,
                                        groups=groups,
                                        messages=messages,
                                    )
                                except ValueError:
                                    pass  # No matching entries
                
                # convert and store entries | csv or sel per each file            
                if cfg["entries"]["convert"] and entries:                
                    criteria = {
                        "fids": [datalog_id],
                        "groups": cfg["entries"]["filter_annotation_type"],
                    }                
                    file_fmt = cfg["entries"]["output_format"]
                    
                    if file_fmt == "csv":
                        # store as .csv file
                        entryplanter.savecsv(
                            os.path.join(output_folder, study_id, datalog_id + "." + file_fmt),
                            criteria=criteria,
                            ref_timestamp=ref_timestamp,
                        )
                    elif file_fmt == "sel":
                        # store as SignalPlant .sel text file
                        entryplanter.savesel(
                            os.path.join(output_folder, study_id, datalog_id + "." + file_fmt),
                            ref_timestamp,
                            header.amp.sampling_freq,
                            list(mappings.keys()),
                            criteria=criteria,                        
                        )
                    else:
                        pass

                print(f"DONE")

