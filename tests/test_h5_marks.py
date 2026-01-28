#!/usr/bin/env python3
"""
检查 H5 文件中嵌入的标注
"""
# pyright: ignore (h5py type stubs issue)
import h5py
import os
from glob import glob

# 查找所有生成的 H5 文件
h5_files = glob("examples/data/out/**/*.h5", recursive=True)

print(f"✅ 找到 {len(h5_files)} 个 H5 文件\n")

for h5_path in h5_files:
    if not os.path.exists(h5_path):
        print(f"⚠️ 文件不存在: {h5_path}")
        continue
    
    print(f"📄 检查文件: {h5_path}")
    with h5py.File(h5_path, 'r') as f:
        # 打印文件属性
        print("  属性:")
        for key, val in f.attrs.items():
            if isinstance(val, bytes):
                val = val.decode('utf-8', errors='replace')
            print(f"    - {key}: {val}")
        
        # 打印数据集
        print("  数据集:")
        for key in f.keys():
            ds = f[key]
            print(f"    - {key}: {ds.shape}")
            if key == 'Marks':
                marks = f[key]
                print(f"      Marks 数据: {marks[()]}")
            elif key == 'marks_positions':
                positions = list(ds[()])
                print(f"      positions: {positions}")
            elif key == 'marks_groups':
                groups = list(ds[()])
                groups_str = [g.decode('utf-8') if isinstance(g, bytes) else g for g in groups]
                print(f"      groups: {groups_str}")
            elif key == 'marks_messages':
                msgs = list(ds[()])
                msgs_str = [m.decode('utf-8') if isinstance(m, bytes) else m for m in msgs]
                print(f"      messages: {msgs_str}")
    print()
