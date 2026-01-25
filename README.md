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
2. 运行工具集：打开 `index.html` 或运行 `python app_gui.py`
3. 使用 VS Code 任务：`Ctrl+Shift+P` > `Tasks: Run Task` > `运行 Epycon GUI`

## 打包为可执行文件

项目支持打包为独立可执行文件，无需安装 Python：

1. 安装 PyInstaller：`pip install pyinstaller`
2. 运行打包：`pyinstaller app_gui.py --name WorkMateDataCenter --add-data "editor.html;." --add-data "h5_preview.html;." --add-data "WorkMate Log Parser.html;." --add-data "index.html;." --add-data "config;config" --add-data "epycon;epycon"`
3. 生成的文件位于 `dist/WorkMateDataCenter/`

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

## 项目结构

- `.vscode/`：VS Code 工作区配置目录
  - `settings.json`：编辑器和 Python 环境设置。
  - `tasks.json`：定义运行任务，如启动 GUI 服务。
- `index.html`：工具集入口页面，整合本地运行的编辑器和日志解析器。
- `app_gui.py`：Flask Web 应用，提供 GUI 接口和 HTTP API，用于本地编辑器和直接运行转换。
- `editor.html`：HTML 前端，用于本地标注编辑。
- `h5_preview.html`：HDF5 文件预览工具。
- `fix_encoding.py`：编码修复脚本。
- `WorkMate Log Parser.html`：WorkMate 日志解析器相关 HTML。
- `config/`：配置文件目录
  - `config.json`：运行时配置。
  - `schema.json`：配置验证 schema。
- `docs/`：文档目录
  - `delimiter_migration.md`：分隔符迁移指南。
  - `papers/`：相关论文和文档 PDF 存放目录。
- `epycon/`：核心 Python 包
  - `__main__.py`：命令行批量转换入口。
  - `cli/`：命令行接口模块。
  - `config/`：包内配置，如 byteschema.py 和 schema.json。
  - `core/`：核心工具模块，如数据类、格式化、验证、bins.py、helpers.py。
  - `iou/`：输入输出模块
    - `parsers.py`：日志解析器。
    - `planters.py`：数据导出器（CSV/HDF）。
    - `constants.py`：常量定义。
  - `utils/`：工具模块，如装饰器和 person.py。
- `examples/`：示例目录
  - `demo.py`：演示脚本，展示 LogParser 使用。
  - `data/`：示例数据
    - `study01/`：示例研究文件夹，包含 .log 文件用于测试。
- `scripts/`：脚本目录
  - `generate_fake_wmx32.py`：生成假 WMx32 日志文件的脚本。
  - `README.md`：脚本使用说明。
