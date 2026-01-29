#!/usr/bin/env python
"""验证 CI 输出的完整性和正确性"""

import os
import sys
import h5py
from pathlib import Path

def validate_outputs(output_dir="examples/data/out/study01"):
    """验证 epycon 转换输出"""
    errors = []
    warnings = []
    
    # 检查输出目录
    if not os.path.exists(output_dir):
        errors.append(f"输出目录不存在: {output_dir}")
        return False, errors, warnings
    
    # 检查 HDF5 文件
    h5_file = os.path.join(output_dir, "study01_merged.h5")
    if not os.path.exists(h5_file):
        errors.append(f"HDF5 文件不存在: {h5_file}")
    else:
        try:
            with h5py.File(h5_file, 'r') as f:
                datasets = list(f.keys())
                print(f"✓ HDF5 文件: {os.path.getsize(h5_file)} 字节")
                print(f"  数据集: {datasets}")
                
                # 验证必需的数据集
                required_datasets = ['Data', 'ChannelSettings', 'Info']
                for ds in required_datasets:
                    if ds not in datasets:
                        errors.append(f"HDF5 缺少必需数据集: {ds}")
                    else:
                        dataset = f[ds]
                        shape = dataset.shape  # type: ignore
                        print(f"    [{ds}] 形状={shape}")
        except Exception as e:
            errors.append(f"读取 HDF5 文件失败: {e}")
    
    # 检查 entries CSV 文件
    csv_file = os.path.join(output_dir, "entries_summary.csv")
    if not os.path.exists(csv_file):
        warnings.append(f"entries CSV 文件不存在: {csv_file}")
    else:
        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            if len(lines) < 1:
                errors.append("entries CSV 为空")
            else:
                num_entries = len(lines) - 1  # 排除头行
                print(f"✓ Entries 文件: {num_entries} 条记录")
                
                # 打印 entries 摘要
                for line in lines[1:]:
                    print(f"    {line.strip()}")
        except Exception as e:
            errors.append(f"读取 entries CSV 失败: {e}")
    
    # 整体验证
    success = len(errors) == 0
    return success, errors, warnings

if __name__ == "__main__":
    output_dir = sys.argv[1] if len(sys.argv) > 1 else "examples/data/out/study01"
    
    success, errors, warnings = validate_outputs(output_dir)
    
    if warnings:
        print("⚠ 警告:")
        for w in warnings:
            print(f"  - {w}")
    
    if errors:
        print("❌ 错误:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    
    if success:
        print("✅ 所有验证通过")
        sys.exit(0)
