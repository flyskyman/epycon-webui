
import os
import shutil
import tempfile
import struct
import unittest
import numpy as np
from epycon.iou.parsers import LogParser

class TestCornerCases(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.wm_version = "4.3.2"  # Testing WMx64
    
    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def create_dummy_log(self, filename, size_bytes=0, header_only=False, random_data=False):
        path = os.path.join(self.test_dir, filename)
        
        # Header size for WMx64
        HEADER_SIZE = 0x393C
        
        if size_bytes == 0 and not header_only:
            # Completely empty file
            with open(path, 'wb') as f:
                pass
            return path
            
        header = bytearray(HEADER_SIZE)
        
        if random_data:
            # Random garbage
            data_to_write = os.urandom(size_bytes)
            with open(path, 'wb') as f:
                f.write(data_to_write)
            return path
            
        # --- Build Minimal Valid Header (WMx64) ---
        # 1. Timestamp (uint64 scaled 1000)
        header[0:8] = struct.pack('<Q', 1000000) 
        # 2. Num Channels (uint16)
        header[0x8:0xA] = struct.pack('<H', 1) 
        # 3. Data start address
        header[0x393A:0x393C] = struct.pack('<H', HEADER_SIZE & 0xFFFF)
        
        # 4. Amplifier Settings (needed to avoid parse errors)
        # WMx64 offsets: Res: 0x3832, FS: 0x3838
        header[0x3832:0x3834] = struct.pack('<H', 1)    # Resolution
        header[0x3838:0x383A] = struct.pack('<H', 1000) # Sampling Freq
        
        # 5. Sample Mapping (0x383A - 0x393A)
        # Just map 1:1 for simplicity
        sample_map_start = 0x383A
        for i in range(256):
            if sample_map_start + i < HEADER_SIZE:
                header[sample_map_start + i] = i
        
        # 6. Channel 1 Subblock
        # Offset 0x32, size 0x20 per channel
        ch_offset = 0x32
        
        # Name: "CH1" + zeros
        name = b'CH1' + b'\x00'*9
        header[ch_offset:ch_offset+12] = name
        
        # IDs mapping (0xE offset) -> bytes [0, 0xFF] (0=valid index, 0xFF=none)
        header[ch_offset+0xE : ch_offset+0x10] = b'\x00\xFF'
        
        # Input Source (0x15 offset) -> 1 (Surface)
        header[ch_offset+0x15] = 1
        
        # JBox Pins (0x16 offset) -> [0xFF, 0xFF]
        header[ch_offset+0x16 : ch_offset+0x18] = b'\xFF\xFF'

        # --- Data Content ---
        if header_only:
            data = b''
        elif size_bytes > HEADER_SIZE:
             # Make sure size_bytes aligns with sample size (4 bytes/sample)
             data_len = size_bytes - HEADER_SIZE
             num_samples = data_len // 4
             data = b''.join(struct.pack('<i', i % 1000) for i in range(num_samples))
        else:
             data = b'' # Should not happen based on logic below but safe fallback

        with open(path, 'wb') as f:
            f.write(header)
            f.write(data)
        
        return path

    def test_empty_file(self):
        """Test parsing a completely empty file (0 bytes)"""
        path = self.create_dummy_log("empty.log", size_bytes=0)
        with self.assertRaises(Exception): # Should assert specific exception, likely ValueError/OSError
            with LogParser(path, version=self.wm_version) as parser:
                pass

    def test_header_only_file(self):
        """Test parsing a file with only header (valid) but no data"""
        path = self.create_dummy_log("header_only.log", header_only=True)
        with LogParser(path, version=self.wm_version) as parser:
            header = parser.get_header()
            self.assertIsNotNone(header)
            self.assertEqual(len(header.channels), 1)
            
            # Read data - should be empty iterator or yield empty chunks
            chunks = list(parser)
            self.assertEqual(len(chunks), 0)

    def test_truncated_header(self):
        """Test parsing a file smaller than header size"""
        path = os.path.join(self.test_dir, "truncated.log")
        with open(path, 'wb') as f:
            f.write(b'\x00' * 100) # Only 100 bytes
            
        with self.assertRaises(Exception):
            with LogParser(path, version=self.wm_version) as parser:
                pass

    def test_garbage_data(self):
        """Test parsing a file with random garbage"""
        path = self.create_dummy_log("garbage.log", size_bytes=20000, random_data=True)
        # This might fail during header parsing or data reading
        with self.assertRaises(Exception):
             with LogParser(path, version=self.wm_version) as parser:
                 list(parser)

    def test_single_sample_file(self):
        """Test parsing a file with exactly one sample"""
        # Header + 4 bytes (1 sample * 1 channel * 4 bytes)
        HEADER_SIZE = 0x393C
        path = self.create_dummy_log("single.log", size_bytes=HEADER_SIZE + 4)
        
        with LogParser(path, version=self.wm_version) as parser:
            chunks = list(parser)
            self.assertTrue(len(chunks) > 0)
            data = np.concatenate(chunks)
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0], 0)

if __name__ == '__main__':
    unittest.main()
