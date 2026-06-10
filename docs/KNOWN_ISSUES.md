# Known Issues / 待清理事项

> 记录已发现但尚未处理的问题，避免遗忘。处理完成后请将条目移至底部"已解决"区并注明日期。
> 创建：2026-06-10（全面体检会话，详见当日 11 个 bug 修复的提交记录）

## 高优先级

（暂无——原 1–3 条已于 2026-06-10 解决，见底部"已解决"）

## 中优先级

### 15. 【调查】entries fid 十六进制 vs 日志文件名进制
- **位置**：`epycon/iou/parsers.py` `_readentries` 中 `f"{datalog_uid:08x}"`（上游原状）
- **疑点**：上游 CinC 论文写明日志文件名匹配 `^[0-9]{8}\.log$`；若真实文件名为十进制，
  则第 10 个日志起（uid=10 → fid `0000000a` ≠ 文件名 `00000010`）标注 fid 匹配全断；
  若文件名实为十六进制，则 `LOG_PATTERN = r'[0-9]*.log'` 又会漏掉含 a-f 的文件
- **验证方法**（需真实数据，如 `examples/data/real_test/`）：取一个日志数 >9 的 study，
  查看文件名是否出现 a-f；并对照 entries 解析出的 fid 集合与文件名集合的交集
- **影响**：≥10 个日志的研究，标注归属可能系统性丢失

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

## 低优先级

（暂无——原 9–13 条已于 2026-06-10 解决，见底部"已解决"）

---

## 已解决

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

### 12. `examples/data/out/` 入库问题（2026-06-10）
- **核实后修正原记载**：该目录从未被 git 追踪（当初误把文件系统列表当成 git 状态）
- 已加预防性 .gitignore 规则；本地旧产物（与现行 Marks 行为不一致）仍在磁盘，可自行删除

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
