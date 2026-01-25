import os
import sys
import threading
import webbrowser
import logging
import tkinter as tk
from tkinter import filedialog, messagebox
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from glob import iglob
import dataclasses
import struct
import csv
import tempfile
import shutil
from datetime import datetime, timezone

# ========================================================
# 🛡️ 运行时环境
# ========================================================
current_dir = os.path.dirname(os.path.abspath(__file__))
candidates = [current_dir, os.path.join(current_dir, "epycon")]
for path in candidates:
    if os.path.exists(path) and path not in sys.path:
        sys.path.insert(0, path)

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# ========================================================
# 🔧 强制 UTF-8 写入
# ========================================================
try:
    import builtins
    _real_open = builtins.open
    class UTF8EnforcedOpen:
        def __enter__(self):
            self.original_open = builtins.open
            def new_open(file, mode='r', buffering=-1, encoding=None, errors=None, newline=None, closefd=True, opener=None):
                if 'w' in mode or 'a' in mode:
                    encoding = 'utf-8'
                    errors = 'replace' 
                return self.original_open(file, mode, buffering, encoding, errors, newline, closefd, opener)
            builtins.open = new_open
        def __exit__(self, exc_type, exc_val, exc_tb):
            builtins.open = self.original_open
except ImportError: pass

# ========================================================
# 📦 导入 Epycon
# ========================================================
try:
    from epycon.config.byteschema import ENTRIES_FILENAME, LOG_PATTERN
    from epycon.iou import LogParser, EntryPlanter, CSVPlanter, HDFPlanter, readentries, mount_channels
except ImportError as e:
    root = tk.Tk(); root.withdraw()
    messagebox.showerror("启动错误", f"无法加载 Epycon。\n{e}"); sys.exit(1)

app = Flask(__name__)
CORS(app)

class MemoryLogHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.logs = []
    def emit(self, record):
        self.logs.append(self.format(record))

# ========================================================
# 🏗️ [核心] 自定义可变 Entry 对象
# ========================================================
@dataclasses.dataclass
class MutableEntry:
    timestamp: float
    group: str
    message: str
    fid: str = '0'
    duration: float = 0
    color: int = 0

# ========================================================
# ⚖️ [核心] 全自动时间归一化 (Unix Seconds)
# ========================================================
def to_unix_seconds(val):
    try:
        if isinstance(val, datetime):
            return val.replace(tzinfo=timezone.utc).timestamp()
        num = float(val)
        if num > 100_000_000_000_000_000: # FILETIME
            return (num - 116444736000000000) / 10_000_000.0
        if num > 100_000_000_000: # Milliseconds
            return num / 1000.0
        return num
    except:
        return 0.0

# ========================================================
# 🛠️ [核心] entries.log 去壳
# ========================================================
def prepare_standard_entries_file(original_path):
    try:
        with open(original_path, 'rb') as f:
            raw = f.read(256)
        valid_gids = [1, 2, 3, 4, 5, 6, 17]
        target_offset = 0
        gid_128 = struct.unpack_from('<H', raw, 128)[0]
        if gid_128 in valid_gids:
            target_offset = 128
        else:
            for i in range(0, 200, 4):
                gid = struct.unpack_from('<H', raw, i)[0]
                if gid in valid_gids and i+220 < len(raw):
                    if struct.unpack_from('<H', raw, i+220)[0] in valid_gids:
                        target_offset = i
                        break
        if target_offset > 0 and target_offset != 36:
            temp_dir = tempfile.gettempdir()
            temp_path = os.path.join(temp_dir, f"std_{os.path.basename(original_path)}")
            with open(original_path, 'rb') as src, open(temp_path, 'wb') as dst:
                dst.write(b'\x00' * 36) 
                src.seek(target_offset)
                shutil.copyfileobj(src, dst)
            return temp_path
        return original_path
    except: return original_path

