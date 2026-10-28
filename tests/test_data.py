"""Offline tests for the kline data layer (app.data): every fetch goes through a stub."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import polars as pl
import pytest

from app.data.params import InvalidRequestError, make_request
from app.data.schema import SCHEMA, MalformedDataError, frame_from_csv, frame_from_rest

FIXTURES = Path(__file__).parent / "fixtures" / "binance"
TODAY = date(2025, 1, 2)


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


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
