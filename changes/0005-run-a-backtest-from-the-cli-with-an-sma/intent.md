# Intent: Run a backtest from the CLI with an SMA crossover
Author: owner (product owner), drafted by Claude on 2026-11-07 from the owner's request for the next step. Change id: 0005. Entry route: idea.

## Problem
Since change 0004 the project can download KuCoin klines (`app/data/`) and backtest one symbol
long/flat (`app/backtest/`), but only from Python code, and only with positions the caller
builds by hand. The owner cannot yet try a trading idea on real data without writing a script.
The smallest step that makes the tool usable end to end is one command that loads the candles,
turns them into positions with one built-in strategy, runs the backtest and prints the result.
It is kept small on purpose, so that this change and the ones that build on it stay cheap to run.

## Proposed outcome
A command `python -m app.backtest run` backtests one built-in strategy, a simple moving-average
(SMA) crossover, on one symbol's cached KuCoin klines and prints the summary.

**The command**
```
python -m app.backtest run SYMBOL INTERVAL START END [--market spot|futures]
    [--fast 20] [--slow 50] [--fee 0.001] [--cache-dir DIR]
```
- `SYMBOL`, `INTERVAL`, `START`, `END`, `--market` and `--cache-dir` mean what they mean for
  `python -m app.data download`: the same names, values, defaults and checks.
- It loads the frame with `app.data.load_klines`, which uses the cache and fills missing days
  from KuCoin as it does today.
- `--fast` and `--slow` are the two SMA lengths, in rows; `--fee` is passed to `run_backtest`
  (default `DEFAULT_FEE`, 0.1%).

**The strategy**, a public function next to the engine (the design names it and its module):
- It takes a klines frame and the two lengths and returns one position per row, `0` or `1`,
  which `run_backtest` accepts as is.
- A row's position is `1` when the fast SMA of `close` is above the slow SMA at that row's
  close, else `0`.
- It is `0` while the slow SMA is not yet defined (the first `slow − 1` rows), so the strategy
  never trades on a part-filled average.
- The averages count rows, not wall time: a missing quiet candle (change 0003) is skipped, not
  filled. The output says so in one line.
- It only reads the current row and earlier ones; the engine already fills at the next row's
  open, so the pair has no lookahead.

**The output**, plain text on stdout:
- one line naming the run: symbol, interval, market, date range, number of candles, strategy
  and its lengths, fee;
- the summary of `run_backtest`: total return, max drawdown, trade count, win rate and time in
  market, the fractions shown as percentages;
- a buy-and-hold line for comparison (see Open questions).

**Inputs it must refuse**, each with `error: ...` on stderr and exit code 2, before any
backtest:
- what `python -m app.data download` refuses (bad symbol, interval, market or dates), with the
  same messages;
- `--fast` or `--slow` not a whole number of at least 1, or `--fast` not below `--slow`;
- a date range with fewer candles than `--slow`, so the strategy could never take a position;
- a missing day (`KlineGapError`) or a download error, with the reason `load_klines` gives;
- a `--fee` that `run_backtest` refuses (`BacktestInputError`).
- Exit code 0 on success, as `python -m app.data` does.

How to check it is done:
- Tests run offline, without the network: the strategy on small frames built by hand; the
  command through its `main(argv, fetch=...)` with the existing stub (`tests/kucoin_stub.py`)
  or a pre-filled cache directory, as `tests/test_data_cli.py` does.
- They show that:
  - the strategy gives the hand-computed positions on a small frame, including the warm-up
    rows at `0`;
  - a row where the fast SMA equals the slow SMA is `0` (above, not at or above);
  - the strategy's positions never use a later row: changing the closes after row `k` leaves
    rows `0` to `k` unchanged;
  - the command prints the summary `run_backtest` returns for those positions, on a fixed
    frame, and exits 0;
  - each refused input above prints its error and exits 2.
- Build, test and lint stay green.

