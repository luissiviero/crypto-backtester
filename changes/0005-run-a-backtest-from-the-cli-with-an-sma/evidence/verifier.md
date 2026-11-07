# Verifier report: change 0005, test phase (CI session, `SDLC_GATE_COMMANDS=runner`)

**Verdict: matches the plan.** One spec departure is documented in plan.md and is for the owner to confirm: the one-line edit to the existing `tests/test_backtest.py`, against `spec.md:62` and `spec.md:189`. This verdict says nothing about the final tree's targets; that result is the runner's, in `sdlc/test`.

## Commands run
**Read, not run.** I read `evidence/gate-build.json`, the runner's run on commit `86a123a84387fc7f59e0a2ba6fcd5eb83130c514` of 2026-11-07T20:26:24Z. That is the tree this phase started from, not the final one. The final tree's result comes from the runner, which runs the three targets once after this session and shows the result in the check run `sdlc/test` and in this phase's own gate record. If a target is red there, the next fix round starts by itself, and nothing in this report stands in for that result.

The two commits after `86a123a` (`4103884`, `eedfb32`) only touch files under `changes/0005-.../evidence/` and `status.yaml` (`git diff --stat 86a123a HEAD`). No source or test file changed.

The `commands` check reads `"ok": true`, `"reason": "build, test and lint exit 0"`, `"ran_by": "runner"`, with no `deferred` flag. The `evidence` check reads `"ok": true`, `"evidence present: verifier.md"`.

| Command | Exit code | Output tail (from the build gate record) |
|---|---|---|
| `python -m compileall -q .` | 0 | `""` (no output) |
| `python -m pytest` | 0 | see below |
| `python -m ruff check .` | 0 | `All checks passed!` |

pytest output tail:
```
tests/test_backtest_cli.py .......................                       [ 36%]
tests/test_strategies.py ..................                              [100%]
============================= 193 passed in 0.60s ==============================
```

First lines of the three logs (read, not run):
- `evidence/test.log`: `# python -m pytest — deferred to the runner — 2026-11-07T20:27:55Z`
- `evidence/build.log`: `# python -m compileall -q . — deferred to the runner — 2026-11-07T20:27:55Z`
- `evidence/lint.log`: `# python -m ruff check . — deferred to the runner — 2026-11-07T20:27:55Z`

These marks are not failures. This session wrote them, and the runner replaces each file with the target's real output.

I did not start the test runner, as CI rules require.

## Behavior exercised
All of these were direct `python -c` calls. They use `tests/kucoin_stub.py` and a fixed clock (`loader.utc_now = lambda: NOW`), and write to a temporary cache directory.

**The strategy, `sma_cross_positions`:**
- `app.backtest.__all__` gave `['DEFAULT_FEE', 'BacktestInputError', 'BacktestResult', 'Summary', 'run_backtest', 'sma_cross_positions']`.
- The plan's example, closes `[1,2,3,2,1,1,3]` with fast 2 and slow 3, gave `[0, 0, 1, 1, 0, 0, 1]`. This matches the hand-computed list in plan.md.
- The tie case `[2,2,2,2]` with 2 and 3 gave `[0, 0, 0, 0]`.
- Inputs just outside the spec's examples:
  - The smallest allowed lengths, fast 1 and slow 2, gave `[0, 1, 1, 0, 0]`.
  - An integer `close` column gave `[0, 1, 1, 1]`.
  - A frame shorter than `slow` gave `[0, 0]`.
- Refusals, each a `BacktestInputError`:
  - `(2,2)` gave `fast 2 is not below slow 2: the fast SMA must be the shorter one`.
  - `(0,3)` gave `fast 0 is not a whole number of at least 1`.
  - `(True,3)` gave `fast True is not a whole number of at least 1`.
  - `(2.0,3)` gave `fast 2.0 is not a whole number of at least 1`.

**The CLI, `main(argv, fetch=stub)`, on 2026-10-01, `SPOT_1H` (24 candles):**
- `--fast 3 --slow 5` exited 0 and printed the eight lines of R11:
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
- The candle-count boundary:
  - `--slow 23` exited 0 with `trades 1`.
  - `--slow 24` exited 2 with `error: the range has 24 candles, not more than slow 24: the strategy could never take a position; widen the dates or lower --slow`.
