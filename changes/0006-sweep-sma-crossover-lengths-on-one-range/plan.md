# Plan: Sweep SMA crossover lengths on one range (from intent.md 2026-11-07, spec.md 2026-11-07)

## Files that change
- `app/backtest/sweep.py` — new: `MAX_PAIRS = 400`; `count_pairs(fasts: Sequence[int], slows:
  Sequence[int]) -> tuple[int, int]` (kept, skipped) by `bisect.bisect_right(slows, fast)` per
  fast on the sorted distinct lists; `pairs(fasts, slows) -> list[tuple[int, int]]` (kept
  pairs, fast-major order); `SweepRow` frozen dataclass (`fast: int`, `slow: int`,
  `summary: Summary`); `sweep(frame: pl.DataFrame, pairs: Sequence[tuple[int, int]], fee:
  float) -> list[SweepRow]`, sorted by `(-row.summary.total_return, row.fast, row.slow)`.
  No I/O (spec Design, "Sweep module").
- `app/backtest/__main__.py` — the `sweep` sub-command (`SWEEP_HELP`, `SWEEP_WARNING`, the
  table header constants, `_sweep(args, fetch) -> int`, `_lengths(text, name, example) ->
  list[int]`, a `_table(rows) -> list[str]` formatter) and the helpers `run` and `sweep`
  share (`_add_range_arguments`, `_add_fee_arguments`, `_load(request, args, fetch)`,
  `_hold_line(frame, fee)`); `_run` uses the helpers with identical output.
- `tests/test_backtest_sweep.py` — new: the tests of Proof.
- `changes/0006-sweep-sma-crossover-lengths-on-one-range/plan.md` — this file, whenever the
  build departs from it.

Unchanged: `app/backtest/__init__.py` (`__all__` and docstring), `inputs.py`, `engine.py`,
`summary.py`, `strategy.py`, every module of `app/data/`, `app/__init__.py` (version
`0.1.0`), `pyproject.toml` (`app.backtest` is already a package, so `sweep.py` ships),
`.github/workflows/ci.yml`, every test file already on `main`, `tests/conftest.py`,
`tests/kucoin_stub.py`, `tests/fixtures/`. The Setup and Test commands stay as they are.

