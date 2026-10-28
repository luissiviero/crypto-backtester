"""load_klines: cached days first, then Vision in parallel, then REST for Vision's 404 days."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import polars as pl

from app.data import cache as day_cache
from app.data import rest, vision
from app.data.http import Fetch, HttpResponse, urllib_fetch, with_retries
from app.data.params import DAY_MS, KlineRequest, day_start_ms, make_request
from app.data.schema import empty_frame

VISION_WORKERS = 4
CACHED, VISION, REST, MISSING = "cached", "vision", "rest", "missing"
NO_CANDLES = "not on Vision (404) and REST returned no candles"
MISSING_IN_FILE = "missing candles in source file"
MISSING_IN_REST = "missing candles in REST response"
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def utc_now() -> datetime:
    """The clock; tests monkeypatch it."""
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Gap:
    """Missing candles: open times of the first and last one, how many, and why."""

    start: datetime
    end: datetime
    candles: int
    reason: str


class KlineGapError(Exception):
    """The range is not complete; `.frame` holds the rows that were found."""

    def __init__(self, gaps: tuple[Gap, ...], frame: pl.DataFrame) -> None:
        self.gaps = gaps
        self.frame = frame
        missing = sum(gap.candles for gap in gaps)
        first = gaps[0]
        super().__init__(
            f"{missing} candle(s) missing in {len(gaps)} gap(s); the first from "
            f"{first.start:%Y-%m-%d %H:%M:%S} UTC ({first.candles} candles): {first.reason}"
        )


@dataclass(frozen=True)
class DayOutcome:
    """Where a day's candles came from (cached, vision, rest) or why it has none (missing)."""

    day: date
    source: str
    frame: pl.DataFrame
    reason: str | None = None


def load_klines(
    symbol: str,
    interval: str,
    start: date | str,
    end: date | str,
    *,
    market: str = "spot",
    cache_dir: str | Path | None = None,
    cache: bool = True,
    fetch: Fetch | None = None,
) -> pl.DataFrame:
    """Load an inclusive UTC date range into one frame; raise KlineGapError if any is missing."""
    now = utc_now()
    request = make_request(symbol, interval, start, end, market, now.date())
    root = day_cache.cache_root(cache_dir) if cache else None
    outcomes = sync_days(request, fetch=fetch or urllib_fetch, root=root, now=now)
    frame = combine(outcomes)
    gaps = find_gaps(request, outcomes, now)
    if gaps:
        raise KlineGapError(gaps, frame)
    return frame


def sync_days(
    request: KlineRequest, *, fetch: Fetch, root: Path | None, now: datetime
) -> list[DayOutcome]:
    """One outcome per day of the request; closed days fetched here are written to the cache."""
    fetch = with_retries(fetch)
    today = now.date()
    outcomes: dict[date, DayOutcome] = {}
    to_fetch = []
    for day in request.days():
        cached = _read_cached(root, request, day) if day < today else None
        if cached is not None:
            outcomes[day] = DayOutcome(day, CACHED, cached)
        else:
            to_fetch.append(day)
    rest_days = []
    for answer in _vision_pass(fetch, request, to_fetch):
        if answer.frame is not None:
            outcomes[answer.day] = DayOutcome(answer.day, VISION, answer.frame)
        elif answer.reason == vision.NOT_ON_VISION:
            rest_days.append(answer.day)
        else:
            outcomes[answer.day] = DayOutcome(answer.day, MISSING, empty_frame(), answer.reason)
    outcomes.update(_rest_pass(fetch, request, sorted(rest_days)))
    now_ms = _to_ms(now)
    result = []
    for day in request.days():
        outcome = outcomes[day]
        frame = _on_grid(outcome.frame, _expected_ms(request, day, now_ms))
        outcome = DayOutcome(day, outcome.source, frame, outcome.reason)
        if root is not None and day < today and _worth_caching(request, outcome):
            day_cache.write_day(day_cache.day_path(root, request, day), frame)
        result.append(outcome)
    return result


def combine(outcomes: list[DayOutcome]) -> pl.DataFrame:
    frames = [outcome.frame for outcome in outcomes]
    frame = pl.concat(frames) if frames else empty_frame()
    return frame.sort("open_time").unique(subset="open_time", keep="first", maintain_order=True)


