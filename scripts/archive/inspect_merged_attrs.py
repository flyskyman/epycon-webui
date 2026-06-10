import os
import h5py

outdir = r"C:/Backup/output"
if not os.path.exists(outdir):
    print(f"Output directory not found: {outdir}")
    raise SystemExit(0)

for root, dirs, files in os.walk(outdir):
    for fname in sorted(files):
        if not fname.lower().endswith('.h5'):
            continue
        path = os.path.join(root, fname)
        print('\nFile:', path)
        try:
            with h5py.File(path, 'r') as f:
                keys = sorted(list(f.attrs.keys()))
                if not keys:
                    print('  (no root attributes)')
                for k in keys:
                    val = f.attrs[k]
                    if isinstance(val, bytes):
                        try:
                            val = val.decode('utf-8')
                        except Exception:
                            val = str(val)
                    print(f'  {k}: {val}')

                # list top-level datasets/groups and their shapes
                items = []
                def visitor(name, obj):
                    if isinstance(obj, h5py.Dataset):
                        items.append((name, obj.shape, obj.dtype))
                f.visititems(visitor)
                if items:
                    print('  Datasets:')
                    for name, shape, dtype in items:
                        print(f'    {name}: shape={shape}, dtype={dtype}')
                else:
                    print('  (no datasets)')
        except Exception as e:
            print('  ERROR reading file:', e)
