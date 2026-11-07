"""The kline data layer: KuCoin REST klines and a local Parquet cache.

Deprecated and removed (KuCoin does not publish them): the `trades`, `taker_buy_base_volume`
and `taker_buy_quote_volume` columns, `BinanceBanError`, the `um` market and the `1s` interval.
"""

from app.data.cache import cache_info, clear_cache
from app.data.http import DownloadError, Fetch, HttpResponse
from app.data.loader import Gap, KlineGapError, load_klines
from app.data.params import InvalidRequestError

__all__ = [
    "DownloadError",
    "Fetch",
    "Gap",
    "HttpResponse",
    "InvalidRequestError",
    "KlineGapError",
    "cache_info",
    "clear_cache",
    "load_klines",
]
