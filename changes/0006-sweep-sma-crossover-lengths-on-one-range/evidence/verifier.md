# Verifier report: change 0006, sweep SMA crossover lengths on one range (test phase)

## Commands run

This is a CI session (`SDLC_GATE_COMMANDS=runner`), so I did not run the three targets. I read the build phase's gate record, which is the runner's run on **commit 3cd37833ea of 2026-11-07T23:03:05Z**. That is the tree this phase started from, not the final tree. The final tree's result comes from the runner, which runs the three targets once after this session and shows the result in the check run `sdlc/test` and in this phase's own gate record. Nothing in this report stands in for that run.

`git diff --stat 3cd3783 HEAD` touches only files under `changes/0006-.../evidence/` and `status.yaml`. So `app/` and `tests/` at HEAD (55d7200) are the same as on the tree the record judged.

From `evidence/gate-build.json`, check `commands`: `ok: true`, `"reason": "build, test and lint exit 0"`, `ran_by: runner`. No `deferred` flag is set on `commands` or `evidence`.

- `python -m compileall -q .`: exit 0, output `""`. Read, not run.
- `python -m pytest`: exit 0. Read, not run. Tail of the output:
  ```
  tests/test_backtest_cli.py .......................                       [ 31%]
  tests/test_backtest_sweep.py ..............................              [ 44%]
  ...
  ============================= 223 passed in 0.48s ==============================
  ```
- `python -m ruff check .`: exit 0, output `All checks passed!`. Read, not run.

First line of each log in `evidence/`. Each one is this session's deferred placeholder, which the runner replaces. They are not failures.
- `test.log`: `# python -m pytest — deferred to the runner — 2026-11-07T23:04:39Z`
- `build.log`: `# python -m compileall -q . — deferred to the runner — 2026-11-07T23:04:39Z`
- `lint.log`: `# python -m ruff check . — deferred to the runner — 2026-11-07T23:04:39Z`

## Behavior exercised

I called the code directly: the CLI, and `main(argv, fetch=KuCoin stub)` with `loader.utc_now` patched to the stub's `NOW` and a temporary cache directory. These calls read no `.env*`. I did not start pytest. Python is 3.14.4.

**Sub-command help**
- `python -m app.backtest sweep --help` lists the arguments in `run`'s order: positionals, `--market {spot,futures}`, `--fast` (default 5,10,20), `--slow` (default 30,50,100), `--fee` (default 0.001), `--cache-dir`. The epilog is `SMA_NOTE`. This matches R1 and R3.
- `python -m app.backtest run --help` shows the same options, help strings and epilog as `main:app/backtest/__main__.py`. This matches R13.

**Refusals made before any load, through the real CLI** (each exits 2, prints one `error:` line on stderr and nothing on stdout)
- `--fast 5,,10` → `error: fast '' is not a whole number of at least 1` (R4).
- 21 fasts `1..21` × 21 slows `22..42` → `error: the grid has 441 pairs with fast below slow, more than 400: pass shorter --fast or --slow lists` (R6).
- `--fast 50 --slow 10,20,50` → `error: no pair has fast below slow: pass a --fast value below a --slow value` (R6).
- `--fee 2` → `error: fee 2.0 is out of range: it must be at least 0 and below 1, for example 0.001` (R2). The fee is checked before the pair count, as Design step 3 orders.

**The cap, from inside the limit**
- A grid of exactly 400 pairs (fasts `1..20`, slows `21..40`) on 120 synthetic candles: exit 0. Run line `... 120 candles; sma-cross, 400 pairs tried, 0 skipped; fee 0.10%`, 400 table rows, 1 stub call.

**Defaults**
- No `--fast` or `--slow` on 120 synthetic candles: exit 0, `9 pairs tried, 0 skipped`, nine rows.
- Rows are sorted by total return, highest first: 0.00%, -0.19%, -0.20%, ... -0.26%.
- Ties are broken by fast: `20 50`, `10 50`, `5 50` read -0.25%, -0.26%, -0.26%, and the two at -0.26% are ordered 10 before 5 only because their rounded value hides a difference in the raw return.
- Then come the `buy and hold    -0.18%` line and the warning line (R10, R11).

**Skip counting**
- `--fast 2 --slow 23,24` on the 24-candle day: `1 pairs tried, 1 skipped`, one row `2 23 -0.03% 0.03% 1 0.00% 4.17%`, `buy and hold 1.45%` (R8).

**Neighbouring flow: `run`**
- `run ... --fast 2 --slow 23` on the same day prints `total return -0.03%`, `max drawdown 0.03%`, `trades 1`, `win rate 0.00%`, `time in market 4.17%`, `buy and hold 1.45%`. Every number equals the sweep row (R9).

**Two-word negative list**
- `--fast -5,10` written as two words, on Python 3.14: `(2, '', 'error: fast -5 is not a whole number of at least 1\n')`, and the stub made no call. This is the 3.14 path described in the spec's flagged concern.

**Static review against spec and plan**
- All 17 `test:` Proof items exist with those names in `tests/test_backtest_sweep.py`. The refusal cases listed in Proof are all there, including `--fast=-5,10`, two-word `--fast -5`, and two-word `--fast -5,10` as its own test.
- `count_pairs` counts by bisecting and never builds the grid.
- `_sweep` follows Design steps 1 to 9 in order. The note is printed with `flush=True` before the backtests run.
- `main` is unchanged.
- `git diff --stat main...HEAD` on these paths is empty: `app/backtest/__init__.py`, `inputs.py`, `engine.py`, `summary.py`, `strategy.py`, `app/data/`, `app/__init__.py`, `pyproject.toml`, `tests/test_backtest_cli.py`, `tests/conftest.py`, `tests/kucoin_stub.py`, `.github/`. This covers R13, R14 and R15.
- The one change to `plan.md` records that the two-word negative list became its own Proof test. That is a declared departure, not a mismatch.

## Not exercised

- The three targets on the final tree. That result comes from the runner (check run `sdlc/test`).
- The pytest suite in this session (not run in CI). My first attempts at multi-step shell commands were refused by the permission system (no approval surface). I then used single commands only.
- `--market futures` on a successful sweep, and the `OSError` hint for a bad cache directory on `sweep`. These are not called, and not covered by the sweep tests either.
- A real KuCoin fetch. Every load went through the stub.
- Windows and macOS. I ran on Linux only.
- Python 3.10 to 3.13, where argparse itself refuses the two-word `--fast -5,10`. I ran on 3.14 only.
- Large real ranges, such as a year of 1m candles with 400 pairs. Neither run time nor memory was measured.

## Screenshots

None. spec.md says "Mock: none"; the change is CLI text output only.

## Mismatches with plan.md / spec.md

None.

A wording note, not a mismatch: when one pair is tried, the run line reads `1 pairs tried`. That follows the spec's literal format `{tried} pairs tried` (spec.md, Design, "Output").

## Verdict

matches the plan
