import os
from platform import system
from datetime import datetime
# from yaml.constructor import SafeConstructor

from epycon.core._typing import (
    Union,
    Sequence,
)

from re import (
    sub,
)
from json import (
    dumps,
    loads,
)

# ----------------------- HELPER FUNCTIONS ------------------------------

def default_log_path():
    """Returns a platform-specific default log file path."""
    log_name = "epycon.log"
    
    this_system = system()
    
    if this_system == "Windows":
        log_path = os.path.join(os.environ["APPDATA"], "Local", "epycon")
    
    elif this_system == "Linux" or this_system == "Darwin":
        # 修正：使用用户主目录下的 logs 文件夹，避免 /var/log 的权限问题
        log_path = os.path.join(os.path.expanduser("~"), ".epycon", "logs")
    
    else:
        # Fallback to a generic location for other systems
        log_path = ""

    try:
        os.makedirs(log_path, exist_ok=True)
    except OSError as e:        
        print(f"Error creating log directory: {e}. Generic location will be used instead.")
        log_path = ""
    
    return os.path.join(log_path, f"{log_name}")


def deep_override(cfg_dict: dict, keys: list, value):
    """ Override value in nested dictionary fields.

    Args:
        cfg_dict (dict): source nested dictionary
        keys (list): list of keys sorted from the top to bottom level
        value (_type_): value to be stored

    Raises:
        KeyError: _description_

    Returns:
        _type_: _description_
    """
    current_dict = cfg_dict
    
    for key in keys[:-1]:  # Iterate through all keys except the last one
        current_dict = current_dict[key]  # Directly access nested dicts
    if keys[-1] in current_dict:
        current_dict[keys[-1]] = value
    else:
        raise KeyError(f"Invalid key `{keys[-1]}`")
    
    return cfg_dict


def difftimestamp(timestamps: Sequence[Union[int, float]]) -> float:
    assert len(timestamps) == 2
    return abs((datetime.fromtimestamp(timestamps[0]) - datetime.fromtimestamp(timestamps[1])).total_seconds())


def safe_string(name:str, safe_char: str = '-'):
    """_summary_

    Args:
        name (str): _description_

    Returns:
        _type_: _description_
    """    
    replace_chars = r"[,;\/:\\]"
    
    return sub(replace_chars, safe_char, name)

def pretty_json(custom_dict):
    """Saves dictionary into pretty json omitting empty space within time series data.

    Args:
        custom_dict (_type_): _description_

    Raises:
        ValueError: _description_

    Returns:
        _type_: _description_
    """
    s = dumps(custom_dict, indent=4, separators=(',', ':'))
    s = sub(r"\s+(?=[+-]?[0-9^()])", '', s)
    s = sub(r"(?<=[0-9])+\s+(?=[\]])", '', s)

    # check json string validity
    try:
        loads(s)
    except ValueError:
        raise ValueError
    else:
        return s


def get_channel_mappings(header, cfg):
    """获取通道映射，正确处理不同的 channels 类型
    
    Args:
        header: LogParser header object
        cfg: Configuration dictionary with 'data' key containing 'leads' and 'custom_channels'
        
    Returns:
        dict: Mapping of channel names to indices/references
    """
    if hasattr(header.channels, 'add_custom_mount'):
        # ChannelCollection 对象
        custom_channels = cfg.get("data", {}).get("custom_channels", {})
        if custom_channels:
            header.channels.add_custom_mount(custom_channels, override=False)
        if cfg.get("data", {}).get("leads") == "computed":
            return header.channels.computed_mappings
        else:
            return header.channels.raw_mappings
    elif isinstance(header.channels, list) and header.channels:
        # 简单 list，每个元素是 Channel 对象（有 name 和 reference 属性）
        # reference 是实际数据列的索引
        mappings = {}
        for ch in header.channels:
            if hasattr(ch, 'name') and hasattr(ch, 'reference'):
                # Channel 对象：使用 reference 作为数据列索引
                # 只包含 reference 在有效范围内的通道
                if ch.reference is not None and ch.reference < header.num_channels:
                    mappings[ch.name] = [ch.reference]
            elif hasattr(ch, 'name'):
                # 只有 name 没有 reference，跳过或使用默认
                pass
            elif isinstance(ch, str):
                # 字符串通道名，使用索引（legacy 支持）
                idx = list(header.channels).index(ch)
                if idx < header.num_channels:
                    mappings[ch] = [idx]
        return mappings if mappings else {f"ch{i}": [i] for i in range(header.num_channels)}
    else:
        # fallback: 使用默认名称
        return {f"ch{i}": [i] for i in range(header.num_channels)} if header.num_channels > 0 else {"ch0": [0]}

