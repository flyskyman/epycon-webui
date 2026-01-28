#!/usr/bin/env python3
"""
交互式 HDF5 属性查看器
用法: python inspect_h5_attrs.py <h5文件路径|all|目录>
"""
import sys
import os
import h5py
from pathlib import Path
from glob import glob

def inspect_h5_file(filepath):
    """详细检查 HDF5 文件的属性和结构"""
    # 检查路径是否为目录
    if os.path.isdir(filepath):
        print(f"❌ 错误: '{filepath}' 是一个目录，不是文件")
        print(f"💡 提示: 使用 'python inspect_h5_attrs.py \"{filepath}\"' 扫描目录中的所有 H5 文件")
        return False
    
    # 检查文件是否存在
    if not Path(filepath).exists():
        print(f"❌ 文件不存在: {filepath}")
        return False
    
    print("=" * 70)
    print(f"文件: {filepath}")
    print("=" * 70)
    
    try:
        with h5py.File(filepath, 'r') as f:
            # 1. 文件级属性（全局属性）
            print("\n📋 文件级属性 (Global Attributes):")
            print("-" * 70)
            if len(f.attrs) > 0:
                for key in sorted(f.attrs.keys()):
                    value = f.attrs[key]
                    if isinstance(value, bytes):
                        value = value.decode('utf-8', errors='replace')
                    print(f"  {key:20s} = {value}")
            else:
                print("  (无属性)")
            
            # 2. 数据集
            print("\n📊 数据集 (Datasets):")
            print("-" * 70)
            for key in f.keys():
                item = f[key]
                if isinstance(item, h5py.Dataset):
                    print(f"  {key:20s} shape={item.shape}, dtype={item.dtype}")
                    # 显示数据集的属性
                    if len(item.attrs) > 0:
                        for attr_key in item.attrs.keys():
                            attr_val = item.attrs[attr_key]
                            if isinstance(attr_val, bytes):
                                attr_val = attr_val.decode('utf-8', errors='replace')
                            print(f"    └─ {attr_key}: {attr_val}")
            
            # 3. 组
            print("\n📁 组 (Groups):")
            print("-" * 70)
            has_groups = False
            for key in f.keys():
                item = f[key]
                if isinstance(item, h5py.Group):
                    has_groups = True
                    print(f"  {key}/")
                    for subkey in item.keys():
                        print(f"    └─ {subkey}")
            if not has_groups:
                print("  (无组)")
            
            # 4. 数据预览
            print("\n👁️ 数据预览:")
            print("-" * 70)
            if 'Data' in f:
                data = f['Data']
                if isinstance(data, h5py.Dataset):
                    print(f"  Data: {data.shape}, 前3个样本:")
                    if len(data.shape) == 2:
                        print(f"    {data[:, :3]}")
                    else:
                        print(f"    {data[:3]}")
            
            if 'Marks' in f:
                marks = f['Marks']
                if isinstance(marks, h5py.Dataset):
                    print(f"\n  Marks: {marks.shape}, 共 {len(marks)} 个标注")
                    if len(marks) > 0:
                        print(f"    前3个: {marks[:3]}")
        
        print("\n" + "=" * 70)
        return True
                    
    except Exception as e:
        print(f"❌ 读取失败: {e}")
        print(f"💡 提示: 确保这是一个有效的 HDF5 文件")
        print("\n" + "=" * 70)
        return False

def main():
    if len(sys.argv) < 2:
        print("用法: python inspect_h5_attrs.py <h5文件路径|all|目录路径>")
        print("\n示例:")
        print("  python inspect_h5_attrs.py examples/data/out/study01/00000000.h5  # 单文件")
        print("  python inspect_h5_attrs.py all                                    # 所有文件")
        print("  python inspect_h5_attrs.py c:\\eptest                              # 扫描目录")
        print("  python inspect_h5_attrs.py \"c:\\eptest\\*.h5\"                      # 通配符")
        print("\n自动发现:")
        h5_files = glob('examples/data/out/**/*.h5', recursive=True)
        if h5_files:
            print(f"\n找到 {len(h5_files)} 个 H5 文件:")
            for idx, f in enumerate(h5_files, 1):
                print(f"  [{idx}] {f}")
            print(f"\n提示: python inspect_h5_attrs.py \"{h5_files[0]}\"")
        return
    
    filepath = sys.argv[1]
    
    # 支持 'all' 参数查看所有文件
    if filepath.lower() == 'all':
        h5_files = glob('examples/data/out/**/*.h5', recursive=True)
        if not h5_files:
            print("❌ 未找到任何 H5 文件")
            return
        print(f"\n🔍 检查所有 {len(h5_files)} 个 H5 文件:\n")
        success = 0
        for idx, f in enumerate(h5_files, 1):
            print(f"\n{'='*70}")
            print(f"[{idx}/{len(h5_files)}] {f}")
            print('='*70)
            if inspect_h5_file(f):
                success += 1
            if idx < len(h5_files):
                input("\n按 Enter 继续查看下一个文件...")
        print(f"\n✅ 成功检查 {success}/{len(h5_files)} 个文件")
    
    # 检查是否为目录
    elif os.path.isdir(filepath):
        print(f"\n🔍 扫描目录: {filepath}\n")
        h5_files = glob(os.path.join(filepath, '**', '*.h5'), recursive=True)
        if not h5_files:
            print(f"❌ 目录中未找到任何 H5 文件")
            print(f"💡 提示: 确保目录中存在 .h5 文件")
            return
        print(f"找到 {len(h5_files)} 个 H5 文件:\n")
        success = 0
        for idx, f in enumerate(h5_files, 1):
            print(f"\n{'='*70}")
            print(f"[{idx}/{len(h5_files)}] {f}")
            print('='*70)
            if inspect_h5_file(f):
                success += 1
            if idx < len(h5_files):
                input("\n按 Enter 继续查看下一个文件...")
        print(f"\n✅ 成功检查 {success}/{len(h5_files)} 个文件")
    
    # 支持通配符
    elif '*' in filepath or '?' in filepath:
        h5_files = glob(filepath, recursive=True)
        if not h5_files:
            print(f"❌ 未找到匹配的文件: {filepath}")
            return
        print(f"\n🔍 找到 {len(h5_files)} 个匹配文件:\n")
        success = 0
        for idx, f in enumerate(h5_files, 1):
            print(f"\n{'='*70}")
            print(f"[{idx}/{len(h5_files)}] {f}")
            print('='*70)
            if inspect_h5_file(f):
                success += 1
            if idx < len(h5_files):
                input("\n按 Enter 继续查看下一个文件...")
        print(f"\n✅ 成功检查 {success}/{len(h5_files)} 个文件")
    
    # 单文件
    else:
        inspect_h5_file(filepath)

if __name__ == '__main__':
    main()
