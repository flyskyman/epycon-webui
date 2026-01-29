#!/usr/bin/env python3

import h5py

with h5py.File("examples/data/out/study01/study01_merged.h5", 'r') as f:
    print("Groups and datasets in file:")
    
    def print_structure(group, indent=0):
        for key in group.keys():
            item = group[key]
            prefix = "  " * indent
            if isinstance(item, h5py.Group):
                print(f"{prefix}Group: {key}")
                print_structure(item, indent + 1)
            else:
                print(f"{prefix}Dataset: {key}, shape={item.shape}, dtype={item.dtype}")
    
    print_structure(f)
    
    # Check if Marks exists and what it contains
    if 'Marks' in f:
        print("\nMarks dataset details:")
        marks = f['Marks']
        print(f"  Type: {type(marks)}")
        print(f"  Shape: {marks.shape}")
        print(f"  Dtype: {marks.dtype}")
        print(f"  Value: {marks[()]}")
