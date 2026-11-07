The engine matches plan.md and spec.md on every case I ran, and the wheel built from a clean copy of HEAD contains all four `app/backtest/` modules. The verdict covers the code paths I called directly. The build, test and lint results for the final tree are not covered here: they come from the runner's run.

## Commands run

This is a CI session (`SDLC_GATE_COMMANDS=runner`), so I did not run the targets myself.

**Read, not run:** `evidence/gate-design.json`, the runner's run on commit `155b4a62f4b9acbc4488d6b79f47e1220589555e` of 2026-11-07T11:10:43Z. That is the tree the build phase started from, not the final one. The final tree's result is the runner's: it runs the three targets once after this session and shows the result in the check run `sdlc/test` and in this phase's own gate record. Nothing in this report stands in for that.

The record's `commands` entry: `ok: true`, `"reason": "build, test and lint exit 0"`, `ran_by: runner`, not deferred.
- `python -m compileall -q .`: exit 0, output `""`
- `python -m pytest`: exit 0, tail `============================= 105 passed in 0.34s ==============================`. These are the existing tests only; `tests/test_backtest.py` did not exist at that commit.
- `python -m ruff check .`: exit 0, `All checks passed!`

There are no `test.log`, `build.log` or `lint.log` files in `evidence/` yet.

## Behavior exercised

All calls were `python -c` against HEAD a9f33f3.

