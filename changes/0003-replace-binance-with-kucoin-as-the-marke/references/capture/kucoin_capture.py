#!/usr/bin/env python3
"""Capture real KuCoin kline answers once, for the design of the KuCoin data layer.

Read-only: every request is a public GET with no API key and no account. It places no order
and writes only into its own output folder (by default `kucoin-capture/` beside this script).
It follows no redirect and calls only the hosts in ALLOWED_HOSTS. Standard library only.

    python kucoin_capture.py [--out DIR]

It answers what KuCoin's docs leave open: row order, time unit, page size, order in time, which
intervals exist, how far back history goes, whether a key is needed from this location, and
futures contract size. Results are in `summary.json`; raw answers sit beside it. Exit code 0
when both main samples came back usable, 1 otherwise.
"""

from __future__ import annotations

import argparse
import http.client
import itertools
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SPOT_URL = "https://api.kucoin.com/api/v1/market/candles"
FUTURES_URL = "https://api-futures.kucoin.com/api/v1/kline/query"
UNIFIED_URL = "https://api.kucoin.com/api/ua/v1/market/kline"
CONTRACT_URL = "https://api-futures.kucoin.com/api/v1/contracts/XBTUSDTM"
BULK_PAGE_URL = "https://www.kucoin.com/markets/historydata"
ALLOWED_HOSTS = {"api.kucoin.com", "api-futures.kucoin.com", "www.kucoin.com"}

SPOT_SYMBOL = "BTC-USDT"
FUTURES_SYMBOL = "XBTUSDTM"
SAMPLE_DAY = datetime(2026, 10, 1, tzinfo=timezone.utc)
HISTORY_FLOOR = datetime(2017, 1, 1, tzinfo=timezone.utc)
DAY = 86_400

SPOT_INTERVALS = {
    "1min": 60,
    "3min": 180,
    "5min": 300,
    "15min": 900,
    "30min": 1_800,
    "1hour": 3_600,
    "2hour": 7_200,
    "4hour": 14_400,
    "6hour": 21_600,
    "8hour": 28_800,
    "12hour": 43_200,
    "1day": 86_400,
}
FUTURES_MINUTES = (1, 3, 5, 15, 30, 60, 120, 240, 360, 480, 720, 1440)
KEPT_HEADERS = (
    "content-type",
    "location",
    "retry-after",
    "gw-ratelimit-limit",
    "gw-ratelimit-remaining",
    "gw-ratelimit-reset",
)

PAUSE_SECONDS = 0.4
READ_TIMEOUT = 60.0
MAX_BODY_BYTES = 64 * 1024 * 1024
MAX_429_WAIT = 60.0
BULK_LINK = re.compile(r"""https?://[^\s"'<>\\]+""")
BULK_HINT = re.compile(r"\.zip|\.csv|\.gz|historydata|historical|download", re.IGNORECASE)


@dataclass(frozen=True)
class Response:
    status: int
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""


Fetch = Callable[[str], Response]


class Stop(Exception):
    """KuCoin or the network said to stop asking."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


_OPENER = urllib.request.build_opener(_NoRedirect())


def real_fetch(url: str) -> Response:
    request = urllib.request.Request(url, headers={"User-Agent": "crypto-backtester-capture"})
    try:
        with _OPENER.open(request, timeout=READ_TIMEOUT) as answer:
            return Response(answer.status, dict(answer.headers), answer.read(MAX_BODY_BYTES + 1))
    except urllib.error.HTTPError as error:
        with error:
            return Response(error.code, dict(error.headers), error.read(MAX_BODY_BYTES + 1))


def seconds(moment: datetime) -> int:
    return int(moment.timestamp())


def iso(epoch_seconds: float) -> str:
    moment = datetime.fromtimestamp(epoch_seconds, timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def time_unit(value: int) -> tuple[str, int]:
    """The unit of a raw time, and how many of that unit make one second."""
    if value >= 10**14:
        return "microseconds", 1_000_000
    if value >= 10**11:
        return "milliseconds", 1_000
    return "seconds", 1


def find_rows(payload: Any) -> list[Any] | None:
    """The candle list in KuCoin's envelope: `data`, or the first list inside it."""
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for value in data.values():
            if isinstance(value, list):
                return value
    return None


