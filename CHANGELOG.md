# CHANGELOG

## v0.0.2-alpha - 2026-01-25

- 包含本地 Web UI 与批量转换功能的初始可分发版本。
- 新增：基于 `epycon` 的本地 Flask Web 界面（`app_gui.py`），提供 `index.html` 工具集入口。
- 新增：使用 PyInstaller 打包为独立可执行文件（`WorkMateDataCenter.exe`），无需 Python 环境运行。
- 修复：编码与时间戳兼容性问题（Windows 环境），修复 EXE 启动时默认打开页面的问题（默认打开 `index.html`）。
- 更新：整合 `examples/` 示例目录，更新演示脚本路径与文档说明。

> 说明：可在 GitHub Releases 下载 ZIP 包，解压后运行 `WorkMateDataCenter.exe`。
