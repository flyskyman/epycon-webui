#!/usr/bin/env python3
"""
检查 H5 文件中嵌入的标注
"""

import h5py
import os
from glob import glob

# 查找所有生成的 H5 文件
h5_files = glob("examples/data/out/**/*.h5", recursive=True)

print(f"Found {len(h5_files)} H5 files\n")

for h5_path in h5_files:
    if not os.path.exists(h5_path):
        print(f"WARNING: File does not exist: {h5_path}")
        continue
    
    print(f"Checking: {h5_path}")
    with h5py.File(h5_path, 'r') as f:
        # Check for Marks group/dataset
        if 'Marks' in f:
            marks_group = f['Marks']
            print("  Marks group found!")
            print(f"  Keys in Marks: {list(marks_group.keys())}")
            
            for key in marks_group.keys():
                data = marks_group[key][()]
                print(f"    {key}: {data}")
        else:
            print("  No Marks group found")
    print()