def price_order(rows: list[list[Any]]) -> dict[str, Any]:
    """Which column order fits every row: high is the largest price and low the smallest."""
    ohlc = oclh = checked = 0
    for row in rows:
        try:
            first, second, third, fourth = (float(row[index]) for index in range(1, 5))
        except (IndexError, TypeError, ValueError):
            continue
        checked += 1
        ohlc += second >= max(first, fourth) and third <= min(first, fourth)
        oclh += third >= max(first, second) and fourth <= min(first, second)
    fits_ohlc, fits_oclh = checked > 0 and ohlc == checked, checked > 0 and oclh == checked
    if fits_ohlc and not fits_oclh:
        verdict = "open, high, low, close"
    elif fits_oclh and not fits_ohlc:
        verdict = "open, close, high, low"
    else:
        verdict = "unclear"
    return {"verdict": verdict, "rows_checked": checked, "fit_ohlc": ohlc, "fit_oclh": oclh}


def analyse(body: bytes, window: tuple[int, int] | None, step: int | None) -> dict[str, Any]:
    """What the answer shows. Nothing here trusts the shape of the body."""
    try:
        payload = json.loads(body)
    except (ValueError, RecursionError):
        return {"json": False}
    facts: dict[str, Any] = {"json": True}
    if isinstance(payload, dict):
        facts["code"] = str(payload.get("code"))[:40]
        if payload.get("msg") is not None:
            facts["msg"] = str(payload["msg"])[:200]
    rows = find_rows(payload)
    if rows is None:
        return facts
    facts["rows"] = len(rows)
    if window is not None and step is not None:
        facts["expected_rows"] = (window[1] - window[0]) // step
    if not rows or not all(isinstance(row, list) and row for row in rows):
        if rows:
            facts["row_keys"] = sorted(rows[0]) if isinstance(rows[0], dict) else None
        return facts
    facts["row_fields"] = sorted({len(row) for row in rows})
    facts["sample_row"] = rows[0]
    facts["price_order"] = price_order(rows)
    try:
        times = [int(float(row[0])) for row in rows]
    except (TypeError, ValueError):
        facts["time_field"] = "does not parse"
        return facts
    unit, per_second = time_unit(times[0])
    in_seconds = [value / per_second for value in times]
    facts["time_unit"] = unit
    facts["first_row_time"] = iso(in_seconds[0])
    facts["last_row_time"] = iso(in_seconds[-1])
    if len(times) > 1:
        ascending = all(a < b for a, b in itertools.pairwise(times))
        descending = all(a > b for a, b in itertools.pairwise(times))
        facts["order_in_time"] = (
            "oldest first" if ascending else "newest first" if descending else "mixed"
        )
    if window is not None:
        facts["rows_outside_window"] = sum(not window[0] <= v <= window[1] for v in in_seconds)
        facts["row_at_window_end"] = any(v == window[1] for v in in_seconds)
    return facts


class Capture:
    def __init__(self, out: Path, fetch: Fetch, pause: Callable[[float], None]) -> None:
        self.out = out
        self.fetch = fetch
        self.pause = pause
        self.entries: dict[str, dict[str, Any]] = {}

    def _get(self, url: str) -> Response:
        parts = urllib.parse.urlsplit(url)
        if parts.scheme != "https" or parts.hostname not in ALLOWED_HOSTS:
            raise Stop(f"refusing to call {url}: not on the allowed hosts")
        self.pause(PAUSE_SECONDS)
        waited = False
        while True:
            try:
                answer = self.fetch(url)
            except (OSError, http.client.HTTPException) as error:
                return Response(0, {}, f"{type(error).__name__}: {error}".encode())
            if answer.status == 418:
                raise Stop("HTTP 418: KuCoin asks this IP address to stop")
            if answer.status != 429 or waited:
                return answer
            waited = True
            self.pause(min(_wait_seconds(answer), MAX_429_WAIT))

    def ask(
        self,
        name: str,
        base: str,
        params: dict[str, str | int] | None = None,
        *,
        window: tuple[int, int] | None = None,
        step: int | None = None,
        save: bool = True,
    ) -> dict[str, Any]:
        query = urllib.parse.urlencode(params or {})
        url = f"{base}?{query}" if query else base
        answer = self._get(url)
        lower = {key.lower(): value for key, value in answer.headers.items()}
        entry: dict[str, Any] = {
            "url": url,
            "status": answer.status,
            "bytes": len(answer.body),
            "headers": {key: lower[key] for key in KEPT_HEADERS if key in lower},
        }
        if answer.status == 0:
            entry["network_error"] = answer.body.decode(errors="replace")[:300]
        entry.update(analyse(answer.body, window, step))
        if save and answer.status != 0:
            suffix = "json" if entry.get("json") else "txt"
            path = self.out / f"{name}.{suffix}"
            path.write_bytes(answer.body[:MAX_BODY_BYTES])
            entry["body_file"] = path.name
        self.entries[name] = entry
        return entry


