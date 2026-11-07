"""The backtest engine: a long/flat backtest of one symbol on a klines frame.

It does no I/O: pass it a frame such as `app.data.load_klines` returns and one position per row.
"""

from app.backtest.engine import BacktestResult, run_backtest
from app.backtest.inputs import DEFAULT_FEE, BacktestInputError
from app.backtest.summary import Summary

__all__ = [
    "DEFAULT_FEE",
    "BacktestInputError",
    "BacktestResult",
    "Summary",
    "run_backtest",
]