- **Worked example** (the test file's opens `[100,100,110,120,100,90,81]`, closes `[100,110,120,100,90,85,81]`, positions `[1,1,0,0,1,0,0]`, fee 0.001):
  - Positions held `0,1,1,0,0,1,0`.
  - Trades: `1 → 3` at `100.0 → 120.0`, return `0.197601`; `5 → 6` at `90.0 → 81.0`, return `-0.101799`; both `closed_at_end` false.
  - `Summary(total_return=0.07568647568108022, max_drawdown=0.10269730089999984, trade_count=2, win_rate=0.5, time_in_market=0.42857142857142855)`
  - `max abs equity diff 2.220446049250313e-16` against the spec's seven equity values, and summary diffs `2.22e-16 1.53e-16 0.0`. All within 1e-9.
- **Gap case** (`Datetime("ms","UTC")`, hours 00, 01, 03, 04; decision at the 01:00 close):
  - It filled at the 03:00 open (`entry_price 13.0`).
  - Both trade time columns kept the input's dtype: `Datetime(time_unit='ms', time_zone='UTC')`.
  - The position still open after the last row closed at the last close (`exit_price 15.0`) with `closed_at_end` true.
- **End-of-frame close with the fee** (`[1,1,1]`, opens `[100,100,110]`, closes `[100,105,120]`):
  - Final equity `1.1976012`, equal to the expected `0.999**2*120/100` (`1.1976012`).
  - `final==1+tr True`, trade `closed_at_end: True`.
- **Last-row decision** (`[0,0,1]`): positions `[0,0,0]`, equity `[1.0,1.0,1.0]`, 0 trades. The decision was not filled.
- **Zero-trade run:**
  - `trade_count=0, win_rate=0.0`, with an empty trades frame that keeps its schema: Int64 times on an integer frame, `Datetime(ms, UTC)` on a datetime frame.
  - A one-row frame gives equity `[1.0]` and no trades.
- **Refused inputs (R14):** every case raised `BacktestInputError`, a `ValueError` subclass, with the bad index or value and what is accepted. Literal messages include:
  - `positions has 2 values but the frame has 3 rows: pass one position per row`
  - `positions[1] is True: each position must be the integer 0 (flat) or 1 (long); cast a Boolean or Float series with .cast(pl.Int8)`
  - The same refusal for `None`, `nan`, `2`, `-1`, `0.5`, `'1'`, a Boolean Series, a Float Series and an Int Series with a null.
  - `frame is empty: pass at least one candle`
  - `open_time[2] is 1, not after open_time[1] 1: open_time must be strictly increasing`
  - `open_time[1] is null: every row needs an open_time`
  - `fee nan is out of range: it must be at least 0 and below 1, for example 0.001`, and the same for `-0.01`, `1` and `1.5`
  - `fee True is not a number: …` and `fee '0.001' is not a number: …`
  - `frame is a list: …` and `frame is a LazyFrame: …`
  - `frame lacks the column(s) close: it needs open_time, open, close`
  - `open[1] is None`, `close[1] is inf`, `open[1] is nan`, `open[1] is 0.0` and `close[1] is -2.0`, each with `: every price must be a finite number above 0`
  - Non-numeric prices (the latest commit): `open has dtype String: prices must be numbers`, `close has dtype Boolean: prices must be numbers`, and `open has dtype Date: prices must be numbers`
- **Just outside the refusals, all accepted:**
  - fee `0` (int) with Int64 prices: `total_return=0.19999999999999996`
  - fee `0.999`: `total_return=-0.9999989`
  - A Decimal(10,2) `open` column: same result as Float64, `0.1976012…`
- **No I/O dependency:** importing `app.backtest` alone loads `[]` `app.data` modules, and `numpy loaded: False`.
- **Neighbouring flows:**
  - `app.data.__all__` imports unchanged: `['DownloadError', 'Fetch', 'Gap', 'HttpResponse', 'InvalidRequestError', 'KlineGapError', 'cache_info', 'clear_cache', 'load_klines']`.
  - `python -m app.data --help` printed the usage with `download`, `cache-info` and `cache-clear`.
  - `python -m app.data cache-info --cache-dir /tmp/claude-1001/v0004-cache` printed `No cached klines under /tmp/claude-1001/v0004-cache/kucoin.`
- **Wheel (plan step 6, panel #1):**
  - I made a `git archive` of HEAD, extracted it to `/tmp/claude-1001/v0004-src`, and ran `python -m pip wheel /tmp/claude-1001/v0004-src --no-deps -w /tmp/claude-1001/v0004-wheel`. It printed `Successfully built crypto-backtester` (`crypto_backtester-0.1.0-py3-none-any.whl`).
  - `python -m zipfile -l` lists `app/backtest/__init__.py` (464), `app/backtest/engine.py` (3687), `app/backtest/inputs.py` (4009) and `app/backtest/summary.py` (1197), plus `app/__init__.py` and the eight `app/data/*.py` modules.
- **Proof tests:** all 19 test names in plan.md's Proof exist in `tests/test_backtest.py`. I counted them; I did not run them.

**Blocked:** one call needed approval and was denied automatically: my `bash -c 'mkdir … && python -m app.data cache-info …'`. It broke the one-command-per-call rule. I reran it as separate commands without the `mkdir`, which worked.

**Side effect:** pip stored a cached copy of the wheel in `/home/runner/work/crypto-backtester/crypto-backtester/.sdlc-cache/pip/wheels/…`. That directory is ignored by git: `git status` shows only the pre-existing `hook-log.jsonl` change and `CLAUDE.local.md`.

## Not exercised

- **The targets on the final tree:** build, test and lint on a9f33f3 are the runner's (`sdlc/test`). The design record above predates every backtest file.
- **The pytest suite**, including `tests/test_backtest.py`: not run here, because this is CI.
- **Platforms:** only Linux with Python 3.14. Not Windows or macOS, and not the oldest supported Python (3.10).
- **Speed** on about 525,600 rows (a year of 1-minute candles): not timed.
- **A real `load_klines` frame** or a `KlineGapError.frame`: not run, because there is no network. Only hand-built frames.
- **Other inputs:** other `open_time` dtypes (Date, Datetime with another unit or timezone, strings), a polars `Object` column, and position sequences such as numpy arrays or generators.
- **No test for Boolean prices:** `tests/test_backtest.py:89` tests a String `open` but no Boolean or Date price column. I checked those by calling the function directly. The plan does not require such a test.

## Mismatches with plan.md / spec.md

None. The two build-time changes to the plan are written into `plan.md` (lines 6–7 and 17–19), and the code matches them: `__all__` has `DEFAULT_FEE` first, and there is no `TRADE_SCHEMA`.

## Verdict

matches the plan
