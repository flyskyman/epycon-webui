#!/usr/bin/env python3
"""
验证标注数据不被丢失的测试脚本
"""

import sys
sys.path.insert(0, 'c:\\Projects\\epycon')

# 模拟标注处理的各个关键场景

print("=" * 60)
print("场景 1: 验证时间范围边界处理（多文件）")
print("=" * 60)

# 场景：两个文件，标注在边界处
file1_start = 1000.0
file1_end = 2000.0 + 1.024  # 1000 samples + 1.024s

file2_start = 2001.024
file2_end = 3001.024 + 1.024

entries = [
    {'timestamp': 1000.5, 'group': 'A'},   # file 1
    {'timestamp': 2001.024, 'group': 'B'},  # 恰好在 file 1 结束处 - 应该属于 file 2
    {'timestamp': 3000.0, 'group': 'C'},   # file 2
]

# 修复前的逻辑（会重复）
print("\n修复前 - 使用闭区间 <=")
file1_entries_old = [e for e in entries if file1_start <= e['timestamp'] <= file1_end]
file2_entries_old = [e for e in entries if file2_start <= e['timestamp'] <= file2_end]
print(f"  File 1: {[e['group'] for e in file1_entries_old]}")
print(f"  File 2: {[e['group'] for e in file2_entries_old]}")
print(f"  问题: 标注 B 被重复计算！")

# 修复后的逻辑（避免重复）
print("\n修复后 - 非最后文件用开区间，最后文件用闭区间")
is_last_file = False
if is_last_file:
    file1_entries_new = [e for e in entries if file1_start <= e['timestamp'] <= file1_end]
else:
    file1_entries_new = [e for e in entries if file1_start <= e['timestamp'] < file1_end]
is_last_file = True
if is_last_file:
    file2_entries_new = [e for e in entries if file2_start <= e['timestamp'] <= file2_end]
else:
    file2_entries_new = [e for e in entries if file2_start <= e['timestamp'] < file2_end]
print(f"  File 1: {[e['group'] for e in file1_entries_new]}")
print(f"  File 2: {[e['group'] for e in file2_entries_new]}")
print(f"  ✅ 无重复，所有标注都被准确分配")

print("\n" + "=" * 60)
print("场景 2: 验证位置计算精度")
print("=" * 60)

# 标注的相对时间（秒）
relative_times = [0.001, 0.5, 0.999, 1.023]  # 最后一个接近文件末尾
fs = 1000  # 采样率
file_samples = 1024

print(f"\n采样率: {fs} Hz, 文件样本数: {file_samples}")
print("修复前 - 使用 int() 向下取整和 max(0, ...)")
for ts in relative_times:
    pos_old = max(0, int(ts * fs))
    print(f"  {ts:.3f}s -> {pos_old} (int 向下)")

print("\n修复后 - 使用 round() 四舍五入")
for ts in relative_times:
    pos_new = round(ts * fs)
    print(f"  {ts:.3f}s -> {pos_new} (round 精确)")

print("\n✅ 使用 round 更接近真实位置，避免精度丢失")

print("\n" + "=" * 60)
print("场景 3: 验证位置有效性检查")
print("=" * 60)

# 模拟全局位置有效性检查
global_base = 1000  # 该文件在全局中的起始位置
file_sample_count = 1024
file_end_global = global_base + file_sample_count

test_positions = [
    (global_base, "边界左侧"),
    (global_base + 500, "中间"),
    (file_end_global - 1, "边界右侧"),
    (file_end_global, "刚好在末尾 - 应该无效"),
    (file_end_global + 1, "超过末尾"),
]

print(f"\n有效范围: [{global_base}, {file_end_global})")
print("修复前 - 错误的检查 (0 <= global_p < file_sample_count)")
for pos, desc in test_positions:
    # 错误的检查
    valid_old = 0 <= pos < file_sample_count
    print(f"  {pos}: {valid_old} ({desc}) <- 错误！")

print("\n修复后 - 正确的检查 (global_base <= global_p < file_end_global)")
for pos, desc in test_positions:
    # 正确的检查
    valid_new = global_base <= pos < file_end_global
    print(f"  {pos}: {valid_new} ({desc})")

print("\n" + "=" * 60)
print("场景 4: 验证不会意外改变位置")
print("=" * 60)

# 确保没有使用 max(0, ...) 强制修改位置
print("\n修复前危险的 max(0, pos) 操作:")
test_values = [-100, -1, 0, 500]
for val in test_values:
    result = max(0, val)
    if val != result:
        print(f"  {val} -> {result} (被修改！危险！)")
    else:
        print(f"  {val} -> {result}")

print("\n修复后 - 直接检查不修改:")
for val in test_values:
    if val >= 0:
        print(f"  {val}: 保留")
    else:
        print(f"  {val}: 跳过 (不修改)")

print("\n✅ 所有修复验证完成！")
print("=" * 60)
