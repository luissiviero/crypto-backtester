# Spec: Backtest engine core: long/flat on one symbol
Change id: 0004. Status: proposed. Produced by: sdlc plugin 1.0.51, /sdlc-design prompt v1 (article p.14). Skills: coding-standards, security-baseline, ux-and-brand, data-conventions, definition-of-done (plugin 1.0.51); overrides: none; policy sources: none

## Requirements
- R1. A new package `app/backtest/` exposes one entry point, `run_backtest(frame, positions,
  *, fee=0.001)`, and its result and error types, in `app/backtest/__init__.py` (`__all__`),
  like `app/data/__init__.py` does for the data layer.
- R2. `frame` is a polars DataFrame shaped like `app.data.load_klines`'s output (spot or
  futures); only `open_time`, `open` and `close` are read. Other columns (`high`, `low`,
  `volume`, `close_time`, `quote_volume`, anything extra) are ignored, so a futures frame's
  `volume` in contracts is never used.
- R3. `positions` holds one target position per row of the frame, as a polars Series or a
  Python sequence. Each value must be the integer `0` (flat) or `1` (long).
- R4. `fee` is a keyword argument, a proportional fee charged on every fill. Its default is
  `0.001`, one named module constant.
- R5. The engine starts flat with equity `1.0`. Row 0 is always flat, at equity `1.0`.
- R6. The position decided at row `i`'s close is filled at row `i+1`'s open, whatever the
  gap in `open_time` between the two rows. Nothing is filled at the decision row's own
  prices. The engine never assumes one row per interval.
- R7. A fill happens only when the decided position differs from the position held. Buying
  turns equity `E` into `E × (1 − fee) / open` coins. Selling turns `q` coins into
  `q × open × (1 − fee)`.
- R8. A decision on the last row is never filled at a next open, because there is no next row.
- R9. If the position is still long after the last row's open, the engine closes it at the
  last row's close, with the fee, and records it as a trade marked as closed at the frame's
  end (answer to open question 3).
- R10. Each row's equity is marked at its close, after any fill at that row's open
  (answer to open question 2). For a long row: coins × close. For a flat row: the cash. On
  the last row with an open position, the equity is the cash from the end-of-frame close, so
  the curve's last value is the final equity.
- R11. The output is one result object with three parts:
  - an equity frame, one row per row of the input, in input order;
  - a trades frame, one row per closed trade: entry time and price, exit time and price,
    return after fees, and whether the trade was closed at the frame's end;
  - a summary: total return, max drawdown, number of trades, win rate and time in market.
- R12. Summary definitions, from the intent:
  - total return = final equity / 1.0 − 1;
  - max drawdown = the largest value of `1 − equity / running peak` over the equity curve,
    as a fraction `>= 0` (`0.0` when the curve never falls);
  - win rate = the share of trades whose return after fees is `> 0`;
  - time in market = the share of the frame's rows in which the position held after the
    row's open is long. It counts rows, not wall time.
- R13. A trade's return after fees is `exit value / entry equity − 1`, which is
  `(1 − fee)² × exit price / entry price − 1`.
- R14. These inputs are refused with `BacktestInputError` (a `ValueError` subclass) before any
  calculation:
  - a `positions` length that differs from the frame's height;
  - a position value other than `0` or `1`: null, NaN, `2`, `-1`, `0.5`, a string, or a
    boolean (`True` and `False` are not `0` and `1`; see the closed concern);
  - an empty frame, or one whose `open_time` is not strictly increasing;
  - a fee below 0 or not below 1. The check is `not 0 <= fee < 1`, so NaN is refused too.
    A boolean or a non-number fee is also refused.
  - by security-baseline rule 2 (validate every input against a schema; see the closed
    concern): a `frame` that is not a polars DataFrame; a frame missing `open_time`, `open`
    or `close`; a null `open_time`; an `open` or `close` that is null, non-finite or `<= 0`.
- R15. Every error message says which input is wrong and what is accepted. It quotes the
  first bad row index or value where there is one, never a stack trace (ux-and-brand rule 4,
  applied to messages a caller reads).
- R16. The engine does no I/O: no network, no file, no cache, no `load_klines` call, no
  logging. No new dependency: polars and the standard library only, no numpy import.
- R17. No lookahead: a fill uses only the open of a row after the decision row, or the last
  row's close for the end-of-frame close. The position decided at row `i` never affects
  equity at or before row `i`.
- R18. Results match hand calculations within an absolute tolerance of about 1e-9.
- R19. `app/data/` and every test file already on `main` stay unchanged. The tests are new,
  in `tests/test_backtest.py`, on frames built by hand in that file, with no stub or fixture
  files. The package version stays `0.1.0` (`app/__init__.py` and `pyproject.toml`).
