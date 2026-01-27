# Changelog

## [0.0.3-alpha] - 2026-01-26

### Added
- ✨ 独立 exe 应用程序（WorkMate_DataCenter.exe）
- 🌐 自动打开浏览器功能
- 📦 完整打包 numpy, h5py, flask, werkzeug 依赖
- 🎨 改进 UTF-8 编码支持

### Fixed
- 🔧 修复 Windows 控制台 GBK 编码问题（中文/表情显示）
- 🐛 修复 Tcl/Tk 数据路径查询

### Changed
- 📝 应用文件重命名：app_gui.py → WorkMate_DataCenter.py
- 🗑️ 清理临时文件和过时配置

### Maintenance
- ♻️ 清理：从仓库删除了重复入口 `WorkMate_DataCenter.py`，保留 `app_gui.py` 作为唯一实现（变更在分支 `chore/remove-workmate-datacenter`，待 PR 合并）。

### Repo Organization
- 📁 资产整理：将运行时第三方静态文件（如 `vue.js`、`tailwind.js`）移至 `ui/vendor/` 以便更清晰地区分源码与静态前端资产（见 PR #2）。

## [0.0.2-alpha] - Previous

See git history for details.
