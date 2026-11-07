"""CLI: `python -m app.backtest run`, the SMA crossover on one symbol's KuCoin klines."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from app.backtest.engine import run_backtest
from app.backtest.inputs import DEFAULT_FEE, BacktestInputError, _check_fee
from app.backtest.strategy import STRATEGY_NAME, sma_cross_positions, validate_lengths
from app.data import DownloadError, Fetch, KlineGapError, load_klines, loader
from app.data.params import MARKETS, InvalidRequestError, make_request

SMA_NOTE = "SMAs count candles, not wall time: an interval without a candle is skipped, not filled."
RUN_HELP = "backtest the SMA crossover on a date range, loading missing days from KuCoin"


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
    run.add_argument("symbol", metavar="SYMBOL")
    run.add_argument("interval", metavar="INTERVAL")
    run.add_argument("start", metavar="START", help="first day, YYYY-MM-DD (UTC)")
    run.add_argument("end", metavar="END", help="last day, YYYY-MM-DD (UTC), inclusive")
    run.add_argument("--market", choices=MARKETS, default="spot")
    run.add_argument("--fast", default="20", help="fast SMA length in candles (default 20)")
    run.add_argument("--slow", default="50", help="slow SMA length in candles (default 50)")
    run.add_argument(
        "--fee", default=str(DEFAULT_FEE), help=f"proportional fee per fill (default {DEFAULT_FEE})"
    )
    run.add_argument("--cache-dir")
    run.set_defaults(command=_run)
    return parser


def _run(args: argparse.Namespace, fetch: Fetch | None) -> int:
    today = loader.utc_now().date()
    request = make_request(args.symbol, args.interval, args.start, args.end, args.market, today)
    fast, slow = _length(args.fast, "fast"), _length(args.slow, "slow")
    validate_lengths(fast, slow)
    fee = _fee(args.fee)
    frame = load_klines(
        request.symbol,
        request.interval,
        request.start,
        request.end,
        market=request.market,
        cache_dir=args.cache_dir,
        fetch=fetch,
    )
    if frame.height <= slow:
        raise BacktestInputError(
            f"the range has {frame.height} candles, not more than slow {slow}: the strategy "
            "could never take a position; widen the dates or lower --slow"
        )
    result = run_backtest(frame, sma_cross_positions(frame, fast, slow), fee=fee)
    hold = run_backtest(frame, [1] * frame.height, fee=fee)
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
        ("buy and hold", _percent(hold.summary.total_return)),
    ):
        print(f"{label:<14}{value:>8}")
    return 0


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
