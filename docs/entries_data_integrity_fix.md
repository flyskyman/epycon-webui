# Entries 数据完整性修复报告

## 问题总结

在之前的合并模式实现中，发现了**4 个关键问题**可能导致有效标注数据丢失：

### 问题 1: 多文件时间范围重叠导致重复或遗漏
**位置**: `app_gui.py` 第 728 行（合并模式）、第 838 行（常规模式）

**问题描述**:
```python
# 原代码 - 两个文件都用闭区间
file_entries = [e for e in all_entries_norm if file_start_sec <= e.timestamp <= file_end_sec]
```

当多个文件存在时，恰好在文件边界处的标注会被**分配给两个文件**或**都不分配**。

**修复方案**:
- 非最后一个文件使用开区间: `file_start_sec <= e.timestamp < file_end_sec`
- 最后一个文件使用闭区间: `file_start_sec <= e.timestamp <= file_end_sec`
- 这样保证每条标注恰好被分配给一个文件

### 问题 2: 位置有效性检查逻辑错误
**位置**: `app_gui.py` 第 791 行（修复前）

**问题描述**:
```python
# 错误的检查逻辑
if 0 <= global_p < file_sample_count:  # file_sample_count 是当前文件的样本数，不是边界！
    valid.append((global_p, g, m))
```

**问题解析**:
- `global_p` 是全局位置（从 0 开始的绝对位置）
- `file_sample_count` 是当前文件的样本数
- 正确的边界应该是: `[global_base, global_base + file_sample_count)`

**修复方案**:
```python
# 正确的检查逻辑
if global_base <= global_p < file_end_global:
    valid.append((global_p, g, m))
```

### 问题 3: 位置计算精度丢失
**位置**: `app_gui.py` 第 773-774 行（修复前）

**问题描述**:
```python
# 危险的操作
safe_pos = [max(0, int(e.timestamp - file_start_sec) * fs) for e in file_entries]
```

**问题解析**:
1. `int()` 向下取整，丢失小数部分
2. `max(0, pos)` 如果位置计算为负，会强制设为 0，**改变了标注的实际位置**
3. 这会导致标注被嵌入到错误的位置，或根本无法检测到无效标注

**修复方案**:
```python
# 使用 round 四舍五入获得更精确的位置
for e in file_entries:
    relative_pos = round((e.timestamp - file_start_sec) * fs)
    global_p = global_base + relative_pos
    
    # 检查有效性，不修改位置
    if global_base <= global_p < file_end_global:
        valid.append((global_p, str(e.group), str(e.message)))
    # 无效的直接跳过，不强制转换
```

### 问题 4: 常规模式也存在相同问题
**位置**: `app_gui.py` 第 909 行

原本的常规模式（单文件输出）中也使用了相同的危险操作。已统一修复。

---

## 修复内容清单

✅ **合并模式**:
- [x] 时间范围边界处理（开/闭区间）
- [x] 全局位置有效性检查
- [x] 位置计算精度优化
- [x] 添加详细的调试日志

✅ **常规模式**:
- [x] 位置计算精度优化
- [x] 位置有效性检查改进
- [x] 添加详细的调试日志

---

## 数据完整性保证

### 场景 1: 多文件合并
**原问题**: 边界标注被重复计算或遗漏
**现状**: 每条标注恰好被分配给一个文件 ✅

### 场景 2: 位置精度
**原问题**: int() 向下取整导致偏差
**现状**: 使用 round() 四舍五入，位置更精确 ✅

### 场景 3: 范围检查
**原问题**: 范围检查逻辑错误导致有效标注被过滤
**现状**: 使用正确的全局范围检查 `[global_base, global_base + file_sample_count)` ✅

### 场景 4: 位置修改
**原问题**: max(0, pos) 强制修改位置，导致标注嵌入位置错误
**现状**: 对无效位置直接跳过，不修改 ✅

---

## 验证结果

通过 `validate_entries_logic.py` 的完整场景验证，所有修复都已确保：
- ✅ 无数据丢失
- ✅ 无数据重复
- ✅ 位置精确性
- ✅ 范围检查正确性

---

## 建议

1. **监控 log 输出**: 在转换过程中查看标注匹配和过滤的日志，确保没有异常警告
2. **多文件测试**: 使用多个日志文件进行合并测试，验证边界处理的正确性
3. **端到端验证**: 生成的 H5 文件中 Marks 数据集应包含所有有效标注，无遗漏
