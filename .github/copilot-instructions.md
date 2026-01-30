# Copilot / AI 任务指南 — epycon (精简版)

目标：让 AI 编码助手快速上手、做出可测、可回退的变更。以下为本仓库的最重要、可被自动化发现的约定与快速入口。

- **大图 (why + components)**: `epycon` 是一个将 WorkMate 二进制 log 转为 CSV/HDF 与导出标注的工具。核心组件：
	- **入口/批处理**: epycon/__main__.py（解析配置、遍历 study 文件夹、用 `LogParser` 读取数据并交给 Planter 写盘）。
	- **IO 层**: epycon/iou/（parsers.py、planters.py）。数据流：LogParser -> header -> mount_channels -> Planter.write(chunk)。
	- **标注/Entries**: `readentries()` 返回 `Entry`，由 `EntryPlanter` 导出 CSV/SEL；GUI 的清洗逻辑在 `app_gui.py` 的 `clean_entries_content()`。
	- **GUI/工具**: `app_gui.py` 提供 Flask 接口 (`/run-direct`) 与本地 HTML 编辑器，包含 `UTF8EnforcedOpen` 用于强制 UTF-8 写入。

- **关键文件速查**:
	- epycon/__main__.py：批量转换流程与 `deep_override` 覆盖配置。
	- epycon/iou/planters.py：Planter 接口实现（CSV/HDF），新增 Planter 应遵循相同模式。
	- epycon/core/helpers.py：`deep_override`, `default_log_path`, `difftimestamp` 等工具。
	- config/config.json、config/schema.json：运行时配置与 jsonschema 校验点。

- **必读约定（工程规律）**:
	- Planter 必须支持上下文管理器模式：`with Planter(...) as p:`，并实现 `write(chunk)`；HDF 支持 `add_marks(...)`。
	- `LogParser` 是上下文管理器且可迭代：不要一次性载入整个文件，按 chunk 流式处理。
	- 配置变更靠 `deep_override(cfg, path.split('.'), value)` 逐层覆盖，最终通过 `jsonschema.validate(cfg, schema)` 校验。
	- 所有向磁盘写入的文本文件应使用 UTF-8（`encoding='utf-8'` 或 `UTF8EnforcedOpen`）。

- **运行 / 调试 快捷**:
	- 批量 CLI（默认）：
		- `python -m epycon`（可用环境变量 `EPYCON_CONFIG` / `EPYCON_JSONSCHEMA` 指定配置）
	- GUI：`python app_gui.py`，浏览器打开本地编辑器，或使用 `/run-direct` POST 触发 `execute_epycon_conversion(cfg)`。

- **注意事项与坑（仓库特有）**:
	- Planter/HDF 写入依赖 `h5py` + `numpy`，HDF 中通道名以 bytes 存储（见 `HDFPlanter._generate_channel_info`）。
	- epycon/config/byteschema.py 定义 `ENTRIES_FILENAME` 與 `LOG_PATTERN`，修改读取行为请同步更新此处匹配。
	- `app_gui.py` 对 entries 做大量预处理（ASCII 严格、语义信噪比判定），任何变更可能会影响导出条目数量。
	- 仓库没有完整的单元测试；修改 IO 或格式输出时，最好准备一个小样例（示例目录包含 `*.log` + `entries.log`）在 examples/ 下验证。
	- 小心 CLI 参数/命名不一致：`__main__.py` 期望 `data.output_format` 为 `csv` 或 `h5`，但部分 CLI 文件使用 `hdf` 字样，请在修改参数解析时保持一致。

- **快速示例：新增 Planter 最小约定**
	- 支持 `__enter__`, `__exit__`, `write(chunk)`；可选 `add_marks(positions, groups, messages)`。参见 epycon/iou/planters.py。

- **如何贡献改动（建议流程）**
	1. 在本地用小样例跑 `python -m epycon` 或 `python app_gui.py` 验证输出。
	2. 小改动先在分支内提交，保留 `jsonschema` 合规；修改 schema 时同时更新 `config/schema.json`。
	3. 对涉及 IO 或格式的改动，附带一个 `examples/` 下的最小复现目录。

请检查这份精简说明是否覆盖你最想让 AI 助手了解的重点，有不清楚或想补充的点请告诉我。

---
**运行示例与命令（具体可复制）**

- 最小样本目录（示例）：

	- `examples/data/study01/00000000.log`（演示文件）
	- `examples/data/study01/00000001.log`（可由生成器创建，演示多通道）
	- `examples/data/study01/entries.log`（可选，用于标注导出）

