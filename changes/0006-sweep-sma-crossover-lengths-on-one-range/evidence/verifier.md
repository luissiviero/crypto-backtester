The sweep matches plan.md and spec.md. Every acceptance case I called offline behaved as specified, and the design gate's `commands` record is green. That record was taken on the design tree, so it doesn't stand in for the runner's run on the final tree.

**Commands run** (read, not run: this is a CI session)

I read `evidence/gate-design.json`, the runner's run on commit `44ea2daa9018050097cce32db232dd4d2dcec1e0` of 2026-11-07T22:39:20Z (`details.ran_by: runner`, not deferred). That is the tree this phase started from, not the final one. The final tree's result comes from the runner, which runs the three targets once after this session and shows it in the check run `sdlc/test`; a red target there starts the next fix round by itself.
- `python -m compileall -q .`: exit 0, output `""`
- `python -m pytest`: exit 0, `193 passed in 0.71s` (Python 3.14.4, pytest-9.2.0)
- `python -m ruff check .`: exit 0, `All checks passed!`
- There are no `test.log`, `build.log` or `lint.log` under `evidence/` yet; none are expected before the runner's test gate.

**Behavior exercised**

One `python -c` call, with `loader.utc_now` set to `NOW` (2026-10-03 12:00 UTC), driving `main(argv, fetch=KuCoin stub)` with a fresh `--cache-dir` for each call. I did not start pytest, since this is a CI session.
- **Main success case:** `sweep btc-usdt 1h 2026-10-01 2026-10-01 --fast 2,3,5 --slow 5,8,12,24` exited 0 with 1 stub call. The run line read `... 24 candles; sma-cross, 8 pairs tried, 4 skipped; fee 0.10%`, followed by `SMA_NOTE`, an aligned header and 8 rows sorted by total return (`5 8 1.37%` first, `2 5 -0.81%` last), then `buy and hold     1.45%` and the warning.
- **Rows equal `run` (R9):** the 2/8 row (`0.48% 0.50% 3 33.33% 50.00%`) and the 3/8 row (`1.12% 0.41% 2 50.00% 50.00%`) are the same as `run --fast 2 --slow 8` and `run --fast 3 --slow 8`. The buy-and-hold line is the same character for character.
- **Same requests as `run` (R7):** `sweep calls == run calls: True`.
- **Repeats tried once (R3):** `--fast 3,2,2,3 --slow 8,8` gave `2 pairs tried, 0 skipped`.
- **Candle-count boundary (R8):** `--fast 1 --slow 23` worked (`1 pairs tried`). Just outside it, `--slow 24` on 24 candles exited 2 with the R8 message after 1 call.
- **Cap boundary (R6):**
  - Exactly 400 pairs (fasts 1..20, slows 21..40) is accepted: `60 pairs tried, 340 skipped`. Equal returns sort by fast, then slow.
  - 441 pairs gives `error: the grid has 441 pairs with fast below slow, more than 400: ...` with 0 calls.
- **Refusals with exit 2, one `error:` line, empty stdout and 0 calls:**
  - `--fast ""` → `--fast is empty: ... 5,10,20`
  - `5,,10` → `fast '' is not a whole number of at least 1`
  - `x` → `fast 'x' ...`
  - `--fast=-5,10` and two-word `-5` → `fast -5 ...`
  - `--slow 0` → `slow 0 ...`
  - `1.5` → `fast '1.5' ...`
  - `--fee abc` and `--fee 1.5` → the same messages as `run`
  - `--fast 50 --slow 10,20` → `no pair has fast below slow: ...`
  - interval `7m` and end date 2026-10-05 → `make_request`'s messages
  - `--market margin` → `SystemExit(2)` from argparse
- **Two-word `--fast -5,10`:** on this Python (3.14) it reaches the command and gets the R4 message, which is what plan.md expects for 3.14.
- **Default grid with no lengths given:**
  - On the 24-candle day: exit 2 with the R8 message after 1 call.
  - On a 120-candle synthetic range (2026-09-28 .. 2026-10-02): `9 pairs tried, 0 skipped`, 9 rows.
- **Neighbour 1, `run`:** `run --help` is byte-identical to origin/main's (`run --help identical: True`). `run` output is as above; `run` with its defaults on the 24-candle day exits 2 with its old message. The top-level help differs only because it now lists `sweep`, which is expected.
- **Neighbour 2, data layer:** `load_klines` returned a `(24, 8)` frame. The first call made 1 fetch, the cached reload made none, and the two frames are equal.
- **Static checks:** `app.backtest.__all__` is unchanged. `git diff --stat origin/main...HEAD` is empty for `app/data`, `__init__.py`, `inputs`, `engine`, `summary`, `strategy`, `pyproject.toml`, `app/__init__.py`, `tests/test_backtest_cli.py`, `conftest.py` and `kucoin_stub.py`. All 17 Proof test names exist in `tests/test_backtest_sweep.py`.

**Not exercised**
- The three targets on the final tree; that result is the runner's.
- The new test file; I did not run pytest here.
- The `--market futures` sweep.
- The `OSError` hint for an unwritable `--cache-dir`.
- `DownloadError` and `KlineGapError` during a sweep.
- Two-word `--fast -5,10` on Python 3.10–3.13, where argparse refuses it itself.
- Windows and macOS.
- Large real ranges (speed of 400 pairs on 1m candles).
- A bad symbol: `btc` is accepted by `make_request` (`KlineRequest(symbol='BTC', ...)`), so I never hit a symbol refusal.

**Mismatches with plan.md / spec.md**

None. Two small notes that are not mismatches:
- With one pair the run line reads `1 pairs tried`, which is the spec's format taken literally.
- `_run` now computes buy and hold after printing its rows, not before. Its output is unchanged.

**Blocked actions**
- The guard denied a heredoc to `python -` (an unverifiable redirect) and a `for` loop over a shell variable. I re-ran both checks without them, so nothing went unchecked.
- `python -I` couldn't import polars, so the script ran with plain `python` from the repository root.

**Verdict:** matches the plan

Files: `/home/runner/work/crypto-backtester/crypto-backtester/app/backtest/sweep.py`, `/home/runner/work/crypto-backtester/crypto-backtester/app/backtest/__main__.py`, `/home/runner/work/crypto-backtester/crypto-backtester/tests/test_backtest_sweep.py`, `/home/runner/work/crypto-backtester/crypto-backtester/changes/0006-sweep-sma-crossover-lengths-on-one-range/evidence/gate-design.json`
