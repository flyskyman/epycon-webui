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
    # DFile 内采样索引（x64 条目 0x06，i32）；x32 schema 未验证该字段，为 None。
    # 与时间戳定位互为独立来源，仅作交叉校验（issue #36）
    sample_index: Union[int, None] = None

    def to_datetime(self, format: str = "%H:%M:%S") -> str:
        return datetime.fromtimestamp(self.timestamp).strftime(format)


@dataclass(frozen=True)
class EntriesHeader:
    """entries.log 文件头（issue #36，849 个真实 study 验证）。

    WorkMate 的 epoch 字段是采集机墙钟按其 OS 时区解释的结果（实测一批机器为
    US Central、另一批为 UTC+8），头里的 ASCII 墙钟才是操作者看到的时刻；两者之差
    即采集机 OS 的 UTC 偏移，用它格式化 DFile 时间戳才能还原墙钟。
    """
    timestamp: float                    # 头 u64 ms → 秒，与 DFile 头同一时间语义
    wall_clock: Union[str, None]        # "MM/DD/YYYY HH:MM:SS"；x32 无时间串 → None
    num_datalogs: Union[int, None]      # x64 头 0x20；x32 → None
    utc_offset_sec: Union[int, None]    # 墙钟 − epoch，按 15 min 取整；无墙钟 → None


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

    def __len__(self):
        return len(self.content)

    def __getitem__(self, index):
        return self.content[index]

    def __iter__(self):
        return iter(self.content)

    def add_custom_mount(self, mount: Dict, override: bool = False):
        """ Create custom mapping for computing bipolar leads.

        Args:
            override (bool, optional): _description_. Defaults to False.
        """
        # validate user-defined electrical references
        if not mount:
            return

        for _, item in mount.items():
            _validate_mount(item, max=len(self.content) - 1)

        if override:
            self.mount = mount
        else:
            self.mount = {**self.mount, **mount}

    @property
    def raw_mappings(self):
        return {item.name: (item.reference,) for item in self.content}

    @property
    def computed_mappings(self):
        mappings = dict()
        for key, indices in self.mount.items():
            if len(indices) == 1:
                mappings[key] = (self.content[indices[0]].reference,)

            if len(indices) == 2:
                # 双极 = u+ − u−（mount_channels 做 source[0] − source[1]），与 WorkMate
                # 的 u+/u− 标签语义及其屏幕显示一致（issue #12）。曾为 u− − u+（#16）。
                # 起搏伪差符号取决于 JBox 接线（header 不记录 tip 在哪个针脚），不是判据。
                mappings[key] = (
                    self.content[indices[0]].reference,
                    self.content[indices[1]].reference,
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