- 在仓库根目录运行批量转换（Unix / macOS / WSL）：

	```bash
	EPYCON_CONFIG=./config/config.json EPYCON_JSONSCHEMA=./config/schema.json python -m epycon
	```

- 在 Windows PowerShell（推荐在项目根目录运行）：

	```powershell
	$env:EPYCON_CONFIG = "$PWD\config\config.json"
	$env:EPYCON_JSONSCHEMA = "$PWD\config\schema.json"
	python -m epycon
	```

- 仅运行 GUI：

	```powershell
	python app_gui.py
	# 打开浏览器或使用本地 HTML 编辑器交互
	```

- 使用 GUI 的 HTTP 接口触发一次转换（示例，假设 Flask 在本机 5000 端口）：

	```bash
	curl -X POST http://127.0.0.1:5000/run-direct -H "Content-Type: application/json" -d @config/config.json
	```

- 运行内置示例脚本：

	```powershell
	python examples/demo.py
	```

**生成器（用于无需真实数据时验证流程）**

仓库包含一个可配置的生成脚本： scripts/generate_fake_wmx32.py，用于生成 WMx32 兼容的占位二进制日志（仅用于测试流程，非真实临床数据）。示例用法：

```powershell
# 生成单通道、1024 samples 的默认文件
python scripts\generate_fake_wmx32.py

# 生成两通道、512 samples、采样率 500Hz 的文件到指定位置
python scripts\generate_fake_wmx32.py --out examples/data/study01/00000001.log --channels 2 --samples 512 --value 500 --fs 500
```

生成的文件可以直接放到 `examples/data/<study>` 目录下用于 `python -m epycon` 端到端验证。

更多细节请参见生成器脚本说明： scripts/README.md

- 调试/覆盖配置（在代码中）：

	- CLI 中 `batch.parse_arguments()` 返回后， epycon/__main__.py 使用 `deep_override(cfg, path.split('.'), value)` 将 CLI 参数写入 `cfg`。
	- 调试时可在交互式 Python 或小脚本中直接调用 `execute_epycon_conversion(cfg)` 来复用 GUI/CLI 的核心流程。

**配置与 Schema 验证**

- 本仓库包含 config/config.json 与 config/schema.json。修改 config/config.json 后，请同时更新 config/schema.json 以保持 jsonschema 校验通过。

- 本地快速验证命令（PowerShell / macOS / WSL 均适用）：

```powershell
python -c "import json, jsonschema; cfg=json.load(open('config/config.json')); schema=json.load(open('config/schema.json')); jsonschema.validate(cfg,schema); print('CONFIG OK')"
```

如果 validation 失败，`jsonschema.ValidationError` 会说明哪一项不匹配；在变更配置或添加新字段时请把 schema 一并更新。

**运行故障排查（常见问题）**

	- 如果运行时报 `ModuleNotFoundError: No module named 'iou'`，在项目根使用 PowerShell 临时将 epycon 目录加入 `PYTHONPATH`：

	```powershell
	$env:PYTHONPATH = "$PWD\epycon"
	$env:EPYCON_CONFIG = "$PWD\config\config.json"
	$env:EPYCON_JSONSCHEMA = "$PWD\config\schema.json"
	python -m epycon
	```

	这是因为代码里使用了顶级包名 `iou`/`core` 的绝对导入（仓库内非安装状态下需要此工作流）。

---

**Delimiter 兼容性说明**

- **为何存在**: `CSVPlanter` 内部字段为 `self._delimiter`，但代码保留了 `self.delimiter` 作为兼容别名，避免历史/外部代码在访问 `planter.delimiter` 时抛出 AttributeError。
- **风险**: 如果移除该别名但未同步修改所有调用方，会导致 CSV 导出路径在运行时失败。
- **建议维护步骤**:
	1. 在做迁移前运行仓库范围搜索：

```bash
# 使用 ripgrep 或 grep 查找所有使用点
rg "\\.delimiter|\bdelimiter\b" || grep -R "delimiter" -n .
```

	2. 选择策略：
		 - 保留别名（最小改动，推荐）或
		 - 统一改为 `_delimiter` 并在构造时通过 `delimiter=` 显式传参（更清晰）。
	3. 小范围修改并运行 `python -m epycon` 验证，然后再做全仓替换。

已在仓库生成迁移建议文档： docs/delimiter_migration.md
