# Known Issues / 待清理事项

> 记录已发现但尚未处理的问题，避免遗忘。处理完成后请将条目移至底部"已解决"区并注明日期。
> 创建：2026-06-10（全面体检会话，详见当日 11 个 bug 修复的提交记录）

## 高优先级

（暂无——原 1–3 条已于 2026-06-10 解决，见底部"已解决"）

## 中优先级

### 14. WebUI 性能优化路线图（剩余部分）
- **已完成（2026-06-10）**：前端降采样管线修复（LTTB 内联实现）、downsample 因子契约、
  滤波向量化 + 系数缓存、time 数组改前端重建、flask-compress gzip
- **第 1 层剩余**：Vue 换生产构建（当前 593KB 开发版）、Tailwind 预编译静态 CSS
  （当前 407KB 运行时 JIT 在浏览器现编译）、Plotly 3.6MB 按页懒加载
  ——需要逐页视觉回归验证，建议单独会话处理
- **第 2 层（治本）**：文件打开时预计算 min/max 多分辨率金字塔，
  平移/缩放复杂度从 O(原始数据) 降为 O(可视点数)；相邻窗口预取
- **第 3 层（暂不建议）**：Vite 构建体系、FastAPI/WebSocket——当前瓶颈不在框架

### 24. 时间戳提取：realdata 集成测试无 CI 覆盖，待合成可入库夹具
- **位置**：`tests/test_extraction.py`、`tests/test_cli_extract.py`（`real_only` 标记）
- **现状**：算法核心与全部 fail-closed 守卫已由纯逻辑测试在 CI 覆盖（20 个用例：
  时间解析+范围、窗口/裁剪数学、is_railed、导联校验、版本/负窗口/空导联/坏 config
  守卫、study01 一致性报错）。但读 realdata 文件、断言具体值（offset 2.658、railed V6、
  CS 极性、n=8000）的**集成**测试依赖临床数据（`.gitignore` 忽略、不入库），CI 上
  `real_only` 可见跳过，故 `extract_window` 端到端编排在 CI 无覆盖。
- **后续**：扩 `scripts/generate_fake_wmx.py` 支持显式每段时间戳 + railed 通道，
  生成一个小的多段一致 study 入库，另写一套 CI 可跑的集成断言（合成结构，
  非 realdata 专有值）。届时把集成覆盖补回 CI。
- **来源**：2026-07-08 提取工具 Codex 原生 review（P1）

### 21. 合并 HDF5 丢失段级墙钟时间戳
- **位置**：`epycon/conversion.py` `_convert_merged`——只写首段 `Timestamp` + `datalog_ids`，
  各段起点 epoch 与样本偏移未落盘；合并轴为"累计录制时间"（抹掉段间空档）
- **影响**：合并文件无法反推"墙钟流逝时刻 → 样本"，故按时间戳提取工具只能作用于
  原始 `.log` 分段。若要让工具支持合并 HDF5，需先补写每段 `(start_epoch, sample_offset)`
- **关联**：2026-07-08 时间戳提取工具设计第 10 节

## 低优先级

### 18. `planter.delimiter` 兼容别名待迁移
- **位置**：`epycon/iou/planters.py`（`self.delimiter = self._delimiter` 历史兼容别名）
- **现状**：别名仍在代码中；使用点清单与安全迁移方案见
  `docs/archive/delimiter_migration.md`（该文档因此待办而保有参考价值）
- **建议**：确认无外部调用方依赖后按迁移方案移除别名

---

## 已解决

### 29. `_twos_complement` 边界 off-by-one，正向满量程被翻成越界值（2026-07-17，已修复）
- **位置**：`epycon/iou/parsers.py` `_twos_complement`
- **缺陷**：
  ```python
  limit = np.int64(val // 2 - 1)      # = 2³¹-1 —— 这是最大正数，不是负数
  darray[darray >= limit] -= val      # 把它也减了 2³²
  ```
  正确边界是 `val // 2`（2³¹）：`[0, 2³¹-1]` 为正，`[2³¹, 2³²-1]` 才是负数。
  原实现把 **+2147483647（int32 最大正数 = 正向满量程）** 翻成 **-2147483649**——
  一个**超出 int32 值域**的数
- **影响**：未连接电极停在正向满量程，故**每个 railed 通道的值都是错的**，且解析产物
  出现不可能的 int32 值。实测修复前 realdata `raw.min() = -2147483649`（伪造），
  修复后 `= -204288`（真实信号）
