# Spec: Sweep SMA crossover lengths on one range
Change id: 0006. Status: proposed. Produced by: sdlc plugin 1.0.51, /sdlc-design prompt v1 (article p.14). Skills: coding-standards, security-baseline, ux-and-brand, data-conventions, definition-of-done (plugin 1.0.51); overrides: none; policy sources: none

## Requirements
- R1. `python -m app.backtest sweep SYMBOL INTERVAL START END [--market spot|futures]
  [--fast LIST] [--slow LIST] [--fee FEE] [--cache-dir DIR]` exists next to `run`.
- R2. `SYMBOL`, `INTERVAL`, `START`, `END`, `--market`, `--fee` and `--cache-dir` behave as
  they do for `run`: the same defaults (`spot`, `0.001`, the data layer's cache directory),
  the same checks and the same messages (`app/data/params.py: make_request`, `--market`
  `choices=MARKETS`, the fee text parse and `app/backtest/inputs.py: _check_fee`, the
  `OSError` cache-directory hint of `main`).
- R3. `--fast` and `--slow` are comma-separated lists of whole numbers of at least 1; the
  defaults are `5,10,20` and `30,50,100`. A repeated value is tried once.
- R4. A list that is empty, or holds an item that is not a whole number of at least 1, is
  refused naming the item, in the words `run` uses: `fast 'x' is not a whole number of at
  least 1`, `slow 0 is not a whole number of at least 1`; an empty list gets
  `--fast is empty: pass comma-separated whole numbers, for example 5,10,20` (`--slow`:
  `30,50,100`).
- R5. The grid is every distinct fast paired with every distinct slow. A pair whose fast is
  not below its slow is skipped and counted.
- R6. Before any kline is loaded: a grid with no pair whose fast is below its slow is refused;
  a grid of more than 400 such pairs is refused, naming the count and the cap.
- R7. The klines are loaded once, with `app.data.load_klines`, with the same arguments `run`
  passes.
- R8. After loading, a pair whose slow is not below the candle count (`run` refuses
  `frame.height <= slow`) is skipped and counted with the R5 skips; if every pair is skipped,
  the range is refused.
- R9. Each remaining pair is backtested as `run_backtest(frame, sma_cross_positions(frame,
  fast, slow), fee=fee)`; its row shows fast, slow, total return, max drawdown, trades, win
  rate and time in market, formatted as `run` formats them, so each number equals what `run`
  prints for that pair on the same range.
- R10. Rows are sorted by total return, highest first; equal returns by fast, then slow,
  smallest first.
- R11. Output on stdout, in order: the run line; `run`'s SMA note (`SMA_NOTE`); a header line
  and one row per pair in aligned columns; `run`'s buy-and-hold line, character for character;
  the warning line (Design, "Output").
- R12. Every refusal prints one `error: ...` line on stderr, prints nothing on stdout and exits
  2; success exits 0. Every refusal of R2, R4 and R6 happens before any fetch.
- R13. `python -m app.backtest run` keeps its options, help, output and exit codes; every test
  already on `main` passes unchanged.
- R14. `app.backtest.__all__` is unchanged; any sweep helper stays out of it. `app/data/`,
  `inputs.py`, `engine.py`, `summary.py` and `strategy.py` are unchanged. No new dependency
  (polars and the standard library, no threads or processes). Version stays `0.1.0`.
- R15. Tests live in a new file only and run offline (stub `tests/kucoin_stub.py`, the
  `clock` fixture, `--cache-dir` under `tmp_path`).
- Policies:
  - coding-standards applies: `CLAUDE.md` conventions first (rule 1: Python >= 3.10, type
    hints on public functions, ruff at line length 100, one test module per area); rule 2,
    the sweep follows `__main__.py`'s style (text options parsed by the command, one
    `error:` line, module constants for copy); rule 3, the diff stays inside plan.md; rule 4,
    every behaviour has a test; rule 5, no dependency; rule 7, small functions, no dead code.
  - security-baseline applies to the command-line input: rule 2, every input is validated
    before use and its size is bounded (the 400-pair cap; the pair count is computed without
    building the grid, so a long list cannot cost time or memory before the cap refuses it);
    no path or URL is built from input beyond what `load_klines` already does. Rule 6: no
    `eval`, `exec`, `pickle` or shell. Rule 7: the only network call is `load_klines`'s
    existing one; the tests make none. Rules 1, 3, 4 and 5 do not apply: no endpoint, secret,
    personal data or stored state of its own.
  - Risk list (security-baseline rule 8): none of `auth`, `data migrations`, `money movement`
    or `production config` applies. The command simulates a strategy on public historical
    prices in memory: no order, no funds, no credential, no stored schema, no configuration.
  - ux-and-brand applies to the CLI text output: rule 3 (success and every error state are
    specified, R11 and R12), rule 4 (each message says what is wrong and what to pass), rule 6
    (labels, note and warning are module constants, as `SMA_NOTE` is). Rule 1: the layout
    follows the intent's sketch and `run`'s output. Rules 2, 5 and 7 do not apply: no colours,
    fonts, controls or screenshots in plain stdout text.
  - data-conventions does not apply: no new stored field, schema, migration, event or
    personal data; the command reads and fills the existing public kline cache through
    `load_klines` (rule 1), and writes no report file (rule 6).
  - definition-of-done applies: build, test and lint green with their output pasted, the
    verifier report and each phase's gate.

