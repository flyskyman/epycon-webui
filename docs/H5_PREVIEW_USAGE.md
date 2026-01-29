# HDF5 文件预览器使用说明

## 功能说明

`ui/h5_preview.html` 是一个基于浏览器的 HDF5 文件预览工具，可以在浏览器中直接查看 HDF5 文件的结构和内容，**无需安装任何软件**。

## 如何查看 subject_id 和 subject_name

### ✅ 数据确实已写入

通过 epycon 生成的 HDF5 文件中**已经包含**了完整的 metadata，包括：

- `subject_id` - 患者 ID
- `subject_name` - 患者姓名
- `study_id` - 研究 ID
- `datetime` - 记录时间
- `timestamp` - Unix 时间戳
- `merged` - 是否为合并文件
- `num_files` - 合并的文件数量
- `num_channels` - 通道数量
- `sampling_freq` - 采样频率
- `author`, `device`, `owner` - 其他元数据

### 📖 如何在预览器中查看

1. **打开预览器**
   - 双击 `ui/h5_preview.html` 文件
   - 或在浏览器中打开该文件

2. **选择 HDF5 文件**
   - 点击"选择文件"按钮
   - 选择任何 `.h5` 或 `.hdf5` 文件

3. **查看全局属性**
   - 文件加载后，**根节点 `/` 会自动被选中并显示**
   - 在右侧面板中查看 **"📋 全局属性 (File-level Attributes)"** 部分
   - `subject_id` 和 `subject_name` 会以**粗体蓝色**高亮显示

### 🔍 验证数据是否正确写入

如果想通过 Python 验证 HDF5 文件中的属性：

```python
import h5py

with h5py.File('your_file.h5', 'r') as f:
    print("全局属性:")
    for key in sorted(f.attrs.keys()):
        print(f"  {key}: {f.attrs[key]}")
    
    # 查看特定属性
    if 'subject_id' in f.attrs:
        print(f"\nsubject_id = {f.attrs['subject_id']}")
    if 'subject_name' in f.attrs:
        print(f"subject_name = {f.attrs['subject_name']}")
```

或使用项目提供的检查脚本：

```powershell
python scripts/inspect_h5.py "path/to/your/file.h5"
```

## 改进内容（2026-01-28）

### ✨ 新增功能

1. **自动显示全局属性**
   - 文件打开后自动选中根节点并显示全局属性
   - 无需手动点击根节点

2. **重要字段高亮**
   - `subject_id`, `subject_name`, `study_id` 以粗体蓝色显示
   - 便于快速识别关键信息

3. **属性排序优化**
   - 重要字段优先显示在列表顶部
   - 其他字段按字母顺序排列

4. **空属性警告**
   - 如果根节点没有属性，会显示警告信息
   - 提示可能的数据写入问题

5. **BigInt 序列化支持** ⭐ 新增
   - 自动处理 BigInt 类型（如 `timestamp`）
   - 避免 "Do not know how to serialize a BigInt" 错误
   - 所有数值类型现在都能正确显示

## 技术细节

- 使用 **h5wasm** 库在浏览器中解析 HDF5 文件
- 纯前端实现，数据不会上传到服务器
- 支持大文件的切片预览（避免浏览器卡顿）
- 支持查看 Group、Dataset、Attributes、Links 等所有 HDF5 结构

## 常见问题

### Q: 为什么看不到属性？

**A:** 请确保：
1. 点击了左侧树形结构中的 **根节点 `/`**（文件打开后应自动选中）
2. 查看右侧的 **"📋 全局属性"** 面板
3. 如果仍然看不到，可能是浏览器兼容性问题，建议使用 Chrome/Edge 最新版

### Q: 属性显示为乱码？

**A:** 如果 `subject_name` 包含中文等非 ASCII 字符，可能显示为 JSON 字符串。这是正常的，实际数据是正确的。

### Q: 看到 "Do not know how to serialize a BigInt" 错误？

**A:** 这个问题已在最新版本修复。如果仍然遇到：
1. 刷新页面 (Ctrl+F5 强制刷新)
2. 清除浏览器缓存
3. 确保使用的是最新版的 h5_preview.html

### Q: 可以编辑属性吗？

**A:** 不可以。这是一个**只读预览器**，不支持修改 HDF5 文件。

## 相关文档

- [HDF5 属性查看脚本](../scripts/inspect_h5.py)
- [通道分组策略说明](./delimiter_migration.md)
- [完整项目文档](../README.md)