For the owner, not the run (guardrail file; the owner may land these in a PR of their own
before the build PR is reviewed), `CLAUDE.md`:
- Opening paragraph, "with an SMA crossover strategy and the CLI `python -m app.backtest
  run`." Suggested: "with an SMA crossover strategy and the CLI `python -m app.backtest run |
  sweep`."
- Architecture, the `app/backtest/` bullet. Suggested: "`app/backtest/` is the backtest
  engine, one module per job (inputs, engine, summary, strategy, sweep, and the CLI in
  `__main__.py`); its public API is `app/backtest/__init__.py` (`run_backtest`,
  `sma_cross_positions`). Only the CLI does I/O, through `app.data.load_klines`; the engine
  and strategy tests, `tests/test_backtest.py` and `tests/test_strategies.py`, use frames
  built by hand, and the CLI tests, `tests/test_backtest_cli.py` and
  `tests/test_backtest_sweep.py`, run offline against `tests/kucoin_stub.py`."

## Order of work
1. `app/backtest/sweep.py` with its unit tests in `tests/test_backtest_sweep.py` (hand-built
   frames: integer `open_time`, `open` = `close`, as `tests/test_strategies.py` builds them).
   - `count_pairs([5, 10, 20], [30, 50, 100]) == (9, 0)`; `count_pairs([5, 50], [10, 50]) ==
     (1, 3)`.
   - `sweep` on a frame of constant closes (every SMA equal, no position, return exactly 0)
     returns rows ordered by fast, then slow; on a varying frame each row's summary equals
     `run_backtest(frame, sma_cross_positions(frame, f, s), fee=fee).summary` and the order
     is by descending total return.
   - Commit with its tests.
2. Refactor `app/backtest/__main__.py` without behaviour change: `_add_range_arguments(parser)`
   adds `symbol`, `interval`, `start`, `end` (same metavars and help) and `--market`;
   `_add_fee_arguments(parser)` adds `--fee` and `--cache-dir`; `run` keeps `--fast` and
   `--slow` between them, so its help lists the options in today's order. `_load(request,
   args, fetch)` wraps the `load_klines` call; `_hold_line(frame, fee)` returns
   `f"{'buy and hold':<14}{value:>8}"`. `tests/test_backtest_cli.py` must pass unchanged.
   Commit.
3. The `sweep` sub-command in `app/backtest/__main__.py`, in the order of spec Design:
   - `_lengths(text, name, example)`: `items = text.split(",")`; `text.strip() == ""` →
     `BacktestInputError(f"--{name} is empty: pass comma-separated whole numbers, for example
     {example}")`; each item `value = _length(item, name)`, then `value < 1` →
     `BacktestInputError(f"{name} {value} is not a whole number of at least 1")` (the words
     of `validate_lengths`); return `sorted(set(values))`.
   - `fee = _fee(args.fee)`; `kept, skipped = count_pairs(fasts, slows)`; `kept == 0` →
     `no pair has fast below slow: pass a --fast value below a --slow value`; `kept >
     MAX_PAIRS` → `f"the grid has {kept} pairs with fast below slow, more than {MAX_PAIRS}:
     pass shorter --fast or --slow lists"`.
   - `frame = _load(...)`; `grid = [(f, s) for f, s in pairs(fasts, slows) if s <
     frame.height]`; `skipped += kept - len(grid)`; empty → `f"the range has {frame.height}
     candles, not more than any slow length with a smaller fast: no pair could take a
     position; widen the dates or lower --slow"`.
   - Print the run line (spec Design, "Output") and `SMA_NOTE`, `flush=True` on the note;
     then `rows = sweep(frame, grid, fee)`, the table from `_table(rows)`, `_hold_line`,
     `SWEEP_WARNING`; return 0.
   - `_table`: headers `("fast", "slow", "total return", "max drawdown", "trades", "win
     rate", "time in market")`; cells `str(fast)`, `str(slow)`, `_percent(...)` for the four
     fractions, `str(trade_count)`; width per column `max(len(header), longest cell)`;
     `"  ".join(cell.rjust(width) ...)`, the header row the same.
   - Parser: `sweep` with `help=SWEEP_HELP`, `epilog=SMA_NOTE`, `--fast default="5,10,20"`,
     `--slow default="30,50,100"`, help naming them comma-separated lengths in candles.
   - The CLI tests of Proof. Commit with them.
4. Run build, test and lint; paste the output.

## Risks
- **Breaking `run` in the refactor (riskiest step, 2).** Moving the argument lines into
  helpers can reorder `run`'s options in `--help` or change a default. Mitigations: the
  helpers add the arguments in today's order with today's strings; `tests/test_backtest_cli.py`
  pins `run`'s output and refusals and must pass unchanged; a new test compares
  `run --help`'s option names in order (`--market`, `--fast`, `--slow`, `--fee`,
  `--cache-dir`) to catch a reorder. If a helper makes `run` harder to read, step 2 may keep
  `run`'s lines inline and only share `_load` and `_hold_line`; say so here.
- **The test data.** `SPOT_1H` holds 24 candles of 2026-10-01, so the default slows
  (30, 50, 100) are all skipped there: the success tests pass short lists (for example
  `--fast 2,3,5 --slow 5,8,12,24`, where slow 24 is skipped by the candle count and fast 5
  with slow 5 by the order rule). The tests compute the expected rows themselves with
  `load_klines(..., cache=False, fetch=spot_day())`, `sma_cross_positions` and
  `run_backtest`, as `tests/test_backtest_cli.py` does, and sort them by the spec's key.
- **"Loaded once".** The test compares the stub's `calls` after one `sweep` with those after
  one `run` of the same range on a fresh stub and a fresh cache; a second load from the cache
  would make no extra call, so the test also asserts that `_load` is reached once by
  counting calls of a monkeypatched `app.backtest.__main__.load_klines` wrapper.
- **The clock.** `make_request` refuses an end after `loader.utc_now()`; the tests use the
  `clock` fixture (NOW 2026-10-03 12:00 UTC) and read the clock through `loader.utc_now()`,
  as `_run` does.
- **Negative items and argparse** (spec Flagged concerns): `--fast -5,10` may reach argparse
  as an option on some Python versions; the test uses `--fast=-5,10`.
- **Header printed before the backtests.** An engine error after the run line would leave
  stdout non-empty; `load_klines` frames already pass the engine's checks (the `run` tests
  show it), so the only errors after the header are bugs.
- **Float ties.** Equal returns on real data are rare; the tie test uses constant closes,
  whose returns are exactly `0.0`.