# ========================================================
# 🧹 [终极核心] V68.1 融合版 (Strict ASCII + Semantic SNR)
# ========================================================
def is_semantic_garbage(text):
    """
    语义信噪比检测 (V67.7 核心算法)
    判断字符串是否由大量的 ASCII 符号组成（视觉乱码）。
    例如: "((m(*" 或 "\\;8\\;B" 虽然是 ASCII，但应被剔除。
    """
    if not text: return True
    
    # 统计字符构成
    alpha_num_count = 0  # 字母、数字
    risky_sym_count = 0  # 风险符号 (括号, 斜杠, @, #, etc.)
    safe_sym_count = 0   # 安全符号 (空格, ., -, :)
    
    for char in text:
        if char.isalnum(): 
            alpha_num_count += 1
        elif char in " .-:/": 
            # 这些是时间、数值、日期中常见的安全符号，不计入风险
            safe_sym_count += 1
        else:
            # 风险符号：\ | ( ) [ ] { } < > ? ! @ # $ % ^ & * _ = + ; ' " ` ~
            risky_sym_count += 1
            
    total_len = len(text)
    
    # [逻辑 1] 极短字符串 (1-2字符)
    # 必须是字母数字，或者是明确的白名单单字
    if total_len <= 2:
        # 如果包含风险符号 (如 "m(" ) -> 删
        if risky_sym_count > 0: return True
        
        # 单字母/双字母检查 (白名单机制)
        # 允许纯数字 (如 "1", "12")
        if text.isdigit(): return False
        
        # 允许特定含义的字母组合 (如 "A1", "V2")
        if text.isalnum() and any(c.isdigit() for c in text): return False
        
        # 纯字母检查：只保留常见标记
        # V68.0 的白名单：A, V, P, R, T, S, M, I, W (波形/导联/事件标记)
        if text.isalpha():
            if text.upper() not in ['A', 'V', 'P', 'R', 'T', 'S', 'M', 'I', 'W', 'L', 'B']:
                return True # "e", "q" 等无意义字母视为噪点
        
        return False

    # [逻辑 2] 信噪比失衡 (符号比字多)
    # 例如 "((m(*" -> Risky=4, Alpha=1 -> 删
    # 例如 "\;8\;B" -> Risky=4, Alpha=3 -> 删
    if risky_sym_count >= alpha_num_count and risky_sym_count > 1:
        return True
        
    # [逻辑 3] 稀疏内容检测
    # 如果有效文字极少 (<30%) 且总长度 > 4
    if total_len > 4:
        ratio = alpha_num_count / total_len
        if ratio < 0.3: return True
        
    return False

def clean_entries_content(entries):
    cleaned_list = []
    
    # 系统底层数据组黑名单
    GROUP_BLACKLIST = {
        'SYS', 'SYSTEM', 'DEBUG', 'DBG', 
        'UNK', 'UNKNOWN', 'IDK', 
        'ERROR', 'ERR', 'WARN', 
        'DATA', 'BLOB', 'ALARM'
    }
    
    for e in entries:
        raw_msg = str(e.message)
        raw_grp = str(e.group)

        # 1. [物理层] Null 截断 (模拟 C 字符串)
        if '\x00' in raw_msg: raw_msg = raw_msg.split('\x00')[0]
        if '\x00' in raw_grp: raw_grp = raw_grp.split('\x00')[0]

        raw_msg = raw_msg.strip()
        raw_grp = raw_grp.strip()

        # 2. 基础非空校验
        if not raw_msg: continue
        if raw_grp.upper() in GROUP_BLACKLIST: continue

        # 3. [物理层] Strict ASCII 检测 (V68.0 核心)
        # 英文软件不应包含任何 > 127 的字节
        try:
            raw_msg.encode('ascii')
            raw_grp.encode('ascii')
        except UnicodeEncodeError:
            # 包含乱码字节 -> 丢弃
            continue

        # 4. [物理层] 控制符检测
        # 过滤 0-31 的控制符 (保留 Tab, LF, CR)
        is_clean_ascii = True
        for char in raw_msg:
            code = ord(char)
            if code < 32 and code not in (9, 10, 13):
                is_clean_ascii = False
                break
        if not is_clean_ascii: continue

        # 5. [逻辑层] 语义信噪比检测 (V67.7 核心回归)
        # 过滤掉 "((m(*", "\;8\;B1", "#6#6" 这种由合法 ASCII 组成的乱码
        if is_semantic_garbage(raw_msg):
            continue

        # 6. 组装
        new_e = MutableEntry(
            timestamp=to_unix_seconds(e.timestamp),
            group=raw_grp,
            message=raw_msg
        )
        cleaned_list.append(new_e)

    cleaned_list.sort(key=lambda x: x.timestamp)
    return cleaned_list

# ========================================================
# 📐 辅助工具
# ========================================================
def get_raw_log_start_seconds(file_path):
    try:
        with open(file_path, 'rb') as f:
            raw = float(struct.unpack('<Q', f.read(8))[0])
            return to_unix_seconds(raw)
    except: return 0.0