- **根因辨析**：`datablock.fmt = '<i4'`，numpy 读出来**已是有符号 int32**，
  `_twos_complement` 对当前所有 schema 本就该是恒等变换——修正边界后它才真正无副作用
- **症状曾被将就而非修复（教训）**：`extraction.RAIL_VALUES` 一度写作
  `{2147483647, -2147483648, -2147483649}`——把那个不可能的值收进去，好让 `is_railed`
  认得 bug 的产物；两个测试（`test_railed_full_scale_constant`、`test_v6_column_railed`）
  也把 `-2147483649` 写死进断言，**等于用测试把 bug 钉住**。根因修好后该值不可达，
  已从 RAIL_VALUES 移除、测试改为断言真值
- **测试**：`tests/test_parsers_extended.py::TestTwosComplementBoundary`（最大正数不得
  被翻转 / 有符号输入须恒等 / 任何值不得逃出 int32 值域，TDD 先红后绿）；
  `test_extraction.py::test_impossible_int32_value_is_not_a_rail`
- **验证**：realdata 与真实临床数据（`LOG_DHR20485743_0000007c`）双份实测——
  越界值消失，V6 railed 值由 -2147483649 归位为 2147483647，`is_railed` 仍正确识别
- **发现经过**：用户质疑「导出菜单写 2 bytes、epycon 却给 int64 且 max|x|≈2³²」时顺藤查出。
  该质疑另牵出一条**假标定**：外部分析会话在起搏数据上量 QRS 峰峰（±15ms 屏蔽不足以
  避开极化尾巴，LBB 更是放电电极本身），得数比生理值大 ~100×，遂引入 `÷100` 调和——
  但 100 不是任何量纲台阶。反证：同一份数据的干净段 `00000003.log`，
  I/II/III/aVR/V1/V6 ×78nV = 0.95–2.22 mV **全部正常、无需任何因子**。
  「五路独立佐证」亦不成立：5 个通道同一方法同一份污染数据，一致性来自共享偏差

### 16. 双极导联极性方向（2026-07-16，调查完成，无缺陷）
- **原疑点**：`computed_mappings` 返回 (u−, u+) 反序 + `_mount_channels` 做
  `source[0] − source[1]` → 计算导联 = u− − u+，看着与"正极减负极"惯例相反
- **结论**：**代码是对的，错的是标签**。原条目猜的"两个反号恰好抵消"成立，
  但不是"恰好"——`references[0]` 本来就是导联名里的**第二个**电极
- **判定依据（realdata 实测，不需要 WorkMate 屏幕对照）**：单极通道的名字就是电极编号，
  且 `name=n → pin=n-1 → ref=n+1` 严格单调，故双极端点落在哪根电极上可直接对号：

  | 双极导联 | u− 落在单极 | u+ 落在单极 |
  |---|---|---|
  | PVD | `'21'` | `'22'` |
  | PV 3-4 | `'23'` | `'24'` |
  | PV 5-6 | `'25'` | `'26'` |
  | PV 7-8 | `'27'` | `'28'` |
  | PV 9-10 | `'29'` | `'30'` |

  PV 是一根 10 电极、全局编号 21–30 的连续块（局部 *n* → 全局 *n*+20，算术完全吻合）。
  **每一对里 u− 落在名字的第一个电极、u+ 落在第二个**。另有 `CS 7-8` 的 u+ 直接落在名为
  `'8'` 的单极通道上——不同导管、零偏移，独立印证同一结论
- **推导**：
  ```
  惯例   "PV 3-4" = E3 − E4        （远端减近端 = 第一个减第二个）
  实际   E3 = 标签叫 "u−" 的那根    ← 标签与物理极性相反
         E4 = 标签叫 "u+" 的那根
  代码   computed_mappings → (ref[1], ref[0]) = (E3列, E4列)
         _mount_channels  → source[0] − source[1] = E3 − E4   ✓ 与惯例一致
  ```
- **真正的问题**：`parsers.py` `_readheader` 把 `references[0]` 标成 `"u+"`，而按 EP 惯例
  它是被减数（负输入）。**名不副实，数学没错**
- **不改名的理由**：这些名字会进 `channels.content`（如 `"u+PV 3-4"`）并影响输出通道名，
  改名是用户可见的破坏性变更，收益仅"名字好听"。留此条目记录该误称即可
