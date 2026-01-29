# 性能回归检测指南

## 概述

EPYCON 现已集成性能回归检测系统，在每次提交时自动检测性能变化。

## 工作原理

### 1. **基准测试收集**
- 在 `scripts/test_performance_regression.py` 中定义关键操作的性能基准
- 测试覆盖：HDF5 写入、CSV 写入、配置覆盖、时间戳计算、数组操作
- 每个基准运行 3-100 次迭代以获得稳定的平均值

### 2. **基准数据存储**
基准数据保存在 `scripts/benchmarks.json`：

```json
{
  "HDF5 Write (100K samples)": {
    "avg": 0.00735,
    "std": 0.00444,
    "min": 0.00531,
    "max": 0.01568,
    "iterations": 3
  },
  "Array Operations (1M elements)": {
    "avg": 0.08084,
    "std": 0.00350,
    "min": 0.07682,
    "max": 0.08624,
    "iterations": 3
  }
}
```

### 3. **回归检测**
- **阈值**：15% 性能下降
- **黄色警告**：5-15% 之间的下降
- **红色报警**：超过 15% 的下降

### 4. **CI/CD 集成**
在 GitHub Actions 中自动运行：

```yaml
- name: Run performance benchmarks
  env:
    PYTHONPATH: ${{ github.workspace }}/epycon:${{ github.workspace }}
  run: |
    echo "Running performance benchmarks..."
    python scripts/test_performance_regression.py
```

## 本地运行

### 首次运行（生成基准）
```powershell
cd c:\Projects\epycon
python scripts/test_performance_regression.py
```

输出：
```
✅ Baseline saved to C:\Projects\epycon\scripts\benchmarks.json
```

### 后续运行（检测回归）
```powershell
python scripts/test_performance_regression.py
```

输出示例：
```
🟢 HDF5 Write (100K samples)
   Average: 7.35ms (±4.44ms)
   Status: OK: -0.3%
   Baseline: 7.36ms

🔴 Timestamp Diff (4 ops)
   Average: 0.01ms (±0.00ms)
   Status: Regression: 66.6% slower
   Baseline: 0.00ms

✅ NO REGRESSIONS DETECTED (threshold: 15%)
```

## 更新基准

当优化代码后需要更新基准：

```powershell
# 1. 在代码中进行优化
# 2. 运行性能测试
python scripts/test_performance_regression.py

# 3. 检查新结果
cat scripts/benchmarks.json

# 4. 如果改进确认无误，提交新基准
git add scripts/benchmarks.json
git commit -m "perf: update performance baseline after optimization"
git push
```

## 添加新的基准

在 `scripts/test_performance_regression.py` 中添加新函数：

```python
def benchmark_my_operation():
    """Benchmark description"""
    def op():
        # 你的操作代码
        pass
    return op
```

然后在 `main()` 中注册：

```python
benchmarks = [
    ('My Operation', benchmark_my_operation(), 5),  # 运行 5 次
    # ... 其他基准
]
```

## 常见场景

### 场景 1：代码优化后基准改进
```
✅ Array Operations
   Status: Improvement: -8.3%
```
→ 提交新基准并记录优化说明

### 场景 2：检测到性能回归
```
🔴 HDF5 Write
   Status: Regression: 22.1% slower
```
→ 调查最近改动，优化代码或回滚更改

### 场景 3：正常波动（<5%）
```
🟢 Config Override
   Status: OK: 1.2%
```
→ 无需操作，正常范围内的性能变化

## GitHub Actions 输出

所有性能基准在 CI 中自动运行。检查方式：

1. 打开 GitHub 项目
2. 进入 **Actions** 标签页
3. 选择最新的 workflow 运行
4. 找到 **Run performance benchmarks** 步骤
5. 查看完整的性能报告

## 性能基准清单

| 操作 | 数据量 | 目标 | 当前 |
|------|--------|------|------|
| HDF5 写入 | 100K 样本 | <8ms | 7.35ms ✅ |
| CSV 写入 | 10K 样本 | <15ms | 9.79ms ✅ |
| 配置覆盖 | 4 层嵌套 | <1ms | 0.00ms ✅ |
| 时间戳计算 | 4 操作 | <0.1ms | 0.01ms ✅ |
| 数组运算 | 1M 元素 | <100ms | 80.84ms ✅ |

## 故障排除

### 基准数据丢失
如果 `scripts/benchmarks.json` 被删除：
```powershell
python scripts/test_performance_regression.py
# 脚本会自动重新生成基准
```

### 性能测试失败
检查依赖是否安装：
```powershell
pip install numpy h5py
```

### 跨平台性能差异
不同操作系统的基准时间会有差异。建议：
- 每个 CI 环境维护独立基准
- 重点关注相对变化（% 改变）而非绝对时间

## 下一步优化

- [ ] 添加内存使用量跟踪
- [ ] 记录 CPU 使用率变化
- [ ] 构建性能历史趋势图
- [ ] 自动生成性能报告 PDF
- [ ] 集成性能比较至 PR 评论