- Policies:
  - coding-standards applies: CLAUDE.md conventions (Python >= 3.10, type hints on public
    functions, ruff at line length 100, one test module per area, one module per job as in
    `app/data/`; rule 1); match `app/data/` naming, frozen dataclasses and error style
    (rule 2); every behaviour has a test (rule 4); no new dependency (rule 5); small
    functions, no dead code (rule 7).
  - security-baseline applies to input handling only (rule 2, see R14). Rules 1, 3, 5 and 7
    do not apply: no endpoint, no secret, no stored state, no network. Rule 6: no new
    dependency, no `eval`, `exec` or `pickle`.
  - Risk list (security-baseline rule 8): none of `auth`, `data migrations`, `money movement`
    or `production config` applies. The engine simulates equity on historical prices in
    memory. It moves no funds, places no orders, holds no credentials, stores nothing and
    changes no configuration.
  - ux-and-brand: no screen and no CLI (the CLI is out of scope), so rules 1 to 3 and 5 to 7
    do not apply and there is no Mock line. Rule 4 shapes the error messages (R15).
  - data-conventions does not apply: no stored field, schema of record, migration, event
    or personal data. The frames returned are in memory and public market data
    (rule 1: public).
  - definition-of-done applies: build, test and lint green with their output pasted, the
    verifier report and the gates of each phase.

## Design
- **Place in the codebase.** `app/backtest/` is a sibling of `app/data/`. It is a pure
  function of its inputs and imports nothing from `app.data`. It accepts any frame with the
  columns of R2, so a frame from `load_klines`, from `KlineGapError.frame` or built by hand
  in a test works the same. `open_time` may have any orderable dtype (the data layer's
  `Datetime("ms", "UTC")` or plain integers in tests).
- **Modules, one per job** (as in `app/data/`):
  - input validation: turns `(frame, positions, fee)` into checked plain values, or raises
    `BacktestInputError`;
  - the engine: one forward pass over the rows that tracks cash, coins, the held position,
    the equity per row and the open trade;
  - the summary: the four metrics computed from the equity column and the trades;
  - `__init__.py`: the public API.
- **Public API.**
  - `run_backtest(frame: pl.DataFrame, positions: pl.Series | Sequence[int], *, fee: float =
    DEFAULT_FEE) -> BacktestResult`.
  - `DEFAULT_FEE = 0.001`.
  - `BacktestResult`, a frozen dataclass: `equity: pl.DataFrame`, `trades: pl.DataFrame`,
    `summary: Summary`.
  - `Summary`, a frozen dataclass: `total_return: float`, `max_drawdown: float`,
    `trade_count: int`, `win_rate: float`, `time_in_market: float`.
  - `BacktestInputError(ValueError)`, like `InvalidRequestError` in `app/data/params.py`.
- **Equity frame**: `open_time` (the input's dtype), `position` (`Int8`, the position held
  after the row's open), `equity` (`Float64`, marked at the row's close).
