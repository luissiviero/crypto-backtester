"""Tests for the SMA crossover sweep: the module on frames built by hand."""

from __future__ import annotations

from collections.abc import Sequence

import polars as pl

from app.backtest.engine import run_backtest
from app.backtest.strategy import sma_cross_positions
from app.backtest.sweep import count_pairs, pairs, sweep

VARYING = [10, 12, 11, 14, 13, 9, 8, 12, 15, 14, 16, 11, 10, 13, 17, 18, 14, 12, 15, 19]


def _frame(closes: Sequence[float]) -> pl.DataFrame:
    prices = pl.Series(closes, dtype=pl.Float64)
    return pl.DataFrame({"open_time": list(range(len(closes))), "open": prices, "close": prices})


def test_count_pairs_counts_kept_and_skipped() -> None:
    assert count_pairs([5, 10, 20], [30, 50, 100]) == (9, 0)
    assert count_pairs([5, 50], [10, 50]) == (2, 2)
    assert pairs([5, 50], [10, 50]) == [(5, 10), (5, 50)]
    assert pairs([2, 3, 5], [5, 8]) == [(2, 5), (2, 8), (3, 5), (3, 8), (5, 8)]
    assert count_pairs([2, 3, 5], [5, 8]) == (5, 1)


def test_sweep_rows_match_run_backtest() -> None:
    frame = _frame(VARYING)
    grid = pairs([2, 3, 4], [5, 6, 8])
    rows = sweep(frame, grid, 0.001)
    assert sorted((row.fast, row.slow) for row in rows) == sorted(grid)
    for row in rows:
        positions = sma_cross_positions(frame, row.fast, row.slow)
        assert row.summary == run_backtest(frame, positions, fee=0.001).summary
    returns = [row.summary.total_return for row in rows]
    assert returns == sorted(returns, reverse=True)
    assert len(set(returns)) > 1


def test_sweep_ties_sort_by_fast_then_slow() -> None:
    frame = _frame([5.0] * 12)
    rows = sweep(frame, [(3, 8), (2, 8), (3, 5), (2, 5)], 0.001)
    assert [(row.fast, row.slow) for row in rows] == [(2, 5), (2, 8), (3, 5), (3, 8)]
    assert all(row.summary.total_return == 0.0 for row in rows)
