I checked change 0001 against plan.md and spec.md. Every behaviour I called through the stub does what the plan says. The project's own build, test and lint have not been run on this build's code yet: the record I read is from the design commit, so the runner's run after this session is the one that decides.

**Verdict: matches the plan**

## Commands run

This is a CI session (`SDLC_GATE_COMMANDS=runner`), so I did not run the three targets myself. I read `evidence/gate-design.json`, the runner's run on commit `8bab7390db810111a16f75c1c8ed082360de9032` of 2026-10-27T13:10:49Z. That is the tree the build phase started from, not the final one. The final tree's result comes from the runner, which runs the three targets once after this session and shows them in the check run `sdlc/test`. A red result there starts the next fix round, and nothing in this report replaces it.

From `gate-design.json`, all three read, not run, with `ran_by: runner`:
- **Build:** `python -m compileall -q .` exited 0 with no output.
- **Test:** `python -m pytest` exited 0, ending `tests/test_smoke.py .  [100%]` and `1 passed in 0.01s`. That tree had no data layer yet.
- **Lint:** `python -m ruff check .` exited 0 with `All checks passed!`.

None of the gate's checks (including `commands` and `evidence_links`) failed or was deferred. No `test.log`, `build.log` or `lint.log` exists yet, and there is no `gate-build.json`.

Things I ran myself:
- `python -m compileall -q app tests scripts` gave no output and exit 0. This is not the build target; it skips the read-only `framework/` folder.
- I matched the 19 Proof test names in plan.md against the `def test_` lines in `tests/test_data.py` and `tests/test_data_cli.py`. All 19 exist, so there are no missing Proof tests.

## Behavior exercised

All loader calls went through the stub (`tests/binance_stub.Binance`, with sleep recorded and the clock set to 2025-01-02 05:30 UTC).

**Loading data:**
- **Two-day load (2024-12-31 to 2025-01-01):** 48 rows. The schema is exactly the spec's (times `Datetime(ms, UTC)`, `trades` `Int64`, the rest `Float64`). The one gap between times is `3600 s`, there are no duplicates, and it runs from `2024-12-31 00:00` to `2025-01-01 23:00` across the 2025 change to microsecond files. The first load made 4 fetch calls; the second made `0` and returned an equal frame.
- **Cache layout:** only `binance-vision/spot/BTCUSDT/1h/BTCUSDT-1h-2024-12-31.parquet` and `...-2025-01-01.parquet`.
- **Vision 404 then REST:** 48 rows from one REST call (`https://data-api.binance.vision/api/v3/klines?...&limit=1000`). Both days were cached.
- **Day missing from both sources:** `Gap(2024-12-31 00:00 .. 23:00, candles=24, reason='not on Vision (404) and REST returned no candles')`, with `.frame` holding 24 rows.
- **Two candles missing inside a file:** `Gap(2024-12-30 05:00 .. 06:00, candles=2, reason='missing candles in source file')`, with `.frame` holding 22 rows in the same schema.
- **Spot vs futures for the same candles:** `spot==um: True`, with `close_time` `2025-01-01 00:59:59.999000+00:00`.
- **Checksum mismatch:** a 24-candle gap with reason `'checksum mismatch'`, and the cache dir stayed empty.
- **`cache=False`:** with `CRYPTO_BACKTESTER_CACHE_DIR` set, nothing was written (`cache=False wrote: False`).
- **Current day through REST:** 5 rows, the last opening at `04:00`; the unfinished 05:00 candle was dropped. Nothing was cached, and a second load fetched again (2 calls).

**Inputs just outside the accepted ones** (each raised `InvalidRequestError` with `calls: 0`):
- an end date after today
- `1s` on `um`
- `BTC/USD`
- start after end
- `coinm`
- `7m`

**Network failures:**
- **418:** raised `BinanceBanError`. Over 8 days it made 9 calls and cached nothing, so pending downloads were cancelled.
- **Retries:** 503, 429, 500 then 404 gave 4 calls with sleeps `[1.0, 2.0, 4.0]`. A plain 404 gave 1 call and no sleep. Five 503s raised `DownloadError ... after 3 retries`.
- **Retry-After:** `Retry-After: 120` raised `DownloadError ... Retry-After 120 s; run again after that wait`. Lowercase `retry-after: 2` slept `[2.0]`.

