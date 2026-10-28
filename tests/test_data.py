"""Offline tests for the kline data layer (app.data): every fetch goes through a stub."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import polars as pl
import pytest

from app.data import http, rest, vision
from app.data.http import BinanceBanError, DownloadError, HttpResponse, WeightPacer, with_retries
from app.data.params import InvalidRequestError, KlineRequest, make_request
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


def zip_of(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buffer.getvalue()


class Binance:
    """A stub Fetch: Vision days built from fixtures, REST pages served from JSON fixtures.

    Unknown URLs answer 404. Every URL asked for is recorded in `calls`.
    """

    def __init__(self, rest_headers: dict[str, str] | None = None) -> None:
        self.responses: dict[str, HttpResponse] = {}
        self.rest_rows: list[list[object]] = []
        self.rest_headers = rest_headers if rest_headers is not None else {WEIGHT: "10"}
        self.calls: list[str] = []

    def vision(self, market: str, day: str, csv: str, *, checksum: str | None = None) -> None:
        request = make_request("BTCUSDT", "1h", day, day, market, TODAY)
        url = vision.day_url(request, request.start)
        body = zip_of({f"BTCUSDT-1h-{day}.csv": fixture(csv)})
        digest = checksum or hashlib.sha256(body).hexdigest()
        self.responses[url] = HttpResponse(200, {}, body)
        self.responses[f"{url}.CHECKSUM"] = HttpResponse(200, {}, f"{digest}  x.zip\n".encode())

    def rest(self, name: str) -> None:
        self.rest_rows.extend(json.loads(fixture(name)))

    def rest_calls(self) -> list[str]:
        return [url for url in self.calls if "/klines?" in url]

    def __call__(self, url: str) -> HttpResponse:
        self.calls.append(url)
        if "/klines?" in url:
            query = {key: values[0] for key, values in parse_qs(urlsplit(url).query).items()}
            start, end = int(query["startTime"]), int(query["endTime"])
            rows = [row for row in self.rest_rows if start <= row[0] <= end]
            body = json.dumps(rows[: int(query["limit"])]).encode()
            return HttpResponse(200, self.rest_headers, body)
        return self.responses.get(url, HttpResponse(404))


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


def spot_request(day: str = "2024-12-31") -> KlineRequest:
    return make_request("BTCUSDT", "1h", day, day, "spot", TODAY)


def test_vision_day_checks_the_checksum() -> None:
    binance = Binance()
    binance.vision("spot", "2024-12-31", "spot-BTCUSDT-1h-2024-12-31.csv")
    request = spot_request()
    good = vision.fetch_day(binance, request, request.start)
    assert good.reason is None and good.frame is not None and good.frame.height == 24
    url = "https://data.binance.vision/data/spot/daily/klines/BTCUSDT/1h/BTCUSDT-1h-2024-12-31.zip"
    assert binance.calls == [url, f"{url}.CHECKSUM"]

    binance.vision("spot", "2024-12-31", "spot-BTCUSDT-1h-2024-12-31.csv", checksum="0" * 64)
    assert vision.fetch_day(binance, request, request.start).reason == "checksum mismatch"

    binance.responses.pop(binance.calls[1])
    assert vision.fetch_day(binance, request, request.start).reason == "checksum unavailable"


def test_vision_reads_only_the_expected_member(monkeypatch: pytest.MonkeyPatch) -> None:
    data = fixture("spot-BTCUSDT-1h-2024-12-31.csv")
    body = zip_of({"../../evil.csv": b"x", "BTCUSDT-1h-2024-12-31.csv": data})
    assert vision._extract_csv(body, "BTCUSDT-1h-2024-12-31.csv") == data
    with pytest.raises(MalformedDataError):
        vision._extract_csv(zip_of({"other.csv": data}), "BTCUSDT-1h-2024-12-31.csv")
    with pytest.raises(MalformedDataError):
        vision._extract_csv(b"not a zip", "BTCUSDT-1h-2024-12-31.csv")
    monkeypatch.setattr(vision, "MAX_CSV_BYTES", len(data) - 1)
    with pytest.raises(MalformedDataError, match="size bound"):
        vision._extract_csv(body, "BTCUSDT-1h-2024-12-31.csv")


DAY_MS = 86_400_000
DEC_31_MS = 1_735_603_200_000


@pytest.fixture
def small_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    spot = rest.ENDPOINTS["spot"]
    monkeypatch.setitem(rest.ENDPOINTS, "spot", rest.Endpoint(spot.url, 10, spot.weight_limit))


def fetch_dec_31(fetch: http.Fetch, days: int = 1) -> rest.RestRange:
    pacer = rest.pacer_for("spot")
    return rest.fetch_range(fetch, pacer, spot_request(), DEC_31_MS, DEC_31_MS + days * DAY_MS)


def test_rest_pages_until_an_empty_page(sleeps: list[float], small_pages: None) -> None:
    binance = Binance()
    binance.rest("rest-spot-BTCUSDT-1h-2024-12-31.json")
    result = fetch_dec_31(binance, days=2)
    assert result.failure is None
    assert result.frame.height == 24
    assert len(binance.rest_calls()) == 4
    end_ms = DEC_31_MS + 2 * DAY_MS - 1
    assert binance.rest_calls()[0] == (
        "https://data-api.binance.vision/api/v3/klines?symbol=BTCUSDT&interval=1h"
        f"&startTime={DEC_31_MS}&endTime={end_ms}&limit=10"
    )
    assert sleeps == []


@pytest.mark.parametrize(
    ("answer", "failure"),
    [
        (HttpResponse(451, {WEIGHT: "1"}, b"{}"), "REST refused (HTTP 451)"),
        (HttpResponse(400, {WEIGHT: "1"}, b"{}"), "REST refused (HTTP 400)"),
        (HttpResponse(200, {WEIGHT: "1"}, b"{}"), "unexpected REST response"),
        (HttpResponse(200, {WEIGHT: "1"}, b"[[1, 2"), "unexpected REST response"),
    ],
)
def test_rest_failures_end_the_range(answer: HttpResponse, failure: str) -> None:
    fetch, calls = sequence(answer)
    result = fetch_dec_31(fetch)
    assert result.failure == failure
    assert result.frame.is_empty()
    assert len(calls) == 1


def test_rest_waits_when_weight_header_is_missing(sleeps: list[float], small_pages: None) -> None:
    binance = Binance(rest_headers={})
    binance.rest("rest-spot-BTCUSDT-1h-2024-12-31.json")
    assert fetch_dec_31(binance).frame.height == 24
    assert len(binance.rest_calls()) == 3
    assert sleeps == [1.0, 1.0]


def test_rest_pauses_when_weight_nears_limit(sleeps: list[float], small_pages: None) -> None:
    binance = Binance(rest_headers={WEIGHT: "4800"})
    binance.rest("rest-spot-BTCUSDT-1h-2024-12-31.json")
    assert fetch_dec_31(binance).frame.height == 24
    assert sleeps == [15.0, 15.0]
