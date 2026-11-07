"""KuCoin's public klines endpoints: spot and USDT-margined futures, paged one call at a time."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlencode

import polars as pl

from app.data.http import MAX_BODY_BYTES, DownloadError, Fetch, HttpResponse, RateLimitPacer
from app.data.params import FUTURES_GRANULARITY, SPOT_TYPES, KlineRequest
from app.data.schema import (
    MalformedDataError,
    empty_frame,
    frame_from_futures_rows,
    frame_from_spot_rows,
)

SPOT_URL = "https://api.kucoin.com/api/v1/market/candles"
FUTURES_URL = "https://api-futures.kucoin.com/api/v1/kline/query"
SUCCESS_CODE = "200000"
UNEXPECTED_RESPONSE = "unexpected KuCoin response"
MAX_MESSAGE = 200
MAX_CODE = 20

ParseRows = Callable[[object, int], pl.DataFrame]
_OPEN_MS = pl.col("open_time").dt.epoch("ms")


@dataclass(frozen=True)
class RestRange:
    """The candles KuCoin gave for a range and the span its answered pages vouch for.

    `[covered_from_ms, covered_until_ms)` is the whole range unless paging stopped early, with
    `failure` saying why; `error` is the DownloadError that stopped it, if one did.
    """

    frame: pl.DataFrame
    failure: str | None
    covered_from_ms: int
    covered_until_ms: int
    error: DownloadError | None = None


def spot_url(request: KlineRequest, start_ms: int, end_ms: int) -> str:
    query = urlencode(
        {
            "symbol": request.symbol,
            "type": SPOT_TYPES[request.interval],
            "startAt": start_ms // 1000,
            "endAt": end_ms // 1000,
        }
    )
    return f"{SPOT_URL}?{query}"


def futures_url(request: KlineRequest, start_ms: int, end_ms: int) -> str:
    query = urlencode(
        {
            "symbol": request.symbol,
            "granularity": FUTURES_GRANULARITY[request.interval],
            "from": start_ms,
            "to": end_ms - 1,
        }
    )
    return f"{FUTURES_URL}?{query}"


def parse_answer(
    response: HttpResponse, parse_rows: ParseRows, interval_ms: int
) -> tuple[pl.DataFrame | None, str | None]:
    """The page's rows, or None and the reason the answer is not usable."""
    if len(response.body) > MAX_BODY_BYTES:
        return None, UNEXPECTED_RESPONSE
    try:
        payload = json.loads(response.body)
    except (ValueError, RecursionError):
        payload = None
    if not isinstance(payload, dict):
        if response.status == 200:
            return None, UNEXPECTED_RESPONSE
        return None, f"KuCoin refused (HTTP {response.status})"
    code = str(payload.get("code", ""))
    if code != SUCCESS_CODE or response.status != 200:
        message = _clean(str(payload.get("msg", "")), MAX_MESSAGE)
        return None, (
            f"KuCoin refused (HTTP {response.status}, code {_clean(code, MAX_CODE)}): {message}"
        )
    try:
        return parse_rows(payload.get("data"), interval_ms), None
    except MalformedDataError:
        return None, UNEXPECTED_RESPONSE


def _clean(text: str, limit: int) -> str:
    """Untrusted text for a reason: printable characters only, cut to `limit`."""
    return "".join(character for character in text if character.isprintable())[:limit]


def fetch_range(
    fetch: Fetch, pacer: RateLimitPacer, request: KlineRequest, start_ms: int, end_ms: int
) -> RestRange:
    """Page through [start_ms, end_ms) from the rows returned, never from a page size."""
    if request.market == "futures":
        return _fetch_futures(fetch, pacer, request, start_ms, end_ms)
    return _fetch_spot(fetch, pacer, request, start_ms, end_ms)


def _page(
    fetch: Fetch, pacer: RateLimitPacer, url: str, parse_rows: ParseRows, interval_ms: int
) -> tuple[pl.DataFrame | None, str | None, DownloadError | None]:
    pacer.wait()
    try:
        response = fetch(url)
    except DownloadError as error:
        return None, str(error), error
    pacer.record(response)
    page, failure = parse_answer(response, parse_rows, interval_ms)
    return page, failure, None


def _fetch_spot(
    fetch: Fetch, pacer: RateLimitPacer, request: KlineRequest, start_ms: int, end_ms: int
) -> RestRange:
    """Backwards: KuCoin keeps the newest rows, so each window ends at the oldest one returned."""
    frames = []
    window_end = end_ms
    while window_end > start_ms:
        url = spot_url(request, start_ms, window_end)
        page, failure, error = _page(fetch, pacer, url, frame_from_spot_rows, request.interval_ms)
        if page is None:
            return _range(frames, failure, window_end, end_ms, error)
        page = page.filter((_OPEN_MS >= start_ms) & (_OPEN_MS < window_end))
        if page.is_empty():
            break
        frames.append(page)
        window_end = page.select(_OPEN_MS.min()).item()
    return _range(frames, None, start_ms, end_ms)


def _fetch_futures(
    fetch: Fetch, pacer: RateLimitPacer, request: KlineRequest, start_ms: int, end_ms: int
) -> RestRange:
    """Forwards: KuCoin keeps the oldest rows, so each window starts after the newest one."""
    frames = []
    window_start = start_ms
    while window_start < end_ms:
        url = futures_url(request, window_start, end_ms)
        page, failure, error = _page(
            fetch, pacer, url, frame_from_futures_rows, request.interval_ms
        )
        if page is None:
            return _range(frames, failure, start_ms, window_start, error)
        # The window's end row (open at `to`, or later) belongs to the next range.
        page = page.filter((_OPEN_MS >= window_start) & (_OPEN_MS < end_ms))
        if page.is_empty():
            break
        frames.append(page)
        window_start = page.select(_OPEN_MS.max()).item() + request.interval_ms
    return _range(frames, None, start_ms, end_ms)


def _range(
    frames: list[pl.DataFrame],
    failure: str | None,
    covered_from_ms: int,
    covered_until_ms: int,
    error: DownloadError | None = None,
) -> RestRange:
    frame = pl.concat(frames) if frames else empty_frame()
    return RestRange(frame, failure, covered_from_ms, covered_until_ms, error)
