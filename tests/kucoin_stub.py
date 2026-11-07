"""Shared offline stubs for the data-layer tests: fixtures, a sequence Fetch, a KuCoin stub."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from app.data import http, rest
from app.data.http import HttpResponse

FIXTURES = Path(__file__).parent / "fixtures" / "kucoin"
TODAY = date(2026, 10, 3)
NOW = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)
HEADERS = {"gw-ratelimit-remaining": "1997", "gw-ratelimit-reset": "29999"}
HOUR_MS = 3_600_000
MINUTE_MS = 60_000
SPOT_1H = "spot-BTC-USDT-1hour-2026-10-01.json"
FUTURES_1H = "futures-XBTUSDTM-60-2026-10-01.json"
FUTURES_1M = "futures-XBTUSDTM-1-2026-10-01.json"


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def fixture_rows(name: str) -> list[list[object]]:
    return json.loads(fixture(name))["data"]


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


def ms(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


def cached_days(root: Path, market: str, symbol: str, interval: str, days: list[str]) -> Path:
    """Fake day files (100 bytes each) in the cache layout."""
    directory = root / "kucoin" / market / symbol / interval
    directory.mkdir(parents=True, exist_ok=True)
    for day in days:
        (directory / f"{symbol}-{interval}-{day}.parquet").write_bytes(b"x" * 100)
    return directory


def sequence(*answers: HttpResponse | Exception) -> tuple[http.Fetch, list[str]]:
    """A Fetch that gives the answers in turn and records each URL."""
    calls: list[str] = []
    pending = list(answers)

    def fetch(url: str) -> HttpResponse:
        calls.append(url)
        answer = pending.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    return fetch, calls


def _prices(index: int) -> tuple[float, float, float, float]:
    """Open, close, high, low of a synthetic candle; high the largest, low the smallest."""
    open_price = 80_000.0 + index % 97
    close_price = open_price + (index % 7) - 3
    return (
        open_price,
        close_price,
        max(open_price, close_price) + 5,
        min(open_price, close_price) - 5,
    )


class KuCoin:
    """A stub Fetch for both KuCoin klines endpoints, honouring their measured window rules.

    Spot serves `[startAt, endAt)` newest first and keeps the newest `spot_page` rows; futures
    serves `[from, to]` oldest first and keeps the oldest `futures_page` rows. A URL that
    contains a `refuse` match gets that response instead; any other URL answers 404. Every
    URL asked for is recorded in `calls`.
    """

    def __init__(
        self, headers: dict[str, str] | None = None, spot_page: int = 1500, futures_page: int = 200
    ) -> None:
        self.headers = HEADERS if headers is None else headers
        self.spot_page = spot_page
        self.futures_page = futures_page
        self.spot_rows: list[list[object]] = []
        self.futures_rows: list[list[object]] = []
        self.refusals: list[tuple[str, HttpResponse]] = []
        self.calls: list[str] = []

    def add_spot(self, name: str) -> None:
        self.spot_rows.extend(fixture_rows(name))

    def add_futures(self, name: str) -> None:
        self.futures_rows.extend(fixture_rows(name))

    def add_spot_synthetic(self, start: datetime, count: int, interval_ms: int) -> None:
        for index in range(count):
            open_price, close_price, high, low = _prices(index)
            seconds = (ms(start) + index * interval_ms) // 1000
            values = (open_price, close_price, high, low, 1.5, 1.5 * close_price)
            self.spot_rows.append([str(seconds), *(str(value) for value in values)])

    def add_futures_synthetic(self, start: datetime, count: int, interval_ms: int) -> None:
        for index in range(count):
            open_price, close_price, high, low = _prices(index)
            open_ms = ms(start) + index * interval_ms
            self.futures_rows.append(
                [open_ms, open_price, high, low, close_price, 120, 120 * close_price / 1000]
            )

    def refuse(self, match: str, response: HttpResponse) -> None:
        self.refusals.append((match, response))

    def __call__(self, url: str) -> HttpResponse:
        self.calls.append(url)
        for match, response in self.refusals:
            if match in url:
                return response
        parts = urlsplit(url)
        base = f"{parts.scheme}://{parts.netloc}{parts.path}"
        query = {key: values[0] for key, values in parse_qs(parts.query).items()}
        if base == rest.SPOT_URL:
            start, end = int(query["startAt"]), int(query["endAt"])
            rows = [row for row in self.spot_rows if start <= int(row[0]) < end]
            rows.sort(key=lambda row: -int(row[0]))
            rows = rows[: self.spot_page]
        elif base == rest.FUTURES_URL:
            start, end = int(query["from"]), int(query["to"])
            rows = sorted(row for row in self.futures_rows if start <= row[0] <= end)
            rows = rows[: self.futures_page]
        else:
            return HttpResponse(404)
        body = json.dumps({"code": rest.SUCCESS_CODE, "data": rows}).encode()
        return HttpResponse(200, self.headers, body)
