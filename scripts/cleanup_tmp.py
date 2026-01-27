#!/usr/bin/env python3
import shutil
from pathlib import Path

root = Path('.').resolve()
removed = []

targets = [root / 'htmlcov', root / 'coverage.xml', root / 'run_tests_fixed.ps1', root / '.pytest_cache']
for t in targets:
    if t.exists():
        try:
            if t.is_dir():
                shutil.rmtree(t)
            else:
                t.unlink()
            removed.append(str(t))
        except Exception as e:
            print(f"Failed to remove {t}: {e}")

# remove all __pycache__ directories
for p in list(root.rglob('__pycache__')):
    try:
        shutil.rmtree(p)
        removed.append(str(p))
    except Exception as e:
        print(f"Failed to remove {p}: {e}")

print('Cleanup removed:', removed)
