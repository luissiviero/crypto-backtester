"""Offline tests for the kline data layer (app.data): every fetch goes through a stub."""

from __future__ import annotations

import hashlib
import io
import json
import time
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import polars as pl
import pytest

from app.data import Gap, KlineGapError, cache, http, load_klines, loader, rest, vision
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


def test_cache_root_priority(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cache.sys, "platform", "linux")
    monkeypatch.setenv(cache.ENV_VAR, str(tmp_path / "env"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    assert cache.cache_root(tmp_path / "arg") == tmp_path / "arg"
    assert cache.cache_root() == tmp_path / "env"
    monkeypatch.delenv(cache.ENV_VAR)
    assert cache.cache_root() == tmp_path / "xdg" / "crypto-backtester"
    monkeypatch.setenv("XDG_CACHE_HOME", "relative")
    assert cache.cache_root() == Path.home() / ".cache" / "crypto-backtester"
    monkeypatch.setattr(cache.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    assert cache.cache_root() == tmp_path / "local" / "crypto-backtester" / "Cache"


def test_day_path_layout_and_escape(tmp_path: Path) -> None:
    request = spot_request()
    path = cache.day_path(tmp_path, request, request.start)
    expected = tmp_path / "binance-vision/spot/BTCUSDT/1h/BTCUSDT-1h-2024-12-31.parquet"
    assert path == expected.resolve()
    forged = KlineRequest("../../..", "1h", "spot", request.start, request.end)
    with pytest.raises(cache.CachePathError):
        cache.day_path(tmp_path, forged, request.start)


def test_atomic_write_leaves_only_the_day_file(tmp_path: Path) -> None:
    frame = frame_from_csv(fixture("spot-BTCUSDT-1h-2024-12-31.csv"))
    path = cache.day_path(tmp_path, spot_request(), date(2024, 12, 31))
    cache.write_day(path, frame)
    assert [file.name for file in path.parent.iterdir()] == [path.name]
    read = cache.read_day(path)
    assert read is not None and read.equals(frame)
    path.write_bytes(b"not parquet")
    assert cache.read_day(path) is None


def cached_days(root: Path, market: str, symbol: str, interval: str, days: list[str]) -> Path:
    directory = root / "binance-vision" / market / symbol / interval
    directory.mkdir(parents=True, exist_ok=True)
    for day in days:
        (directory / f"{symbol}-{interval}-{day}.parquet").write_bytes(b"x" * 100)
    return directory


def test_cache_info_and_clear_touch_only_day_files(tmp_path: Path) -> None:
    spot = cached_days(tmp_path, "spot", "BTCUSDT", "1h", ["2024-01-01", "2024-01-02"])
    cached_days(tmp_path, "um", "BTCUSDT", "1h", ["2024-01-01"])
    (spot / "notes.txt").write_text("keep")
    (spot / "ETHUSDT-1h-2024-01-01.parquet").write_text("keep")
    info = cache.cache_info(tmp_path)
    assert info == [
        cache.CacheEntry("spot", "BTCUSDT", "1h", 2, 200),
        cache.CacheEntry("um", "BTCUSDT", "1h", 1, 100),
    ]
    assert cache.cache_info(tmp_path, market="um", symbol="btcusdt") == info[1:]

    result = cache.clear_cache("BTCUSDT", "1h", start="2024-01-02", cache_dir=tmp_path)
    assert result == cache.ClearResult(1, 100)
    assert sorted(file.name for file in spot.iterdir()) == [
        "BTCUSDT-1h-2024-01-01.parquet",
        "ETHUSDT-1h-2024-01-01.parquet",
        "notes.txt",
    ]
    assert cache.clear_cache("BTCUSDT", cache_dir=tmp_path) == cache.ClearResult(1, 100)
    assert cache.cache_info(tmp_path) == info[1:]
    with pytest.raises(InvalidRequestError):
        cache.clear_cache("../x", cache_dir=tmp_path)


NOW = datetime(2025, 1, 2, 12, 0, tzinfo=timezone.utc)
SPOT_DEC_31 = "spot-BTCUSDT-1h-2024-12-31.csv"
SPOT_JAN_01 = "spot-BTCUSDT-1h-2025-01-01.csv"


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch, sleeps: list[float]) -> None:
    monkeypatch.setattr(loader, "utc_now", lambda: NOW)


def load(fetch: http.Fetch, start: str, end: str, root: Path, **options: object) -> pl.DataFrame:
    return load_klines("BTCUSDT", "1h", start, end, cache_dir=root, fetch=fetch, **options)


def two_vision_days() -> Binance:
    binance = Binance()
    binance.vision("spot", "2024-12-31", SPOT_DEC_31)
    binance.vision("spot", "2025-01-01", SPOT_JAN_01)
    return binance


def test_multi_day_range_loads_expected_rows_and_schema(clock: None, tmp_path: Path) -> None:
    frame = load(two_vision_days(), "2024-12-31", "2025-01-01", tmp_path)
    assert frame.schema == pl.Schema(SCHEMA)
    assert frame.height == 48
    assert frame["open_time"].is_sorted()
    assert frame["open_time"][0] == utc(2024, 12, 31)
    assert frame["open_time"][-1] == utc(2025, 1, 1, 23)
    assert frame["close_time"][-1] == datetime(2025, 1, 1, 23, 59, 59, 999000, timezone.utc)
    assert frame["trades"][:2].to_list() == [1000, 1001]


def test_range_across_2025_has_continuous_utc_timestamps(clock: None, tmp_path: Path) -> None:
    frame = load(two_vision_days(), "2024-12-31", "2025-01-01", tmp_path)
    steps = frame["open_time"].diff().drop_nulls().unique().to_list()
    assert steps == [timedelta(hours=1)]
    assert frame["open_time"].dtype == pl.Datetime("ms", "UTC")


def test_vision_404_day_is_filled_from_rest(clock: None, tmp_path: Path) -> None:
    binance = Binance()
    binance.vision("spot", "2025-01-01", SPOT_JAN_01)
    binance.rest("rest-spot-BTCUSDT-1h-2024-12-31.json")
    frame = load(binance, "2024-12-31", "2025-01-01", tmp_path)
    assert frame.height == 48
    assert frame.head(24).equals(frame_from_csv(fixture(SPOT_DEC_31)))
    assert len(binance.rest_calls()) == 1
    rest_day = tmp_path / "binance-vision/spot/BTCUSDT/1h/BTCUSDT-1h-2024-12-31.parquet"
    assert rest_day.is_file()


def test_day_missing_from_both_sources_raises_gap_error(clock: None, tmp_path: Path) -> None:
    binance = Binance()
    binance.vision("spot", "2024-12-31", SPOT_DEC_31)
    with pytest.raises(KlineGapError) as caught:
        load(binance, "2024-12-30", "2024-12-31", tmp_path)
    reason = "not on Vision (404) and REST returned no candles"
    assert caught.value.gaps == (Gap(utc(2024, 12, 30), utc(2024, 12, 30, 23), 24, reason),)
    assert caught.value.frame.height == 24
    assert not list(tmp_path.rglob("*2024-12-30*"))


def test_candles_missing_inside_file_raise_exact_gap_with_frame(
    clock: None, tmp_path: Path
) -> None:
    binance = Binance()
    binance.vision("spot", "2024-12-30", "spot-BTCUSDT-1h-2024-12-30-missing-two.csv")
    with pytest.raises(KlineGapError) as caught:
        load(binance, "2024-12-30", "2024-12-30", tmp_path)
    gap = Gap(utc(2024, 12, 30, 5), utc(2024, 12, 30, 6), 2, "missing candles in source file")
    assert caught.value.gaps == (gap,)
    frame = caught.value.frame
    assert frame.schema == pl.Schema(SCHEMA)
    assert frame.height == 22
    hours = [moment.hour for moment in frame["open_time"]]
    assert hours == [hour for hour in range(24) if hour not in (5, 6)]


def test_second_load_makes_no_fetch(clock: None, tmp_path: Path) -> None:
    first = load(two_vision_days(), "2024-12-31", "2025-01-01", tmp_path)
    again = Binance()
    assert load(again, "2024-12-31", "2025-01-01", tmp_path).equals(first)
    assert again.calls == []


def test_cache_holds_parquet_files_only(clock: None, tmp_path: Path) -> None:
    load(two_vision_days(), "2024-12-31", "2025-01-01", tmp_path)
    files = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))
    assert [file for file in files if not Path(tmp_path, file).is_dir()] == [
        "binance-vision/spot/BTCUSDT/1h/BTCUSDT-1h-2024-12-31.parquet",
        "binance-vision/spot/BTCUSDT/1h/BTCUSDT-1h-2025-01-01.parquet",
    ]


