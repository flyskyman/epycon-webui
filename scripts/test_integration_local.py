#!/usr/bin/env python
"""
本地集成测试脚本 — 模拟 CI 环境运行
用于在推送到 GitHub 前在本地验证所有步骤
"""

import os
import sys
import json
import subprocess
from pathlib import Path

# Ensure UTF-8 output on all platforms
if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

def run_command(cmd, description):
    """运行命令并报告结果"""
    print(f"\n{'='*60}")
    print(f"[RUN] {description}")
    print(f"{'='*60}")
    print(f"$ {cmd}")
    result = os.system(cmd)
    if result != 0:
        print(f"[FAIL] {description}")
        return False
    print(f"[OK] {description}")
    return True

def main():
    os.chdir(Path(__file__).parent.parent)  # 切换到项目根目录
    
    print(f"[START] 开始本地集成测试 — {Path.cwd()}")
    
    all_passed = True
    
    # 1. 配置验证
    if not run_command(
        'python -c "import json, jsonschema; cfg=json.load(open(\'config/config.json\')); schema=json.load(open(\'config/schema.json\')); jsonschema.validate(cfg,schema); print(\'CONFIG OK\')"',
        "验证 config.json JSON Schema 合规性"
    ):
        all_passed = False
    
    # 2. 生成测试数据
    if not run_command(
        'python scripts/generate_fake_wmx32.py --out examples/data/study01/00000000.log --with-entries --with-master --entries-count 5 --entries-fids 2 --version 4.3 --channels 2',
        "生成测试数据（5 entries, 2 fids, 2 channels）"
    ):
        all_passed = False
    
    # 3. 创建输出目录
    os.makedirs('examples/data/out', exist_ok=True)
    
    # 4. 更新配置为 CI 路径
    print(f"\n{'='*60}")
    print(f"🔧 配置 CI 输出路径")
    print(f"{'='*60}")
    with open('config/config.json', 'r') as f:
        cfg = json.load(f)
    cfg['paths']['input_folder'] = 'examples/data'
    cfg['paths']['output_folder'] = 'examples/data/out'
    with open('config/config.json', 'w') as f:
        json.dump(cfg, f, indent=2)
    print("✅ 配置已更新")
    
    # 5. 运行 epycon
    if not run_command(
        'python -m epycon',
        "运行 epycon 批量转换"
    ):
        all_passed = False
    
    # 6. 验证输出
    if not run_command(
        'python scripts/validate_ci_output.py examples/data/out/study01',
        "验证输出文件完整性"
    ):
        all_passed = False
    
    # 最终报告
    print(f"\n{'='*60}")
    if all_passed:
        print("[PASS] 所有本地集成测试通过！")
        print("[OK] 可以安心推送到 GitHub")
        return 0
    else:
        print("[FAIL] 部分测试失败，请检查上述错误日志")
        return 1

if __name__ == '__main__':
    sys.exit(main())
