"""Offline tests for the kline data layer: parameters, rows and the transport."""

from __future__ import annotations

import email.message
import io
import urllib.error
import urllib.request
import urllib.response
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import polars as pl
import pytest
from kucoin_stub import (
    FUTURES_1H,
    HEADERS,
    HOUR_MS,
    SPOT_1H,
    TODAY,
    fixture,
    fixture_rows,
    sequence,
    utc,
)

from app.data import http, loader, rest
from app.data.http import DownloadError, HttpResponse, RateLimitPacer, with_retries
from app.data.params import InvalidRequestError, make_request
from app.data.schema import (
    SCHEMA,
    MalformedDataError,
    frame_from_futures_rows,
    frame_from_spot_rows,
)


@pytest.mark.parametrize(
    ("symbol", "interval", "start", "end", "market"),
    [
        ("BTC-USDT", "1h", "2026-10-01", "2026-10-02", "um"),
        ("BTC-USDT", "1s", "2026-10-01", "2026-10-02", "spot"),
        ("BTC-USDT", "1w", "2026-10-01", "2026-10-02", "spot"),
        ("XBTUSDTM", "6h", "2026-10-01", "2026-10-02", "futures"),
        ("XBTUSDM", "1h", "2026-10-01", "2026-10-02", "futures"),
        ("XBTMZ25", "1h", "2026-10-01", "2026-10-02", "futures"),
        ("BTC-USDT", "1h", "2026-10-01", "2026-10-02", "futures"),
        ("BTC/USDT", "1h", "2026-10-01", "2026-10-02", "spot"),
        ("../etc", "1h", "2026-10-01", "2026-10-02", "spot"),
        ("B", "1h", "2026-10-01", "2026-10-02", "spot"),
        ("BTC-USDT", "1h", "2026-10-03", "2026-10-02", "spot"),
        ("BTC-USDT", "1h", "2026-10-01", "2026-10-04", "spot"),
        ("BTC-USDT", "1h", "01/10/2026", "2026-10-02", "spot"),
    ],
)
def test_make_request_refuses_invalid_parameters(
    symbol: str, interval: str, start: str, end: str, market: str
) -> None:
    with pytest.raises(InvalidRequestError):
        make_request(symbol, interval, start, end, market, TODAY)


def test_make_request_normalises_valid_parameters() -> None:
    request = make_request("btc-usdt", "6h", "2026-09-30", date(2026, 10, 2), "spot", TODAY)
    assert request.symbol == "BTC-USDT"
    assert request.days() == [date(2026, 9, 30), date(2026, 10, 1), date(2026, 10, 2)]
    assert request.interval_ms == 6 * HOUR_MS
    assert make_request("xbtusdtm", "1m", "2026-10-01", "2026-10-01", "futures", TODAY).symbol == (
        "XBTUSDTM"
    )


def assert_rows_map(frame: pl.DataFrame, rows: list[list[object]], order: str) -> None:
    assert frame.schema == pl.Schema(SCHEMA)
    assert frame.height == len(rows)
    for row, candle in zip(rows, frame.iter_rows(named=True)):
        prices = [float(value) for value in row[1:5]]  # type: ignore[arg-type]
        assert candle["high"] == max(prices) and candle["low"] == min(prices)
        assert [candle[name] for name in order.split()] == prices
        assert candle["close_time"] - candle["open_time"] == timedelta(milliseconds=HOUR_MS - 1)
        assert candle["quote_volume"] == float(row[6])  # type: ignore[arg-type]


def test_spot_rows_map_to_columns() -> None:
    rows = fixture_rows(SPOT_1H)
    frame = frame_from_spot_rows(rows, HOUR_MS)
    assert_rows_map(frame, rows, "open close high low")
    assert frame["open_time"][-1] == utc(2026, 10, 1)


def test_futures_rows_map_to_columns() -> None:
    rows = fixture_rows(FUTURES_1H)
    frame = frame_from_futures_rows(rows, HOUR_MS)
    assert_rows_map(frame, rows, "open high low close")
    assert frame["open_time"][0] == utc(2026, 10, 1)


