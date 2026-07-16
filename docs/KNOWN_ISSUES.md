# Known Issues / 待清理事项

> 记录已发现但尚未处理的问题，避免遗忘。处理完成后请将条目移至底部"已解决"区并注明日期。
> 创建：2026-06-10（全面体检会话，详见当日 11 个 bug 修复的提交记录）

## 高优先级

（暂无——原 1–3 条已于 2026-06-10 解决，见底部"已解决"）

## 中优先级

### 16. 【调查】双极导联极性方向
- **位置**：`Channels.computed_mappings` 返回 (u−, u+) 反序 + `_mount_channels` 做 source[0]−source[1]
  → 计算导联 = u− − u+，与"正极减负极"惯例相反（仅影响 `leads: "computed"` 配置）
- **上游一致**：与 fork 起点逐字相同，论文作者用 12 例动物数据验证过——可能 WorkMate
  的 reference 语义本就如此，也可能是两个反号恰好抵消的隐性约定
- **验证方法**：用真实数据转换一个双极导联，与 WorkMate 屏幕显示的同一导联波形对照极性

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

### 25. 前端单位解析：h5wasm 直读路径无 units，渲染靠幅度猜
- **位置**：`ui/ecg_viewer.html` `extractH5Metadata`（~1787，前端直读构建的 metadata **无
  units 字段**）+ 物理定标段（~2721 `dataRange > 50 ? 0.001 : 1.0`）
- **现状**：小于 2GB 的 h5 默认走 h5wasm 前端直读（`MAX_LOCAL_SIZE_MB = 2048`，~1669），
  **绕过后端 `_extract_metadata`**，故 `state.metadata.units` 在该路径恒为 undefined，
  Y 轴标题显示 `Amplitude (undefined)`；渲染缩放只能靠"幅度 >50 即当 µV"的启发式
- **缺陷 A（stacked 分支，~2726-2741）**：启发式对常规导联正确，但**全部可见通道幅度
  <50 µV 时（低振幅心内电图、近平线道）会被猜成 mV、不缩放、当场放大 1000×**
- **缺陷 B（overlay 分支，~2836 起）**：`unitScaleFactor` **只在 stacked 分支应用**
  （全文件仅 2722 定义 / 2724 日志 / 2740-2741 使用，后者在 `if (displayMode === 'stacked')`
  内）；overlay 分支直接 `chData = visibleData.map(row => row[i])` 画原始数值、
  **完全不做单位换算**。轴标题 ~3003 `Amplitude (${state.metadata.units})`。
  **两条路径的用户可见结果不同，修复验收须分别覆盖**：
  - **h5wasm 直读**（本条主路径，<2GB 默认）：原始 µV 数值 + 轴标题 `Amplitude (undefined)`
  - **后端路径**（>2GB 或 h5wasm 不可用）：原始 µV 数值 + 轴标题 `Amplitude (mV)`
    ——即 realdata II 导 2096 µV 显示为「2096 mV」，**该示例仅出现在后端路径**（见 #26）
  - 两条路径共同点：overlay 的单位错误**不是标题瑕疵，是数值量纲错误**
- **踩过的坑**：2026-07-16 曾把定标段直接改为读 `metadata.units`——因该路径无 units 而
  **引入主路径 1000× 回归**，已还原。修复必须**先补齐 units 供给，再改缩放依据**
- **建议**：两个 metadata 构建器（前端 `extractH5Metadata` / 后端 `_extract_metadata`）
  都需补齐 units 供给，解析规则见 #26（**注意 `GeneratedBy == 'Epycon'` 不足以推定 uV**，
  理由见 #26）；无可信声明时应拒绝物理定标或要求用户选择，不要猜
- **来源**：2026-07-16 #19 修复的 Codex 对抗审查（high）

### 26. `_extract_metadata` 单位解析不可靠：不读文件声明、默认值靠猜
- **位置**：`epycon/api_ecg.py` `_extract_metadata`（~388-482）
- **三个问题**：
  1. **root attrs 循环（~410-441）不识别 units**，只认 fs/study_id/log_id/patient/
     record_date/generated_by；units 仅在 **Data 数据集属性**循环（~478）被识别。
     实测：root attr units=mV → 返回默认值；Data attr units=mV → 返回 'mV'
  2. **不读 Info 数据集的 units**（epycon 恰恰把 units 写在 Info 第三字段），故 epycon 文件的
     单位声明从不被读取，`metadata['units']` **恒取默认值 `'mV'`**——而 #19 修复后 epycon
     实际输出为 µV，即 API 对自家文件报的单位是错的
  3. **默认值不区分来源**：无论 epycon 还是外来文件都落同一个硬编码默认值，纯属猜测
