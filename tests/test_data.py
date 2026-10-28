"""Offline tests for the kline data layer (app.data): every fetch goes through a stub."""

from __future__ import annotations

from datetime import date

import pytest

from app.data.params import InvalidRequestError, make_request

TODAY = date(2025, 1, 2)


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
