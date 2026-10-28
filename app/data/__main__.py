"""CLI: `python -m app.data download | cache-info | cache-clear`."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from itertools import groupby

from app.data import loader
from app.data.cache import SUBTREE, cache_info, cache_root, clear_cache
from app.data.http import DownloadError, Fetch, urllib_fetch
from app.data.params import MARKETS, InvalidRequestError, make_request

SOURCE_LABELS = {
    loader.CACHED: "skipped, already cached",
    loader.VISION: "fetched from Vision",
    loader.REST: "filled from REST",
}


def main(argv: Sequence[str] | None = None, fetch: Fetch | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return args.command(args, fetch or urllib_fetch)
    except (InvalidRequestError, DownloadError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.data", description="Binance Vision kline data and its local cache."
    )
    commands = parser.add_subparsers(required=True, metavar="COMMAND")

    download = commands.add_parser("download", help="fill the cache for a date range")
    download.add_argument("symbol", metavar="SYMBOL")
    download.add_argument("interval", metavar="INTERVAL")
    download.add_argument("start", metavar="START", help="first day, YYYY-MM-DD (UTC)")
    download.add_argument("end", metavar="END", help="last day, YYYY-MM-DD (UTC), inclusive")
    download.add_argument("--market", choices=MARKETS, default="spot")
    download.add_argument("--cache-dir")
    download.set_defaults(command=_download)

    info = commands.add_parser("cache-info", help="show the cache size")
    info.add_argument("--market", choices=MARKETS)
    info.add_argument("--symbol")
    info.add_argument("--interval")
    info.add_argument("--cache-dir")
    info.set_defaults(command=_cache_info)

    clear = commands.add_parser("cache-clear", help="delete cached day files")
    clear.add_argument("symbol", metavar="SYMBOL")
    clear.add_argument("interval", metavar="INTERVAL", nargs="?")
    clear.add_argument("--market", choices=MARKETS, default="spot")
    clear.add_argument("--start", help="first day to delete, YYYY-MM-DD")
    clear.add_argument("--end", help="last day to delete, YYYY-MM-DD")
    clear.add_argument("--cache-dir")
    clear.set_defaults(command=_cache_clear)
    return parser


def _download(args: argparse.Namespace, fetch: Fetch) -> int:
    now = loader.utc_now()
    request = make_request(
        args.symbol, args.interval, args.start, args.end, args.market, now.date()
    )
    root = cache_root(args.cache_dir)
    outcomes = loader.sync_days(request, fetch=fetch, root=root, now=now)
    for (source, reason), group in groupby(outcomes, key=lambda o: (o.source, o.reason)):
        days = [outcome.day for outcome in group]
        span = f"{days[0]}" if len(days) == 1 else f"{days[0]} .. {days[-1]}"
        label = SOURCE_LABELS.get(source) or f"not found: {reason}"
        print(f"{span:<24}  {label} ({_count(len(days), 'day')})")
    gaps = loader.find_gaps(request, outcomes, now)
    for gap in gaps:
        if gap.reason in (loader.MISSING_IN_FILE, loader.MISSING_IN_REST):
            print(
                f"{gap.start:%Y-%m-%d %H:%M:%S} .. {gap.end:%Y-%m-%d %H:%M:%S} UTC  "
                f"{_count(gap.candles, 'candle')} missing: {gap.reason}"
            )
    counts = {source: 0 for source in (*SOURCE_LABELS, loader.MISSING)}
    for outcome in outcomes:
        counts[outcome.source] += 1
    missing = sum(gap.candles for gap in gaps)
    print(
        f"Total for {request.symbol} {request.interval} {request.market}: "
        f"{counts[loader.VISION]} fetched, {counts[loader.CACHED]} skipped, "
        f"{counts[loader.REST]} from REST, {counts[loader.MISSING]} not found; "
        f"{_count(missing, 'candle')} missing. Cache: {root}"
    )
    return 1 if gaps else 0


def _cache_info(args: argparse.Namespace, fetch: Fetch) -> int:
    root = cache_root(args.cache_dir)
    entries = cache_info(
        args.cache_dir, market=args.market, symbol=args.symbol, interval=args.interval
    )
    if not entries:
        print(f"No cached klines under {root / SUBTREE}.")
        return 0
    print(f"{'market':<8}{'symbol':<14}{'interval':<10}{'days':>6}{'size':>12}")
    for entry in entries:
        print(
            f"{entry.market:<8}{entry.symbol:<14}{entry.interval:<10}{entry.files:>6}"
            f"{human_size(entry.size):>12}"
        )
    files = sum(entry.files for entry in entries)
    size = sum(entry.size for entry in entries)
    print(f"Total: {_count(files, 'day file')}, {human_size(size)} under {root / SUBTREE}")
    return 0


def _cache_clear(args: argparse.Namespace, fetch: Fetch) -> int:
    result = clear_cache(
        args.symbol,
        args.interval,
        market=args.market,
        start=args.start,
        end=args.end,
        cache_dir=args.cache_dir,
    )
    what = " ".join(part for part in (args.symbol.upper(), args.interval, args.market) if part)
    if result.files == 0:
        print(f"Nothing to delete: no cached day files match {what}.")
    else:
        print(f"Deleted {_count(result.files, 'day file')} ({human_size(result.size)}) for {what}.")
    return 0


def human_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    value = float(size)
    for unit in ("KiB", "MiB", "GiB", "TiB"):
        value /= 1024
        if value < 1024 or unit == "TiB":
            break
    return f"{value:.1f} {unit}"


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}" if number == 1 else f"{number} {noun}s"


if __name__ == "__main__":
    sys.exit(main())
