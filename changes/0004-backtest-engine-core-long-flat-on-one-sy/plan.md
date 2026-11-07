# Plan: Backtest engine core: long/flat on one symbol (from intent.md 2026-11-07, spec.md 2026-11-07)

## Files that change
- `app/backtest/__init__.py` — new: module docstring and the public API. It re-exports
  `run_backtest`, `DEFAULT_FEE`, `BacktestResult`, `Summary` and `BacktestInputError`, with
  `__all__` sorted as in `app/data/__init__.py`.
- `app/backtest/inputs.py` — new: `BacktestInputError(ValueError)`, `DEFAULT_FEE = 0.001`,
  `REQUIRED_COLUMNS = ("open_time", "open", "close")` and
  `validate(frame, positions, fee) -> Inputs`. `Inputs` is a frozen dataclass holding
  `open_time: pl.Series`, `opens: list[float]`, `closes: list[float]`,
  `positions: list[int]` and `fee: float`. Small private helpers do one check each:
  `_check_fee`, `_check_frame`, `_check_positions`.
- `app/backtest/engine.py` — new: `run_backtest(frame, positions, *, fee=DEFAULT_FEE) ->
  BacktestResult`, the frozen dataclass `BacktestResult(equity, trades, summary)`, the forward
  pass `_simulate(inputs)`, and the two frame builders `_equity_frame` and `_trades_frame`.
  `TRADE_SCHEMA` is built from the input's `open_time` dtype.