- **Trades frame**: `entry_time` and `exit_time` (the input's `open_time` dtype),
  `entry_price` and `exit_price` (`Float64`), `return` (`Float64`, after fees),
  `closed_at_end` (`Boolean`). A normal exit has the `open_time` and `open` of the exit row.
  An end-of-frame close has the last row's `open_time` and its `close`, with
  `closed_at_end = true`. With no trades, the frame is empty but keeps these columns and
  dtypes.
- **The pass, row by row.** At row `i > 0`, the target is `positions[i − 1]`. If it differs
  from the held position, fill at `open[i]` (R7) and, on an exit, append the trade. Then mark
  equity at `close[i]`. After the last row, if long, sell at the last `close` and overwrite
  the last equity value with the resulting cash (R9, R10). `positions[last]` is never read
  for a fill (R8). A plain Python loop over the validated values is enough at this size: a
  year of 1-minute candles is about 525,600 rows. It keeps every number an exact IEEE
  product, in the order of the intent's formulas, for the 1e-9 comparisons.
- **Validation order.** fee, then frame (type, columns, height, `open_time` nulls and strict
  increase, prices), then positions (length, then values). The first failure raises. The
  message names the input, the first bad row index and the accepted values. Example:
  `positions[3] is 2: each position must be 0 (flat) or 1 (long)`.
- **Win rate with no trades** is `0.0` (open concern below). Max drawdown on a flat curve
  is `0.0`.
- **Packaging.** `pyproject.toml`'s explicit `[tool.setuptools] packages = ["app",
  "app.data"]` (added by change 0002) also gets `"app.backtest"`, so a regular
  (non-editable) install ships the new package (open concern below).
- **Unchanged**: `app/data/`, `app/__init__.py` (version `0.1.0`), every existing test
  file, `.github/workflows/ci.yml`, and the runtime dependencies.
- **Worked example** (the intent's two-trade table, fee 0.001), with the answers to open
  questions 2 and 3:
  - equity per row: `1.0`, `1.0989`, `1.1988`, `1.1976012`, `1.1976012`, `1.1299367322`,
    `1.07568647568108` (= `1.2 × 0.9 × 0.999⁴`);
  - positions held: `0, 1, 1, 0, 0, 1, 0`;
  - trades: (row 1, 100) → (row 3, 120), return `0.1976012`; (row 5, 90) → (row 6, 81),
    return `−0.1017991`; neither closed at the end;
  - summary: total return `0.07568647568108`, max drawdown `1 − 0.9 × 0.999³ =
    0.1026973009` (peak `1.1988` at row 2, trough at row 6), 2 trades, win rate `0.5`,
    time in market `3/7 ≈ 0.4285714286`.

## Open questions from intent
- "The default fee? Recommended: 0.1% (`0.001`) per fill." Answered in part: the default is
  `0.001`, as the keyword argument `fee`, per the intent's recommendation, which the owner
  accepted when they merged the intent. Carried forward: confirming that 0.1% is KuCoin's
  current base spot fee. Neither the codebase nor a policy states a fee, and this run has
  no network access to check KuCoin's fee page. The owner confirms or corrects the number at
  the design gate. Correcting it changes one constant and the default-fee test. The build
  can go ahead without it.
- "Equity marked at close or at open? Recommended: at close." Answered: at close, after any
  fill at that row's open (R10), per the intent's recommendation. The codebase has no
  earlier convention: nothing in `app/` computes equity. The worked example under Design
  states the max drawdown this gives.
- "A position still open at the frame's end? Recommended: close it at the last close."
  Answered: closed at the last row's close, with the fee, as a trade with
  `closed_at_end = true`. It counts in the trade count and the win rate, so the trade list,
  the final equity and the total return agree (R9, R10).

## Flagged concerns
- Packaging contradicts the intent: the intent says `pyproject.toml` needs no change, but its
  explicit `packages = ["app", "app.data"]` leaves `app.backtest` out of a regular
  (non-editable) install. The editable install of `commands.setup`, and so CI and the tests,
  still import it through the `app` directory. The design adds `"app.backtest"` to the list,
  a one-line edit to a non-guardrail file. The alternative is to leave `pyproject.toml`
  unchanged, as the intent says, and accept that a wheel install does not ship the engine.
- Win rate with no trades: the intent defines win rate as a share of trades and is silent
  when there are none. The design returns `0.0`, not `None` or NaN, so `Summary.win_rate`
  stays a plain `float`, and "no trades" is read from `trade_count == 0`.
- [x] Inputs refused beyond the intent's list (a frame that is not a DataFrame or lacks
  `open_time`, `open` or `close`; a null `open_time`; a null, non-finite or non-positive
  `open` or `close`; a NaN, boolean or non-number fee; boolean position values): decided:
  refuse each with `BacktestInputError` before any calculation, per security-baseline rule 2
  ("validate every external input against a schema"). A non-positive price would otherwise
  divide by zero or give negative coins, and NaN passes `fee < 0` and `fee >= 1` alike.

## Acceptance
- `tests/test_backtest.py` (new; no other test file changes) passes offline with frames
  built by hand, comparing with an absolute tolerance of about 1e-9 (`pytest.approx(...,
  abs=1e-9)` or the same). It shows:
  - buy-and-hold: long from row 0, flat decided before the end, so the final equity is
    `(1 − fee)² × exit open / entry open`;
  - the intent's two-trade example gives the trades, equity curve and summary stated
    under Design (total return `0.07568647568108`, max drawdown `0.1026973009`, 2 trades,
    win rate `0.5`, time in market `3/7`);
  - no fill on the decision candle: a row whose close differs from the next row's open is
    entered at that next open;
  - a gap: a 1h frame without the 02:00 row, a decision at the 01:00 close fills at the
    03:00 open;
  - a position open at the end is closed at the last close with the fee and marked
    `closed_at_end`, and the final equity equals `1 + total return`;
  - a decision on the last row is not filled;
  - each refused input of R14 raises `BacktestInputError`;
  - the default fee is `0.001`, and a zero-trade run gives win rate `0.0`;
  - `run_backtest` reads no network or file: the tests use no stub, fixture or monkeypatch
    of `app.data`.
- `python -m compileall -q .` prints nothing and exits 0. `python -m pytest` passes every
  test, the existing ones included. `python -m ruff check .` prints `All checks passed!`.
- `app/data/` is unchanged and the package version is still `0.1.0`.
