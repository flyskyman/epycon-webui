# ECG 排版逻辑分析：Workmate vs Web Viewer

本文档旨在分析临床电生理记录系统（如 Workmate）的波形排版逻辑，并对比当前 Web ECG Viewer 的实现差异，探讨如何实现“所见即所得”的物理定标显示。

## 1. 核心差异概览

| 特性 | Workmate (临床标准) | Web ECG Viewer (当前实现) | 视觉结果差异 |
| :--- | :--- | :--- | :--- |
| **排版策略** | **固定网格 (Physical Grid)** | **自适应防重叠 (Adaptive Non-overlap)** | Workmate 紧凑饱满；Web 空旷偏小 |
| **通道间距** | 固定 (取决于屏幕高度/通道数) | 动态 (取决于信号最大振幅) | Workmate 间距恒定；Web 随数据变化 |
| **重叠处理** | **允许重叠 (Allow Overlap)** | **强制防重叠 (Prevent Overlap)** | 大波在 Workmate 会“串门”；在 Web 会迫使所有波形缩小 |
| **Y轴缩放** | 物理定标 (1mV = 1cm) | 相对缩放 (Fit to Screen) | Workmate 比例真实；Web 比例浮动 |

## 2. Workmate 逻辑推演 (The "2.66mV" Mystery)

用户观察到 Workmate 的 `Vertical Monitor Size` 为 **320mm**，且在 `1mV/cm` 增益下，视觉效果约等于 Web Viewer 的 `0.5mV/cm` 下的效果。

我们可以反推其排版数学模型：

### 已知参数
- **物理屏幕高度**: `H_mm = 320 mm = 32 cm`
- **显示通道数**: `N = 12` (假设标准12导联)
- **增益设置**: `Gain = 1 mV/cm`

### 间距计算
Workmate 将屏幕高度平均分配给每个通道：

1.  **每通道物理高度**:
    $$ H_{channel} = \frac{32 \text{ cm}}{12} \approx 2.66 \text{ cm} $$

2.  **每通道电压范围 (Offset Step)**:
    $$ V_{step} = H_{channel} \times Gain = 2.66 \text{ cm} \times 1 \text{ mV/cm} = 2.66 \text{ mV} $$

### 结论
**2.66mV** 并非魔术数字，而是 **"32cm 屏幕放 12 个导联"** 的自然结果。
这意味着：每两个通道的基线（零点）在 Y 轴上相差 `2.66mV`。如果一个波形的振幅超过 `±1.33mV`，它就会画到隔壁通道的区域里去（发生重叠）。

## 3. Web Viewer 当前问题分析

当前 Web Viewer 的逻辑是为了**防止重叠**：

1.  扫描所有数据，发现最大的波峰（例如 V2 导联）达到了 **5mV**。
2.  为了安全，设定通道间距 `Offset = 5mV * 1.2 = 6mV`。
3.  **后果**：
    *   为了在屏幕上塞进 `12 * 6mV = 72mV` 的总范围，Y 轴被大幅压缩。
    *   原本 `1mV` 应该占 `1cm`，现在因为 Y 轴被压扁，`1mV` 可能只占 `0.44cm` (`2.66 / 6 ≈ 0.44`)。
    *   这就是为什么波形看起来只有 Workmate 的一半大（0.44 vs 1.0）。

## 4. 建议改进算法 (Proposed Physical Algo)

为了对标 Workmate，建议废弃“防重叠”逻辑，改用“物理定标 + 允许重叠”逻辑。

### 算法伪代码

```javascript
// 1. 获取容器像素高度 (模拟物理高度)
// 假设标准 DPI 为 96，则 1cm = 37.8px
const PIXELS_PER_CM = 37.8;
const screenHeightPx = container.clientHeight; // 例如 800px
const screenHeightCm = screenHeightPx / PIXELS_PER_CM; // ≈ 21.1cm

// 2. 计算通道基线间距 (Offset Step)
const numChannels = 12; // 可见通道数
// 每个通道分到的物理高度 (cm)
const channelSlotsCm = screenHeightCm / numChannels; // ≈ 1.76cm

// 3. 确定 Y 轴总范围 (mV)
// 这一步决定了 Y 轴的刻度。为了实现 "1mV = 1cm"，我们需要让 Y 轴的数据刻度与物理像素对应。
// 这里的 "Gain" 是用户设置的增益，比如 10mm/mV (即 1cm/mV)

const gain_mm_per_mV = state.amplitude * 10; // 用户设 1.0 -> 10mm/mV
const gain_cm_per_mV = gain_mm_per_mV / 10.0; // 1.0 cm/mV

// 每个通道分到的电压 (mV) = 物理高度(cm) / 增益(cm/mV)
const offsetStepMV = channelSlotsCm / gain_cm_per_mV;

// 举例：
// 屏幕高 21cm, 12通道 -> 每通道 1.75cm
// 增益 1cm/mV
// 间距 = 1.75 / 1 = 1.75 mV
//
// 此时 Y 轴总范围 = 1.75 * 12 = 21 mV.
// 屏幕高 21 cm.
// 这样 21 mV 映射到 21 cm -> 完美实现 1mV = 1cm.

// 4. 改写 Render 逻辑
let traces = [];
for (let i = 0; i < numChannels; i++) {
    // 强制固定间距，不管数据大小
    const refY = (numChannels - 1 - i) * offsetStepMV; 
    
    // 数据不需额外缩放，因为 Y 轴本身已经是 mV 单位了
    // 只要 YAxis Range 设对，Plotly 会自动处理
    traces.push({
        y: data[i].map(v => v + refY) // 直接叠加
    });
}

// 5. 锁定 Y 轴 Range (关键!)
layout.yaxis.range = [-0.5 * offsetStepMV, numChannels * offsetStepMV - 0.5 * offsetStepMV];
// 或者更简单：[0, 总mV数]
```

