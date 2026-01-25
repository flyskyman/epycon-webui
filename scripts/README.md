generate_fake_wmx32.py — generator for fake WorkMate logs

Purpose
- Produce minimal WMx32/WMx64 binary logs that `epycon` can parse.
- Useful for CI and local end-to-end verification without real data.

Usage
- Default (creates `samples/study01/00000000.log`):

  ```powershell
  python scripts\generate_fake_wmx32.py
  ```

- Options:
  - `--out / -o` : output path (default `samples/study01/00000000.log`)
  - `--channels / -c` : number of channels
  - `--samples / -n` : number of samples per channel
  - `--value / -v` : int value written to each sample
  - `--fs` : sampling frequency (written into header)
  - `--version / -V` : schema version (`4.1`, `4.2`, `4.3`)

Examples

```powershell
# single-channel, 1024 samples
python scripts\generate_fake_wmx32.py --out samples/study01/00000000.log

# two-channel, 512 samples, fs=500
python scripts\generate_fake_wmx32.py --out samples/study01/00000001.log --channels 2 --samples 512 --fs 500 --version 4.1

# WMx64-style
python scripts\generate_fake_wmx32.py --out samples/study01/00000002.log --version 4.3
```

Notes
- Generated logs are synthetic and simplified — they are intended only for tooling/testing, not clinical use.
- The generator fills header offsets used by the parser but does not attempt a byte-perfect reproduction of proprietary formats.
- For CI, run the generator then `python -m epycon` to verify end-to-end conversion.

Additional options

- `--with-entries`: also write a minimal `entries.log` alongside the generated log.
- `--with-master`: also write a `MASTER` file (contains `subject_id` at expected offset).

Advanced entries options

- `--entries-json`: path to a JSON file describing entries. Format: a list of objects with keys `group` (int), `timestamp` (int, unix seconds), `message` (string), optional `fid` (int). Example:

```json
[
  {"group":2, "timestamp":1690000000, "message":"note 1", "fid":1},
  {"group":3, "timestamp":1690000100, "message":"note 2", "fid":2}
]
```

- `--entries-fids`: when generating entries automatically, rotate their `fid` across N datalog ids (default 1).

Example: generate log + entries + master

```powershell
python scripts\generate_fake_wmx32.py --out samples/study01/00000004.log --with-entries --with-master
```
