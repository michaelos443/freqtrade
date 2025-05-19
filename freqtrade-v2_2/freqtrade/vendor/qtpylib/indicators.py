# QTPyLib: Quantitative Trading Python Library
# https://github.com/ranaroussi/qtpylib
#
# Copyright 2016-2018 Ran Aroussi
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import warnings
from datetime import datetime, timedelta
from typing import Optional, Callable, Union


import numpy as np
import pandas as pd
from pandas.core.base import PandasObject


# =============================================
warnings.simplefilter(action="ignore", category=RuntimeWarning)

# =============================================


def _validate_numeric(func: Callable) -> Callable:
    """Decorator to validate numeric inputs for numpy/pandas functions"""
    def wrapper(data, window, *args, **kwargs):
        if not isinstance(data, (np.ndarray, pd.Series)):
            raise TypeError("Input data must be numpy array or pandas Series")
        if not isinstance(window, int) or window <= 0:
            raise ValueError("Window must be a positive integer")
        if len(data) < window:
            raise ValueError("Series length must be greater than or equal to the window size.")
        return func(data, window, *args, **kwargs)
    return wrapper


@_validate_numeric
def numpy_rolling_window(data: np.ndarray, window: int) -> np.ndarray:
    """
    Generates a rolling window for a numpy array.
    Source: https://stackoverflow.com/a/6811241

    Parameters:
    -----------
    data : np.ndarray
        The input data array.
    window : int
        The size of the rolling window.

    Returns:
    --------
    np.ndarray
        The rolling window array.

    Example
    -------
    >>> data = np.array([1, 2, 3, 4, 5])
    >>> window = 3
    >>> numpy_rolling_window(data, window)
    array([[1, 2, 3],
           [2, 3, 4],
           [3, 4, 5]])
    """
    if window <= 0:
        raise ValueError("Window must be greater than 0")

    if data.ndim != 1:
        raise ValueError("Input data must be a 1-dimensional array")

    shape = data.shape[:-1] + (data.shape[-1] - window + 1, window)
    strides = data.strides + (data.strides[-1],)
    # Check memory safety
    if (shape[0] * shape[1] * data.itemsize) > (data.nbytes * 10):
        raise MemoryError("Rolling window would create excessively large array")
    return np.lib.stride_tricks.as_strided(data, shape=shape, strides=strides)


def numpy_rolling_series(func: Callable) -> Callable:
    def func_wrapper(data: Union[pd.Series, np.ndarray],
                     window: int,
                     as_source : bool = False):
        # Validate the input.
        if not isinstance(data, (np.ndarray, pd.Series)):
            raise TypeError("Input data must be numpy array or pandas Series")
        series = data.values if isinstance(data, pd.Series) else data

        if len(series) < window:
            raise ValueError("Series length must be greater than or equal to the window size.")

        # Initialize the new series with NaN values
        new_series = np.full_like(series, np.nan, dtype=np.float64)

        try:
            calculated = func(series, window)
        except Exception as e:
            raise RuntimeError(f"Rolling calculation failed: {str(e)}") from e

        new_series[-len(calculated):] = calculated

        if as_source and isinstance(data, pd.Series):
            return pd.Series(index=data.index, data=new_series)

        return new_series

    return func_wrapper


@numpy_rolling_series
def numpy_rolling_mean(data, window, as_source=False):
    return np.mean(numpy_rolling_window(data, window), axis=-1)


@numpy_rolling_series
def numpy_rolling_std(data, window, as_source=False):
    """
    Calculates the rolling standard deviation of a numpy array.
    """
    return np.std(numpy_rolling_window(data, window), axis=-1, ddof=1)


# ---------------------------------------------


def convert_time(input_time: str) -> float:
    """Convert time string 'HH:MM' to decimal representation of hours."""
    try:
        hours, minutes = map(int, input_time.split(":"))
        return hours + minutes / 60
    except ValueError:
        raise ValueError(f"Invalid time format: {time_str}. Expected 'HH:MM' format.")