def _wait_seconds(answer: Response) -> float:
    lower = {key.lower(): value for key, value in answer.headers.items()}
    try:
        return max(float(lower.get("gw-ratelimit-reset", "")) / 1000.0, 1.0)
    except ValueError:
        return 30.0


def usable(entry: dict[str, Any]) -> bool:
    """A 200 with KuCoin's success code, rows, and every row inside the asked window."""
    return (
        entry.get("status") == 200
        and entry.get("code") == "200000"
        and entry.get("rows", 0) > 0
        and entry.get("rows_outside_window", 0) == 0
    )


def spot_params(interval: str, start: int, end: int) -> dict[str, str | int]:
    return {"symbol": SPOT_SYMBOL, "type": interval, "startAt": start, "endAt": end}


def futures_params(minutes: int, start: int, end: int, per_second: int) -> dict[str, str | int]:
    return {
        "symbol": FUTURES_SYMBOL,
        "granularity": minutes,
        "from": start * per_second,
        "to": end * per_second,
    }


def oldest_day(has_data: Callable[[int], bool | None]) -> str:
    """Bisect the first day with candles; assumes data, once it starts, does not stop."""
    low, high = 0, (SAMPLE_DAY - HISTORY_FLOOR).days
    if has_data(high) is not True:
        return "unknown: the sample day has no data"
    while low < high:
        middle = (low + high) // 2
        answer = has_data(middle)
        if answer is None:
            return "unknown: a probe failed"
        if answer:
            high = middle
        else:
            low = middle + 1
    return (HISTORY_FLOOR + timedelta(days=low)).strftime("%Y-%m-%d")


def run(capture: Capture) -> dict[str, Any]:
    start = seconds(SAMPLE_DAY)
    day_end = start + DAY
    three_days_end = start + 3 * DAY
    day = (start, day_end)
    three_days = (start, three_days_end)
    findings: dict[str, Any] = {}

    print("Spot samples")
    spot_1h = capture.ask(
        "spot-BTC-USDT-1hour", SPOT_URL, spot_params("1hour", *day), window=day, step=3_600
    )
    capture.ask("spot-BTC-USDT-1min", SPOT_URL, spot_params("1min", *day), window=day, step=60)
    spot_page = capture.ask(
        "spot-BTC-USDT-1min-3days",
        SPOT_URL,
        spot_params("1min", *three_days),
        window=three_days,
        step=60,
    )

    print("Futures samples")
    by_ms = capture.ask(
        "futures-XBTUSDTM-60-from-to-in-ms",
        FUTURES_URL,
        futures_params(60, *day, 1_000),
        window=day,
        step=3_600,
    )
    by_s = capture.ask(
        "futures-XBTUSDTM-60-from-to-in-seconds",
        FUTURES_URL,
        futures_params(60, *day, 1),
        window=day,
        step=3_600,
    )
    per_second = 1_000 if usable(by_ms) else 1 if usable(by_s) else None
    findings["futures_from_to_accepted_in"] = {
        "milliseconds": usable(by_ms),
        "seconds": usable(by_s),
    }
    futures_unit = per_second or 1_000
    capture.ask(
        "futures-XBTUSDTM-1-one-day",
        FUTURES_URL,
        futures_params(1, *day, futures_unit),
        window=day,
        step=60,
    )
    futures_page = capture.ask(
        "futures-XBTUSDTM-1-3days",
        FUTURES_URL,
        futures_params(1, *three_days, futures_unit),
        window=three_days,
        step=60,
    )
    findings["page_size_seen"] = {
        "spot": spot_page.get("rows"),
        "futures": futures_page.get("rows"),
    }

    print("Contract details, unknown symbols")
    contract = capture.ask("futures-contract-XBTUSDTM", CONTRACT_URL)
    capture.ask("spot-unknown-symbol", SPOT_URL, {**spot_params("1hour", *day), "symbol": "ZZ-ZZ"})
    capture.ask(
        "futures-unknown-symbol",
        FUTURES_URL,
        {**futures_params(60, *day, futures_unit), "symbol": "ZZZZUSDTM"},
    )
    findings["contract_fields"] = _contract_fields(capture.out / "futures-contract-XBTUSDTM.json")
    findings["contract_status"] = contract.get("status")

    print("Which intervals exist")
    findings["spot_intervals"] = {
        interval: usable(
            capture.ask(
                f"probe-spot-{interval}",
                SPOT_URL,
                spot_params(interval, *day),
                window=day,
                save=False,
            )
        )
        for interval in SPOT_INTERVALS
    }
    findings["futures_interval_minutes"] = {
        str(minutes): usable(
            capture.ask(
                f"probe-futures-{minutes}",
                FUTURES_URL,
                futures_params(minutes, *day, futures_unit),
                window=day,
                save=False,
            )
        )
        for minutes in FUTURES_MINUTES
    }

    print("Unified endpoint, no key (its parameter names are my best guess)")
    for name, symbol, trade_type in (
        ("unified-spot", SPOT_SYMBOL, "SPOT"),
        ("unified-futures", FUTURES_SYMBOL, "FUTURES"),
    ):
        capture.ask(
            name,
            UNIFIED_URL,
            {
                "tradeType": trade_type,
                "symbol": symbol,
                "type": "1hour",
                "startAt": start,
                "endAt": day_end,
            },
        )

    print("Oldest candle (one probe per step, about a minute)")
    findings["oldest_day"] = _oldest_days(capture, futures_unit)

    print("Bulk download page")
    page = capture.ask("bulk-page", BULK_PAGE_URL)
    findings["bulk_page_status"] = page.get("status")
    findings["bulk_page_links"] = _bulk_links(capture.out / "bulk-page.txt")

    findings["spot_ok"] = usable(spot_1h)
    findings["futures_ok"] = per_second is not None
    return findings


