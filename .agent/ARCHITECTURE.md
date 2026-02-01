# Epycon 架构说明

## 转码逻辑入口点

### 推荐使用（生产转码）
| 入口 | 描述 |
|------|------|
| **WebUI** `editor.html` → `/run-direct` API → `app_gui.py:execute_epycon_conversion` | 主程序转码逻辑，支持合并模式和常规模式 |

### 仅供测试/参考
| 入口 | 描述 |
|------|------|
| `epycon/cli/run.py` | **弃用**。早期基准测试代码，仅为 pytest 测试保留。**不建议用于生产转码**。 |

---

## 重要历史背景

### `epycon/iou/planters.py`
- **Commit `76ed04b`**：修复 H5 导出数据丢失，添加 `_logical_length` 追踪
- **Commit `e99352e`**：Revert 误删了 `append` 模式（后已恢复）
- **关键功能**：`_logical_length` 追踪、压缩支持、append 模式

### `epycon/cli/run.py`
- **状态**：已弃用，仅为测试保留
- **采样率**：✅ 已修复（从 header.amp.sampling_freq 获取并传递）
- **配置路径**：已修复为 `../config/`

---

## 采样率处理

| 路径 | 采样率来源 |
|------|-----------|
| WebUI 查看器 `api_ecg.py:get_data` | 从 HDF5 文件 `Fs` 属性读取 ✅ |
| WebUI 转码 `app_gui.py` (合并模式) | 从 LogParser header 传递 ✅ |
| WebUI 转码 `app_gui.py` (常规模式) | 从 LogParser header 传递 ✅ |
| CLI `run.py` | **未传递** ⚠️（弃用代码）|

---

## 测试依赖

以下测试文件依赖 `epycon.cli.run`，请勿移动或删除：
- `tests/test_cli_integration.py`
- `tests/test_cli_coverage.py`