def session(df: pd.DataFrame, start: str = "17:00", end: str = "16:00") -> pd.DataFrame:
    """
    Filters the input DataFrame to remove data from the previous Globex session,
    returning only data within the specified session time window.
    The function assumes that the DataFrame has a DatetimeIndex and that the time
    is in the same timezone as the input time strings.

    Parameters:
    df (pd.DataFrame): The input DataFrame with a DatetimeIndex.
    start (str): The start time of the session in 'HH:MM' format.
    end (str): The end time of the session in 'HH:MM' format.

    Returns:
    pd.DataFrame: A filtered DataFrame containing only data within the specified session
    time window.
    """
    # Validate the input dataframe
    if not isinstance(df, pd.DataFrame):
        raise TypeError("session() requires a DataFrame as input")
    if df.empty:
        return df
    # Validate time format
    def validate_time(time_str: str):
        try:
            return datetime.strptime(time_str, "%H:%M").strftime("%H:%M")
        except ValueError:
            raise ValueError("Invalid time format. Use 'HH:MM' format.")
    start = validate_time(start)
    end = validate_time(end)

    start_decimal = convert_time(start)
    end_decimal = convert_time(end)
    current_decimal = convert_time(df[-1:].index[0].strftime("%H:%M"))

    # same-dat session?
    is_same_day = start_decimal < end_decimal
    previous_day = (
        datetime.strptime(current_day, "%Y-%m-%d") - timedelta(days=1)
    ).strftime("%Y-%m-%d")

    # Determine the session start based on whether we are past the session start time
    if current_decimal >= start_decimal:
        session_start = f"{current_day} {start}"
    else:
        session_start = f"{previous_day} {start}"
    # Filter the dataframe based on the session start time
    df = df[df.index >= session_start]
    if not is_same_day:
        # Filter the dataframe based on the session end time
        df = df[df.index < f"{current_day} {end}"]
    # Return a copy of the filtered dataframe
    return df.copy()


# ---------------------------------------------


def heikinashi(bars: pd.DataFrame):
    required_columns = ["open", "high", "low", "close"]
    if not all(x in bars.columns for x in required_columns):
        raise ValueError(
            "Heikin-Ashi requires a DataFrame with open, high, low, close columns"
        )
    if bars.empty:
        return bars

    # Create a copy to avoid modifying the original DataFrame
    bars = bars.copy()
    # Calculate HA close (average of open, high, low, close)
    bars["ha_close"] = (bars["open"] + bars["high"] + bars["low"] + bars["close"]) / 4

    # Calculate HA open value which is the average of the previous HA open
    # and HA close values (shifted by 1).
    bars.at[0, "ha_open"] = (bars.at[0, "open"] + bars.at[0, "close"]) / 2
    for i in range(1, len(bars)):
        bars.at[i, "ha_open"] = (bars.at[i - 1, "ha_open"] + bars.at[i - 1, "ha_close"]) / 2

    bars["ha_high"] = bars.loc[:, ["high", "ha_open", "ha_close"]].max(axis=1)
    bars["ha_low"] = bars.loc[:, ["low", "ha_open", "ha_close"]].min(axis=1)

    return pd.DataFrame({
            "open": bars["ha_open"],
            "high": bars["ha_high"],
            "low": bars["ha_low"],
            "close": bars["ha_close"],
        }, index=bars.index)


# ---------------------------------------------


def tdi(
    series, rsi_lookback=13, rsi_smooth_len=2, rsi_signal_len=7,
    bb_lookback=34, bb_std: float = 1.6185
):
    """
    Calculate the Trader's Dynamic Index (TDI) for a given time series.
    """
    rsi_data = rsi(series, rsi_lookback)
    # Smooth the RSI data and calculate the RSI signal using simple
    # moving average.
    rsi_smooth = sma(rsi_data, rsi_smooth_len)
    rsi_signal = sma(rsi_data, rsi_signal_len)

    bb_series = bollinger_bands(rsi_data, bb_lookback, bb_std)

    return pd.DataFrame(
        index=series.index,
        data={
            "rsi": rsi_data,
            "rsi_signal": rsi_signal,
            "rsi_smooth": rsi_smooth,
            "rsi_bb_upper": bb_series["upper"],
            "rsi_bb_lower": bb_series["lower"],
            "rsi_bb_mid": bb_series["mid"],
        },
    )