**CLI through `main(argv, fetch=stub)`:**
- **`download`:**
  - The first run printed `not found: ... (1 day)`, `fetched from Vision (2 days)`, a line for the 2 missing candles, and `Total ... 2 fetched, 0 skipped, 0 from REST, 1 not found; 26 candles missing`. Exit 1.
  - A fully cached range printed `skipped, already cached (2 days)` with 0 calls. Exit 0.
  - A REST-only day printed `filled from REST (1 day)`. Exit 0.
- **`cache-info`:** printed `spot BTCUSDT 1h 3 14.9 KiB` and `Total: 3 day files, 14.9 KiB`.
- **`cache-clear`:**
  - `--start 2025-01-01` printed `Deleted 1 day file (5.0 KiB)`.
  - Clearing the whole symbol deleted the other 2 files.
  - My `notes.txt` and a `keep.parquet` in the cache root were left in place.
  - `../x` printed `error: invalid symbol '../x' ...` and exited 2.
- **Bad interval and 418:** each printed one `error:` line and exited 2.

**Real entry point `python -m app.data`, on the empty dir `/tmp/claude-1001/empty`:**
- `cache-info` printed `No cached klines under /tmp/claude-1001/empty/binance-vision.`
- `cache-clear BTCUSDT` printed `Nothing to delete: no cached day files match BTCUSDT spot.`
- A download with a 2099 end date printed `error: end 2099-01-02 is in the future (today is 2026-10-28 UTC)` and exited 2.
- `--market coinm` got the argparse usage error and exit 2. No subcommand also exited 2.
- A real download for 2024-01-01 failed on the sandbox's network block: `error: ...BTCUSDT-1d-2024-01-01.zip: URLError: <urlopen error Tunnel connection failed: 403 user denied> after 3 retries; check the network and run again`. Exit 2, no traceback, and no files were left behind.

**Neighbouring flows:**
- `python -c "import app; print(app.__version__)"` gives `0.1.0`, the same as `pyproject.toml`, which now has `dependencies = ["polars>=1.0"]`.
- The diff against main for `app/__init__.py`, `tests/test_smoke.py`, `.github`, `CLAUDE.md` and `sdlc.yaml` is empty (0 lines). This matches the plan's note that `ci.yml` was left out.
- `python scripts/measure_storage.py` printed exactly what `evidence/storage-measurement.md` records: seed 20261028, daily files 26.56 / 26.17 MiB against one yearly file 23.02 / 21.81 MiB, which is +15.4% / +20.0%, under the 20% reopen threshold.

## Not exercised

- The test suite (pytest), including `-k` runs: not run in CI. The runner judges it on the final tree.
- The build, test and lint targets on the final tree. The record I read is from the design commit, before any data-layer code existed.
- Real Binance hosts. The network is blocked here, so real file layouts and real headers were not checked.
- The real 10 s connect / 60 s read timeouts in `_HTTPSHandler`.
- The rule of at most 4 parallel Vision downloads (I saw cancellation, not the concurrency limit).
- The REST weight pause at 80% and the 1 s wait when the weight header is missing (tests exist, not run here).
- REST paging over several pages, and the 451 / other 4xx refusal paths.
- The zip size limits (64 MiB body, 256 MiB member), unexpected member names, and a missing `.CHECKSUM`.
- The `1s` and `1m` intervals, and multi-month ranges.
- Cache-folder selection on Windows (`%LOCALAPPDATA%`) and the `XDG_CACHE_HOME` / `~/.cache` defaults. I ran on Linux only, with an explicit dir or the environment variable.
- `scripts/measure_storage.py --from-cache`.
- The project CI (`.github/workflows/ci.yml`). Without the owner adding polars there, it will fail on `import polars`, as the plan's Risks section says.

## Mismatches with plan.md / spec.md

None.

The files that matter are under `/home/runner/work/crypto-backtester/crypto-backtester/`: `changes/0001-binance-vision-kline-data-layer/plan.md`, `spec.md`, `evidence/gate-design.json`, `evidence/storage-measurement.md`, the code in `app/data/`, `tests/binance_stub.py`, and `scripts/measure_storage.py`.