## Affected users and systems
- The owner, who will run backtests from the terminal on klines they download.
- `app/backtest/`: a new CLI module (`__main__.py`) and a new strategy module; the strategy
  function joins the public API in `app/backtest/__init__.py`. The engine (`inputs.py`,
  `engine.py`, `summary.py`) is used, not changed.
- `app/data/`: called through `load_klines`, not changed. Its CLI's argument checks may be
  shared; the design says whether that needs a small refactor in `app/data/`, and if so, that
  `python -m app.data` behaves exactly as before.
- New test files only, for example `tests/test_strategies.py` and `tests/test_backtest_cli.py`;
  no test file already on `main` is edited. `tests/kucoin_stub.py` and the fixture files are
  read, not changed.
- KuCoin's public REST API, only when a day is not cached yet, through `load_klines` as today.
- No new dependency. `pyproject.toml` and `.github/workflows/ci.yml` need no change.

## Constraints
- Feature-type change. Its tests are new and live in new files, so the change edits no test
  file already on `main` (a change that edits one gets an Important framework finding).
- No new dependency: pure polars and the standard library (`argparse`), no numpy of its own.
- No network in the tests: every test fetch goes through the stub or a pre-filled cache.
- No lookahead: the strategy uses only prices at or before the decision row's close.
- The engine's behaviour and public API from change 0004 do not change.
- `python -m app.data` keeps its commands, options, output and exit codes.
- Results are exact for the hand-computed tests (tolerance about 1e-9).
- Python >= 3.10, type hints on public functions, ruff clean at line length 100.
- The package version stays 0.1.0 unless the design says otherwise.
- **Guardrail lines for the owner.** A run cannot edit `CLAUDE.md`, so `plan.md` names the lines
  for the owner, who may land them before the build PR (on change 0003 an outdated `CLAUDE.md`
  kept `sdlc/review` red):
  - the opening paragraph names one CLI, `python -m app.data ...`; it needs
    `python -m app.backtest run` too;
  - the Architecture bullet for `app/backtest/` says "It does no I/O" and lists only inputs,
    engine and summary; it needs the strategy module and the CLI, and that only the CLI does
    I/O, through `load_klines`;
  - the `tests/` bullet may need the new test files.
- Out of scope: more than one strategy, other indicators, a strategy plug-in mechanism,
  parameter search, shorts, leverage, several symbols, a portfolio, plots, saving results to a
  file, a trade list on screen, slippage, futures funding, live or paper trading.

## Open questions
- **A buy-and-hold line?** Recommended: yes.
  One extra line with the total return of holding from the first fill to the end, computed by
  `run_backtest` with all positions at `1` and the same fee. It is one more call, and without
  it the strategy's number has nothing to compare to.
- **Default SMA lengths?** Recommended: `--fast 20 --slow 50`.
  A common pair; both are rows of the chosen interval. Any pair the owner prefers works.
- **Fetch missing days, or use the cache only?** Recommended: fetch, as `load_klines` does.
  The command then works on a fresh range in one step. The alternative, refusing a range that
  is not cached, would need a new cache-only mode in `app/data/`.
- **How are percentages shown?** Recommended: two decimals, for example `7.57%`, and the trade
  count as a whole number. The design may pick another layout, kept the same for every line.

## Examples/References
- A sketch of the output (numbers made up; the design fixes the exact layout):
  ```
  BTC-USDT 1hour spot, 2026-01-01 .. 2026-06-30: 4344 candles; sma-cross fast 20 slow 50; fee 0.10%
  SMAs count candles, not hours: a quiet hour without a candle is skipped.
  total return    12.34%
  max drawdown    18.20%
  trades              41
  win rate        36.59%
  time in market  48.07%
  buy and hold     9.80%
  ```
- The engine it calls: `app/backtest/` and `changes/0004-backtest-engine-core-long-flat-on-one-sy/`.
- The CLI it mirrors: `app/data/__main__.py` (`python -m app.data download`) and its tests,
  `tests/test_data_cli.py`.
