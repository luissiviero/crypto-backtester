"""load_klines: cached days first, then KuCoin's REST klines for the rest, one call at a time."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import polars as pl

from app.data import cache as day_cache
from app.data import rest
from app.data.http import Fetch, RateLimitPacer, urllib_fetch, with_retries
from app.data.params import DAY_MS, KlineRequest, day_start_ms, make_request

CACHED, REST, MISSING = "cached", "rest", "missing"
NO_CANDLES = "no candles; check the symbol exists"
NO_CANDLES_ON_DAY = "no candles on this day"
BEFORE_FIRST = (
    "no candles before {day}: the date may be before KuCoin's oldest candle for this symbol"
)
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
    """Where a day's candles came from (cached, rest) or why it is not complete (missing)."""

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
    """Load an inclusive UTC date range into one frame; raise KlineGapError if any is missing.

    KuCoin publishes no candle for an interval without trades, so a day's rows exist only for
    the intervals that had trades: a short frame is normal, and callers must never assume one
    row per interval. A day is complete when it has at least one candle and every page that
    covered it was answered; a day with no candle, a refused or cut-short page, or a date
    before KuCoin's oldest candle raises KlineGapError with the reason.

    Futures `volume` counts contracts, spot `volume` coins: do not compare the two; compare
    `quote_volume`, which is in the quote currency on both markets.

    Deprecated and removed (KuCoin does not publish them): the `trades`,
    `taker_buy_base_volume` and `taker_buy_quote_volume` columns, `BinanceBanError`, the `um`
    market and the `1s` interval.
    """
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
    """One outcome per day of the request.

    Each complete closed day fetched here is written to the cache as soon as its range is in,
    so a run stopped part way (retries exhausted, a long Retry-After) keeps the days its
    answered pages cover, then raises.
    """
    fetch = with_retries(fetch)
    today = now.date()
    now_ms = _to_ms(now)
    outcomes: dict[date, DayOutcome] = {}

    def settle(outcome: DayOutcome) -> None:
        frame = _on_grid(outcome.frame, _expected_ms(request, outcome.day, now_ms))
        outcome = replace(outcome, frame=frame)
        if outcome.source == REST and frame.is_empty() and outcome.day < today:
            # Rows only off the day's grid: no candle the day can keep.
            outcome = replace(outcome, source=MISSING, reason=NO_CANDLES_ON_DAY)
        if root is not None and outcome.day < today and _worth_caching(outcome):
            day_cache.write_day(day_cache.day_path(root, request, outcome.day), frame)
        outcomes[outcome.day] = outcome

    to_fetch = []
    for day in request.days():
        cached = _read_cached(root, request, day) if day < today else None
        if cached is not None:
            settle(DayOutcome(day, CACHED, cached))
        else:
            to_fetch.append(day)
    _rest_pass(fetch, request, to_fetch, settle)
    return [outcomes[day] for day in request.days()]


def combine(outcomes: list[DayOutcome]) -> pl.DataFrame:
    """Join the days of sync_days: each is on its own grid, sorted and unique, in day order."""
    return pl.concat([outcome.frame for outcome in outcomes])


def find_gaps(request: KlineRequest, outcomes: list[DayOutcome], now: datetime) -> tuple[Gap, ...]:
    """Every expected open time absent from a missing day's frame; consecutive ones form one gap.

    A complete day's quiet intervals are not gaps: KuCoin has no candle for them.
    """
    step = request.interval_ms
    now_ms = _to_ms(now)
    runs: list[_Run] = []
    for outcome in outcomes:
        if outcome.source != MISSING:
            continue
        present = set(outcome.frame["open_time"].dt.epoch("ms").to_list())
        reason = _gap_reason(outcome)
        for open_ms in _expected_ms(request, outcome.day, now_ms):
            if open_ms in present:
                continue
            if runs and runs[-1].last_ms == open_ms - step and runs[-1].reason == reason:
                runs[-1].last_ms = open_ms
                runs[-1].candles += 1
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


def _rest_pass(
    fetch: Fetch,
    request: KlineRequest,
    days: list[date],
    on_outcome: Callable[[DayOutcome], None],
) -> None:
    """Consecutive days form one range; ranges run one after the other, on one pacer.

    A day is complete (REST) only when it lies inside the span the answered pages cover and
    has a candle. A DownloadError that stopped a range is raised once its days are settled.
    """
    pacer = RateLimitPacer()
    open_ms = pl.col("open_time").dt.epoch("ms")
    for first, last in _consecutive_ranges(days):
        end_ms = day_start_ms(last) + DAY_MS
        answer = rest.fetch_range(fetch, pacer, request, day_start_ms(first), end_ms)
        first_day_with_rows = _first_day(answer.frame)
        day = first
        while day <= last:
            day_ms = day_start_ms(day)
            frame = answer.frame.filter((open_ms >= day_ms) & (open_ms < day_ms + DAY_MS))
            in_span = (
                answer.covered_from_ms <= day_ms and day_ms + DAY_MS <= answer.covered_until_ms
            )
            if in_span and not frame.is_empty():
                on_outcome(DayOutcome(day, REST, frame))
            elif not in_span:
                on_outcome(DayOutcome(day, MISSING, frame, answer.failure))
            elif first_day_with_rows is None:
                on_outcome(DayOutcome(day, MISSING, frame, NO_CANDLES))
            elif day < first_day_with_rows:
                reason = BEFORE_FIRST.format(day=first_day_with_rows.isoformat())
                on_outcome(DayOutcome(day, MISSING, frame, reason))
            else:
                on_outcome(DayOutcome(day, MISSING, frame, NO_CANDLES_ON_DAY))
            day += timedelta(days=1)
        if answer.error is not None:
            raise answer.error


def _first_day(frame: pl.DataFrame) -> date | None:
    if frame.is_empty():
        return None
    return frame["open_time"].min().date()


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


def _worth_caching(outcome: DayOutcome) -> bool:
    """A complete day, whatever its row count; a missing day never."""
    return outcome.source == REST


def _gap_reason(outcome: DayOutcome) -> str:
    return outcome.reason or NO_CANDLES


def _to_ms(moment: datetime) -> int:
    return (moment - _EPOCH) // timedelta(milliseconds=1)


def _to_datetime(open_ms: int) -> datetime:
    return _EPOCH + timedelta(milliseconds=open_ms)