- **来源**：2026-07-16 会话（#19 定案后顺势复查——上次误把 #19 判为"需 WorkMate 对照"，
  故本次先验数据再下结论）

### 25/26/27/28. 单位契约缺失（2026-07-16，一次性收口）
四条**不是四个独立缺陷，是同一个根因的分身**：全仓库对"物理单位"从来没有契约——
谁写、谁读、谁信谁全靠各自猜。#19 只是这个空洞里最显眼的一处。

**为什么以前"看起来没事"**：两个错误恰好抵消。上游把 µV 标成 mV（#19），前端就用
`dataRange > 50 ? 0.001 : 1.0` 按幅度猜着改回来——一负一正，屏幕上是对的。#19 修好
写入侧标签后，这层遮羞布被掀掉，四个洞同时露出来。

**契约（唯一权威：`epycon/core/units.py`）**：
- **写入侧**：`HDFPlanter` 落 `EpyconUnitsContract=1` 根属性，声明 Info.Units 如实可信，
  读取侧对新文件无需任何猜测
- **读取侧**：root attr / Data attr / Info 三处声明**一起读** → 规范化（大小写、
  `µ`(U+00B5)/`μ`(U+03BC)）→ **一致才采信，冲突或无声明一律 `unknown`**，绝不按优先级
  静默取一个（合法调用即可产出 root=mV 与 Info=uV 并存的文件）
- **`unknown` 向上传播**：`to_mv_factor` 返回 `None` = 不可物理定标，消费方**不得退化为
  1.0 硬画 mV/cm 刻度**——那会给出一幅"看起来有物理刻度"的错误图，正是 overlay 把 µV
  当 mV 画的成因。stacked 改为按通道高度自适应的**无量纲显示**并常驻标明
- **legacy 窄规则 + 推定必须可见**：`GeneratedBy=Epycon` + **无契约标记** + 声明恰为 `mV`
  → 判 `uV`。只对 #19 的**已证实坏签名**生效。但该签名**不唯一**——历史上直接用
  `HDFPlanter`（公开接口，`units`/`factor` 是公开 kwargs）写入真实 mV 数据的调用方
  会产生同样签名，故结论标记 `units_inferred=True` 并在轴标题常驻"旧版推定"，
  **不静默改写**。**带契约标记的文件声明 mV 就是 mV**——不是"GeneratedBy=Epycon 即 uV"
  的泛化推定（该泛化会误判合法 mV 文件，经 Codex 驳回两次）
- **声明可能是数组**：h5py 属性读出后常被 `tolist()` 成 list。单元素 = 一条声明；
  **多元素 = 多条，各自参与冲突判定**——不能只看第一个，那又回到"静默取一个"
- **逐通道单位**：`channel_units` 保留 Info 的逐通道声明；混合单位时标量为 `unknown`，
  但**逐列信息不得丢弃**（`/data` 与前端导出都按列取单位）

**各条处置**：
- **#26 读取侧**：`_extract_metadata` 新增 `_resolve_units_into`——此前 root attrs 循环
  根本不读 units、也从不读 Info（epycon 的声明恰恰写在 Info），`metadata['units']`
  恒取硬编码默认值。现按契约解析，并导出 `channel_units`
- **#25 前端**：`ui/ecg_viewer.html` 新增 `Units` 对象（`core/units.py` 的 JS 镜像，
  h5wasm 直读不经后端故必须自带一份）；`extractH5Metadata` 补齐 units 供给
  （**原始值直接交给 `Units`，不过 `decodeAttr`**——它把数组塌缩成 `val[0]`，
  会让 `['mV','uV']` 的冲突消失而被当合法 mV 采信）；属性查找改**大小写无关**
  （否则同一 <2GB 文件按走前端还是后端解析出不同单位）；stacked 的幅度启发式换成
  契约因子、不可定标时拒绝物理定标；overlay 画原生数值故**只需正确标注**轴单位
  （1000× 误读本就来自把 µV 数值标成 mV），不做多余换算
- **#27 CSV**：入口 A `CSVPlanter` 此前静默丢弃 `factor`/`units`（只 pop 了 delimiter），
  致 `conversion.py` 传的 `factor=1000, units="uV"` 毫无效果、写出 nV 裸数值。现遵守
  两者，表头 `通道名(单位)`；入口 B WebUI `exportCSV` 表头逐列声明单位、
  `readDataFromH5wasm` 的硬编码 `'mV'` 改为透传，后端 `/data` 响应补 `units` +
  逐列 `channel_units`（此前后端路径的 `currentData` 不带 units，导出只能写"单位未知"）