## Design
- **Sweep module** (`app/backtest/sweep.py`, new), pure, no I/O, not re-exported from
  `app/backtest/__init__.py` (R14), as `strategy.validate_lengths` is a module function:
  - `MAX_PAIRS = 400`.
  - `count_pairs(fasts, slows) -> tuple[int, int]`: (kept, skipped) for two sorted lists of
    distinct lengths, kept = pairs with fast below slow, computed per fast by bisecting the
    slows, so the cap check costs nothing on a long list (security-baseline rule 2).
  - `pairs(fasts, slows) -> list[tuple[int, int]]`: the kept pairs, built only after the cap
    check.
  - `SweepRow` (frozen dataclass: `fast`, `slow`, `summary: Summary`) and
    `sweep(frame, pairs, fee) -> list[SweepRow]`: one `run_backtest(frame,
    sma_cross_positions(frame, fast, slow), fee=fee)` per pair, sorted by the key
    `(-summary.total_return, fast, slow)` (R10).
- **CLI** (`app/backtest/__main__.py`): a second sub-command `sweep` beside `run`.
  - Arguments in `run`'s order: positionals, `--market`, `--fast` (default `"5,10,20"`),
    `--slow` (default `"30,50,100"`), `--fee`, `--cache-dir`; the epilog is `SMA_NOTE`. The
    lines `run` and `sweep` share move into small helpers (the range arguments, the fee and
    cache arguments, the kline load, the buy-and-hold line); `run`'s help text and output stay
    byte for byte the same (R13).
  - Order of checks: (1) `make_request(...)` with `loader.utc_now().date()`; (2) `--fast` then
    `--slow` parsed as lists: split on `,`, each item through `run`'s `_length` (`int()` of
    the text, else the R4 message), then `< 1` refused with the same words, then deduplicated
    and sorted; (3) `--fee` as `run` parses it; (4) `count_pairs`: 0 kept → `no pair has fast
    below slow: pass a --fast value below a --slow value`; more than `MAX_PAIRS` →
    `the grid has N pairs with fast below slow, more than 400: pass shorter --fast or --slow
    lists`; (5) `load_klines(...)` once; (6) drop pairs with `slow >= frame.height` and add
    them to the skipped count; none left → `the range has N candles, not more than any slow
    length with a smaller fast: no pair could take a position; widen the dates or lower
    --slow`; (7) print the run line and the note, flushed; (8) `sweep(...)` and buy and hold
    (`run_backtest(frame, [1] * frame.height, fee=fee)`); (9) print the table, the buy-and-hold
    line and the warning.
  - Every refusal is a `BacktestInputError` raised by the command (or `run`'s existing
    exceptions), so `main`'s existing handler prints it and returns 2; `main` itself does
    not change.
- **Output, worked shape** (numbers made up):
  ```
  BTC-USDT 1h spot, 2026-01-01 .. 2026-10-31: 7296 candles; sma-cross, 9 pairs tried, 0 skipped; fee 0.10%
  SMAs count candles, not wall time: an interval without a candle is skipped, not filled.
  fast  slow  total return  max drawdown  trades  win rate  time in market
    10    50        14.20%        11.30%      18    38.89%          47.10%
    20   100         9.05%        15.02%       9    44.44%          51.30%
     5    30        -2.10%        19.75%      44    27.27%          45.80%
  buy and hold     -3.74%
  The best pair on past data is often luck: check it on another date range before trusting it.
  ```
  - The run line: `{symbol} {interval} {market}, {start} .. {end}: {height} candles;
    sma-cross, {tried} pairs tried, {skipped} skipped; fee {fee:.2%}`. "Tried" is the number
    of rows; "skipped" counts both kinds of skip (R5, R8). The intent's sketch reads
    `9 pairs (0 skipped)`; the intent leaves the exact layout to the design, and the explicit
    words say which number is which.
  - Table: seven columns separated by two spaces, each right-aligned to the width of its
    header or its longest cell, whichever is wider; fractions as `f"{x:.2%}"`, trades as an
    integer, as `run` prints them (R9).
  - Buy-and-hold: `f"{'buy and hold':<14}{value:>8}"`, `run`'s line.
