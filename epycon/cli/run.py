import os
import json
import argparse
import logging
import jsonschema
from typing import cast, Any

from ..iou.parsers import (
    LogParser,
    _readheader,
    _readdata,
    _readentries,
)


from ..iou.planters import (
    HDFPlanter,
)

from ..core.helpers import (
    default_log_path,
    difftimestamp
)

from ..core._validators import (
    _validate_path,
)


import numpy as np

logger = logging.getLogger(__name__)

# Schema will be loaded inside main block

if __name__ == '__main__':
    config_path = os.environ.get("EPYCON_CONFIG", os.path.join(os.path.dirname(__file__), 'config', 'config.json'))
    jsonschema_path = os.environ.get("EPYCON_JSONSCHEMA", os.path.join(os.path.dirname(__file__), 'config', 'schema.json'))
    
    # Instantiate basic logger
    from ..core.helpers import default_log_path as get_default_log_path
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        filename=get_default_log_path(),
    )
    
    # Load jsonschema
    try:
        with open(jsonschema_path, "r") as f:
            schema = json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"Config file not found: {jsonschema_path}")

    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input_folder", type=str,)
    parser.add_argument("-o", "--output_folder", type=str,)
    parser.add_argument("-s", "--studies", type=list,)

    parser.add_argument("-fmt", "--output_format", type=str, choices=['csv', 'hdf'])
    
    parser.add_argument("-e", "--entries", type=bool,)
    parser.add_argument("-efmt", "--entries_format", type=str, choices=['csv', 'sel'])

    parser.add_argument("--custom-config-path", type=str, help="Path to configuration file")

    args = parser.parse_args()

    # Validate custom config path if provided
    if args.config_file:
        _validate_path(args.config_file)

    config_path = args.config_path if args.config_path else config_path

    # Load JSON configuration if provided
    try:
        with open(config_path, "r") as f:
            cfg = json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"Config file not found: {config_path}")

    config = {**cfg, **vars(parser.parse_args())}

    # Override arguments from command line interface if provided
    overrides = {"arg1": args.arg1, "arg2": args.arg2}
    for arg, value in overrides.items():
        if value is not None:
            config[arg] = value

    # Validate the config
    try:
        jsonschema.validate(config, schema)
    except jsonschema.ValidationError as e:
        raise ValueError(f"Invalid config: {e}")


    import time
    from glob import glob
    from epycon.iou.planters import HDFPlantercinc
    
    # 可选的 scipy 导入（仅用于加速度数据处理）
    try:
        from scipy.signal import filtfilt, butter
        # 设计一个低通滤波器用于加速度数据处理
        fs_filter = 2000  # 采样频率
        fc = 50    # 截止频率
        order = 4  # 滤波器阶数
        b, a = butter(order, fc / (fs_filter / 2), btype='low')
        HAS_SCIPY = True
    except ImportError:
        HAS_SCIPY = False
        filtfilt = None  # type: ignore
        b, a = None, None  # type: ignore
    
    # path = r'C:\Users\jakub\Research\Data\WorkMate'
    # out_path = r'C:\Users\jakub\Research\Data\WorkMate_export'
    
    path = '/backup/data/VuVeL/WorkMate'
    out_path = '/backup/data/VuVeL/WorkMate_export'

    res: dict[int, dict[int, list[float]]] = {
        40: {480: [], 240: [], 120: [], 60: [], 30: []},
        20: {480: [], 240: [], 120: [], 60: [], 30: []},
        10: {480: [], 240: [], 120: [], 60: [], 30: []},
    }
    stat: dict[str, list[Any]] = {
        'fold_id': [],
        'size_orig': [],
        'size_h5': [],
        'size_h5gzip': [],
        'size_csv': [],
        'time_h5': [],
        'time_h5gzip': [],
        'time_csv': [],
        'time_marks': [],
        'time_header': [],
    }

    foldid_list = []
    for folder in glob(os.path.join(path, '**')):
        start = time.time()

        logfiles = glob(os.path.join(path, folder, '0*.log'))
        fold_id = os.path.basename(folder)

        try:
            os.makedirs(os.path.join(out_path, fold_id))
        except FileExistsError:            
            pass

        entryparser = EpParser(folder)
        marks = entryparser.read_entries()
        t_marks = time.time() - start

        
        for logfile in logfiles:
            print(logfile)
            foldid_list.append(fold_id)
            
            size_orig = os.path.getsize(logfile)
            
            start = time.time()
            file_id = os.path.basename(logfile).split('.')[0]
            header = _readheader(logfile)            
            data = cast(np.ndarray, _readdata(logfile, version='4.2', mount=False))
                        
            # planter = HDFPlanter(f_path=r'C:\Users\jakub\Research\Codes\Python\epycon\data\Pigs_export\27-15\00000000.h5')
            #
            #
            # ---------------- read header ---------------
            #
            # 
            if file_id in marks:        
                temp = [(item.group, _samplefromtimestamp([item.timestamp, header.timestamp], 2000), item.message) for item in marks[file_id].content]
                group, start_sample, info = list(zip(*temp))        
            else:
                group = ()
                start_sample = ()
                info = ()
            
            t_header = time.time() - start
            

            #
            #
            # ---------------- create hdf with no compression ---------------
            #
            # 
            start = time.time()
            planter = HDFPlanter(f_path=os.path.join(out_path, fold_id, file_id + '.h5'))
            with planter:
                planter.create(
                    data,
                    # chnames=[ch.name for ch in header.mount],
                    chnames=None,
                    sampling_freq=header.amp.sampling_freq,
                    compression=None,
                )

                planter.addmark(
                    startsample=start_sample,
                    endsample=start_sample,
                    info=info,
                    group=group,
                )

            t_h5 = time.time() - start            
            size_h5 = os.path.getsize(os.path.join(out_path, fold_id, file_id + '.h5'))

            try:
                os.remove(os.path.join(out_path, fold_id, file_id + '.h5'))
            except OSError:
                pass



            #
            #
            # ---------------- create hdf with gzip compression ---------------
            #
            # 

            start = time.time()
            planter = HDFPlanter(f_path=os.path.join(out_path, fold_id, file_id + '_gzip.h5'))
            with planter:
                planter.create(
                    data,
                    # chnames=[ch.name for ch in header.mount],
                    chnames=None,
                    sampling_freq=header.amp.sampling_freq,
                    compression=None,
                )

                planter.addmark(
                    startsample=start_sample,
                    endsample=start_sample,
                    info=info,
                    group=group,
                )


            t_h5gzip = time.time() - start
            size_h5gzip = os.path.getsize(os.path.join(out_path, fold_id, file_id + '_gzip.h5'))

            try:
                os.remove(os.path.join(out_path, fold_id, file_id + '_gzip.h5'))
            except OSError:
                pass

            #
            #
            # ---------------- create csv  ---------------
            #
            #          
            csv_data = np.transpose(data).astype(np.int32)
            start = time.time()
            _tocsv(                
                f_path=os.path.join(out_path, fold_id, file_id + '.csv'),
                chunk=csv_data,
                chnames=[ch.name for ch in header.mount],                
                )
            t_csv = time.time() - start            
            size_csv = os.path.getsize(os.path.join(out_path, fold_id, file_id + '.csv'))

            try:
                os.remove(os.path.join(out_path, fold_id, file_id + '.csv'))
            except OSError:
                pass
                
            # Aggregate stats
            # Aggregate stats
            # Aggregate stats
            stat['size_orig'].append(size_orig)
            stat['size_h5'].append(size_h5)
            stat['size_h5gzip'].append(size_h5gzip)
            stat['size_csv'].append(size_csv)
            stat['time_h5'].append(t_h5)
            stat['time_h5gzip'].append(t_h5gzip)
            stat['time_csv'].append(t_csv)
            stat['time_marks'].append(t_marks)
            stat['time_header'].append(t_header)




            continue



            # Analyze accelerometry
            # Analyze accelerometry
            # Analyze accelerometry
            # Analyze accelerometry
            if file_id in marks:
                cuk = [(entry.message, _samplefromtimestamp([entry.timestamp, header.timestamp], 2000)) for entry in marks[file_id].content if entry.message.startswith('IRE Cuk')]
            else:
                continue

            if not cuk:
                continue
            
            ch_id = [idx for idx, item in enumerate(header.mount) if item.name.startswith('acce')]

            if not ch_id:
                continue

            acc = data[ch_id[0], :]
            y = filtfilt(b, a, np.transpose(acc))
            z = np.abs(y)

            for trial, sample in cuk:
                startsample = sample - (2000 * 10)
                endsample = sample + (2000 * 10)

                startsample = max(0, startsample)
                endsample = min(z.shape[0]-1, endsample)

                peak_val = np.amax(z[startsample:endsample])
                
                try:
                    pulse_width, pulse_spacing, _ = [int(val) for val in trial.lstrip('IRE Cuk: ').split(',')]
                except (ValueError, AttributeError):
                    print(f'Wrong trial {trial} in {file_id}')
                    continue

                res[pulse_width][pulse_spacing].append(peak_val)
    
    stat['fold_id'] = foldid_list

    with open(os.path.join(r'C:\Users\jakub\Research\Results\2023_cinc_epycon', 'epycon_stats.json'), "w") as outfile:
        json.dump(stat, outfile)
    
    # with open(os.path.join(r'C:\Users\jakub\Research\Data', 'ire_res.json'), "w") as outfile:
    #     json.dump(res, outfile)
    print()