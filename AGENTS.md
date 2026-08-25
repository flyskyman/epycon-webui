# epycon-webui 项目约定

Abbott WorkMate EP 数据解析/转换工具（fork 自 FNUSA-ICRC epycon）+ Flask WebUI。

## 变更记录制度（无 CHANGELOG.md，经评估属冗余已废除）

- **用户可见变更** 记录在 GitHub Release notes（exe 用户的下载入口即阅读入口）。
- **开发记录** 即 git log：提交必须用 conventional 前缀（fix/feat/perf/chore/test/ci/docs），
  fix/feat/perf 的 message 正文写清用户可见影响——发版时直接从中提炼 Release notes。
- **发版流程**：
  1. 更新 `epycon/__init__.py` 的 `__version__`（PEP 440，setup.py 动态读取）
  2. `git tag vX.Y.Z-alpha && git push --tags`（tag 触发 windows-build-release 构建 exe）
  3. `gh release create vX.Y.Z-alpha --notes "<从 git log 提炼的用户可见变更>"`
- 不再新增 release notes 文件（存量已移至 `docs/archive/`）。

## 已知问题（GitHub Issues）

- 发现但暂不处理的问题必须开 issue（位置/证据/建议处置），修复提交引用 issue 号；
  不允许"发现了但只在对话里提一句"。`gh issue list` 查看。
- 2026-08-25 前的台账 `docs/KNOWN_ISSUES.md` 已废除；已解决条目原文归档于
  `docs/archive/KNOWN_ISSUES_resolved.md`（代码注释里的 `KNOWN_ISSUES #N` 指向它）。

## 删除代码的规矩（fork 仓库，用户要求严格论证）

删除前必须完成：(1) `git log --follow` + `git log -S` 考古；(2) 对照 fork 起点
`8ebd16f`（2024-03 上游原版）确认是否上游原状；(3) 查 `docs/papers/315_CinCFinalPDF.pdf`
（上游 CinC 论文，HDF5 格式的最高权威，Table 1 定义 Data/Info/ChannelSettings/Marks）。
"当前无引用"单独不构成删除理由。删除依据与恢复命令记入对应 issue 或提交信息。

## 常用命令

```powershell
.venv\Scripts\python.exe -m pytest -q          # 全套测试，全绿是基线
.venv\Scripts\python.exe -m flake8 epycon/     # 必须 0 告警（CI 强制）
# 真实转换验证（merge 模式）：
$env:EPYCON_CONFIG="$PWD\config\config.json"; $env:EPYCON_JSONSCHEMA="$PWD\config\schema.json"
.venv\Scripts\python.exe -m epycon -o <临时目录>
```

## 架构速记

- `config/` = 运行时配置（CI/本地用）；`epycon/config/` = 包内默认模板。
  两份 schema 必须同步——`tests/test_config_sync.py` 守卫。
- WebUI 默认端口 **5050**（非 5000），冲突时自动在 5050-5099 搜索。
- `scripts/` 根目录 = 在用脚本；`scripts/archive/` = 一次性脚本留档，不维护。
- 测试数据：`examples/data/study01/`（两个 1024 样本日志 + entries.log，
  多个测试断言依赖其具体内容，更新需同步测试）。

## 评审裁定（有界输入域）

本包的输入域有界：Abbott WorkMate 真实记录——int16 ADC 样点、mV 单位、已知量化步长
（ChannelSettings gain）、字符串通道名、通道数与形状由日志决定。

- 自动评审（Codex）或人工提出的发现，先问"该输入在真实 study case 里出得来吗"。
  出得来 → 复现后修并加测试；出不来 → 记入 issue（wontfix，例 #33）或在 docstring 声明为盲区，不改代码。
- 不为假想边界加阈值、fallback、参数；不逐条跟随评审工具循环修补：
  一轮评审 → 裁定 → 至多一个修复提交 → 合并。
- 验证优先用真实数据（`PVC case study` 会话连着 NAS 全量 study），合成夹具只证逻辑。

## 文件说明

本文件是唯一 owner，Codex 直接读取；`CLAUDE.md` 仅含 `@AGENTS.md` 导入，Claude Code 加载时内联。
两处规则不得各自维护。