def find_gaps(request: KlineRequest, outcomes: list[DayOutcome], now: datetime) -> tuple[Gap, ...]:
    """Every expected open time absent from the frames; consecutive ones form one gap."""
    step = request.interval_ms
    runs: list[_Run] = []
    for outcome in outcomes:
        present = set(outcome.frame["open_time"].dt.epoch("ms").to_list())
        reason = _gap_reason(outcome)
        for open_ms in _expected_ms(request, outcome.day, _to_ms(now)):
            if open_ms in present:
                continue
            last = runs[-1] if runs else None
            if last is not None and last.last_ms == open_ms - step and last.reason == reason:
                last.last_ms = open_ms
                last.candles += 1
            else:
                runs.append(_Run(open_ms, open_ms, 1, reason))
    return tuple(
        Gap(_to_datetime(run.first_ms), _to_datetime(run.last_ms), run.candles, run.reason)
        for run in runs
    )


@dataclass
class _Run:
    first_ms: int
    last_ms: int
    candles: int
    reason: str


def _read_cached(root: Path | None, request: KlineRequest, day: date) -> pl.DataFrame | None:
    if root is None:
        return None
    return day_cache.read_day(day_cache.day_path(root, request, day))


class _Cancelled(Exception):
    """Raised in the pool's threads once one of them hit a stop (a ban)."""


def _vision_pass(fetch: Fetch, request: KlineRequest, days: list[date]) -> list[vision.VisionDay]:
    """Up to VISION_WORKERS days at a time; a stop in one cancels every pending download."""
    if not days:
        return []
    stop = threading.Event()

    def guarded(url: str) -> HttpResponse:
        if stop.is_set():
            raise _Cancelled(url)
        return fetch(url)

    pool = ThreadPoolExecutor(max_workers=VISION_WORKERS)
    try:
        futures = [pool.submit(vision.fetch_day, guarded, request, day) for day in days]
        return [future.result() for future in as_completed(futures)]
    except BaseException:
        stop.set()
        raise
    finally:
        pool.shutdown(wait=True, cancel_futures=True)


def _rest_pass(fetch: Fetch, request: KlineRequest, days: list[date]) -> dict[date, DayOutcome]:
    """Consecutive days form one REST range; ranges run one after the other."""
    pacer = rest.pacer_for(request.market)
    outcomes = {}
    for first, last in _consecutive_ranges(days):
        start_ms = day_start_ms(first)
        answer = rest.fetch_range(fetch, pacer, request, start_ms, day_start_ms(last) + DAY_MS)
        day = first
        while day <= last:
            day_ms = day_start_ms(day)
            open_ms = pl.col("open_time").dt.epoch("ms")
            frame = answer.frame.filter((open_ms >= day_ms) & (open_ms < day_ms + DAY_MS))
            if frame.is_empty():
                outcomes[day] = DayOutcome(day, MISSING, frame, answer.failure or NO_CANDLES)
            else:
                outcomes[day] = DayOutcome(day, REST, frame)
            day += timedelta(days=1)
    return outcomes


def _consecutive_ranges(days: list[date]) -> list[tuple[date, date]]:
    ranges: list[tuple[date, date]] = []
    for day in days:
        if ranges and ranges[-1][1] == day - timedelta(days=1):
            ranges[-1] = (ranges[-1][0], day)
        else:
            ranges.append((day, day))
    return ranges


def _expected_ms(request: KlineRequest, day: date, now_ms: int) -> list[int]:
    """The day's candle grid; on the current day only candles already closed."""
    start = day_start_ms(day)
    grid = range(start, start + DAY_MS, request.interval_ms)
    return [open_ms for open_ms in grid if open_ms + request.interval_ms <= now_ms]


def _on_grid(frame: pl.DataFrame, expected_ms: list[int]) -> pl.DataFrame:
    on_grid = frame.filter(pl.col("open_time").dt.epoch("ms").is_in(expected_ms))
    return on_grid.sort("open_time").unique(subset="open_time", keep="first", maintain_order=True)


def _worth_caching(request: KlineRequest, outcome: DayOutcome) -> bool:
    """A closed Vision day is final; a REST day only when complete (a refused page is not)."""
    if outcome.source == VISION:
        return not outcome.frame.is_empty()
    if outcome.source == REST:
        return outcome.frame.height == DAY_MS // request.interval_ms
    return False


def _gap_reason(outcome: DayOutcome) -> str:
    if outcome.source == MISSING:
        return outcome.reason or NO_CANDLES
    if outcome.source == REST:
        return MISSING_IN_REST
    return MISSING_IN_FILE


def _to_ms(moment: datetime) -> int:
    return (moment - _EPOCH) // timedelta(milliseconds=1)


def _to_datetime(open_ms: int) -> datetime:
    return _EPOCH + timedelta(milliseconds=open_ms)