# ---------------------------------------------


def awesome_oscillator(df, weighted=False, fast=5, slow=34):
    # Calculate the midprice for each bar
    midprice = (df["high"] + df["low"]) / 2

    if weighted:
        ao = (midprice.ewm(fast).mean() - midprice.ewm(slow).mean()).values
    else:
        ao = numpy_rolling_mean(midprice, fast) - numpy_rolling_mean(midprice, slow)

    return pd.Series(index=df.index, data=ao)


# ---------------------------------------------


def nans(length=1):
    mtx = np.empty(length)
    mtx[:] = np.nan
    return mtx


# ---------------------------------------------


def typical_price(bars):
    res = (bars["high"] + bars["low"] + bars["close"]) / 3.0
    return pd.Series(res, index=bars.index)


# ---------------------------------------------


def mid_price(bars):
    res = (bars["high"] + bars["low"]) / 2.0
    return pd.Series(index=bars.index, data=res)


# ---------------------------------------------


def ibs(bars):
    """Internal bar strength"""
    res = np.round((bars["close"] - bars["low"]) / (bars["high"] - bars["low"]), 2)
    return pd.Series(index=bars.index, data=res)


# ---------------------------------------------


def true_range(bars):
    return pd.DataFrame(
        {
            "hl": bars["high"] - bars["low"],
            "hc": abs(bars["high"] - bars["close"].shift(1)),
            "lc": abs(bars["low"] - bars["close"].shift(1)),
        }
    ).max(axis=1)


# ---------------------------------------------


def atr(bars, window=14, exp=False):
    tr = true_range(bars)

    if exp:
        res = rolling_weighted_mean(tr, window)
    else:
        res = rolling_mean(tr, window)

    return pd.Series(res)


# ---------------------------------------------


def crossed(
        series1: Union[pd.Series, np.ndarray],
        series2: Union[pd.Series, float, int, np.ndarray, np.integer, np.floating],
        direction: Optional[str] = None) -> pd.Series:
    """
    Detects whether the two time series (or arrays) cross each other in a specified
    direction ("above" or "below").
    """
    if isinstance(series1, np.ndarray):
        # Convert numpy array to pandas Series
        series1 = pd.Series(series1)

    if isinstance(series2, float | int | np.ndarray | np.integer | np.floating):
        series2 = pd.Series(index=series1.index, data=series2)

    # Validate that series1 and series2 have the same length
    if len(series1) != len(series2):
        raise ValueError("series1 and series2 must have the same length")

    # Initialize the above and below series with False values
    above = pd.Series(index=series1.index, data=False)
    below = pd.Series(index=series1.index, data=False)

    if direction is None or direction == "above":
        above = pd.Series((series1 > series2) & (series1.shift(1) <= series2.shift(1)))

    if direction is None or direction == "below":
        below = pd.Series((series1 < series2) & (series1.shift(1) >= series2.shift(1)))

    if direction is None:
        return above | below
    elif direction == "above":
        return above
    elif direction == "below":
        return below
    else:
        raise ValueError("Invalid direction. Must be 'above', 'below', or None.")


def crossed_above(
        series1: Union[pd.Series, np.ndarray],
        series2: Union[pd.Series, np.ndarray, float, int]) -> pd.Series:
    """
    Detects when series1 crosses above series2.

    Args:
        series1 (pd.Series or np.ndarray): The first time series.
        series2 (pd.Series or np.ndarray or float or int): The second time series or
            a constant value.

    Returns:
        pd.Series: A boolean series indicating when series1 crosses above series2.
    """
    return crossed(series1, series2, "above")


def crossed_below(series1, series2):
    return crossed(series1, series2, "below")


# ---------------------------------------------


def rolling_std(series, window=200, min_periods=None):
    # Validate input
    if not isinstance(series, (pd.Series, np.ndarray)):
        raise TypeError("Input must be a pandas Series or numpy array")
    if not isinstance(window, int) or window <= 0:
        raise ValueError("Window must be a positive integer")
    min_periods = window if min_periods is None else min_periods
    if min_periods == window and len(series) > window:
        return numpy_rolling_std(series, window, True)
    else:
        try:
            return series.rolling(window=window, min_periods=min_periods).std()
        except Exception:  # noqa: F841
            return pd.Series(series).rolling(window=window, min_periods=min_periods).std()


