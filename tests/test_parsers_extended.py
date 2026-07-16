import os
import tempfile
import numpy as np
import pytest
from unittest.mock import patch, MagicMock
from epycon.iou.parsers import LogParser


class TestLogParser:
    """Test LogParser functionality."""

    def test_log_parser_init(self):
        """Test LogParser initialization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, 'test.log')
            with open(log_path, 'wb') as f:
                f.write(b'fake log data')
            
            parser = LogParser(log_path, version='4.3.2')
            # Check that diary is set correctly for x64 version
            from epycon.iou.parsers import WMx64LogSchema
            assert parser.diary == WMx64LogSchema

    @patch('epycon.iou.parsers._readmaster')
    @patch('epycon.iou.parsers.Header')
    def test_log_parser_get_header(self, mock_header_class, mock_readmaster):
        """Test LogParser get_header method."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, 'test.log')
            with open(log_path, 'wb') as f:
                f.write(b'fake log data')
            
            # Mock header
            mock_header = MagicMock()
            mock_header.amp.sampling_freq = 2000
            mock_header.num_channels = 4
            mock_header_class.return_value = mock_header
            
            parser = LogParser(log_path, version='4.3.2')
            parser._header = mock_header  # Simulate header being set
            header = parser.get_header()
            
            assert header == mock_header

    def test_log_parser_iteration(self):
        """Test LogParser iteration setup (simplified)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, 'test.log')
            with open(log_path, 'wb') as f:
                f.write(b'fake log data')
            
            parser = LogParser(log_path, version='4.3.2')
            # Test that parser is properly initialized as an iterator
            assert hasattr(parser, '__next__')
            assert hasattr(parser, '__iter__')

    def test_log_parser_context_manager(self):
        """Test LogParser context manager interface (simplified)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, 'test.log')
            with open(log_path, 'wb') as f:
                f.write(b'fake log data')
            
            parser = LogParser(log_path, version='4.3.2')
            # Test that parser has context manager methods
            assert hasattr(parser, '__enter__')
            assert hasattr(parser, '__exit__')


def _make_x64_log(path, raw_names, inactive=()):
    """构造最小 x64 假日志头（按 byteschema WMx64 偏移），只为测通道名解析。

    raw_names: 每个通道 name 字段的原始字节（≤12 字节，不足补 \x00），
    用于模拟 WorkMate 名字缓冲区未清零的残留尾字节。
    inactive: 这些下标的通道 ids 置双 0xFF（无有效参考，应被解析拒绝）。
    """
    import struct

    header = bytearray(0x393C)
    header[0x0:0x8] = struct.pack('<Q', 1700000000000)   # timestamp (ms)
    header[0x8:0xA] = struct.pack('<H', len(raw_names))  # num_channels
    for i, raw in enumerate(raw_names):
        off = 0x32 + i * 0x20                            # channels block + subblock
        header[off:off + len(raw)] = raw                 # name @ 0x0:0xC
        if i in inactive:
            header[off + 0xE:off + 0x10] = b'\xFF\xFF'   # ids：双参考无效
        else:
            header[off + 0xE:off + 0x10] = bytes([i, 0xFF])  # ids：单极
        header[off + 0x15] = 1                           # input_source: ECG
        header[off + 0x16:off + 0x18] = b'\xFF\xFF'      # jbox pins：无
    header[0x383A:0x393A] = bytes(i % 256 for i in range(0x100))  # 恒等 sample_mapping
    header[0x3832:0x3834] = struct.pack('<H', 1)         # resolution
    header[0x3838:0x383A] = struct.pack('<H', 2000)      # sampling_freq
    header[0x393A:0x393C] = struct.pack('<H', 0x393C)    # datablock start
    with open(path, 'wb') as f:
        f.write(header)


class TestChannelNameParsing:
    """通道名解析：WorkMate 名字缓冲区残留（内嵌 \x00 后的旧字节）应被截断。

    见 KNOWN_ISSUES #20：realdata 中如 '15\x00p'（残留 p）与干净 '15' 指向
    同一 reference，截断后应由既有去重吸收。
    """

    def test_name_truncated_at_first_null(self):
        """内嵌 \x00 后的残留尾字节不进入通道名。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, '00000000.log')
            _make_x64_log(log_path, [b'15\x00p', b'CS d'])

            with LogParser(log_path, version='4.3.2') as parser:
                names = parser.get_header().get_chnames()

            assert names == ['15', 'CS d']

    def test_truncated_duplicate_absorbed_by_dedup(self):
        """截断后与既有干净名相同的条目按重复跳过，不产生第二个通道。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, '00000000.log')
            _make_x64_log(log_path, [b'15', b'15\x00p'])

            with LogParser(log_path, version='4.3.2') as parser:
                header = parser.get_header()

            assert header.get_chnames() == ['15']
            assert header.channels.mount['15'] == (0,)

    def test_rejected_stale_row_does_not_suppress_later_valid_channel(self):
        """未激活行的残留脏名不得挤掉后续真实同名通道（Codex review P2）。

        名字只有在该行通过参考校验被接受后才进入去重集合；
        否则前面被拒绝的残留行会让真实通道被误判为重复而丢失。
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, '00000000.log')
            _make_x64_log(log_path, [b'15\x00p', b'15'], inactive={0})

            with LogParser(log_path, version='4.3.2') as parser:
                header = parser.get_header()

            assert header.get_chnames() == ['15']
            assert header.channels.mount['15'] == (0,)


class TestTwosComplementBoundary:
    """样本已是有符号 int32（`datablock.fmt = '<i4'`），_twos_complement 应为恒等变换。

    原实现 `limit = val // 2 - 1` 把 **最大正数** 2147483647（= 正向满量程）也判为负数，
    减去 2³² 得到 -2147483649——一个**超出 int32 值域**的数。realdata 与真实临床数据里
    整段 railed 的通道就是这个值；`extraction.RAIL_VALUES` 一度把 -2147483649 收进去
    迁就它，属于将就症状而非修根因。
    """

    def test_max_positive_int32_is_not_flipped(self):
        """2147483647 是最大正数，不是负数。"""
        from epycon.iou.parsers import _twos_complement
        out = _twos_complement(np.array([2147483647], dtype=np.int32), 4)
        assert int(out[0]) == 2147483647

    def test_signed_int32_input_is_identity(self):
        """输入已有符号，函数不该改动任何值。"""
        from epycon.iou.parsers import _twos_complement
        vals = np.array([0, 1, -1, 32767, -32768, 2147483646, 2147483647,
                         -2147483648, -2147483647], dtype=np.int32)
        out = _twos_complement(vals.copy(), 4)
        assert out.tolist() == vals.tolist()

    def test_no_value_escapes_int32_range(self):
        from epycon.iou.parsers import _twos_complement
        vals = np.array([2147483647, -2147483648], dtype=np.int32)
        out = _twos_complement(vals, 4)
        assert out.min() >= -2147483648
        assert out.max() <= 2147483647
