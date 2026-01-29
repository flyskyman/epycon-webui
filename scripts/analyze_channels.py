#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""分析 C:\Backup 目录下所有患者数据的通道数"""

import os
import sys
from pathlib import Path
from epycon.iou import LogParser

def analyze_study(study_path):
    """分析单个study目录"""
    study_name = os.path.basename(study_path)
    print(f"\n{'='*70}")
    print(f"患者目录: {study_name}")
    print('='*70)
    
    log_files = sorted([f for f in os.listdir(study_path) 
                       if f.endswith('.log') and f[:8].isdigit()])
    
    if not log_files:
        print("  ⚠️ 未找到数据文件")
        return None
    
    channels_info = []
    for log_file in log_files:
        log_path = os.path.join(study_path, log_file)
        try:
            with LogParser(log_path, version="4.3.2", samplesize=1024) as parser:
                header = parser.get_header()
                num_channels = header.num_channels
                channels_info.append((log_file, num_channels))
                print(f"  {log_file}: {num_channels:3d} 个通道")
        except Exception as e:
            print(f"  {log_file}: ❌ 读取失败 - {e}")
    
    return channels_info

def main():
    backup_dir = r"C:\Backup"
    
    print("\n" + "🔍 通道数分析报告".center(70, '='))
    print(f"数据目录: {backup_dir}\n")
    
    studies = [d for d in os.listdir(backup_dir) 
              if os.path.isdir(os.path.join(backup_dir, d)) and d != 'output']
    
    all_results = {}
    for study in sorted(studies):
        study_path = os.path.join(backup_dir, study)
        channels_info = analyze_study(study_path)
        if channels_info:
            all_results[study] = channels_info
    
    # 汇总分析
    print("\n" + "📊 汇总分析".center(70, '='))
    for study, info in all_results.items():
        channel_counts = set(ch for _, ch in info)
        if len(channel_counts) > 1:
            print(f"\n⚠️  {study}")
            print(f"    发现不同通道数: {sorted(channel_counts)}")
            for fname, ch in info:
                print(f"      {fname}: {ch} 通道")
        else:
            print(f"\n✅ {study}")
            print(f"    所有文件通道数一致: {list(channel_counts)[0]} 个通道")
    
    print("\n" + "="*70 + "\n")

if __name__ == "__main__":
    main()
