"""
Utility functions for Freqtrade and scripts.

This file should not import any file from the freqtrade directory
to avoid circular import issues!
"""

import gzip
import logging
from collections.abc import Iterator, Mapping
from io import StringIO
from pathlib import Path
from typing import Any, TextIO, Dict, Optional, Union
from urllib.parse import urlparse

import pandas as pd
import rapidjson

from freqtrade.enums import SignalTagType, SignalType


logger = logging.getLogger(__name__)

# Type aliases for commonly used data structures.
DictMap = dict[str, Any] | Mapping[str, Any]
JSONSerializable = Union[bool, int, float, str, None, dict, list]


def dump_json_to_file(file_obj: TextIO, data: JSONSerializable) -> None:
    """
    Serialize data to JSON and write it to a file.
    :param file_obj: File object to write to
    :param data: JSON Data to save
    :raises: IOError, TypeError if data is not JSON serializable.
    """
    try:
        rapidjson.dump(
            data, file_obj, default=str, number_mode=rapidjson.NM_NATIVE, skipkeys=True
        )
    except TypeError as e:
        # Handle data that cannot be serialized
        raise TypeError(f"Data is not serializable to JSON: {e}")
    except IOError as e:
        # Handle file write errors
        raise IOError(f"Error while writing to the file: {e}")


def file_dump_json(
        filename: Path, data: JSONSerializable, is_zip: bool = False,
        log: bool = True) -> None:
    """
    Dump JSON data into a file
    :param filename: file to create
    :param is_zip: if file should be zip
    :param data: JSON Data to save
    :param log: Log if enabled
    :raise: ValueError: If the filename parameter is a directory.
    """
    if filename.is_dir():
        raise ValueError(f'"{filename}" is a directory - should be file!')
    if log:
        logger.info(f'dumping json to "{filename}"')

    mode = "wt" if is_zip else "w"
    opener = gzip.open if is_zip else open

    if filename.suffix != ".gz" and is_zip:
        logger.info(f"Adding '.gz' to filename: {filename}")
        filename = filename.with_suffix(".gz")
    try:
        with opener(filename, mode, encoding="utf-8") as file:
            dump_json_to_file(file, data)

        logger.debug(f'json saved to "{filename}"')
    except IOError:
        logger.exception(f"Exception occurred when writing to file: {filename}")


def json_load(datafile: TextIO) -> Optional[Any]:
    """
    Load data with rapidjson.
    Use this to have a consistent experience,
    set number_mode to "NM_NATIVE" for greatest speed

    :param datafile: file to load
    :return: the data as a JSON object, or None if loading fails
    """
    try:
        return rapidjson.load(datafile, number_mode=rapidjson.NM_NATIVE)
    except rapidjson.JSONDecodeError as e:
        logger.error(f"Failed to load JSON: {e}")
        return None
    except (IOError, ValueError) as e:
        logger.error("Data loading error: %s", e)
        return None


def file_load_json(file: Path) -> Optional[Any]:
    """
    Loads JSON data from a file, either compressed (.gz) or regular format. 

    The function first checks if the file is compressed with a .gz extension. 
    If not, it attempts to load the original file. If neither is available, it returns None.

    :param file: The file path to the JSON file, which can be either compressed or regular.

    :return: The JSON data if loading is successful, otherwise None.

    :raises: OSError, IOError, ValueError, rapidjson.JSONDecodeError if loading fails.
    """
    # Define the potential compressed file path
    gzipfile = file if file.suffix == ".gz" else file.with_suffix(file.suffix + ".gz")
    try:
        # Try gzip file first, otherwise regular json file.
        gzip_exists = gzipfile.is_file()
        regular_exists = file.is_file()
        if gzip_exists:
            # Load compressed json file
            logger.debug(f"Loading historical data from file {gzipfile}")
            with gzip.open(gzipfile, "rt", encoding="utf-8") as datafile:
                pairdata = json_load(datafile)

        elif regular_exists:
            logger.debug(f"Loading historical data from file {file}")
            with file.open() as datafile:
                pairdata = json_load(datafile)

        else:
            logger.warning(
                f"No historical data file found for {file} - please download it first."
            )
            return None

    except (OSError, IOError, ValueError, rapidjson.JSONDecodeError) as exception:  # type: ignore
        logger.error(f"Unable to read file {file} : {exception}")
        return None

    return pairdata


def is_file_in_dir(file: Path, directory: Path) -> bool:
    """
    Helper function to check if file is in directory.
    """
    return file.is_file() and file.parent.samefile(directory)


def pair_to_filename(pair: str) -> str:
    for ch in ["/", " ", ".", "@", "$", "+", ":"]:
        pair = pair.replace(ch, "_")
    return pair


def deep_merge_dicts(
        source: Dict[str, Any], destination: Dict[str, Any],
        allow_null_overrides: bool = True) -> Dict[str, Any]:
    """
    Values from Source override destination, destination is returned (and modified!!)

    :param source: dict to merge
    :param destination: dict to merge into
    :param allow_null_overrides: allow null values to override existing non-null values
    :return: destination   
    Sample:
    >>> a = { 'first' : { 'rows' : { 'pass' : 'dog', 'number' : '1' } } }
    >>> b = { 'first' : { 'rows' : { 'fail' : 'cat', 'number' : '5' } } }
    >>> merge(b, a) == { 'first' : { 'rows' : { 'pass' : 'dog', 'fail' : 'cat', 'number' : '5' } } }
    True
    """
    for key, value in source.items():
        # If the value is a dictionary, we need to merge it recursively
        if isinstance(value, dict):
            # Get the corresponding value in the destination or create one if it doesn't exist
            node = destination.setdefault(key, {})
            deep_merge_dicts(value, node, allow_null_overrides)

        # If the value is not None or null overrides are allowed, update the destination
        elif value is not None or allow_null_overrides:
            destination[key] = value

    return destination


