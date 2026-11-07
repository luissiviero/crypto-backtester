# Plan: Replace Binance with KuCoin as the market-data source (from intent.md 2026-11-06, spec.md 2026-11-07)

## Files that change
- `app/data/vision.py` — deleted.
- `app/data/params.py` — `MARKETS = ("spot", "futures")`; `1s` and `SPOT_ONLY_INTERVALS`
  removed; `FUTURES_REFUSED_INTERVALS = frozenset({"6h"})`; `SPOT_TYPES` (`"1m": "1min"`,
  ... `"1h": "1hour"`, ... `"1d": "1day"`) and `FUTURES_GRANULARITY` (`"1m": 1` ... `"1d":
  1440`, no `6h`); `validate_symbol(symbol, market)` with `_SPOT_SYMBOL =
  [A-Z0-9-]{2,30}` and `_FUTURES_SYMBOL = [A-Z0-9]{2,25}USDTM`; messages name KuCoin examples
  (`BTC-USDT`, `XBTUSDTM`) and `spot` / `futures`.
- `app/data/http.py` — `BinanceBanError` and the 418 branch removed; `WEIGHT_HEADER`,
  `WEIGHT_THRESHOLD` and `WeightPacer` replaced by `REMAINING_HEADER =
  "gw-ratelimit-remaining"`, `RESET_HEADER = "gw-ratelimit-reset"`, `RATE_LIMIT_RESERVE =
  100`, `MAX_RATE_LIMIT_WAIT = 60.0` and `RateLimitPacer` (`wait()`, `record()`); module and
  `DownloadError` docstrings without Binance.
- `app/data/schema.py` — eight-column `SCHEMA`; `frame_from_spot_rows(rows, interval_ms)`
  and `frame_from_futures_rows(rows, interval_ms)`; `frame_from_csv`, `frame_from_rest`,
  `CSV_FIELDS`, `INT_COLUMNS`, `MICROSECOND_THRESHOLD`, `_to_milliseconds`, `_is_number`
  and the `csv`/`io` imports removed.
- `app/data/rest.py` — KuCoin endpoints, `parse_answer`, spot and futures paging,
  `RestRange` with `covered_from_ms` / `covered_until_ms`; `pacer_for` replaced by
  `RateLimitPacer()`.
- `app/data/cache.py` — `SUBTREE = "kucoin"`, `file_name` moved here, hyphen in the
  day-file pattern, per-market symbol checks, `CachePathError` docstring.
- `app/data/loader.py` — Vision pass and thread pool removed; per-day outcomes from the
  covered span; new gap reasons; `_worth_caching`, `find_gaps`, docstrings.
- `app/data/__main__.py` — KuCoin wording, `futures` market, help epilogs, labels, total line.
- `app/data/__init__.py` — docstring; `BinanceBanError` out of the import and `__all__`.
- `scripts/measure_storage.py` — eight-column synthetic rows, `--from-cache BTC-USDT 1m`
  usage, `validate_symbol(symbol, market)`.
- `tests/kucoin_stub.py` — new: `KuCoin` stub Fetch, `sequence`, `fixture`, `utc`,
  `cached_days` (under `kucoin/`), synthetic row builders in the captured formats.
- `tests/fixtures/kucoin/` — new: `spot-BTC-USDT-1hour-2026-10-01.json`,
  `futures-XBTUSDTM-60-2026-10-01.json`, `futures-XBTUSDTM-1-2026-10-01.json`,
  `spot-unknown-symbol.json`, `futures-unknown-symbol.json`,
  `futures-from-in-seconds.json` — byte copies of the captured bodies in
  `references/capture/` (same content, shorter names).
- `tests/test_data.py` — rewritten for KuCoin (tests listed in Proof).
- `tests/test_data_cli.py` — rewritten for KuCoin.
- `tests/binance_stub.py` — deleted.
- `tests/fixtures/binance/` — deleted (all six files).
- `changes/0003-replace-binance-with-kucoin-as-the-marke/plan.md` — this file, when the
  build departs from it.

Unchanged: `pyproject.toml`, `.github/workflows/ci.yml`, `app/__init__.py` (version 0.1.0),
`tests/test_smoke.py`.

