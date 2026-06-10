# Delimiter Usage & Migration Plan

此文档列出仓库中与 `delimiter` 相关的使用点，并给出安全的迁移建议（如果要移除 `planter.delimiter` 别名）。

## 发现的使用点

- [epycon/iou/planters.py](../epycon/iou/planters.py):
  - 行 ~160: `self._delimiter = kwargs.pop("delimiter", ",")`
  - 行 ~174: `self.delimiter = self._delimiter`  (兼容别名)
  - 行 ~203: CSV header 写入使用 `self.delimiter.join(self.column_names)`
  - 行 ~208: 数据格式化使用 `self._fmt = self.delimiter.join([...])`

> 说明：目前仓库中未发现其他文件直接访问 `planter.delimiter`（若有，请用 ripgrep/grep 全量复查）。

## 迁移方案（两种可选策略）

策略 A — 保留别名（低风险，推荐）
- 不做代码改动，保留 `self.delimiter = self._delimiter`。如果遇到与分隔符相关的问题，只需在构造 `CSVPlanter(..., delimiter=';')` 时传入想要的值。

策略 B — 移除别名并统一使用 `_delimiter`（重构）
- 步骤：
  1. 全量搜索 `delimiter` 使用点：

```bash
rg "\\.delimiter|\bdelimiter\b" || grep -R "delimiter" -n .
```

  2. 在 [epycon/iou/planters.py](../epycon/iou/planters.py) 内把所有 `self.delimiter` 替换为 `self._delimiter`。
  3. 修改所有调用方，确保通过构造函数参数 `delimiter=` 或内部访问 `_delimiter`（不建议外部访问 `_delimiter`，应通过参数注入）。
  4. 在单个模块验证无误后再做全仓替换并运行端到端转换。

## 建议的代码补丁（示例，不会直接应用）

- 在 [epycon/iou/planters.py](../epycon/iou/planters.py) 中，将以下片段：

```python
self._delimiter = kwargs.pop("delimiter", ",")
# ...
self.delimiter = self._delimiter
```

替换为（保留注释）或直接不改：

```python
self._delimiter = kwargs.pop("delimiter", ",")
# 保留以下别名以确保向后兼容：
self.delimiter = self._delimiter
```

- 若选择移除别名，则在文件中把 `self.delimiter` 全部替换为 `self._delimiter`，并在外部构造该类时显式传参。

## 回退与验证

- 任何变更后请运行：

```powershell
$env:PYTHONPATH = "$PWD\epycon"
$env:EPYCON_CONFIG = "$PWD\config\config.json"
$env:EPYCON_JSONSCHEMA = "$PWD\config\schema.json"
python -m epycon
```

- 若 CSV 路径失败，检查 traceback 是否包含 `AttributeError: 'CSVPlanter' object has no attribute 'delimiter'`，若有即为调用方未适配导致的问题。

---

若需要，我可以：
- 生成一个可应用的补丁（把 `self.delimiter` 替换为 `self._delimiter` 并修改所有调用点），或
- 在若干调用点先尝试改动并 run 验证，再做全仓替换。

请选择下一步（生成补丁 / 先试改部分文件 / 保持现状）。
