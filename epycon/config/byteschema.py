from dataclasses import dataclass

MASTER_FILENAME = 'MASTER'

ENTRIES_FILENAME = 'entries.log'

LOG_PATTERN = r'[0-9]*.log'

ID_MAP_FILE = 'id_mapping'

PATIENT_LIST = 'patient_list.txt'

# annotation subtype → 标签。7/9/13/16/20 按 849 个真实 study 的文本形态命名（issue #36）：
# 7 全空文本（常带负采样索引）、9 "IMAGEn"、13 数值/"Print Review Fit"（语义未定）、
# 16 "RF On - Session n"/"RF Off - n s"、20 刺激器 "Amp n=.. PW n=.."。8 在解析层被过滤，不列。
GROUP_MAP = {
    1: 'PROTOCOL',
    2: 'EVENT',
    3: 'NOTE',
    4: 'IDK',
    5: 'HIDDEN_NOTE',
    6: 'PACE',
    7: 'BLANK',
    9: 'IMAGE',
    13: 'VALUE',
    16: 'RF',
    17: 'RATE',
    20: 'STIM',
}

SOURCE_MAP = {
    0: 'PRES',
    1: 'ECG',
    2: 'JBOX',
    3: 'PRES',
    4: 'EXT',
    5: 'SYNC',
    }

# ----------------------- WMx32 -----------------------
# ---------------------- Datalog ----------------------


@dataclass
class DatalogHeaderWMx32:
    """ Log file header
    """
    block_size = 0x0000, 0x35B8
    timestamp = 0x0, 0x4
    num_channels = 0x4, 0x6


@dataclass
class DatalogChannelsWMx32:
    """ Log file channel settings
    """
    block_size = 0x2E, 0x34AE
    subblock_size = 0x0, 0x1E
    name = 0x0, 0xC
    display_scale = 0xC, 0xE
    ids = 0xE, 0x10
    lowpass_freq = 0x10, 0x12
    highpass_freq = 0x12, 0x14
    display_color = 0x14, 0x15
    input_source = 0x15, 0x16
    jbox_pins = 0x16, 0x18
    analysis_type = 0x18, 0x19
    sync_type = 0x19, 0x1A


@dataclass
class DatalogAmplifierWMx32:
    """ Log file amplifier settings
    """
    resolution = 0x34AE, 0x34B0
    highpass_freq = 0x34B0, 0x34B2
    notch_freq = 0x34B2, 0x34B4
    sampling_freq = 0x34B4, 0x34B6


@dataclass
class DatalogDatablockWMx32:
    """ Log file data chunks
    """
    sample_mapping = 0x34B6, 0x35B6
    start_address = 0x35B6, 0x35B8
    fmt = '<i4'


@dataclass
class WMx32LogSchema:
    """ Log file schema for WM <= 4.1
    """
    channel_size = 32   # Number of bytes per channel
    page_size = 64      # Max number of channels in one page
    sample_size = 4     # Number of bytes per data sample
    nb_pages = 7        # Total number of pages
    timestamp_fmt = '<L', 1

    supported_versions = ("4.1")

    header = DatalogHeaderWMx32
    channels = DatalogChannelsWMx32
    amplifier = DatalogAmplifierWMx32
    datablock = DatalogDatablockWMx32


# ---------------------- Master -----------------------
@dataclass
class WMx32MasterSchema:
    """ Master file
    """
    subject_id = 0x43, 0x4F


# ---------------------- Entries ----------------------
@dataclass
class WMx32EntriesSchema:
    """ Annotation entries
    """
    header = 0x00, 0x20
    header_timestamp = 0x02, 0x06
    timestamp_fmt = '<L', 1
    header_date = 0x06, 0x10
    entry_type = 0x0, 0x2
    datalog_id = 0x2, 0x6
    timestamp = 0xA, 0xE
    text = 0xE, 0xC0
    line_size = 0xD8


# ----------------------- WMx64 -----------------------
# ---------------------- Datalog ----------------------
@dataclass
class DatalogHeaderWMx64:
    """ Log file header
    """
    block_size = 0x0000, 0x393C
    timestamp = 0x0, 0x8
    num_channels = 0x8, 0xA


@dataclass
class DatalogChannelsWMx64:
    """ Log file channel settings
    """
    block_size = 0x32, 0x3832
    subblock_size = 0x0, 0x20
    name = 0x0, 0xC
    display_scale = 0xC, 0xE
    ids = 0xE, 0x10
    lowpass_freq = 0x10, 0x12
    highpass_freq = 0x12, 0x14
    display_color = 0x14, 0x15
    input_source = 0x15, 0x16
    jbox_pins = 0x16, 0x18
    analysis_type = 0x18, 0x19
    sync_type = 0x19, 0x1A


@dataclass
class DatalogAmplifierWMx64:
    """ Log file amplifier settings
    """
    resolution = 0x3832, 0x3834
    highpass_freq = 0x3834, 0x3836
    notch_freq = 0x3836, 0x3838
    sampling_freq = 0x3838, 0x383A


@dataclass
class DatalogDatablockWMx64:
    """ Log file data chunks
    """
    sample_mapping = 0x383A, 0x393A
    start_address = 0x393A, 0x393C
    fmt = '<i4'


@dataclass
class WMx64LogSchema:
    """ Log file schema for WM > 4.1
    """
    channel_size = 32   # Number of bytes per channel
    page_size = 64      # Max number of channels in one page
    sample_size = 4     # Number of bytes per data sample
    nb_pages = 7        # Total number of pages
    timestamp_fmt = '<Q', 1000

    supported_versions = ("4.2", "4.3")

    header = DatalogHeaderWMx64
    channels = DatalogChannelsWMx64
    amplifier = DatalogAmplifierWMx64
    datablock = DatalogDatablockWMx64


# ---------------------- Master -----------------------
@dataclass
class WMx64MasterSchema:
    """ Master file
    """
    subject_name = 0x02, 0x43
    subject_id = 0x43, 0x4F


# ---------------------- Entries ----------------------
@dataclass
class WMx64EntriesSchema:
    """ Annotation entries

    布局在 849 个真实 study（334,968 条）上逐字段验证，见 issue #36：
    头 0x02 u64 ms epoch（DFile0 之后 1–18 s）、0x0A "MM/DD/YYYY"、0x16 "HH:MM:SS"
    墙钟、0x20 u16 DFile 数；条目 0x02 u32 DFile 索引（高 16 位恒 0）、0x06 i32 DFile 内
    采样索引（有符号，负值 = 段起点之前）、0x0A u64 ms epoch（哨兵 0xFFFF…）。
    """
    header = 0x00, 0x24
    header_timestamp = 0x02, 0x0A
    timestamp_fmt = '<Q', 1000
    header_date = 0x0A, 0x14
    header_time = 0x16, 0x1E
    header_num_datalogs = 0x20, 0x22
    entry_type = 0x0, 0x2
    datalog_id = 0x2, 0x6
    sample_index = 0x6, 0xA
    timestamp = 0xA, 0x12
    text = 0x12, 0xC2
    line_size = 0xDC
