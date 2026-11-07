# Spec: Run a backtest from the CLI with an SMA crossover
Change id: 0005. Status: proposed. Produced by: sdlc plugin 1.0.51, /sdlc-design prompt v1 (article p.14). Skills: coding-standards, security-baseline, ux-and-brand, data-conventions, definition-of-done (plugin 1.0.51); overrides: none; policy sources: none

## Requirements
- R1. A public strategy function `sma_cross_positions(frame, fast, slow)` in a new module
  `app/backtest/strategy.py`, exported from `app/backtest/__init__.py` (`__all__`). It returns
  one position per row of `frame`, the integer `0` or `1`, in a form `run_backtest` accepts as
  is.
- R2. A row's position is `1` when the fast SMA of `close` is strictly above the slow SMA at
  that row, else `0`. A row where the two are equal is `0`.
- R3. The position is `0` on the first `slow − 1` rows, where the slow SMA is not defined. No
  average is ever computed over fewer rows than its length.
- R4. The averages count rows, not wall time: a missing candle (an interval without trades,
  change 0003) is skipped, never filled.
- R5. No lookahead: a row's position depends only on the closes of that row and earlier rows.
  Changing the closes after row `k` leaves the positions of rows `0` to `k` unchanged. The
  engine fills each decision at the next row's open (change 0004), so the pair trades on no
  future price.
- R6. `sma_cross_positions` refuses, with `BacktestInputError`, a `fast` or `slow` that is not
  an `int` of at least 1 (a `bool` is refused), a `fast` not below `slow`, and a `frame` that
  is not a polars DataFrame or has no numeric `close` column (security-baseline rule 2).
- R7. A command `python -m app.backtest run SYMBOL INTERVAL START END [--market spot|futures]
  [--fast 20] [--slow 50] [--fee 0.001] [--cache-dir DIR]`, in a new module
  `app/backtest/__main__.py` with `main(argv=None, fetch=None) -> int`, like
  `app/data/__main__.py`.
- R8. `SYMBOL`, `INTERVAL`, `START`, `END`, `--market` (default `spot`) and `--cache-dir` take
  the same values, defaults and checks as `python -m app.data download`, with the same
  messages. `INTERVAL` is one of `1m … 1d` as in `app/data/params.py: INTERVAL_MS` (the
  intent's sketch writes `1hour`, KuCoin's spot name; the command takes `1h`, as `download`
  does).
- R9. Defaults: `--fast 20`, `--slow 50`, `--fee` = `DEFAULT_FEE` (`0.001`).
- R10. The command loads the frame with `app.data.load_klines` (cache first, then KuCoin for
  the days not cached), computes the positions with `sma_cross_positions`, runs
  `run_backtest` with them and the fee, and runs `run_backtest` a second time with every
  position at `1` and the same fee for the buy-and-hold line.
- R11. On success it prints to stdout exactly these eight lines and exits 0:
  1. `<SYMBOL> <INTERVAL> <market>, <START> .. <END>: <n> candles; sma-cross fast <f> slow <s>; fee <fee %>`
  2. `SMAs count candles, not wall time: an interval without a candle is skipped, not filled.`
  3. `total return` and the strategy's total return;
  4. `max drawdown`;
  5. `trades`, the trade count as a whole number;
  6. `win rate`;
  7. `time in market`;
  8. `buy and hold` and the buy-and-hold total return.
  Each of lines 3 to 8 is the label left-aligned in 14 characters and the value right-aligned
  in 8 (`f"{label:<14}{value:>8}"`), wider only when a value needs it. Fractions are
  percentages with two decimals (`7.57%`, `-3.10%`), the fee too (`0.10%`). The symbol is
  upper case and the dates are `YYYY-MM-DD`.
