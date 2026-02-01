import sys
import tkinter as tk
from tkinter import filedialog
import os

def open_dialog():
    """在独立进程中打开文件选择框"""
    try:
        root = tk.Tk()
        root.withdraw()  # 隐藏主窗口
        
        # 尝试置顶窗口
        try:
            root.lift()
            root.attributes('-topmost', True)
            root.focus_force()
        except Exception:
            pass

        # 针对 macOS 的特殊处理：必须 update 让窗口事件循环跑起来
        root.update()
        
        file_path = filedialog.askopenfilename(
            title="选择 ECG 数据文件",
            filetypes=[
                ("All Supported", "*.h5 *.hdf5 *.he5 *.hdf *.npy *.npz"),
                ("HDF5 Files", "*.h5 *.hdf5 *.he5 *.hdf"),
                ("NumPy Files", "*.npy *.npz"),
                ("All Files", "*.*")
            ]
        )
        
        root.destroy()
        
        if file_path:
            # 将路径输出到 stdout，供父进程读取
            print(file_path)
            return True
        return False
        
    except Exception as e:
        # 将错误输出到 stderr
        print(f"Error: {e}", file=sys.stderr)
        return False

if __name__ == "__main__":
    open_dialog()
