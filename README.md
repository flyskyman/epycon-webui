# epycon-web-ui
A web-ui base on the epycon whici is a Python package for parsing and conversion EP signals recorded by Abbott WorkMate system.
基于epycon的网页版操作界面，并做了一些必要的兼容性修正。以便在Windows下运行。

## 项目结构

- `.vscode/`：VS Code 工作区配置目录
  - `settings.json`：编辑器和 Python 环境设置。
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