# ---------------------------------------------


def rolling_mean(series, window=200, min_periods=None):
    if not isinstance(series, (pd.Series, np.ndarray)):
        raise TypeError("Input must be a pandas Series or numpy array")
    min_periods = window if min_periods is None else min_periods
    if min_periods == window and len(series) > window:
        return numpy_rolling_mean(series, window, True)
    else:
        try:
            return series.rolling(window=window, min_periods=min_periods).mean()
        except Exception:  # noqa: F841
            return pd.Series(series).rolling(window=window, min_periods=min_periods).mean()


# ---------------------------------------------


def rolling_min(series, window=14, min_periods=None):
    if not isinstance(series, (pd.Series, np.ndarray)):
        raise TypeError("Input must be a pandas Series or numpy array")
    min_periods = window if min_periods is None else min_periods
    return series.rolling(window=window, min_periods=min_periods).min()


# ---------------------------------------------


def rolling_max(series, window=14, min_periods=None):
    min_periods = window if min_periods is None else min_periods
    try:
        return series.rolling(window=window, min_periods=min_periods).max()
    except Exception as e:  # noqa: F841
        return pd.Series(series).rolling(window=window, min_periods=min_periods).max()


# ---------------------------------------------


def rolling_weighted_mean(series, window=200, min_periods=None):
    min_periods = window if min_periods is None else min_periods
    try:
        return series.ewm(span=window, min_periods=min_periods).mean()
    except Exception as e:  # noqa: F841
        return pd.ewma(series, span=window, min_periods=min_periods)


# ---------------------------------------------


def hull_moving_average(
        series: Union[pd.Series, np.ndarray],
        window: int = 200,
        min_periods: Optional[int] = None):
    """
    Calculate the Hull Moving Average (HMA) of a given series using the specified window.

    The HMA is a weighted moving average that is designed to reduce lag in the moving
    average.

    Parameters:
    -----------
    series : pd.Series or np.ndarray
        The time series data.
    window : int, optional, default 200
        The number of periods over which to compute the moving average.
    min_periods : int, optional, default None
        The minimum number of observations in the window required to have a value
        (otherwise, the result is NaN).

    Returns:
    --------
    pd.Series
        The calculated Hull Moving Average of the input series.
    """
    if not isinstance(series, (pd.Series, np.ndarray)):
        raise TypeError("Input must be a pandas Series or numpy array.")
    min_periods = window if min_periods is None else min_periods
    half_window = rolling_weighted_mean(series, window / 2, min_periods)
    full_window = rolling_weighted_mean(series, window, min_periods)
    diff = 2 * half_window - full_window
    return rolling_weighted_mean(diff, int(np.sqrt(window)), min_periods)


# ---------------------------------------------


def sma(series, window=200, min_periods=None):
    return rolling_mean(series, window=window, min_periods=min_periods)


# ---------------------------------------------


def wma(series, window=200, min_periods=None):
    return rolling_weighted_mean(series, window=window, min_periods=min_periods)


# ---------------------------------------------


def hma(series, window=200, min_periods=None):
    return hull_moving_average(series, window=window, min_periods=min_periods)


# ---------------------------------------------


def vwap(bars):
    """
    calculate vwap of entire time series
    (input can be pandas series or numpy array)
    bars are usually mid [ (h+l)/2 ] or typical [ (h+l+c)/3 ]
    """
    raise ValueError(
        "using `qtpylib.vwap` facilitates lookahead bias. Please use "
        "`qtpylib.rolling_vwap` instead, which calculates vwap in a rolling manner."
    )
    # typical = ((bars['high'] + bars['low'] + bars['close']) / 3).values
    # volume = bars['volume'].values

    # return pd.Series(index=bars.index,
    #                  data=np.cumsum(volume * typical) / np.cumsum(volume))


# ---------------------------------------------