- R12. Refused inputs, each before any backtest, print one `error: <reason>` line on stderr and
  exit 2:
  - what `download` refuses (symbol, interval, market, dates), with its messages;
  - `--fast` or `--slow` not a whole number of at least 1, or `--fast` not below `--slow`;
  - a `--fee` that is not a number, or one the engine's fee check refuses
    (`BacktestInputError`, with the engine's message), both before any kline is loaded
    (panel #1);
  - a frame with no more candles than `--slow` (`height <= slow`, panel #2): such a range
    can never take a position;
  - a missing day (`KlineGapError`) or a download error (`DownloadError`), with the reason
    `load_klines` gives; a cache directory error (`OSError`) with the same hint as `download`.
- R13. Messages say what is wrong and what is accepted, and never show a stack trace
  (ux-and-brand rule 4).
- R14. Unchanged: the engine (`inputs.py`, `engine.py`, `summary.py`) and its public API; all
  of `app/data/` and `python -m app.data` (commands, options, output, exit codes); every test
  file already on `main`, `tests/kucoin_stub.py` and the fixtures; `pyproject.toml` (its
  package list already holds `app.backtest`, which ships the two new modules);
  `.github/workflows/ci.yml`; the package version `0.1.0`.
- R15. No new dependency: polars and the standard library (`argparse`), no numpy import.
- R16. Tests are offline and new, in new files: the strategy on frames built by hand; the
  command through `main(argv, fetch=...)` with `tests/kucoin_stub.py` or a pre-filled cache
  directory and the fixed clock of `tests/conftest.py`. Hand-computed results match within
  about 1e-9.
- Policies:
  - coding-standards applies: CLAUDE.md conventions (Python >= 3.10, type hints on public
    functions, ruff at 100, one test module per area, one module per job; rule 1); the CLI
    mirrors `app/data/__main__.py` (argparse sub-command, `main(argv, fetch)`, `error: ...`
    and exit 2, copy as module constants; rule 2); every behaviour has a test (rule 4); no
    new dependency (rule 5); small functions, no dead code (rule 7).
  - security-baseline applies to input handling (rule 2): every argument is checked before
    it is used (R6, R8, R12); the symbol and interval reach a URL or a cache path only
    through `app/data/params.py`'s existing checks. Rule 6: no `eval`, `exec`, `pickle` or
    shell. Rule 7: the only network call is `load_klines`'s existing one to KuCoin's public
    API; the tests make none. Rules 1, 3, 4 and 5 do not apply: no endpoint, no secret, no
    personal data, no stored state of its own.
  - Risk list (security-baseline rule 8): none of `auth`, `data migrations`, `money movement`
    or `production config` applies. The command simulates a strategy on historical public
    prices in memory: it places no order, moves no funds, holds no credential, adds no
    stored schema and changes no configuration.
  - ux-and-brand applies to the CLI output, a text interface a person reads: rule 3 (the
    success output and every error state are specified, R11 and R12), rule 4 (R13), rule 6
    (the note and labels are module constants, as `DOWNLOAD_NOTES` is). Rules 2, 5 and 7 do
    not apply: no colours, fonts, controls or screenshots in plain stdout text. Rule 1: the
    layout follows the intent's sketch and `app/data/__main__.py`'s style.
  - data-conventions does not apply: no new stored field, schema, migration, event or
    personal data. The command reads and fills the existing kline cache through
    `load_klines`; the market data is public (rule 1).
  - definition-of-done applies: build, test and lint green with their output pasted, the
    verifier report and each phase's gate.

## Design
- **Strategy module** (`app/backtest/strategy.py`), pure, no I/O:
  - `sma_cross_positions(frame: pl.DataFrame, fast: int, slow: int) -> pl.Series` returns an
    `Int8` Series named `position`, one value per row. Its `.to_list()` gives Python `int`s,
    which the engine's `type(value) is int` check accepts.
  - The averages are polars rolling means of `close` over `fast` and `slow` rows, which are
    null until the window is full (R3). The position is `fast_sma > slow_sma`, with a
    null comparison read as `0`. A rolling window over rows is what R4 asks: a missing
    candle is simply not a row.
  - `validate_lengths(fast, slow) -> None` holds the length checks of R6, raising
    `BacktestInputError`; both `sma_cross_positions` and the CLI call it. It is a module
    function, not part of `app/backtest/__init__.py`, as `make_request` is for `app/data/`.
  - The strategy name shown on screen is a module constant, `sma-cross`.
- **CLI module** (`app/backtest/__main__.py`), the only part of `app/backtest/` that does
  I/O:
  - argparse with one sub-command `run` (`prog="python -m app.backtest"`), positional
    `SYMBOL INTERVAL START END` and `--market` with `choices=MARKETS`, default `spot`,
    exactly as `download` declares them, so a bad market gets argparse's own message and exit
    2, as on `download`. `--fast`, `--slow` and `--fee` are read as text and converted by
    the command, so a bad value gives one `error:` line and `main` returns 2 instead of an
    argparse usage dump. `--cache-dir` is passed through as `download` passes it.
  - Order of checks: (1) `make_request(symbol, interval, start, end, market, today)` from
    `app/data/params.py`, with `today` from `loader.utc_now()` as `_download` does: the same
    function, so the same messages, and it gives the normalised symbol and parsed dates for
    the header; (2) `--fast` and `--slow` to `int`, then `validate_lengths`; (3) `--fee` to
    `float`, then the engine's own fee check, `app/backtest/inputs.py: _check_fee`, called
    as it is (panel #1: one copy of the `0 <= fee < 1` rule, `inputs.py` unchanged, nothing
    downloaded for a bad fee); (4) `load_klines(...)` with the request's values, `market`,
    `cache_dir` and `fetch`; (5) refuse `frame.height <= slow` (panel #2); (6)
    `sma_cross_positions`, then `run_backtest(frame, positions, fee=fee)`; (7)
    `run_backtest(frame, [1] * frame.height, fee=fee)` for buy and hold.
  - `main` catches `InvalidRequestError`, `KlineGapError`, `DownloadError` and
    `BacktestInputError` and prints `error: {error}` to stderr with exit 2; an `OSError`
    gets `download`'s cache-directory hint. The length, fee-text and candle-count refusals
    raise `BacktestInputError` from the command, so they go through the same handler.
  - Message shapes (final wording at the build, each naming the value and what is
    accepted): `fast '0' is not a whole number of at least 1`, `fast 50 is not below slow
    20: the fast SMA must be the shorter one`, `fee 'abc' is not a number: pass a
    proportional fee, for example 0.001`, `the range has 30 candles, not more than slow 50:
    the strategy could never take a position; widen the dates or lower --slow`.
- **app/data/ needs no refactor.** The command calls `make_request`, `MARKETS`,
  `loader.utc_now` and `load_klines` as they are; `python -m app.data` is untouched.
- **Buy and hold** is "long from the first fill to the end": all positions `1`, so the engine
  buys at row 1's open and closes at the last close, both with the fee. It is one more
  `run_backtest` call, no new engine code.
- **Output, worked shape** (numbers made up):
  ```
  BTC-USDT 1h spot, 2026-01-01 .. 2026-06-30: 4344 candles; sma-cross fast 20 slow 50; fee 0.10%
  SMAs count candles, not wall time: an interval without a candle is skipped, not filled.
  total return    12.34%
  max drawdown    18.20%
  trades              41
  win rate        36.59%
  time in market  48.07%
  buy and hold     9.80%
  ```
- **Docs inside the package**: the `app/backtest/__init__.py` docstring says the engine and
  strategy do no I/O and the CLI loads klines through `load_klines`.

## Open questions from intent
- "A buy-and-hold line? Recommended: yes." Answered: yes, per the intent's recommendation,
  which the owner accepted by opening the intent PR (fast lane): one line `buy and hold`, from
  a second `run_backtest` call with every position `1` and the same fee (R10, R11).
- "Default SMA lengths? Recommended: `--fast 20 --slow 50`." Answered: `20` and `50`, per the
  recommendation (R9). Neither the codebase nor a policy names other defaults.
- "Fetch missing days, or use the cache only? Recommended: fetch, as `load_klines` does."
  Answered: fetch, by calling `load_klines` with its default `cache=True`
  (`app/data/loader.py: load_klines`); no cache-only mode is added to `app/data/`.
- "How are percentages shown? Recommended: two decimals, for example `7.57%`, and the trade
  count as a whole number." Answered: two decimals for every fraction and the fee, the trade
  count as a whole number, in one fixed two-column layout (R11).

## Flagged concerns
- decided (by panel #1): The CLI's fee parser refuses a bad --fee before load_klines by returning inputs._check_fee(float(text)), so inputs.py stays unchanged and the engine's message is kept; test_run_refuses_bad_fee also asserts the stub's calls == [] for --fee 1.5 and --fee -0.1. — Where a bad `--fee` is caught: the intent says a fee "that `run_backtest` refuses
  (`BacktestInputError`)" is refused "before any backtest", and is silent on whether that is
  before or after loading the klines. The design converts the text to a number before loading
  (so `--fee abc` costs nothing) but leaves the range check to the engine, which runs after
  `load_klines`: `--fee 1.5` on an uncached range downloads and caches the days first, then
  exits 2 with the engine's message. The alternative is a range check in the CLI before
  loading, which copies the engine's rule (`0 <= fee < 1`) into a second place, since the
  intent keeps `inputs.py` unchanged.
- decided (by panel #2): Refuse when `frame.height <= slow` (exit 2, message "the range has N candles, not more than slow S: the strategy could never take a position; widen the dates or lower --slow"), and add proof tests pinning `--slow 24` on 24 candles to exit 2 and `--slow 23` on 24 candles to exit 0. — The candle-count check follows the intent's literal rule, "fewer candles than `--slow`":
  a range of exactly `--slow` candles is accepted, although its only possible long signal is
  on the last row, which the engine never fills (change 0004, R8), so such a run always
  prints 0 trades. The intent's stated reason ("so the strategy could never take a position")
  would refuse it too (a height of `--slow` or less). The design keeps the literal rule; the
  owner may ask for `<=` instead.

## Acceptance
- New test files only (for example `tests/test_strategies.py` and `tests/test_backtest_cli.py`);
  no test file already on `main` changes. They run offline and show:
  - the strategy's positions on a small hand-built frame match the hand-computed list,
    warm-up rows `0` included;
  - a row where the fast SMA equals the slow SMA is `0`;
  - changing the closes after row `k` leaves rows `0` to `k` unchanged;
  - the returned Series is accepted by `run_backtest` as is;
  - each refused `fast`/`slow` of R6 raises `BacktestInputError`;
  - `python -m app.backtest run` on a fixed frame from the stub (or a pre-filled cache) prints
    the eight lines of R11 with the summary `run_backtest` returns for
    `sma_cross_positions` on that frame and the buy-and-hold return, and exits 0;
  - each refused input of R12 prints its `error:` line on stderr and exits 2 (a bad
    `--market` through argparse's exit 2, as on `download`); a bad `--fee` makes no fetch;
  - on a 24-candle range, `--slow 24` exits 2 and `--slow 23` exits 0;
  - `sma_cross_positions` is in `app.backtest.__all__`.
- Results match hand calculations within about 1e-9.
- `python -m compileall -q .` prints nothing and exits 0; `python -m pytest` passes every
  test, the existing ones included; `python -m ruff check .` prints `All checks passed!`.
- `app/data/`, the engine modules, `pyproject.toml` and the version `0.1.0` are unchanged.
- Mock: none, screens follow the UX conventions
