import argparse
import os
import struct
import time


def generate_wmx(out_path, version='4.3.2', num_channels=1, num_samples=1024, sample_value=1000, sampling_freq=1000):
    """Generate a fake WMx binary log. Supports WMx32 (4.1) and WMx64 (4.2/4.3/4.3.2).

    The generator fills header regions used by the parser (`epycon/config/byteschema.py`).
    It is intentionally minimal but sets timestamp, channel definitions, amplifier settings,
    sample mapping and data block start address to plausible values.
    """
    if version == '4.1':
        # WMx32
        header_size = 0x35B8
        header = bytearray(b"\x00") * header_size
        # timestamp (uint32)
        ts = int(time.time())
        header[0:4] = struct.pack('<L', ts)
        # num_channels uint16 at 0x4:0x6
        header[4:6] = struct.pack('<H', num_channels)

        channels_start = 0x2E
        subblock_size = 0x1E
        amp_res_offset = (0x34AE, 0x34B0)
        amp_fs_offset = (0x34B4, 0x34B6)
        sample_map_start = 0x34B6
        sample_map_len = 0x35B6 - 0x34B6
        datablock_start_off = (0x35B6, 0x35B8)

    else:
        # WMx64
        header_size = 0x393C
        header = bytearray(b"\x00") * header_size
        # timestamp (uint64) scaled by 1000 to mimic byteschema
        ts = int(time.time() * 1000)
        header[0:8] = struct.pack('<Q', ts)
        # num_channels uint16 at 0x8:0xA
        header[0x8:0xA] = struct.pack('<H', num_channels)

        channels_start = 0x32
        subblock_size = 0x20
        amp_res_offset = (0x3832, 0x3834)
        amp_fs_offset = (0x3838, 0x383A)
        sample_map_start = 0x383A
        sample_map_len = 0x393A - 0x383A
        datablock_start_off = (0x393A, 0x393C)

    # create channel subblocks
    for ch_idx in range(num_channels):
        bchunk = bytearray(b"\x00") * subblock_size
        # name (put into first 12 bytes to be safe)
        name = f'CH{ch_idx+1}'.encode('ascii')
        name = name + b'\x00' * (0xC - len(name))
        bchunk[0x0:0xC] = name
        # ids mapping (two bytes) at subblock offset 0xE
        if subblock_size >= 0x10:
            bchunk[0xE:0x10] = bytes([ch_idx & 0xFF, 0xFF])
        # input source
        if subblock_size > 0x15:
            bchunk[0x15] = 1
        # jbox pins
        if subblock_size > 0x16:
            bchunk[0x16:0x18] = bytes([0xFF, 0xFF])

        dest = channels_start + ch_idx * subblock_size
        max_block = (0x34AE if version == '4.1' else 0x3832)
        if dest + subblock_size <= max_block:
            header[dest:dest+subblock_size] = bchunk

    # amplifier settings
    header[amp_res_offset[0]:amp_res_offset[1]] = struct.pack('<H', 1)
    header[amp_fs_offset[0]:amp_fs_offset[1]] = struct.pack('<H', sampling_freq)

    # sample mapping
    sample_map = bytearray([i % 256 for i in range(sample_map_len)])
    header[sample_map_start:sample_map_start+sample_map_len] = sample_map

    # datablock start address (store low 16 bits)
    start_addr_val = header_size
    header[datablock_start_off[0]:datablock_start_off[1]] = struct.pack('<H', start_addr_val & 0xFFFF)

    # write samples (int32 per value)
    data = b''.join(struct.pack('<i', sample_value) for _ in range(num_samples * num_channels))

    with open(out_path, 'wb') as f:
        f.write(header)
        f.write(data)


def write_master(out_dir, subject_id='SUBJ001'):
    # MASTER subject id should be at offset 0x43:0x4F (fill rest with zeros)
    size = 0x4F
    b = bytearray(b"\x00") * size
    sid = subject_id.encode('ascii')[:(0x4F-0x43)]
    b[0x43:0x43+len(sid)] = sid
    path = os.path.join(out_dir, 'MASTER')
    with open(path, 'wb') as f:
        f.write(b)
    return path


