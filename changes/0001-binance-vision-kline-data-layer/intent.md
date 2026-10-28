# Intent: Binance Vision kline data layer
Author: owner (product owner). Change id: 0001. Entry route: idea.

## Problem
The backtester has no market data. In the owner's words: "Download Binance Vision daily kline
(OHLCV) files for one symbol and interval, cache them locally, and load a date range into a
DataFrame, as the data layer for later backtests."

Today every later feature (strategies, signals, performance reports) is blocked: there is no
way to get candles into the program, and fetching them by hand for each experiment is slow and
easy to get wrong (missing days, mixed intervals, re-downloading the same files). The owner's
disk space is limited, so the cache has to stay small.

## Proposed outcome
A data module in `app/` that, for one symbol, one interval and one market at a time, does the
following.

**Sources**
- Downloads the daily kline zip files that Binance Vision (`data.binance.vision`) publishes,
  for two markets:
  - spot (`data/spot/daily/klines/<SYMBOL>/<INTERVAL>/`);
  - USDⓈ-M futures (`data/futures/um/daily/klines/<SYMBOL>/<INTERVAL>/`).
- Fills the days Binance Vision does not have from the public Binance REST klines endpoint (no
  API key): spot `GET /api/v3/klines`, USDⓈ-M `GET /fapi/v1/klines`. These are mainly today
  and the last day or two before Vision publishes them. The REST rows go through the same
  normalisation as the files, so the result does not depend on the source.
- When neither source has data, the gap is reported, never hidden. This happens before a
  symbol was listed, after it was delisted, or for an unknown symbol. A requested range that
  comes back with fewer rows than it should raises a clear error or returns the list of gaps
  next to the data (the exact shape is settled in design), never a silently short frame.

**The DataFrame**
- An inclusive date range loads into one **polars** DataFrame: one row per candle, sorted by
  open time, with no duplicate rows.
- It keeps all of Binance's kline columns for now (the owner may trim them later):
  - open time, open, high, low, close, volume;
  - close time, quote asset volume, number of trades;
  - taker buy base volume, taker buy quote volume.
  The unused "ignore" column may be dropped. Column names and dtypes are fixed in design and
  are the same whichever market or source the row comes from.
- **Timestamps are normalised.** Spot files from 2025-01-01 on give open and close times in
  microseconds; older spot files, the futures files and the REST API use milliseconds. The
  loader detects the unit of each file and converts every time to one UTC timestamp type. A
  range that crosses 2025-01-01 loads as one continuous series.

**The cache (small and fast)**
- Each day is downloaded once. A repeated load of a cached range makes no network request.
- The cache stores **compressed Parquet**, not the original zip. Each zip is checked against
  its `.CHECKSUM` file, converted, then deleted. Parquet is the lighter and faster option: no
  CSV parsing on load, columnar compression, and only one copy on disk.
