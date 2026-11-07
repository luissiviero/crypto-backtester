# Intent: Sweep SMA crossover lengths on one range
Author: owner (product owner), drafted by Claude on 2026-11-07 from the owner's request for the next step. Change id: 0006. Entry route: idea.

## Problem
Since change 0005, `python -m app.backtest run` backtests the SMA crossover with one pair of
lengths at a time. The first real run (BTC-USDT 1h spot, 2026-09-01 .. 2026-11-06, fast 20
slow 50) lost 10.66% while buy and hold lost 3.74%, and the owner cannot tell whether other
lengths would do better without running the command once per pair and comparing the numbers
by hand. The owner wants one command that tries a grid of lengths on one date range and shows
the results side by side. It is kept small on purpose, so that this change and the ones that
build on it stay cheap to run.

## Proposed outcome
A command `python -m app.backtest sweep` runs the SMA crossover for every pair of a grid of
fast and slow lengths on one symbol's klines and prints one row per pair, best first.

**The command**
```
python -m app.backtest sweep SYMBOL INTERVAL START END [--market spot|futures]
    [--fast 5,10,20] [--slow 30,50,100] [--fee 0.001] [--cache-dir DIR]
```
- `SYMBOL`, `INTERVAL`, `START`, `END`, `--market`, `--fee` and `--cache-dir` mean what they
  mean for `python -m app.backtest run`: the same values, defaults, checks and messages.
- `--fast` and `--slow` are comma-separated lists of whole numbers of at least 1, in candles.
  A value may repeat; repeats are tried once.
- The grid is every fast length paired with every slow length. A pair whose fast is not below
  its slow is skipped, not refused; the output says how many were skipped.
- The klines are loaded once, with `app.data.load_klines`, as `run` loads them.

**What each row holds**
- fast, slow, total return, max drawdown, trades, win rate and time in market, the numbers
  `run_backtest` returns for `sma_cross_positions(frame, fast, slow)` and the fee; a row's
  numbers equal what `python -m app.backtest run` prints for that pair on the same range.
- The rows are sorted by total return, highest first; equal returns are ordered by fast, then
  slow, smallest first, so the order never changes between runs.

**The output**, plain text on stdout:
- one line naming the run: symbol, interval, market, date range, number of candles, strategy,
  number of pairs tried (and skipped), fee;
- the SMA note `run` prints;
- a header line and one row per pair, in aligned columns, the fractions as percentages with
  two decimals;
- one buy-and-hold line, as `run` prints it;
- one warning line: the best pair on past data is often luck, so check it on another date
  range before trusting it.

**Inputs it must refuse**, each with `error: ...` on stderr and exit code 2, before any
backtest:
- what `run` refuses for `SYMBOL`, `INTERVAL`, `START`, `END`, `--market`, `--fee` and the
  cache directory, with the same messages;
- a `--fast` or `--slow` list that is empty or holds a value that is not a whole number of at
  least 1, naming the value;
- a grid with no pair whose fast is below its slow, checked before any kline is loaded;
- a grid of more than 400 such pairs (see Open questions), checked before any kline is loaded;
- a range in which every pair is skipped. A pair whose slow length is not below the candle
  count (`run` refuses that range) is skipped and counted, as a pair with fast not below slow
  is.
- Exit code 0 on success.

How to check it is done:
- Tests run offline, without the network, through `main(argv, fetch=...)` with the existing
  stub (`tests/kucoin_stub.py`) and the fixed clock, as the tests of `run` do.
- They show that:
  - each row equals the numbers `run_backtest` gives for that pair on the same frame;
  - the rows are sorted by total return, ties by fast then slow;
  - pairs with fast not below slow, and pairs with slow not below the candle count, are
    skipped and counted in the header line;
  - repeated values are tried once;
  - the klines are loaded once for the whole grid (the stub sees one set of requests);
  - each refused input above prints its error and exits 2;
  - `python -m app.backtest run` prints exactly what it printed before.
- Build, test and lint stay green.

## Affected users and systems
- The owner, who will compare lengths from the terminal.
- `app/backtest/__main__.py`: a new `sweep` sub-command next to `run`; the argument handling
  `run` and `sweep` share may move into helpers there. Whether the sweep itself lives in the
  CLI module or a new module is the design's choice.
