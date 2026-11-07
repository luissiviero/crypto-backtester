"""Offline tests for the local Parquet cache: layout, writes, listing and clearing."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest
from kucoin_stub import (
    HOUR_MS,
    SPOT_1H,
    TODAY,
    cached_days,
    fixture_rows,
)

from app.data import cache
from app.data.params import InvalidRequestError, KlineRequest, make_request
from app.data.schema import frame_from_spot_rows


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


def spot_request(day: str = "2026-10-01") -> KlineRequest:
    return make_request("BTC-USDT", "1h", day, day, "spot", TODAY)


def test_day_path_layout_and_escape(tmp_path: Path) -> None:
    request = spot_request()
    path = cache.day_path(tmp_path, request, request.start)
    expected = tmp_path / "kucoin/spot/BTC-USDT/1h/BTC-USDT-1h-2026-10-01.parquet"
    assert path == expected.resolve()
    forged = KlineRequest("../../..", "1h", "spot", request.start, request.end)
    with pytest.raises(cache.CachePathError):
        cache.day_path(tmp_path, forged, request.start)


def test_atomic_write_leaves_only_the_day_file(tmp_path: Path) -> None:
    frame = frame_from_spot_rows(fixture_rows(SPOT_1H), HOUR_MS).sort("open_time")
    path = cache.day_path(tmp_path, spot_request(), date(2026, 10, 1))
    cache.write_day(path, frame)
    assert [file.name for file in path.parent.iterdir()] == [path.name]
    read = cache.read_day(path)
    assert read is not None and read.equals(frame)
    path.write_bytes(b"not parquet")
    assert cache.read_day(path) is None


def test_cache_info_and_clear_touch_only_day_files(tmp_path: Path) -> None:
    spot = cached_days(tmp_path, "spot", "BTC-USDT", "1h", ["2026-10-01", "2026-10-02"])
    cached_days(tmp_path, "futures", "XBTUSDTM", "1h", ["2026-10-01"])
    (spot / "notes.txt").write_text("keep")
    (spot / "ETH-USDT-1h-2026-10-01.parquet").write_text("keep")
    old = tmp_path / "binance-vision" / "spot" / "BTCUSDT" / "1h" / "BTCUSDT-1h-2024-01-01.parquet"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"x")
    info = cache.cache_info(tmp_path)
    assert info == [
        cache.CacheEntry("spot", "BTC-USDT", "1h", 2, 200),
        cache.CacheEntry("futures", "XBTUSDTM", "1h", 1, 100),
    ]
    assert cache.cache_info(tmp_path, market="futures", symbol="xbtusdtm") == info[1:]
    assert cache.cache_info(tmp_path, symbol="xbtusdtm") == info[1:]
    assert cache.cache_info(tmp_path, symbol="btc-usdt") == info[:1]
    with pytest.raises(InvalidRequestError, match="invalid spot symbol"):
        cache.cache_info(tmp_path, symbol="BTC/USDT")
    with pytest.raises(InvalidRequestError, match="invalid futures symbol"):
        cache.cache_info(tmp_path, market="futures", symbol="BTC-USDT")

    result = cache.clear_cache("BTC-USDT", "1h", start="2026-10-02", cache_dir=tmp_path)
    assert result == cache.ClearResult(1, 100)
    assert sorted(file.name for file in spot.iterdir()) == [
        "BTC-USDT-1h-2026-10-01.parquet",
        "ETH-USDT-1h-2026-10-01.parquet",
        "notes.txt",
    ]
    assert cache.clear_cache("BTC-USDT", cache_dir=tmp_path) == cache.ClearResult(1, 100)
    assert cache.cache_info(tmp_path) == info[1:]
    assert cache.clear_cache("XBTUSDTM", market="futures", cache_dir=tmp_path).files == 1
    assert old.is_file()
    with pytest.raises(InvalidRequestError):
        cache.clear_cache("../x", cache_dir=tmp_path)


def test_clear_cache_refuses_a_datetime_bound(tmp_path: Path) -> None:
    spot = cached_days(tmp_path, "spot", "BTC-USDT", "1h", ["2026-10-01"])
    with pytest.raises(InvalidRequestError, match="not a datetime"):
        cache.clear_cache("BTC-USDT", start=datetime(2026, 10, 1), cache_dir=tmp_path)  # noqa: DTZ001
    with pytest.raises(InvalidRequestError, match="not a datetime"):
        cache.clear_cache("BTC-USDT", end=datetime(2026, 10, 1), cache_dir=tmp_path)  # noqa: DTZ001
    assert (spot / "BTC-USDT-1h-2026-10-01.parquet").is_file()
