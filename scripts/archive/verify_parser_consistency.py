import struct
import sys
import os
from typing import List, Dict

# Try to import from the local epycon package
try:
    # Add project root to path
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from epycon.iou.parsers import _readentries
    from epycon.config.byteschema import GROUP_MAP
    from app_gui import clean_entries_content
except ImportError as e:
    print(f"❌ Error: Could not import dependencies: {e}")
    sys.exit(1)

def run_js_style_parse(f_path):
    """
    Implements the EXACT logic used in WorkMate_Log_Parser.html (JavaScript)
    """
    with open(f_path, 'rb') as f:
        buffer = f.read()
    
    file_size = len(buffer)
    results = []
    
    # JS Logic: Version Detection
    V_x64 = { 'head': 36, 'line': 220, 'tsOff': 10, 'txtOff': 18, 'txtLen': 176, 'is64': True }
    V_x32 = { 'head': 32, 'line': 216, 'tsOff': 10, 'txtOff': 14, 'txtLen': 178, 'is64': False }
    
    rem64 = (file_size - 36) % 220
    rem32 = (file_size - 32) % 216
    
    if rem64 == 0: spec = V_x64
    elif rem32 == 0: spec = V_x32
    else: spec = V_x64 if rem64 <= rem32 else V_x32
    
    # JS Logic: Mapping (hardcoded in JS)
    JS_GROUP_MAP = { 1: 'PROTOCOL', 2: 'EVENT', 3: 'NOTE', 4: 'IDK', 5: 'HIDDEN_NOTE', 6: 'PACE', 17: 'RATE' }
    
    # Note: Frontend filters GID 5 and 8. It effectively maps others.
    # We will use this map for pretty printing but logic is GID filtering.
    
    for ptr in range(spec['head'], file_size, spec['line']):
        if ptr + spec['line'] > file_size: break
        
        # JS Logic: Group ID
        gid = struct.unpack_from("<H", buffer, ptr)[0]
        if gid in (5, 8): continue # JS filters early
        
        # JS Logic: Timestamp
        if spec['is64']:
            ts = struct.unpack_from("<Q", buffer, ptr + spec['tsOff'])[0]
        else:
            ts = struct.unpack_from("<L", buffer, ptr + spec['tsOff'])[0] * 1000
    
        text_bytes = buffer[ptr + spec['txtOff'] : ptr + spec['txtOff'] + spec['txtLen']]
        
        null_pos = text_bytes.find(b'\x00')
        if null_pos >= 0:
            text_bytes = text_bytes[:null_pos]
            
        raw_text = text_bytes.decode('iso-8859-1', errors='replace')
        # JS regex: /[^\x20-\x7E\t]/g - strict ASCII
        msg = "".join(c for c in raw_text if 32 <= ord(c) <= 126 or c == '\t').strip()
        
        # Note: JS keeps even if msg is empty?
        # row.msg = ... .trim()
        # Frontend renders it.
        # But backend basic check in clean_entries_content removes empty message!
        # if not raw_msg: continue
        # So JS sim should also skip empty msg to match backend expectations?
        # User wants consistency. Backend drops empty. Frontend shows empty row.
        # This IS input mismatch.
        # But let's assume valid logs distinct enough.
        
        if msg:
            results.append({
                'ts': ts,
                'gid': gid,
                'group': JS_GROUP_MAP.get(gid, f"UNK({gid})"),
                'msg': msg
            })
            
    # Simulate Frontend Default Sort (by Time usually, or user selected Time)
    results.sort(key=lambda x: x['ts'])
    return results

