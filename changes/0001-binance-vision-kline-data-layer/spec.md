# Spec: Binance Vision kline data layer
Change id: 0001. Status: proposed. Produced by: sdlc plugin 1.0.50, /sdlc-design prompt v1 (article p.14). Skills: coding-standards, security-baseline, ux-and-brand, data-conventions, definition-of-done (plugin 1.0.50); overrides: none; policy sources: none

## Requirements

Function
- R1. A new package `app/data/` loads klines for one symbol, one interval and one market
  (`spot` or `um`, USDⓈ-M futures) per call, over an inclusive UTC date range.
- R2. Each day comes from the Binance Vision daily zip
  (`https://data.binance.vision/data/spot/daily/klines/<SYMBOL>/<INTERVAL>/…` or
  `…/data/futures/um/daily/klines/…`); a day Vision answers with 404 is filled from the public
  REST klines endpoint (spot `GET /api/v3/klines`, USDⓈ-M `GET /fapi/v1/klines`), with no API key.
- R3. The result is one polars DataFrame: one row per candle, sorted by `open_time`, no
  duplicate `open_time`, with the fixed schema of Design § Schema whatever the market or
  source.
- R4. Every time column is one UTC type; microsecond files (spot from 2025-01-01) and
  millisecond files (older spot, futures, REST) give the same values for the same candle, and a
  range crossing 2025-01-01 is one continuous series.
- R5. A requested range never comes back silently short: any missing candle is reported as a
  gap with its reason (Design § Gaps).
- R6. Each closed day is fetched at most once into the cache; loading a fully cached range
  makes no network request.
- R7. The cache holds zstd-compressed Parquet only, one file per day, at
  `<cache>/binance-vision/<market>/<SYMBOL>/<interval>/<SYMBOL>-<interval>-<YYYY-MM-DD>.parquet`,
  written atomically; no zip, CSV or temporary file stays behind.
