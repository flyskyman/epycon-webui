# WorkMate 数据处理中心

一个基于 epycon 的 Web UI 工具集，用于解析和转换 Abbott WorkMate 系统记录的 EP 信号数据。提供便捷的图形界面，支持数据转换、日志解析和 HDF5 预览。

## 特性

- **数据转换**：将 WorkMate 日志文件转换为 CSV 或 HDF5 格式
- **日志解析**：深度搜索和过滤 WorkMate 日志条目
- **HDF5 预览**：浏览和可视化 HDF5 文件内容
- **Web 界面**：本地 Flask 服务，支持配置管理和批量处理
- **跨平台**：优化 Windows 兼容性，处理编码和时间戳问题

## 快速开始

1. 安装依赖：`pip install -r requirements.txt`
2. 运行工具集：打开 `ui/index.html` 或运行 `python app_gui.py`
3. 使用 VS Code 任务：`Ctrl+Shift+P` > `Tasks: Run Task` > `运行 Epycon GUI`

## 打包为可执行文件

项目支持打包为独立可执行文件，无需安装 Python：

1. 安装 PyInstaller：`pip install pyinstaller`
2. 运行打包：`pyinstaller app_gui.py --name WorkMateDataCenter --add-data "ui;ui" --add-data "config;config" --add-data "epycon;epycon"`
3. 生成的文件位于 `dist/WorkMateDataCenter/`

注意：运行时前端第三方 bundle 已集中放置于 `ui/vendor/`，请确保在打包时将该目录一并包含（例如使用 `--add-data "ui/vendor;ui/vendor"`）。

**注意**：这是目录模式打包，包含 EXE 和支持文件。您可以压缩整个文件夹分发。

运行 EXE 后，自动打开浏览器访问 `http://127.0.0.1:5000` 使用工具集。

下载与分发

- 已在 GitHub Releases 上传可分发压缩包：WorkMateDataCenter-v0.0.2-alpha.zip（包含 `WorkMateDataCenter.exe` 及必要支持文件）。
- Release 页面： https://github.com/flyskyman/epycon-webui/releases/tag/v0.0.2-alpha

快速下载安装并运行（Windows）：

1. 从上面 Release 页面下载 `WorkMateDataCenter-v0.0.2-alpha.zip`。
2. 右键解压到任意目录（例如 `C:\Tools\WorkMateDataCenter`）。
3. 双击 `WorkMateDataCenter.exe` 启动，或在 PowerShell 中运行：

```powershell
Start-Process -FilePath "C:\path\to\WorkMateDataCenter.exe"
```

4. 程序会启动本地服务并在默认浏览器打开 `http://127.0.0.1:5000`，可在界面中选择示例数据或上传自己的 `.log` 文件进行转换。

提示：若你希望在无浏览器（服务器）环境使用批处理功能，请使用源码方式运行：

```powershell
python -m epycon
```


## 项目结构（当前）

- `app_gui.py`：Flask Web 应用，项目的图形/HTTP 入口（保留为可执行主入口）。
- `epycon/`：核心 Python 包，项目实现（`__main__.py`, `core/`, `iou/`, `cli/`, `config/` 等）。
- `ui/`：前端静态资源目录（运行时界面）
  - `index.html`：工具集入口页面（现在位于 `ui/index.html`）。
  - `editor.html`：本地标注编辑器界面（`ui/editor.html`）。
  - `WorkMate Log Parser.html`：日志解析器界面（`ui/WorkMate Log Parser.html`）。
  - `h5_preview.html`：HDF5 预览页面（`ui/h5_preview.html`）。
  - `vendor/`：第三方运行时 bundle（`ui/vendor/vue.js`, `ui/vendor/tailwind.js` 等）。
- `scripts/`：构建与工具脚本
  - `WorkMateDataCenter.spec`：PyInstaller 打包配置（现在在 `scripts/`）。
  - `fix_encoding.py`：编码修复脚本（`scripts/fix_encoding.py`）。
  - `generate_fake_wmx32.py`：测试数据生成脚本。
  - `README.md`：脚本目录说明。
- `config/`：运行时配置（`config.json`, `schema.json`）。
- `docs/`：项目文档与历史发布档案（`release_notes_v0.0.3-alpha.md`, 压缩包等）。
- `examples/`：示例和示例数据（`examples/demo.py`, `examples/data/`）。
- 项目根还包含：`README.md`, `CHANGELOG.md`, `LICENSE`, `setup.py`, `requirements.txt` 等元数据与开发文件。

打包说明：为了简化 PyInstaller 配置，`--add-data "ui;ui"` 可用于包含整个前端目录（示例命令已在上方“打包为可执行文件”部分）。
