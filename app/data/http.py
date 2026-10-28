"""HTTP transport: the urllib fetch, retries with backoff, and the REST weight pause."""

from __future__ import annotations

import http.client
import random
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime

CONNECT_TIMEOUT = 10.0
READ_TIMEOUT = 60.0
MAX_BODY_BYTES = 64 * 1024 * 1024
RETRY_DELAYS = (1.0, 2.0, 4.0)
MAX_JITTER = 0.5
MAX_RETRY_AFTER = 60.0
WEIGHT_HEADER = "X-MBX-USED-WEIGHT-1M"
WEIGHT_THRESHOLD = 0.8
UNKNOWN_WEIGHT_WAIT = 1.0
TRANSIENT_ERRORS = (OSError, http.client.HTTPException)


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: Mapping[str, str] = field(default_factory=dict)
    body: bytes = b""

    def header(self, name: str) -> str | None:
        """Look a header up by name, case-insensitively."""
        wanted = name.lower()
        for key, value in self.headers.items():
            if key.lower() == wanted:
                return value
        return None


Fetch = Callable[[str], HttpResponse]


class DownloadError(RuntimeError):
    """A download that cannot go on: retries exhausted, a ban, a too-long Retry-After."""


class BinanceBanError(DownloadError):
    """HTTP 418: Binance has banned this IP address for a while."""


def sleep(seconds: float) -> None:
    time.sleep(seconds)


def jitter() -> float:
    return random.uniform(0.0, MAX_JITTER)


def wall_clock() -> float:
    return time.time()


class _HTTPSConnection(http.client.HTTPSConnection):
    """Connects within CONNECT_TIMEOUT, then waits up to READ_TIMEOUT for each read."""

    def connect(self) -> None:
        self.timeout = CONNECT_TIMEOUT
        super().connect()
        self.sock.settimeout(READ_TIMEOUT)


class _HTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req: urllib.request.Request) -> http.client.HTTPResponse:
        return self.do_open(_HTTPSConnection, req)


_OPENER = urllib.request.build_opener(_HTTPSHandler())


def urllib_fetch(url: str) -> HttpResponse:
    """GET a URL with the standard library; an HTTP error status becomes a response."""
    request = urllib.request.Request(url, headers={"User-Agent": "crypto-backtester"})
    try:
        with _OPENER.open(request) as response:
            return HttpResponse(response.status, dict(response.headers), _read(response))
    except urllib.error.HTTPError as error:
        with error:
            return HttpResponse(error.code, dict(error.headers), _read(error))


def _read(response: http.client.HTTPResponse | urllib.error.HTTPError) -> bytes:
    # One byte over the cap tells the caller the body was larger than any valid answer.
    return response.read(MAX_BODY_BYTES + 1)


def with_retries(fetch: Fetch) -> Fetch:
    """Wrap a Fetch: retry connection errors, 429 and 5xx; raise on 418; return the rest."""

    def fetch_with_retries(url: str) -> HttpResponse:
        failure = ""
        for attempt in range(len(RETRY_DELAYS) + 1):
            retry_after = None
            try:
                response = fetch(url)
            except TRANSIENT_ERRORS as error:
                failure = f"{type(error).__name__}: {error}"
            else:
                if response.status == 418:
                    raise BinanceBanError(
                        f"Binance answered HTTP 418 for {url}: this IP address is banned for "
                        "a while; wait before running again"
                    )
                if response.status != 429 and response.status < 500:
                    return response
                failure = f"HTTP {response.status}"
                retry_after = _retry_after(response)
            if attempt == len(RETRY_DELAYS):
                break
            if retry_after is not None and retry_after > MAX_RETRY_AFTER:
                raise DownloadError(
                    f"{url}: {failure} with Retry-After {retry_after:.0f} s; run again after "
                    "that wait"
                )
            sleep(max(RETRY_DELAYS[attempt] + jitter(), retry_after or 0.0))
        raise DownloadError(
            f"{url}: {failure} after {len(RETRY_DELAYS)} retries; check the network and run again"
        )

    return fetch_with_retries


def _retry_after(response: HttpResponse) -> float | None:
    value = response.header("Retry-After")
    if value is None:
        return None
    try:
        return max(float(value), 0.0)
    except ValueError:
        pass
    try:
        return max(parsedate_to_datetime(value).timestamp() - wall_clock(), 0.0)
    except (TypeError, ValueError):
        return None


class WeightPacer:
    """Pauses REST calls on the used-weight header of the previous response."""

    def __init__(self, weight_limit: int) -> None:
        self.weight_limit = weight_limit
        self.last: HttpResponse | None = None

    def wait(self) -> None:
        """Call before each REST request."""
        if self.last is None:
            return
        weight = _int_or_none(self.last.header(WEIGHT_HEADER))
        if weight is None:
            sleep(UNKNOWN_WEIGHT_WAIT)
        elif weight >= WEIGHT_THRESHOLD * self.weight_limit:
            sleep(60.0 - wall_clock() % 60.0)

    def record(self, response: HttpResponse) -> None:
        self.last = response


def _int_or_none(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None