def round_dict(d: Dict[str, float], n: int) -> Dict[str, float]:
    """
    Rounds float values in the dict to n digits after the decimal point.
    """
    return {
        k: (round(v, n) if isinstance(v, float) else v) for k, v in d.items()
        if v is not None
    }


def safe_value_fallback(obj: DictMap, key1: str, key2: str | None = None, default_value=None):
    """
    Search a value in obj, return this if it's not None.
    Then search key2 in obj - return that if it's not none - then use default_value.
    Else falls back to None.

    :param obj: object to search
    :param key1: key to search first
    :param key2: key to search second
    :param default_value: value to return if key1 and key2 do not exist
    :return: value of key1 or key2 in obj, or default_value, or None
    """
    if key1 and obj.get(key1) is not None:
        return obj[key1]
    else:
        if key2 and obj.get(key2) is not None:
            return obj[key2]
    return default_value


def safe_value_fallback2(dict1: DictMap, dict2: DictMap, key1: str, key2: str, default_value=None):
    """
    Search a value in dict1, return this if it's not None.
    Fall back to dict2 - return key2 from dict2 if it's not None.
    Else falls back to None.

    """
    if key1 in dict1 and dict1[key1] is not None:
        return dict1[key1]
    else:
        if key2 in dict2 and dict2[key2] is not None:
            return dict2[key2]
    return default_value


def plural(num: float, singular: str, plural: str | None = None) -> str:
    return singular if (num == 1 or num == -1) else plural or singular + "s"


def chunks(lst: list[Any], n: int) -> Iterator[list[Any]]:
    """
    Split lst into chunks of the size n.
    :param lst: list to split into chunks
    :param n: number of max elements per chunk
    :return: None
    """
    for chunk in range(0, len(lst), n):
        yield (lst[chunk : chunk + n])


def parse_db_uri_for_logging(uri: str):
    """
    Helper method to parse the DB URI and return the same DB URI with the password censored
    if it contains it. Otherwise, return the DB URI unchanged
    :param uri: DB URI to parse for logging
    """
    parsed_db_uri = urlparse(uri)
    if not parsed_db_uri.netloc:  # No need for censoring as no password was provided
        return uri
    pwd = parsed_db_uri.netloc.split(":")[1].split("@")[0]
    return parsed_db_uri.geturl().replace(f":{pwd}@", ":*****@")


def dataframe_to_json(dataframe: pd.DataFrame) -> str:
    """
    Serialize a DataFrame for transmission over the wire using JSON
    :param dataframe: A pandas DataFrame
    :returns: A JSON string of the pandas DataFrame
    """
    return dataframe.to_json(orient="split")


def json_to_dataframe(data: str) -> pd.DataFrame:
    """
    Deserialize JSON into a DataFrame
    :param data: A JSON string
    :returns: A pandas DataFrame from the JSON string
    """
    dataframe = pd.read_json(StringIO(data), orient="split")
    if "date" in dataframe.columns:
        dataframe["date"] = pd.to_datetime(dataframe["date"], unit="ms", utc=True)

    return dataframe


def remove_entry_exit_signals(dataframe: pd.DataFrame) -> pd.DataFrame:
    """
    Remove Entry and Exit signals from a DataFrame

    :param dataframe: The DataFrame to remove signals from
    """
    try:
        if isinstance(dataframe, pd.DataFrame):
            if not dataframe.empty:
                # Reset entry and exit signals for long and short positions
                for signal in [SignalType.ENTER_LONG, SignalType.EXIT_LONG, SignalType.ENTER_SHORT, SignalType.EXIT_SHORT]:
                    dataframe[signal.value] = 0
                # Reset signal tags to None
                for tags in [SignalTagType.ENTER_TAG, SignalTagType.EXIT_TAG]:
                    dataframe[tags.value] = None
                dataframe[SignalTagType.ENTER_TAG.value] = None
                dataframe[SignalTagType.EXIT_TAG.value] = None
            else:
                raise ValueError("Dataframe supplied is empty.")
        else:
            raise TypeError(
                f"Expected a pandas DataFrame, but got {type(dataframe).__name__}."
            )
    except KeyError as key_err:
        logger.exception(f"Error removing entry/exit signals: {key_err}")

    return dataframe


def append_candles_to_dataframe(left: pd.DataFrame, right: pd.DataFrame) -> pd.DataFrame:
    """
    Append the `right` dataframe to the `left` dataframe

    :param left: The full dataframe you want appended to
    :param right: The new dataframe containing the data you want appended
    :returns: The dataframe with the right data in it
    """
    if left.iloc[-1]["date"] != right.iloc[-1]["date"]:
        left = pd.concat([left, right], ignore_index=True)

    # Only keep the last 1500 candles in memory
    left = left.tail(1500)
    left.reset_index(drop=True, inplace=True)

    return left