- Default location: the user's cache directory, outside the repository:
  `$XDG_CACHE_HOME/crypto-backtester/` (normally `~/.cache/crypto-backtester/`) on Linux and
  macOS, `%LOCALAPPDATA%\crypto-backtester\Cache\` on Windows. It is worked out with the
  standard library, with no new dependency.
- The location can be overridden, highest priority first: a `cache_dir` argument (API) or
  `--cache-dir` (CLI), then the environment variable `CRYPTO_BACKTESTER_CACHE_DIR`. This lets
  the owner point the cache at another drive.
- Layout: `<cache>/binance-vision/<market>/<SYMBOL>/<interval>/<SYMBOL>-<interval>-<YYYY-MM-DD>.parquet`.
  There is one file per day, written atomically (temporary file, then rename), so an
  interrupted run never leaves a half-written day behind.
- Ways to keep the cache small:
  - an option to load with no cache at all: download, convert in memory, return, keep nothing;
  - a CLI command that shows the cache size per market, symbol and interval;
  - a CLI command that deletes cached data for a symbol, interval or date range.
- REST-filled days are cached only when the day is closed (it ended in UTC). Today's partial
  day is always fetched again.

**Ways to use it**
- **Python API**: one call (shape settled in design, for example
  `load_klines(symbol, interval, start, end, market="spot", cache_dir=None)`) that fetches
  only what is missing and returns the DataFrame.
- **CLI**: `python -m app.data` with these subcommands:
  - `download` fills the cache ahead of time and reports what it fetched, skipped (already
    cached), filled from REST, or could not find;
  - `cache-info` shows the cache size;
  - `cache-clear` deletes cached data.
  For example: `python -m app.data download BTCUSDT 1h 2024-01-01 2024-01-31 --market spot`.

**Downloads**
- Up to 4 Vision files are downloaded in parallel, using a thread pool.
- Timeouts: 10 s to connect, 60 s to read.
- Retries: 3 at most, with exponential backoff (1 s, 2 s, 4 s, plus jitter), on connection
  errors, timeouts, HTTP 429 and 5xx responses. A `Retry-After` header is honoured. HTTP 418
  (Binance's IP ban) stops the run with a clear message.
- A 404 is not retried: it means the day is not on Vision, so it goes to the REST fill.
- REST requests run one at a time, ask for the maximum page size, and pause when the rate-limit
  weight headers come close to the limit.
- HTTP client: the standard library (`urllib.request`), with no new dependency. The fetch
  function can be injected so tests can stub it.

How to check it is done:
- The automated tests run with no network access. They use small fixture files that have the
  real layouts (spot without a header row and in microseconds after 2025, futures with a
  header row, and REST JSON responses).
- The tests show that:
  - a multi-day range loads into the expected rows and schema;
  - a range that crosses 2025-01-01 has continuous UTC timestamps;
  - a Vision day returning 404 is filled from REST;
  - a day missing from both sources is reported as a gap;
  - a second load makes no fetch;
  - the cache holds Parquet files only (no zip);
  - spot and futures fixtures for the same candles load into identical DataFrames.
- `python -m app.data download …` and `cache-info` work against the stubbed transport.
- Build, test and lint stay green.

## Affected users and systems
- The owner, as the person running backtests. Later changes (strategies, the backtest engine)
  will build on this module.
- `app/`: a new data package (`app/data/`, with a `__main__` for the CLI). `tests/`: a new
  `test_<area>.py` with offline fixtures.
- External services, all public and read-only, with no account or API key:
  - `data.binance.vision` (the files);
  - the Binance spot REST API (`api.binance.com`, or the market-data-only
    `data-api.binance.vision`);
  - the USDⓈ-M REST API (`fapi.binance.com`).
- The owner's local disk: the cache directory, outside the repo by default.
- Dependencies: **polars** becomes the project's first runtime dependency (`pyproject.toml`).
  There is no HTTP library dependency, because `urllib` is used.
- CI: `.github/workflows/ci.yml` installs only pytest and ruff today, so it must also install
  the project (`pip install -e .` or polars).

## Constraints
- No secrets, accounts or API keys. Both Binance Vision and the REST klines endpoints are
  public.
- No personal data. Market data only.
- Tests never touch the network. The CI runner and the SDLC sandbox do not allow the Binance
  hosts (`sandbox.allowed_domains` is empty), so every fetch is tested through a stubbed
  transport and local fixtures.
- Treat downloaded files and REST responses as untrusted input:
  - check each zip against Binance's `.CHECKSUM`;
  - extract only the expected CSV, in memory or in a temporary location, and never write
    outside the cache directory;
  - validate symbol, interval, market and dates before building a URL or a path from them;
  - check the shape of REST JSON before using it.
- Do not commit cached data, and never write data into the repository by default.
- Respect Binance's rate limits. The data layer must never get the owner's IP banned (418).
- Python >= 3.10, type hints on public functions, ruff clean at line length 100, version kept
  in step between `app/__init__.py` and `pyproject.toml`.
- **Guardrail dependency.** `sdlc.yaml` `commands.setup` is `python -m pip install pytest
  ruff`, and `CLAUDE.md` documents the same. The framework's phase jobs run that command before
  each phase, so polars would not be installed there and the build gate's tests would fail. Both
  files are protected and only the owner can change them, in a reviewed PR. Before the build,
  `commands.setup` must also install the project's runtime dependencies (for example
  `python -m pip install -e . pytest ruff`). This change does not edit them.
- Out of scope:
  - monthly files, aggregated trades, COIN-M futures, other exchanges;
  - resampling between intervals;
  - several symbols in one call;
  - a size cap or automatic eviction of the cache (the clear command covers it for now);
  - a console script in `pyproject.toml` (can come later; `python -m app.data` works without
    installing).

## Open questions
- REST access by region: `api.binance.com` and `fapi.binance.com` refuse some regions (HTTP
  451). For spot, `data-api.binance.vision` is a public market-data-only mirror; the futures
  API has none. Which spot host is the default, and what does the loader do when the REST fill
  is refused? (Proposed: report those days as gaps, with the reason.)
- How are gaps returned to the API caller: an exception listing them, or a result object with
  the frame and the gaps? The CLI prints them either way.
- Is one Parquet file per day small enough? A month or year per file saves per-file overhead
  but complicates updates. Design measures one year of BTCUSDT 1m both ways and picks one.
- Which Parquet compression codec and level (zstd is the expected choice)?

## Examples/References
- Binance Vision bucket browser: https://data.binance.vision/
- Binance public data repository (file layouts, column list, checksum files, the 2025
  microsecond change): https://github.com/binance/binance-public-data
- Example file URLs:
  - spot: `https://data.binance.vision/data/spot/daily/klines/BTCUSDT/1h/BTCUSDT-1h-2024-01-01.zip`
    (and `.zip.CHECKSUM` beside it);
  - USDⓈ-M: `https://data.binance.vision/data/futures/um/daily/klines/BTCUSDT/1h/BTCUSDT-1h-2024-01-01.zip`.
- REST klines documentation:
  - spot: https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints#klinecandlestick-data
  - USDⓈ-M: https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Kline-Candlestick-Data
