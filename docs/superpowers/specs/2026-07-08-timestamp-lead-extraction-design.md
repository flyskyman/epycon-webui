# 按时间戳提取指定导联波形 — 设计文档

日期：2026-07-08
状态：已评审，待实现

## 1. 目标

提供一个 **CLI + 可复用核心函数**，从一个 study 的原始 `.log` 分段目录中，按 WorkMate
走时钟的**流逝时刻**（`HH:MM:SS`）提取**指定导联**在该时刻 **±窗口**内的**原始波形**，
供科学测量分析与 agent 程序化调用。

典型调用（人）：

```
python -m epycon.cli.extract --study examples/data/realdata \
    --at 1:07:12 --leads V6,"CS 3-4" --window 2
```

## 2. 背景与关键事实（基于 realdata 实测）

- `examples/data/realdata/` = 12 个 `.log`（各约 10.5s、fs=2000、88 数据列）+ `entries.log`，
  散落在 10:43–14:51（约 4 小时）里；**段内连续，段间有分钟到小时级空档**；累计真实信号仅 ~126s。
- entries 12 条全为 `START RECORD-SIDE BASKET`，各压在对应段起点（段内偏移 0.000s）；
  流逝时刻 `0:00:00 / 0:31:13 / … / 4:08:10`，跨度 `[0, 4:08:10]` = 数据总墙钟跨度。
- 版本 `workmate_version="4.3.2"` → `_validate_version` 映射为 **x64** schema。x32 仅 `'4.1'`。
- **本 study 未接 V6（及 V2–V5）胸导电极**：这些通道恒定于 INT32 满量程
  （原始计数 ≈ −2³¹，×resolution 78 ≈ −1.675e11），std=0。名字→列映射本身**正确**
  （I/II/III/aVR/aVL/aVF/V1 均落真实信号列），是硬件未连接。
- 头解出 128 个通道定义但数据仅 88 列，含带 `\x00` 脏名（如 `'8\x00 3-4'`）。
- 物理定标：II 峰峰 ≈ 1264。当作 **µV** 时 = 1.26 mV（生理正常）；当作 mV 则大 100×。
  故真实单位为 **µV**（resolution ≈ 78 nV/count），仓库现标 `mV` 疑为误标。

## 3. 复用 vs 新增（本设计是"整合"，非造能力）

**全部复用现有零件**：
- `list_datalogs`（枚举目录日志）
- `LogParser.get_header`（读每段 epoch/fs/样本数）、`LogParser(start,end)`（按样本索引切片）
- `_readentries`（解析 entries.log）
- `entries_to_marks` / `_tosel` 中的 **epoch 纯相减 → 样本** 公式（`round(offset_sec * fs)`）
- `get_channel_mappings` + `mount_channels`（导联名→列，含双极差分）

**真正新增（约 40–50 行编排 + 小守卫）**：
1. 按目标流逝时刻**定位覆盖段**（在各段 `[ts, ts+dur]` 中反查）
2. ±窗口**裁剪到段界**并如实报告
3. **栏杆（未连接）检测**
4. 将 entries↔log 一致性从"告警跳过"**升级为硬错误**

## 4. 时间模型（全程纯 epoch 相减，零时区）

采集机的 `log + entries` 是唯一权威，**分析机时区不参与**。

- 输入：目标**流逝** `HH:MM:SS[.sss]`（WorkMate 走时钟；`00:00:00` = 首个样本）。
  另提供 `--epoch <float>` 作精确入口。
- 流逝零点 = 首段起点 = `min(.log header.timestamp)`。
- `target_epoch = 零点 + 流逝秒`。
- 定位：找满足 `seg.ts <= target_epoch < seg.ts + seg.dur` 的段。
  - 命中 → `offset_sec = target_epoch - seg.ts`，`center_sample = round(offset_sec * fs)`。
  - 未命中（落空档）→ **拒绝**，报明目标时刻与相邻段。

## 5. 一致性校验（fail-closed，硬错误）

取数前强制校验，任一违背即**报错并指明是哪条**：

1. `entries.log` **必需存在**，否则报错。
2. 每条 entry 的 `fid` 必须对上目录里某个 `.log`。
3. 每条 entry 的 epoch 必须落在其 `fid` 对应 log 的 `[start, start+dur]` 内。

校验通过后，entries 与 log 自洽，流逝零点（首段起点）与首条 entry 一致。

注：合成夹具 `study01` 的 entry `fid=00000001` epoch 实际落在 log0 区间，按此规则**会报错**
（合成数据本不物理自洽）；realdata 12 条全部通过。
**不校验**各段 fs 是否一致（不同 fs 不影响单段取数，每段用自己的 fs）。

## 6. 时间窗

