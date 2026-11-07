**Verdict: matches the plan.** The new `run` command and the strategy behave as plan.md and spec.md describe on every input I tried. Two limits on that: the build, test and lint targets have not been run on this branch, and I did not run the test suite.

## Commands run

This is a CI session (`SDLC_GATE_COMMANDS=runner`), so I read the three targets from the design gate's record instead of running them. `gate-build.json` doesn't exist yet. That record is the runner's run on commit `79311818e9cec7f9fffeffe9fc6a3273c90caa0c` of 2026-11-07T18:42:50Z: the tree this phase started from, not the final one. The final tree's result is the runner's, which runs the three targets after this session and shows them in the check run `sdlc/test`. Nothing here stands in for it.

The `commands` check reads `"ok": true` with `"ran_by": "runner"`. No check in that record carries `deferred: true`, and there are no `test.log`, `build.log` or `lint.log` files yet.

| Target (read, not run) | Exit | Output |
|---|---|---|
| `python -m compileall -q .` | 0 | empty |
| `python -m pytest` | 0 | `collected 152 items` … `============================= 152 passed in 0.54s ==============================` |
| `python -m ruff check .` | 0 | `All checks passed!` |

Those 152 tests predate the build, so none of the new tests are in them.

You suggested running `pytest -q`, `ruff check` and compiling `app tests scripts` for information. I ran none of them: my instructions forbid starting the test runner in a CI session, even with `-k`, and say to read the gate record instead of running the targets.

## Behavior exercised

Everything was offline. I called `app.backtest.__main__.main(argv, fetch=KuCoin())` from `tests/kucoin_stub.py`, with `loader.utc_now` set to `kucoin_stub.NOW`, the stub's sleeps turned off, and every `--cache-dir` under `$TMPDIR`.

**Success output (R11).** `run btc-usdt 1h 2026-10-01 2026-10-01 --fast 3 --slow 5` exits 0 after 1 fetch and prints exactly eight lines. The lowercase symbol comes out upper case, and the six value lines are each 22 characters (14 + 8):
```
BTC-USDT 1h spot, 2026-10-01 .. 2026-10-01: 24 candles; sma-cross fast 3 slow 5; fee 0.10%
SMAs count candles, not wall time: an interval without a candle is skipped, not filled.
total return    -0.73%
max drawdown     1.25%
trades               3
win rate        33.33%
time in market  50.00%
buy and hold     1.45%
```
- **Numbers check:** calling `run_backtest` directly on the same frame gives `-0.007348…, 0.012495…, 3, 0.3333…, 0.5`, and buy and hold gives `0.014482…`. These match the printed lines.
- **Cache reuse:** running again on the same cache with an empty stub exits 0 with `calls 0` and the same output.
- **Futures:** `--market futures` on `xbtusdtm` exits 0 with the header `XBTUSDTM 1h futures, ...`.

**Refusals (R12).** Each prints one `error:` line on stderr and exits 2:
- **Lengths** (no fetch):
  - `--fast 0` gives `fast 0 is not a whole number of at least 1`
  - `--fast x` gives `fast 'x' ...`
  - `--fast 1.5` gives `fast '1.5' ...`
  - `--fast 50 --slow 20` and `20/20` give `fast 50 is not below slow 20: the fast SMA must be the shorter one`
- **Fees** (no fetch):
  - `--fee abc` gives `fee 'abc' is not a number: pass a proportional fee, for example 0.001`
  - `--fee 1.5`, `-0.1` and `nan` give `fee 1.5 is out of range: it must be at least 0 and below 1, for example 0.001`
- **Request checks** (no fetch, same messages as `download`):
  - `BTC/USDT` gives `invalid spot symbol 'BTC/USDT': ...`
  - `1hour` gives `unknown interval '1hour': use one of 1m, ... 1d`
  - an end date in the future gives `end 2026-10-05 is in the future (today is 2026-10-03 UTC)`
  - start after end gives `start 2026-10-02 is after end 2026-10-01`
  - `01/10/2026` gives `invalid start date '01/10/2026': use YYYY-MM-DD, ...`
