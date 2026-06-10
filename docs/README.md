# docs/ 目录说明

## 活文档（维护中）

| 文件 | 用途 |
|---|---|
| `ARCHITECTURE.md` | 转码入口点与调用链（conversion.py 单一实现的导览图） |
| `ECG_LAYOUT_SPEC.md` | Workmate vs Web Viewer 排版逻辑对比与物理定标（1mV=1cm）分析 |
| `KNOWN_ISSUES.md` | 已知问题台账：发现暂不处理的问题入账，处理后移入"已解决" |
| `technical_rendering_spec.md` | ECG 渲染"黄金配置"技术规范（README 流水线图的依据） |
| `papers/315_CinCFinalPDF.pdf` | 上游 CinC 论文——HDF5 数据模型与文件格式的最高权威（Table 1） |
| `H5_PREVIEW_USAGE.md` | HDF5 预览工具用法 |
| `VIEW_H5_ATTRIBUTES.md` | `scripts/inspect_h5_attrs.py` 用法 |
| `PERFORMANCE_REGRESSION.md` | 性能基准（`scripts/test_performance_regression.py` + `benchmarks.json`）说明 |

## archive/（历史留档，不维护）

一次性修复记录、阶段性总结、会话记录、历史 release notes（自 2026-06 起
发版说明直接写在 GitHub Release，见 CLAUDE.md 发版流程）、过时指南。
仅供考古，内容可能与现行代码不符。
