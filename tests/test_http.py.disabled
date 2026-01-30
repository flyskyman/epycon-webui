import os
import requests

port = os.environ.get('EPYCON_GUI_PORT', '5000')
config = {
    'paths': {
        'input_folder': 'examples/data',
        'output_folder': 'examples/data/out'
    },
    'data': {'output_format': 'h5'},
    'global_settings': {'workmate_version': '4.3.2'}
}
url = f'http://127.0.0.1:{port}/run-direct'
print(f"发送请求到 {url}...")
resp = requests.post(url, json=config, timeout=60)
print(f"HTTP 状态码: {resp.status_code}")
print(f"响应内容前 500 字符: {resp.text[:500]}")
try:
    r = resp.json()
    print(f"Status: {r['status']}")
    print(f"\n完整日志:")
    print(r['logs'])
except Exception as e:
    print(f"解析 JSON 失败: {e}")