- R8. Cache root, highest priority first: the `cache_dir` argument / `--cache-dir` option, the
  `CRYPTO_BACKTESTER_CACHE_DIR` environment variable, then the platform default
  (`%LOCALAPPDATA%\crypto-backtester\Cache\` on Windows; `$XDG_CACHE_HOME/crypto-backtester/`,
  else `~/.cache/crypto-backtester/`, elsewhere), worked out with the standard library.
- R9. `cache=False` loads with no cache: it neither reads nor writes any cache file.
- R10. REST-filled days are cached only when the UTC day has ended; the current day is always
  fetched again.
- R11. CLI `python -m app.data` with `download`, `cache-info` and `cache-clear` (Design § CLI).
- R12. Downloads: at most 4 Vision files in parallel; timeouts 10 s connect, 60 s read; at most
  3 retries with backoff 1 s, 2 s, 4 s plus jitter on connection errors, timeouts, 429 and 5xx;
  `Retry-After` honoured; 404 never retried; 418 stops the run with a clear message. REST
  calls run one at a time, at the maximum page size, and pause when the used-weight header nears
  the limit.
- R13. HTTP goes through the standard library (`urllib.request`); the fetch function is
  injectable so tests stub it. polars is the only new runtime dependency.

Out of scope (intent): monthly files, aggregated trades, COIN-M, other exchanges, resampling,
several symbols per call, a cache size cap or eviction, a console script.

Policies applied
- coding-standards: rule 1, `CLAUDE.md` conventions (Python >= 3.10, type hints on public
  functions, ruff at line length 100, one test module per area named `test_<area>.py`);
  rule 4, every behaviour ships with an offline test; rule 5, polars is a new dependency, so it
  gets a `plan.md` Risks line and rides on the owner's merge; rule 7, small single-purpose modules.
- security-baseline: rule 2 applies (downloads and REST bodies are untrusted input: schema,
  size bounds, no path built from unvalidated text; Design § Untrusted input); rule 3, no
  secret anywhere (the endpoints are public); rule 6, polars has its Risks line, TLS
  verification stays on, no `eval`/`exec`/`pickle` or shell on external data; rule 7, tests
  make no outbound call (`sandbox.allowed_domains` is empty), and the runtime calls only the
  three Binance hosts of Design § Sources. Rule 1 (authentication) does not apply: the change
  serves no endpoint. Rule 5 (audit) does not apply: the project has no audit log and the cache
  holds public data. Rule 8: no risk-list item is touched (below).
- data-conventions: rule 1, every stored field is public market data, no personal or sensitive
  field; rule 2, the schema is defined once, in the package (the project has no `schemas/`);
  rule 3, no migration (a new cache outside the repository); rule 4 does not apply (no event or
  external API is published); rule 5, the cache stores only the columns the intent asks for
  (the "ignore" column is dropped) and is kept until the owner clears it; rule 6, the dataset's
  owner is the repository owner and its freshness is "closed days are immutable, the current
  day is refetched".
- ux-and-brand: the change has no screen; rules 3 and 4 apply to CLI output and error
  messages (every command reports its outcome, errors say what happened and what to do next,
  no stack trace for an expected failure); rules 1, 2, 5, 6 and 7 do not apply (no mock, no
  component library, no visual loop).
- definition-of-done: build, test and lint stay green with their output pasted; tests never
  touch the network.
- Risk list (`sdlc.yaml`): none of `auth`, `data migrations`, `money movement`,
  `production config` applies: public read-only market data, no account, no order, no schema
  migration, `deploy.action: none`.

## Design

### Shape
`app/data/` is a package with one responsibility per module: parameter validation, HTTP
transport (retries, backoff, rate-limit pauses), the Vision source (URL, checksum, safe
extraction), the REST source (paging, JSON shape check), normalisation to the schema, the
cache (root, layout, atomic write, read, info, clear), the loader (orchestration and gaps) and
the CLI (`__main__`). Nothing outside `app/data/` changes in `app/`; `app.__version__` stays
`0.1.0` (the intent asks no release, and `tests/test_smoke.py` pins it).

### Public API (`from app.data import …`)
- `load_klines(symbol: str, interval: str, start: date | str, end: date | str, *,
  market: str = "spot", cache_dir: str | Path | None = None, cache: bool = True,
  fetch: Fetch | None = None) -> pl.DataFrame` — fetches only what is missing; raises
  `KlineGapError` when any candle in the range is missing.
- `KlineGapError(Exception)` with `.gaps: tuple[Gap, ...]` and `.frame: pl.DataFrame` (the
  rows that were found, in the same schema).
- `Gap` (frozen dataclass): `start` and `end` (open times of the first and last missing candle,
  UTC), `candles: int`, `reason: str`.
- `Fetch` — a callable `(url: str) -> HttpResponse` with `HttpResponse(status: int,
  headers: Mapping[str, str], body: bytes)`; the default uses `urllib.request` with the
  timeouts of R12. Retries, backoff and rate-limit pauses wrap any `Fetch`, so the stub sees
  the same retry behaviour; the sleep function is injectable for tests.
- `cache_info(...)` and `clear_cache(...)`, which back the CLI.
- `InvalidRequestError(ValueError)` for bad parameters, `BinanceBanError` for HTTP 418.

### Parameters (validated before any URL or path is built)
- `market` ∈ {`spot`, `um`}.
- `interval` ∈ {`1s` (spot only), `1m`, `3m`, `5m`, `15m`, `30m`, `1h`, `2h`, `4h`, `6h`,
  `8h`, `12h`, `1d`}: the daily-file intervals, each dividing a UTC day exactly.
- `symbol`: upper-cased, then must match `^[A-Z0-9]{2,30}$`.
- `start`, `end`: ISO dates or `date`; `start <= end`; `end` no later than today (UTC).

### Sources
- Vision: `https://data.binance.vision/data/<spot|futures/um>/daily/klines/<SYMBOL>/<INTERVAL>/<SYMBOL>-<INTERVAL>-<YYYY-MM-DD>.zip`
  and the `.zip.CHECKSUM` beside it. Days run through a pool of 4 threads.
- REST (sequential, after the Vision pass): spot `https://data-api.binance.vision/api/v3/klines`
  (limit 1000), USDⓈ-M `https://fapi.binance.com/fapi/v1/klines` (limit 1500). Consecutive
  missing days form one range, paged with `startTime`/`endTime` in milliseconds; an empty
  page ends the range. Before each call, when `X-MBX-USED-WEIGHT-1M` of the last response is at
  80 % or more of the documented per-minute limit (spot 6000, USDⓈ-M 2400), the run sleeps to
  the next minute boundary.
- Retries (both sources): R12. A `Retry-After` longer than 60 s stops the run with the wait
  in the message instead of sleeping. 418 raises `BinanceBanError` at once and cancels the
  pending Vision downloads. Any other 4xx from REST (400 for an unknown symbol, 451 for a
  refused region) ends the REST fill for that range; its days become gaps with the status in
  the reason.

### Untrusted input
- Zip: the body is at most 64 MiB; its SHA-256 must equal the first token of the `.CHECKSUM`
  body; it must hold the member `<SYMBOL>-<INTERVAL>-<YYYY-MM-DD>.csv` (anything else is
  ignored), whose uncompressed size is at most 256 MiB; it is read in memory, never extracted
  to disk. A missing or mismatching checksum makes the day a gap ("checksum mismatch" /
  "checksum unavailable") and nothing is cached.
- CSV: an optional header row (first field not numeric) is skipped; each row needs 12 fields
  (the 12th, "ignore", is dropped); a row that does not parse makes the day a gap
  ("malformed Vision file").
- REST JSON: the body must be a list of lists of at least 11 items, with numeric times and
  numeric strings for prices and volumes; anything else ends the fill with a gap ("unexpected
  REST response").
- Paths: built only from validated parts; the final path is checked to lie inside
  `<cache>/binance-vision/`. `cache-clear` deletes only files matching the day-file name
  pattern under that subtree, never the cache root itself.

### Schema
| column | dtype |
|---|---|
| `open_time` | `Datetime("ms", "UTC")` |
| `open`, `high`, `low`, `close`, `volume` | `Float64` |
| `close_time` | `Datetime("ms", "UTC")` |
| `quote_volume` | `Float64` |
| `trades` | `Int64` |
| `taker_buy_base_volume`, `taker_buy_quote_volume` | `Float64` |

Unit detection per file: an `open_time` of 10^14 or more is microseconds. Times convert to
milliseconds by floor division, so a microsecond `close_time` ending `…999999` and the
millisecond `…999` of a futures or REST row become the same value; the same candle from any
market or source gives an identical row.

### Cache
- Each day is a `DataFrame.write_parquet(compression="zstd", compression_level=3)` to a
  temporary file in the same directory, then `os.replace` onto the final name.
- A closed day is written whatever its source; the current UTC day is never written. A day
  with no data at all is not written, so it is asked for again on the next load.
- `load_klines` reads every cached day of the range, fetches the others, concatenates, sorts
  by `open_time` and drops duplicate `open_time`s.

### Gaps
The expected candles are the interval grid from `start` 00:00 UTC to the end of `end`, or, for
the current day, up to the last candle whose `close_time` has passed (an unfinished candle is
dropped: it would leak a still-moving price into a backtest). Every expected open time absent
from the frame is missing; consecutive missing candles form one `Gap`, with the reason of its
day: "not on Vision (404) and REST returned no candles", "REST refused (HTTP 451)", "checksum
mismatch", "missing candles in source file", and so on. When any gap exists, `load_klines`
raises `KlineGapError` with the gaps and the partial frame.

### CLI (`python -m app.data`, argparse)
- `download SYMBOL INTERVAL START END [--market spot|um] [--cache-dir DIR]` — fills the cache
  and prints one line per day group: fetched, skipped (already cached), filled from REST, or
  not found (with the gap reason), then a one-line total. Exit 0 when nothing is missing, 1
  when any gap was reported.
- `cache-info [--market M] [--symbol S] [--interval I] [--cache-dir DIR]` — a table of
  market, symbol, interval, day files and size (human-readable), and the total.
- `cache-clear SYMBOL [INTERVAL] [--market spot|um] [--start DATE] [--end DATE]
  [--cache-dir DIR]` — deletes the matching day files and prints how many and how much.
- Expected failures (invalid parameter, 418, a too-long `Retry-After`) print one line on
  stderr saying what happened and what to do, and exit 2; no traceback.
- `main(argv, fetch=None) -> int` is the entry point, so tests drive it with the stub.

### Dependencies and CI
- `pyproject.toml` gains `dependencies = ["polars>=1.0"]`.
- The project CI (`.github/workflows/ci.yml`, not a guardrail) installs polars beside pytest
  and ruff, pinned like them. The SDLC phase jobs already install it: `commands.setup` on the
  default branch is `python -m pip install pytest ruff polars` (the owner's commit 801dc74),
  which settles the intent's "guardrail dependency" constraint.

### What stays unchanged
`app/__init__.py`, `tests/test_smoke.py`, every guardrail file. No data is written into the
repository.

### Assumptions (the intent is silent; see Flagged concerns)
A1 millisecond precision for every time column; A2 `Float64` for prices and volumes; A3 the
interval list and symbol pattern above; A4 the size bounds (64 MiB zip, 256 MiB CSV); A5 the
80 % weight threshold and the documented weight limits; A6 a `Retry-After` over 60 s stops
the run; A7 `cache=False` neither reads nor writes the cache; A8 a day with no data is not
cached; A9 the current day's unfinished candle is dropped; A10 a candle missing inside a source
file is a gap, so a known exchange outage raises unless the caller uses `KlineGapError.frame`;
A11 `cache-clear` defaults to `--market spot`; A12 `download` exits 1 when anything is missing.

## Open questions from intent
- "Which spot host is the default, and what does the loader do when the REST fill is
  refused?" — answered by design choice, not by the codebase or a policy:
  `data-api.binance.vision` (the market-data-only mirror the intent names) is the spot
  default; USDⓈ-M has no mirror and uses `fapi.binance.com`. A refused fill (451, or any 4xx
  but 418) reports its days as gaps with the status in the reason, as the intent proposes.
  Open as a flagged concern, since it is a choice the owner did not make.
- "How are gaps returned to the API caller: an exception listing them, or a result object
  with the frame and the gaps?" — answered: both in one: `load_klines` returns the DataFrame
  when the range is complete and raises `KlineGapError` carrying `.gaps` and `.frame`
  otherwise (Design § Gaps). This keeps the one-call API returning a DataFrame (intent
  "Python API") and makes a short frame impossible to miss (intent: "never a silently short
  frame"); the intent delegates the shape to design.
- "Is one Parquet file per day small enough? … Design measures one year of BTCUSDT 1m both ways
  and picks one." — carried forward: the design run has no network (`sandbox.allowed_domains`
  is empty) and writes no code, so it cannot measure. The design keeps one file per day (the
  intent's own layout, its atomic per-day writes and its closed-day REST caching all assume
  it); the build measures one year of synthetic 1m candles with realistic price movement,
  one file per day against one file per year, and records the two sizes in the change's
  evidence. The owner decides on that figure; switching layout would be a later change.
- "Which Parquet compression codec and level (zstd is the expected choice)?" — zstd, as
  expected; level 3 (the zstd default) is a design choice, measured with the question above.

## Flagged concerns
- decided (by panel #1): Keep data-api.binance.vision as the fixed spot REST host (no switch) and refused fills (451, any non-418 4xx) as gaps with the status; the weight pause must treat a missing X-MBX-USED-WEIGHT-1M as unknown and pause conservatively, pinned by an offline no-header test. — Spot REST host and refused fills: the design picks `data-api.binance.vision` as the spot
  default with no option to switch, and turns a 451 or other 4xx REST refusal into reported
  gaps; the intent left the default open and only proposed the refusal behaviour.
- Storage layout and codec level not measured: the intent asked the design to measure one
  year of BTCUSDT 1m as daily against larger files; the design keeps one file per day with
  zstd level 3 unmeasured, and the measurement moves to the build on synthetic data.
- Assumptions where the intent is silent (A1–A12 in Design § Assumptions), the weightiest
  being A10: a candle missing inside a Vision file (a real exchange outage) raises
  `KlineGapError`, so a long range over a known outage always needs the caller to take
  `.frame`.

## Acceptance
- An offline pytest module for the data layer, run through a stubbed `Fetch` and fixture
  files with the real layouts (spot without a header and in microseconds from 2025, futures
  with a header, REST JSON), proves:
  - a multi-day range loads into the expected rows, order and schema (Design § Schema);
  - a range crossing 2025-01-01 has continuous UTC `open_time`s, one interval apart;
  - a Vision 404 day is filled from REST;
  - a day missing from both sources raises `KlineGapError` with that day's gap and reason;
  - a second load of the same range makes zero fetch calls;
  - the cache holds `.parquet` files only, at the layout of R7;
  - spot and futures fixtures for the same candles load into identical DataFrames;
  - a checksum mismatch is a gap and caches nothing; 418 raises `BinanceBanError`; 429/5xx
    are retried at most 3 times and 404 never; invalid symbol, interval, market or dates
    raise `InvalidRequestError` before any fetch; `cache=False` writes nothing; the current
    day is not cached.
- `python -m app.data download …` and `cache-info` run against the stub (through
  `main(argv, fetch=…)`) and print the outcome; `cache-clear` deletes only matching day files.
- Build `python -m compileall -q .` (no output, exit 0), test `python -m pytest` (all pass,
  the smoke test included), lint `python -m ruff check .` (`All checks passed!`).
- The build's evidence records the size of one synthetic year of 1m candles as 365 daily files
  and as one file (open question 3).
