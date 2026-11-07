"""The SMA crossover sweep: count, build and backtest a grid of fast and slow lengths. No I/O."""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass

import polars as pl

from app.backtest.engine import run_backtest
from app.backtest.strategy import sma_cross_positions
from app.backtest.summary import Summary

MAX_PAIRS = 400


@dataclass(frozen=True)
class SweepRow:
    """One pair of lengths and the summary of its backtest."""

    fast: int
    slow: int
    summary: Summary


def count_pairs(fasts: Sequence[int], slows: Sequence[int]) -> tuple[int, int]:
    """(kept, skipped) for sorted distinct lengths: kept pairs have fast below slow.

    Counts without building the grid, so a long list costs nothing before the cap check.
    """
    kept = sum(len(slows) - bisect_right(slows, fast) for fast in fasts)
    return kept, len(fasts) * len(slows) - kept


def pairs(fasts: Sequence[int], slows: Sequence[int]) -> list[tuple[int, int]]:
    """The pairs with fast below slow, fast-major, for sorted distinct lengths."""
    return [(fast, slow) for fast in fasts for slow in slows[bisect_right(slows, fast) :]]


def sweep(frame: pl.DataFrame, pairs: Sequence[tuple[int, int]], fee: float) -> list[SweepRow]:
    """One backtest per pair, sorted by total return, highest first; ties by fast, then slow."""
    rows = [
        SweepRow(
            fast, slow, run_backtest(frame, sma_cross_positions(frame, fast, slow), fee=fee).summary
        )
        for fast, slow in pairs
    ]
    return sorted(rows, key=lambda row: (-row.summary.total_return, row.fast, row.slow))
