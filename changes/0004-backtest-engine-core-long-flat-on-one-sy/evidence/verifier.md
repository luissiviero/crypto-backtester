The engine matches plan.md and spec.md on every case run in the test phase. This report covers the full suite as recorded by the runner's build-gate run, the Proof tests read one by one, and direct calls of `app.backtest`. The build, test and lint results for the final tree are the runner's, after this session (check run `sdlc/test`).

## Verifier report: change 0004, TEST phase

### Commands run
**The targets were read, not run.** This is a CI session (`SDLC_GATE_COMMANDS=runner`).

I read `evidence/gate-build.json`, the runner's run on commit `1044038d8640fb41e4b244743b1a517077633a09` of `2026-11-07T13:49:38Z`. That is the tree this phase started from, not the final one. The final tree's result is the runner's, which runs the three targets once after this session and shows it in the check run `sdlc/test`. If a target is red there, the next fix round starts by itself, and nothing in this report stands in for it. `git diff --stat 1044038 HEAD -- . ':!changes'` is empty, so the source at HEAD `302d77d` is the same as the commit the runner tested.

`commands` check: `"ok": true`, `"reason": "build, test and lint exit 0"`, `"ran_by": "runner"`. It is not deferred. The `evidence` check is also not deferred: `"ok": true`, `"evidence present: verifier.md"`.
- `python -m compileall -q .`: exit 0, output `""`
- `python -m pytest`: exit 0. Tail:
  ```
  collected 152 items
  tests/test_backtest.py ...............................................   [ 30%]
  ...
  ============================= 152 passed in 0.35s ==============================
  ```
- `python -m ruff check .`: exit 0, `All checks passed!`

First line of each log:
- `evidence/test.log`: `# python -m pytest — deferred to the runner — 2026-11-07T13:51:14Z`
- `evidence/build.log`: `# python -m compileall -q . — deferred to the runner — 2026-11-07T13:51:14Z`
- `evidence/lint.log`: `# python -m ruff check . — deferred to the runner — 2026-11-07T13:51:14Z`

These deferred marks are not failures. This session wrote them, and the runner replaces them with the real output.

### Behavior exercised
I called `app.backtest` directly with `python -c`. The test runner was not started.

- **Worked example**
  - Inputs: opens `[100,100,110,120,100,90,81]`, closes `[100,110,120,100,90,85,81]`, positions `[1,1,0,0,1,0,0]`, fee `0.001`.
  - Equity came back as `[1.0, 1.0989, 1.1988, 1.1976012, 1.1976012, 1.1299367322, 1.0756864756810802]`, and positions held as `[0,1,1,0,0,1,0]`.
  - Trades: (1, 100.0) → (3, 120.0), return 0.197601; (5, 90.0) → (6, 81.0), return -0.101799. Both have `closed_at_end` false.
  - Summary: `Summary(total_return=0.07568647568108022, max_drawdown=0.10269730089999984, trade_count=2, win_rate=0.5, time_in_market=0.42857142857142855)`.
  - Largest error against the spec numbers is `2.22e-16`, well inside 1e-9.
- **Gap**
  - Inputs: a `Datetime("ms","UTC")` frame at 00:00, 01:00, 03:00 and 04:00, positions `[0,1,0,0]`.
  - The entry is at `2024-01-01 03:00:00 UTC` at the price 120.0 (the 03:00 open), and the exit is at 04:00 at 130.0. The time columns keep the dtype `datetime[ms, UTC]`.
- **Data-layer neighbour**
  - Input: a 3-row frame built with `app.data.schema.SCHEMA` (all 8 columns), positions `[1,1,1]`.
  - The entry is at 01:00 at 106.0, and the exit at 02:00 at 120.0 with `closed_at_end` true. The final equity is 1.129812, which equals 0.999² × 120 / 106. The equity column is typed `i8` for position and `f64` for equity.
- **Data CLI neighbour**: `python -m app.data --help` still prints its usage.
- **One-row frame** with positions `[1]`: the last-row decision is not filled. Trade count is 0 and win rate is 0.0.
- **Fee boundaries**
  - Accepted: `0`, `-0.0`, `1e-12`, `0.999999`.
  - Refused: `1` gives `fee 1 is out of range: it must be at least 0 and below 1, for example 0.001`. `inf` is refused the same way.
- **Positions**
  - Lengths 2 and 4 against a 3-row frame are refused: `positions has 2 values but the frame has 3 rows: pass one position per row`.
  - `True`, `2` from a Series, `None` from an Int64 Series, `1.0`, `'1'` and `nan` are each refused with `positions[i] is …: each position must be the integer 0 (flat) or 1 (long); cast a Boolean or Float series with .cast(pl.Int8)`.
- **Frames**
  - A list is refused: `frame is a list: pass a polars DataFrame …`.
  - Duplicate times are refused: `open_time[1] is 1, not after open_time[0] 1: open_time must be strictly increasing`.
  - An empty frame is refused: `frame is empty: pass at least one candle`.
  - A missing column is refused: `frame lacks the column(s) close: it needs open_time, open, close`.
  - `issubclass(BacktestInputError, ValueError)` is `True`, and `DEFAULT_FEE` is `0.001`.

**Static checks**
- **Proof tests:** all 19 tests named in the Proof section exist in `tests/test_backtest.py`.
  - The worked-example tests compare with `pytest.approx(..., abs=1e-9)` at lines 151, 161 and 167–172.
  - Position values are parametrised at line 37 over `[None, math.nan, 2, -1, 0.5, "1", True]`.
  - Fees are parametrised at line 67 over `[-0.01, 1, 1.5, math.nan, True, "0.001", None]`, which is the plan's list plus two more.
  - The zero-trade test asserts `trade_count == 0` and `win_rate == 0.0` together (lines 237–238).
- **Scope of the diff:** `git diff origin/main -- app/data` is empty (0 lines). Outside the change folder, the diff from `origin/main` touches only the four new `app/backtest/*.py` files, `pyproject.toml` and the new `tests/test_backtest.py`. No existing test file changed.
- **Version:** still `0.1.0` in both `app/__init__.py:3` and `pyproject.toml:3`.
- **Packaging:** `pyproject.toml:9` reads `packages = ["app", "app.data", "app.backtest"]`. The wheel listing (panel #1) is in the build phase's verifier report; this phase built no wheel.
- **No I/O:** the only imports in `app/backtest` are `__future__`, `math`, `collections.abc`, `dataclasses`, `polars` and its own modules. There is no `open(`, network module, `logging`, `numpy` or `app.data` import. The only `load_klines` mention is in message and docstring text.
- **Test isolation:** `tests/test_backtest.py` contains no `app.data`, monkeypatch, fixture or kucoin reference.

### Not exercised
- The build, test and lint targets on the final tree. The runner runs them after this session and reports them in `sdlc/test`.
- The pytest suite itself. In CI I read the build gate's run instead of running it.
- The wheel listing (panel #1) in this phase. Only the `packages` entry was read; the build phase's verifier built and listed the wheel.
- Windows and macOS. I ran on Linux only.
- Large frames and speed (for example 525,600 rows).
- `open_time` dtypes other than Int64 and `Datetime("ms","UTC")`.
- Price columns that are integer- or Float32-typed.
- A Float `0.5` position given inside a polars Series, and a negative position given inside a Series.

### Mismatches with plan.md / spec.md
None.

### Verdict
matches the plan
