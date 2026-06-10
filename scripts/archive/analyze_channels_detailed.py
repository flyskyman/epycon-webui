import os
from epycon.iou.parsers import LogParser
from epycon.core._dataclasses import Channels

def analyze_channels_detailed(base_dir, cfg):
    """深度分析：检查每个文件映射后的输出通道数"""
    
    for study_dir in sorted(os.listdir(base_dir)):
        study_path = os.path.join(base_dir, study_dir)
        if not os.path.isdir(study_path) or study_dir == 'output':
            continue
            
        print(f"\n{'='*80}")
        print(f"患者: {study_dir}")
        print('='*80)
        
        log_files = sorted([f for f in os.listdir(study_path) if f.endswith('.log') and f.startswith('0')])
        
        output_channels_list = []
        
        for log_file in log_files:
            log_path = os.path.join(study_path, log_file)
            try:
                with LogParser(log_path, version="4.3.2", samplesize=1024) as parser:
                    header = parser.get_header()
                    if header is None:
                        print(f"  {log_file}: 无法读取文件头")
                        continue
                    
                    num_raw = header.num_channels
                    
                    # 复用app_gui.py的映射获取逻辑
                    if cfg["data"]["leads"] == "computed":
                        if isinstance(header.channels, Channels):
                            file_mappings = header.channels.computed_mappings
                        else:
                            file_mappings = {f"ch{i}": [i] for i in range(header.num_channels)}
                    else:
                        if isinstance(header.channels, Channels):
                            file_mappings = header.channels.raw_mappings
                        else:
                            file_mappings = {f"ch{i}": [i] for i in range(header.num_channels)}
                    
                    # 应用通道过滤
                    if cfg["data"]["channels"]:
                        file_mappings = {k:v for k,v in file_mappings.items() if k in cfg["data"]["channels"]}
                    
                    num_output = len(file_mappings)
                    output_channels_list.append(num_output)
                    
                    if num_raw != num_output:
                        print(f"  {log_file}: 原始 {num_raw} → 输出 {num_output} 通道 ⚠️")
                    else:
                        print(f"  {log_file}: {num_output} 个输出通道")
                        
            except Exception as e:
                print(f"  {log_file}: 错误 - {e}")
        
        # 检查该患者的输出通道数是否一致
        unique_outputs = set(output_channels_list)
        if len(unique_outputs) > 1:
            print(f"\n❌ 患者内部输出通道数不一致！发现 {sorted(unique_outputs)} - 这就是merge失败的原因！")
        elif len(unique_outputs) == 1:
            print(f"\n✅ 患者内部输出通道数一致: {list(unique_outputs)[0]} 通道")
        else:
            print(f"\n⚠️ 未找到有效的数据文件")

if __name__ == "__main__":
    import json
    
    # 加载配置
    with open(r"test_backup_config.json", "r", encoding="utf-8") as f:
        cfg = json.load(f)
    
    backup_dir = cfg["paths"]["input_folder"].replace("/", "\\")
    
    print(f"深度分析: {backup_dir}")
    print(f"配置: leads={cfg['data']['leads']}, channels filter={cfg['data']['channels']}")
    
    analyze_channels_detailed(backup_dir, cfg)
    
    print("\n" + "="*80)
    print("结论: 如果患者内部'输出通道数'不一致，才会触发merge错误！")
    print("="*80)
