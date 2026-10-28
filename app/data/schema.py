"""The kline schema, defined once, and the normalisation of Vision CSV and REST rows to it."""

from __future__ import annotations

import csv
import io
import math
from collections.abc import Sequence

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
    "trades": pl.Int64(),
    "taker_buy_base_volume": pl.Float64(),
    "taker_buy_quote_volume": pl.Float64(),
}
COLUMNS = tuple(SCHEMA)
TIME_COLUMNS = ("open_time", "close_time")
INT_COLUMNS = (*TIME_COLUMNS, "trades")
CSV_FIELDS = len(COLUMNS) + 1  # Binance's trailing "ignore" field, dropped
MICROSECOND_THRESHOLD = 10**14


class MalformedDataError(ValueError):
    """A Vision file or REST body whose rows do not fit the kline layout."""


def empty_frame() -> pl.DataFrame:
    return pl.DataFrame(schema=SCHEMA)


def frame_from_csv(data: bytes) -> pl.DataFrame:
    """Parse a Vision daily kline CSV (optional header row, 12 fields per row)."""
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError:
        raise MalformedDataError("the file is not ASCII text") from None
    rows = [row for row in csv.reader(io.StringIO(text)) if row]
    if rows and not _is_number(rows[0][0]):
        rows = rows[1:]
    for row in rows:
        if len(row) != CSV_FIELDS:
            raise MalformedDataError(f"a row has {len(row)} fields, expected {CSV_FIELDS}")
    return _frame_from_fields([row[: len(COLUMNS)] for row in rows])


def frame_from_rest(rows: object) -> pl.DataFrame:
    """Parse a REST klines body: a list of lists of at least 11 items."""
    if not isinstance(rows, list):
        raise MalformedDataError("the body is not a list")
    fields = []
    for row in rows:
        if not isinstance(row, list) or len(row) < len(COLUMNS):
            raise MalformedDataError("a row is not a list of at least 11 items")
        for index, value in enumerate(row[: len(COLUMNS)]):
            if COLUMNS[index] in INT_COLUMNS:
                if isinstance(value, bool) or not isinstance(value, int):
                    raise MalformedDataError(f"{COLUMNS[index]} is not an integer")
            elif not isinstance(value, str):
                raise MalformedDataError(f"{COLUMNS[index]} is not a numeric string")
        fields.append([str(value) for value in row[: len(COLUMNS)]])
    return _frame_from_fields(fields)


def _is_number(text: str) -> bool:
    try:
        float(text)
    except ValueError:
        return False
    return True


def _frame_from_fields(rows: Sequence[Sequence[str]]) -> pl.DataFrame:
    columns: dict[str, list[int] | list[float]] = {}
    try:
        for index, name in enumerate(COLUMNS):
            if name in INT_COLUMNS:
                columns[name] = [int(row[index]) for row in rows]
            else:
                columns[name] = [_finite(row[index]) for row in rows]
    except ValueError as exc:
        raise MalformedDataError(f"a value does not parse: {exc}") from None
    for name in TIME_COLUMNS:
        columns[name] = _to_milliseconds(columns[name])
    raw_schema = {name: pl.Int64() if name in INT_COLUMNS else pl.Float64() for name in COLUMNS}
    frame = pl.DataFrame(columns, schema=raw_schema)
    return frame.with_columns(
        pl.col(name).cast(pl.Datetime("ms")).dt.replace_time_zone("UTC") for name in TIME_COLUMNS
    )


def _finite(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise ValueError(f"{text!r} is not a finite number")
    return value


def _to_milliseconds(times: list[int]) -> list[int]:
    """Detect the unit of one file's times (microseconds from 10^14) and floor them to ms."""
    if not times:
        return times
    in_microseconds = times[0] >= MICROSECOND_THRESHOLD
    if any((time >= MICROSECOND_THRESHOLD) != in_microseconds for time in times):
        raise MalformedDataError("the file mixes millisecond and microsecond times")
    if in_microseconds:
        return [time // 1000 for time in times]
    return times
