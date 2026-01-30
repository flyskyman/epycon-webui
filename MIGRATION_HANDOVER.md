# EPYCON 项目迁移交接单 (Mac/Linux 环境)

> **目标**：从 Windows 迁移至 Mac 后，确保开发环境无缝衔接，且了解当前架构决策。

---

## 1. 项目整体进度 (Task Summary) ✅

项目目前已完成 **核心架构优化与稳定性增强**。

- **核心修复**:
    - 解决了 `__main__.py` 和 `batch.py` 中由于代码冲突导致的变量未定义 (`merge_mode`, `all_datalogs`)。
    - 修复了 `LogParser` 在 Header 读取失败时导致的文件句柄泄露风险。
    - 完善了类型标注（Type Stubs），静态分析不再报错。
- **性能监控**:
    - 集成了 `psutil` 逻辑，支持监控转换过程中的内存增量与 CPU 占用。
    - 更新了性能基准 (`scripts/benchmarks.json`)，已包含监控开销。
- **测试体系**:
    - 全面重构了测试套件，现在支持 `pytest` 自动化运行。
    - 新增了 `test_entries_embedding.py` 验证 HDF5 标记嵌入的准确性。
- **环境兼容**:
    - **已预修复 Mac 兼容性**: 针对非 Windows 系统，日志路径已自动切换至 `~/.epycon/logs`，避免 `/var/log` 权限问题。

---

## 2. 下一步计划 (Next Steps) 🚀

项目正处于 **功能扩展阶段**，即将在新分支开展工作：

1.  **初始化数据库集成**: 在 `feature/database-integration` 分支开始。
2.  **存储选型**: 实现前端 **IndexedDB** 持久化，用于存储用户的转换历史和日志搜索快照。
3.  **UI 优化**: 引入历史记录选项卡，精简主转换界面的进度反馈。
4.  **Mac 适配验证**: 在真实的 Mac 物理环境运行 `pytest` 确认文件 I/O 表现。

---

## 3. 技术决策与避坑指南 (Pitfalls) ⚠️

### 核心决策
*   **Squash Merge**: `master` 分支严格执行压缩合并，确保主线历史简洁。
*   **Single-Pass I/O**: `parsers.py` 内部逻辑必须保持一次读取、内存解析的策略，防止在大规模扫描时耗尽系统文件描述符。
*   **Performance Baseline**: 如果在 Mac 上运行性能脚本报“回归”，请使用 `python scripts/test_performance_regression.py --update` 更新 Mac 环境的专属基准。

### 需要注意的坑
*   **路径分隔符**: 虽然代码中已尽量使用 `os.path.join` 或 `Pathlib`，但在处理 WorkMate 原始数据中的 Windows 风格路径时，请务必使用 `path.replace('\\', '/')` 处理。
*   **时间戳精度**: Mac 上的 `time.perf_counter()` 精度与 Windows 略有差异，在运行 `Timestamp Diff` 的微秒级测试时，可能会出现较大的百分比波动（属正常噪音）。
*   **Flask 绑定**: `app_gui.py` 默认绑定 `127.0.0.1`。在 Mac 上如果需要局域网访问，请设置环境变量 `EPYCON_HOST=0.0.0.0`。

---

## 4. 关键文件路径说明 📁

| 文件/目录 | 说明 |
| :--- | :--- |
| `epycon/iou/parsers.py` | **核心逻辑**：负责 WorkMate (WMx32/x64) 原始二进制解析。 |
| `epycon/iou/planters.py` | **I/O 写入**：HDF5/CSV 生成器，包含 Marks 嵌入逻辑。 |
| `app_gui.py` | **启动入口**：Flask 服务与 GUI 后端逻辑。 |
| `scripts/test_performance_regression.py` | **性能守门员**：集成 `psutil` 的回归检测脚本。 |
| `tests/` | **测试中心**：所有 `test_*.py` 均可直接由 `pytest` 运行。 |
| `scripts/benchmarks.json` | **基准库**：性能测试的参考指标（建议到 Mac 后重置一次）。 |

---

## 5. Mac 环境快速启动 🛠️

```bash
# 1. 建议使用 virtualenv
python3 -m venv venv
source venv/bin/activate

# 2. 安装依赖 (已包含 psutil)
pip install -r requirements.txt

# 3. 运行自动化测试
pytest tests/

# 4. 确认性能监控生效
python scripts/test_performance_regression.py --update
```