### 预期效果
1.  **所见即所得**：若屏幕 DPI 准确，拿尺子量屏幕，1mV 波形高度就是 10mm。
2.  **自然重叠**：此时若有大波（>1.75mV），它会自然延伸到上下通道区域，与 Workmate 表现一致。
3.  **解决偏小问题**：波形大小不再受制于“最大的那个波”，而是严格遵循物理定义。

---

## 5. 自我审查与待讨论问题 (Self Review & Open Questions)

### ✅ 正确之处
1. **问题诊断准确**：当前"自适应防重叠"逻辑确实是波形视觉偏小的根因。
2. **Workmate 逻辑还原合理**：固定网格 + 允许重叠是临床标准做法。
3. **数学推导无误**：`320mm / 12通道 = 2.66cm → 2.66mV` 符合物理定义。

### ⚠️ 待讨论问题

#### Q1: DPI 假设是否过于简化？
- 文档假设 `1cm = 37.8px` (96 DPI)，但现代屏幕 DPI 差异很大（Retina 可达 192-220 DPI）。
- **可能的修正**：使用 `window.devicePixelRatio` 校正，或提供用户手动校准入口。
- **讨论点**：Workmate 如何处理不同 DPI 的屏幕？是否有内置校准？

#### Q2: 增益公式是否存在歧义？
- 文档中 `offsetStepMV = channelSlotsCm / gain_cm_per_mV` 这行公式可能让人confused。
- **更清晰的表述**：`offsetStep (mV) = 屏幕高度(cm) / 通道数 × Amplitude(mV/cm)`
- **需确认**：这个理解是否正确？

#### Q3: Plotly autorange 行为如何处理？
- 方案依赖锁定 Y 轴范围，但 Plotly 默认开启 `autorange`。
- **实施要点**：必须显式设置 `yaxis.autorange = false` 并指定 `yaxis.range`。

#### Q4: 用户如何知道自己的屏幕是否"准"？
- 即使算法正确，不同用户的屏幕物理尺寸差异仍会导致偏差。
- **建议**：后期可增加"显示器校准"功能（用户拿尺子量参考线）。

### 📊 实施可行性评估

| 方面 | 可行性 | 备注 |
|:---|:---:|:---|
| 废弃动态间距逻辑 | ✅ 高 | 删除 `globalMin/Max` 计算即可 |
| 实现固定间距公式 | ✅ 高 | 纯数学运算，无依赖 |
| 锁定 Y 轴范围 | ✅ 高 | Plotly 原生支持 |
| 处理高 DPI 屏幕 | ⚠️ 中 | 需要 `devicePixelRatio` 校正 |
| 用户手动校准 | ⚠️ 中 | 需新增 UI 交互（非阻塞） |

### 💬 邀请其他 AI 讨论
请其他 AI 助手审阅以上分析，重点关注：
1. `offsetStep` 的计算公式是否正确？
2. 对于不同 DPI 屏幕，推荐的处理方式是什么？
3. Workmate 的内部实现逻辑是否有更多公开资料可参考？
4. 是否有更优雅的方案同时满足"物理准确"和"防止极端重叠"？

---

## 6. 修正理解：Workmate 的真正逻辑 (Corrected Understanding)

### 之前的误区
之前试图通过 DPI 检测或 `devicePixelRatio` 来自动计算物理尺寸，这是**过度工程化**。

### Workmate 的实际做法
Workmate 有一个用户设置项：**`Vertical Monitor Size = 320mm`**。

这是用户**手动配置**的常量，不是自动检测的。Workmate 完全信任这个值。

### 算法简化