def rolling_vwap(bars, window=200, min_periods=None):
    """
    calculate vwap using moving window
    (input can be pandas series or numpy array)
    bars are usually mid [ (h+l)/2 ] or typical [ (h+l+c)/3 ]
    """
    min_periods = window if min_periods is None else min_periods

    typical = (bars["high"] + bars["low"] + bars["close"]) / 3
    volume = bars["volume"]

    weighted = (volume * typical).rolling(window=window, min_periods=min_periods)
    left = weighted.sum()
    right = volume.rolling(window=window, min_periods=min_periods).sum()

    return (
        pd.Series(index=bars.index, data=(left / right))
        .replace([np.inf, -np.inf], float("NaN"))
        .ffill()
    )


# ---------------------------------------------


def rsi(series, window=14):
    """
    compute the n period relative strength indicator
    """

    # 100-(100/relative_strength)
    deltas = np.diff(series)
    seed = deltas[: window + 1]

    # default values
    ups = seed[seed > 0].sum() / window
    downs = -seed[seed < 0].sum() / window
    rsival = np.zeros_like(series)
    rsival[:window] = 100.0 - 100.0 / (1.0 + ups / downs)

    # period values
    for i in range(window, len(series)):
        delta = deltas[i - 1]
        if delta > 0:
            upval = delta
            downval = 0
        else:
            upval = 0
            downval = -delta

        ups = (ups * (window - 1) + upval) / window
        downs = (downs * (window - 1.0) + downval) / window
        rsival[i] = 100.0 - 100.0 / (1.0 + ups / downs)

    # return rsival
    return pd.Series(index=series.index, data=rsival)


# ---------------------------------------------


def macd(series, fast: int = 3, slow: int = 10, smooth: int = 16) -> pd.DataFrame:
    """
    Compute the Moving Average Convergence/Divergence (MACD) using fast and slow 
    exponential moving averages (EMAs), along with the MACD signal line and histogram.
    
    The MACD is calculated as the difference between the fast and slow EMAs.
    The signal line is the smoothed version of the MACD line, and the histogram
    represents the difference between the MACD line and the signal line.

    Parameters:
    -----------
    series : pd.Series
        The input time series data. The index must be datetime-based.
    fast : int
        The window size for the fast EMA (default is 3).
    slow : int
        The window size for the slow EMA (default is 10).
    smooth : int
        The window size for the signal line (default is 16).

    Returns
    -------
    pd.DataFrame
        A DataFrame containing the MACD line, signal line, and histogram with the
        same index as the input series.
    """
    if not all(x > 0 for x in [fast, slow, smooth]):
        raise ValueError("All MACD parameters must be greater than 0")
    if fast >= slow:
        raise ValueError("MACD fast period must be less than the slow period")

    ema_fast = rolling_weighted_mean(series, window=fast)
    ema_slow = rolling_weighted_mean(series, window=slow)

    # MACD is the difference between the fast and slow moving averages
    macd_line = ema_fast - ema_slow
    # The signal line is an EMA of the MACD line
    signal = rolling_weighted_mean(macd_line, window=smooth)
    histogram = macd_line - signal
    # return macd_line, signal, histogram
    return pd.DataFrame(
        index=series.index,
        data={"macd": macd_line.values, "signal": signal.values, "histogram": histogram.values},
    )


# ---------------------------------------------


def bollinger_bands(series: pd.Series, window: int = 20, stds: int = 2) -> pd.DataFrame:
    """
    Calculate Bollinger Bands for the given time series.

    The middle band is a simple moving average, and the upper/lower bands are
    calculated as the moving average plus/minus the standard deviation multiplied
    by a factor.

    Parameters:
    -----------
    series : pd.Series
        The time series data.
    window : int, optional, default 20
        The number of periods over which to compute the moving average and standard deviation.
    stds : int, optional, default 2
        The number of standard deviations to use for the upper/lower bands.

    Returns:
    --------
    pd.DataFrame
        A DataFrame containing the 'upper', 'mid', and 'lower' Bollinger Bands.
    """
    ma = rolling_mean(series, window=window, min_periods=1)
    std = rolling_std(series, window=window, min_periods=1)
    upper = ma + std * stds
    lower = ma - std * stds

    return pd.DataFrame(
        index=series.index,
        data={"upper": upper, "mid": ma, "lower": lower}
    )