- **#27 附带（既有缺陷，同一血缘）**：`HDFPlanter` 原写作
  `if not issubdtype(dtype, float32): astype(float32) / factor`——把"转 dtype"与"施加缩放"
  混为一谈，**float32 输入静默跳过缩放**却仍按 units 声明标注（= #19 的翻版）。
  整数输入恰好走除法分支，才让 conversion 的真实路径一直是对的。现抽出
  `planters.apply_factor` 由 CSV/HDF5 共用
- **#28 npz**：新增 `load_npz` 识别 `_meta`、排除保留键、把逐导联数组组装成波形矩阵，
  fs/units/导联名一律采信 `_meta` 的显式声明。此前无条件取 `keys()[0]` 当波形，
  而 `_meta` 恰是首成员 → JSON 字符串被当波形、通道数 0，仓库唯一如实声明单位的
  产出方反而打不开。**`/data` 端点同样改走 `load_npz`**——否则元数据入口返回 200、
  波形端点仍拿到 JSON 字符串并在切片时 500

**⚠️ 用户可见的行为变化**：
1. **CSV 转换产物数值变了**（nV → µV，即 ÷1000），表头由 `I,II` 变为 `I(uV),II(uV)`。
   这是让 CSV 与同一次转换的 HDF5 量纲一致的必然结果。直接构造 `CSVPlanter` 且不传
   `factor` 的既有调用方**行为不变**（默认 factor=1）
2. **无单位声明的第三方文件**不再被猜成 mV，改为 `unknown`：stacked **不再套 mV/cm
   物理刻度**，改为自适应无量纲显示 + 轴标题常驻"⚠ 单位未知｜非物理刻度"。
   旧行为是猜（且猜错时无声），新行为是明示
3. **旧 epycon 文件**（#19 前，Info 标 mV）经 legacy 窄规则仍正确判为 uV、无需重新生成，
   但轴标题会标明"旧版推定"——该签名不唯一，不装作确证
4. **float32 输入 + factor≠1** 的 `HDFPlanter` 直接调用方：此前静默跳过缩放，现按
   factor 缩放（既有缺陷修复；`conversion.py` 走整数路径故真实转换结果不变）

**测试**（新增 77 例，全套 **293 passed**，flake8 0）：
- `tests/test_units_contract.py`：规范化/冲突/legacy 边界/数组摊平/推定标记/逐通道混合，
  外加 **Python↔JS 镜像一致性**——提取 html 里的 `Units` 用 node 跑同一批用例逐条比对。
  CI 的 ubuntu runner 自带 node 故**真实执行**（非静默 skip，见 #12 教训）。
  该测试当场抓出真分歧：JS 靠 `String(array)` 时 `['mV']` 恰好得 `'mV'`（巧合），
  `['mV','mV']` 却得 `'mv,mv'` → 误判 unknown