- The defaults (20 and 50) on 24 candles exited 2 with `... not more than slow 50 ...`.
- Fees just outside the accepted range (the stub's calls stayed at 0, so nothing was fetched):
  - `--fee 1` exited 2 with `error: fee 1.0 is out of range: it must be at least 0 and below 1, for example 0.001`.
  - `--fee inf` exited 2 with the same message for `inf`.
- `--fee 0.999999` exited 0. Its header shows `fee 100.00%`, which is two-decimal rounding as R11 specifies.
- `1hour` (the intent's own example) exited 2 with `error: unknown interval '1hour': use one of 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d`, which is `download`'s message.
- Run as a subprocess:
  - `python -m app.backtest --help` exited 0 and printed the `run` sub-command.
  - `python -m app.backtest run ... --market margin` exited 2 with `argument --market: invalid choice: 'margin' (choose from spot, futures)`.

**Neighboring flows:**
- `app.data.__main__.main(["download", ...])` exited 0 (`1 fetched ... 0 candles missing`).
- `cache-info` on the same cache exited 0 and listed `spot BTC-USDT 1h 1 3.9 KiB`.
- `run` on that cache with an empty stub exited 0, printed the same output, and made `calls 0`.

**Tests against plan.md Proof:**
- All 8 strategy tests in Proof exist in `tests/test_strategies.py`, and all 10 CLI tests exist in `tests/test_backtest_cli.py`.
- They cover what the plan says:
  - the hand-computed list, with its Int8 type and `position` name;
  - the warm-up rows;
  - the tie;
  - the lookahead check, against both `[9,9,9]` and every `k`;
  - the Series fed straight into `run_backtest`;
  - the parametrised refusals;
  - the fee test asserts `calls == []` for `abc`, `1.5`, `-0.1` and `nan`;
  - the boundary at 24 and 23;
  - the missing-day and HTTP 503 refusals;
  - `--cache-dir` under `tmp_path` everywhere;
  - the `clock` fixture through `pytestmark`, which also pulls in `sleeps`.
- One extra test, `test_run_reports_unusable_cache_dir`, covers the `OSError` hint from R12.

**Diff against `origin/main`:**
- Source and test files that changed: `app/backtest/__init__.py`, `app/backtest/__main__.py`, `app/backtest/strategy.py`, `tests/test_backtest.py` (one line), `tests/test_backtest_cli.py`, `tests/test_strategies.py`, and the change folder. Every one is listed under plan.md "Files that change".
- `git diff --stat origin/main...HEAD` is empty for `app/data`, `pyproject.toml`, `app/__init__.py`, `.github`, `inputs.py`/`engine.py`/`summary.py`, `tests/conftest.py`, `tests/kucoin_stub.py`, `tests/fixtures`, the other test files and the guardrail files.

## Not exercised
- The final tree's build, test and lint. Those belong to the runner and appear in `sdlc/test`.
- The live KuCoin path: `fetch=None` through `urllib_fetch`. Only the stub was used.
- `--market futures` end to end.
- Multi-day ranges that succeed, and a range with a real intra-day gap (a candle with no trades, R4) through the CLI. R4 was checked only through the design: windows count rows.
- Non-integer closes near a tie (the floating-point risk in plan.md).
- Windows and macOS. I ran only on Linux, Python 3.14.4, polars 2.1.0.
- The default cache directory and the environment variable `CRYPTO_BACKTESTER_CACHE_DIR`.

## Screenshots
None: spec.md Acceptance says "Mock: none", and the change is a plain-text CLI.

## Mismatches with plan.md / spec.md
- **plan.md:** none.
- **spec.md:** `spec.md:189` (Acceptance, "no test file already on `main` changes") and `spec.md:62` (R14, "every test file already on `main`" is unchanged) are not met. `tests/test_backtest.py` gained one line, `"sma_cross_positions"`, in `test_public_api`'s expected set. plan.md records this as a build departure (Files that change, and Risks, "The public-API test on `main`"). The spec contradicts itself here: R1 and Acceptance require the name to be in `__all__`, and the test on `main` pins `__all__` exactly. The owner should confirm the choice at review.
- **Cosmetic, within spec:** `--fee 1` is echoed as `fee 1.0` in the engine's message, because the text goes through `float()` first. This matches what the plan says (reuse `_check_fee`'s message as is).

## Verdict
**Matches the plan.**
