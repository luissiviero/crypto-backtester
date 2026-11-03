"""Measure the cache layout: one year of 1m klines as 365 daily Parquet files vs one file.

Usage:
    python scripts/measure_storage.py                    # synthetic year, fixed seed
    python scripts/measure_storage.py --from-cache BTCUSDT 1m [--market spot] [--cache-dir DIR]

Prints a markdown table of the total size at zstd levels 3 and 9. Files are written to a
temporary directory that is deleted afterwards; nothing is written to the repository.
"""

from __future__ import annotations

import argparse
import random
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.data import cache
from app.data.params import (
    DAY_MS,
    day_start_ms,
    validate_interval,
    validate_market,
    validate_symbol,
)
from app.data.schema import SCHEMA, TIME_COLUMNS

SEED = 20261028
YEAR = 2023
LEVELS = (3, 9)
REOPEN_THRESHOLD = 0.20
MINUTE_MS = 60_000


def synthetic_year(seed: int = SEED, year: int = YEAR) -> list[pl.DataFrame]:
    """365 days of 1m candles: a seeded random-walk price, log-normal volumes."""
    rng = random.Random(seed)
    price = 16_500.0
    days = []
    day = date(year, 1, 1)
    while day.year == year:
        rows: dict[str, list[float] | list[int]] = {name: [] for name in SCHEMA}
        for minute in range(DAY_MS // MINUTE_MS):
            open_ms = day_start_ms(day) + minute * MINUTE_MS
            open_price = round(price, 2)
            price = max(price * (1 + rng.gauss(0, 0.0007)), 1.0)
            close_price = round(price, 2)
            high = round(max(open_price, close_price) * (1 + abs(rng.gauss(0, 0.0003))), 2)
            low = round(min(open_price, close_price) * (1 - abs(rng.gauss(0, 0.0003))), 2)
            volume = round(rng.lognormvariate(2.5, 0.9), 5)
            taker = round(volume * rng.uniform(0.3, 0.7), 5)
            candle = {
                "open_time": open_ms,
                "open": open_price,
                "high": high,
                "low": low,
                "close": close_price,
                "volume": volume,
                "close_time": open_ms + MINUTE_MS - 1,
                "quote_volume": round(volume * close_price, 8),
                "trades": int(volume * rng.uniform(20, 60)) + 1,
                "taker_buy_base_volume": taker,
                "taker_buy_quote_volume": round(taker * close_price, 8),
            }
            for name, value in candle.items():
                rows[name].append(value)
        days.append(_to_frame(rows))
        day += timedelta(days=1)
    return days


def _to_frame(rows: dict[str, list[float] | list[int]]) -> pl.DataFrame:
    raw_schema = {
        name: pl.Int64 if name in TIME_COLUMNS else dtype for name, dtype in SCHEMA.items()
    }
    raw = pl.DataFrame(rows, schema=raw_schema)
    return raw.with_columns(
        pl.col(name).cast(pl.Datetime("ms")).dt.replace_time_zone("UTC") for name in TIME_COLUMNS
    )


def cached_days(
    symbol: str, interval: str, market: str, cache_dir: str | None
) -> list[pl.DataFrame]:
    market = validate_market(market)
    interval = validate_interval(interval, market)
    symbol = validate_symbol(symbol)
    directory = cache.cache_root(cache_dir) / cache.SUBTREE / market / symbol / interval
    if not directory.is_dir():
        return []
    frames = (cache.read_day(path) for path in sorted(directory.glob("*.parquet")))
    return [frame for frame in frames if frame is not None]


def measure(days: list[pl.DataFrame]) -> dict[str, dict[int, int]]:
    """Total bytes per layout and zstd level."""
    sizes: dict[str, dict[int, int]] = {"daily": {}, "yearly": {}}
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        for level in LEVELS:
            total = 0
            for index, frame in enumerate(days):
                path = root / f"day-{level}-{index}.parquet"
                frame.write_parquet(path, compression="zstd", compression_level=level)
                total += path.stat().st_size
            sizes["daily"][level] = total
            path = root / f"year-{level}.parquet"
            pl.concat(days).write_parquet(path, compression="zstd", compression_level=level)
            sizes["yearly"][level] = path.stat().st_size
    return sizes


def report(title: str, source: str, days: list[pl.DataFrame]) -> str:
    sizes = measure(days)
    rows = sum(frame.height for frame in days)
    lines = [
        f"# Storage measurement ({title})",
        "",
        f"Source: {source}; {len(days)} days, {rows} rows, the schema of `app.data.schema`.",
        "",
        _row("layout", [f"zstd {level}" for level in LEVELS]),
        _row("---", ["---"] * len(LEVELS)),
        _row(f"{len(days)} daily files", [_mib(sizes["daily"][level]) for level in LEVELS]),
        _row("one yearly file", [_mib(sizes["yearly"][level]) for level in LEVELS]),
        _row("daily vs yearly", [_overhead(sizes, level) for level in LEVELS]),
        "",
    ]
    overhead = sizes["daily"][3] / sizes["yearly"][3] - 1
    verdict = "exceeds" if overhead > REOPEN_THRESHOLD else "is within"
    lines.append(
        f"Reopen rule (spec § Storage measurement): daily files at zstd 3 are "
        f"{overhead:+.1%} against one yearly file, which {verdict} the 20 % threshold."
    )
    return "\n".join(lines)


def _row(label: str, cells: list[str]) -> str:
    return "| " + " | ".join([label, *cells]) + " |"


def _mib(size: int) -> str:
    return f"{size / 1024 / 1024:.2f} MiB"


def _overhead(sizes: dict[str, dict[int, int]], level: int) -> str:
    return f"{sizes['daily'][level] / sizes['yearly'][level] - 1:+.1%}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--from-cache", nargs=2, metavar=("SYMBOL", "INTERVAL"))
    parser.add_argument("--market", default="spot")
    parser.add_argument("--cache-dir")
    args = parser.parse_args(argv)
    if args.from_cache is None:
        source = f"synthetic 1m candles for {YEAR}, random seed {SEED}"
        print(report("synthetic", source, synthetic_year()))
        return 0
    symbol, interval = args.from_cache
    days = cached_days(symbol, interval, args.market, args.cache_dir)
    if not days:
        print(f"No cached days for {symbol} {interval} {args.market}.", file=sys.stderr)
        return 1
    print(report("cached data", f"cached {symbol.upper()} {interval} {args.market}", days))
    return 0


if __name__ == "__main__":
    sys.exit(main())
