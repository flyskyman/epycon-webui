# Epycon 架构说明

## 转码逻辑入口点（2026-06-10 治本重构后）

转换语义的**唯一实现**：`epycon/conversion.py`（`convert_study` + `entries_to_marks`）。
任何转换行为（标注定位、合并、缩放）的修改只允许发生在该模块。

| 入口 | 调用链 |
|------|--------|
| **WebUI**（生产） | `editor.html` → `/run-direct` API → `app_gui.py:execute_epycon_conversion` → `epycon.conversion.convert_study` |
| **CLI** | `python -m epycon` → `epycon/__main__.py` → `epycon.conversion.convert_study` |

两条入口的差异仅在前置处理：WebUI 多做 entries 清洗（ASCII/SNR 净化）、
进度回调、汇总 CSV、智能输出目录；采样级行为由
`tests/test_conversion.py` 的等价性测试锁定一致。

## 历史注记

- 此前 WebUI 与 CLI 各自维护平行实现并漂移出多个标注定位 bug
  （墙钟偏移映射、亚秒截断、字段名漂移等），2026-06-10 合一。
- `epycon/cli/run.py`（弃用的早期基准代码）已删除。
- 本文件曾随未合入的侧线提交（a82e626）游离于主线外，2026-06-10 恢复并入库。

## 延伸阅读

- `CLAUDE.md` — 维护约定（发版流程、台账、删除代码规矩、常用命令）
- `README.md` 项目结构一节
- `docs/KNOWN_ISSUES.md` — 待办与调查项
- `.agent/ECG_LAYOUT_SPEC.md` — ECG 查看器布局逻辑规范
  （与 `docs/archive/layout_logic_analysis.md` 同源）
