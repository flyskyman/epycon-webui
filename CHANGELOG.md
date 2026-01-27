# Changelog

## [Unreleased]

### Fixed
- 🐛 **类型检查错误修复**: 修复 Pylance 静态类型检查 51 个错误（降至 0 个）
  - `bins.parsebin`: 支持 `Union[bytes, bytearray]` 类型参数
  - `Entry.group`: 支持 `Union[int, str]` 类型（映射到 GROUP_MAP 标签）
  - `LogParser`: 所有 `Optional` 参数添加正确类型注解
  - 添加运行时断言保护和 `BinaryIO` 类型注解

### Added
- ✅ **完整测试套件**: 新增 26 个测试用例覆盖核心功能
  - 基础功能测试 (`test_type_fixes.py`)
  - 边缘情况测试 (`test_edge_cases.py`)
  - 集成测试 (`test_integration.py`)
  - 端到端测试 (`test_end_to_end.py`)
- 📄 **测试报告文档**: 详细测试覆盖率和验证结果 (`docs/TEST_REPORT.md`)

### Technical Details
- `bins.py`: `parsebin` 参数从 `bytearray` 改为 `Union[bytes, bytearray]`
- `_dataclasses.py`: `Entry.group` 字段从 `int` 改为 `Union[int, str]`
- `parsers.py`: 添加 `Optional` 类型、`BinaryIO` 注解和断言保护
- 100% 向后兼容，无破坏性变更

## [0.0.4-alpha] - 2026-01-27

### Added
- 🚀 **无窗口运行模式**: 移除命令行黑色窗口，提供纯净的后台服务体验。
- 🏠 **主中心导航回环**: 为所有子工具页面动态注入“返回主中心”链接，极大提升多页面协作效率。
- 📝 **持久化日志系统**: 在系统临时目录生成 `epycon_gui.log`，方便在无窗口模式下定位问题。
- 🖼️ **自动最小化**: exe 启动后自动最小化控制台窗口（如果还存在残余）并专注浏览器 UI。

### Changed
- 🎨 **UI 深度重构**: 采用 Tailwind CSS 重写主界面，新增“服务运行中”实时反馈及更专业的卡片式布局。
- 📁 **极致目录优化**: 建立了 `ui/` (前端), `scripts/` (打包/脚本), `docs/` (文档) 等核心目录，项目结构达到生产级标准。
- 🛰️ **资源路径修复**: 修复了 exe 环境下由于资源路径语义不一致导致的 CSS/JS 无法加载问题。

### Maintenance
- ♻️ **代码清理**: 彻底移除重复入口及 vendor 冗余文件，统一使用资源加载器。

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
