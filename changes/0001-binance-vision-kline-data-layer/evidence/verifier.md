# Verifier report: change 0001, binance-vision-kline-data-layer (test phase)

The change matches the plan. All 19 Proof tests exist under the names the plan gives, the code does what spec.md asks, and the build gate's run of the three targets was green. Two caveats, both below: permission prompts blocked my own stubbed runs of the loader, and the final tree's result belongs to the runner.

## Commands run

This is a CI session (`SDLC_GATE_COMMANDS=runner`), so I did not run the targets. The results below are **read, not run**.

**Which tree:** I read `evidence/gate-build.json`, the runner's run on commit `e8897a31937ec2f17d0069c4292d62bdb15413cd` of `2026-10-28T17:09:13Z`. That is the tree the test phase started from, not the final one. The final tree's result is the runner's: it runs the three targets once after this session and shows the result in the check run `sdlc/test` and in `gate-test.json`. A red target there starts the next fix round by itself, and nothing here stands in for it.

`git diff --stat e8897a3 HEAD` (HEAD is `6a949d9`) touches only files under `changes/0001-…/evidence/` and `status.yaml`. No code, test or fixture changed since that run.

From `gate-build.json` (`result: continue`). Every check is `ok: true`, and none carries `details.deferred`. The `commands` entry has `ran_by: runner`:
- `python -m compileall -q .`: exit 0, output `""`
- `python -m pytest`: exit 0. Tail:
  ```
  tests/test_data.py ..................................................... [ 76%]
  ......                                                                   [ 85%]
  tests/test_data_cli.py .........                                         [ 98%]
  tests/test_smoke.py .                                                    [100%]
  ============================== 69 passed in 0.55s ==============================
  ```
- `python -m ruff check .`: exit 0, `All checks passed!`
- The `evidence` check is `ok: true`, "evidence present: verifier.md".

First lines of the logs. This session wrote these minutes ago as placeholders and the runner replaces them, so they are not failures:
- `evidence/test.log`: `# python -m pytest — deferred to the runner — 2026-10-28T17:10:48Z`
- `evidence/build.log`: `# python -m compileall -q . — deferred to the runner — 2026-10-28T17:10:48Z`
- `evidence/lint.log`: `# python -m ruff check . — deferred to the runner — 2026-10-28T17:10:48Z`

## Behavior exercised

**Proof tests exist.** I checked every `- test:` line in plan.md for `def <name>(` in the named file. All 19 are present: 16 in `tests/test_data.py` and 3 in `tests/test_data_cli.py`.

**CLI runs.** These were direct, offline, with a scratch cache at `/tmp/claude/vc`:
- `python -m app.data download BTC/USDT 1h 2024-12-31 2024-12-31 …` → exit 2, `error: invalid symbol 'BTC/USDT': use 2 to 30 letters or digits, for example BTCUSDT`
- `python -m app.data download BTCUSDT 1s 2024-12-31 2024-12-31 --market um …` → exit 2, `error: interval '1s' exists on the spot market only`
- `python -m app.data download BTCUSDT 1h 2099-01-01 2099-01-01 …` → exit 2, `error: end 2099-01-01 is in the future (today is 2026-10-28 UTC)`
- `python -m app.data download BTCUSDT 1h 2024-12-31 2024-12-30 …` → exit 2, `error: start 2024-12-31 is after end 2024-12-30`
- `python -m app.data cache-info --cache-dir /tmp/claude/vc` → `No cached klines under /tmp/claude/vc/binance-vision.`
- `python -m app.data cache-clear BTCUSDT 1h --cache-dir /tmp/claude/vc` → `Nothing to delete: no cached day files match BTCUSDT 1h spot.`

Each failure was one stderr line, no traceback, exit 2, and no network call: validation happens before any fetch, as the spec asks.

**Blocked: stubbed loader runs.** I wanted to call `load_klines` through `tests/binance_stub.Binance` for each Acceptance item. The permission policy denied it twice: once for an inline stdin script ("brace with quote character"), and once for a compound shell command. There is no approval surface in this session. These items therefore rest on reading the code and the test bodies, not on calls I made.

**Code read against spec.md.** In `app/data/`:
- **Parameters:** `params.py` has the market and interval sets, `1s` on spot only, the symbol pattern, start ≤ end, and end ≤ today.
- **Retries:** in `http.py`, at most 3 retries with sleeps of 1/2/4 s plus jitter. 404 and other 4xx are returned without a retry. 418 raises `BinanceBanError`, and a `Retry-After` over 60 s stops the run. Header lookup ignores case.
- **Weight pause:** when the weight header is missing or does not parse, the run waits 1 s; at 80 % of the limit or more it sleeps to the next minute.
- **Timeouts:** 10 s to connect, then 60 s per read.
- **Vision files:** `vision.py` checks the SHA-256 against `.CHECKSUM` (missing or wrong → gap), reads only the named CSV member, and enforces the 64 MiB zip / 256 MiB CSV bounds in memory.
- **REST:** `rest.py` uses `data-api.binance.vision` with limit 1000 for spot and `fapi.binance.com` with limit 1500 for um. It pages with an inclusive `endTime`; an empty page ends the range, and a non-200 answer becomes `REST refused (HTTP n)`.
- **Schema:** `schema.py` gives ms UTC time columns, floors µs to ms, and detects the unit from 10^14.
- **Cache:** in `cache.py`, the root comes from the argument, then the env var, then XDG / `~/.cache` / `%LOCALAPPDATA%`. Writes are atomic (temp file in the same directory, then `os.replace`), and paths are checked to stay inside `binance-vision/`. `clear_cache` deletes only files matching the day-file pattern and skips symlinks.
- **Loader:** in `loader.py`, a pool of 4 threads runs the Vision pass, and a ban cancels pending downloads. The current day is never written, and its unfinished candles are dropped. Gap reasons match spec § Gaps.

**Test bodies read.**
- The two-missing-candles test asserts `Gap(12-30 05:00, 12-30 06:00, 2, "missing candles in source file")` and a 22-row frame in the schema.
- The retry test asserts 4 calls with sleeps `[1.25, 2.25, 4.25]`, and a single call on 404.
- The weight test asserts sleeps to the minute boundary at weight 4800 (80 % of 6000).
- The current-day test asserts hours 0–4 only, no file written, and a second REST fetch on reload.

## Not exercised

- `load_klines` and `sync_days` against the stub, run by me. Permission was denied, so the Acceptance items rest on the runner's green test run at `e8897a3` and on reading the code.
- `download` with a working fetch, `cache-info` with real files, and `cache-clear` deleting real files. These need the stub, which the CLI only takes through `main(argv, fetch=…)`, and that needs a script.
- The real Binance endpoints. There is no network, so layout drift and real headers are untested.
- The real urllib connection handler: the 10 s / 60 s timeouts in an actual socket.
- Windows (`%LOCALAPPDATA%` path, `os.replace` semantics). I ran on Linux only.
- `scripts/measure_storage.py`. I did not run it; `evidence/storage-measurement.md` is present in the diff.
- The three targets on the final tree. That result is the runner's (`sdlc/test`).

## Mismatches with plan.md / spec.md

None. The build's departures are recorded in plan.md Risks:
- `DownloadError` when retries run out.
- REST days cached only when complete.
- `Vision refused (HTTP n)`.
- Each closed day cached as soon as its answer is in.
- `.github/workflows/ci.yml` left without polars. The project CI's pytest will fail on `import polars` until the owner adds it; the SDLC jobs are unaffected.

## Verdict

**matches the plan**
