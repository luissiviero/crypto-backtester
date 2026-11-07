"""The long/flat engine: one forward pass that fills each decision at the next row's open."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import polars as pl

from app.backtest.inputs import DEFAULT_FEE, Inputs, validate
from app.backtest.summary import START_EQUITY, Summary, summarize


@dataclass(frozen=True)
class BacktestResult:
    """The equity per row (marked at close), the closed trades and the summary."""

    equity: pl.DataFrame
    trades: pl.DataFrame
    summary: Summary


@dataclass(frozen=True)
class _Trade:
    entry_row: int
    entry_price: float
    exit_row: int
    exit_price: float
    ret: float
    closed_at_end: bool


@dataclass
class _Pass:
    equity: list[float] = field(default_factory=list)
    held: list[int] = field(default_factory=list)
    trades: list[_Trade] = field(default_factory=list)


def run_backtest(
    frame: pl.DataFrame, positions: pl.Series | Sequence[int], *, fee: float = DEFAULT_FEE
) -> BacktestResult:
    """Backtest long/flat `positions` (0 or 1, decided at each row's close) on `frame`.

    Each decision fills at the next row's open, whatever the gap; a position still long after
    the last row's open is closed at the last close. Raises BacktestInputError on bad input.
    """
    inputs = validate(frame, positions, fee)
    run = _simulate(inputs)
    return BacktestResult(
        equity=_equity_frame(inputs.open_time, run),
        trades=_trades_frame(inputs.open_time, run.trades),
        summary=summarize(run.equity, run.held, [trade.ret for trade in run.trades]),
    )


def _simulate(inputs: Inputs) -> _Pass:
    fee = inputs.fee
    opens, closes = inputs.opens, inputs.closes
    cash, coins, held = START_EQUITY, 0.0, 0
    entry_row, entry_cash = 0, 0.0
    run = _Pass(equity=[START_EQUITY], held=[0])
    for row in range(1, len(opens)):
        target = inputs.positions[row - 1]
        if target != held:
            if target:
                entry_row, entry_cash = row, cash
                coins, cash = cash * (1 - fee) / opens[row], 0.0
            else:
                cash, coins = coins * opens[row] * (1 - fee), 0.0
                run.trades.append(
                    _Trade(
                        entry_row, opens[entry_row], row, opens[row], cash / entry_cash - 1, False
                    )
                )
            held = target
        run.held.append(held)
        run.equity.append(coins * closes[row] if held else cash)
    if held:
        last = len(closes) - 1
        cash = coins * closes[last] * (1 - fee)
        run.trades.append(
            _Trade(entry_row, opens[entry_row], last, closes[last], cash / entry_cash - 1, True)
        )
        run.equity[last] = cash
    return run


def _equity_frame(open_time: pl.Series, run: _Pass) -> pl.DataFrame:
    return pl.DataFrame(
        [
            open_time,
            pl.Series("position", run.held, dtype=pl.Int8),
            pl.Series("equity", run.equity, dtype=pl.Float64),
        ]
    )


def _trades_frame(open_time: pl.Series, trades: list[_Trade]) -> pl.DataFrame:
    return pl.DataFrame(
        [
            open_time.gather([trade.entry_row for trade in trades]).alias("entry_time"),
            pl.Series("entry_price", [trade.entry_price for trade in trades], dtype=pl.Float64),
            open_time.gather([trade.exit_row for trade in trades]).alias("exit_time"),
            pl.Series("exit_price", [trade.exit_price for trade in trades], dtype=pl.Float64),
            pl.Series("return", [trade.ret for trade in trades], dtype=pl.Float64),
            pl.Series("closed_at_end", [trade.closed_at_end for trade in trades], dtype=pl.Boolean),
        ]
    )