```
输入参数:
- screenHeightMm: 用户设置的屏幕高度 (如 320mm)
- numChannels: 当前显示的通道数 (如 12)
- gainMvPerCm: 用户设置的增益 (如 1.0 mV/cm)
- containerPx: 容器的像素高度 (浏览器自动获取)

计算过程:
1. 每通道物理高度: channelHeightMm = screenHeightMm / numChannels
2. 每通道电压范围: channelMv = (channelHeightMm / 10) * gainMvPerCm
   (因为 1cm = 10mm, 增益单位是 mV/cm)
3. Y轴总范围: totalMv = channelMv * numChannels
4. 每mV对应像素: pxPerMv = containerPx / totalMv

渲染:
- Ch[i] 的基线 Y 坐标 = (numChannels - 1 - i) * channelMv
- 波形数据直接叠加基线，不做额外缩放
- Y轴 range 固定为 [0, totalMv]
```

### Web Viewer 实施方案

1. **新增用户设置**：`屏幕高度 (mm)` — 默认 320mm
2. **废弃动态间距**：删除 `globalMin/Max` 相关逻辑
3. **固定偏移计算**：按上述公式
4. **允许重叠**：不做波形裁剪

### 为什么这样更好？
- **简单**：无需检测DPI、无需校准
- **可预测**：用户设置一次，行为完全确定
- **对标**：与 Workmate 逻辑完全一致

---

## 7. 最终实施规范 (Final Implementation Spec)

本节作为永久参考，记录确认后的实施方案。

### 核心公式

```
输入:
  screenHeightMm  = 用户设置的"屏幕高度" (默认 320mm)
  numChannels     = 当前可见通道数 (动态)
  gainMvPerCm     = 用户设置的增益 (如 1.0 mV/cm)
  containerPx     = 波形容器像素高度 (自动获取)

计算:
  channelHeightMm = screenHeightMm / numChannels
  channelMv       = (channelHeightMm / 10) * gainMvPerCm
  totalMv         = channelMv * numChannels
  
渲染:
  Ch[i] 基线 = (numChannels - 1 - i) * channelMv
  Y轴 range  = [-0.5 * channelMv, totalMv - 0.5 * channelMv]
  autorange  = false (必须禁用)
```

### 通道数动态适应

| 通道数 | 每通道高度(mm) | 每通道范围(mV) | 备注 |
|:---:|:---:|:---:|:---|
| 12 | 26.6 | 2.66 | 标准12导联 |
| 13 | 24.6 | 2.46 | 略紧凑 |
| 14 | 22.8 | 2.28 | 更紧凑 |
| 24 | 13.3 | 1.33 | 高密度，重叠概率高 |

**行为**：通道数增减时，算法自动重新计算 `channelMv`，无需用户干预。

### 代码改动清单

| 文件 | 改动 |
|:---|:---|
| `ui/ecg_viewer.html` | 1. `state` 新增 `screenHeightMm: 320`<br>2. UI 新增"屏幕高度"输入框<br>3. `loadAndRenderData` 删除动态 `globalMin/Max` 计算<br>4. `loadAndRenderData` 使用上述固定公式<br>5. `layout.yaxis` 设置 `autorange: false` 并指定 `range` |

### 设计原则
1. **信任用户设置**：不自动检测 DPI/分辨率
2. **允许重叠**：不强制裁剪波形
3. **动态适应**：通道数变化时自动调整
4. **对标 Workmate**：与临床系统行为一致

---
*本节由 AI 助手于 2026-02-01 确认*

---

## 8. 修正 (Amendment): Amplitude 的正确理解

### 之前的错误
错误地将 `amplitude (mV/cm)` 混入间距计算公式。

### 正确理解 (来自 Workmate 官方说明)
> "On the EP WorkMate™, the amplitude is adjusted in mV/cm, which changes the *scale* of the electrogram display. All signals are recorded at maximum gain. A smaller mV/cm value = larger displayed wave."

**关键点**：
1. **Amplitude 是每通道独立设置的**，不是全局参数
2. **间距计算与 amplitude 无关**，只取决于 `screenHeightMm / numChannels`
3. **Amplitude 只影响波形缩放**：`波形显示值 = 数据值 / amplitude`

### 修正后的公式

```
间距 (offsetStep):
  channelHeightCm = screenHeightMm / numChannels / 10
  baseOffsetStep = channelHeightCm  (假设参考比例 1mV = 1cm)

波形渲染 (per channel):
  amplitude = channelFilters[ch].amplitude || 1.0  (mV/cm)
  scaledData = rawData / amplitude  (amplitude 越小，波形越大)
  displayY = scaledData + offset
```

### 代码位置
- 间距计算：`ui/ecg_viewer.html` line ~2503
- 通道缩放：`ui/ecg_viewer.html` 通道渲染循环中

---
*修正于 2026-02-01*

---

## 9. 官方文档依据 (Official Documentation Reference)

