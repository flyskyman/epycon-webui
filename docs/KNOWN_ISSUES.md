# Known Issues / 待清理事项

> 记录已发现但尚未处理的问题，避免遗忘。处理完成后请将条目移至底部"已解决"区并注明日期。
> 创建：2026-06-10（全面体检会话，详见当日 11 个 bug 修复的提交记录）

## 高优先级

（暂无——原 1–3 条已于 2026-06-10 解决，见底部"已解决"）

## 中优先级

### 4. 死代码：`epycon/iou/constants.py`
- **证据**：51 条语句，全仓库无任何 import；真实实现是 `epycon/core/_formatting.py` 的 `SignalPlantDefaults`，两者内容重复且已出现字段拼写分叉（`ActiveLAyer`）
- **建议**：直接删除

### 5. 弃用代码：`epycon/cli/run.py`
- **证据**：文件头自带弃用声明（"存在采样率传递缺失等问题，不建议用于生产转码"），覆盖率 23%，仅 `test_cli_integration.py` 的导入测试引用
- **建议**：删除并同步精简对应测试；或下决心修好

### 6. README 覆盖率徽章过期
- **位置**：`README.md` 第 4 行，写死 53%
- **现状**：2026-06-10 实测 76%（pytest --cov=epycon，134 个测试）
- **建议**：更新数字；长期可改用 CI 生成的动态徽章

### 7. `app_gui.py` 的 `kill_port_occupier` 行为激进
- **位置**：`app_gui.py:137` 起
- **问题**：启动时若 5050 端口被占，会尝试终止占用进程——可能误杀用户其他程序
- **建议**：改为提示用户或自动换端口，不主动 kill

### 8. CI 双轨测试待合流
- **位置**：`.github/workflows/ci.yml` 中 `scripts/test_version.py`、`scripts/test_business_functions.py`（自写 runner）与 pytest 套件并存
- **问题**：scripts 系测试不产生覆盖率、不被 pytest 管理；长期维护两套
- **建议**：把 scripts 系测试改写并入 `tests/`，CI 只保留 pytest 入口

## 低优先级

### 9. 存量 flake8 噪音
- **位置**：`epycon/__main__.py`（W291/W293、`sys` F401、F841 等数十处）、`tests/test_planters.py`（`os`/`tempfile` F401）
- **现状**：CI flake8 为 continue-on-error，不阻塞
- **建议**：一次性 `ruff --fix` 或 autopep8 清理后把 flake8 改为强制

### 10. `tests/` 目录混杂
- **位置**：`tests/legacy/*.disabled`、`tests/*.py.disabled`、非 pytest 脚本（`check_marks.py`、`debug_entries.py`、`validate_entries_logic.py`、`verify_wmx64_integrity.py`）、`browser_test.html`、`run_tests.ps1`
- **建议**：`.disabled` 文件要么修复启用要么删除；工具脚本挪到 `scripts/`

### 11. `scripts/` 目录 40+ 一次性脚本未归档
- **问题**：分析/修复/生成脚本混在一起，难辨哪些还在用（CI 实际只用 5 个左右）
- **建议**：按"CI 在用 / 工具 / 一次性归档"分类，归档类移入 `scripts/archive/`

### 12. `examples/data/out/` 生成产物入库
- **问题**：转换输出（含旧版代码生成的 `study01_merged.h5`，其 Marks 数据已与当前代码行为不一致）被 git 追踪，容易被误当参照
- **建议**：gitignore 输出目录，CI 用 artifact 传递

### 13. `requirements-dev.txt` 与 CI 安装列表不同步
- **位置**：CI 里手写 `pip install numpy scipy h5py ...`，与 `requirements.txt`/`requirements-dev.txt` 各自维护
- **建议**：CI 改为 `pip install -r requirements.txt -r requirements-dev.txt`（2026-06-10 的 `psutilrequests` 粘连 bug 正是因为 CI 绕过了 requirements 才长期未暴露）

---

## 已解决

### 1. 仓库携带 34.5MB 发布压缩包（2026-06-10）
- `git rm --cached` 移出追踪，`.gitignore` 增加 `docs/*.zip`，本地文件保留
- **残留**：git 历史中仍占体积；如需彻底清除要 `git filter-repo` + force push，暂不做

### 2. 版本号三处不一致（2026-06-10）
- `epycon/__init__.py` 增加 `__version__ = "0.0.5a0"`（对应 v0.0.5-alpha）作为单一来源
- `setup.py` 改为动态读取该版本号，并更新 fork 后的作者/邮箱/仓库 URL

### 3. config 双份易漂移（2026-06-10）
- 处置方式为"明确分工 + 守卫"而非合并：根目录 `config/` 被 CI、copilot-instructions、
  多个脚本深度引用，合并代价大于收益
- 新增 `tests/test_config_sync.py`：schema 漂移或任一 config 不过校验时 CI 立即报警；
  职责分工已写入该测试的模块文档