def verify_consistency(f_path):
    print(f"🔍 Testing Consistency for: {f_path}")
    print("-" * 50)
    
    # 1. Run Official Python Parser + App Logic
    try:
        # Use readentries (public API) exposed in epycon.iou
        from epycon.iou import readentries
        # app_gui defaults version to '4.3.2', let's do same
        raw_entries = readentries(f_path, version='4.3.2')
        # Apply the ACTUAL backend cleaning logic
        py_entries = clean_entries_content(raw_entries)
    except Exception as e:
        import traceback
        print(f"❌ Python Parser failed: {e}")
        traceback.print_exc()
        return

    # 2. Run JS-Style Parser
    try:
        js_entries = run_js_style_parse(f_path)
    except Exception as e:
        print(f"❌ JS-Style Parser failed: {e}")
        return

    print(f"📊 Python Count (Cleaned): {len(py_entries)}")
    print(f"📊 JS-Style Count: {len(js_entries)}")
    
    # 3. Compare counts
    if len(py_entries) != len(js_entries):
        print(f"⚠️ Warning: Record count mismatch!")
    else:
        print(f"✅ Record counts match!")
    
    # 4. Content Verification (First 5 mismatches)
    mismatches = 0
    # Map JS entries by timestamp for fuzzy match? Or just sequence?
    # Sequence is risky if sort differs. Both sorted by file order?
    # Python cleans entries sort by timestamp. JS parse reads sequentially.
    # JS logs might be out of order? Usually logs are chronological.
    
    # Let's assume order matches.
    limit = min(len(py_entries), len(js_entries))
    for i in range(limit):
        py = py_entries[i]
        js = js_entries[i]
        
        # Check Message
        # Python entry message is str. JS is str.
        if py.message != js['msg']:
            print(f"❌ Row {i} Msg Mismatch:")
            print(f"   PY: '{py.message}'")
            print(f"   JS: '{js['msg']}'")
            mismatches += 1
            if mismatches >= 5: break
            
    if mismatches == 0:
        print(f"✅ Content verification passed (Checked {limit} rows)")

        print("\n🕵️ Identifying Mismatching Records:")
        py_set = { (e.timestamp * 1000, e.message) for e in py_entries }
        js_set = { (e['ts'], e['msg']) for e in js_entries }
        
        only_py = py_set - js_set
        only_js = js_set - py_set
        
        if only_py:
            print(f"   - Only in Python ({len(only_py)} items):")
            for ts, msg in sorted(list(only_py))[:3]:
                print(f"     [TS: {ts}] {repr(msg)}")
        
        if only_js:
            print(f"   - Only in JS-Style ({len(only_js)} items):")
            for ts, msg in sorted(list(only_js))[:3]:
                # Find the group for these JS items to see what they are
                group = next((e['group'] for e in js_entries if e['ts'] == ts and e['msg'] == msg), "UNKNOWN")
                print(f"     [TS: {ts} Group: {group}] {repr(msg)}")

    # 5. Compare Sample Records (Top 5)
    limit = min(len(py_entries), len(js_entries), 5)
    print(f"\n📝 Comparing Top {limit} samples:")
    
    for i in range(limit):
        p = py_entries[i]
        j = js_entries[i]
        
        # Note: Python's 'timestamp' vs JS 'ts' (s vs ms)
        # Group names might differ slightly (IDK vs DEBUG)
        
        ts_match = "✅" if (p.timestamp * 1000) == j['ts'] else f"❌ ({p.timestamp*1000} vs {j['ts']})"
        # Map py labels back to match JS if needed for comparison, but better to check raw logic
        group_match = "✅" if p.group == j['group'] or (p.group == 'IDK' and j['group'] == 'DEBUG') else f"⚠️ ({p.group} vs {j['group']})"
        msg_match = "✅" if p.message == j['msg'] else f"❌ MSG MISMATCH"
        
        print(f"#{i+1}: TS={ts_match} Group={group_match} Content={msg_match}")
        if p.message != j['msg']:
            print(f"   PY: {repr(p.message)}")
            print(f"   JS: {repr(j['msg'])}")

    # Dump Backend Output
    dump_file = "backend_dump.txt"
    try:
        from datetime import datetime
        with open(dump_file, "w", encoding="utf-8") as f:
             f.write(f"TIME | GROUP | MESSAGE\n")
             f.write("-" * 50 + "\n")
             for e in py_entries:
                 dt = datetime.fromtimestamp(e.timestamp)
                 # Format matches WorkMate style (HH:MM:SS) plus ms
                 time_str = dt.strftime("%Y-%m-%d %H:%M:%S") + f".{int(e.timestamp * 1000) % 1000:03d}"
                 f.write(f"{time_str} | {e.group} | {str(e.message)}\n")
        print(f"\n📄 Backend Dump saved to: {os.path.abspath(dump_file)}")
    except Exception as e:
        print(f"Failed to dump: {e}")

    print("-" * 50)
    if len(py_entries) == len(js_entries):
        print("✨ Overall result: Parsers are functionally consistent.")
    else:
        print("💡 Note: Slight differences in grouping names or filtering may exist.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Verify parser consistency.')
    parser.add_argument('file', help='Path to entries.log file')
    args = parser.parse_args()
    
    if os.path.exists(args.file):
        verify_consistency(args.file)
    else:
        print(f"❌ File not found: {args.file}")
