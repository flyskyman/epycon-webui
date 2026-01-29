import os
import sys
import struct
from itertools import islice
from datetime import datetime
from collections import abc
from typing import BinaryIO

import numpy as np
import h5py as h

from epycon.core._typing import (
    Union, List, Sequence, PathLike, ArrayLike, Optional,
)

from epycon.core._validators import (
    _validate_int, _validate_str, _validate_version, _validate_reference
)

from epycon.core.bins import (
    readbin,
    readchunk,
    parsebin,
    )

from epycon.core.helpers import (
    safe_string,
    pretty_json,
)

from epycon.utils.decorators import checktypes
from epycon.core._dataclasses import (
    Header,
    Channel,
    Channels,
    Entry,    
)

from epycon.config.byteschema import (
    WMx32LogSchema, WMx32MasterSchema, WMx32EntriesSchema,
    WMx64LogSchema, WMx64MasterSchema, WMx64EntriesSchema,
)

from epycon.config.byteschema import (
    GROUP_MAP, SOURCE_MAP, MASTER_FILENAME, ENTRIES_FILENAME
)


def _twos_complement(darray, bytesize):
    import numpy as np
    # 强制使用 64 位整数，修复 Windows 溢出报错
    val = np.int64(1 << (bytesize * 8))
    darray = darray.astype(np.int64)
    limit = np.int64(val // 2 - 1)
    darray[darray >= limit] -= val
    return darray


class LogParser(abc.Iterator):
    """_summary_

    Args:
        abc (_type_): _description_
    """
    def __init__(
        self,
        f_path: Union[str, bytes, os.PathLike],
        version: Optional[str] = None,        
        samplesize: int = 1024,
        start: int = 0,
        end: Optional[int] = None,
        **kwargs
        ) -> None:
        super().__init__()

        # validate WM version and return correct byte schema             
        if _validate_version(version) == 'x32':
            self.diary = WMx32LogSchema
        elif _validate_version(version) == 'x64':
            self.diary = WMx64LogSchema
        else:
            raise NotImplementedError

        self.f_path = f_path
        self.timestampfmt, self.timestampfactor = self.diary.timestamp_fmt
        
        self.samplesize = _validate_int("chunk size", samplesize, min_value=1024)
        self.start = _validate_int("start sample", start, min_value=0)
        self.end = _validate_int("end sample", end, min_value=start) if end is not None else None
            
        
        # file related content required for parsing.        
        self._f_obj: Optional[BinaryIO] = None
        self._header: Optional[Header] = None
        self._stopbyte: Optional[Union[int, float]] = None
        self._chunksize: Optional[int] = None
        self._blocksize: Optional[int] = None
        self._channel_mapping: Optional[object] = None
        self._mount_negidx: Optional[object] = None
        self._mount_posidx: Optional[object] = None                


    def __enter__(self):
        try:
            self._f_obj = open(self.f_path, "rb")

            # read and store header in advance
            self._header = self._readheader()
            
            # Ensure start is not None (it's validated in __init__)
            assert self.start is not None
            assert self.samplesize is not None
            
            # adjust the range of datablocks to read given as the number of active channels times bytes per sample
            self._block_size = self._header.num_channels * self.diary.sample_size 

            # compute size of data block to read at once
            self._chunksize = self._block_size * self.samplesize

            # convert start sample to byte address         
            startbyte = self._header.datablock_address + self.start * self._block_size

            if self.end is not None:
                # convert end sample to byte address
                stopbyte = self._header.datablock_address + self.end * self._block_size                
            else:
                # set stop byte to the last one (use a very large int instead of Inf)
                stopbyte = sys.maxsize

            # get address of the last/user defined byte
            self._stopbyte = int(min(stopbyte, self._f_obj.seek(0, 2)))                      
            
            # Seek to start position
            self._f_obj.seek(max(self._header.datablock_address, startbyte))

        except IOError as e:            
            raise IOError(e)
    
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        # Clear file header
        if self._header is not None:
            self._header = None

        # Close file object
        if self._f_obj:
            self._f_obj.close()
        
        if exc_type:
            print(f"Exception occurred: {exc_type}, {exc_value}")

    def __iter__(self):
        return self

    def __next__(self) -> np.ndarray:
        """_summary_

        Raises:
            StopIteration: _description_            

        Returns:
            np.ndarray: _description_
        """
        # Type assertions to help type checker
        assert self._f_obj is not None
        assert self._chunksize is not None
        assert self._stopbyte is not None
        
        try:
            if self._f_obj.tell() >= self._stopbyte:
                raise StopIteration
            
            chunksize_raw = min(self._chunksize, self._stopbyte - self._f_obj.tell())
            chunksize = int(chunksize_raw)  # Ensure it's an int
            chunk = self._f_obj.read(chunksize)

            if not chunk:
                raise StopIteration
            else:
                chunk = np.frombuffer(
                    bytearray(chunk),
                    dtype=np.dtype(self.diary.datablock.fmt),
                    )
            
        except StopIteration:
            self.__exit__(exc_type=None, exc_value=None, exc_traceback=None)
            raise

        return self._process_chunk(chunk)


    def read(
        self,
    ) -> np.ndarray:
        """ Reads block of data.

        Returns:
            np.ndarray: _description_
        """
        # Type assertions
        assert self._f_obj is not None
        assert self._stopbyte is not None
        
        bytes_to_read = int(self._stopbyte - self._f_obj.tell())
        chunk = self._f_obj.read(bytes_to_read)

        if not chunk:
            # Return empty array instead of None
            return np.array([], dtype=np.dtype(self.diary.datablock.fmt))
        else:
            chunk = np.frombuffer(
                bytearray(chunk),
                dtype=np.dtype(self.diary.datablock.fmt),
                )
            
        return self._process_chunk(chunk)
            

    def _process_chunk(
        self,
        chunk: np.ndarray,
        ) -> np.ndarray:
        """_summary_

        Args:
            byte_chunk (_type_): _description_

        Returns:
            _type_: _description_
        """
        # Type assertion
        assert self._header is not None
        
        chunk = _twos_complement(chunk, self.diary.sample_size)

        # Multiply signal by resolution to get correct physical units.
        chunk = chunk * self._header.amp.resolution

        # Reshape array
        return chunk.reshape(
            (
                len(chunk) // self._header.num_channels,
                self._header.num_channels,
                )
            )        


    def _readheader(self) -> Header:
        """_summary_

        Args:
            f_path (str): _description_

        Returns:
            _type_: _description_
        """

        # read header bytearray
        start_byte, bytes_to_read = self.diary.header.block_size
        bheader = readbin(self.f_path, start_byte, bytes_to_read)        

        # Get timestamp (preserve original units, typically milliseconds)
        startbyte, endbyte = self.diary.header.timestamp
        timestamp_raw = parsebin(bheader[startbyte:endbyte], self.timestampfmt)
        # Handle tuple or scalar return from parsebin
        if isinstance(timestamp_raw, tuple):
            timestamp_raw = timestamp_raw[0]
        # Preserve raw timestamp (milliseconds) instead of converting to seconds
        timestamp = int(timestamp_raw)

        # Get number of active channels
        startbyte, endbyte = self.diary.header.num_channels
        num_channels_raw = parsebin(bheader[startbyte:endbyte], '<H')
        num_channels = int(num_channels_raw) if not isinstance(num_channels_raw, tuple) else int(num_channels_raw[0])

        # Get the address of the first data chunk
        startbyte, endbyte = self.diary.datablock.start_address
        datablock_raw = parsebin(bheader[startbyte:endbyte], '<H')
        datablock_startbyte = int(datablock_raw) if not isinstance(datablock_raw, tuple) else int(datablock_raw[0])

        # create mapping from channel id (index) into sample position (value at given index) in the data chunk
        startbyte, endbyte = self.diary.datablock.sample_mapping
        sample_mapping = parsebin(bheader[startbyte:endbyte], 'B' * (endbyte-startbyte))
        
        # Get the amplifier hardware settings
        amp_settings = dict()
        hp_raw = parsebin(
            bheader[self.diary.amplifier.highpass_freq[0]:self.diary.amplifier.highpass_freq[1]],
            '<H',
        )
        amp_settings["highpass_freq"] = int(hp_raw) if not isinstance(hp_raw, tuple) else int(hp_raw[0])

        notch_raw = parsebin(
            bheader[self.diary.amplifier.notch_freq[0]:self.diary.amplifier.notch_freq[1]],
            '<H',
        )
        amp_settings["notch_freq"] = int(notch_raw) if not isinstance(notch_raw, tuple) else int(notch_raw[0])

        res_raw = parsebin(
            bheader[self.diary.amplifier.resolution[0]:self.diary.amplifier.resolution[1]],
            '<H',
        )
        amp_settings["resolution"] = int(res_raw) if not isinstance(res_raw, tuple) else int(res_raw[0])

        sf_raw = parsebin(
            bheader[self.diary.amplifier.sampling_freq[0]:self.diary.amplifier.sampling_freq[1]],
            '<H',
        )
        amp_settings["sampling_freq"] = int(sf_raw) if not isinstance(sf_raw, tuple) else int(sf_raw[0])

        # for field_name, (startbyte, endbyte) in self.diary.amplifier.items():            
        #     amp_settings[field_name] = parsebin(bheader[startbyte:endbyte], '<H')
        
        # get info about recording channels
        channels = Channels(list(), dict())
        used_channels = set()
        
        startbyte, endbyte = self.diary.channels.block_size
        
        it = iter(bheader[startbyte:endbyte])
        i = 0
        mount = dict()
        while (bchunk := bytes(islice(
            it,
            self.diary.channels.subblock_size[1],
            ))):

            # validate channel existence
            if bchunk[:1] == b"\x00":
                continue
            
            ch_name = safe_string(
                bchunk[self.diary.channels.name[0]:self.diary.channels.name[1]].decode("unicode-escape").strip("\x00")
            )

            # skip channel duplicates
            if ch_name in used_channels:
                continue
            else:
                used_channels.add(ch_name)

            # source of data acquisition
            startbyte, endbyte = self.diary.channels.input_source
            source_id = parsebin(bchunk[startbyte:endbyte], 'B')
            source_id_int = int(source_id) if not isinstance(source_id, tuple) else int(source_id[0])
            source = SOURCE_MAP[source_id_int]            

            # retrieve and map bytes into data byte order in the stream data chunk
            startbyte, endbyte = self.diary.channels.ids
            mount_pair = parsebin(bchunk[startbyte:endbyte], 'BB')
            references = list(map(
                lambda x: sample_mapping[x] if x != 0xff else None,
                mount_pair,
            ))

            try:
                # check if channel was actively recorded
                _validate_reference(*references)
            except ValueError:
                continue

            # retrieve and filter junction box pins; pin polarity = [positive, negative]
            startbyte, endbyte = self.diary.channels.jbox_pins
            pins = parsebin(bchunk[startbyte:endbyte], 'BB')
            pins = list(map(
                lambda x: x if x != 0xff else None,
                pins,
            ))

            if any(item is None for item in references):
                # store single-reference leads (usually unipolar or surface ecg leads)
                channels.content.append(
                    Channel(ch_name, references[0], source, (pins[0],) if pins[0] is not None else tuple(),)
                    )
                
                # create mapping computed channel -> index of the original channel in the channels list
                channels.mount[ch_name] = (i,)
                i += 1
            else:
                # store bipolar leads as separate unipolar channels
                channels.content.extend([
                    Channel("u+"+ch_name, references[0], source, (pins[0],) if pins[0] is not None else tuple(),),
                    Channel("u-"+ch_name, references[1], source, (pins[1],) if pins[1] is not None else tuple(),),
                    ])
                
                # create mapping computed channel -> index of the original channel in the channels list
                channels.mount[ch_name] = (i, i+1)
                i += 2
            
        return Header(
            timestamp,
            num_channels,
            channels,  # Pass the Channels object with mount mappings
            amp_settings,  # type: ignore  # __post_init__ will convert dict to AmplifierSettings
            datablock_startbyte,
        )

    def get_header(self):
        """ Returns pased datalog header.

        Returns:
            _type_: _description_
        """
        return self._header


def _mount_channels(darray, mappings):
    """Mount channels from raw data array based on mappings.
    
    Args:
        darray: Raw data array with shape (samples, all_channels)
        mappings: Dict mapping channel names to source indices.
                  Values must be lists: [index] for single ref,
                  or [pos_ref, neg_ref] for differential.
    
    Returns:
        Mounted data array with shape (samples, len(mappings))
    
    Raises:
        TypeError: If mapping values are not lists/tuples
    """
    result = np.empty((len(mappings), darray.shape[0]), dtype=darray.dtype)

    # Iterate through the tuples, performing the selection/summation    
    for t, source in enumerate(mappings.values()):
        # Normalize source to list if it's a single int (common mistake)
        if isinstance(source, int):
            source = [source]
        elif not isinstance(source, (list, tuple)):
            raise TypeError(f"Mapping values must be list or tuple, got {type(source).__name__}")
        
        if len(source) == 1:
            result[t] = darray[:, source[0]]
        else:            
            result[t] = darray[:, source[0]] - darray[:, source[1]]
        
    return result.transpose()


@checktypes
def _readdata(
    f_path: str,
    **kwargs,
) -> Union[np.ndarray, LogParser]:
    """
    """ 

    # Extract some of the arguments (pass chunksize on).    
    chunksize = kwargs.get("chunksize", None)
    if chunksize is not None:
        chunksize = _validate_int("chunksize", chunksize, min_value=1)

    nsamples = kwargs.get("nrows", None)
    
    # Instantiate data parser.
    parser = LogParser(f_path, **kwargs)

    if chunksize:
        return parser

    with parser:
        return parser.read()


@checktypes
def _readheader(
    f_path: str,
) -> Header:
    """_summary_

    Args:
        f_path (str): _description_

    Returns:
        Header: _description_
    """
    
    # Instantiate data parser.
    parser = LogParser(f_path)
    
    with parser:
        header = parser.get_header()
    
    if header is None:
        raise ValueError(f"Failed to read header from {f_path}")
    
    return header


def _readmaster(
    f_path: Union[str, bytes, os.PathLike],
    ):
    """ Parses the content of the MASTER file.

    Args:
        f_path (Union[str, bytes, os.PathLike]): path to  MASTER file

    Raises:
        IOError: _description_

    Returns:
        _type_: _description_
    """

    try:
        # read binary file
        barray = readbin(f_path)
    except IOError as e:
        raise IOError

    # Read ID
    id_start, id_end = WMx64MasterSchema.subject_id    
    sub_id = barray[id_start:id_end].decode("ascii", "ignore").strip("\x00")

    # Read Name (Added in V68.1)
    name_start, name_end = WMx64MasterSchema.subject_name
    sub_name = barray[name_start:name_end].decode("ascii", "ignore").strip("\x00")

    return {
        "id": sub_id,
        "name": sub_name
    }


def _readentries(
    f_path: Union[str, bytes, os.PathLike],
    version: Optional[str] = None,
    ):
    """ Parses the content of the ENTRIES file.

    Args:
        f_path (Union[str, bytes, os.PathLike]): _description_

    Returns:
        _type_: _description_
    """
    # TODO: check entries at the end of procedure with invalid timestamp

    # initialize entries dictionary
    entries = list()                           
                
    # validate WM version and return correct byte schema             
    if _validate_version(version) == 'x32':
        diary = WMx32EntriesSchema
    elif _validate_version(version) == 'x64':
        diary = WMx64EntriesSchema
    else:
        raise NotImplementedError
    
    try:
        # read entire binary file
        barray = readbin(f_path)
    except IOError as e:
        raise IOError

    if barray is None:
        return entries

    # Validate expected byte size
    if (len(barray) - diary.header[1]) % diary.line_size != 0:
        sys.exit(f'Invalid length of byte array. Check byte schema version.')
        
    # Convert header type into byte format and timestamp factor
    fmt, factor = diary.timestamp_fmt

    # Read and validate timestamp format (preserve milliseconds)
    header_timestamp = int(struct.unpack(fmt, barray[diary.header_timestamp[0]:diary.header_timestamp[1]])[0])

    try:
        # header_timestamp is stored in milliseconds; convert to seconds for datetime
        header_date = datetime.fromtimestamp(header_timestamp / factor)
    except ValueError as err:
        sys.exit(f'Invalid timestamp format.')    

    # iterate over byte array
    for pointer in range(diary.header[1], len(barray), diary.line_size):
        # entry type
        start_byte, end_byte = diary.entry_type
        group = struct.unpack("<H", barray[pointer + start_byte:pointer + end_byte])[0]        

        # datalog file uid
        start_byte, end_byte = diary.datalog_id
        datalog_uid = struct.unpack("<L", barray[pointer + start_byte:pointer + end_byte])[0]
        datalog_uid = f"{datalog_uid:08x}"

        # timestamp (preserve milliseconds)
        start_byte, end_byte = diary.timestamp
        timestamp = int(struct.unpack(fmt, barray[pointer + start_byte:pointer + end_byte])[0])

        # retrieve text annotation
        # Text is null-terminated, decode as latin-1 (single-byte encoding)
        start_byte, end_byte = diary.text
        text_bytes = barray[pointer + start_byte:pointer + end_byte]
        # Find null terminator and decode
        null_pos = text_bytes.find(b'\x00')
        if null_pos >= 0:
            text_bytes = text_bytes[:null_pos]
        message = text_bytes.decode('latin-1', errors='replace')
        # Filter out non-printable characters (keep ASCII printable range)
        message = "".join(c for c in message if c.isprintable() or c in ' \t')
        
        # Skip entries with empty or whitespace-only messages
        # These are typically device-generated markers (e.g., IDK type with \x06)
        if not message or not message.strip():
            continue

        entries.append(
            Entry(
                fid=datalog_uid,
                group=GROUP_MAP.get(group, 0),  # Returns str label or 0 for unknown
                timestamp=timestamp,
                message=message,
                )
        )        

    return entries