For the owner, not the run (guardrail file; edit in a PR of your own after this change
reaches `main`), `CLAUDE.md`:
- lines 5 and 6 become: `` `app/data/`: KuCoin spot and USDT-margined perpetual klines from KuCoin's public REST API `` /
  `as polars frames, cached per day as Parquet outside the repository; its CLI is`;
- line 30: remove `vision, ` from the module list;
- lines 36 and 37: `tests/binance_stub.py` becomes `tests/kucoin_stub.py` and
  `tests/fixtures/binance/` becomes `tests/fixtures/kucoin/`.
The Setup and Test lines and the CI install step need no change (no new dependency, same
`testpaths`).

## Order of work
1. **Parameters** (`params.py`). Markets, intervals, the two KuCoin interval tables,
   `validate_interval(interval, market)` refusing `6h` on futures with
   `interval '6h' is not offered on the futures market`, `validate_symbol(symbol, market)`.
   `make_request` passes the market to `validate_symbol`. Keep `parse_date`, `day_start_ms`,
   `KlineRequest` as they are.
2. **Schema** (`schema.py`). `SCHEMA` = `open_time`, `open`, `high`, `low`, `close`,
   `volume`, `close_time`, `quote_volume` with today's dtypes. Row parsers:
   - `frame_from_spot_rows(rows: object, interval_ms: int)`: `rows` must be a list; each row
     a list of exactly 7 `str`; time = `int(row[0]) * 1000`; open = row[1], close = row[2],
     high = row[3], low = row[4], volume = row[5], quote_volume = row[6].
   - `frame_from_futures_rows(rows: object, interval_ms: int)`: each row a list of exactly 7
     `int`/`float` (not `bool`); time = `row[0]` as an `int` (a float time with a fraction is
     malformed); open, high, low, close, volume, quote_volume in order.
   - Shared: `_int64` bound on the time, `_finite` on every number, `close_time = open_time +
     interval_ms - 1`, then the existing cast to `Datetime("ms", "UTC")`. Every failure is
     `MalformedDataError`.