# ---------------------------------------------


def weighted_bollinger_bands(series, window=20, stds=2):
    ema = rolling_weighted_mean(series, window=window)
    std = rolling_std(series, window=window)
    upper = ema + std * stds
    lower = ema - std * stds

    return pd.DataFrame(
        index=series.index, data={"upper": upper.values, "mid": ema.values, "lower": lower.values}
    )


# ---------------------------------------------


def returns(series):
    try:
        res = (series / series.shift(1) - 1).replace([np.inf, -np.inf], float("NaN"))
    except Exception as e:  # noqa: F841
        res = nans(len(series))

    return pd.Series(index=series.index, data=res)


# ---------------------------------------------


def log_returns(series: pd.Series):
    """
    Calculate the logarithmic returns of the given time series.

    The log return is calculated as the natural logarithm of the ratio of
    consecutive values in the series.

    Parameters:
    -----------
    series : pd.Series
        The time series data.

    Returns:
    --------
    pd.Series
        The calculated logarithmic returns of the input series.
    """
    try:
        res = np.log(series / series.shift(1)).replace([np.inf, -np.inf], float("NaN"))
    except Exception as e:  # noqa: F841
        # Create a result of NaN values if an exception occurs.
        res = nans(len(series))

    return pd.Series(index=series.index, data=res)


# ---------------------------------------------


def implied_volatility(series, window=252):
    """
    Compute the implied volatility using the logarithmic returns of the series.

    The implied volatility is calculated as the standard deviation of the
    logarithmic returns multiplied by the square root of the window size.

    Parameters:
    -----------
    series : pd.Series
        The time series data.
    window : int, optional, default 252
        The number of periods over which to compute the standard deviation.

    Returns:
    --------
    pd.Series
        The calculated implied volatility of the input series.
    """
    try:
        logret = np.log(series / series.shift(1))
        # replace inf with NaN
        logret.replace([np.inf, -np.inf], float("NaN"), inplace=True)
        res = numpy_rolling_std(logret, window) * np.sqrt(window)
    except Exception as e:  # noqa: F841
        res = nans(len(series))

    return pd.Series(index=series.index, data=res)


# ---------------------------------------------


def keltner_channel(bars, window=14, atrs=2):
    # Calculate rolling mean of typical price
    typical_mean = rolling_mean(typical_price(bars), window)
    atrval = atr(bars, window) * atrs

    upper = typical_mean + atrval
    lower = typical_mean - atrval

    return pd.DataFrame(
        index=bars.index,
        data={"upper": upper.values, "mid": typical_mean.values, "lower": lower.values},
    )


# ---------------------------------------------


def roc(series, window=14):
    """
    compute rate of change
    """
    if not isinstance(series, pd.Series):
        series = pd.Series(series)
    if len(series) < window:
        return nans(len(series))
    res = (series - series.shift(window)) / series.shift(window)
    return pd.Series(index=series.index, data=res)


# ---------------------------------------------


def cci(series, window=14):
    """
    compute commodity channel index
    """
    price = typical_price(series)
    typical_mean = rolling_mean(price, window)
    res = (price - typical_mean) / (0.015 * numpy_rolling_std(typical_mean, window))
    return pd.Series(index=series.index, data=res)


# ---------------------------------------------


def stoch(df, window=14, d=3, k=3, fast=False):
    """
    compute the n period relative strength indicator
    http://excelta.blogspot.co.il/2013/09/stochastic-oscillator-technical.html
    """

    result_df = pd.DataFrame(index=df.index)

    result_df["rolling_max"] = df["high"].rolling(window).max()
    result_df["rolling_min"] = df["low"].rolling(window).min()

    result_df["fast_k"] = (
        100 * (df["close"] - result_df["rolling_min"])
        / (result_df["rolling_max"] - result_df["rolling_min"])
    )
    result_df["fast_d"] = result_df["fast_k"].rolling(d).mean()

    if fast:
        return result_df.loc[:, ["fast_k", "fast_d"]]

    result_df["slow_k"] = result_df["fast_k"].rolling(k).mean()
    result_df["slow_d"] = result_df["slow_k"].rolling(d).mean()

    return result_df.loc[:, ["slow_k", "slow_d"]]


