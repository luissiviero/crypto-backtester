"""Offline tests for the kline data layer (app.data): every fetch goes through a stub."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import polars as pl
import pytest

from app.data import http
from app.data.http import BinanceBanError, DownloadError, HttpResponse, WeightPacer, with_retries
from app.data.params import InvalidRequestError, make_request
from app.data.schema import SCHEMA, MalformedDataError, frame_from_csv, frame_from_rest

FIXTURES = Path(__file__).parent / "fixtures" / "binance"
TODAY = date(2025, 1, 2)
WEIGHT = "X-MBX-USED-WEIGHT-1M"


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Record every sleep of the transport instead of waiting; jitter fixed at 0.25 s."""
    recorded: list[float] = []
    monkeypatch.setattr(http, "sleep", recorded.append)
    monkeypatch.setattr(http, "jitter", lambda: 0.25)
    monkeypatch.setattr(http, "wall_clock", lambda: 1_735_689_645.0)  # 45 s into a minute
    return recorded


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


@pytest.mark.parametrize(
    ("symbol", "interval", "start", "end", "market"),
    [
        ("BTC/USDT", "1h", "2024-01-01", "2024-01-02", "spot"),
        ("../etc", "1h", "2024-01-01", "2024-01-02", "spot"),
        ("B", "1h", "2024-01-01", "2024-01-02", "spot"),
        ("BTCUSDT", "1M", "2024-01-01", "2024-01-02", "spot"),
        ("BTCUSDT", "1s", "2024-01-01", "2024-01-02", "um"),
        ("BTCUSDT", "1h", "2024-01-01", "2024-01-02", "coinm"),
        ("BTCUSDT", "1h", "2024-01-03", "2024-01-02", "spot"),
        ("BTCUSDT", "1h", "2024-01-01", "2025-01-03", "spot"),
        ("BTCUSDT", "1h", "01/01/2024", "2024-01-02", "spot"),
    ],
)
def test_make_request_refuses_invalid_parameters(
    symbol: str, interval: str, start: str, end: str, market: str
) -> None:
    with pytest.raises(InvalidRequestError):
        make_request(symbol, interval, start, end, market, TODAY)


def test_make_request_normalises_valid_parameters() -> None:
    request = make_request("btcusdt", "1s", "2024-12-31", date(2025, 1, 2), "spot", TODAY)
    assert request.symbol == "BTCUSDT"
    assert request.days() == [date(2024, 12, 31), date(2025, 1, 1), date(2025, 1, 2)]
    assert request.interval_ms == 1_000


def test_microsecond_and_millisecond_files_normalise_identically() -> None:
    spot = frame_from_csv(fixture("spot-BTCUSDT-1h-2025-01-01.csv"))
    futures = frame_from_csv(fixture("um-BTCUSDT-1h-2025-01-01.csv"))
    assert spot.schema == pl.Schema(SCHEMA)
    assert spot.equals(futures)
    assert spot.height == 24
    assert spot["open_time"][0] == datetime(2025, 1, 1, tzinfo=timezone.utc)
    assert spot["close_time"][0] == datetime(2025, 1, 1, 0, 59, 59, 999000, tzinfo=timezone.utc)


def test_rest_rows_normalise_like_the_vision_file() -> None:
    vision = frame_from_csv(fixture("spot-BTCUSDT-1h-2024-12-31.csv"))
    rest = frame_from_rest(json.loads(fixture("rest-spot-BTCUSDT-1h-2024-12-31.json")))
    assert rest.equals(vision)


@pytest.mark.parametrize(
    "body",
    [
        b"1735689600000,1,1,1,1,1,1735693199999,1,1,1,1\n",
        b"1735689600000,1,1,1,abc,1,1735693199999,1,1,1,1,0\n",
        b"1735689600000,1,1,1,nan,1,1735693199999,1,1,1,1,0\n",
        (
            b"1735689600000,1,1,1,1,1,1735693199999,1,1,1,1,0\n"
            b"1735693200000000,1,1,1,1,1,1,1,1,1,1,0\n"
        ),
        "1735689600000,1,1,1,1,1,1735693199999,1,1,1,1,\u00e9\n".encode(),
    ],
)
def test_malformed_csv_rows_are_rejected(body: bytes) -> None:
    with pytest.raises(MalformedDataError):
        frame_from_csv(body)


@pytest.mark.parametrize(
    "body",
    [{"code": -1121}, [[1, "1"]], [["1", "1", "1", "1", "1", "1", 2, "1", 3, "1", "1"]]],
)
def test_malformed_rest_bodies_are_rejected(body: object) -> None:
    with pytest.raises(MalformedDataError):
        frame_from_rest(body)


def test_retries_on_429_and_5xx_but_not_404(sleeps: list[float]) -> None:
    fetch, calls = sequence(
        HttpResponse(429), HttpResponse(500), HttpResponse(503), HttpResponse(200)
    )
    assert with_retries(fetch)("https://x/a").status == 200
    assert len(calls) == 4
    assert sleeps == [1.25, 2.25, 4.25]

    fetch, calls = sequence(HttpResponse(404))
    assert with_retries(fetch)("https://x/b").status == 404
    assert len(calls) == 1
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


def test_http_418_raises_ban_error(sleeps: list[float]) -> None:
    fetch, calls = sequence(HttpResponse(418))
    with pytest.raises(BinanceBanError, match="418"):
        with_retries(fetch)("https://x/a")
    assert len(calls) == 1
    assert sleeps == []


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({}, [1.0]),
        ({"x-mbx-used-weight-1m": "n/a"}, [1.0]),
        ({WEIGHT: "1919"}, []),
        ({WEIGHT: "1920"}, [15.0]),
    ],
)
def test_weight_pacer(sleeps: list[float], headers: dict[str, str], expected: list[float]) -> None:
    pacer = WeightPacer(2400)
    pacer.wait()
    pacer.record(HttpResponse(200, headers))
    pacer.wait()
    assert sleeps == expected
