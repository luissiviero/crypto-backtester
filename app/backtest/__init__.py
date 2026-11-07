"""The backtest engine: a long/flat backtest of one symbol on a klines frame.

The engine and the strategy do no I/O: pass them a frame such as `app.data.load_klines` returns
and, for the engine, one position per row. The CLI (`python -m app.backtest run`) loads klines
through `app.data.load_klines`.
"""

from app.backtest.engine import BacktestResult, run_backtest
from app.backtest.inputs import DEFAULT_FEE, BacktestInputError
from app.backtest.strategy import sma_cross_positions
from app.backtest.summary import Summary

__all__ = [
    "DEFAULT_FEE",
    "BacktestInputError",
    "BacktestResult",
    "Summary",
    "run_backtest",
    "sma_cross_positions",
]