SPOT_ROW = ["1790812800", "1", "1", "1", "1", "1", "1"]
FUTURES_ROW = [1790812800000, 1, 1, 1, 1, 1, 1]


@pytest.mark.parametrize(
    ("parse", "rows"),
    [
        (frame_from_spot_rows, {"rows": []}),
        (frame_from_spot_rows, [SPOT_ROW[:6]]),
        (frame_from_spot_rows, [[*SPOT_ROW, "1"]]),
        (frame_from_spot_rows, [[1790812800, *SPOT_ROW[1:]]]),
        (frame_from_spot_rows, [[*SPOT_ROW[:4], "nan", *SPOT_ROW[5:]]]),
        (frame_from_spot_rows, [[*SPOT_ROW[:4], "abc", *SPOT_ROW[5:]]]),
        (frame_from_spot_rows, [["1790812800.5", *SPOT_ROW[1:]]]),
        (frame_from_spot_rows, [[str(2**62), *SPOT_ROW[1:]]]),
        (frame_from_futures_rows, "[]"),
        (frame_from_futures_rows, [FUTURES_ROW[:6]]),
        (frame_from_futures_rows, [[*FUTURES_ROW[:3], True, *FUTURES_ROW[4:]]]),
        (frame_from_futures_rows, [[*FUTURES_ROW[:3], "1", *FUTURES_ROW[4:]]]),
        (frame_from_futures_rows, [[*FUTURES_ROW[:3], float("inf"), *FUTURES_ROW[4:]]]),
        (frame_from_futures_rows, [[1790812800000.5, *FUTURES_ROW[1:]]]),
        (frame_from_futures_rows, [[2**70, *FUTURES_ROW[1:]]]),
        (frame_from_futures_rows, [None]),
    ],
)
def test_malformed_rows_are_rejected(parse: Callable[[object, int], object], rows: object) -> None:
    with pytest.raises(MalformedDataError):
        parse(rows, HOUR_MS)


def test_retries_on_429_and_5xx_but_not_404(sleeps: list[float]) -> None:
    fetch, calls = sequence(
        HttpResponse(429), HttpResponse(500), HttpResponse(503), HttpResponse(200)
    )
    assert with_retries(fetch)("https://x/a").status == 200
    assert len(calls) == 4
    assert sleeps == [1.25, 2.25, 4.25]

    fetch, calls = sequence(HttpResponse(404), HttpResponse(418))
    assert with_retries(fetch)("https://x/b").status == 404
    assert with_retries(fetch)("https://x/c").status == 418
    assert len(calls) == 2
    assert sleeps == [1.25, 2.25, 4.25]


def test_retries_stop_after_three(sleeps: list[float]) -> None:
    fetch, calls = sequence(TimeoutError("read"), OSError("reset"), *[HttpResponse(502)] * 2)
    with pytest.raises(DownloadError, match="after 3 retries"):
        with_retries(fetch)("https://x/a")
    assert len(calls) == 4
    assert sleeps == [1.25, 2.25, 4.25]


def test_retry_after_is_honoured_and_a_long_one_stops(sleeps: list[float]) -> None:
    fetch, _ = sequence(HttpResponse(429, {"retry-after": "7"}), HttpResponse(200))
    assert with_retries(fetch)("https://x/a").status == 200
    assert sleeps == [7.0]

    fetch, calls = sequence(HttpResponse(429, {"Retry-After": "120"}))
    with pytest.raises(DownloadError, match="Retry-After 120 s"):
        with_retries(fetch)("https://x/b")
    assert len(calls) == 1
    assert sleeps == [7.0]


