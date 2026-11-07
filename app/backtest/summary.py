"""The backtest summary: five numbers computed from the equity curve and the trades."""

from __future__ import annotations

from dataclasses import dataclass

START_EQUITY = 1.0


@dataclass(frozen=True)
class Summary:
    """Total return, max drawdown, trade count, win rate and time in market.

    `win_rate` is the share of trades whose return after fees is above 0: 0.0 when there are
    no trades; see trade_count. `time_in_market` counts rows, not wall time.
    """

    total_return: float
    max_drawdown: float
    trade_count: int
    win_rate: float
    time_in_market: float


def summarize(equity: list[float], held: list[int], returns: list[float]) -> Summary:
    wins = sum(1 for value in returns if value > 0)
    return Summary(
        total_return=equity[-1] / START_EQUITY - 1,
        max_drawdown=max_drawdown(equity),
        trade_count=len(returns),
        win_rate=wins / len(returns) if returns else 0.0,
        time_in_market=sum(held) / len(held),
    )


def max_drawdown(equity: list[float]) -> float:
    peak = equity[0]
    worst = 0.0
    for value in equity:
        peak = max(peak, value)
        worst = max(worst, 1 - value / peak)
    return worst