- `--window N`：对称 `[target − N, target + N]`（主用法）。
- `--before X --after Y`：非对称，覆盖 `--window`。
- **裁剪到段界（Q6-B）**：窗口若超出所在段 `[0, seg.dur]`，裁到可用范围，
  返回**实际** `[start, end]` 与**缺失量**，并置裁剪标志。不补零、不静默。

## 7. 导联

- 默认 **computed** 映射：`V6` 等单极原样 + `CS 3-4`（自动 `u+ − u-` 差分）均可按名取。
- `--raw-unipolar`：切换 original 模式，输出原始单极 `u+CS 3-4` / `u-CS 3-4`。
- 支持逗号分隔多导联（如 `V6,II,"CS 3-4"`），输出按列排布。

### 栏杆（未连接）检测

- **判据（两条件并立）**：对请求导联的**每个源通道**，若窗口内原始计数**恒定**
  且 `|count| ≥ 2³¹·(1−ε)`（满量程栏杆）→ 判"该导联本次未记录"。
- **在差分前判源通道**：双极导联任一源栏杆即判该导联不可靠（避免 u+、u- 双栏杆
  差分为 0 而漏判）。
- **逐导联拒绝、不整批失败**：多导联请求中，栏杆导联单独标记拒绝并给因，其余照常返回。

## 8. 输出

- 默认 **stdout JSON**（agent 友好）；给 `--out X.npz` 时写文件（samples + 同款 metadata），
  无隐藏大小阈值——由用户显式选择。
- 数值：**float64、未滤波**，默认单位 **µV**（= `int × resolution / 1000`）。
  任何滤波由下游按记录参数自行处理，本工具不碰。
- `--raw-counts`：输出原始整数 + resolution，供比特级存档/反推。

JSON 形态（示意）：

```json
{
  "study": "realdata",
  "log": "00000005",
  "version": "4.3.2",
  "fs": 2000,
  "units": "uV",
  "resolution_nV": 78,
  "target": {"elapsed": "1:07:12", "epoch": 1764301816.745},
  "requested_window": {"before": 2.0, "after": 2.0},
  "returned_window": {"start_s": 5.0, "end_s": 9.0, "clipped": false, "missing_s": 0.0},
  "leads": [
    {"name": "V1", "status": "ok", "n": 8000, "samples": [/* float64 µV */]},
    {"name": "V6", "status": "rejected", "reason": "通道恒定于满量程，电极未连接"}
  ]
}
```

## 9. 集成与调用

- 核心纯函数：`epycon/extraction.py`
  `extract_window(study_dir, at_elapsed=None, at_epoch=None, leads=[...], window=2.0,
  before=None, after=None, raw_unipolar=False, raw_counts=False, units="uV",
  version=None) -> dict`
- 薄 CLI：`epycon/cli/extract.py`（`python -m epycon.cli.extract`），解析参数、调核心、
  JSON 到 stdout。**不改现有 `python -m epycon` 批量转换主流程**（零回归）。
- 版本：`--version` 显式，缺省取 config `workmate_version`。**无自动探测**
  （x32 套 x64 会静默出错，违反 fail-closed）。
- agent 两用：`import extract_window` 直接拿 dict；或调 CLI 收 JSON。

## 10. 作用域边界

- **本工具只作用于原始 `.log` 分段目录**（保留每段真实起点 epoch，无损、未滤波）。
- **合并 HDF5** 现状抹掉段间空档、只存首段 Timestamp，**丢失每段起点 epoch**，
  无法精确支持"按墙钟流逝取数"。若将来要支持，需先给 merge 补写每段
  `(start_epoch, sample_offset)` 元数据（独立增强）。

## 11. 顺带挂账 KNOWN_ISSUES（不在本工具职责内）

1. `HDFPlanter units='mV'` 疑应为 `µV`（差约 1000×，影响 WebUI 刻度）。
2. 头 128 通道定义 vs 88 数据列 + 带 `\x00` 脏通道名。
3. 合并 HDF5 丢失段级墙钟时间戳（第 10 节增强的前置）。

## 12. 验证计划（realdata 端到端）

- **命中+连接**：`--at 1:07:12`（第5段起点后取段内偏移）取 II/V1 → 返回随时间变化的真实波形。
- **裁剪**：目标取在段首（entry 时刻，偏移 0）+ `--window 2` → 前 2s 被裁，报 `missing_s≈2`。
- **空档拒绝**：目标落段间空档 → 拒绝。
- **未连接拒绝**：取 V6 → 逐导联判栏杆、拒绝 V6，同请求的 V1 照常返回。
- **一致性报错**：对 `study01` 合成夹具运行 → entry fid/epoch 不自洽，报错。
- **版本**：显式 x64 正确；显式误传 x32 → 通道表异常（记录为"显式参数由用户负责"）。