- **Too few candles:**
  - `--slow 24` on the 24-candle day gives `error: the range has 24 candles, not more than slow 24: ...` and exit 2
  - `--slow 23` exits 0
  - `--slow 30` exits 2
- **Bad market:** `--market margin` raises `SystemExit(2)` with argparse's `argument --market: invalid choice: 'margin' (choose from spot, futures)`.
- **Missing day** (2026-09-30 .. 2026-10-01): `error: 24 candle(s) missing in 1 gap(s); ...`, exit 2.
- **Download error** (503 from the stub): `error: https://api.kucoin.com/... HTTP 503 after 3 retries; check the network and run again`, exit 2.

**Help screens.**
- `python -m app.backtest --help` lists `run`.
- `run --help` shows the same positionals, help text and `--market` choices as `download`, plus `--fast`, `--slow`, `--fee` and the SMA note as the epilog.
- `python -m app.backtest` with no sub-command exits 2 with `the following arguments are required: COMMAND`.

**Strategy, called directly.**
- The hand example `[1,2,3,2,1,1,3]` with fast 2, slow 3 gives `[0, 0, 1, 1, 0, 0, 1]`.
- The tie case gives `[0, 0, 0, 0]`.
- Changing the closes after row 3 leaves `[0, 0, 1, 1]`.
- Integer `close` works, and an empty frame gives `[]`.
- It returns an `Int8` Series named `position`.
- It refuses `True`, `2.0`, `0`, `fast >= slow`, a list, a frame with no `close`, and a String `close`, each with `BacktestInputError`.
- `app.backtest.__all__` now holds `sma_cross_positions`.

**Neighbouring flows.**
- `app.data.__main__.main(["download", ...])` exits 0 with `1 fetched, 0 skipped, 0 not found`, and a bad symbol still exits 2 with the same message.
- `run_backtest` on a hand-built 4-row frame returns `0.21`, 1 trade, `0.75` time in market, and still refuses a position of `2` with its old message.

**Scope checks.**
- `git diff main...HEAD` is empty for `app/data`, the three engine modules, `app/__init__.py`, `pyproject.toml`, `.github`, `conftest.py`, the stub and the fixtures.
- `tests/test_backtest.py` gained only the one `__all__` line that plan.md Risks records.
- `app/backtest/` has no numpy, eval, exec, pickle or subprocess.
- All 18 Proof test names exist in the new test files, plus one extra, `test_run_reports_unusable_cache_dir`.

Two of my commands were blocked by permission rules and I re-ran them in an allowed form: a script containing `{"`, and a command chained with `; echo`.

## Not exercised
- **The targets on the final tree:** build, test and lint have not run on this branch's head. The runner's `sdlc/test` check decides that, including whether the 19 new tests pass.
- **The cache-directory error path:** I didn't trigger the `OSError` handler.
- **Real network:** nothing ran against the real KuCoin API (the default `fetch=None` path).
- **Other platforms and inputs:** I ran on Linux with Python 3.x only, not Windows. I didn't try multi-day ranges beyond 09-30..10-01, intervals other than `1h`, non-integer ties, or very large ranges.
- **Fees just under 1:** `--fee 0.999999` is accepted (it is under 1) and the header shows `fee 100.00%`. That is what two decimals give, not a mismatch.

## Mismatches with plan.md / spec.md
None.

## Verdict
matches the plan

Files involved:
- /home/runner/work/crypto-backtester/crypto-backtester/app/backtest/__main__.py
- /home/runner/work/crypto-backtester/crypto-backtester/app/backtest/strategy.py
- /home/runner/work/crypto-backtester/crypto-backtester/app/backtest/__init__.py
- /home/runner/work/crypto-backtester/crypto-backtester/tests/test_backtest.py
- /home/runner/work/crypto-backtester/crypto-backtester/changes/0005-run-a-backtest-from-the-cli-with-an-sma/evidence/gate-design.json
