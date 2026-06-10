def main():
    import os
    import json
    import logging
    import jsonschema

    from epycon.core._validators import _validate_path
    from epycon.core.helpers import default_log_path, deep_override
    from epycon.cli import batch

    config_path = os.environ.get("EPYCON_CONFIG", os.path.join(os.path.dirname(__file__), 'config', 'config.json'))
    jsonschema_path = os.environ.get("EPYCON_JSONSCHEMA", os.path.join(
        os.path.dirname(__file__), 'config', 'schema.json'))

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
    # 转换语义的单一实现在 epycon/conversion.py（CLI 与 GUI 共用）
    from glob import iglob

    from epycon.config.byteschema import ENTRIES_FILENAME
    from epycon.iou import EntryPlanter, readentries
    from epycon.conversion import convert_study, resolve_subject

    input_folder = _validate_path(cfg["paths"]["input_folder"], name='input folder')
    output_folder = _validate_path(cfg["paths"]["output_folder"], name='output folder')
    valid_studies = set(cfg["paths"]["studies"])

    for study_path in iglob(os.path.join(input_folder, '**')):
        study_id = os.path.basename(study_path)

        if valid_studies and study_id not in valid_studies:
            continue

        out_dir = os.path.join(output_folder, study_id)
        try:
            os.makedirs(out_dir, exist_ok=True)
        except OSError:
            logger.error(f"Unable to create output folder {study_id} in {output_folder}.")
            continue

        # ----------------------- subject & entries -----------------------
        subject_id, subject_name = resolve_subject(study_path, cfg, logger=logger)

        # 标注既服务于导出 (entries.convert)，也服务于 H5 嵌入 (pin_entries)
        need_entries = cfg["entries"]["convert"] or (
            cfg["data"]["output_format"] == "h5" and cfg["data"]["pin_entries"]
        )
        entries = list()
        if need_entries:
            try:
                entries = readentries(
                    f_path=os.path.join(study_path, ENTRIES_FILENAME),
                    version=cfg["global_settings"]["workmate_version"],
                    )
            except OSError:
                logger.warning("Could not find ENTRIES log file. Annotation export will be skipped.")

        if cfg["entries"]["convert"] and cfg["entries"]["summary_csv"] and entries:
            # create summary csv containing all annotations
            criteria = {
                "fids": cfg["data"]["data_files"],
                "groups": cfg["entries"]["filter_annotation_type"],
                }
            EntryPlanter(entries).savecsv(
                os.path.join(out_dir, "entries_summary.csv"),
                criteria=criteria,
            )

        logger.info(f"Converting study {study_id}")
        convert_study(
            study_path, study_id, out_dir, cfg, entries,
            subject_id=subject_id, subject_name=subject_name, logger=logger,
        )
        print("DONE")


if __name__ == "__main__":
    main()
