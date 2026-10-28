"""Binance Vision daily kline files: URL, checksum and in-memory extraction of one CSV."""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
import zlib
from dataclasses import dataclass
from datetime import date

import polars as pl

from app.data.http import Fetch
from app.data.params import KlineRequest
from app.data.schema import MalformedDataError, frame_from_csv

VISION_BASE = "https://data.binance.vision/data"
MARKET_PATHS = {"spot": "spot", "um": "futures/um"}
MAX_ZIP_BYTES = 64 * 1024 * 1024
MAX_CSV_BYTES = 256 * 1024 * 1024

NOT_ON_VISION = "not on Vision (404)"
CHECKSUM_MISMATCH = "checksum mismatch"
CHECKSUM_UNAVAILABLE = "checksum unavailable"
MALFORMED_FILE = "malformed Vision file"

_SHA256 = re.compile(r"[0-9a-f]{64}")
_ZIP_ERRORS = (zipfile.BadZipFile, KeyError, OSError, EOFError, NotImplementedError, zlib.error)


@dataclass(frozen=True)
class VisionDay:
    """A day's Vision answer: a frame, or the reason there is none."""

    day: date
    frame: pl.DataFrame | None
    reason: str | None = None


def file_name(request: KlineRequest, day: date) -> str:
    return f"{request.symbol}-{request.interval}-{day.isoformat()}"


def day_url(request: KlineRequest, day: date) -> str:
    market = MARKET_PATHS[request.market]
    return (
        f"{VISION_BASE}/{market}/daily/klines/{request.symbol}/{request.interval}/"
        f"{file_name(request, day)}.zip"
    )


def fetch_day(fetch: Fetch, request: KlineRequest, day: date) -> VisionDay:
    url = day_url(request, day)
    archive = fetch(url)
    if archive.status == 404:
        return VisionDay(day, None, NOT_ON_VISION)
    if archive.status != 200:
        return VisionDay(day, None, f"Vision refused (HTTP {archive.status})")
    checksum = fetch(f"{url}.CHECKSUM")
    expected = _expected_sha256(checksum.body) if checksum.status == 200 else None
    if expected is None:
        return VisionDay(day, None, CHECKSUM_UNAVAILABLE)
    if hashlib.sha256(archive.body).hexdigest() != expected:
        return VisionDay(day, None, CHECKSUM_MISMATCH)
    try:
        data = _extract_csv(archive.body, f"{file_name(request, day)}.csv")
        return VisionDay(day, frame_from_csv(data))
    except MalformedDataError:
        return VisionDay(day, None, MALFORMED_FILE)


def _expected_sha256(body: bytes) -> str | None:
    tokens = body.decode("ascii", errors="replace").split()
    if not tokens or not _SHA256.fullmatch(tokens[0].lower()):
        return None
    return tokens[0].lower()


def _extract_csv(body: bytes, member: str) -> bytes:
    """Read the one expected member in memory, with size bounds; ignore any other member."""
    if len(body) > MAX_ZIP_BYTES:
        raise MalformedDataError("the zip is larger than the size bound")
    try:
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            info = archive.getinfo(member)
            if info.file_size > MAX_CSV_BYTES:
                raise MalformedDataError("the CSV member is larger than the size bound")
            with archive.open(info) as handle:
                data = handle.read(MAX_CSV_BYTES + 1)
    except _ZIP_ERRORS as error:
        raise MalformedDataError(f"the zip does not open: {error}") from None
    if len(data) > MAX_CSV_BYTES:
        raise MalformedDataError("the CSV member is larger than the size bound")
    return data
