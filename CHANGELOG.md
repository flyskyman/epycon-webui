# Changelog

## [Unreleased]

### Added
- 🚀 **智能合并模式**: 支持按时间戳排序合并多个日志文件为单个HDF5文件
  - 自动时间戳排序和文件合并
  - 支持追加模式 (append) 用于多文件处理
  - 合并后的元数据完整保留
- 🔒 **数据匿名化引擎**: 8位伪随机患者ID生成系统
  - `Tokenize` 类实现可重现的匿名化
  - 保护医疗数据隐私合规性
  - 支持全局匿名化配置
- 📊 **完整元数据导出**: HDF5文件包含完整的文件属性
  - 作者、设备、机构信息
  - 时间戳、采样率、通道数等技术参数
  - SignalPlant兼容的元数据格式
- 🏷️ **标注数据嵌入**: 可选将标注数据直接嵌入HDF5文件
  - `pin_entries` 配置选项
  - SignalPlant `Marks` 数据集格式
  - 时间同步和数据对齐
- 🔧 **通道映射优化**: 正确显示标准导联名称
  - I, II, III, aVR, aVL, aVF, V1-V6标准命名
  - 自动类型转换和验证
  - 兼容计算导联和原始导联
- ✅ **全面测试套件**: 57+ 自动化测试用例
  - 29个业务逻辑测试用例
  - 28个扩展边界测试用例
  - 版本兼容性测试
  - 数据完整性验证
- 📚 **完整文档重写**: 全面的README.md和使用指南
  - 项目概述和架构说明
  - 详细配置选项文档
  - 开发指南和贡献规范
  - 输出格式详细说明
- 🔄 **CI/CD修复**: 修复GitHub Actions工作流
  - 正确运行scripts目录下的测试
  - 修复PYTHONPATH配置
  - 自动化集成测试和验证

### Changed
- 🎨 **用户界面增强**: 网页配置器支持新功能选项
  - 合并模式开关
  - 匿名化配置选项
  - 实时配置验证
- 📋 **配置系统扩展**: 支持更多高级选项
  - `merge_logs`: 控制文件合并行为
  - `pseudonymize`: 全局匿名化开关
  - `credentials`: 元数据配置
  - `pin_entries`: 标注嵌入选项

### Fixed
- 🐛 **类型检查错误修复**: 修复 Pylance 静态类型检查 51 个错误（降至 0 个）
  - `bins.parsebin`: 支持 `Union[bytes, bytearray]` 类型参数
  - `Entry.group`: 支持 `Union[int, str]` 类型（映射到 GROUP_MAP 标签）
  - `LogParser`: 所有 `Optional` 参数添加正确类型注解
  - 添加运行时断言保护和 `BinaryIO` 类型注解

### Technical Details
- **合并功能**: `HDFPlanter` 支持 `append=True` 参数实现多文件合并
- **匿名化**: `utils/person.py` 新增 `Tokenize` 类
- **元数据**: HDF5属性系统完整实现SignalPlant兼容格式
- **测试覆盖**: 57个测试用例覆盖所有核心功能和边界情况
- **文档**: 完全重写的README包含详细的项目介绍和使用指南
- **CI修复**: GitHub Actions现在正确运行所有测试套件

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
