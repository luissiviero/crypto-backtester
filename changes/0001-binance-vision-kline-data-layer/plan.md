# Plan: Binance Vision kline data layer (from intent.md 2026-10-27, spec.md 2026-10-27)

## Files that change
- `pyproject.toml` — add `dependencies = ["polars>=1.0"]` under `[project]`.
- `app/data/__init__.py` — new: re-exports the public API (`load_klines`, `KlineGapError`,
  `Gap`, `Fetch`, `HttpResponse`, `InvalidRequestError`, `BinanceBanError`, `cache_info`,
  `clear_cache`) with `__all__`.
- `app/data/params.py` — new: market and interval sets, symbol pattern, date parsing and
  checks, `InvalidRequestError`, interval length in milliseconds.
- `app/data/http.py` — new: `HttpResponse`, `Fetch`, the default `urllib` fetch (a connection
  handler that applies the 10 s connect timeout and then sets the socket's 60 s read timeout;
  `HTTPError` turned into an `HttpResponse`; body size cap), the retry wrapper (backoff 1/2/4 s
  plus jitter, `Retry-After`, 429/5xx/connection/timeout retried, 404 and other 4xx not, 418 →
  `BinanceBanError`, injectable `sleep`), case-insensitive header lookup, and the REST weight
  pause (80 % of the limit → sleep to the next minute; header absent or unparsable → wait 1 s).
- `app/data/schema.py` — new: column names and dtypes (one definition), unit detection,
  CSV-bytes → frame and REST-rows → frame normalisation.
- `app/data/vision.py` — new: Vision URL for a day, zip download, `.CHECKSUM` verification,
  in-memory extraction of the one expected CSV member with size bounds; returns a frame or a
  day outcome with its reason.
- `app/data/rest.py` — new: REST URL per market, paging over a range of missing days, JSON
  shape check, outcome on 4xx.
- `app/data/cache.py` — new: cache root resolution (argument, env var, platform default),
  day-file path with the inside-the-cache check, atomic Parquet write, read, `cache_info`,
  `clear_cache`.
- `app/data/loader.py` — new: `load_klines`, the day sync used by the loader and the CLI
  (`sync_days` returning one outcome per day: cached, fetched, rest, missing+reason), the
  thread pool, expected-candle grid, `Gap`, `KlineGapError`, and a module-level `utc_now()`
  that tests monkeypatch to inject the clock.
- `app/data/__main__.py` — new: argparse CLI with `download`, `cache-info`, `cache-clear`;
  `main(argv=None, fetch=None) -> int`.
- `scripts/measure_storage.py` — new: the storage measurement of spec § Storage measurement
  (synthetic year with a fixed seed, or `--from-cache`); prints a markdown table of daily vs
  yearly totals at zstd 3 and 9. Imports `app.data.schema` for the schema; writes only to a
  temporary directory it deletes.
- `tests/fixtures/binance/` — new: small text fixtures with the real layouts: a spot CSV
  before 2025 (ms, no header), a spot CSV from 2025-01-01 (µs, no header, `close_time`
  ending `…999999`), a futures CSV (ms, header row, `close_time` ending `…999`) holding the
  same candles as the spot ones, a spot CSV with two consecutive candles removed, REST JSON
  pages for spot and futures. Interval `1h`, a few days, synthetic prices. Zips and
  `.CHECKSUM` bodies are built from them inside the tests.
- `tests/test_data.py` — new: the loader, sources, cache and gap tests, with a stub `Fetch`
  that maps URLs to responses (with or without weight headers) and records every call, a
  recording `sleep`, and `tmp_path` as `cache_dir`.
- `tests/test_data_cli.py` — new: the CLI tests through `main(argv, fetch=stub)` and `capsys`.
- `tests/binance_stub.py` — new (added in the build): the stub `Fetch`, the fixture reader and
  the zip builder that both test modules share; split out of `tests/test_data.py`, which
  passed the coding-standards 500-line limit with them inside. It holds no test.
- `changes/0001-binance-vision-kline-data-layer/evidence/storage-measurement.md` — new: the
  output of `python scripts/measure_storage.py`, labelled synthetic with the seed.

## Order of work
1. `pyproject.toml` dependency; check `python -c "import polars"`.
2. `params.py` with tests for valid and invalid symbol, interval (`1s` on `um` refused),
   market and dates (end after today, start after end).
3. `schema.py` with tests: µs and ms files normalise to identical frames; header row
   detected; `ignore` dropped; dtypes as in spec § Schema; malformed row rejected.