def test_spot_and_futures_fixtures_load_identically(clock: None, tmp_path: Path) -> None:
    binance = Binance()
    binance.vision("spot", "2025-01-01", SPOT_JAN_01)
    binance.vision("um", "2025-01-01", "um-BTCUSDT-1h-2025-01-01.csv")
    spot = load(binance, "2025-01-01", "2025-01-01", tmp_path)
    futures = load(binance, "2025-01-01", "2025-01-01", tmp_path, market="um")
    assert spot.equals(futures)
    assert "/data/futures/um/daily/klines/" in binance.calls[-2]


def test_checksum_mismatch_is_a_gap_and_not_cached(clock: None, tmp_path: Path) -> None:
    binance = Binance()
    binance.vision("spot", "2024-12-31", SPOT_DEC_31, checksum="ab" * 32)
    with pytest.raises(KlineGapError) as caught:
        load(binance, "2024-12-31", "2024-12-31", tmp_path)
    assert [gap.reason for gap in caught.value.gaps] == ["checksum mismatch"]
    assert binance.rest_calls() == []
    assert not [path for path in tmp_path.rglob("*") if path.is_file()]


def test_ban_stops_pending_vision_downloads(clock: None, tmp_path: Path) -> None:
    calls: list[str] = []

    def fetch(url: str) -> HttpResponse:
        calls.append(url)
        if "2024-12-01" in url:
            return HttpResponse(418)
        time.sleep(0.05)
        return HttpResponse(404)

    with pytest.raises(BinanceBanError):
        load(fetch, "2024-12-01", "2024-12-20", tmp_path)
    assert len(calls) <= 2 * loader.VISION_WORKERS