- `app/backtest/` engine and strategy (`inputs.py`, `engine.py`, `summary.py`,
  `strategy.py`): used, not changed.
- `app/data/`: called through `load_klines`, not changed.
- New test file only, for example `tests/test_backtest_sweep.py`; no test file already on
  `main` is edited. `tests/kucoin_stub.py` and the fixture files are read, not changed.
- KuCoin's public REST API, only when a day is not cached yet, through `load_klines` as today.
- No new dependency. `pyproject.toml` and `.github/workflows/ci.yml` need no change.

## Constraints
- Feature-type change. Its tests live in a new file, so the change edits no test file already
  on `main`.
- **No new public name.** `tests/test_backtest.py: test_public_api` pins
  `app.backtest.__all__` exactly, so adding a name would force an edit of a test file already
  on `main` (change 0005 had to do this). Keep `app/backtest/__init__.py`'s `__all__` as it
  is: the sweep is a CLI command, and any helper it needs stays out of `__all__`.
- `python -m app.backtest run` keeps its options, output and exit codes.
- No new dependency: polars and the standard library, no numpy of its own, no threads or
  processes.
- No network in the tests: every fetch goes through the stub or a pre-filled cache.
- No lookahead: each pair uses `sma_cross_positions` as it is.
- Speed: one backtest of a year of 1h candles (8760 rows) takes about 10 ms on the owner's
  machine (measured 2026-11-07), so a 400-pair grid on a year of 1h candles takes a few
  seconds. 1m candles are 60 times as many rows; the design says whether the output warns
  before a long run.
- Python >= 3.10, type hints on public functions, ruff clean at line length 100.
- The package version stays 0.1.0 unless the design says otherwise.
- **Guardrail lines for the owner.** A run cannot edit `CLAUDE.md`, so `plan.md` names the lines
  for the owner, who may land them before the build PR is reviewed (on change 0003 an outdated
  `CLAUDE.md` kept `sdlc/review` red):
  - the opening paragraph names the CLI `python -m app.backtest run`; it needs `sweep` too;
  - the `app/backtest/` Architecture bullet lists the modules and test files; it needs any new
    module and the new test file.
- Out of scope: other strategies or indicators, other ranking measures, a held-out date range
  or walk-forward check, saving results to a file, plots, ranges of lengths (`5..50`), several
  symbols, shorts, slippage, futures funding, parallel runs.

## Open questions
- **Default grids?** Recommended: `--fast 5,10,20 --slow 30,50,100`.
  Nine pairs, all with fast below slow, around the `run` defaults (20/50); the owner can pass
  any lists.
- **A cap on the grid size?** Recommended: refuse more than 400 pairs.
  Twenty by twenty lengths is plenty for a first look and runs in seconds on 1h candles. The
  cap counts the pairs kept, after skipping, so a big list that is mostly skipped still runs.
- **Rank by total return only?** Recommended: yes.
  It is the number the owner compared first. Max drawdown and the other columns are shown, so
  the owner can read them; sorting by another measure is a later change.
- **Show every row, or only the best few?** Recommended: every row.
  A 400-row table is long but complete; a `--top` option is a later change if it is needed.

## Examples/References
- A sketch of the output (numbers made up; the design fixes the exact layout):
  ```
  BTC-USDT 1h spot, 2026-01-01 .. 2026-10-31: 7296 candles; sma-cross, 9 pairs (0 skipped); fee 0.10%
  SMAs count candles, not wall time: an interval without a candle is skipped, not filled.
  fast  slow  total return  max drawdown  trades  win rate  time in market
    10    50        14.20%        11.30%      18    38.89%          47.10%
    20   100         9.05%        15.02%       9    44.44%          51.30%
     5    30        -2.10%        19.75%      44    27.27%          45.80%
  ...
  buy and hold     -3.74%
  The best pair on past data is often luck: check it on another date range before trusting it.
  ```
- The command it extends: `app/backtest/__main__.py` (`python -m app.backtest run`) and its
  tests, `tests/test_backtest_cli.py`; change `changes/0005-run-a-backtest-from-the-cli-with-an-sma/`.