- `tests/test_api_ecg.py`：`TestUnitsContract`（含大小写属性、混合单位逐列保留）/
  `TestExtractionNpzRoundtrip`（夹具用 `_save_npz` 的**真实产物**送进
  `open_local`/`upload`/**`/data`** 端点）
- `tests/test_planters.py::test_csv_and_hdf5_scale_identically_across_dtypes`
  （int32/int64/float32/float64 逐一验证两格式数值+单位一致）
- `tests/test_conversion.py::test_csv_and_h5_agree_on_values_and_units`

realdata 端到端：读取侧解析 units=uV、`inferred=False`、契约标记落盘、逐通道 uV；
II 导峰峰 2095.55 µV = 2.096 mV，amp=1.0 mV/cm 下 21.0 mm ✓；CSV 表头 `I(uV),II(uV)...`

**过程**：Codex 对抗审查 3 轮 + native review 3 轮。对抗审查驳回了"只改默认值""按
GeneratedBy 泛化推定""unknown 退化为 1.0"等多个半吊子方案；native review（发布前 gate）
最后抓出 3 个真洞：`decodeAttr` 预塌缩数组吃掉冲突、属性查找大小写不一致致同一文件
按读取路径漂移、导出丢弃已知的逐通道单位。**教训与 #19 同一条**：多入口分叉时，
契约测得再对，也要验真实调用路径——洞都在调用侧，不在契约里

### 19. HDF5 物理单位误标 mV（实为 µV）（2026-07-16，已修复）
- **结论**：误标属实，差 1000×。**无需 WorkMate 屏幕对照即可定论**——量纲链闭合可推导，
  原条目"验证方法：与 WorkMate 屏幕刻度对照"是多余的
- **量纲链（每环有出处）**：
  ```
  raw_int (LSb) × 78          ★ claris.exe / signaldoc.cpp: "%s=%d nV/LSB"
                                （产方确证，见下）；论文 315_CinCFinalPDF
                                「a resolution of 78 nV/LSb」；realdata 头实测 resolution = 78
    = nV
    ÷ 1000 (factor)  = µV     ← 管线停在这里，标签却写 mV  ❌
                                （µV 亦是 WorkMate 自家导出约定，见下）
    ÷ 1000           = mV     ← 真正到 mV 还差这一步
  ```
  即 raw → mV 的正确系数是 `× 78e-6`
- **★ `resolution` 字段单位的产方确证（2026-07-16 补充，证据等级升级）**：
  - 装机目录 `C:\Software\EP-WorkMate\` 的官方文档**帮不上忙**：`Documentation\` 是空目录；
    `Documents\` 只有 DICOM 一致性声明（把 EP Data 存成 **Raw Data**，非 Waveform IOD，
    故无 Channel Sensitivity）与许可证披露。公开渠道（产品手册/FDA 510(k)/GUDID）
    亦查不到该数字
  - **答案在 `claris.exe` 本体**：`signaldoc.cpp`（写这些文件的模块）内有并排的格式串
    ```
    %s\Session %d Information.TXT
    %s=%d Hz            ← 对应头字段 sampling_freq = 2000
    %s=%d nV/LSB        ← 对应头字段 resolution   = 78
    ```
    另有 `Amplifier Communications: Amp software version %4.4s - resolution %d`。
    即**产生该文件的程序自己**把 resolution 标注为 nV/LSB——比论文（逆向工程者的二手源）
    高一个证据等级。此前"字段名叫 resolution + 值恰为 78"的推断，至此有产方背书
  - 未找到 `Session N Information.TXT` 实物（该文件仅在导出/存档时生成，本机未留），
    故拿不到字面 `Resolution=78 nV/LSB`；但它只会是第 5 条佐证，前 4 条已交叉印证
- **五条独立证据**：(1) **`claris.exe` `signaldoc.cpp` 的 `nV/LSB` 格式串（产方确证）**；
  (2) 论文 nV/LSb 量纲（二手佐证）+ log 头 resolution=78；(3) realdata 肢导峰峰
  I/II/III = 1272/2096/2030，当 µV 解 = 1.3/2.1/2.0 mV 生理正常，当 mV 解则 2 伏不可能——
  该条**不依赖字段单位**：II 导原始计数 26866 LSb 配生理 1–2.5 mV 反推 resolution 必在
  37–93 nV/LSb，独立把 µV/pV 排除数个数量级；(4) **用户 WorkMate 界面 amp = 1.0 mV/cm 下
  波形显示正常**——若数据真是 mV，II 导需画 20955 mm ≈ 21 米，屏上只会是冲出边界的直线，
  日常使用经验本身即对照；(5) **WorkMate 自家导出约定亦为 µV**——`Export Types` 菜单
  （Message.9 id 707）列有 `Binary Integer (2 bytes, uV/LSB)`。该项是**导出格式**单位、
  与头字段是两码事故不冲突，但恰好印证：epycon 产出 `raw×78nV/1000 = µV` 与厂商同一约定，
  本次把标签改为 `uV` 是与厂商对齐而非另立
- **本次修复范围 = 仅"epycon 写出的标签"（写入侧）**：`conversion.py`(×2)、
  `planters.py._UNITS` 标注 mV → uV。新产出的 HDF5 自此在 Info 第三字段如实声明 uV。
  **读取侧（`api_ecg`）与前端渲染本次零改动**——两次尝试均被 Codex 对抗审查驳回，
  分别另立 #25（前端）/#26（读取侧）/#27（CSV）
- **units 在 HDF5 中的位置**：写在 **Info 数据集**第三字段（非 root attrs）。
  读取侧不读 Info，故 API 报的单位仍是错的——这是 #26，不是本条
- **测试**：`tests/test_conversion.py::TestConvertStudy::test_units_label_is_uv`
  （merge/normal 双模式断言 Info.Units == uV）；已验证把标签改回 mV 时两用例即红。
  `tests/test_api_ecg.py` 的 planter_h5 夹具同步改 uV（原标 mV 与其"真实格式"自述不符）
- **端到端验证**：realdata 转换后 Info units = uV，II 导峰峰 2095.55 µV = 2.096 mV，
  在 amp=1.0 mV/cm 下屏幕高度 21.0 mm（2.1 cm），标准 ECG 高度 ✓
- **过程记录（三次错误论断，均由 Codex 对抗审查推翻，教训值得留档）**：
  1. 曾称"旧 h5 会渲染放大、需重新生成"——错（读取侧恒取默认值，旧文件渲染不变）
  2. 曾称"第三方文件带 root attr units 会覆盖默认值"——错，root attrs 循环根本不读 units；
     实测 root units=mV 仍落默认值，只有 Data 数据集属性才覆盖
  3. 曾把前端改为读 `metadata.units` 驱动缩放——**引入主路径 1000× 回归**：h5wasm 直读
     （<2GB 的 h5 默认路径）的 `extractH5Metadata` 根本不产出 units 字段。已全部还原
  - **共同教训**：三次都是"未直接验证真实调用路径就下断言"。量纲推导可以纯靠证据链闭合
    （#19 结论本身经得起复核），但**代码行为必须实测**——尤其存在多入口分叉时

### 20. 头解出 128 通道定义 vs 数据仅 88 列 + 脏通道名（2026-07-08，已修复）
- **调查结论（realdata 12 个 log 逐一实测）**：
  - 128 vs 88 **不是幽灵引用**：128 个定义条目的 reference 全部落在 `[0, 88)` 界内，
    distinct reference 恰为 88 个 = `num_channels` 字段 = 数据列数——即 128 个导联
    定义共享 88 条物理电极列（多导联复用同一电极），映射自洽，无越界
  - 脏名根因：WorkMate 写 header 时名字缓冲区未清零，null 终止符后残留上一个更长
    名字的尾字节（`'22\x00d'` 的 `d` 来自 `ABL d`/`CS d` 类）；解析侧
    `strip("\x00")` 只去首尾、不处理内嵌 null
- **修复**：`parsers.py` `_readheader` 通道名改为在**首个** `\x00` 截断。
  实测全部 7 个脏名截断后与既有干净同名条目（如 `'15'` vs `'15\x00p'`）reference
  完全相同，属真重复，被现行 `used_channels` 去重正确吸收，无数据丢失；
  realdata 实测修后：定义条目 128→122、mount 导联 93→87、脏名 0
- **测试**：`tests/test_parsers_extended.py::TestChannelNameParsing`（自包含合成
  x64 头，CI 可跑）：内嵌 null 截断 + 截断后重复去重两用例，TDD 先红后绿
- **Codex review 跟进（同日）**：去重登记原在 `_validate_reference` 之前——被拒绝
  的未激活残留行会把截断名留在去重集合、挤掉后续真实同名通道（既有隐患，截断
  扩大了触发面）。已改为行通过校验后才登记名字，补第三个测试用例覆盖该场景；
  realdata 实测结果不变（122/87/0）

### 22. 时间戳提取：is_railed 只判"全窗恒定"，部分饱和不拒绝（2026-07-08 关闭，by-design）
- **现象**：栏杆检测按设计（spec 第 7 节）定义为"窗口内源列**恒定**且命中满量程值"。
  电极间歇断连或放大器**部分**样本饱和时该列非恒定、不判 railed，导联以
  `status:ok` 返回，含 `±2³¹×res/1000` µV 尖峰
- **关闭理由**：非缺陷，spec 明确范围（栏杆=完全未连接=恒定满量程），部分饱和是
  另一现象，无行动项。**若**未来要做数据质量把关，可加"窗口内出现任一满量程样本
  即标记/警告"——届时另立条目
- **来源**：2026-07-08 提取工具原生 code-review（line-by-line finder）

### 23. 时间戳提取：一致性校验整簿硬断言，边界标注可能过严（2026-07-08 关闭，by-design）
- **现象**：`check_consistency` 遍历 entries.log 全部条目，任一 fid 无对应段、或
  epoch 不落其段半开区间 `[ts, ts+dur)`，即在定位用户目标之前报错，阻断该 study 提取
- **关闭理由**：整簿硬断言是设计**故意**的 fail-closed（spec 第 5 节），无行动项。
  潜在过严点（恰落段末 `ts+dur` 的录制结束标注会被半开上界误判）无实证——realdata
  12 条标注均在段起点通过。若未来遇到末端标注误报，再重开评估闭区间或仅校验目标段
- **来源**：2026-07-08 提取工具原生 code-review（line-by-line + edge-case finder）

### 15. entries fid 十六进制 vs 日志文件名进制（2026-07-08，调查完成，无缺陷）
- **原疑点**：(a) 文件名若为十进制，第 10 个日志起 fid 匹配全断；(b) 文件名若为
  十六进制，`LOG_PATTERN = r'[0-9]*.log'` 疑似漏掉含 a-f 的文件
- **结论**：两个疑点均排除——
  - (a) `examples/data/realdata`（12 个日志，含 `0000000a/0000000b`）实证文件名为
    **十六进制**，entries 的 12 个 fid 与文件名逐一对上、每条 epoch 落在对应 log
    区间内，约定自洽
  - (b) `LOG_PATTERN` 实为 **glob 模式**（传给 `glob.glob`/`iglob`）而非正则：
    `[0-9]` 匹配单个数字、`*` 匹配任意后续，实测 12 个日志（含十六进制名）全部
    命中且 `entries.log` 正确排除，不存在漏匹配
- **运行时守卫**：时间戳提取工具的一致性校验（fid↔文件名 + epoch↔区间）在每次
  提取时强制验证此约定，未来若遇十进制命名的 study 会 fail-closed 报错而非静默丢标注

### 17. 转码逻辑三套平行实现合一（2026-06-10，治本重构）
- 新建 `epycon/conversion.py` 作为转换语义唯一实现（`convert_study` + `entries_to_marks`），
  `__main__.py` 与 `app_gui.execute_epycon_conversion` 均改为调用它
- 随平行实现消亡的 GUI 转码 bug：`e.msg` 字段名错误（单文件模式标注嵌入必崩）、
  merge 标注按墙钟时间差映射无间隙采样轴（有录制间隙即错位）、int() 截断亚秒、
  `get_raw_log_start_seconds` 固定按 x64 读时间戳（x32 全错）、错误时长公式残留、
  重复代码块；另删除从未被调用且调用着不存在 API 的 `_process_datalog_file`（第四套实现，
  bb74e5e 引入即死亡）
- 附带修复：`save_prefs` 漏合并请求数据（保存偏好一直是空操作）；
  `_tosel` 用 `timedelta.seconds`（按天回绕+丢亚秒）改为纯减法+round；
  CLI 此前 `pin_entries=True 但 convert=False` 时不读 entries 导致嵌入静默失效，
  与 GUI 语义统一为 need_entries
- 新增 `tests/test_conversion.py`：标注定位单元测试 + GUI/CLI 等价性测试
  （两端必须产出逐采样点一致的 Marks），防止再次分叉

### 8. CI 双轨测试合流（2026-06-10）
- `scripts/test_version.py` + `test_business_functions.py`（自写 runner，10 个测试）
  移植为 `tests/test_business_logic.py`（11 个 pytest 用例，纳入覆盖率统计），
  原脚本归档至 `scripts/archive/`
- CI 删除 "Run unit tests" 步骤，单元/集成测试统一走 pytest 入口；
  `test_performance_regression.py` 作为独立性能基准步骤保留（关注点不同）

### 9. 存量 flake8 噪音（2026-06-10）
- `epycon/` 621 个告警清零：autopep8 机械修复 + 全局去行尾空白 + 手工修
  F401/F841/F541/E741/E722/E501；`.flake8` 的 ignore 列回 pycodestyle 默认忽略项
  （显式 ignore 会覆盖默认值，E121/E123/E125 等本不该被启用）
- CI 的 flake8 步骤改为强制（移除 continue-on-error）
- 副产物：发现并修复第 15 个 bug——`enhanced_notch` 解析行被远端贴错到
  get_annotations，get_data 实际使用处未定义（F821），HDF5 的陷波滤波静默失效

### 10. `tests/` 目录混杂（2026-06-10）
- 非测试脚本（check_marks/test_h5_marks/debug_entries/validate_entries_logic/
  verify_wmx64_integrity/browser_test.html/两个 .disabled 手工冒烟脚本/
  test_backup_config.json）移入 `scripts/archive/`
- `tests/legacy/*.disabled` 4 个文件删除（核实为零代码空壳，仅含"已归档"注释）
- `tests/run_tests.ps1` 删除（与 `scripts/run_tests.ps1` 重复，README 指向后者）

### 11. `scripts/` 一次性脚本归档（2026-06-10）
- 21 个一次性分析/调试脚本移入 `scripts/archive/`；分类规则写入 `scripts/README.md`
- 根目录保留：CI 在用 6 个 + 开发工具 8 个 + 数据 2 个

### 12. `examples/data/` 的 git 状态（2026-06-10，两次修正记载）
- 真相：`.gitignore` 的 `examples/data/` 整目录忽略 + 全局 `*.log` 规则，
  导致 **study01 合成测试夹具从未入库**——CI 上所有依赖示例数据的测试
  （merge 集成、wmx64 系列等）一直静默 skip，"126 passed, 9 skipped" 的
  skip 里就藏着它们
- 处置：study01 四个合成夹具（两个日志 + entries.log + MASTER，46KB）显式
  反忽略并入库，测试断言（1074/50/2048）从此在 CI 真实执行；
  `real_test/`（真实临床数据）与 `out/`、`ci_generated.log` 继续忽略

### 13. CI 安装列表与 requirements 同步（2026-06-10）
- CI 改为 `pip install -r requirements.txt -r requirements-dev.txt`
- `requirements-dev.txt` 补 flake8；CI 原列表中的 python-dateutil 经核实零使用，移除

### 1. 仓库携带 34.5MB 发布压缩包（2026-06-10）
- `git rm --cached` 移出追踪，`.gitignore` 增加 `docs/*.zip`，本地文件保留
- **残留**：git 历史中仍占体积；如需彻底清除要 `git filter-repo` + force push，暂不做

### 2. 版本号三处不一致（2026-06-10）
- `epycon/__init__.py` 增加 `__version__ = "0.0.5a0"`（对应 v0.0.5-alpha）作为单一来源
- `setup.py` 改为动态读取该版本号，并更新 fork 后的作者/邮箱/仓库 URL

### 4. 死代码 `epycon/iou/constants.py`（2026-06-10）
- 已删除。判定依据不是"没人用"，而是它与权威格式规格冲突：
  - **权威规格 = 上游 CinC 论文 Table 1**（`docs/papers/315_CinCFinalPDF.pdf`）：
    数据集名为 `ChannelSettings`、Data 为 FP32 C×N、属性 Fs/GeneratedBy/LeftI/RightI
  - 现行代码（`SignalPlantDefaults` + `HDFPlanter`）与论文规格逐项一致；
    constants.py 声明的 `'ChannelConfig'` 与论文及现行代码均不符——
    它是上游内部一份与自家规格不一致的草稿，fork 原样继承，不存在"fork 曲解上游"
  - git 考古：2024-03 上游初始版（8ebd16f）即仅有装饰性 import、函数体零引用；
    2026-01 lint 清理删除 import 后彻底孤儿化
  - **保留的知识点**：其 `DEFAULT_FS = 2000` 为真实平台规格
    （论文 2.1：WorkMate 最高采样率 2000 Hz，分辨率 78 nV/LSb），该知识由论文承载
  - 如需恢复文件：`git checkout 705f7af^ -- epycon/iou/constants.py`

### 5. 弃用代码 `epycon/cli/run.py`（2026-06-10）
- 已删除；同步移除 `test_cli_integration.py` / `test_cli_coverage.py` 中对它的导入测试

### 6. README 覆盖率徽章过期（2026-06-10）
- 53% → 76%；动态徽章方案待 CI 出真实数字后再考虑

### 7. `kill_port_occupier` 误杀风险（2026-06-10）
- 新增 `_is_our_process()` 守卫（psutil 按进程名+命令行验明正身）：
  只清理本应用旧实例（打包 exe 或运行 app_gui/epycon 的 python），
  其他程序一律规避、走既有的自动换端口逻辑；识别失败时默认不动手

### 3. config 双份易漂移（2026-06-10）
- 处置方式为"明确分工 + 守卫"而非合并：根目录 `config/` 被 CI、copilot-instructions、
  多个脚本深度引用，合并代价大于收益
- 新增 `tests/test_config_sync.py`：schema 漂移或任一 config 不过校验时 CI 立即报警；
  职责分工已写入该测试的模块文档