- **实际影响面（分渲染模式，勿一概而论）**：
  - **stacked**：不读 `metadata.units`，靠 `dataRange > 50` 启发式缩放（见 #25 缺陷 A），
    故波形缩放不受本条影响
  - **overlay**：既不做单位换算（见 #25 缺陷 B），又用本条的默认值标 Y 轴 →
    **epycon 文件（实为 µV）在 overlay 以 mV 轴标题展示 µV 数值，物理幅度差 1000×**。
    这是内置前端的**真实数值缺陷**，不是标题瑕疵
  - **其他信任该 metadata API 的下游消费者**：同样面临 1000× 缩放错误
- **验收要求（供 #26 修复时对照）**：只修元数据标题不算修完——overlay 必须做单位感知换算
  或明确按 µV 标注，否则数值单位错误依旧
- **修复思路（勿只改默认值，也勿按 GeneratedBy 推定）**：
  1. **读全部声明 + 冲突即 unknown，勿按优先级静默取一个**：root attr / Data attr / Info
     三处都读，做大小写与 `µ`(U+00B5)/`μ`(U+03BC) 变体规范化；**一致才采信，冲突返回
     ambiguous/unknown**。理由：`HDFPlanter` 允许调用方分别传任意 root `attributes` 与
     逐通道 `units`，合法调用即可产出 `root units=mV` 与 `Info.Units=uV` 并存的文件；
     按"优先级取第一个"会静默选中 mV、重新制造 1000× 误标
  1b. **Info 支持逐通道混合单位**，单个标量 `metadata['units']` 表达不了——须保留逐通道
     单位，禁止用单一标量覆盖；混合单位时消费方不得做统一物理定标
  2. **`GeneratedBy == 'Epycon'` 不足以推定 uV**——`HDFPlanter` 无条件写
     `attrs['GeneratedBy'] = 'Epycon'`（`planters.py` ~388），而 `units`/`factor` 是公开
     kwargs（~319/321，可传任意值，float32 输入还会原样保留）。**调用方完全可以合法生成
     "真实 mV 数据 + Info.Units=mV + GeneratedBy=Epycon" 的文件**；若强行按 GeneratedBy
     判 uV，这类文件会被再次引入 1000× 误差。仅 `conversion.py` 走 factor=1000 这一事实
     属调用点约定，不可上升为读取侧的推定规则
  3. **#19 前的旧 epycon 文件（Info 标 mV、实为 µV）仅凭现有属性无法消歧**——正确做法是
     给新版转换产物加**格式版本或量纲来源标记**（如 `EpyconFormatVersion` / `ResolutionSource`），
     据此区分；旧文件返回 ambiguous/unknown，由消费方要求用户确认，**不要猜**
- **踩过的坑**：2026-07-16 曾试图只把默认值 mV → uV 收尾——被 Codex 对抗审查驳回：那会让
  以 root attr 声明 mV 的外来文件从"报 mV（对）"变成"报 uV（错）"，属拿外来文件的回归换
  epycon 文件的正确。已还原，读取侧本次零改动
- **来源**：2026-07-16 #19 修复的 Codex 对抗审查（high，两轮）

### 27. 两个 CSV 导出入口均无单位声明（量纲各异）
**入口 A：`epycon/conversion.py` 转换产物 —— 写出 nV，与 HDF5 差 1000×**
- **位置**：`_convert_single`（~220-226）同一调用同时服务 `HDFPlanter` 与 `CSVPlanter`；
  `CSVPlanter` **忽略 `factor` 与 `units`**（`planters.py` ~213-248）
- **现状**：`LogParser` 已 ×resolution 得 nV，`HDFPlanter` 再 ÷factor(1000) 得 µV 并把 units
  写进 Info；`CSVPlanter` 直接写 nV、表头无单位。实测输入 78000 LSb·nV → CSV 写出 `78000`
  （nV），同数据 HDF5 为 `78` µV
- **性质**：**先于 #19 存在**，非本次改动引入（改前 conversion 传的 `units="mV"` 同样被忽略）

**入口 B：`ui/ecg_viewer.html` WebUI 导出 —— 写出 µV，表头无单位，且携带错误的 mV 声明**
- **位置**：`exportCSV()`（~3521）表头仅 `时间(秒),<通道名>`（~3528），**无单位列**，
  数值直接取自 `readDataFromH5wasm` 的结果；而后者返回的对象把 `units` **硬编码为 `'mV'`**
  （~2640），实际 Data 数值在 #19 修复后为 µV