- **Long runs**: no separate warning. The run line, which names the candle and pair counts, is
  printed and flushed before the first backtest, so a large run shows its size at once
  (the intent's speed note: 400 pairs on a year of 1m candles take minutes). The 400 cap
  bounds the worst case.
- **Unchanged**: `run` (`_run`'s behaviour), `main`, `app/backtest/__init__.py`, the engine,
  strategy, summary and inputs modules, `app/data/`, `pyproject.toml`, the CI workflow.

## Open questions from intent
- "Default grids? Recommended: `--fast 5,10,20 --slow 30,50,100`." Answered: those defaults,
  per the recommendation the owner accepted by opening the intent PR (fast lane); nine pairs
  around `run`'s defaults 20/50 (`app/backtest/__main__.py`, `--fast`/`--slow` defaults) (R3).
- "A cap on the grid size? Recommended: refuse more than 400 pairs." Answered: 400, counted
  on the pairs with fast below slow, before loading (R6); a bound on input size is also
  security-baseline rule 2. The candle-count skips (R8) cannot count toward it, since they
  are known only after loading, which the intent puts after the cap check.
- "Rank by total return only? Recommended: yes." Answered: yes, ties by fast then slow (R10).
- "Show every row, or only the best few? Recommended: every row." Answered: every row; no
  `--top` option (R11).

## Flagged concerns
- decided (by panel #1): Keep argparse's refusal with no argv rewrite; correct the aside, since a bare `-5` is a value on every version and only a two-word comma list starting with a minus is refused by argparse on 3.10-3.13; and add to `test_sweep_refuses_bad_lengths` a two-word `--fast -5` case expecting the R4 message and a two-word `--fast -5,10` case asserting only exit 2, nothing on stdout and no stub call. — A `--fast` or `--slow` list that starts with a minus sign, written as two words
  (`--fast -5,10`), may be read by argparse as an option rather than a value, depending on the
  Python version's negative-number rule: argparse then prints its usage and
  `error: argument --fast: expected one argument` and exits 2, which does not name the value
  as R4 asks. Written as `--fast=-5,10`, or with the minus sign later in the list, the value
  reaches the command and gets the R4 message. `run` has the same behaviour for `--fast -5`
  on the versions where argparse reads it as an option. The design accepts argparse's refusal
  (exit 2, one `error:` line in argparse's form) rather than rewriting argv; the test of a
  negative item uses the `--fast=...` form.

## Acceptance
- A new test file (for example `tests/test_backtest_sweep.py`); no test file already on
  `main` changes. Offline, through `main(argv, fetch=stub)` with `tests/kucoin_stub.py`, the
  `clock` fixture and a `tmp_path` cache, the tests show:
  - each row's numbers equal `run_backtest`'s for that pair on the same frame, formatted as
    `run` prints them, and the whole stdout equals the expected lines;
  - the rows are sorted by total return, ties by fast then slow (a tie is built with pairs
    that never trade, whose return is exactly 0);
  - pairs with fast not below slow and pairs with slow not below the candle count are
    skipped and counted in the run line;
  - repeated values are tried once;
  - the stub sees exactly the requests one `run` of the same range makes;
  - each refusal of R2, R4, R6 and R8 prints one `error:` line, nothing on stdout, exits 2,
    and (R2, R4, R6) the stub sees no request; a bad `--market` exits 2 through argparse;
  - the defaults give nine pairs;
  - `python -m app.backtest run` prints what `tests/test_backtest_cli.py` expects (that file
    passes unchanged).
- `python -m compileall -q .` prints nothing and exits 0; `python -m pytest` passes every
  test; `python -m ruff check .` prints `All checks passed!`.
- `app.backtest.__all__`, `app/data/`, the engine modules, `pyproject.toml` and the version
  `0.1.0` are unchanged.
- Mock: none, screens follow the UX conventions
