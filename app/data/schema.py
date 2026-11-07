"""The kline schema, defined once, and the normalisation of KuCoin spot and futures rows to it."""

from __future__ import annotations

import math

import polars as pl

TIME_DTYPE = pl.Datetime("ms", "UTC")
SCHEMA: dict[str, pl.DataType] = {
    "open_time": TIME_DTYPE,
    "open": pl.Float64(),
    "high": pl.Float64(),
    "low": pl.Float64(),
    "close": pl.Float64(),
    "volume": pl.Float64(),
    "close_time": TIME_DTYPE,
    "quote_volume": pl.Float64(),
}
COLUMNS = tuple(SCHEMA)
TIME_COLUMNS = ("open_time", "close_time")
ROW_ITEMS = 7

# Where each value sits in a row (after the time at index 0): spot puts close before high.
_SPOT_ORDER = {"open": 1, "close": 2, "high": 3, "low": 4, "volume": 5, "quote_volume": 6}
_FUTURES_ORDER = {"open": 1, "high": 2, "low": 3, "close": 4, "volume": 5, "quote_volume": 6}


class MalformedDataError(ValueError):
    """A KuCoin answer whose rows do not fit the kline layout."""


def empty_frame() -> pl.DataFrame:
    return pl.DataFrame(schema=SCHEMA)


def frame_from_spot_rows(rows: object, interval_ms: int) -> pl.DataFrame:
    """Parse spot rows: 7 strings each, the time in seconds, prices open, close, high, low."""
    parsed = []
    for row in _rows(rows):
        if not all(isinstance(value, str) for value in row):
            raise MalformedDataError("a spot row holds a value that is not a string")
        try:
            open_ms = _open_ms(int(row[0]) * 1000, interval_ms)
            values = {name: _finite(float(row[index])) for name, index in _SPOT_ORDER.items()}
        except ValueError as exc:
            raise MalformedDataError(f"a value does not parse: {exc}") from None
        parsed.append((open_ms, values))
    return _frame(parsed, interval_ms)


def frame_from_futures_rows(rows: object, interval_ms: int) -> pl.DataFrame:
    """Parse futures rows: 7 JSON numbers each, the time in milliseconds, prices in OHLC order."""
    parsed = []
    for row in _rows(rows):
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in row):
            raise MalformedDataError("a futures row holds a value that is not a number")
        time = row[0]
        if isinstance(time, float) and not time.is_integer():
            raise MalformedDataError(f"the open time {time!r} is not a whole number")
        try:
            open_ms = _open_ms(int(time), interval_ms)
            values = {name: _finite(float(row[index])) for name, index in _FUTURES_ORDER.items()}
        except (ValueError, OverflowError) as exc:
            raise MalformedDataError(f"a value does not parse: {exc}") from None
        parsed.append((open_ms, values))
    return _frame(parsed, interval_ms)


def _rows(rows: object) -> list[list[object]]:
    if not isinstance(rows, list):
        raise MalformedDataError("the data is not a list")
    for row in rows:
        if not isinstance(row, list) or len(row) != ROW_ITEMS:
            raise MalformedDataError(f"a row is not a list of exactly {ROW_ITEMS} items")
    return rows


def _frame(parsed: list[tuple[int, dict[str, float]]], interval_ms: int) -> pl.DataFrame:
    columns: dict[str, list[int] | list[float]] = {
        "open_time": [open_ms for open_ms, _ in parsed],
        "close_time": [open_ms + interval_ms - 1 for open_ms, _ in parsed],
    }
    for name in COLUMNS:
        if name not in TIME_COLUMNS:
            columns[name] = [values[name] for _, values in parsed]
    raw_schema = {name: pl.Int64() if name in TIME_COLUMNS else pl.Float64() for name in COLUMNS}
    frame = pl.DataFrame(columns, schema=raw_schema)
    return frame.with_columns(
        pl.col(name).cast(pl.Datetime("ms")).dt.replace_time_zone("UTC") for name in TIME_COLUMNS
    )


def _open_ms(value: int, interval_ms: int) -> int:
    """An open time whose close time (open + interval - 1) still fits a 64-bit integer."""
    if not -(2**63) <= value < 2**63 - interval_ms:
        raise ValueError(f"{value!r} does not fit a 64-bit time")
    return value


def _finite(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError(f"{value!r} is not a finite number")
    return value