# ---------------------------------------------


def zlma(series, window=20, min_periods=None, kind="ema"):
    """
    John Ehlers' Zero lag (exponential) moving average
    https://en.wikipedia.org/wiki/Zero_lag_exponential_moving_average
    """
    min_periods = window if min_periods is None else min_periods

    lag = (window - 1) // 2
    series = 2 * series - series.shift(lag)
    if kind in ["ewm", "ema"]:
        return wma(series, lag, min_periods)
    elif kind == "hma":
        return hma(series, lag, min_periods)
    return sma(series, lag, min_periods)


def zlema(series, window, min_periods=None, kind="ema"):
    return zlma(series, window, min_periods, kind)


def zlsma(
        series: pd.Series, window: int, min_periods: int = None,
        kind: Literal["sma"] = "sma") -> pd.Series:
    """
    Calculate Zero-Lag Simple Moving Average (ZLSMA) of a given series.

    Calls the `zlma` function to compute the ZLSMA, which is used to reduce
    the lag of a standard moving average.

    Parameters:
    -----------
    series : pd.Series
        The time series data.
    window : int
        The number of periods over which to compute the moving average.
    min_periods : int, optional, default None
        The minimum number of observations in the window required to have a value
        (otherwise, the result is NaN).
    kind : Literal["sma"]
        The type of moving average to compute.

    Returns:
    --------
    pd.Series
        The calculated Zero-Lag Moving Average of the input series.
    """
    return zlma(series, window, min_periods, kind)


def zlhma(series, window, min_periods=None, kind="hma"):
    return zlma(series, window, min_periods, kind)


# ---------------------------------------------


def zscore(bars, window=20, stds=1, col="close"):
    """get zscore of price"""
    std = numpy_rolling_std(bars[col], window)
    mean = numpy_rolling_mean(bars[col], window)
    return (bars[col] - mean) / (std * stds)


# ---------------------------------------------


def pvt(bars):
    """Price Volume Trend"""
    trend = ((bars["close"] - bars["close"].shift(1)) / bars["close"].shift(1)) * bars["volume"]
    return trend.cumsum()


def chopiness(bars, window=14):
    atrsum = true_range(bars).rolling(window).sum()
    highs = bars["high"].rolling(window).max()
    lows = bars["low"].rolling(window).min()
    return 100 * np.log10(atrsum / (highs - lows)) / np.log10(window)


# =============================================


PandasObject.session = session
PandasObject.atr = atr
PandasObject.bollinger_bands = bollinger_bands
PandasObject.cci = cci
PandasObject.crossed = crossed
PandasObject.crossed_above = crossed_above
PandasObject.crossed_below = crossed_below
PandasObject.heikinashi = heikinashi
PandasObject.hull_moving_average = hull_moving_average
PandasObject.ibs = ibs
PandasObject.implied_volatility = implied_volatility
PandasObject.keltner_channel = keltner_channel
PandasObject.log_returns = log_returns
PandasObject.macd = macd
PandasObject.returns = returns
PandasObject.roc = roc
PandasObject.rolling_max = rolling_max
PandasObject.rolling_min = rolling_min
PandasObject.rolling_mean = rolling_mean
PandasObject.rolling_std = rolling_std
PandasObject.rsi = rsi
PandasObject.stoch = stoch
PandasObject.zscore = zscore
PandasObject.pvt = pvt
PandasObject.chopiness = chopiness
PandasObject.tdi = tdi
PandasObject.true_range = true_range
PandasObject.mid_price = mid_price
PandasObject.typical_price = typical_price
PandasObject.vwap = vwap
PandasObject.rolling_vwap = rolling_vwap
PandasObject.weighted_bollinger_bands = weighted_bollinger_bands
PandasObject.rolling_weighted_mean = rolling_weighted_mean

PandasObject.sma = sma
PandasObject.wma = wma
PandasObject.ema = wma
PandasObject.hma = hma

PandasObject.zlsma = zlsma
PandasObject.zlwma = zlema
PandasObject.zlema = zlema
PandasObject.zlhma = zlhma
PandasObject.zlma = zlma
