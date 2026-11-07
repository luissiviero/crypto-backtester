"""Backtest inputs: the frame, the positions and the fee, checked before any calculation."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import polars as pl

DEFAULT_FEE = 0.001
REQUIRED_COLUMNS = ("open_time", "open", "close")


class BacktestInputError(ValueError):
    """A frame, position series or fee the backtest engine refuses."""


@dataclass(frozen=True)
class Inputs:
    open_time: pl.Series
    opens: list[float]
    closes: list[float]
    positions: list[int]
    fee: float


def validate(frame: pl.DataFrame, positions: pl.Series | Sequence[int], fee: float) -> Inputs:
    checked_fee = _check_fee(fee)
    opens, closes = _check_frame(frame)
    checked_positions = _check_positions(positions, frame.height)
    return Inputs(
        open_time=frame["open_time"],
        opens=opens,
        closes=closes,
        positions=checked_positions,
        fee=checked_fee,
    )


def _check_fee(fee: float) -> float:
    if isinstance(fee, bool) or not isinstance(fee, (int, float)):
        raise BacktestInputError(
            f"fee {fee!r} is not a number: pass a proportional fee as a float, for example 0.001"
        )
    if not 0 <= fee < 1:
        raise BacktestInputError(
            f"fee {fee!r} is out of range: it must be at least 0 and below 1, for example 0.001"
        )
    return float(fee)


def _check_frame(frame: pl.DataFrame) -> tuple[list[float], list[float]]:
    if not isinstance(frame, pl.DataFrame):
        raise BacktestInputError(
            f"frame is a {type(frame).__name__}: pass a polars DataFrame such as load_klines returns"
        )
    missing = [name for name in REQUIRED_COLUMNS if name not in frame.columns]
    if missing:
        raise BacktestInputError(
            f"frame lacks the column(s) {', '.join(missing)}: it needs "
            f"{', '.join(REQUIRED_COLUMNS)}"
        )
    if frame.height == 0:
        raise BacktestInputError("frame is empty: pass at least one candle")
    _check_open_time(frame["open_time"])
    return _check_prices(frame["open"]), _check_prices(frame["close"])


def _check_open_time(open_time: pl.Series) -> None:
    nulls = open_time.is_null().arg_true()
    if nulls.len():
        raise BacktestInputError(f"open_time[{nulls[0]}] is null: every row needs an open_time")
    earlier = open_time.slice(0, open_time.len() - 1)
    later = open_time.slice(1)
    not_increasing = (later <= earlier).arg_true()
    if not_increasing.len():
        row = not_increasing[0] + 1
        raise BacktestInputError(
            f"open_time[{row}] is {open_time[row]!r}, not after open_time[{row - 1}] "
            f"{open_time[row - 1]!r}: open_time must be strictly increasing"
        )


def _check_prices(column: pl.Series) -> list[float]:
    if not column.dtype.is_numeric():
        raise BacktestInputError(f"{column.name} has dtype {column.dtype}: prices must be numbers")
    prices = column.cast(pl.Float64).to_list()
    for row, value in enumerate(prices):
        if value is None or not math.isfinite(value) or value <= 0:
            raise BacktestInputError(
                f"{column.name}[{row}] is {value!r}: every price must be a finite number above 0"
            )
    return prices


def _check_positions(positions: pl.Series | Sequence[int], height: int) -> list[int]:
    values = positions.to_list() if isinstance(positions, pl.Series) else list(positions)
    if len(values) != height:
        raise BacktestInputError(
            f"positions has {len(values)} values but the frame has {height} rows: "
            "pass one position per row"
        )
    for row, value in enumerate(values):
        if type(value) is not int or value not in (0, 1):
            raise BacktestInputError(
                f"positions[{row}] is {value!r}: each position must be the integer 0 (flat) "
                "or 1 (long); cast a Boolean or Float series with .cast(pl.Int8)"
            )
    return values