@pytest.mark.parametrize(
    ("symbol", "interval", "start", "end", "market"),
    [
        ("BTC-USDT", "1h", "2024-12-31", "2024-12-31", "spot"),
        ("BTCUSDT", "2m", "2024-12-31", "2024-12-31", "spot"),
        ("BTCUSDT", "1h", "2024-12-31", "2024-12-31", "futures"),
        ("BTCUSDT", "1h", "2024-12-31", "2025-01-03", "spot"),
    ],
)
def test_invalid_parameters_raise_before_any_fetch(
    clock: None, tmp_path: Path, symbol: str, interval: str, start: str, end: str, market: str
) -> None:
    binance = Binance()
    with pytest.raises(InvalidRequestError):
        load_klines(symbol, interval, start, end, market=market, cache_dir=tmp_path, fetch=binance)
    assert binance.calls == []
    assert not list(tmp_path.iterdir())


def test_no_cache_mode_writes_nothing(clock: None, tmp_path: Path) -> None:
    binance = two_vision_days()
    frame = load(binance, "2024-12-31", "2025-01-01", tmp_path, cache=False)
    assert frame.height == 48
    assert not list(tmp_path.iterdir())
    per_load = len(binance.calls)
    load(binance, "2024-12-31", "2025-01-01", tmp_path)
    load(binance, "2024-12-31", "2025-01-01", tmp_path, cache=False)
    assert len(binance.calls) == 3 * per_load


def test_current_day_is_not_cached(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(loader, "utc_now", lambda: utc(2025, 1, 1, 5, 30))
    binance = Binance()
    binance.rest("rest-um-BTCUSDT-1h-2025-01-01.json")
    frame = load(binance, "2025-01-01", "2025-01-01", tmp_path, market="um")
    assert [moment.hour for moment in frame["open_time"]] == [0, 1, 2, 3, 4]
    assert not [path for path in tmp_path.rglob("*") if path.is_file()]
    load(binance, "2025-01-01", "2025-01-01", tmp_path, market="um")
    assert len(binance.rest_calls()) == 2
    assert binance.rest_calls()[0].startswith("https://fapi.binance.com/fapi/v1/klines?")
