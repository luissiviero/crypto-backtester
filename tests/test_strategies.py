"""Offline tests for the SMA crossover strategy, on frames built by hand."""

from __future__ import annotations

from collections.abc import Sequence

import polars as pl
import pytest

import app.backtest
from app.backtest.engine import run_backtest
from app.backtest.inputs import BacktestInputError
from app.backtest.strategy import sma_cross_positions

EXAMPLE = [1, 2, 3, 2, 1, 1, 3]
# fast 2: [-, 1.5, 2.5, 2.5, 1.5, 1, 2]; slow 3: [-, -, 2, 7/3, 2, 4/3, 5/3]
EXAMPLE_POSITIONS = [0, 0, 1, 1, 0, 0, 1]


def _frame(closes: Sequence[float]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "open_time": list(range(len(closes))),
            "open": pl.Series(list(closes), dtype=pl.Float64),
            "close": pl.Series(list(closes), dtype=pl.Float64),
        }
    )


def test_positions_match_hand_computed_example() -> None:
    positions = sma_cross_positions(_frame(EXAMPLE), 2, 3)
    assert positions.name == "position"
    assert positions.dtype == pl.Int8
    assert positions.to_list() == EXAMPLE_POSITIONS


def test_warm_up_rows_are_flat() -> None:
    # Rising closes: the fast SMA is above the slow one wherever both exist.
    positions = sma_cross_positions(_frame([1, 2, 3, 4, 5, 6]), 2, 4).to_list()
    assert positions == [0, 0, 0, 1, 1, 1]


def test_equal_smas_give_flat() -> None:
    assert sma_cross_positions(_frame([2, 2, 2, 2]), 2, 3).to_list() == [0, 0, 0, 0]


def test_positions_ignore_later_closes() -> None:
    changed = [*EXAMPLE[:4], 9, 9, 9]
    positions = sma_cross_positions(_frame(changed), 2, 3).to_list()
    assert positions[:4] == EXAMPLE_POSITIONS[:4] == [0, 0, 1, 1]
    for k in range(len(EXAMPLE)):
        later = [*EXAMPLE[: k + 1], *([50] * (len(EXAMPLE) - k - 1))]
        kept = sma_cross_positions(_frame(later), 2, 3).to_list()[: k + 1]
        assert kept == EXAMPLE_POSITIONS[: k + 1]


def test_positions_accepted_by_run_backtest() -> None:
    frame = _frame(EXAMPLE)
    result = run_backtest(frame, sma_cross_positions(frame, 2, 3), fee=0.0)
    assert result.equity["position"].to_list() == [0, 0, 0, 1, 1, 0, 0]
    # Long from row 3's open (2) to row 5's open (1).
    assert result.summary.trade_count == 1
    assert abs(result.summary.total_return - (-0.5)) < 1e-9


@pytest.mark.parametrize(
    ("fast", "slow", "message"),
    [
        (0, 3, "fast 0 is not a whole number of at least 1"),
        (-1, 3, "fast -1 is not a whole number of at least 1"),
        (1.0, 3, "fast 1.0 is not a whole number of at least 1"),
        ("2", 3, "fast '2' is not a whole number of at least 1"),
        (True, 3, "fast True is not a whole number of at least 1"),
        (2, 0, "slow 0 is not a whole number of at least 1"),
        (2, None, "slow None is not a whole number of at least 1"),
        (3, 2, "fast 3 is not below slow 2: the fast SMA must be the shorter one"),
        (3, 3, "fast 3 is not below slow 3: the fast SMA must be the shorter one"),
    ],
)
def test_refuses_bad_lengths(fast: object, slow: object, message: str) -> None:
    with pytest.raises(BacktestInputError) as caught:
        sma_cross_positions(_frame(EXAMPLE), fast, slow)  # type: ignore[arg-type]
    assert str(caught.value) == message


@pytest.mark.parametrize(
    ("frame", "message"),
    [
        ({"close": [1.0, 2.0]}, "frame is a dict: pass a polars DataFrame"),
        (pl.DataFrame({"open": [1.0, 2.0]}), "frame lacks the column close"),
        (pl.DataFrame({"close": ["1", "2"]}), "close has dtype String: prices must be numbers"),
    ],
)
def test_refuses_frame_without_close(frame: object, message: str) -> None:
    with pytest.raises(BacktestInputError) as caught:
        sma_cross_positions(frame, 2, 3)  # type: ignore[arg-type]
    assert str(caught.value).startswith(message)


def test_public_api_exports_strategy() -> None:
    assert "sma_cross_positions" in app.backtest.__all__
    assert app.backtest.sma_cross_positions is sma_cross_positions