4. `http.py` with tests on a stub transport and a recording `sleep`: the number of attempts
   and the recorded backoff sleeps, `Retry-After` honoured and the over-60 s stop, 404 not
   retried, 418 raises, weight pause at 80 %, 1 s wait when the weight header is absent.
5. `vision.py` with tests: good zip, checksum mismatch, missing checksum, unexpected member
   names ignored, oversize member refused.
6. `rest.py` with tests: paging until an empty page, 451 outcome, malformed JSON outcome.
7. `cache.py` with tests: root priority (argument > env var > default via monkeypatched
   environment and `sys.platform`), layout path, atomic write leaves no temp file, path
   escaping refused, `cache_info` sizes, `clear_cache` deletes only matching day files.
8. `loader.py` with the spec's Acceptance tests: multi-day load, 2025-01-01 crossing, 404 →
   REST, missing day → `KlineGapError`, two missing candles inside a file → one exact gap with
   reason "missing candles in source file" and the rest in `.frame`, second load makes no
   fetch, Parquet only, spot = futures, `cache=False` writes nothing, current day not cached
   and its unfinished candle dropped (clock injected through `utc_now`).
9. `__main__.py` and `test_data_cli.py`: `download` report lines and exit codes, `cache-info`
   table, `cache-clear`, an invalid parameter printing one stderr line with exit 2.
10. `scripts/measure_storage.py`; run it and commit its output as
    `evidence/storage-measurement.md`; commit no data.
11. Run build, test and lint; paste their output.

## Risks
- Departure (build run, 2026-10-28): `.github/workflows/ci.yml` is out of this run's reach —
  the run's permission settings deny every edit under `.github/` (a workflow file also needs a
  token with the `workflows` scope), so the CI install line was not changed and the file left
  "Files that change". Until the owner adds `polars==2.1.0` (the version the build tested
  with) to the "Install the toolchain" step, the project CI's `python -m pytest` fails on
  `import polars`; the SDLC phase jobs are unaffected (`commands.setup` installs polars).
- Build choices where the spec is silent (build run, 2026-10-28): (a) retries exhausted on a
  connection error, 429 or 5xx raise `DownloadError` (the base of `BinanceBanError`, also
  exported) rather than turning a passing outage into a gap; the CLI treats it as an expected
  failure (one stderr line, exit 2). (b) A REST-filled closed day is cached only when it holds
  every candle of the day: a fill cut short by a refusal mid-range would otherwise freeze a
  partial day in the cache; Vision days are cached whatever they hold (the file is final).
  (c) A Vision answer other than 200 or 404 makes the day a gap "Vision refused (HTTP <n>)".
- New dependency (coding-standards rule 5, security-baseline rule 6): polars becomes the
  project's first runtime dependency, as the intent asks; it is lower-bounded in
  `pyproject.toml` and pinned in CI. The SDLC phase jobs install it unpinned
  (`commands.setup` on main: `python -m pip install pytest ruff polars`), so a polars major
  release could break the phase jobs before CI; the owner can pin it there.
- The design branch was cut from the intent PR head, before the owner's commit 801dc74 on
  main that adds polars to `commands.setup`. The build branch must take `sdlc.yaml` from main
  (it does not touch it); the build gate reads the default branch's setup.
- `CLAUDE.md` documents `python -m pip install pytest ruff` and "healthy: `1 passed`"; after
  this change both are stale. It is a guardrail file: the owner updates it in a PR of their
  own. The run does not edit it.
- Riskiest step: the loader (step 8), where the Vision pass, the REST fill, the cache and the
  gap grid meet; an off-by-one in the grid (inclusive end, the current day's unfinished
  candle) or in REST paging (`endTime` inclusive in ms) would hide or invent gaps. Mitigation:
  the grid is computed from integer milliseconds only, and the tests assert exact gap
  boundaries.
- Thread pool and 418: a ban must stop every pending Vision download; the loader cancels
  pending futures and re-raises. Tests cover it with a stub that answers 418 on one day.
