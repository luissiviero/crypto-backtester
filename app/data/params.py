"""Request parameters: validated before any URL or cache path is built from them."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

MARKETS = ("spot", "futures")

INTERVAL_MS = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "2h": 7_200_000,
    "4h": 14_400_000,
    "6h": 21_600_000,
    "8h": 28_800_000,
    "12h": 43_200_000,
    "1d": 86_400_000,
}
FUTURES_REFUSED_INTERVALS = frozenset({"6h"})
DAY_MS = 86_400_000

# KuCoin's names for our intervals: the spot `type` and the futures `granularity` in minutes.
SPOT_TYPES = {
    "1m": "1min",
    "3m": "3min",
    "5m": "5min",
    "15m": "15min",
    "30m": "30min",
    "1h": "1hour",
    "2h": "2hour",
    "4h": "4hour",
    "6h": "6hour",
    "8h": "8hour",
    "12h": "12hour",
    "1d": "1day",
}
FUTURES_GRANULARITY = {
    "1m": 1,
    "3m": 3,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "2h": 120,
    "4h": 240,
    "8h": 480,
    "12h": 720,
    "1d": 1440,
}

_SPOT_SYMBOL = re.compile(r"[A-Z0-9-]{2,30}")
_FUTURES_SYMBOL = re.compile(r"[A-Z0-9]{2,25}USDTM")


class InvalidRequestError(ValueError):
    """A symbol, interval, market or date the data layer refuses."""


@dataclass(frozen=True)
class KlineRequest:
    symbol: str
    interval: str
    market: str
    start: date
    end: date

    @property
    def interval_ms(self) -> int:
        return INTERVAL_MS[self.interval]

    def days(self) -> list[date]:
        count = (self.end - self.start).days + 1
        return [self.start + timedelta(days=offset) for offset in range(count)]


def validate_market(market: str) -> str:
    if market not in MARKETS:
        raise InvalidRequestError(
            f"unknown market {market!r}: use 'spot' or 'futures' (USDT-margined perpetuals)"
        )
    return market


def validate_interval(interval: str, market: str) -> str:
    if interval not in INTERVAL_MS:
        choices = ", ".join(INTERVAL_MS)
        raise InvalidRequestError(f"unknown interval {interval!r}: use one of {choices}")
    if interval in FUTURES_REFUSED_INTERVALS and market == "futures":
        raise InvalidRequestError(f"interval {interval!r} is not offered on the futures market")
    return interval


def validate_symbol(symbol: str, market: str) -> str:
    normalized = symbol.upper()
    if market == "futures":
        if not _FUTURES_SYMBOL.fullmatch(normalized):
            raise InvalidRequestError(
                f"invalid futures symbol {symbol!r}: use a USDT-margined perpetual, 7 to 30 "
                "letters or digits ending in USDTM, for example XBTUSDTM"
            )
    elif not _SPOT_SYMBOL.fullmatch(normalized):
        raise InvalidRequestError(
            f"invalid spot symbol {symbol!r}: use 2 to 30 letters, digits or hyphens, "
            "for example BTC-USDT"
        )
    return normalized


def parse_date(value: date | str, name: str) -> date:
    # A datetime is a date too, but its time of day and zone do not say which UTC day is meant.
    if isinstance(value, datetime):
        raise InvalidRequestError(
            f"invalid {name} date {value!r}: pass a date or YYYY-MM-DD, not a datetime"
        )
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise InvalidRequestError(
            f"invalid {name} date {value!r}: use YYYY-MM-DD, for example 2024-01-31"
        ) from None


def make_request(
    symbol: str,
    interval: str,
    start: date | str,
    end: date | str,
    market: str,
    today: date,
) -> KlineRequest:
    market = validate_market(market)
    interval = validate_interval(interval, market)
    symbol = validate_symbol(symbol, market)
    start_day = parse_date(start, "start")
    end_day = parse_date(end, "end")
    if start_day > end_day:
        raise InvalidRequestError(f"start {start_day} is after end {end_day}")
    if end_day > today:
        raise InvalidRequestError(f"end {end_day} is in the future (today is {today} UTC)")
    return KlineRequest(symbol, interval, market, start_day, end_day)


def day_start_ms(day: date) -> int:
    return (day - date(1970, 1, 1)).days * DAY_MS