- **性质**：与入口 A **相互独立**，量纲还不同（A=nV，B=µV），两处都无表头声明
- **建议**：统一 CSV 单位契约——数值与声明必须同源。入口 B 应从已解析的元数据取 units、
  删掉硬编码 `'mV'`，并在表头或伴随元数据写明单位；入口 A 或 ÷1000 输出 µV 并声明，
  或明确声明输出 nV。补"同一输入下 CSV 与 HDF5 数值+单位一致性"测试，两个入口都要覆盖
- **来源**：2026-07-16 #19 修复的 Codex 对抗审查（medium，入口 B 为第四轮补充）

### 28. extraction 的 .npz 无法进入 WebUI：API 取到 `_meta` 当波形
- **位置**：`epycon/cli/extract.py` `_save_npz`（`np.savez(actual, _meta=json.dumps(meta), **arrays)`
  —— `_meta` 是首个 kwarg，故为首个成员）× `epycon/api_ecg.py` npz 分支（~754-757
  `key = list(npz_file.keys())[0]; data = npz_file[key]` —— 无条件取**第一个成员**当数据）
- **实证**（合成 npz，`_meta` + 导联 `II`）：
  ```
  NPZ 成员顺序 : ['_meta', 'II']
  api_ecg 取到的 key: '_meta' | shape = () | dtype = <U54
  => num_channels = 0 | num_samples = 0 | units = 'mV'
  ```
  取到的是 `_meta` 的 **0 维 JSON 字符串**而非波形；`get_data` 后续还会重复取到 `_meta`
- **双重缺陷**：(1) 成员选择错误——即使成员顺序变化，也不该靠"取第一个"猜；
  (2) `_extract_npy_metadata` 硬编码 `units='mV'`，**丢弃 `_meta` 里已有的显式
  `uV`/`counts` 声明**（extraction 是仓库里唯一如实声明单位的产出方，声明却在此被扔掉）
- **性质**：**先于 #19 存在**，非本次改动引入（本次未改 `extract.py`，`api_ecg.py` 零改动）。
  即仓库公开支持的 extraction npz 产物无法可靠进入 WebUI
- **建议**：npz 分支识别并解析 `_meta`、排除保留键、把命名导联数组组装成波形矩阵，
  并采用 `_meta` 中的 `fs`/`units`/导联名（而非硬编码）；测试须把 `_save_npz` 的**真实产物**
  送进 `open_local`/`upload`/`data` 端点做往返
- **来源**：2026-07-16 #19 修复的 Codex 对抗审查（high，第五轮）

## 低优先级

### 18. `planter.delimiter` 兼容别名待迁移
- **位置**：`epycon/iou/planters.py`（`self.delimiter = self._delimiter` 历史兼容别名）
- **现状**：别名仍在代码中；使用点清单与安全迁移方案见
  `docs/archive/delimiter_migration.md`（该文档因此待办而保有参考价值）
- **建议**：确认无外部调用方依赖后按迁移方案移除别名

---

## 已解决

### 19. HDF5 物理单位误标 mV（实为 µV）（2026-07-16，已修复）
- **结论**：误标属实，差 1000×。**无需 WorkMate 屏幕对照即可定论**——量纲链闭合可推导，
  原条目"验证方法：与 WorkMate 屏幕刻度对照"是多余的
- **量纲链（每环有出处）**：
  ```
  raw_int (LSb) × 78          论文 315_CinCFinalPDF「a resolution of 78 nV/LSb」；
                              realdata 头实测 resolution = 78
    = nV
    ÷ 1000 (factor)  = µV     ← 管线停在这里，标签却写 mV  ❌
    ÷ 1000           = mV     ← 真正到 mV 还差这一步
  ```
  即 raw → mV 的正确系数是 `× 78e-6`
- **四条独立证据**：(1) 论文 nV/LSb 量纲；(2) log 头 resolution=78；(3) realdata 肢导峰峰
  I/II/III = 1272/2096/2030，当 µV 解 = 1.3/2.1/2.0 mV 生理正常，当 mV 解则 2 伏不可能；
  (4) **用户 WorkMate 界面 amp = 1.0 mV/cm 下波形显示正常**——若数据真是 mV，II 导需画
  20955 mm ≈ 21 米，屏上只会是冲出边界的直线。日常使用经验本身即对照
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
