"""The public Binance REST klines endpoints, used to fill the days Vision does not have."""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import urlencode

import polars as pl

from app.data.http import Fetch, WeightPacer
from app.data.params import KlineRequest
from app.data.schema import MalformedDataError, empty_frame, frame_from_rest


@dataclass(frozen=True)
class Endpoint:
    url: str
    page_size: int
    weight_limit: int


ENDPOINTS = {
    "spot": Endpoint("https://data-api.binance.vision/api/v3/klines", 1000, 6000),
    "um": Endpoint("https://fapi.binance.com/fapi/v1/klines", 1500, 2400),
}
UNEXPECTED_RESPONSE = "unexpected REST response"


@dataclass(frozen=True)
class RestRange:
    """The candles REST gave for a range, and why it stopped early, if it did."""

    frame: pl.DataFrame
    failure: str | None = None


def pacer_for(market: str) -> WeightPacer:
    return WeightPacer(ENDPOINTS[market].weight_limit)


def page_url(request: KlineRequest, start_ms: int, end_ms: int) -> str:
    endpoint = ENDPOINTS[request.market]
    query = urlencode(
        {
            "symbol": request.symbol,
            "interval": request.interval,
            "startTime": start_ms,
            "endTime": end_ms,
            "limit": endpoint.page_size,
        }
    )
    return f"{endpoint.url}?{query}"


def fetch_range(
    fetch: Fetch, pacer: WeightPacer, request: KlineRequest, start_ms: int, end_ms: int
) -> RestRange:
    """Page through [start_ms, end_ms) one call at a time; an empty page ends the range."""
    frames = []
    failure = None
    next_ms = start_ms
    while next_ms < end_ms:
        pacer.wait()
        response = fetch(page_url(request, next_ms, end_ms - 1))
        pacer.record(response)
        if response.status != 200:
            failure = f"REST refused (HTTP {response.status})"
            break
        try:
            page = frame_from_rest(json.loads(response.body))
        except (ValueError, RecursionError, MalformedDataError):
            failure = UNEXPECTED_RESPONSE
            break
        if page.is_empty():
            break
        last_open_ms = page["open_time"].dt.epoch("ms").max()
        if last_open_ms < next_ms:
            failure = UNEXPECTED_RESPONSE
            break
        frames.append(page)
        next_ms = last_open_ms + request.interval_ms
    return RestRange(pl.concat(frames) if frames else empty_frame(), failure)