def _contract_fields(path: Path) -> dict[str, Any]:
    wanted = ("multiplier", "firstOpenDate", "baseCurrency", "quoteCurrency", "status")
    try:
        data = json.loads(path.read_bytes())["data"]
        return {key: data.get(key) for key in wanted}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {}


def _oldest_days(capture: Capture, futures_unit: int) -> dict[str, str]:
    def spot_probe(interval: str) -> Callable[[int], bool | None]:
        def probe(offset: int) -> bool | None:
            first = seconds(HISTORY_FLOOR) + offset * DAY
            entry = capture.ask(
                "probe-oldest-spot",
                SPOT_URL,
                spot_params(interval, first, first + DAY),
                save=False,
            )
            return _has_rows(entry)

        return probe

    def futures_probe(minutes: int) -> Callable[[int], bool | None]:
        def probe(offset: int) -> bool | None:
            first = seconds(HISTORY_FLOOR) + offset * DAY
            entry = capture.ask(
                "probe-oldest-futures",
                FUTURES_URL,
                futures_params(minutes, first, first + DAY, futures_unit),
                save=False,
            )
            return _has_rows(entry)

        return probe

    return {
        "spot_1min": oldest_day(spot_probe("1min")),
        "spot_1hour": oldest_day(spot_probe("1hour")),
        "futures_1min": oldest_day(futures_probe(1)),
        "futures_1hour": oldest_day(futures_probe(60)),
    }


def _has_rows(entry: dict[str, Any]) -> bool | None:
    if entry.get("status") != 200 or "rows" not in entry:
        return None
    return entry["rows"] > 0


def _bulk_links(path: Path) -> list[str]:
    """Links on the page that look like data files. They are listed, never followed."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    found = {link for link in BULK_LINK.findall(text) if BULK_HINT.search(link)}
    return sorted(found)[:50]


def report(entries: dict[str, dict[str, Any]], findings: dict[str, Any]) -> None:
    print("\nSamples")
    for name, entry in entries.items():
        if name.startswith("probe-"):
            continue
        order = entry.get("price_order", {}).get("verdict", "-")
        print(
            f"  {name}: HTTP {entry['status']}, code {entry.get('code', '-')}, "
            f"{entry.get('rows', '-')} of {entry.get('expected_rows', '-')} rows, "
            f"fields {entry.get('row_fields', '-')}, times in {entry.get('time_unit', '-')}, "
            f"{entry.get('order_in_time', '-')}, prices {order}"
        )
    print("\nFindings")
    for key, value in findings.items():
        print(f"  {key}: {value!a}")


def main(
    argv: list[str] | None = None,
    fetch: Fetch = real_fetch,
    pause: Callable[[float], None] = time.sleep,
) -> int:
    parser = argparse.ArgumentParser(description="Capture KuCoin kline answers once (read-only).")
    default_out = Path(__file__).resolve().parent / "kucoin-capture"
    parser.add_argument("--out", type=Path, default=default_out, help="the output folder")
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)

    capture = Capture(args.out, fetch, pause)
    findings: dict[str, Any] = {}
    stopped = None
    try:
        findings = run(capture)
    except Stop as stop:
        stopped = str(stop)
        findings["stopped"] = stopped

    summary = {
        "captured_at": iso(time.time()),
        "findings": findings,
        "requests": capture.entries,
    }
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    report(capture.entries, findings)
    print(f"\nSaved in {str(args.out)!a}")
    if stopped or not (findings.get("spot_ok") and findings.get("futures_ok")):
        print("A main sample failed: see Findings and summary.json.")
        return 1
    print("Both main samples are usable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
