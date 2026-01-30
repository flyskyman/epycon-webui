import os

from epycon.core._typing import (
    Union, List, Any, Tuple, PathLike, 
)

def _validate_int(
    name: str,
    value: Union[int, float],
    min_value: int = 0,
    mxn_value: Union[int, None] = None,
    ) -> Union[int, None]:
    """Checks whether the parameter is either
    an int or float that can be cast to an integer
    without loss of accuracy. Raises a ValueError otherwise.

    Args:
        name (str): Parameter name for error messages.
        value (Union[int, float]): The value to validate.
        min_value (int, optional): Minimum allowed value. Defaults to 0.
        mxn_value (Union[int, None], optional): Maximum allowed value. Defaults to None.

    Raises:
        ValueError: If value is not a valid integer within the specified range.
        
    Returns:
        Union[int, None]: The validated integer value, or None if input was None.
    """    

    if value is None:
        return value

    messsage = f"Parameter `{name}` expected to be an {min_value} <= integer <= {mxn_value}"
    if isinstance(value, float):
        if int(value) != value:
            raise ValueError(messsage)
        value = int(value)

    if not isinstance(value, int):
        raise ValueError(messsage)

    if mxn_value is not None:
        assert mxn_value >= min_value
        if value > mxn_value:
            raise ValueError(messsage)

    if value < min_value:    
        raise ValueError(messsage)

    return int(value)


def _validate_str(
    name: str,
    value: str,
    valid_set: set,
    ) -> Union[str, None]:
    """Checks whether the parameter belongs to a set of valid parameters.
    Raises a ValueError otherwise.

    Args:
        name (str): Parameter name for error messages.
        value (Union[str, None]): The string value to validate.
        valid_set (set): Set of valid string values.        

    Raises:
        ValueError: If value is not in the valid_set.
        
    Returns:
        Union[str, None]: The validated string value, or None if input was None.
    """    

    if value is None:
        return value

    messsage = f"Parameter `{name}` containing `{value}` expected to be from {valid_set}"    
    if not isinstance(value, str):
        raise ValueError(messsage)

    if value not in valid_set:
        raise ValueError(messsage)

    return value


def _validate_version(
    version: Union[str, None],
) -> str:
    valid_x32, valid_x64 = {'4.1'}, {'4.2', '4.3', '4.3.2'} 

    if version is None:
        return 'x64'
    
    if version in valid_x32:
        return 'x32'    
    elif version in valid_x64:
        return 'x64'
    else:
        raise ValueError(f'Invalid parameter `version`: {version}. Expected one of {valid_x32 | valid_x64}')


def _validate_reference(positive_ref, negative_ref):
    """ Validates electrical reference indices.
    If ref == 140, the lead is inactive with no recorded signal.

    Args:
        positive_ref (int): Positive electrode reference index.
        negative_ref (int): Negative electrode reference index.

    Raises:
        ValueError: If either reference is 140 (inactive lead).
        ValueError: If both references are None.
    """
    if any(value == 140 for value in (negative_ref, positive_ref)):
        raise ValueError
    
    if all(value is None for value in (negative_ref, positive_ref)):
        raise ValueError        


def _validate_mount(mount: tuple, max: int):
    """ Validates custom mount schema for computing bipolar leads.

    Args:
        mount (tuple): Tuple of electrode indices (max 2 elements).
        max (int): Maximum valid electrode index.

    Raises:
        ValueError: If mount contains more than 2 elements.
        TypeError: If mount elements are not integers.
        IndexError: If any index exceeds the maximum.
    """
    if len(mount) > 2:
        raise ValueError(f"Too many electrical sources for lead computation. Expected 2, got {len(mount)}")
    
    for item in mount:
        if not isinstance(item, int):
            raise TypeError(f"Electrical sources for lead computation requires type `int` not {type(item)}")
        
        if item > max:
            raise IndexError(f"Index {item} of the electrical source out of bounds. Max. {max}")


def _validate_tuple(
    name: str,
    arr: Union[List, Tuple],
    size: int,
    dtype: Any = str,    
    ) -> Union[List, Tuple, None]:
    """Validates that an array/tuple has the expected size and element types.

    Args:
        name (str): Parameter name for error messages.
        arr (Union[list, tuple]): The array to validate.
        size (int): Expected length of the array.
        dtype (Any, optional): Expected type of elements. Defaults to str.

    Raises:
        ValueError: If array length doesn't match expected size.
        TypeError: If any element doesn't match expected type.

    Returns:
        Union[list, tuple, None]: The validated array, or None if input was None.
    """
    if arr is None:
        return arr

    messsage = f"Parameter `{name}` expected to have length of {size} and type {dtype}"
    if len(arr) != size:
        raise ValueError(messsage)

    if not all(isinstance(item, dtype) for item in arr):
        raise TypeError(messsage)
    
    return arr
    

def _validate_path(
        f_path: Union[str, bytes, PathLike],
        name: str = "file or directory",
    ) -> str:

    """ Checks if the path exists and the user has read/write access.

    Args:
        path: The path to validate (string).

    Raises:
        ValueError: If the path does not exist, is not readable, or not writable.
    """
    # Ensure path is absolute and normalized
    f_path = os.path.abspath(os.path.realpath(f_path))
    path_str = str(f_path)
    message = f"Path to {name} does not exist or user does not have read/write permisson: {path_str}"
    
    if not os.path.exists(f_path):
        raise ValueError(message)

    # Check if it's a file
    if os.path.isfile(f_path):
        # Open and close for read access if it's a file
        try:
            with open(f_path, "rb"):
                pass
        except OSError:
            raise ValueError(message)
    else:
        # Check if it's a directory and user has access (can list contents)
        try:
            os.listdir(f_path)
        except PermissionError:
            raise ValueError(message)
        
    return path_str