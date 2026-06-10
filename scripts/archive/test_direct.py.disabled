import sys
import importlib

# 强制重新加载模块
if 'app_gui' in sys.modules:
    del sys.modules['app_gui']

import app_gui
importlib.reload(app_gui)

config = {
    'paths': {
        'input_folder': 'examples/data',
        'output_folder': 'examples/data/out'
    },
    'data': {'output_format': 'h5'},
    'global_settings': {'workmate_version': '4.3.2'}
}

print("Calling execute_epycon_conversion directly...")
success, logs = app_gui.execute_epycon_conversion(config)
print(f"Success: {success}")
print(f"Logs:")
for log in logs:
    print(f"  {log}")
