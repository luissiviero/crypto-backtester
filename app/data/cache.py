"""The local Parquet cache: one zstd file per closed day, outside the repository by default."""

from __future__ import annotations

import os
import re
import sys
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import polars as pl

from app.data.params import (
    MARKETS,
    KlineRequest,
    parse_date,
    validate_interval,
    validate_market,
    validate_symbol,
)
from app.data.schema import SCHEMA
from app.data.vision import file_name

ENV_VAR = "CRYPTO_BACKTESTER_CACHE_DIR"
APP_NAME = "crypto-backtester"
SUBTREE = "binance-vision"
COMPRESSION_LEVEL = 3

_DAY_FILE = re.compile(
    r"(?P<symbol>[A-Z0-9]{2,30})-(?P<interval>[0-9]{1,2}[smhd])-(?P<day>\d{4}-\d{2}-\d{2})\.parquet"
)


class CachePathError(ValueError):
    """A cache path that would land outside `<cache>/binance-vision/`."""


@dataclass(frozen=True)
class CacheEntry:
    market: str
    symbol: str
    interval: str
    files: int
    size: int


@dataclass(frozen=True)
class ClearResult:
    files: int
    size: int


def cache_root(cache_dir: str | Path | None = None) -> Path:
    """The `cache_dir` argument, else the environment variable, else the platform default."""
    if cache_dir is not None:
        return Path(cache_dir).expanduser()
    from_env = os.environ.get(ENV_VAR)
    if from_env:
        return Path(from_env).expanduser()
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        base = Path(local) if local else Path.home() / "AppData" / "Local"
        return base / APP_NAME / "Cache"
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg and Path(xdg).is_absolute() else Path.home() / ".cache"
    return base / APP_NAME


def day_path(root: Path, request: KlineRequest, day: date) -> Path:
    subtree = (root / SUBTREE).resolve()
    name = f"{file_name(request, day)}.parquet"
    path = (subtree / request.market / request.symbol / request.interval / name).resolve()
    if not path.is_relative_to(subtree):
        raise CachePathError(f"{path} is outside {subtree}")
    return path


def write_day(path: Path, frame: pl.DataFrame) -> None:
    """Write atomically: a temporary file in the same directory, then a rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    os.close(handle)
    try:
        frame.write_parquet(temporary, compression="zstd", compression_level=COMPRESSION_LEVEL)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def read_day(path: Path) -> pl.DataFrame | None:
    """A cached day, or None when it is absent or unreadable (it is then fetched again)."""
    if not path.is_file():
        return None
    try:
        frame = pl.read_parquet(path)
    except (OSError, pl.exceptions.PolarsError):
        return None
    if frame.schema != pl.Schema(SCHEMA):
        return None
    return frame


def cache_info(
    cache_dir: str | Path | None = None,
    *,
    market: str | None = None,
    symbol: str | None = None,
    interval: str | None = None,
) -> list[CacheEntry]:
    """Day files and bytes per market, symbol and interval, optionally filtered."""
    markets = [validate_market(market)] if market else list(MARKETS)
    wanted_symbol = validate_symbol(symbol) if symbol else None
    if interval is not None:
        validate_interval(interval, "spot")
    entries = []
    subtree = cache_root(cache_dir) / SUBTREE
    for market_name in markets:
        for directory in _interval_dirs(subtree / market_name, wanted_symbol, interval):
            files = _day_files(directory)
            if files:
                size = sum(file.stat().st_size for file, _ in files)
                entry = CacheEntry(
                    market_name, directory.parent.name, directory.name, len(files), size
                )
                entries.append(entry)
    return entries


def clear_cache(
    symbol: str,
    interval: str | None = None,
    *,
    market: str = "spot",
    start: date | str | None = None,
    end: date | str | None = None,
    cache_dir: str | Path | None = None,
) -> ClearResult:
    """Delete the matching day files only; never a directory, never outside the subtree."""
    market = validate_market(market)
    symbol = validate_symbol(symbol)
    if interval is not None:
        validate_interval(interval, market)
    first = parse_date(start, "start") if start is not None else date.min
    last = parse_date(end, "end") if end is not None else date.max
    subtree = (cache_root(cache_dir) / SUBTREE).resolve()
    files = size = 0
    for directory in _interval_dirs(subtree / market, symbol, interval):
        for file, day in _day_files(directory):
            resolved = file.resolve()
            if first <= day <= last and resolved.is_relative_to(subtree):
                size += resolved.stat().st_size
                resolved.unlink()
                files += 1
    return ClearResult(files, size)


def _interval_dirs(market_dir: Path, symbol: str | None, interval: str | None) -> list[Path]:
    if not market_dir.is_dir():
        return []
    symbols = [market_dir / symbol] if symbol else sorted(market_dir.iterdir())
    found = []
    for symbol_dir in symbols:
        if not symbol_dir.is_dir() or symbol_dir.is_symlink():
            continue
        intervals = [symbol_dir / interval] if interval else sorted(symbol_dir.iterdir())
        found.extend(path for path in intervals if path.is_dir() and not path.is_symlink())
    return found


def _day_files(directory: Path) -> list[tuple[Path, date]]:
    """The regular files named `<SYMBOL>-<interval>-<YYYY-MM-DD>.parquet` for this directory."""
    files = []
    for path in sorted(directory.iterdir()):
        match = _DAY_FILE.fullmatch(path.name)
        if (
            match
            and match["symbol"] == directory.parent.name
            and match["interval"] == directory.name
            and path.is_file()
            and not path.is_symlink()
        ):
            try:
                files.append((path, date.fromisoformat(match["day"])))
            except ValueError:
                continue
    return files
