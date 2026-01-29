# 如何在 HDFView 中查看文件属性

## 问题
在 HDFView 中看不到 subject_id 和 subject_name 等属性信息。

## 解决方法

### 在 HDFView 中查看文件级属性：

1. **打开文件后，查看属性面板**
   - 在左侧树形视图中，选中**文件根节点**（文件名本身）
   - 在菜单栏选择：`Object → Show Properties`
   - 或右键点击文件根节点 → `Show Properties`

2. **属性显示位置**
   - 属性会显示在底部的 **Attributes** 面板中
   - 如果没有看到，检查 `View → Attributes` 是否勾选

3. **查看的关键信息**
   ```
   subject_id     = SUBJ001
   subject_name   = (可能为空)
   study_id       = study01
   timestamp      = 1769603458
   datetime       = 2026-01-28T20:30:58
   author         = mymail@mailbox.com (如果设置了)
   merged         = True (合并模式)
   ```

### 常见问题

**Q: 为什么看不到属性？**
- 确保选中的是**文件根节点**，而不是某个数据集
- 某些版本的 HDFView 需要在 `Tools → User Options` 中启用属性显示

**Q: subject_name 为空怎么办？**
- 如果 MASTER 文件中的 name 字段为空，这是正常的
- subject_id 是必需的，subject_name 是可选的

## 命令行验证方法（推荐）

### 方法 1：使用我们的验证脚本
```powershell
python verify_master.py
```

### 方法 2：查看单个文件详情
```powershell
python inspect_h5_attrs.py examples/data/out/study01/00000000.h5
```

### 方法 3：使用 h5dump 工具（如果安装了）
```powershell
h5dump -A your_file.h5
```

### 方法 4：快速 Python 单行命令
```powershell
python -c "import h5py; f=h5py.File('your_file.h5','r'); print('subject_id:', f.attrs.get('subject_id')); print('subject_name:', f.attrs.get('subject_name'))"
```

## 验证文件属性是否完整

运行验证脚本会显示：
- ✅ MASTER信息完整：同时有 subject_id 和 study_id
- ⚠️ 缺少部分MASTER信息：缺少 subject_id 或 study_id

## 相关文件

- `verify_master.py` - 批量验证所有 H5 文件
- `inspect_h5_attrs.py` - 详细查看单个文件的所有属性
- `scripts/ps_helpers.ps1` - PowerShell 辅助函数（包含 Test-Master / Test-H5Files / Invoke-PyScript）
