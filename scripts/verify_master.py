#!/usr/bin/env python3
"""验证HDF5文件是否包含MASTER文件信息"""
import h5py
import os
from glob import glob

print("=" * 70)
print("验证 HDF5 文件中的 MASTER 信息")
print("=" * 70)

# 查找所有 H5 输出文件
h5_files = glob('examples/data/out/**/*.h5', recursive=True)
if not h5_files:
    print('\n❌ 未找到 H5 输出文件')
    print('提示: 请先运行 app_gui.py 进行转换\n')
    exit(1)

print(f'\n✅ 找到 {len(h5_files)} 个 H5 文件\n')

for idx, h5_path in enumerate(h5_files, 1):
    print(f'[{idx}] {os.path.relpath(h5_path)}')
    try:
        with h5py.File(h5_path, 'r') as f:
            attrs = dict(f.attrs)
            
            # 关键字段验证
            has_subject_id = 'subject_id' in attrs and attrs['subject_id']
            has_subject_name = 'subject_name' in attrs
            has_study_id = 'study_id' in attrs and attrs['study_id']
            
            print(f'    subject_id:   {attrs.get("subject_id", "❌ 缺失")}')
            print(f'    subject_name: {attrs.get("subject_name", "❌ 缺失") or "(空)"}')
            print(f'    study_id:     {attrs.get("study_id", "❌ 缺失")}')
            print(f'    timestamp:    {attrs.get("timestamp", "N/A")}')
            print(f'    datetime:     {attrs.get("datetime", "N/A")}')
            
            # 可选字段
            if 'author' in attrs:
                print(f'    author:       {attrs["author"]}')
            if 'merged' in attrs:
                print(f'    merged:       {attrs["merged"]}')
            if 'num_files' in attrs:
                print(f'    num_files:    {attrs["num_files"]}')
            
            # 验证结果
            if has_subject_id and has_study_id:
                print(f'    ✅ MASTER信息完整')
            else:
                print(f'    ⚠️ 缺少部分MASTER信息')
            
    except Exception as e:
        print(f'    ❌ 读取失败: {e}')
    print()

print("=" * 70)
print("✅ 验证完成")
print("=" * 70)