- **No new public name.** `sweep.py`'s names are not added to `app/backtest/__init__.py`, so
  `tests/test_backtest.py::test_public_api` passes unchanged (intent Constraints).
- **No new dependency** (coding-standards rule 5; security-baseline rule 6): `bisect`,
  `dataclasses` and polars only.
- **CLAUDE.md drift.** Until the owner lands the lines above, the deploy review may flag an
  outdated `CLAUDE.md`. The run cannot edit it.

## Options not taken
- **The sweep loop inside `__main__.py`.** Not taken: a pure module keeps the CLI short and
  lets the sort and the skip count be tested on hand-built frames; the intent leaves the choice
  to the design.
- **Building the grid before the cap check.** Not taken: two long lists would build a large
  list of pairs before the refusal; `count_pairs` bisects instead (security-baseline rule 2).
- **Counting the candle-count skips toward the cap.** Not taken: they are known only after
  loading, and the intent checks the cap before loading.
- **A long-run warning on stderr** (above a pairs × candles threshold). Not taken: the run
  line shows both counts and is flushed before the first backtest; the 400 cap bounds the
  worst case; a threshold would be a number with no source.
- **Rewriting argv so `--fast -5,10` reaches the command.** Not taken: it fights argparse for
  one edge case; `--fast=-5,10` works (spec Flagged concerns).
- **Ranges such as `5..50`, `--top`, other ranking measures.** Out of scope per the intent.
- **Threads or processes for speed.** Out of scope per the intent's Constraints.

Interrogation answers:
1. What could break: `run`, through the step-2 refactor (pinned by the unchanged
   `tests/test_backtest_cli.py`); nothing else imports `__main__.py`. Shapes touched: the
   `load_klines` frame (read only), `run_backtest`'s inputs (as `run` passes them), `Summary`
   (read only).
2. Riskiest step: step 2, the shared helpers; mitigated above.
3. Other options: listed above.
4. An engineer who never saw this conversation can implement it from spec Design (order of
   checks, the output shape) and Order of work (messages and calls). Nothing is missing.
5. Every Proof test is still to be written, in the new file; the existing tests exist and
   must keep passing.

## Proof
- test: test_count_pairs_counts_kept_and_skipped
- test: test_sweep_rows_match_run_backtest
- test: test_sweep_ties_sort_by_fast_then_slow
- test: test_sweep_prints_table
- test: test_sweep_skips_and_counts_pairs
- test: test_sweep_tries_repeats_once
- test: test_sweep_loads_klines_once
- test: test_sweep_refuses_bad_request
- test: test_sweep_refuses_bad_market
- test: test_sweep_refuses_bad_lengths
- test: test_sweep_refuses_bad_fee
- test: test_sweep_refuses_empty_grid
- test: test_sweep_refuses_grid_over_cap
- test: test_sweep_refuses_range_with_every_pair_skipped
- test: test_sweep_defaults_give_nine_pairs
- test: test_run_help_keeps_option_order
- `test_sweep_prints_table` runs `sweep btc-usdt 1h 2026-10-01 2026-10-01 --fast 2,3,5
  --slow 5,8,12,24` and compares every stdout line with lines built in the test from
  `run_backtest`; it also checks that every table line has the header's length.
- The refusal tests assert exit 2, one `error:` line on stderr, empty stdout, and (all but
  the every-pair-skipped one) `kucoin.calls == []`. Cases: bad symbol, interval and dates;
  `--fast ""`, `--fast 5,,10`, `--fast x`, `--fast=-5,10`, `--slow 0`, `--fast 1.5`; `--fee
  abc`, `--fee 1.5`; `--fast 50 --slow 10,20` (no pair); 21 fasts `1..21` by 21 slows
  `22..42` (441 pairs, over the cap); the default grid on the 24-candle day (every pair
  skipped by the candle count). A bad `--market` raises `SystemExit` with code 2.
- `test_sweep_defaults_give_nine_pairs` uses a stub with enough synthetic candles
  (`kucoin.add_spot_synthetic(utc(2026, 9, 28), 120, 3_600_000)`, range 2026-09-28 ..
  2026-10-02, 120 candles, more than the largest slow 100) and checks `9 pairs tried, 0
  skipped` and nine table rows.
- `tests/test_backtest_cli.py` and the rest of the suite pass unchanged.
- `python -m compileall -q .` prints nothing. `python -m pytest` reports every test passed.
  `python -m ruff check .` prints `All checks passed!`.