def get_safe_n_channels(header):
    try:
        if hasattr(header, 'n_channels'): return int(header.n_channels)
        if hasattr(header.amp, 'n_channels'): return int(header.amp.n_channels)
        if hasattr(header, 'channels'):
            if hasattr(header.channels, 'raw_mappings'): return len(header.channels.raw_mappings)
        return 0
    except: return 0

def export_global_csv(entries, output_folder, study_id):
    try:
        filename = f"{study_id}_All_Entries_Normalized.csv"
        path = os.path.join(output_folder, study_id, filename)
        with open(path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['UnixSeconds', 'Group', 'Message'])
            for e in entries:
                writer.writerow([f"{e.timestamp:.3f}", e.group, e.message])
        return filename
    except: return None

# --- 核心转换逻辑 ---
def execute_epycon_conversion(cfg):
    mem_handler = MemoryLogHandler()
    logger = logging.getLogger("epycon_gui")
    logger.setLevel(logging.INFO)
    if logger.hasHandlers(): logger.handlers.clear()
    logger.addHandler(mem_handler)
    
    utf8_guard = UTF8EnforcedOpen()
    
    try:
        with utf8_guard:
            input_folder = cfg["paths"]["input_folder"]
            output_folder = cfg["paths"]["output_folder"]
            
            if not input_folder or not os.path.exists(input_folder):
                logger.error(f"❌ 输入文件夹不存在: {input_folder}")
                return False, mem_handler.logs
                
            output_fmt = cfg["data"]["output_format"]
            valid_datalogs = set(cfg["data"]["data_files"])
            
            direct_logs = list(iglob(os.path.join(input_folder, "*.log")))
            study_list = []
            if direct_logs:
                study_list.append(input_folder)
            else:
                for sub_path in iglob(os.path.join(input_folder, '**')):
                    if os.path.isdir(sub_path): study_list.append(sub_path)
            
            if not study_list:
                 logger.warning("⚠️ 未找到 log 文件。")
                 return False, mem_handler.logs

            processed_count = 0
            
            for study_path in study_list:
                study_id = os.path.basename(study_path)
                logs_in_study = sorted(list(iglob(os.path.join(study_path, LOG_PATTERN))))
                if not logs_in_study: continue

                try: os.makedirs(os.path.join(output_folder, study_id), exist_ok=True)
                except: pass
                
                # --- [Step 1] 读取并清洗 Entries ---
                all_entries_norm = []
                epath = os.path.join(study_path, ENTRIES_FILENAME)
                need_entries = cfg["entries"]["convert"] or (cfg["data"]["output_format"] == "h5" and cfg["data"]["pin_entries"])
                
                if need_entries and os.path.exists(epath):
                    try:
                        logger.info(f"🔎 读取标注: {os.path.basename(epath)}")
                        clean_path = prepare_standard_entries_file(epath) 
                        native_entries = readentries(clean_path, version=cfg["global_settings"]["workmate_version"])
                        
                        all_entries_norm = clean_entries_content(native_entries)
                        
                        if clean_path != epath and os.path.exists(clean_path):
                            try: os.remove(clean_path)
                            except: pass
                            
                        logger.info(f"✅ 归一化标注: {len(all_entries_norm)} 条 (ASCII+SNR双重净化)")
                        export_global_csv(all_entries_norm, output_folder, study_id)
                    except Exception as e:
                        logger.warning(f"⚠️ 读取失败: {e}")

                # --- [Step 2] 精确对齐 ---
                for datalog_path in logs_in_study:
                    datalog_id = os.path.basename(datalog_path).replace(".log", "")
                    if valid_datalogs and datalog_id not in valid_datalogs: continue
                    
                    processed_count += 1
                    logger.info(f"处理文件: {datalog_id}.log")
                    
                    try:
                        log_start_sec = get_raw_log_start_seconds(datalog_path)
                        
                        n_channels = 0
                        with LogParser(datalog_path, version=cfg["global_settings"]["workmate_version"], samplesize=1024) as p:
                            header = p.get_header()
                            fs = header.amp.sampling_freq
                            n_channels = get_safe_n_channels(header)
                        
                        file_size = os.path.getsize(datalog_path)
                        duration_sec = 0.0
                        if n_channels > 0 and fs > 0:
                            n_samples = (file_size - 32) // (n_channels * 2)
                            duration_sec = n_samples / fs
                        
                        log_end_sec = log_start_sec + duration_sec
                        
                        target_entries_rel = [] 
                        for e in all_entries_norm:
                            if log_start_sec <= e.timestamp <= log_end_sec:
                                diff_seconds = e.timestamp - log_start_sec
                                new_e = dataclasses.replace(e)
                                new_e.timestamp = diff_seconds
                                target_entries_rel.append(new_e)

                        # 转换波形
                        with LogParser(
                            datalog_path, 
                            version=cfg["global_settings"]["workmate_version"], 
                            samplesize=cfg["global_settings"]["processing"]["chunk_size"]
                        ) as parser:
                            if cfg["data"]["leads"] == "computed":
                                mappings = header.channels.computed_mappings
                            else:
                                mappings = header.channels.raw_mappings
                            if cfg["data"]["channels"]:
                                mappings = {k:v for k,v in mappings.items() if k in cfg["data"]["channels"]}
                            column_names = list(mappings.keys())
                            
                            out_path = os.path.join(output_folder, study_id, f"{datalog_id}.{output_fmt}")
                            PlanterClass = CSVPlanter if output_fmt == "csv" else HDFPlanter
                            
                            with PlanterClass(out_path, column_names=column_names, sampling_freq=fs) as planter:
                                for chunk in parser:
                                    chunk = mount_channels(chunk, mappings)
                                    planter.write(chunk)
                                    
                                if output_fmt == "h5" and cfg["data"]["pin_entries"] and target_entries_rel:
                                    if hasattr(planter, 'add_marks'):
                                        safe_pos = [int(e.timestamp * fs) for e in target_entries_rel]
                                        safe_grp = [str(e.group) for e in target_entries_rel]
                                        safe_msg = [str(e.message) for e in target_entries_rel]
                                        valid = [(p,g,m) for p,g,m in zip(safe_pos, safe_grp, safe_msg) if p>=0]
                                        if valid:
                                            p,g,m = zip(*valid)
                                            planter.add_marks(list(p), list(g), list(m))

                        if cfg["entries"]["convert"] and target_entries_rel:
                            file_fmt = cfg["entries"]["output_format"]
                            entry_out_path = os.path.join(output_folder, study_id, f"{datalog_id}.{file_fmt}")
                            
                            entryplanter = EntryPlanter(target_entries_rel)
                            filter_groups = cfg["entries"]["filter_annotation_type"]
                            criteria = {"groups": filter_groups} if filter_groups else {}
                            
                            if file_fmt == "csv":
                                entryplanter.savecsv(entry_out_path, criteria=criteria, ref_timestamp=0)
                            elif file_fmt == "sel":
                                entryplanter.savesel(entry_out_path, 0, fs, list(mappings.keys()), criteria=criteria)
                            
                            logger.info(f"   -> 📄 精确生成: {datalog_id}.{file_fmt} ({len(target_entries_rel)}条)")

                    except Exception as e:
                        logger.error(f"❌ 文件 {datalog_id} 转换失败: {str(e)}")
                        continue
                        
            logger.info(f"✅ 全部完成! 共处理 {processed_count} 个文件")
            return True, mem_handler.logs
        
    except Exception as e:
        import traceback
        err = traceback.format_exc()
        logger.error(f"❌ 系统错误:\n{err}")
        return False, mem_handler.logs

@app.route('/')
def home():
    html_path = resource_path('editor.html')
    if os.path.exists(html_path): return send_file(html_path)
    return f"Missing editor.html"

@app.route('/run-direct', methods=['POST'])
def run_direct():
    config_data = request.json
    success, logs = execute_epycon_conversion(config_data)
    return jsonify({"status": "success" if success else "error", "logs": "\n".join(logs)})

@app.route('/api/select-folder', methods=['GET'])
def api_select_folder():
    try:
        root = tk.Tk(); root.withdraw(); root.attributes('-topmost', True)
        path = filedialog.askdirectory(); root.destroy()
        if path: path = os.path.normpath(path)
        return jsonify({"path": path})
    except Exception as e:
        return jsonify({"error": str(e), "path": ""})

def open_browser():
    # 打开本地工具集入口页面
    import os
    index_path = os.path.join(os.path.dirname(__file__), 'index.html')
    webbrowser.open_new(f'file://{index_path}')

if __name__ == '__main__':
    threading.Timer(1.0, open_browser).start()
    print("🚀 Epycon GUI (V68.1 终极融合版) 已启动...")
    app.run(port=5000, debug=False)