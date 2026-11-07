"""Offline tests for KuCoin paging, completeness and gaps, through the KuCoin stub."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest
from kucoin_stub import (
    FUTURES_1H,
    FUTURES_1M,
    HEADERS,
    HOUR_MS,
    MINUTE_MS,
    SPOT_1H,
    KuCoin,
    fixture,
    ms,
    utc,
)

from app.data import KlineGapError, http, load_klines, loader, rest
from app.data.http import DownloadError, HttpResponse
from app.data.params import InvalidRequestError
from app.data.schema import frame_from_spot_rows


def test_kucoin_error_code_is_a_refusal_with_its_message(clock: None, tmp_path: Path) -> None:
    kucoin = KuCoin()
    kucoin.refuse(rest.SPOT_URL, HttpResponse(200, HEADERS, fixture("spot-unknown-symbol.json")))
    with pytest.raises(KlineGapError) as caught:
        load_klines("NOPE-USDT", "1h", "2026-10-01", "2026-10-01", cache_dir=tmp_path, fetch=kucoin)
    reason = "KuCoin refused (HTTP 200, code 400100): Unsupported trading pair."
    assert [gap.reason for gap in caught.value.gaps] == [reason]
    assert not list(tmp_path.rglob("*.parquet"))

    body = b'{"code": "400\\u001b[2J", "msg": "bad\\u001b[31m\\npair' + b"x" * 500 + b'"}'
    _, failure = rest.parse_answer(HttpResponse(200, {}, body), frame_from_spot_rows, HOUR_MS)
    assert failure == "KuCoin refused (HTTP 200, code 400[2J): bad[31mpair" + "x" * 189


def load(
    fetch: http.Fetch,
    start: str,
    end: str,
    root: Path,
    symbol: str = "BTC-USDT",
    interval: str = "1h",
    **options: object,
) -> pl.DataFrame:
    return load_klines(symbol, interval, start, end, cache_dir=root, fetch=fetch, **options)


def futures(fetch: http.Fetch, start: str, end: str, root: Path, **options: object) -> pl.DataFrame:
    return load(fetch, start, end, root, "XBTUSDTM", market="futures", **options)


def assert_complete(frame: pl.DataFrame, height: int) -> None:
    assert frame.height == height
    assert frame["open_time"].is_sorted()
    assert frame["open_time"].n_unique() == height


def test_spot_range_over_1500_candles_loads_completely(clock: None, tmp_path: Path) -> None:
    kucoin = KuCoin()
    kucoin.add_spot_synthetic(utc(2026, 9, 29), 3 * 1440, MINUTE_MS)
    assert_complete(load(kucoin, "2026-09-29", "2026-10-01", tmp_path, interval="1m"), 4320)
    assert len(kucoin.calls) == 3
    assert kucoin.calls[0] == (
        "https://api.kucoin.com/api/v1/market/candles?symbol=BTC-USDT&type=1min"
        f"&startAt={ms(utc(2026, 9, 29)) // 1000}&endAt={ms(utc(2026, 10, 2)) // 1000}"
    )


def test_futures_range_over_200_candles_loads_completely(
    clock: None, sleeps: list[float], tmp_path: Path
) -> None:
    kucoin = KuCoin(headers={})
    kucoin.add_futures_synthetic(utc(2026, 10, 1), 1440, MINUTE_MS)
    assert_complete(futures(kucoin, "2026-10-01", "2026-10-01", tmp_path, interval="1m"), 1440)
    assert len(kucoin.calls) == 8
    assert kucoin.calls[0] == (
        "https://api-futures.kucoin.com/api/v1/kline/query?symbol=XBTUSDTM&granularity=1"
        f"&from={ms(utc(2026, 10, 1))}&to={ms(utc(2026, 10, 2)) - 1}"
    )
    assert sleeps == [1.0] * 7


def test_futures_end_of_window_row_adds_no_next_day_candle(clock: None, tmp_path: Path) -> None:
    kucoin = KuCoin()
    kucoin.refuse(rest.FUTURES_URL, HttpResponse(200, HEADERS, fixture(FUTURES_1H)))
    frame = futures(kucoin, "2026-10-01", "2026-10-01", tmp_path)
    assert_complete(frame, 24)
    assert frame["open_time"][-1] == utc(2026, 10, 1, 23)
    assert len(kucoin.calls) == 1


def test_futures_day_without_some_minutes_has_no_gap(clock: None, tmp_path: Path) -> None:
    kucoin = KuCoin()
    kucoin.add_futures(FUTURES_1M)
    frame = futures(kucoin, "2026-10-01", "2026-10-01", tmp_path, interval="1m")
    assert_complete(frame, 200)
    opens = set(frame["open_time"].to_list())
    assert utc(2026, 10, 1, 0, 14) not in opens and utc(2026, 10, 1, 2, 15) not in opens
    assert [path.name for path in tmp_path.rglob("*.parquet")] == ["XBTUSDTM-1m-2026-10-01.parquet"]


def test_empty_day_is_a_gap_and_not_cached(clock: None, tmp_path: Path) -> None:
    kucoin = KuCoin()
    kucoin.add_spot(SPOT_1H)
    with pytest.raises(KlineGapError) as caught:
        load(kucoin, "2026-10-01", "2026-10-02", tmp_path)
    gap = loader.Gap(utc(2026, 10, 2), utc(2026, 10, 2, 23), 24, "no candles on this day")
    assert caught.value.gaps == (gap,)
    assert caught.value.frame.height == 24
    assert [path.name for path in tmp_path.rglob("*.parquet")] == ["BTC-USDT-1h-2026-10-01.parquet"]


def test_refused_page_is_a_gap_and_not_cached(clock: None, tmp_path: Path) -> None:
    kucoin = KuCoin()
    kucoin.add_spot(SPOT_1H)
    kucoin.refuse(rest.SPOT_URL, HttpResponse(451, HEADERS, b""))
    with pytest.raises(KlineGapError) as caught:
        load(kucoin, "2026-10-01", "2026-10-01", tmp_path)
    assert [gap.reason for gap in caught.value.gaps] == ["KuCoin refused (HTTP 451)"]
    assert not list(tmp_path.rglob("*.parquet"))


CUT_SHORT = HttpResponse(400, HEADERS, b'{"code": "400000", "msg": "cut short"}')
SPOT_SECOND_PAGE = f"endAt={ms(utc(2026, 9, 30, 23)) // 1000}"
FUTURES_SECOND_PAGE = f"from={ms(utc(2026, 9, 29, 3, 20))}"


def test_page_cut_short_is_a_gap_and_not_cached(clock: None, tmp_path: Path) -> None:
    kucoin = KuCoin()
    kucoin.add_spot_synthetic(utc(2026, 9, 29), 3 * 1440, MINUTE_MS)
    kucoin.refuse(SPOT_SECOND_PAGE, CUT_SHORT)
    with pytest.raises(KlineGapError) as caught:
        load(kucoin, "2026-09-29", "2026-10-01", tmp_path, interval="1m")
    reason = "KuCoin refused (HTTP 400, code 400000): cut short"
    gap = loader.Gap(utc(2026, 9, 29), utc(2026, 9, 30, 22, 59), 2820, reason)
    assert caught.value.gaps == (gap,)
    assert caught.value.frame.height == 1500
    assert [path.name for path in tmp_path.rglob("*.parquet")] == ["BTC-USDT-1m-2026-10-01.parquet"]

    kucoin = KuCoin()
    kucoin.add_futures_synthetic(utc(2026, 9, 29), 3 * 1440, MINUTE_MS)
    kucoin.refuse(FUTURES_SECOND_PAGE, CUT_SHORT)
    with pytest.raises(KlineGapError) as caught:
        futures(kucoin, "2026-09-29", "2026-10-01", tmp_path, interval="1m")
    gap = loader.Gap(utc(2026, 9, 29, 3, 20), utc(2026, 10, 1, 23, 59), 4120, reason)
    assert caught.value.gaps == (gap,)
    assert caught.value.frame.height == 200
    assert not list((tmp_path / "kucoin" / "futures").rglob("*.parquet"))


def test_days_fetched_before_a_download_error_stay_cached(clock: None, tmp_path: Path) -> None:
    kucoin = KuCoin()
    kucoin.add_spot_synthetic(utc(2026, 9, 29), 3 * 1440, MINUTE_MS)
    kucoin.refuse(SPOT_SECOND_PAGE, HttpResponse(503))
    with pytest.raises(DownloadError, match="after 3 retries"):
        load(kucoin, "2026-09-29", "2026-10-01", tmp_path, interval="1m")
    assert [path.name for path in tmp_path.rglob("*.parquet")] == ["BTC-USDT-1m-2026-10-01.parquet"]

    kucoin = KuCoin()
    kucoin.add_futures_synthetic(utc(2026, 9, 29), 3 * 1440, MINUTE_MS)
    kucoin.refuse(f"from={ms(utc(2026, 9, 30, 2, 40))}", HttpResponse(503))
    with pytest.raises(DownloadError, match="after 3 retries"):
        futures(kucoin, "2026-09-29", "2026-10-01", tmp_path, interval="1m")
    files = sorted(path.name for path in (tmp_path / "kucoin" / "futures").rglob("*.parquet"))
    assert files == ["XBTUSDTM-1m-2026-09-29.parquet"]


def test_mistyped_futures_symbol_names_the_symbol_check(clock: None, tmp_path: Path) -> None:
    kucoin = KuCoin()
    kucoin.refuse(
        rest.FUTURES_URL, HttpResponse(200, HEADERS, fixture("futures-unknown-symbol.json"))
    )
    with pytest.raises(KlineGapError) as caught:
        futures(kucoin, "2026-10-01", "2026-10-02", tmp_path)
    assert {gap.reason for gap in caught.value.gaps} == {"no candles; check the symbol exists"}
    assert sum(gap.candles for gap in caught.value.gaps) == 48


def test_day_before_first_candle_names_the_oldest_candle(clock: None, tmp_path: Path) -> None:
    kucoin = KuCoin()
    kucoin.add_spot(SPOT_1H)
    with pytest.raises(KlineGapError) as caught:
        load(kucoin, "2026-09-30", "2026-10-01", tmp_path)
    reason = (
        "no candles before 2026-10-01: the date may be before KuCoin's oldest candle for this "
        "symbol"
    )
    assert caught.value.gaps == (loader.Gap(utc(2026, 9, 30), utc(2026, 9, 30, 23), 24, reason),)


@pytest.mark.parametrize(
    ("symbol", "interval", "end", "market"),
    [
        ("XBTUSDTM", "6h", "2026-10-01", "futures"),
        ("BTC-USDT", "1s", "2026-10-01", "spot"),
        ("BTC-USDT", "1h", "2026-10-01", "um"),
        ("XBTUSDM", "1h", "2026-10-01", "futures"),
        ("BTC-USDT", "1h", "2026-10-04", "spot"),
    ],
)
def test_invalid_parameters_raise_before_any_fetch(
    clock: None, tmp_path: Path, symbol: str, interval: str, end: str, market: str
) -> None:
    kucoin = KuCoin()
    with pytest.raises(InvalidRequestError):
        load_klines(
            symbol, interval, "2026-10-01", end, market=market, cache_dir=tmp_path, fetch=kucoin
        )
    assert kucoin.calls == []
    assert not list(tmp_path.iterdir())


def two_markets() -> KuCoin:
    kucoin = KuCoin()
    kucoin.add_spot(SPOT_1H)
    kucoin.add_futures(FUTURES_1H)
    return kucoin


def test_second_load_makes_no_fetch(clock: None, tmp_path: Path) -> None:
    first = load(two_markets(), "2026-10-01", "2026-10-01", tmp_path)
    first_futures = futures(two_markets(), "2026-10-01", "2026-10-01", tmp_path)
    again = KuCoin()
    assert load(again, "2026-10-01", "2026-10-01", tmp_path).equals(first)
    assert futures(again, "2026-10-01", "2026-10-01", tmp_path).equals(first_futures)
    assert again.calls == []


def test_cache_holds_parquet_files_only_under_kucoin(clock: None, tmp_path: Path) -> None:
    load(two_markets(), "2026-10-01", "2026-10-01", tmp_path)
    futures(two_markets(), "2026-10-01", "2026-10-01", tmp_path)
    files = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))
    assert [file for file in files if not Path(tmp_path, file).is_dir()] == [
        "kucoin/futures/XBTUSDTM/1h/XBTUSDTM-1h-2026-10-01.parquet",
        "kucoin/spot/BTC-USDT/1h/BTC-USDT-1h-2026-10-01.parquet",
    ]


def test_no_cache_mode_writes_nothing(clock: None, tmp_path: Path) -> None:
    kucoin = two_markets()
    frame = load(kucoin, "2026-10-01", "2026-10-01", tmp_path, cache=False)
    assert frame.height == 24
    assert not list(tmp_path.iterdir())
    per_load = len(kucoin.calls)
    load(kucoin, "2026-10-01", "2026-10-01", tmp_path)
    load(kucoin, "2026-10-01", "2026-10-01", tmp_path, cache=False)
    assert len(kucoin.calls) == 3 * per_load


def test_current_day_is_not_cached(
    monkeypatch: pytest.MonkeyPatch, sleeps: list[float], tmp_path: Path
) -> None:
    monkeypatch.setattr(loader, "utc_now", lambda: utc(2026, 10, 1, 5, 30))
    kucoin = KuCoin()
    kucoin.add_futures_synthetic(utc(2026, 10, 1), 6, HOUR_MS)
    frame = futures(kucoin, "2026-10-01", "2026-10-01", tmp_path)
    assert [moment.hour for moment in frame["open_time"]] == [0, 1, 2, 3, 4]
    assert not [path for path in tmp_path.rglob("*") if path.is_file()]
    futures(kucoin, "2026-10-01", "2026-10-01", tmp_path)
    assert len(kucoin.calls) == 4
    assert kucoin.calls[0].startswith(f"{rest.FUTURES_URL}?")