def test_429_without_retry_after_waits_for_the_reset(sleeps: list[float]) -> None:
    for reset in ("20000", "90000"):
        fetch, _ = sequence(HttpResponse(429, {"gw-ratelimit-reset": reset}), HttpResponse(200))
        assert with_retries(fetch)("https://x/a").status == 200
    assert sleeps == [20.0, 60.0]


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({}, [1.0]),
        ({"gw-ratelimit-remaining": "1997"}, [1.0]),
        ({"gw-ratelimit-remaining": "n/a", "gw-ratelimit-reset": "20000"}, [1.0]),
        ({"gw-ratelimit-remaining": "5", "gw-ratelimit-reset": "soon"}, [1.0]),
        (HEADERS, []),
        ({"gw-ratelimit-remaining": "100", "gw-ratelimit-reset": "20000"}, []),
        ({"GW-RateLimit-Remaining": "99", "gw-ratelimit-reset": "20000"}, [20.0]),
        ({"gw-ratelimit-remaining": "5", "gw-ratelimit-reset": "90000"}, [60.0]),
        ({"gw-ratelimit-remaining": "5", "gw-ratelimit-reset": "-5"}, [0.0]),
    ],
)
def test_rate_limit_pacer(
    sleeps: list[float], headers: dict[str, str], expected: list[float]
) -> None:
    pacer = RateLimitPacer()
    pacer.wait()
    pacer.record(HttpResponse(200, headers))
    pacer.wait()
    assert sleeps == expected


def test_http_error_with_kucoin_body_is_a_refusal() -> None:
    def failure(status: int, body: bytes) -> str | None:
        response = HttpResponse(status, {}, body)
        return rest.parse_answer(response, frame_from_futures_rows, HOUR_MS)[1]

    assert failure(400, fixture("futures-from-in-seconds.json")) == (
        "KuCoin refused (HTTP 400, code 300000): Parameter 'from' must be milliseconds"
    )
    assert failure(451, b"<html>") == "KuCoin refused (HTTP 451)"
    assert failure(200, b"<html>") == "unexpected KuCoin response"
    assert failure(200, b'[{"code": "200000"}]') == "unexpected KuCoin response"
    assert failure(200, b'{"code": "200000", "data": {}}') == "unexpected KuCoin response"
    assert failure(200, b'{"code": 200000, "data": []}') is None
    oversized = b'{"code": "200000", "data": []}' + b" " * http.MAX_BODY_BYTES
    assert failure(200, oversized) == "unexpected KuCoin response"


def test_no_module_names_a_binance_host() -> None:
    package = Path(loader.__file__).parents[1]
    for path in package.rglob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        assert "binance.com" not in text and "binance.vision" not in text, path


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
@pytest.mark.parametrize("target", ["http://elsewhere.example/x", "https://elsewhere.example/x"])
def test_redirect_is_not_followed(
    monkeypatch: pytest.MonkeyPatch, status: int, target: str
) -> None:
    opened: list[str] = []

    def answer_redirect(self: object, request: urllib.request.Request) -> object:
        opened.append(request.full_url)
        headers = email.message.Message()
        headers["Location"] = target
        response = urllib.response.addinfourl(io.BytesIO(b""), headers, request.full_url, status)
        response.msg = "Redirect"
        return response

    monkeypatch.setattr(http._HTTPSHandler, "https_open", answer_redirect)
    monkeypatch.setattr(urllib.request.HTTPHandler, "http_open", answer_redirect)
    origin = f"{rest.SPOT_URL}?symbol=BTC-USDT&type=1hour&startAt=1790812800&endAt=1790899200"
    assert http.urllib_fetch(origin).status == status
    assert opened == [origin]


@pytest.mark.parametrize("url", ["http://127.0.0.1:9/x", "ftp://127.0.0.1/x", "file:///etc/hosts"])
def test_only_https_urls_are_opened(url: str) -> None:
    with pytest.raises(urllib.error.URLError, match="unknown url type"):
        http.urllib_fetch(url)


@pytest.mark.parametrize(
    "moment",
    [
        datetime(2026, 10, 1),  # noqa: DTZ001
        datetime(2026, 10, 1, 23, tzinfo=timezone(timedelta(hours=-3))),
    ],
)
@pytest.mark.parametrize(
    "dates",
    [
        lambda moment: (moment, date(2026, 10, 2)),
        lambda moment: (date(2026, 9, 30), moment),
        lambda moment: (moment, moment),
    ],
)
def test_datetime_bound_is_refused_not_a_type_error(
    moment: datetime, dates: Callable[[datetime], tuple[date, date]]
) -> None:
    start, end = dates(moment)
    with pytest.raises(InvalidRequestError, match="not a datetime"):
        make_request("BTC-USDT", "1h", start, end, "spot", TODAY)
