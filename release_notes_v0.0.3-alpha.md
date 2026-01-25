# Release Notes - v0.0.3-alpha

**Release Date:** 2026-01-26

## Overview

WorkMate DataCenter v0.0.3-alpha 是首个独立可执行应用版本，提供开箱即用的 WorkMate 日志处理和数据转换能力。

## Key Features

### 🚀 Standalone Executable
- **Single-file deployment**: `WorkMate_DataCenter.exe`
- **No Python installation required**
- **All dependencies bundled**: numpy, h5py, flask, werkzeug

### 🌐 Web UI
- Auto-opens browser on startup
- JSON configuration editor
- Real-time log processing
- HDF5/CSV export support

### 🔧 Technical Improvements
- Full UTF-8 support on Windows
- Proper Tcl/Tk runtime initialization
- Optimized Tkinter integration

## Installation & Usage

1. Download `WorkMate_DataCenter.exe` from releases
2. Double-click to run
3. Browser automatically opens to `http://127.0.0.1:5000/`
4. Configure and process your WorkMate log files

## Known Limitations

- Alpha version - API may change
- Local processing only (no cloud sync)
- Windows 10+ required

## Contributors

- Development team

---

**For detailed changelog, see CHANGELOG.md**