- `app/backtest/summary.py` — new: the frozen dataclass `Summary(total_return, max_drawdown,
  trade_count, win_rate, time_in_market)` and `summarize(equity: list[float],
  held: list[int], returns: list[float]) -> Summary`. The `Summary` docstring says of
  `win_rate`: "0.0 when there are no trades; see trade_count" (panel #2).
- `pyproject.toml` — `[tool.setuptools] packages = ["app", "app.data", "app.backtest"]`
  (spec Design, Packaging; decided by panel #1: keep the explicit entry, proven by a wheel
  listing; the owner may overturn it at the design gate, and then this line is dropped).
- `tests/test_backtest.py` — new: every test named in Proof, on frames built by hand with a
  `_frame(opens, closes, times=None)` helper in the file. Times default to integers
  `0..n-1`; the gap test uses `datetime(…, tzinfo=timezone.utc)` values cast to
  `pl.Datetime("ms", "UTC")`.
- `changes/0004-backtest-engine-core-long-flat-on-one-sy/plan.md` — this file, whenever the
  build departs from it.

Unchanged: `app/data/` (every module), `app/__init__.py` (version `0.1.0`), every test file
already on `main` (`tests/test_smoke.py`, `tests/test_data*.py`, `tests/conftest.py`,
`tests/kucoin_stub.py`, `tests/fixtures/`), `.github/workflows/ci.yml`, and the runtime
dependencies.

For the owner, not the run (guardrail file; the owner edits it in a PR of their own, before
the build PR if they want `sdlc/review` green on the first pass, per the intent), `CLAUDE.md`:
- lines 4 to 7: "Today the package (`app/`) holds one feature, `app/data/`: …" becomes two
  features. Suggested text: "Today the package (`app/`) holds two features: `app/data/`, …
  (as now) …; and `app/backtest/`, a long/flat backtest of one symbol on a klines frame."
- Architecture, after line 33 (the `app/data/` item), add: "- `app/backtest/` is the backtest
  engine, one module per job (inputs, engine, summary); its public API is
  `app/backtest/__init__.py` (`run_backtest`). It does no I/O; its tests,
  `tests/test_backtest.py`, use frames built by hand and no stub or fixture files."
- Lines 36 and 37: "the data tests run offline against …" stays true. No edit is needed.
- The Setup and Test lines and the CI install step need no change: no new dependency, and
  the same test command.

## Order of work
1. `app/backtest/inputs.py` and the refusal tests. In order:
   - fee: refuse `bool`, anything not `int`/`float`, and `not 0 <= fee < 1` (catches NaN);
   - frame: refuse anything not a `pl.DataFrame`, a missing required column, an empty frame,
     a null `open_time`, an `open_time` that is not strictly increasing (`diff` of the
     series; first offending index), and a null, non-finite or `<= 0` `open`/`close`;
   - positions: refuse a length different from `frame.height`, then any value whose type
     is not `int` or whose value is not `0`/`1`. Check `type(v) is int`, which refuses
     `bool`, `float`, `None` and strings. A polars Series goes through `.to_list()` first,
     so a Boolean series gives `bool`s and a Float series gives `float`s; both are refused.
   Each message names the input, the first bad index or value, and what is accepted
   (spec R15). Commit with its tests.
2. `app/backtest/summary.py` and the summary unit tests: max drawdown as a running peak over
   the equity list; win rate `0.0` with no trades (panel #2); time in market =
   `sum(held) / len(held)`. Commit with its tests.
3. `app/backtest/engine.py`: the pass of spec Design. `cash = 1.0`, `coins = 0.0`,
   `held = 0`; row 0 marks `1.0`; for `i >= 1`: `target = positions[i-1]`; on a buy
   `entry_cash = cash`, `coins = cash * (1 - fee) / opens[i]`, `cash = 0.0`, record entry
   `(i, opens[i])`; on a
   sell `cash = coins * opens[i] * (1 - fee)`, `coins = 0.0`, append the trade with
   `return = cash / entry_cash - 1`; then `equity[i] = coins * closes[i] if held else cash`.
   After the loop, if `held`: sell at `closes[-1]`, append the trade with
   `closed_at_end=True`, and set `equity[-1] = cash`. Build the two frames and call
   `summarize`. Commit with the engine tests (example, buy-and-hold, decision candle, gap,
   last-row decision, open at end).
4. `app/backtest/__init__.py` and the API test (`from app.backtest import …`; `__all__`).
5. `pyproject.toml` packages line.
6. Run build, test and lint. Paste the output. The build verifier also builds a wheel
   (`python -m pip wheel . --no-deps -w <tmp>`, as change 0002's verifier did) and lists
   its contents. `app/backtest/__init__.py`, `inputs.py`, `engine.py` and `summary.py`
   must be in it (panel #1).

## Risks
- **Breaks nothing existing.** No module imports `app.backtest`, and `app/data/` is only
  read: the engine imports nothing from it. The data shape it consumes is
  `app/data/schema.py: SCHEMA`; it reads three of its columns. The touched shared file is
  `pyproject.toml` (one list entry). A typo there would break `pip install -e .` and every
  CI job, so step 6's setup and test run is the check.
- **Riskiest step: the pass in step 3.** An off-by-one between the decision row and the fill
  row is lookahead, the one error the intent forbids, and it can still give plausible
  numbers. Mitigations:
  - the decision-candle test uses a close different from the next open;
  - the gap test uses distinct opens on either side of the gap;
  - the two-trade example pins every equity value, not only the total.
- **Floating point.** The 1e-9 tolerance holds only if the order of operations stays close
  to the intent's formulas. Compute `cash * (1 - fee) / open` and `coins * open * (1 - fee)`
  as plain Python floats. Do not take a vectorised cumulative product of returns, whose
  rounding differs. Tests use `pytest.approx(x, abs=1e-9)`.
- **Speed.** A Python loop over a year of 1-minute rows (about 525,600) takes on the order
  of a second. That is acceptable for this change (spec Design). A faster vectorised pass is
  a later change if the owner needs it.
- **Positions as a polars Series.** An `Int64` Series with nulls gives `None` from
  `.to_list()`, which the `type(v) is int` check refuses. A Float Series of `0.0/1.0` is
  refused too. This is strict on purpose (spec R14 and the closed concern), and the error
  message tells the caller to cast to an integer type.
- **Packaging (panel #1).** No test catches a missing or misspelt `"app.backtest"` entry,
  because the editable install imports through the `app` directory. The wheel listing of
  step 6 is the check. If the owner overturns the decision at the design gate, drop step 5,
  the file and the wheel proof.
- **CLAUDE.md drift.** Until the owner lands the CLAUDE.md lines above, the deploy review
  may raise an outdated-CLAUDE.md Important finding, as on change 0003. The run cannot edit
  that file.
- **No new dependency** (coding-standards rule 5; security-baseline rule 6): polars and the
  standard library only, no numpy import.
- **The default fee** is carried forward for the owner's confirmation (spec, open question
  1). A different number changes `DEFAULT_FEE` and `test_default_fee_is_one_tenth_percent`
  only.

## Options not taken
- **Trades as a tuple of `Trade` dataclasses.** Not taken. A polars frame matches the input
  type, filters and joins directly with the equity frame, and has a fixed empty schema when
  there are no trades. The summary stays a dataclass because it is five scalars.
- **Vectorised polars pass** (shifted positions, fill flags, cumulative product). Not taken:
  it is harder to read for the off-by-one, and its rounding differs from the hand formulas.
  Correctness and exactness are the point of this change.
- **Accepting Boolean or float positions** (`True`/`1.0` as long). Not taken: the intent says
  "a position value other than 0 or 1" is refused, and security-baseline rule 2 favours a
  strict schema. A caller casts with `.cast(pl.Int8)`.
- **`win_rate = None` or NaN with no trades.** Not taken (panel #2): it would make the
  field `float | None`, and NaN fails equality checks. `trade_count == 0` tells "no trades"
  apart from "no winners".
- **Equity marked at open, or an open position left out of the trade list.** Not taken: the
  intent's recommended answers were accepted (spec, open questions 2 and 3).
- **A `Backtest` class with configuration.** Not taken: one function with a keyword fee is
  the smallest API. Later changes (shorts, slippage) can add keyword arguments.
- **Importing `app.data.schema.SCHEMA` to validate column dtypes.** Not taken: the tests'
  hand-built frames use integer times, and the engine needs only three columns. Coupling to
  the full schema would refuse valid inputs.
- **Leaving `pyproject.toml` unchanged** as the intent states. Not taken: a regular
  install would ship no engine (panel #1).
- **`[tool.setuptools.packages.find] include = ["app*"]`** instead of a third hand-kept
  entry. Not taken: it is a wider change to package discovery, so it is the owner's choice
  (panel #1).

Interrogation answers:
1. What could break: nothing that exists calls the new package. The consumers are the
   owner's own scripts. The touched shapes are `pyproject.toml`'s package list and the
   `load_klines` frame, which is read and never mutated: `validate` reads columns into
   lists and does no in-place operation.
2. Riskiest step: the engine pass (step 3), for lookahead and off-by-one. Mitigated as
   described in Risks.
3. Other options: listed above.
4. An engineer without this conversation can implement it from spec Design, the formulas in
   step 3, and the worked example's numbers in the spec. Nothing is missing.
5. Every Proof test is still to be written, in `tests/test_backtest.py`. The existing
   tests already exist and must keep passing.

## Proof
- test: test_two_trade_example_trades
- test: test_two_trade_example_equity_curve
- test: test_two_trade_example_summary
- test: test_buy_and_hold_equals_price_ratio_less_two_fees
- test: test_no_fill_on_decision_candle
- test: test_gap_fills_at_next_existing_row
- test: test_decision_on_last_row_not_filled
- test: test_open_position_closed_at_last_close
- test: test_no_trades_gives_zero_win_rate_and_flat_equity
- test: test_default_fee_is_one_tenth_percent
- test: test_positions_accepts_series_and_list
- test: test_futures_volume_ignored
- test: test_refuses_length_mismatch
- test: test_refuses_bad_position_values
- test: test_refuses_empty_frame
- test: test_refuses_non_increasing_open_time
- test: test_refuses_fee_out_of_range
- test: test_refuses_bad_frame_schema_and_prices
- test: test_public_api
- The bad-value tests are parametrised over the values in spec R14 (null, NaN, `2`, `-1`,
  `0.5`, `"1"`, `True` for positions; `-0.01`, `1`, `1.5`, NaN, `True` for fees).
- `test_no_trades_gives_zero_win_rate_and_flat_equity` asserts `trade_count == 0` and
  `win_rate == 0.0` together (panel #2).
- Target (spec Acceptance): the worked example matches to 1e-9: total return
  `0.07568647568108`, max drawdown `0.1026973009`, 2 trades, win rate `0.5`, time in market
  `3/7`, equity `[1.0, 1.0989, 1.1988, 1.1976012, 1.1976012, 1.1299367322,
  1.07568647568108]`.
- Wheel listing (panel #1): the build verifier's report shows `app/backtest/__init__.py`,
  `app/backtest/inputs.py`, `app/backtest/engine.py` and `app/backtest/summary.py` inside
  the wheel built from the branch.
- `python -m compileall -q .` prints nothing. `python -m pytest` reports every test passed
  (the existing tests plus the new ones). `python -m ruff check .` prints
  `All checks passed!`.
