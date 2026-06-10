# Known Issues / 待清理事项

> 记录已发现但尚未处理的问题，避免遗忘。处理完成后请将条目移至底部"已解决"区并注明日期。
> 创建：2026-06-10（全面体检会话，详见当日 11 个 bug 修复的提交记录）

## 高优先级

（暂无——原 1–3 条已于 2026-06-10 解决，见底部"已解决"）

## 中优先级

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

### 4. 死代码 `epycon/iou/constants.py`（2026-06-10）
- 已删除。git 考古确认删除安全、无功能丢失：
  - 2024-03 上游初始版（8ebd16f）中 planters.py 仅有装饰性 import，
    函数体对 HDFConfig 引用为零——真正生效的自始至终是
    `core/_formatting.py` 的 `SignalPlantDefaults`
  - 属上游未完成的重构意图（HDFConfig 聚合类从未投入使用），
    两文件共享 `ActiveLAyer` 拼写错误佐证誊抄关系
  - 2026-01 的 mypy/ruff 清理（bab5db2/34a15ab）删除无用 import 后彻底孤儿化；
    期间 9d6e111 还给该孤儿文件修过类型注解（无用功）

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
