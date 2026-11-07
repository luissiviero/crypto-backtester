"""Offline tests for the backtest engine, on frames built by hand with hand-computed results."""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import datetime, timezone

import polars as pl
import pytest

from app.backtest.inputs import BacktestInputError, validate


def _frame(
    opens: Sequence[float | None],
    closes: Sequence[float | None],
    times: Sequence[object] | None = None,
) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "open_time": list(range(len(opens))) if times is None else list(times),
            "open": pl.Series(list(opens), dtype=pl.Float64),
            "close": pl.Series(list(closes), dtype=pl.Float64),
        }
    )


def test_refuses_length_mismatch() -> None:
    frame = _frame([100, 100, 100], [100, 100, 100])
    with pytest.raises(BacktestInputError, match="positions has 2 values but the frame has 3"):
        validate(frame, [0, 1], 0.001)


@pytest.mark.parametrize("bad", [None, math.nan, 2, -1, 0.5, "1", True])
def test_refuses_bad_position_values(bad: object) -> None:
    frame = _frame([100, 100, 100], [100, 100, 100])
    with pytest.raises(BacktestInputError, match=r"positions\[1\] is .*: each position must be"):
        validate(frame, [0, bad, 0], 0.001)


def test_refuses_bad_position_series() -> None:
    frame = _frame([100, 100], [100, 100])
    for series in (
        pl.Series([0, None], dtype=pl.Int64),
        pl.Series([0.0, 1.0]),
        pl.Series([False, True]),
    ):
        with pytest.raises(BacktestInputError, match="each position must be"):
            validate(frame, series, 0.001)


def test_refuses_empty_frame() -> None:
    with pytest.raises(BacktestInputError, match="frame is empty"):
        validate(_frame([], []), [], 0.001)


@pytest.mark.parametrize("times", [[0, 2, 2], [0, 3, 1]])
def test_refuses_non_increasing_open_time(times: list[int]) -> None:
    frame = _frame([100, 100, 100], [100, 100, 100], times)
    with pytest.raises(BacktestInputError, match=r"open_time\[2\] .* strictly increasing"):
        validate(frame, [0, 0, 0], 0.001)


@pytest.mark.parametrize("fee", [-0.01, 1, 1.5, math.nan, True, "0.001", None])
def test_refuses_fee_out_of_range(fee: object) -> None:
    frame = _frame([100], [100])
    with pytest.raises(BacktestInputError, match="fee"):
        validate(frame, [0], fee)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("frame", "message"),
    [
        ({"open_time": [0], "open": [1.0], "close": [1.0]}, "polars DataFrame"),
        (pl.DataFrame({"open_time": [0], "open": [1.0]}), "lacks the column"),
        (
            pl.DataFrame({"open_time": [None, 1], "open": [1.0, 1.0], "close": [1.0, 1.0]}),
            r"open_time\[0\] is null",
        ),
        (_frame([100, None], [100, 100]), r"open\[1\] is None"),
        (_frame([100, 100], [100, math.inf]), r"close\[1\] is inf"),
        (_frame([100, 100], [math.nan, 100]), r"close\[0\] is nan"),
        (_frame([100, 0], [100, 100]), r"open\[1\] is 0.0"),
        (_frame([100, -5], [100, 100]), r"open\[1\] is -5.0"),
        (
            pl.DataFrame({"open_time": [0, 1], "open": ["a", "b"], "close": [1.0, 1.0]}),
            "prices must be numbers",
        ),
    ],
)
def test_refuses_bad_frame_schema_and_prices(frame: object, message: str) -> None:
    with pytest.raises(BacktestInputError, match=message):
        validate(frame, [0, 0], 0.001)  # type: ignore[arg-type]


def test_validate_reads_the_three_columns() -> None:
    times = [datetime(2024, 1, 1, hour, tzinfo=timezone.utc) for hour in (0, 1)]
    frame = _frame([100, 110], [105, 120], times).with_columns(pl.lit(7.0).alias("volume"))
    inputs = validate(frame, pl.Series([1, 0]), 0)
    assert inputs.opens == [100.0, 110.0]
    assert inputs.closes == [105.0, 120.0]
    assert inputs.positions == [1, 0]
    assert inputs.fee == 0.0
    assert inputs.open_time.to_list() == times
