WorkMate 数据处理中心 v0.0.2-alpha

发布日期：2026-01-25

简要说明：

- 本次发布将 `epycon` 的功能包装为本地 Web UI，提供便捷的工具集入口 `index.html`。
- 新增独立可执行文件：`WorkMateDataCenter.exe`（位于 release 的压缩包内），无需安装 Python。
- 修复与改进：
  - 处理 Windows 平台的编码问题，强制 UTF-8 写入以减少乱码。
  - 修正时间戳对齐与头部 offset 处理，提升对多段 Dlog + 共用 entries.log 的兼容性。
  - 修复 EXE 启动时页面打开逻辑，默认打开工具集入口页面 `index.html`。

使用说明（快速）：

1. 从 Releases 下载 `WorkMateDataCenter-v0.0.2-alpha.zip` 并解压。
2. 运行 `WorkMateDataCenter.exe`，程序会自动启动本地服务并在浏览器中打开 `http://127.0.0.1:5000`。
3. 在界面中选择 `examples/data/study01/` 以运行演示，或上传自己的 WorkMate `.log` 文件进行转换。

注意：若需在无 GUI 的服务器环境运行，请使用 `python -m epycon` 的批处理入口。

已知问题：

- 部分极端私有格式或异常头部仍可能导致解析失败，建议先在 `examples/` 目录测试样本。

致谢：感谢项目中使用的 `epycon` 项目与相关论文的解析贡献者。
