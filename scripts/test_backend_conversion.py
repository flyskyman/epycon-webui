import sys
import os
import datetime

# Try to import from the local epycon package
try:
    from epycon.iou.parsers import _readheader, _readentries
except ImportError:
    print("❌ Error: Could not import epycon. Please run this script from the project root.")
    sys.exit(1)

def test_backend_header(log_path):
    print(f"Testing Header Read: {log_path}")
    try:
        header = _readheader(log_path)
        print(f"✅ Header Read Success!")
        print(f"   - Timestamp: {header.timestamp}")
        try:
            dt = datetime.datetime.fromtimestamp(header.timestamp / 1_000_000) # Assuming microsecond timestamp
            print(f"   - Date Time: {dt}")
        except Exception as e:
             print(f"   - Date Time conversion failed (Expected if format changed): {e}")

        return True
    except Exception as e:
        print(f"❌ Header Read Failed: {e}")
        return False

def test_backend_entries(entries_path):
    print(f"Testing Entries Read: {entries_path}")
    try:
        entries = _readentries(entries_path, version='4.3.2') # Assuming 4.3.2/x64 based on previous context
        print(f"✅ Entries Read Success! Count: {len(entries)}")
        if len(entries) > 0:
            first = entries[0]
            print(f"   - First Entry TS: {first.timestamp}")
            try:
                dt = datetime.datetime.fromtimestamp(first.timestamp / 1_000_000)
                print(f"   - First Entry Date: {dt}")
            except Exception as e:
                print(f"   - Date Time format check failed: {e}")
        return True
    except Exception as e:
        print(f"❌ Entries Read Failed: {e}")
        return False

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Verify backend conversion.')
    parser.add_argument('log_file', help='Path to .log file (optional)', nargs='?')
    parser.add_argument('entries_file', help='Path to entries.log file (optional)', nargs='?')
    args = parser.parse_args()

    success = True
    if args.log_file and os.path.exists(args.log_file):
        if not test_backend_header(args.log_file): success = False
    
    if args.entries_file and os.path.exists(args.entries_file):
        if not test_backend_entries(args.entries_file): success = False

    if not args.log_file and not args.entries_file:
         print("Usage: python scripts/test_backend_conversion.py [log_file] [entries_file]")
