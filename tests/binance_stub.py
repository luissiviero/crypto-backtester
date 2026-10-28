"""Shared offline stubs for the data-layer tests: fixtures, a sequence Fetch, a Binance stub."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from app.data import http, vision
from app.data.http import HttpResponse
from app.data.params import make_request

FIXTURES = Path(__file__).parent / "fixtures" / "binance"
TODAY = date(2025, 1, 2)
WEIGHT = "X-MBX-USED-WEIGHT-1M"


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


def cached_days(root: Path, market: str, symbol: str, interval: str, days: list[str]) -> Path:
    """Fake day files (100 bytes each) in the cache layout."""
    directory = root / "binance-vision" / market / symbol / interval
    directory.mkdir(parents=True, exist_ok=True)
    for day in days:
        (directory / f"{symbol}-{interval}-{day}.parquet").write_bytes(b"x" * 100)
    return directory


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