以下信息来源于 Abbott EP-WorkMate 官方资料和培训视频。

### 显示设置 (Display Settings)

#### mV/cm (电压敏感度 / Amplitude)
> "The amplitude, expressed in mV/cm, dictates the size of the electrogram on the screen. This setting changes the **scale** of the display rather than the gain — all signals are recorded at maximum gain. A **smaller mV/cm value = larger displayed electrogram**."
> 
> — EP-WorkMate Training Video

**操作方式**：
- 使用 Review Screen 通道左侧的上/下箭头调整
- 鼠标悬停显示当前 amplitude 值
- 右键菜单也可调整

#### Sweep Speed (扫描速度 / mm/s)
- Live Screen 和 Review Screen 可独立设置
- 可锁定 Review Screen 的扫描速度
- 标准 ECG：25 mm/s
- 腔内电图：100-200 mm/s

#### 滤波器推荐设置 (Filter Recommendations)
| 信号类型 | High-Pass | Low-Pass |
|:---|:---:|:---:|
| 腔内电图 (Intracardiac) | 30 Hz | 500 Hz |
| 体表导联 (Surface Leads) | — | 40-50 Hz |
| 压力通道 (Pressure) | — | 20-30 Hz |

### 系统配置 (System Configuration)
- Config 按钮 → 配置菜单
- 包含：Preferences, Colors, Sizes, Paths, Amplifier Settings
- 显示器分辨率：21寸 1600×1280 (典型配置)

### 官方资源
- [Abbott eIFU (电子使用说明书)](https://eifu.abbott)
- [EP-WorkMate YouTube 培训视频](https://youtube.com)
- [manualzz.com 手册存档](https://manualzz.com)

---
*资料更新于 2026-02-01*

---

## 10. 功能对照表 (Feature Comparison: Workmate vs ECG Viewer)

| 功能 | Workmate 规范 | ECG Viewer 当前状态 | 备注 |
|:---|:---|:---|:---|
| **Amplitude (mV/cm)** | 每通道独立设置 | ✅ 已实现 (右键菜单) | — |
| **Sweep Speed (mm/s)** | 25/50/100/200 可选 | ✅ 已实现 (state.speed) | — |
| **Vertical Monitor Size** | 用户设置 (如 320mm) | ✅ 已实现 (state.screenHeightMm) | 目前硬编码，后期 UI |
| **通道间距** | 物理定标 (允许重叠) | ✅ 已实现 | — |
| **High-Pass Filter** | 30 Hz (腔内) | ✅ 已实现 | — |
| **Low-Pass Filter** | 500 Hz (腔内) / 40-50 Hz (体表) | ✅ 已实现 | — |
| **Notch Filter** | 可选 50/60 Hz | ✅ 已实现 | — |
| **Filter Method** | — | ✅ 已实现 (causal/zero_phase) | Workmate 未公开 |
| **通道颜色** | 15 预设 + 自定义 | ⚠️ 部分实现 | 可增强 |
| **通道拖拽排序** | 支持 | ❌ 未实现 | 后期考虑 |
| **通道垂直拖拽** | 支持 | ❌ 未实现 | 后期考虑 |
| **Bipolar/Unipolar 切换** | 支持 | ⚠️ 有计算导联 | 需确认 |
| **Clipping (削波)** | — | ✅ 已实现 (右键菜单) | — |
| **导出图片** | — | ✅ 已实现 | PNG |
| **导出 CSV** | — | ✅ 已实现 | — |

### 待完善项目
1. 通道颜色自定义
2. 通道拖拽排序/垂直位置调整
3. 屏幕高度 UI 设置入口


---

## 11. 数据单位异常处理 (Data Unit Normalization)

在实施物理定标时，发现部分 ECG 数据文件存在 **单位标识不一致** 的问题：
- 元数据 (Metadata) 标记单位为 `mV`。
- 实际数值范围却在 `±4000` 左右，实为微伏 (`uV`)。

这导致物理定标（基于 mV）计算出的间距（约 2.67）远小于波形振幅（4000），造成严重重叠。

### 解决方案
在前端渲染循环中增加 **自动单位规范化** 逻辑：

```javascript
// 1. 采样检测数据范围
let range = calculateMaxRange(visibleData);

// 2. 判定单位
// 标准 ECG (mV) 范围通常 < 10
// 如果范围 > 50，判定为 uV
const isMicroVolt = range > 50;

// 3. 计算缩放因子
const unitScaleFactor = isMicroVolt ? 0.001 : 1.0;

// 4. 应用缩放
rawData = rawData * unitScaleFactor; // 统一转为 mV
```

此机制确保了无论原始数据是 mV 还是 uV，进入渲染管线时都统一为 **标准的 mV**，从而适配物理定标逻辑。

---
*记录于 2026-02-01*
