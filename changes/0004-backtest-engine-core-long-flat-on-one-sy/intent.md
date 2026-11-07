# Intent: Backtest engine core: long/flat on one symbol
Author: owner (product owner), drafted by Claude on 2026-11-07 from the owner's request for the next step. Change id: 0004. Entry route: idea.

## Problem
The project is called a crypto backtester, but it cannot backtest anything yet. Since change 0003,
`app/data/` loads KuCoin klines as polars frames, and nothing uses them. The owner wants the
smallest engine that turns a frame and a trading decision per candle into an equity curve, a list
of trades and a short summary. It is kept small on purpose, so that this change and the ones that
build on it stay cheap to run.

## Proposed outcome
A new package `app/backtest/` runs a long/flat backtest of one symbol on a klines frame from
`app.data.load_klines`, spot or futures.

**Input**
- The frame, as `load_klines` returns it (`open_time`, `open`, `high`, `low`, `close`, ...).
- A target position per candle: `0` (flat) or `1` (long), one value per row of the frame.
- The fee, a proportional fee charged on every fill. Default `0.001` (0.1%). This default is an
  assumption for the design to confirm (see Open questions).
- The engine starts flat, with equity 1.0.

**When a decision is filled**
- A candle's target position is decided at that candle's close and filled at the next row's open.
  Nothing is filled on the decision candle, so the engine never trades on a price it could not
  have known.
- A decision on the last row has no next row and is not filled.
- KuCoin frames can lack rows for quiet intervals (change 0003: no candle when nothing traded).
  The engine must not assume a row per interval. The fill is the open of the next row that
  exists, however far away it is.
- The fee is applied on each fill: buying turns equity `E` into `E × (1 − fee) / open` coins;
  selling turns `q` coins into `q × open × (1 − fee)`.

**Excluded**
- No slippage, no shorts, no leverage, no futures funding. A futures frame is backtested on its
  prices like a spot frame; its `volume` (contracts) is not used.

**Output**, as polars frames or plain dataclasses (the design picks):
- equity per candle, one row per row of the frame;
- the list of trades: entry time and price, exit time and price, and the return after fees;
- a summary: total return, max drawdown, number of trades, win rate and time in market.
  - Total return is final equity / 1.0 − 1.
  - Max drawdown is the largest fall of the equity curve from a running peak, as a fraction.
  - Win rate is the share of trades whose return after fees is above zero.
  - Time in market is the share of the frame's rows in which the position was long. It counts
    rows, not wall time, so a gap does not count as time.

**Inputs it must refuse**, each with a clear error, before any calculation:
- a position series that does not line up with the frame (a different length);
- a position value other than `0` or `1`, null included;
- a frame that is empty, or whose `open_time` is not strictly increasing;
- a fee below 0 or not below 1.

How to check it is done:
- Tests run offline, on small frames built by hand in the test file, with results computed by
  hand. They show that:
  - buy-and-hold equals the price ratio less two fees: long from the first row and closed before
    the frame ends, final equity is `(1 − fee)² × exit open / entry open`;
  - the two-trade example in Examples/References gives exactly that trade list and summary;
  - no fill happens on the decision candle: a candle whose close differs from the next row's open
    is entered at that next open, not at its own close;
  - a gap fills at the next row: with a 1h frame missing the 02:00 row, a decision at the 01:00
    candle's close fills at the 03:00 open;
  - each refused input in the list above raises the error.
- Build, test and lint stay green.

## Affected users and systems
- The owner, who will run backtests on the klines they download.
- `app/backtest/`: new package; its public API in `app/backtest/__init__.py`.
- `tests/test_backtest.py`: new test file. No test file already on `main` is edited.
- `app/data/` is read, not changed: the engine takes the frame `load_klines` returns.
- No external service, no network, no new dependency (polars is already a runtime dependency).
  `pyproject.toml` and `.github/workflows/ci.yml` need no change.

## Constraints
- Feature-type change. Its tests are new; they live in a new file, `tests/test_backtest.py`, so
  the change edits no test file already on `main` (a change that edits one gets an Important
  framework finding).
- No new dependency. Pure polars or plain Python; no numpy import of its own.
- The engine does no I/O: it never calls `load_klines` or the network itself, so the tests need no
  stub or fixture files.
- No lookahead: every fill uses only prices at or after the decision candle's close.
- Results are exact for the hand-computed tests: compare with a tolerance of about 1e-9, not by
  rounding to a few places.
- Python >= 3.10, type hints on public functions, ruff clean at line length 100.
- The package version stays 0.1.0 unless the design says otherwise.
- **Guardrail lines for the owner.** A run cannot edit `CLAUDE.md`, so `plan.md` names the lines
  for the owner:
  - lines 4 and 5: "Today the package (`app/`) holds one feature, `app/data/` ..." no longer holds
    once `app/backtest/` exists;
  - the Architecture section (lines 27 to 40) needs an `app/backtest/` line: the engine, its
    public API in `app/backtest/__init__.py`, and that its tests are `tests/test_backtest.py` with
    hand-built frames and no fixtures.
  - The owner may land these lines before the build PR. On change 0003 (PR #16) an outdated
    `CLAUDE.md` was the build PR's only Important finding, and it kept `sdlc/review` red until the
    owner bypass-merged.
- Out of scope: a CLI, shorts, leverage, several symbols, a portfolio, parameter search, plots,
  live trading, slippage, futures funding, strategies or indicators that produce the positions.

## Open questions
- **The default fee.** 0.1% per fill is an assumption. Recommended: keep `0.001` as the default,
  since it is KuCoin's base spot fee, and make it a keyword argument so a caller can pass a
  futures or a discounted rate. The design confirms the number.
- **Is equity marked at close or at open?** Recommended: at each row's close, after any fill at
  that row's open. The curve then shows the value at the end of each candle, the same moment the
  next decision is taken. Max drawdown depends on this choice; the total return does not.
- **How does the summary treat a position still open at the end of the frame?** Recommended:
  close it at the last row's close, with the fee, as a trade marked as closed at the frame's end,
  so the trade list, the total return and the final equity agree. The alternative, leaving it out
  of the trade list and the win rate while the equity keeps it, makes the numbers disagree.

## Examples/References
- **A two-trade example** (fee 0.1%; a row is `open`/`close`; times are any strictly increasing
  values):

  | Row | 0 | 1 | 2 | 3 | 4 | 5 | 6 |
  |---|---|---|---|---|---|---|---|
  | open | 100 | 100 | 110 | 120 | 100 | 90 | 81 |
  | close | 100 | 110 | 120 | 100 | 90 | 85 | 81 |
  | position | 1 | 1 | 0 | 0 | 1 | 0 | 0 |

  - Trade 1: decided at row 0's close, entered at row 1's open (100); flat decided at row 2's
    close, exited at row 3's open (120). Return after fees `1.2 × 0.999² − 1 = 0.1976012`.
  - Trade 2: entered at row 5's open (90), exited at row 6's open (81). Return after fees
    `0.9 × 0.999² − 1 = −0.1017991`.
  - Summary: 2 trades, win rate 0.5, total return `1.2 × 0.9 × 0.999⁴ − 1 ≈ 0.0756865`. Max
    drawdown and time in market follow from the answers to the open questions; the design states
    the expected numbers.
- The data layer it reads: `app/data/` and `changes/0003-replace-binance-with-kucoin-as-the-marke/`
  (its Missing candles section is why the engine must not assume a row per interval).