3. **Transport** (`http.py`). Remove `BinanceBanError` and the 418 branch in `with_retries`
   (418 is then returned like any 4xx). `RateLimitPacer.wait()`: no previous answer → return;
   `remaining` or `reset` header missing or not an `int` → `sleep(UNKNOWN_WEIGHT_WAIT)`;
   `remaining < RATE_LIMIT_RESERVE` → `sleep(min(max(reset, 0) / 1000, MAX_RATE_LIMIT_WAIT))`;
   else no sleep. Keep `_int_or_none`. In `with_retries`, when a 429 has no usable
   `Retry-After`, `retry_after = min(max(reset, 0) / 1000, MAX_RATE_LIMIT_WAIT)` from
   `gw-ratelimit-reset` (when that header is an integer), so the existing
   `sleep(max(backoff + jitter, retry_after))` waits for the pool to refill; a 5xx and a
   429 without either header keep the 1, 2, 4 s backoff (panel #2).
4. **REST** (`rest.py`).
   - Constants: `SPOT_URL = "https://api.kucoin.com/api/v1/market/candles"`,
     `FUTURES_URL = "https://api-futures.kucoin.com/api/v1/kline/query"`, `SUCCESS_CODE =
     "200000"`, `UNEXPECTED_RESPONSE = "unexpected KuCoin response"`, `MAX_MESSAGE = 200`.
   - `spot_url(request, start_ms, end_ms)`: `urlencode({"symbol", "type": SPOT_TYPES[...],
     "startAt": start_ms // 1000, "endAt": end_ms // 1000})`.
     `futures_url(request, start_ms, end_ms)`: `{"symbol", "granularity":
     FUTURES_GRANULARITY[...], "from": start_ms, "to": end_ms - 1}`.
   - `parse_answer(response, parse_rows, interval_ms) -> tuple[pl.DataFrame | None, str |
     None]`: body longer than `MAX_BODY_BYTES` → `UNEXPECTED_RESPONSE`; JSON decode
     (`ValueError`, `RecursionError`) → for HTTP 200 `UNEXPECTED_RESPONSE`, else `KuCoin
     refused (HTTP <n>)`; envelope not a dict → same; `code` (compared as `str`) not
     `SUCCESS_CODE` or status not 200 → `KuCoin refused (HTTP <n>, code <c>): <msg>` where
     `msg` is `str(payload.get("msg", ""))` with every non-printable character removed,
     cut to `MAX_MESSAGE` (`code` cut to 20 and cleaned the same way); `data` → `parse_rows`
     (`MalformedDataError` → `UNEXPECTED_RESPONSE`).
   - `fetch_range(fetch, pacer, request, start_ms, end_ms) -> RestRange` dispatches on the
     market:
     - spot (backwards): `window_end = end_ms`; loop while `window_end > start_ms`: wait,
       fetch `spot_url(request, start_ms, window_end)`, record, parse; failure → stop with
       `covered = [window_end, end_ms)`; keep rows with `start_ms <= open < window_end`;
       empty → `covered = [start_ms, end_ms)`, stop; `oldest = min(open)`; append;
       `window_end = oldest` (strictly smaller than before, else `UNEXPECTED_RESPONSE`).
     - futures (forwards): `window_start = start_ms`; loop while `window_start < end_ms`:
       fetch `futures_url(request, window_start, end_ms)`; failure → `covered =
       [start_ms, window_start)`; keep rows with `window_start <= open < end_ms` (drops the
       end-of-window row); empty → `covered = [start_ms, end_ms)`, stop; `newest = max(open)`;
       append; `window_start = newest + interval_ms`.
       A loop that ends because the window closed is fully covered too.
     - Each `fetch(...)` call sits in `try` / `except DownloadError as error`: paging stops
       with `failure = str(error)`, `error` kept, and the coverage so far (as for a
       refused page) (panel #3).
     - `RestRange(frame, failure, covered_from_ms, covered_until_ms, error=None)`; the
       frame is the concatenation (sorting and de-duplication stay in the loader's
       `_on_grid`).
5. **Cache** (`cache.py`). `SUBTREE = "kucoin"`; `file_name(request, day)` moves from
   `vision.py`; `_DAY_FILE` symbol group `[A-Z0-9-]{2,30}` (the interval `[0-9]{1,2}[mhd]`
   and the date anchor it; the existing check that the symbol equals the directory name
   stays); `cache_info`: with a market, `validate_symbol(symbol, market)`; without one,
   accept a symbol valid for either market, else raise the spot error; `clear_cache`
   validates with its market.
6. **Loader** (`loader.py`). Remove `threading`, `ThreadPoolExecutor`, `vision`,
   `VISION_WORKERS`, `VISION`, `_vision_pass`, `_Cancelled`, `MISSING_IN_FILE`,
   `MISSING_IN_REST`. Reasons: `NO_CANDLES = "no candles; check the symbol exists"`,
   `NO_CANDLES_ON_DAY = "no candles on this day"`, `BEFORE_FIRST = "no candles before {day}:
   the date may be before KuCoin's oldest candle for this symbol"`.
   `sync_days`: cached closed days first; the rest, grouped by `_consecutive_ranges`, go
   through `_rest_pass` with one `RateLimitPacer` for the run. `_rest_pass` per range: call
   `fetch_range`; `first_day_with_rows` = the earliest day with a row; for each day:
   `in_span = covered_from <= day_start and day_start + DAY_MS <= covered_until` (for the
   current day, `covered_until >= day_start + DAY_MS` still holds because the range end is
   the day's end); rows of the day; `in_span and rows` → `REST`; `not in_span` →
   `MISSING`, reason = the failure; `in_span and not rows` → `MISSING`, reason
   `NO_CANDLES` when the range has no row, `BEFORE_FIRST` when the day is before
   `first_day_with_rows`, else `NO_CANDLES_ON_DAY`. After every day of the range is
   handed to `settle` (which writes complete closed days to the cache), `if answer.error
   is not None: raise answer.error` (panel #3); keep the `sync_days` docstring's promise
   that days fetched before a stop stay cached. `_worth_caching`: `source == REST`.
   `find_gaps`: skip outcomes that are not `MISSING`; the rest as today. `_gap_reason`
   returns `outcome.reason or NO_CANDLES`. `load_klines` docstring: rows exist only for
   intervals with trades (a short frame is normal; never assume one row per interval);
   futures `volume` counts contracts, spot `volume` coins, compare `quote_volume`; and the
   deprecation note: the `trades`, `taker_buy_base_volume` and `taker_buy_quote_volume`
   columns, `BinanceBanError`, the `um` market and the `1s` interval were removed because
   KuCoin does not publish them (panel #1).
7. **CLI and package** (`__main__.py`, `__init__.py`). Description `KuCoin kline data and its
   local cache.`; `download` epilog with the two notes of step 6; `cache-clear` epilog:
   `KuCoin may not serve old futures days again: a cleared futures day can be lost.`; use
   `argparse.RawDescriptionHelpFormatter` only if the epilog needs line breaks; labels
   `loader.CACHED: "skipped, already cached"`, `loader.REST: "fetched from KuCoin"`; total
   line `Total for <symbol> <interval> <market>: <n> fetched, <n> skipped, <n> not found;
   <n> candles missing. Cache: <root>`; drop the per-gap "missing inside a file" lines.
   `__init__.py` docstring `The kline data layer: KuCoin REST klines and a local Parquet
   cache.`, followed by the same deprecation note as `load_klines`; remove
   `BinanceBanError`.
8. **Script** (`scripts/measure_storage.py`): the synthetic candle dict without `trades`
   and the two taker columns; `validate_symbol(symbol, market)`; usage line `BTC-USDT`.
9. **Tests.** Copy the six captured bodies into `tests/fixtures/kucoin/` (names in Files that
   change). Write `tests/kucoin_stub.py`: `KuCoin(headers=None, spot_page=1500,
   futures_page=200)` with `spot_rows` / `futures_rows` lists, `add_spot(name)`,
   `add_futures(name)` (extend from a fixture's `data`), `add_spot_synthetic(start, count,
   interval_ms)` / `add_futures_synthetic(...)` building rows in the captured formats (spot:
   7 strings, seconds; futures: 7 numbers, ms) with `high` the largest and `low` the
   smallest price, `refuse(match, response)` to answer a chosen page with a given
   response, and `__call__` that serves spot `[startAt, endAt)` newest first keeping the
   newest `spot_page`, futures `[from, to]` oldest first keeping the oldest
   `futures_page`, in the KuCoin envelope with default headers
   `{"gw-ratelimit-remaining": "1997", "gw-ratelimit-reset": "29999"}`, any other URL 404,
   and records `calls`. Then rewrite `tests/test_data.py` and `tests/test_data_cli.py`
   with the tests in Proof, then delete `tests/binance_stub.py` and
   `tests/fixtures/binance/`.
10. **Delete `app/data/vision.py`**, grep `app/` and `scripts/` for `binance`, `vision`,
    `um"` (case-insensitive) and clean every hit except the deprecation notes of steps 6
    and 7 (the `load_klines` docstring and the `app/data/__init__.py` module docstring,
    spec R6 and R8, panel #4); run build, test and lint and paste the output.

Steps 1–8 leave the old tests broken until step 9; commit 1–9 as one or a few commits that
each keep `plan.md` in step, and run the suite after step 9.

## Risks
- **Riskiest: paging and completeness (steps 4 and 6).** A wrong window rule either loses
  candles silently (a day marked complete that is not) or loops. Guards: every page must move
  the window strictly (else `UNEXPECTED_RESPONSE`), which also bounds the loop; coverage only
  grows from answered pages; the stub enforces the measured rules (spot end exclusive and
  newest kept, futures end inclusive and oldest kept), and tests cover page caps smaller than
  the range, a refusal on the second page (the days after it, or before it on spot, are
  gaps), and the end-of-window row.
- **The rule "an empty answer means the window has no candle"** rests on the measured
  behaviour (spot keeps the newest, futures the oldest). If KuCoin returned an empty list for
  an over-long window instead, a range would end early and days would read as
  "no candles" gaps (raised, not silent; never cached). The owner's two real downloads at the
  deploy gate (3 days at 1m futures needs about 22 pages) exercise it.
- **A stop part way through a range** (`DownloadError`): the pages already answered are
  kept, their complete closed days cached, then the error is raised (step 6); the test
  below fails a later page on each market.
- **Quiet days are no longer gaps; failures still are.** A day partly covered by a failed
  range is a gap, never a short "complete" day; a test checks it is not cached.
- **The futures `to = end − 1`**: measured only with `to` on a day boundary (the row at
  `to` was returned, so `to` is inclusive). With `end − 1` the last candle of the range
  (open at `end − interval`) is still at or before `to`, and the row at `end` is not asked
  for; rows at or after `end` are dropped anyway, so either reading of `to` gives the same
  frame. A test serves the measured end-of-window row and checks no next-day candle appears.
- **The current day on futures**: the forward loop may ask one more window that starts after
  the last closed candle. If KuCoin refused a window in the future instead of answering an
  empty list, today would read as a gap with KuCoin's message (raised, never silent; today is
  never cached). The owner's deploy-gate downloads use past days and do not exercise it.
- **Untrusted text in reasons**: KuCoin's `msg` reaches the terminal; it is cleaned of
  non-printable characters and cut to 200 characters (security-baseline rule 2).
- **Rate-limit reserve 100 and the 60 s cap** are a guess (spec Flagged concerns); a wrong
  value costs speed or a 429; a 429 then waits the bounded `gw-ratelimit-reset` (step 3)
  rather than the 7 s backoff, which alone would end in `DownloadError` against a 30 s
  window.
- **Callers touched**: `load_klines` (frame columns drop three; `market="um"` and `1s` now
  refused; short frames), `cache_info` / `clear_cache` (new subtree, so existing Binance
  files are invisible to them — intended), `BinanceBanError` importers (none in the repo
  besides tests), `scripts/measure_storage.py`. No other module imports `app.data`.
- **Old cache files**: `read_day` already returns `None` for another schema, and the
  subtree changes, so no Binance file is ever read.
- **Hyphenated symbols in the day-file regex**: `BTC-USDT-1h-2026-10-01.parquet` parses
  with the symbol `BTC-USDT` because the interval and date groups are fixed; a test covers
  it. Path safety: neither `.` nor `/` is allowed in a symbol.
- **Dropped tests**: the Vision, checksum, zip, CSV, microsecond, 418 ban and weight-header
  tests go with the behaviour; the ratchet line in Proof declares it.
- **No new dependency**; `pyproject.toml` and CI unchanged.
- **A file over 500 lines**: `tests/test_data.py` is 566 today; keep the rewrite under 500
  or split by area (`test_data_rest.py`, `test_data_cache.py`) per the one-module-per-area
  convention, and list any new test file here in the same commit.

## Options not taken
- **A contract lookup (`/api/v1/contracts/{symbol}`) per futures request**: clearer error
  for a mistyped symbol; the owner chose no extra call (intent open question 1).
- **Fixed windows of an assumed page size** (1500 spot, 200 futures): simpler coverage, but
  depends on a number measured only at short intervals (intent open question 4).
- **Treat a short day as gaps per missing interval, as today**: every quiet minute would
  raise; the intent defines a day with one candle and a clean answer as complete.
- **Keep `BinanceBanError` as an alias of a generic `RateLimitBanError`**: the intent removes
  it; nothing shows KuCoin bans with 418.
- **Map `BTCUSDT` to `BTC-USDT`**: the intent says callers type KuCoin's names, no mapping.
- **Require exactly one hyphen in spot symbols**: stricter than the intent's "accept the
  hyphen"; KuCoin's own 400100 refusal names a bad pair clearly.
- **One generic parser with a column-order table**: the two endpoints differ in types,
  order and time unit; two small parsers read more clearly.
- **Convert futures volume to coins with the contract multiplier**: out of scope (intent).
- **Bump the version or add a deprecation step for removed fields**: the intent keeps 0.1.0
  (spec Flagged concerns, data-conventions rule 4).

## Proof
- ratchet: tests may fall, because the Binance behaviour they check is removed. Deleted:
  `tests/binance_stub.py`, `tests/fixtures/binance/rest-spot-BTCUSDT-1h-2024-12-31.json`,
  `tests/fixtures/binance/rest-um-BTCUSDT-1h-2025-01-01.json`,
  `tests/fixtures/binance/spot-BTCUSDT-1h-2024-12-30-missing-two.csv`,
  `tests/fixtures/binance/spot-BTCUSDT-1h-2024-12-31.csv`,
  `tests/fixtures/binance/spot-BTCUSDT-1h-2025-01-01.csv`,
  `tests/fixtures/binance/um-BTCUSDT-1h-2025-01-01.csv`; and in `tests/test_data.py` and
  `tests/test_data_cli.py` the Binance-only tests (Vision checksum and member, CSV and
  microsecond parsing, REST-vs-Vision equality, 418 ban, weight header, ban cancelling the
  pool). Behaviours that stay keep a test below.
- test: test_make_request_refuses_invalid_parameters (`um`, `1s`, `6h` futures, `XBTUSDM`,
  `XBTMZ25`, `BTC/USDT`, `../etc`, dates)
- test: test_make_request_normalises_valid_parameters (`btc-usdt` → `BTC-USDT`, `xbtusdtm`)
- test: test_spot_rows_map_to_columns (every row of the spot fixture: `high` max, `low` min,
  `close_time`, schema)
- test: test_futures_rows_map_to_columns
- test: test_malformed_rows_are_rejected (wrong length, bool, non-finite, wrong type, not a list)
- test: test_retries_on_429_and_5xx_but_not_404
- test: test_retries_stop_after_three
- test: test_retry_after_is_honoured_and_a_long_one_stops
- test: test_rate_limit_pacer (headers present above and below the reserve, missing, not an
  integer, reset over the cap)
- test: test_429_without_retry_after_waits_for_the_reset (reset 20000 → a 20 s sleep;
  reset 90000 → 60 s)
- test: test_kucoin_error_code_is_a_refusal_with_its_message (spot-unknown-symbol fixture,
  HTTP 200 code 400100)
- test: test_http_error_with_kucoin_body_is_a_refusal (futures-from-in-seconds fixture, 400)
- test: test_spot_range_over_1500_candles_loads_completely
- test: test_futures_range_over_200_candles_loads_completely
- test: test_futures_end_of_window_row_adds_no_next_day_candle
- test: test_futures_day_without_some_minutes_has_no_gap (00:14 and 02:15 absent)
- test: test_empty_day_is_a_gap_and_not_cached
- test: test_refused_page_is_a_gap_and_not_cached
- test: test_page_cut_short_is_a_gap_and_not_cached (second page refused; spot and futures)
- test: test_days_fetched_before_a_download_error_stay_cached (a later page fails with
  retries exhausted, spot and futures: `DownloadError` raised, the fully answered closed
  days on disk)
- test: test_mistyped_futures_symbol_names_the_symbol_check
- test: test_day_before_first_candle_names_the_oldest_candle
- test: test_invalid_parameters_raise_before_any_fetch
- test: test_second_load_makes_no_fetch
- test: test_cache_holds_parquet_files_only_under_kucoin
- test: test_cache_root_priority
- test: test_day_path_layout_and_escape (hyphenated spot symbol)
- test: test_atomic_write_leaves_only_the_day_file
- test: test_cache_info_and_clear_touch_only_day_files (hyphenated spot symbol, `binance-vision/` untouched)
- test: test_no_cache_mode_writes_nothing
- test: test_current_day_is_not_cached
- test: test_no_module_names_a_binance_host
- test: test_redirect_is_not_followed (origin a KuCoin URL)
- test: test_only_https_urls_are_opened
- test: test_datetime_bound_is_refused_not_a_type_error
- test: test_clear_cache_refuses_a_datetime_bound
- test: test_download_reports_fetched_skipped_and_missing
- test: test_cache_info_shows_sizes
- test: test_cache_clear_deletes_only_matching_day_files
- test: test_invalid_parameter_prints_one_line_and_exits_2
- test: test_unusable_cache_dir_prints_one_line_and_exits_2
- test: test_download_error_prints_one_line_and_exits_2 (retries exhausted)
- All are still to be written in step 9 (the ones that keep an existing name are rewritten
  for KuCoin); `tests/test_smoke.py` stays.
- `python -m compileall -q .` silent, exit 0; `python -m pytest` all passed, offline;
  `python -m ruff check .` "All checks passed!".
- Deploy gate, by the owner with network: `python -m app.data download BTC-USDT 1h
  2026-10-01 2026-10-03 --market spot` and `python -m app.data download XBTUSDTM 1m
  2026-10-01 2026-10-03 --market futures`, both exit 0.

Interrogation (plan-template):
1. Breaks: `load_klines` callers (frame shape, markets, intervals, short frames), the CLI,
   `cache_info`/`clear_cache` (subtree), `scripts/measure_storage.py`, the tests; in Risks.
2. Riskiest: paging and completeness; in Risks with its guards.
3. Options: in Options not taken.
4. Implementable cold: yes — each step names the function, the constants, the window rules,
   the reason texts and the stub's behaviour; the measured endpoint rules are in intent.md
   Constraints and `references/capture/summary.json`.
5. Proof items: none exists yet; all are written in step 9.
