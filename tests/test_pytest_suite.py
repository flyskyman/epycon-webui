"""
Pytest 兼容的测试套件
"""
import os
import sys
import pytest

# 添加项目根目录到路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


class TestBasicFunctionality:
    """基础功能测试"""
    
    def test_parsebin_bytes(self):
        """测试 parsebin 接受 bytes"""
        from epycon.core.bins import parsebin
        result = parsebin(b'\x01\x00', '<H')
        assert result == 1
        assert isinstance(result, int)
    
    def test_parsebin_bytearray(self):
        """测试 parsebin 接受 bytearray"""
        from epycon.core.bins import parsebin
        result = parsebin(bytearray(b'\xFF\x00'), '<H')
        assert result == 255
    
    def test_parsebin_multiple_values(self):
        """测试 parsebin 返回多值"""
        from epycon.core.bins import parsebin
        result = parsebin(b'\x01\x00\x02\x00', '<HH')
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert result == (1, 2)
    
    def test_entry_with_str_group(self):
        """测试 Entry 支持 str group"""
        from epycon.core._dataclasses import Entry
        entry = Entry(fid='00000001', group='PROTOCOL', timestamp=1234567890, message='Test')
        assert entry.group == 'PROTOCOL'
        assert isinstance(entry.group, str)
    
    def test_entry_with_int_group(self):
        """测试 Entry 支持 int group"""
        from epycon.core._dataclasses import Entry
        entry = Entry(fid='00000002', group=1, timestamp=1234567891, message='Test2')
        assert entry.group == 1
        assert isinstance(entry.group, int)
    
    def test_logparser_optional_params(self):
        """测试 LogParser 接受 Optional 参数"""
        from epycon.iou.parsers import LogParser
        try:
            parser = LogParser(
                f_path="nonexistent.log",
                version=None,
                samplesize=1024,
                start=0,
                end=None,
            )
        except FileNotFoundError:
            pass  # 预期行为


class TestEdgeCases:
    """边缘情况测试"""
    
    def test_parsebin_boundary_values(self):
        """测试 parsebin 边界值"""
        from epycon.core.bins import parsebin
        
        # 单字节
        assert parsebin(b'\xFF', 'B') == 255
        
        # 多字节
        assert parsebin(b'\xFF\xFF', '<H') == 65535
        
        # 有符号数
        assert parsebin(b'\xFF\xFF', '<h') == -1
    
    def test_entry_group_types(self):
        """测试 Entry 支持多种 group 类型"""
        from epycon.core._dataclasses import Entry
        
        test_cases = [
            ('PROTOCOL', str),
            ('EVENT', str),
            ('NOTE', str),
            (1, int),
            (2, int),
            (0, int),
        ]
        
        for group_val, expected_type in test_cases:
            entry = Entry(fid='test', group=group_val, timestamp=123, message='test')
            assert isinstance(entry.group, expected_type)
    
    def test_group_map_values(self):
        """测试 GROUP_MAP 所有值都是 str"""
        from epycon.config.byteschema import GROUP_MAP
        
        for key, value in GROUP_MAP.items():
            assert isinstance(value, str), f"GROUP_MAP[{key}] 应该是 str"
        
        # 测试默认值
        default = GROUP_MAP.get(999, 0)
        assert default == 0


class TestIntegration:
    """集成测试"""
    
    @pytest.fixture
    def example_log(self):
        """提供示例日志文件路径"""
        path = "examples/data/study01/00000000.log"
        if os.path.exists(path):
            return path
        pytest.skip(f"示例文件不存在: {path}")
    
    @pytest.fixture
    def example_entries(self):
        """提供示例 entries 文件路径"""
        path = "examples/data/study01/entries.log"
        if os.path.exists(path):
            return path
        pytest.skip(f"Entries 文件不存在: {path}")
    
    def test_read_header(self, example_log):
        """测试读取 header"""
        from epycon.iou.parsers import LogParser
        
        with LogParser(example_log, version='4.2') as parser:
            header = parser.get_header()
            assert header is not None
            assert hasattr(header, 'timestamp')
            assert hasattr(header, 'num_channels')
            assert hasattr(header, 'amp')
    
    def test_read_entries(self, example_entries):
        """测试读取 entries"""
        from epycon.iou.parsers import _readentries
        
        entries = _readentries(example_entries, version='4.2')
        assert isinstance(entries, list)
        
        if entries:
            entry = entries[0]
            assert hasattr(entry, 'fid')
            assert hasattr(entry, 'group')
            assert hasattr(entry, 'timestamp')
            assert hasattr(entry, 'message')
            assert isinstance(entry.group, (int, str))
    
    def test_type_annotations(self):
        """测试类型注解完整性"""
        from typing import get_type_hints
        from epycon.iou.parsers import LogParser
        from epycon.core._dataclasses import Entry
        from epycon.core.bins import parsebin
        
        # LogParser
        hints = get_type_hints(LogParser.__init__)
        assert 'version' in hints
        assert 'end' in hints
        
        # Entry
        hints = get_type_hints(Entry)
        assert 'group' in hints
        
        # parsebin
        hints = get_type_hints(parsebin)
        assert 'barray' in hints


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