def write_entries(out_dir, version='4.3.2', entries=None, datalog_id=1):
    """Write a minimal binary entries.log compatible with parser.

    entries: list of tuples (group:int, timestamp:int, message:str)
             timestamp should be in milliseconds for WMx64, seconds for WMx32
    """
    if entries is None:
        # Use a fixed timestamp from 2024 to avoid potential issues with future dates
        if version == '4.1':
            base_timestamp = 1704038400  # 2024-01-01 00:00:00 UTC (seconds)
        else:
            base_timestamp = 1704038400000  # 2024-01-01 00:00:00 UTC (milliseconds)
        entries = [(2, base_timestamp, 'example entry')]

    if version == '4.1':
        header_len = 0x20
        line_size = 0xD8
        fmt_ts = '<L'
        ts_factor = 1  # input timestamp is in seconds
    else:
        header_len = 0x24
        line_size = 0xDC
        fmt_ts = '<Q'
        ts_factor = 1  # input timestamp is already in milliseconds

    # header: set header timestamp
    header = bytearray(b"\x00") * header_len
    header_ts = int(time.time())
    if fmt_ts == '<L':
        header[0x02:0x06] = struct.pack('<L', header_ts)
    else:
        header[0x02:0x0A] = struct.pack('<Q', int(header_ts*1000))

    buf = bytearray()
    buf.extend(header)

    for grp, ts, msg in entries:
        line = bytearray(b"\x00") * line_size
        # entry_type at 0x0:0x2 (uint16)
        line[0x0:0x2] = struct.pack('<H', grp)
        # datalog_id at 0x2:0x6 (uint32)
        line[0x2:0x6] = struct.pack('<L', datalog_id)
        # timestamp at 0xA:0xE (for 32-bit) or 0xA:0x12 (for 64-bit)
        if fmt_ts == '<L':
            line[0xA:0xE] = struct.pack('<L', int(ts))
        else:
            line[0xA:0x12] = struct.pack('<Q', int(ts))
        # text at 0xE:0xC0 (truncate)
        text_bytes = msg.encode('ascii', 'ignore')
        text_offset = 0xE if fmt_ts == '<L' else 0x12
        max_text = (0xC0 - 0xE) if fmt_ts == '<L' else (0xC2 - 0x12)
        line[text_offset:text_offset+min(len(text_bytes), max_text)] = text_bytes[:min(len(text_bytes), max_text)]
        buf.extend(line)

    path = os.path.join(out_dir, 'entries.log')
    with open(path, 'wb') as f:
        f.write(buf)
    return path


def main():
    parser = argparse.ArgumentParser(description='Generate fake WMx binary log for testing')
    parser.add_argument('--out', '-o', default=os.path.join('samples', 'study01', '00000000.log'))
    parser.add_argument('--channels', '-c', type=int, default=1)
    parser.add_argument('--samples', '-n', type=int, default=1024)
    parser.add_argument('--value', '-v', type=int, default=1000)
    parser.add_argument('--fs', type=int, default=1000)
    parser.add_argument('--version', '-V', choices=['4.1', '4.2', '4.3', '4.3.2'], default='4.3.2', help='WorkMate version/schema to generate (4.1=WMx32, 4.2/4.3/4.3.2=WMx64)')
    parser.add_argument('--with-entries', action='store_true', help='Also write a minimal entries.log')
    parser.add_argument('--with-master', action='store_true', help='Also write a MASTER file')
    parser.add_argument('--entries-count', type=int, default=1, help='Number of entries to generate')
    parser.add_argument('--entry-message', type=str, default='example entry', help='Message text for generated entries')
    parser.add_argument('--entries-json', type=str, default=None, help='Path to a JSON file listing entries as [{"group":int,"timestamp":int,"message":str,"fid":int}, ...]')
    parser.add_argument('--entries-fids', type=int, default=1, help='Number of distinct datalog ids (fids) to rotate entries across')

    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    generate_wmx(args.out, version=args.version, num_channels=args.channels, num_samples=args.samples, sample_value=args.value, sampling_freq=args.fs)
    print(f'Wrote fake WMx log (schema {args.version}) to {args.out}')

    out_dir = os.path.dirname(args.out)
    if args.with_master:
        mpath = write_master(out_dir)
        print(f'Wrote MASTER to {mpath}')

    if args.with_entries:
        # Load entries from JSON file if provided
        if args.entries_json:
            import json
            with open(args.entries_json, 'r', encoding='utf-8') as jf:
                data = json.load(jf)
            # normalize entries: expect list of dicts with keys group,timestamp,message,fid(optional)
            entries = []
            for item in data:
                grp = int(item.get('group', 2))
                ts = int(item.get('timestamp', int(time.time())))
                msg = str(item.get('message', args.entry_message))
                fid = int(item.get('fid', 1))
                entries.append((grp, ts, msg, fid))
        else:
            # Use fixed base timestamp from 2024 to avoid datetime issues
            # For WMx64, timestamp is in milliseconds, so we use smaller base value
            base_timestamp_ms = 1704038400000  # 2024-01-01 00:00:00 UTC (milliseconds)
            entries = []
            for i in range(args.entries_count):
                grp = 2 + (i % 5)  # rotate some group ids
                ts_ms = base_timestamp_ms + i * 60000  # Add minutes in milliseconds to avoid duplicate timestamps
                msg = f"{args.entry_message} #{i+1}"
                fid = 1 + (i % args.entries_fids)
                entries.append((grp, ts_ms, msg, fid))

        # write_entries expects entries as (group,timestamp,message) per datalog id; group by fid
        # create mapping fid -> list of (group,timestamp,message)
        from collections import defaultdict
        grouped = defaultdict(list)
        for grp, ts, msg, fid in entries:
            grouped[fid].append((grp, ts, msg))

        epath = None
        for fid, elist in grouped.items():
            # write separate entries.log per fid by appending fid in filename suffix
            subpath = epath = write_entries(out_dir, version=args.version, entries=elist, datalog_id=fid)
        print(f'Wrote entries to {epath}')
        print(f'Wrote entries to {epath}')


if __name__ == '__main__':
    main()

