import os
import sys

def fix_planters_encoding():
    # 1. 定位文件: epycon/iou/planters.py
    base_dir = os.path.dirname(os.path.abspath(__file__))
    target_path = os.path.join(base_dir, "epycon", "iou", "planters.py")

    print(f"正在寻找文件: {target_path}")

    if not os.path.exists(target_path):
        print("❌ 错误：找不到 planters.py 文件！")
        return

    # 2. 读取文件
    with open(target_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 3. 执行替换：强制添加 encoding="utf-8"
    # 我们查找所有打开文件写入的地方，通常是 open(f_path, "w") 或 'w'
    
    new_content = content
    
    # 替换双引号版本
    if 'open(f_path, "w")' in new_content:
        new_content = new_content.replace('open(f_path, "w")', 'open(f_path, "w", encoding="utf-8")')
        print("✅ 修复了双引号 open(...) 写法")
        
    # 替换单引号版本
    if "open(f_path, 'w')" in new_content:
        new_content = new_content.replace("open(f_path, 'w')", "open(f_path, 'w', encoding='utf-8')")
        print("✅ 修复了单引号 open(...) 写法")

    # 4. 检查是否发生变化
    if new_content == content:
        if 'encoding="utf-8"' in content or "encoding='utf-8'" in content:
            print("✅ 文件似乎已经是修复过的（包含 utf-8），无需修改。")
        else:
            print("⚠️ 警告：未找到匹配的 open() 语句，可能代码格式不同。")
            print("请尝试手动修改 planters.py，搜索 'open(' 并添加 encoding='utf-8'")
    else:
        # 5. 写回文件
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        print("✅ 编码修复成功！现在支持写入特殊字符了。")

if __name__ == "__main__":
    fix_planters_encoding()