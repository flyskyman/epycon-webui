# PowerShell 多行命令问题解决方案

## 问题描述

PowerShell 的 PSReadLine 模块在处理多行输入时存在已知bug，特别是包含中文字符时会导致光标位置计算错误，出现 `ArgumentOutOfRangeException` 异常。

## 解决方案

### 方案 1：使用脚本文件（推荐）✅

不要使用 `python -c "多行代码"`，而是创建 `.py` 文件：

```powershell
# 不推荐
python -c "import sys; print('测试')"

# 推荐
# 1. 创建文件
echo "import sys; print('测试')" > test.py

# 2. 运行文件
python test.py
```

### 方案 2：使用辅助函数 ✅

加载项目提供的 PowerShell 辅助函数：

```powershell
# 加载辅助函数
. .\scripts\ps_helpers.ps1

# 使用函数
Test-Master             # 验证MASTER信息
Test-H5Files            # 检查H5文件
Start-EpyconGUI         # 启动GUI
Invoke-PyScript test.py # 运行Python脚本
```

### 方案 3：配置 PowerShell 优化

已自动添加到 PowerShell 配置文件：

```powershell
# 修复 PSReadLine 多行中文问题
Set-PSReadLineOption -PredictionSource None
Set-PSReadLineOption -EditMode Windows
```

重新加载配置：
```powershell
. $PROFILE
```

### 方案 4：使用单行命令

对于简单命令，用分号连接：

```powershell
python -c "import sys; print(sys.version)"
```

## 已完成的配置

✅ 创建了 `scripts/ps_helpers.ps1` 辅助函数库
✅ 更新了 PowerShell 配置文件 ($PROFILE)
✅ 设置了执行策略为 RemoteSigned

## 最佳实践

1. **复杂脚本** → 创建 `.py` 文件
2. **简单命令** → 使用单行格式
3. **常用操作** → 使用辅助函数
4. **避免** → 多行 `python -c` 命令，特别是包含中文时

## 参考链接

- [PSReadLine Issue #3117](https://github.com/PowerShell/PSReadLine/issues/3117)
- [PowerShell Execution Policies](https://docs.microsoft.com/powershell/module/microsoft.powershell.core/about/about_execution_policies)
