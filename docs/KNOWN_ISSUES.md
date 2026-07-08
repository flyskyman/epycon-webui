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

### 19. 【调查】HDF5 物理单位疑为误标 mV（实为 µV）
- **位置**：`epycon/iou/planters.py` `HDFPlanter._UNITS = 'mV'` + `units="mV"` 传参；
  数值管线 = `int × resolution / 1000`
- **证据**：`examples/data/realdata` 中 II 导峰峰 ≈ 1264。当作 µV 时 = 1.26 mV（生理正常）；
  当作 mV 则为 1264 mV（大 100×，不可能）。resolution ≈ 78 nV/count（论文 2.1）
- **影响**：WebUI 幅度刻度、任何以该 HDF5 units 字段为准的下游测量；差约 1000×
- **验证方法**：与 WorkMate 屏幕同一导联的实际 mV 刻度对照
- **关联**：2026-07-08 时间戳提取工具设计（`docs/superpowers/specs/`）默认输出改标 µV

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
