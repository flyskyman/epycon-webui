
import sys
import os
import re
from datetime import datetime
from pypdf import PdfReader
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / 'epycon'))

from epycon.iou.parsers import _readmaster, _readentries

def verify_identity(log_dir, pdf_path):
    print("="*60)
    print("IDENTITY VERIFICATION REPORT")
    print("="*60)
    
    # --- 1. Analyze LOG Data ---
    print(f"\n[LOG SOURCE]: {log_dir}")
    master_path = os.path.join(log_dir, "MASTER")
    entries_path = os.path.join(log_dir, "entries.log")
    
    log_id = "Unknown"
    log_name = "Unknown"
    log_date = "Unknown"
    
    if os.path.exists(master_path):
        try:
            info = _readmaster(master_path)
            log_id = info.get('id', 'N/A').strip()
            log_name = info.get('name', 'N/A').strip()
            print(f"  > Patient ID:   {log_id}")
            print(f"  > Patient Name: {log_name}")
        except Exception as e:
            print(f"  > Error reading MASTER: {e}")
            
    if os.path.exists(entries_path):
        try:
            # Read first entry to guess date
            entries = _readentries(entries_path, version='4.3.2')
            if entries:
                first_ts = entries[0].timestamp
                dt = datetime.utcfromtimestamp(first_ts)
                log_date = dt.strftime("%Y-%m-%d")
                print(f"  > Procedure Date (UTC): {log_date} ({dt.strftime('%H:%M:%S')})")
        except Exception as e:
            print(f"  > Error reading entries: {e}")

    # --- 2. Analyze PDF Data ---
    print(f"\n[PDF SOURCE]: {pdf_path}")
    pdf_text = ""
    try:
        reader = PdfReader(pdf_path)
        # Usually checking first page is enough for header info
        full_text = ""
        for i in range(min(3, len(reader.pages))):
            full_text += reader.pages[i].extract_text() + "\n"
            
        pdf_text = full_text
    except Exception as e:
        print(f"  > Error reading PDF: {e}")
        return

    # Heuristic extraction for PDF header info
    # Common patterns: "Name: John Doe", "ID: 12345", "Date: 20/01/2020"
    
    # Try find Date
    # Matches dd/mm/yyyy or yyyy-mm-dd or dd-Mon-yyyy
    date_patterns = [
        r'\d{2}/\d{2}/\d{4}',
        r'\d{4}-\d{2}-\d{2}',
        r'\d{2}-[A-Za-z]{3}-\d{4}'
    ]
    
    pdf_dates = []
    for pat in date_patterns:
        matches = re.findall(pat, pdf_text)
        pdf_dates.extend(matches)
        
    # Try find Patient Name/ID (Context based)
    # Looking for lines like "Patient: ..."
    patient_lines = []
    for line in pdf_text.split('\n'):
        if "Patient" in line or "Name" in line or "ID" in line:
            if len(line.strip()) < 50: # Avoid long text
                patient_lines.append(line.strip())

    print(f"  > Detected Dates: {list(set(pdf_dates))}")
    print(f"  > Potential Identity Lines:")
    for l in patient_lines[:5]:
        print(f"    - {l}")

    # --- 3. Comparison Conclusion ---
    print("\n" + "-"*30)
    print("CONCLUSION:")
    
    match_fail = False
    
    # Check ID
    if log_id and log_id in pdf_text:
        print("  ✅ Patient ID Match: Found Log ID in PDF.")
    else:
        print(f"  ❌ Patient ID Mismatch: Log ID '{log_id}' NOT found in PDF text.")
        match_fail = True
        
    # Check Date
    if log_date and log_date in pdf_text:
        print(f"  ✅ Date Match: Found Log Date '{log_date}' in PDF.")
    elif log_date:
        # Try fuzzy match (e.g. log is 2018-03-29, pdf is 29/03/2018)
        # Simple check: is '2018' in pdf?
        year = log_date.split('-')[0]
        if year in pdf_text:
             print(f"  ⚠️ Date Warning: Year '{year}' found, but exact format might differ.")
        else:
             print(f"  ❌ Date Mismatch: Log Date '{log_date}' (Year {year}) NOT found in PDF.")
             match_fail = True

    if match_fail:
        print("\n⛔ CRITICAL: These files likely belong to DIFFERENT patients or procedures!")
    else:
        print("\n✅ PASSED: Files appear to match.")

if __name__ == "__main__":
    verify_identity(sys.argv[1], sys.argv[2])
