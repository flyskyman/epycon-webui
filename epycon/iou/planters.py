import os
import h5py as h
import numpy as np



from epycon.core._dataclasses import Entry
from epycon.core._formatting import _tocsv, _tosel, SignalPlantDefaults

from epycon.core._typing import (
    Union, PathLike, NumpyArray, Tuple, List, Any,
    Iterator, Optional, Dict, cast
)

from epycon.core._validators import (
    _validate_str,
)


def _ensure_hashable(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(_ensure_hashable(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_ensure_hashable(item) for item in value)
    return value


def _normalize_channel_name(channel_name: Union[str, bytes]) -> str:
    if isinstance(channel_name, bytes):
        channel_name = channel_name.decode('utf-8')
    return ''.join(str(channel_name).split())


class EntryPlanter:
    """标注条目输出器，用于导出 CSV/SEL 格式的标注数据。

    Attributes:
        entries: Entry 对象列表
    """

    entries: List[Entry]

    def __init__(
            self,
            entries: List[Entry],
            ) -> None:
        
        self.entries = entries

    def savecsv(
            self,
            f_path: Union[str, bytes, PathLike],            
            criteria: Optional[Dict[str, Union[str, List, Tuple, set]]] = None,
            **kwargs,
            ) -> None:
        
        ref_timestamp = kwargs.pop("ref_timestamp", None)
                
        # format entries
        content = _tocsv(
            list(self._filter(criteria=criteria)),
            ref_timestamp=ref_timestamp if ref_timestamp is not None else None,
            )
                
        with open(f_path, 'w', encoding='utf-8') as f_obj:
            f_obj.write(content)

    def savesel(
            self,
            f_path: Union[str, bytes, PathLike],
            ref_timestamp: float,
            sampling_freq: Union[int, float],
            channel_names: Union[List, Tuple],            
            criteria: Optional[Dict[str, Union[str, List, Tuple, set]]] = None,
            **kwargs,
            ) -> None:        

        # format entries
        _basename = os.path.basename(f_path)
        if isinstance(_basename, bytes):
            _file_name = _basename.decode('utf-8')
        else:
            _file_name = str(_basename)
        content = _tosel(
            list(self._filter(criteria=criteria)),
            ref_timestamp,
            sampling_freq,
            channel_names,
            _file_name,
            )
                
        with open(f_path, 'w', encoding='utf-8') as f_obj:
            f_obj.write(content)

    def _filter(
            self,            
            criteria: Optional[Dict[str, Union[str, List, Tuple, set]]] = None,
        ) -> Iterator[Entry]:
            """ Returns an iterator of MyDataClass items that pass the filter function.

            Args:
                param_name (Union[str, None], optional): _description_. Defaults to None.
                valid (Union[List, Tuple, None], optional): _description_. Defaults to None.

            Returns:
                dict: _description_
            """
            # convert to set
            if criteria:
                for field in ("fids", "groups"):
                    if field in criteria:
                        val = criteria[field]
                        if isinstance(val, str):
                            criteria[field] = {val}
                        elif isinstance(val, (list, tuple, set)):
                            normalized_values = set()
                            for item in val:
                                normalized_values.add(_ensure_hashable(item))
                            criteria[field] = normalized_values
                        else:
                            raise TypeError
            
            # iterate over items
            for item in self.entries:
                valid = True
                if criteria:
                    fids_set = cast(set, criteria.get("fids"))
                    groups_set = cast(set, criteria.get("groups"))
                    if (
                        fids_set
                        and item.fid not in fids_set                        
                        ):
                        valid = False
                    if (
                        valid
                        and groups_set
                        and item.group not in groups_set
                        ):
                        valid = False

                if valid:
                    yield item


class DatalogPlanter:
    """数据日志输出器基类。

    Attributes:
        f_path: 输出文件路径
        column_names: 列/通道名称列表
    """

    f_path: Union[str, bytes, os.PathLike]
    column_names: Union[List, Tuple, None]
    _f_obj: Any
    _extension: Optional[str]
    _header_isstored: bool
    _fmt: Optional[str]

    def __init__(
        self,
        f_path: Union[str, bytes, os.PathLike],
        column_names: Union[List, Tuple, None] = None,
        **kwargs: Any,
    ) -> None:
        
        self.f_path = f_path
        self._f_obj = None
        _ext = os.path.splitext(f_path)[1]
        if isinstance(_ext, bytes):
            _ext = _ext.decode('utf-8')
        self._extension = _validate_str("output file extension", str(_ext).lower(), valid_set={".csv", ".h5"})
        self.column_names = column_names

    def __enter__(self):
        raise NotImplementedError
    
    def __exit__(self, exc_type, exc_value, exc_traceback):
        # 如果是 HDF5 且存在预分配空间，进行裁剪
        if self._f_obj and self._extension == ".h5" and self._DATASET_DNAME in self._f_obj:
            try:
                _dataset = self._f_obj[self._DATASET_DNAME]
                logical_len = _dataset.attrs.get('_logical_length')
                if logical_len is not None and logical_len < _dataset.shape[1]:
                    _dataset.resize(logical_len, axis=1)
            except Exception:
                pass

        # Close file object
        if self._f_obj:
            self._f_obj.close()
        
        # set flags and attributes to defaults
        self._header_isstored = False
        self._fmt = None

        if exc_type:
            print(f"Exception occurred: {exc_type}, {exc_value}")

    def write(self, darray: NumpyArray, **kwargs: Any) -> None:
        raise NotImplementedError


class CSVPlanter(DatalogPlanter):
    """CSV 格式数据输出器。

    Attributes:
        delimiter: CSV 分隔符 (默认为逗号)
    """

    _delimiter: str
    delimiter: str  # 向后兼容别名

    def __init__(
        self,
        f_path: Union[str, bytes, os.PathLike],
        column_names: Union[List, Tuple, None] = None,
        **kwargs: Any,
    ) -> None:

        super().__init__(f_path, column_names)        

        self._delimiter = kwargs.pop("delimiter", ",")
        self._header_isstored = False
        self._fmt = None
        # Backwards compatibility: expose `delimiter` attribute for callers
        # that expect `planter.delimiter` (historical code).
        self.delimiter = self._delimiter
        
    def __enter__(self):
        try:            
            self._f_obj = open(self.f_path, "w")
        except IOError as e:
            raise IOError(e)
        return self

    def write(
        self,
        darray: NumpyArray,        
        **kwargs,
        ) -> None:
        """_summary_

        Args:
            darray (NumpyArray): _description_
            column_names (Union[list, tuple, None], optional): _description_. Defaults to None.
        """

        # write header
        if not self._header_isstored:
            if self.column_names is None:
                # create arbitrary column names if not provided
                self.column_names = [str(i) for i in range(darray.shape[1])]
            else:
                assert len(self.column_names) == darray.shape[1]
            
            self._f_obj.writelines(self.delimiter.join(self.column_names) + '\n')
            self._header_isstored = True

        # write data
        if self._fmt is None:
            # Use %d for integers, else fallback to default
            self._fmt = '%d' if np.issubdtype(darray.dtype, np.integer) else '%.4f'
            
        # Use numpy.savetxt for efficient vectorized writing
        np.savetxt(
            self._f_obj,
            darray,
            fmt=self._fmt,
            delimiter=self.delimiter,
            newline='\n'
        )



class HDFPlanter(DatalogPlanter):
    """HDF5 格式数据输出器，兼容 SignalPlant 格式。

    Attributes:
        cfg: SignalPlant 默认配置对象
        sampling_freq: 采样频率 (Hz)
        units: 物理单位 (str 或 List[str])
        entries: 可选的 Entry 列表
        factor: 数值缩放因子
        extra_attributes: 自定义 HDF5 属性字典
    """

    # class-specific constants
    _DATASET_DNAME: str = 'Data'
    _INFO_DNAME: str = 'Info'
    _CHANNEL_DNAME: str = 'ChannelSettings'
    _MARKS_DNAME: str = 'Marks'
    _DATACACHE_NAME: str = 'RAW'
    _LEFT_INDEX: int = 0
    _RIGHT_INDEX: int = 100
    _UNITS: str = 'mV'
    _PARSER: str = 'Epycon'

    cfg: SignalPlantDefaults
    sampling_freq: Union[int, float]
    units: Union[str, List[str], List[bytes], None]
    entries: Optional[List[Entry]]
    factor: Union[int, float]
    extra_attributes: Dict[str, Any]
    append_mode: bool
    _chunk_step: int = 100000  # 预分配步长
    _current_sample_count: int = 0 # Track actual number of samples written
    
    def __init__(
        self,
        f_path: Union[str, bytes, os.PathLike],
        column_names: Union[List, Tuple, None] = None,
        **kwargs: Any,        
        ) -> None:
        
        super().__init__(f_path, column_names) 
        
        self.cfg = SignalPlantDefaults()

        self.sampling_freq = kwargs.pop("sampling_freq", 1)
        self.units = kwargs.pop("units", "uV")
        self.entries = kwargs.pop("entries", None)
        self.factor = kwargs.pop("factor", 1000)
        self.extra_attributes = kwargs.pop("attributes", {})
        
        # [NEW] 压缩选项
        self.compression = kwargs.pop("compression", None)  # e.g., 'lzf', 'gzip'
        self.compression_opts = kwargs.pop("compression_opts", None)

        self._header_isstored = False

    def __enter__(self):
        try:            
            self._f_obj = h.File(self.f_path, "w")
        except IOError as e:
            raise IOError(e)
        return self
    
    def write(
            self,
            darray: NumpyArray,
            **kwargs: Any,
        ) -> None:
        
        # [NEW] 忽略空数据块，防止计算逻辑长度时出错
        if darray.shape[1] == 0:
            return
                
        # write header
        if not self._header_isstored:
            if self.column_names is None:
                # create arbitrary column names if not provided
                self.column_names = [str(i) for i in range(darray.shape[1])]
            else:
                assert len(self.column_names) == darray.shape[1]
            
            # make a list of encoded channel names with removed white spaces
            normalized_names = [_normalize_channel_name(item) for item in self.column_names]
            self.column_names = [name.encode('UTF-8') for name in normalized_names]

            # write attributes
            self._generate_attributes()
            # write channel info
            self._generate_channel_info()
            # write channel settings
            self._generate_channel_settings()

            self._header_isstored = True
        
        self.add_samples(darray)

    
    def _generate_attributes(self) -> None:
        """_summary_

        Args:
            data_arr (_type_): _description_
        """
        
        # Add attributes with mandatory parameters
        self._f_obj.attrs['Fs'] = np.array([self.sampling_freq], dtype=self.cfg.ATTR_DTYPE)        
        self._f_obj.attrs['GeneratedBy'] = self._PARSER
        self._f_obj.attrs['LeftI'] = self._LEFT_INDEX
        self._f_obj.attrs['RightI'] = self._RIGHT_INDEX

        # Add custom attributes (V68.1 Feature)
        if self.extra_attributes:
            for k, v in self.extra_attributes.items():
                try:
                    # Encode strings to bytes for compatibility
                    if isinstance(v, str):
                        self._f_obj.attrs[k] = v.encode('utf-8')
                    else:
                        self._f_obj.attrs[k] = v
                except Exception:
                    pass


    def _generate_channel_settings(
            self,            
            ):
            """Generates channel settings for Signal Plant

            Args:
                self.f_obj (obj): file obj. handle
                ch_names (list): List of channel names

            Raises:
                TypeError: Check for strings in <ch_names> list

            Returns:
                self.f_obj (obj): file obj. handle
            """

            # Generate content
            content = list()

            channel_settings_values: List[Any] = list(self.cfg.CHANNEL_SETTINGS.values())
            _col_names = self.column_names or []
            for ch_name in _col_names:
                # Generate single channel settings and append to content
                temp: List[Any] = [ch_name]
                temp.extend(channel_settings_values)
                content.append(tuple(temp))

            content = np.array(
                content,
                dtype=self.cfg.CHANNEL_DTYPES,
                )

            # add/append dataset
            if self._CHANNEL_DNAME in self._f_obj:
                del self._f_obj[self._CHANNEL_DNAME]
            
            self._f_obj.create_dataset(self._CHANNEL_DNAME, data=content)


    def _generate_channel_info(
            self,            
            ) -> None:
            """Generates channel info for Signal Plant

            Args:
                self.f_obj (obj): file obj. handle
                ch_names (list): List of channel names
                datacache_names (list, optional): List of channel names. If None names are generated using default values.
                unit_names (list, optional): List of physical unit names. If None names are generated using default values.

            Returns:
                self.f_obj (obj): file obj. handle
            """
            
            _col_names = self.column_names or []
            datacache_names = [self._DATACACHE_NAME.encode('UTF-8') for _ in _col_names]

            # make a list of physical units
            if self.units is None:
                self.units = self._UNITS
            
            _units = self.units
            if isinstance(_units, (tuple, list)):
                self.units = [item.encode('UTF-8') if isinstance(item, str) else item for item in _units]
            elif isinstance(_units, str):
                units_str: str = _units
                self.units = [units_str.encode('UTF-8')] * len(_col_names)
            else:
                raise TypeError

            # Generate content
            content_list = list(zip(_col_names, datacache_names, self.units))

            content_array = np.array(
                content_list,
                dtype=self.cfg.INFO_DTYPES,
                )    

            # add/append dataset
            if self._INFO_DNAME in self._f_obj:
                _info_ds = cast(h.Dataset, self._f_obj[self._INFO_DNAME])
                current_content = _info_ds[:]
                content_array = np.append(current_content, content_array)

                del self._f_obj[self._INFO_DNAME]
            
            self._f_obj.create_dataset(self._INFO_DNAME, data=content_array)

    def add_samples(
            self,
            darray: NumpyArray,            
            ):
        """_summary_

        Args:
            data_arr (_type_): ndarray of the same length as data.shape[1]

        Raises:
            ValueError: Incosistent shape of the input data.
        """
        # TODO: export json with fs, resolution and units
        # columns -> samples, rows -> channels
        darray = darray.transpose()

        # Only float32 supported by SignalPlant
        if not np.issubdtype(darray.dtype, np.float32):
            darray = darray.astype(np.float32) / self.factor

        # Create new dataset if not exists
        if self._DATASET_DNAME not in self._f_obj:
            # 初始预分配更大的空间，提高后续追加效率
            initial_capacity = max(darray.shape[1], self._chunk_step)
            self._f_obj.create_dataset(
                self._DATASET_DNAME, 
                data=None, 
                shape=(darray.shape[0], darray.shape[1]), 
                maxshape=(darray.shape[0], None), 
                chunks=True, 
                dtype=self.cfg.DATASET_DTYPE,
                compression=self.compression,
                compression_opts=self.compression_opts
            )
            # 设置当前实际样本数（作为属性存储，方便追踪逻辑长度）
            self._f_obj[self._DATASET_DNAME].attrs['_logical_length'] = darray.shape[1]
            # 写入数据
            self._f_obj[self._DATASET_DNAME][:, :darray.shape[1]] = darray
            return
    
        # Check for data shape consistency, raise error if does not match
        _dataset = cast(h.Dataset, self._f_obj[self._DATASET_DNAME])
        if _dataset.shape[0] != darray.shape[0]:
            raise ValueError(
                f"""Inconsistent shape of the input data.
                Expected to be {_dataset.shape[0]}, 
                got {darray.shape[0]} instead."""
                )            

        # 获取逻辑长度（实际写入的样本数）
        logical_len = _dataset.attrs.get('_logical_length', _dataset.shape[1])
        new_logical_len = logical_len + darray.shape[1]
        
        # 如果当前物理容量不足，触发预分配 resize
        if new_logical_len > _dataset.shape[1]:
            new_physical_len = ((new_logical_len // self._chunk_step) + 1) * self._chunk_step
            _dataset.resize(new_physical_len, axis=1)
                
        # 写入数据并更新逻辑长度
        _dataset[:, logical_len:new_logical_len] = darray 
        _dataset.attrs['_logical_length'] = new_logical_len
        
    def add_marks(
        self,
        positions: Union[List, Tuple],
        groups: Union[List, Tuple],
        messages: Union[List, Tuple],
        ) -> None:

        """_summary_

        Args:
            start_sample (_type_): _description_
            end_sample (_type_): _description_
            group_id (bytes, optional): _description_. Defaults to ''.
            validity (float, optional): _description_. Defaults to 0.0.
            channel_id (bytes, optional): _description_. Defaults to ''.
            info (bytes, optional): _description_. Defaults to b'a'.
        """
        
        # TODO: add mutiple marks at once

        marks = list()
        for position, group, message in zip(positions, groups, messages):
            # filter out negative samples
            position = max(1, position)

            group_bytes = group if isinstance(group, bytes) else group.encode('UTF-8')
            message_bytes = message if isinstance(message, bytes) else message.encode('UTF-8')
            _col_names = self.column_names or []
            channel_id = _col_names[0] if _col_names else b''

            marks.append((
                int(position),
                int(position),
                group_bytes,
                1.0,
                channel_id,
                message_bytes
            ))

        # create NumPy array
        content = np.array(marks, dtype=self.cfg.MARKS_DTYPES)

        if self._MARKS_DNAME in self._f_obj:           
            # remove old dataset and store the new one
            del self._f_obj[self._MARKS_DNAME]

        self._f_obj.create_dataset(self._MARKS_DNAME, data=content)

