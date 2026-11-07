"""CLI: `python -m app.backtest run | sweep`, the SMA crossover on one symbol's KuCoin klines."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

import polars as pl

from app.backtest.engine import run_backtest
from app.backtest.inputs import DEFAULT_FEE, BacktestInputError, _check_fee
from app.backtest.strategy import STRATEGY_NAME, sma_cross_positions, validate_lengths
from app.backtest.sweep import MAX_PAIRS, SweepRow, count_pairs, pairs, sweep
from app.data import DownloadError, Fetch, KlineGapError, load_klines, loader
from app.data.params import MARKETS, InvalidRequestError, KlineRequest, make_request

SMA_NOTE = "SMAs count candles, not wall time: an interval without a candle is skipped, not filled."
RUN_HELP = "backtest the SMA crossover on a date range, loading missing days from KuCoin"
SWEEP_HELP = "backtest the SMA crossover for every pair of a grid of lengths, best first"
SWEEP_WARNING = (
    "The best pair on past data is often luck: check it on another date range before trusting it."
)
SWEEP_FAST = "5,10,20"
SWEEP_SLOW = "30,50,100"
SWEEP_HEADERS = (
    "fast",
    "slow",
    "total return",
    "max drawdown",
    "trades",
    "win rate",
    "time in market",
)


def main(argv: Sequence[str] | None = None, fetch: Fetch | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return args.command(args, fetch)
    except (InvalidRequestError, KlineGapError, DownloadError, BacktestInputError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except OSError as error:
        print(f"error: {error}; check the cache directory (--cache-dir)", file=sys.stderr)
        return 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.backtest",
        description="Backtest a built-in strategy on cached KuCoin klines.",
    )
    commands = parser.add_subparsers(required=True, metavar="COMMAND")

    run = commands.add_parser("run", help=RUN_HELP, epilog=SMA_NOTE)
    _add_range_arguments(run)
    run.add_argument("--fast", default="20", help="fast SMA length in candles (default 20)")
    run.add_argument("--slow", default="50", help="slow SMA length in candles (default 50)")
    _add_fee_arguments(run)
    run.set_defaults(command=_run)

    grid = commands.add_parser("sweep", help=SWEEP_HELP, epilog=SMA_NOTE)
    _add_range_arguments(grid)
    grid.add_argument(
        "--fast",
        default=SWEEP_FAST,
        help=f"comma-separated fast SMA lengths in candles (default {SWEEP_FAST})",
    )
    grid.add_argument(
        "--slow",
        default=SWEEP_SLOW,
        help=f"comma-separated slow SMA lengths in candles (default {SWEEP_SLOW})",
    )
    _add_fee_arguments(grid)
    grid.set_defaults(command=_sweep)
    return parser


def _add_range_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("symbol", metavar="SYMBOL")
    parser.add_argument("interval", metavar="INTERVAL")
    parser.add_argument("start", metavar="START", help="first day, YYYY-MM-DD (UTC)")
    parser.add_argument("end", metavar="END", help="last day, YYYY-MM-DD (UTC), inclusive")
    parser.add_argument("--market", choices=MARKETS, default="spot")


def _add_fee_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--fee", default=str(DEFAULT_FEE), help=f"proportional fee per fill (default {DEFAULT_FEE})"
    )
    parser.add_argument("--cache-dir")


def _run(args: argparse.Namespace, fetch: Fetch | None) -> int:
    today = loader.utc_now().date()
    request = make_request(args.symbol, args.interval, args.start, args.end, args.market, today)
    fast, slow = _length(args.fast, "fast"), _length(args.slow, "slow")
    validate_lengths(fast, slow)
    fee = _fee(args.fee)
    frame = _load(request, args, fetch)
    if frame.height <= slow:
        raise BacktestInputError(
            f"the range has {frame.height} candles, not more than slow {slow}: the strategy "
            "could never take a position; widen the dates or lower --slow"
        )
    result = run_backtest(frame, sma_cross_positions(frame, fast, slow), fee=fee)
    print(
        f"{request.symbol} {request.interval} {request.market}, "
        f"{request.start} .. {request.end}: {frame.height} candles; "
        f"{STRATEGY_NAME} fast {fast} slow {slow}; fee {_percent(fee)}"
    )
    print(SMA_NOTE)
    summary = result.summary
    for label, value in (
        ("total return", _percent(summary.total_return)),
        ("max drawdown", _percent(summary.max_drawdown)),
        ("trades", str(summary.trade_count)),
        ("win rate", _percent(summary.win_rate)),
        ("time in market", _percent(summary.time_in_market)),
    ):
        print(f"{label:<14}{value:>8}")
    print(_hold_line(frame, fee))
    return 0


def _sweep(args: argparse.Namespace, fetch: Fetch | None) -> int:
    today = loader.utc_now().date()
    request = make_request(args.symbol, args.interval, args.start, args.end, args.market, today)
    fasts = _lengths(args.fast, "fast", SWEEP_FAST)
    slows = _lengths(args.slow, "slow", SWEEP_SLOW)
    fee = _fee(args.fee)
    kept, skipped = count_pairs(fasts, slows)
    if kept == 0:
        raise BacktestInputError(
            "no pair has fast below slow: pass a --fast value below a --slow value"
        )
    if kept > MAX_PAIRS:
        raise BacktestInputError(
            f"the grid has {kept} pairs with fast below slow, more than {MAX_PAIRS}: "
            "pass shorter --fast or --slow lists"
        )
    frame = _load(request, args, fetch)
    grid = [(fast, slow) for fast, slow in pairs(fasts, slows) if slow < frame.height]
    skipped += kept - len(grid)
    if not grid:
        raise BacktestInputError(
            f"the range has {frame.height} candles, not more than any slow length with a smaller "
            "fast: no pair could take a position; widen the dates or lower --slow"
        )
    print(
        f"{request.symbol} {request.interval} {request.market}, "
        f"{request.start} .. {request.end}: {frame.height} candles; "
        f"{STRATEGY_NAME}, {len(grid)} pairs tried, {skipped} skipped; fee {_percent(fee)}"
    )
    print(SMA_NOTE, flush=True)
    for line in _table(sweep(frame, grid, fee)):
        print(line)
    print(_hold_line(frame, fee))
    print(SWEEP_WARNING)
    return 0


def _lengths(text: str, name: str, example: str) -> list[int]:
    if text.strip() == "":
        raise BacktestInputError(
            f"--{name} is empty: pass comma-separated whole numbers, for example {example}"
        )
    values = []
    for item in text.split(","):
        value = _length(item, name)
        if value < 1:
            raise BacktestInputError(f"{name} {value} is not a whole number of at least 1")
        values.append(value)
    return sorted(set(values))


def _table(rows: Sequence[SweepRow]) -> list[str]:
    lines = [SWEEP_HEADERS, *(_cells(row) for row in rows)]
    widths = [max(len(cell) for cell in column) for column in zip(*lines)]
    return ["  ".join(cell.rjust(width) for cell, width in zip(line, widths)) for line in lines]


def _cells(row: SweepRow) -> tuple[str, ...]:
    summary = row.summary
    return (
        str(row.fast),
        str(row.slow),
        _percent(summary.total_return),
        _percent(summary.max_drawdown),
        str(summary.trade_count),
        _percent(summary.win_rate),
        _percent(summary.time_in_market),
    )


def _load(request: KlineRequest, args: argparse.Namespace, fetch: Fetch | None) -> pl.DataFrame:
    return load_klines(
        request.symbol,
        request.interval,
        request.start,
        request.end,
        market=request.market,
        cache_dir=args.cache_dir,
        fetch=fetch,
    )


def _hold_line(frame: pl.DataFrame, fee: float) -> str:
    hold = run_backtest(frame, [1] * frame.height, fee=fee)
    return f"{'buy and hold':<14}{_percent(hold.summary.total_return):>8}"


def _length(text: str, name: str) -> int:
    try:
        return int(text)
    except ValueError:
        raise BacktestInputError(f"{name} {text!r} is not a whole number of at least 1") from None


def _fee(text: str) -> float:
    try:
        value = float(text)
    except ValueError:
        raise BacktestInputError(
            f"fee {text!r} is not a number: pass a proportional fee, for example 0.001"
        ) from None
    return _check_fee(value)


def _percent(fraction: float) -> str:
    return f"{fraction:.2%}"


if __name__ == "__main__":
    sys.exit(main())