- Rate limits: the market-data mirror may not send `X-MBX-USED-WEIGHT-1M`; without the 1 s
  fallback the weight pause would never fire there (panel #1). A test pins the no-header path.
- `urllib.request.urlopen` takes one timeout for connect and read alike; the separate 10 s /
  60 s split needs the custom connection handler named above. If that proves brittle across
  Python 3.10–3.12, the fallback is one 60 s timeout with the connect phase bounded by the
  same retry policy; the build records the choice in this plan.
- Floor-converting µs to ms changes `close_time` of post-2025 spot files by 0.999 ms; this is
  intended (spec § Schema) and makes spot and futures rows identical.
- Untrusted input: zip bombs and oversized bodies are bounded (64 MiB body, 256 MiB member);
  no file is extracted to disk; `cache-clear` cannot delete outside
  `<cache>/binance-vision/`. A bug here could delete the owner's files: `clear_cache` matches
  the exact day-file name pattern and resolves every path before deleting.
- A10 makes real outages raise `KlineGapError`; callers that want the partial data take
  `.frame`. The CLI `download` reports such days as "not found" lines with the reason.
- Callers: none yet (`app/` has only `__version__`); later strategy and engine changes build
  on `load_klines` and the schema, so renaming a column later is a breaking change.
- Real Binance behaviour is never exercised by the tests (no network in CI or the sandbox);
  the fixtures follow the published layouts. A layout drift on Binance's side would show only
  on the owner's machine, as would the real-data storage check.

## Options not taken
- Return a result object `(frame, gaps)` instead of raising: rejected, a caller can ignore the
  gaps and get a silently short frame, which the intent forbids.
- An `allow_gaps` keyword: not added (panel #3); `KlineGapError.frame` already gives a
  non-silent route to the partial data.
- A spot REST host option: not added (panel #1); the intent asks for none.
- Keep the original zip in the cache: rejected by the intent (Parquet only, one copy).
- One Parquet file per month or year: kept off until a measurement exceeds the reopen rule;
  per-day files keep atomic writes and REST closed-day caching simple.
- `requests`/`httpx` or `platformdirs`: rejected by the intent (no new dependency besides
  polars).
- `Datetime("us")` for every time column: exact for all sources, but spot µs and futures ms
  `close_time` would differ by 999 µs for the same candle, breaking "identical frames".
- `api.binance.com` as the spot REST default: refused in more regions than the
  market-data-only mirror.
- `Decimal` prices: exact, but slow and awkward in polars for backtests; `Float64` keeps
  Binance's 8 decimals within double precision.
- Caching empty days: would stop re-asking for pre-listing days, but a temporary Vision or
  REST outage would then be cached as "no data" for good.
- An uncommitted throwaway measurement script: rejected (panel #2), the figure must be
  reproducible.

Interrogation (plan-template):
1. Breaks: nothing existing calls the new package; touched shapes are `pyproject.toml`
   (dependency added) and the CI install step. Data shapes introduced: the schema, the cache
   layout, `Gap` and `KlineGapError`.
2. Most risky: step 8 (above).
3. Alternatives: the list above.
4. An engineer can implement it from spec.md and this plan: every URL, limit, dtype, path,
   reason string and exit code is stated in the spec; the fixtures are described by layout.
5. No item in Proof exists yet: every test below is to be written in this change.

## Proof
All tests are new, written in this change, offline, through the stub `Fetch`:
- test: tests/test_data.py::test_multi_day_range_loads_expected_rows_and_schema
- test: tests/test_data.py::test_range_across_2025_has_continuous_utc_timestamps
- test: tests/test_data.py::test_vision_404_day_is_filled_from_rest
- test: tests/test_data.py::test_day_missing_from_both_sources_raises_gap_error
- test: tests/test_data.py::test_candles_missing_inside_file_raise_exact_gap_with_frame
- test: tests/test_data.py::test_second_load_makes_no_fetch
- test: tests/test_data.py::test_cache_holds_parquet_files_only
- test: tests/test_data.py::test_spot_and_futures_fixtures_load_identically
- test: tests/test_data.py::test_checksum_mismatch_is_a_gap_and_not_cached
- test: tests/test_data.py::test_http_418_raises_ban_error
- test: tests/test_data.py::test_retries_on_429_and_5xx_but_not_404
- test: tests/test_data.py::test_rest_waits_when_weight_header_is_missing
- test: tests/test_data.py::test_rest_pauses_when_weight_nears_limit
- test: tests/test_data.py::test_invalid_parameters_raise_before_any_fetch
- test: tests/test_data.py::test_no_cache_mode_writes_nothing
- test: tests/test_data.py::test_current_day_is_not_cached
- test: tests/test_data_cli.py::test_download_reports_fetched_skipped_rest_and_missing
- test: tests/test_data_cli.py::test_cache_info_shows_sizes
- test: tests/test_data_cli.py::test_cache_clear_deletes_only_matching_day_files

Target (spec Acceptance): build no output and exit 0; `python -m pytest` all passed, the smoke
test included; `python -m ruff check .` `All checks passed!`; the storage figures in
`evidence/storage-measurement.md`, produced by `python scripts/measure_storage.py`.
