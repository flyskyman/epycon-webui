# 通道完整性：读取层的两个陷阱

`epycon.core.integrity` 报告解码后各通道的事实，**不做任何取舍**——重复或死通道对某些分析无害、对另一些致命，取舍属于调用方。

## 为什么需要它

两种情况都来自一份真实的 WorkMate x64 study，用本包读取时都不会有任何提示：

**1. 通道名不是导联方式的证据。** 该 study 的 raw 记录里，`u+HIS` 与 `u+LBB` 在全部 2 447 718 个样点上**逐样点完全相同**，`u-HIS` 与 `u-LBB` 亦然。当时只接了一对电极，`HIS` 这个名字不构成"接了希氏束电极"的证据。17 个通道只携带 15 个独立信号。

**2. 导出索引的 `pins` 字段同样不可信。** `Session N Information.TXT` 中一行标为单极的条目

```
LBB-I.Session 7 - Page 7.13.TXT,7,753,.5  Hz,500 Hz,Lt Cyan,CIM,48,
```

其文件内容与同一导联双极条目（`...,CIM,48,47`）的文件 **md5 完全相同**。调用方若按索引取"单极通道"，拿到的是双极数据。该 study 全目录共 14 组重复内容、52 个冗余文件。

任何据此计算的单极量都会静默出错。损伤电流（COI）首当其冲——双极导联按构造抵消共模损伤电流。

## 用法

```python
from epycon.core.integrity import inspect_channels, summarise

facts = inspect_channels(values, names)     # values: (n_samples, n_channels)
report = summarise(facts)
# report["n_distinct_signals"] < report["n_channels"]  → 存在重复
# report["duplicates"]  {"u+HIS": "u+LBB", ...}
# report["flagged"]     {"STIM": ["dead: never connected"], ...}
```

阈值（`dead_zero_fraction`、`frozen_fraction`、`rail_fraction`）是**参数而非常数**。默认值取自上述单一 study，是起点而非经过验证的界限。

十二导联另有一项客观校验：

```python
from epycon.core.integrity import check_limb_identities
check_limb_identities({"I": ..., "II": ..., "III": ..., "aVR": ..., "aVL": ..., "aVF": ...})
```

`derived=True` 表示四个从属导联由记录仪从 I、II 导出而非独立测量；前提是 I、II 至少一个有变化（六条平直导联让恒等式平凡成立，此时 `informative=False`、不声明 `derived`），且导联以 float64 存储——整型或 float32 存储会留下残差（截断 int16 为 1.5 LSB），`holds` 由调用方按 LSB 设 `tolerance` 判定，`derived` 不能当 dtype 检验用。**已知盲区**：互换 I 与 II 后重新导出其余四个，恒等式依旧成立，故它无法检测 I/II 互换——该盲区在返回值的 `blind_to` 字段中显式声明。

## 另一个与读取有关的坑：导出每页开头约 2 秒不可用

同一份 study 中，raw 宽带记录与其 0.5 Hz 导出通道的相关系数：

| 区间 | 相关 |
|---|---|
| 全窗 10 s | 0.886 |
| 剔除头 2.5 s | **0.9888** |
| 仅头 2 s | 0.36 |

这不是数据损坏，是**高通滤波器的建立过程**：0.5 Hz 一阶高通的时间常数为 1/(2π×0.5) ≈ 0.32 s，5τ ≈ 1.6 s。逐 2 s 分段检查未见时钟漂移（最佳偏移恒为 0）。

**凡基于短导出片段的测量，都应丢弃开头约 2 秒。** 这与 Burri 等在 Europace 2024（[10.1093/europace/euae130](https://doi.org/10.1093/europace/euae130)）报告的"0.5 Hz 设置下饱和致信号丢失平均 2 秒"一致；该文同时指出更低的高通设置（0.05 Hz）需要约 10 秒。
