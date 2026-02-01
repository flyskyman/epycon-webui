from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from epycon.core._validators import _validate_mount

from epycon.core._typing import (
    Union, List, Dict
)

@dataclass(frozen=True)
class Diary:
    group: int    


@dataclass(frozen=True)
class Entry:
    fid: str
    group: Union[int, str]  # int from binary, but mapped to str label via GROUP_MAP
    timestamp: int
    message: str

    def to_datetime(self, format: str = "%H:%M:%S") -> str:
        return datetime.fromtimestamp(self.timestamp).strftime(format)


# @dataclass
# class EntriesList:
#     fid: str
#     timestamp: Union[int, None] = None
#     content: List = field(default_factory=lambda : [])

#     def filter(self, valid: set):
#         return [item for item in self.content if item.group in valid]


@dataclass(frozen=True)
class Channel:
    name: str
    reference: Union[int, None]    
    source: str
    pin: Sequence[int]


@dataclass()
class Channels:
    content: List
    mount: Dict
        
    def add_custom_mount(self, mount: Dict, override: bool = False):
        """ Create custom mapping for computing bipolar leads.

        Args:
            override (bool, optional): _description_. Defaults to False.
        """
        # validate user-defined electrical references
        if not mount:
            return
        
        for _, item in mount.items():
            _validate_mount(item, max=len(self.content)-1)

        if override:
            self.mount = mount
        else:
            self.mount = {**self.mount, **mount}    

    @property
    def raw_mappings(self):
        return {item.name:(item.reference,) for item in self.content}

    @property
    def computed_mappings(self):
        mappings = dict()
        for key, indices in self.mount.items():
            if len(indices) == 1:
                mappings[key] = (self.content[indices[0]].reference,)
            
            if len(indices) == 2:
                mappings[key] = (
                    self.content[indices[1]].reference,
                    self.content[indices[0]].reference,
                    )

        return mappings

# Nested dataclass
@dataclass()
class AmplifierSettings:    
    resolution: int
    highpass_freq: float
    notch_freq: Union[None, int]
    sampling_freq: int


@dataclass()
class Header:
    timestamp: Union[int, float]  # 支持浮点时间戳以保留毫秒精度
    num_channels: int
    channels: Union[List, 'Channels']  # 支持 Channels 对象以保留双极导联映射
    amp: AmplifierSettings
    datablock_address: int

    def __post_init__(self):
        """ Post-init function
        """
        self.amp = AmplifierSettings(**self.amp)  # type: ignore

    def get_chnames(self):
        """获取通道名称列表

        Returns:
            List[str]: 通道名称列表
        """
        if isinstance(self.channels, Channels):
            return [item.name for item in self.channels.content]
        return [item.name for item in self.channels]