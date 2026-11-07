"""The built-in strategy: a simple moving-average crossover of `close`, long/flat, no lookahead."""

from __future__ import annotations

import polars as pl

from app.backtest.inputs import BacktestInputError

STRATEGY_NAME = "sma-cross"


def validate_lengths(fast: int, slow: int) -> None:
    for name, length in (("fast", fast), ("slow", slow)):
        if type(length) is not int or length < 1:
            raise BacktestInputError(f"{name} {length!r} is not a whole number of at least 1")
    if fast >= slow:
        raise BacktestInputError(
            f"fast {fast} is not below slow {slow}: the fast SMA must be the shorter one"
        )


def sma_cross_positions(frame: pl.DataFrame, fast: int, slow: int) -> pl.Series:
    """One position per row: 1 when the fast SMA of `close` is above the slow SMA, else 0.

    The averages count rows, not wall time, and are undefined (position 0) until their window
    is full. A row's position reads only that row's close and earlier ones.
    """
    validate_lengths(fast, slow)
    if not isinstance(frame, pl.DataFrame):
        raise BacktestInputError(
            f"frame is a {type(frame).__name__}: pass a polars DataFrame such as load_klines returns"
        )
    if "close" not in frame.columns:
        raise BacktestInputError("frame lacks the column close: the strategy reads close")
    if not frame["close"].dtype.is_numeric():
        raise BacktestInputError(f"close has dtype {frame['close'].dtype}: prices must be numbers")
    close = frame["close"].cast(pl.Float64)
    above = close.rolling_mean(window_size=fast) > close.rolling_mean(window_size=slow)
    return above.fill_null(False).cast(pl.Int8).alias("position")
