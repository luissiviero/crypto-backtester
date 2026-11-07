# Plan: Run a backtest from the CLI with an SMA crossover (from intent.md 2026-11-07, spec.md 2026-11-07)

## Files that change
- `app/backtest/strategy.py` — new: `STRATEGY_NAME = "sma-cross"`,
  `validate_lengths(fast: int, slow: int) -> None` and
  `sma_cross_positions(frame: pl.DataFrame, fast: int, slow: int) -> pl.Series` (spec R1–R6,
  Design "Strategy module").
- `app/backtest/__main__.py` — new: the CLI `python -m app.backtest run ...`,
  `main(argv: Sequence[str] | None = None, fetch: Fetch | None = None) -> int`, a `_parser()`,
  the `_run(args, fetch) -> int` command, the output constants (`SMA_NOTE`, the labels) and
  small helpers (`_length`, `_fee`, `_percent`); ends with
  `if __name__ == "__main__": sys.exit(main())` as `app/data/__main__.py` does.
- `app/backtest/__init__.py` — re-export `sma_cross_positions`, add it to `__all__` (sorted
  as now), and update the docstring: the engine and strategy do no I/O; the CLI
  (`python -m app.backtest run`) loads klines through `app.data.load_klines`.
- `tests/test_strategies.py` — new: the strategy tests of Proof, on frames built by hand in
  the file (a `_frame(closes)` helper with integer `open_time`, `open` = `close`).
- `tests/test_backtest_cli.py` — new: the CLI tests of Proof, through `main(argv,
  fetch=kucoin)` with `tests/kucoin_stub.py` and the `clock` fixture of `tests/conftest.py`
  (`pytestmark = pytest.mark.usefixtures("clock")`, as `tests/test_data_cli.py` does).
- `changes/0005-run-a-backtest-from-the-cli-with-an-sma/plan.md` — this file, whenever the
  build departs from it.

Unchanged: `app/data/` (every module), `app/backtest/inputs.py`, `engine.py`, `summary.py`,
`app/__init__.py` (version `0.1.0`), `pyproject.toml` (its `packages` list already holds
`"app.backtest"`, so the new modules ship), every test file already on `main`
(`tests/test_*.py`, `tests/conftest.py`, `tests/kucoin_stub.py`, `tests/fixtures/`), and
`.github/workflows/ci.yml`. The Setup and Test commands stay as they are: no new dependency
and the same `python -m pytest`.

For the owner, not the run (guardrail file; the owner may land these in a PR of their own
before the build PR, so the deploy review does not flag an outdated `CLAUDE.md`), `CLAUDE.md`:
- Opening paragraph, "with the CLI `python -m app.data download | cache-info | cache-clear`;
  and `app/backtest/`, a long/flat backtest of one symbol on a klines frame." Suggested end:
  "…; and `app/backtest/`, a long/flat backtest of one symbol on a klines frame, with an SMA
  crossover strategy and the CLI `python -m app.backtest run`."
- Architecture, the `app/backtest/` bullet. Suggested text: "`app/backtest/` is the backtest
  engine, one module per job (inputs, engine, summary, strategy, and the CLI in
  `__main__.py`); its public API is `app/backtest/__init__.py` (`run_backtest`,
  `sma_cross_positions`). Only the CLI does I/O, through `app.data.load_klines`; the engine
  and strategy tests, `tests/test_backtest.py` and `tests/test_strategies.py`, use frames
  built by hand, and the CLI tests, `tests/test_backtest_cli.py`, run offline against
  `tests/kucoin_stub.py`."
- The `tests/` bullet: "the data tests run offline against `tests/kucoin_stub.py` …" may add
  "and the backtest CLI tests". Optional.

## Order of work
1. `app/backtest/strategy.py` and `tests/test_strategies.py`.
   - `validate_lengths`: for each of `fast`, `slow`, refuse `type(x) is not int` (refuses
     `bool`, `float`, `str`) or `x < 1` with `BacktestInputError(f"{name} {x!r} is not a
     whole number of at least 1")`; then refuse `fast >= slow` with
     `f"fast {fast} is not below slow {slow}: the fast SMA must be the shorter one"`.
   - `sma_cross_positions`: `validate_lengths(fast, slow)`; refuse a non-DataFrame and a
     frame with no `close` column or a non-numeric one (messages in the style of
     `app/backtest/inputs.py`); then
     `close = frame["close"].cast(pl.Float64)`,
     `above = close.rolling_mean(window_size=fast) > close.rolling_mean(window_size=slow)`,
     return `above.fill_null(False).cast(pl.Int8).alias("position")`. The default
     `min_samples` of `rolling_mean` is the window size, so both means are null until full
     (R3). Do not pass `min_periods` (renamed in polars 1.21; CI pins polars 2.1.0).
   - Hand-computed example for the tests (fast 2, slow 3, integer closes so every sum is
     exact): closes `[1, 2, 3, 2, 1, 1, 3]` give fast SMA `[-, 1.5, 2.5, 2.5, 1.5, 1, 2]`,
     slow SMA `[-, -, 2, 7/3, 2, 4/3, 5/3]` and positions `[0, 0, 1, 1, 0, 0, 1]`. Tie case:
     closes `[2, 2, 2, 2]` with fast 2, slow 3: both means are exactly `2.0` from row 2, so
     the positions are `[0, 0, 0, 0]`. Lookahead case: the example's closes with rows 4 to 6
     replaced by `[9, 9, 9]` keep rows 0 to 3 at `[0, 0, 1, 1]`.
   - Commit with its tests.
2. `app/backtest/__init__.py`: export `sma_cross_positions`; docstring; the public-API test
   in `tests/test_strategies.py`. Commit.
3. `app/backtest/__main__.py` and `tests/test_backtest_cli.py`.
   - Parser: `prog="python -m app.backtest"`, description "Backtest a built-in strategy on
     cached KuCoin klines."; `add_subparsers(required=True, metavar="COMMAND")`; `run` with
     `symbol`, `interval`, `start`, `end` (metavars and help as `download`),
     `--market choices=MARKETS default="spot"`, `--fast default="20"`, `--slow
     default="50"`, `--fee default=str(DEFAULT_FEE)`, `--cache-dir`; an epilog with the SMA
     note.
   - `_run(args, fetch)`: `now = loader.utc_now()`; `request = make_request(args.symbol,
     args.interval, args.start, args.end, args.market, now.date())`; `fast, slow =
     _length(args.fast, "fast"), _length(args.slow, "slow")` (int() of the text; a
     `ValueError` becomes `BacktestInputError(f"{name} {text!r} is not a whole number of at
     least 1")`), `validate_lengths(fast, slow)`; `fee = _fee(args.fee)`: float() of the
     text, else `BacktestInputError("fee ... is not a number: pass a proportional fee, for
     example 0.001")`, then `return _check_fee(value)` with `_check_fee` imported from
     `app.backtest.inputs` as it is (panel #1: the engine's rule and message, checked
     before any download); `frame = load_klines(request.symbol, request.interval,
     request.start, request.end, market=request.market, cache_dir=args.cache_dir,
     fetch=fetch)`; refuse `frame.height <= slow` (panel #2) with
     `BacktestInputError(f"the range has {frame.height} candles, not more than slow {slow}:
     the strategy could never take a position; widen the dates or lower --slow")`;
     `result = run_backtest(frame, sma_cross_positions(frame, fast, slow), fee=fee)`;
     `hold = run_backtest(frame, [1] * frame.height, fee=fee)`; print the eight lines of
     spec R11; return 0.
   - `main`: as `app/data/__main__.py:main`, catching `(InvalidRequestError, KlineGapError,
     DownloadError, BacktestInputError)` → `error: {error}` on stderr, return 2; `OSError` →
     `error: {error}; check the cache directory (--cache-dir)`, return 2. None of the four
     classes is an `OSError`, so the two handlers do not overlap.
   - `_percent(x) = f"{x:.2%}"`; value lines `f"{label:<14}{value:>8}"`; trade count
     `str(summary.trade_count)`.
   - Commit with its tests.
4. Run build, test and lint; paste the output.

## Risks
- **Breaks nothing existing.** No module imports `app.backtest.strategy` or
  `app.backtest.__main__`. The CLI imports `app.data.params` (`MARKETS`, `make_request`),
  `app.data.loader` (`utc_now`) and the public `app.data` (`load_klines`, `KlineGapError`,
  `InvalidRequestError`, `DownloadError`, `Fetch`) as they are; `urllib_fetch` is not
  needed, since `load_klines` uses it when `fetch` is `None`. The only
  edited existing file is `app/backtest/__init__.py` (one import, one `__all__` entry, the
  docstring); `tests/test_backtest.py` imports from the submodules, not from it.
- **Riskiest step: the strategy's warm-up and comparison (step 1).** An off-by-one in the
  window (or `min_samples` lower than the length) would trade on a part-filled average and
  still look plausible. Mitigations: the hand-computed list pins every row, including the
  first `slow − 1`; the lookahead test changes the closes after row `k` and compares rows
  `0..k`.
- **Floating-point ties.** Polars' rolling mean keeps a running float sum; on non-integer
  closes, two mathematically equal means can differ in the last bit and turn a tie into `1`.
  The tie test uses integer closes, whose sums are exact, so it pins the `>` rule; real
  data's ties are measure-zero and either answer is acceptable there. If the build sees the
  tie test fail on exact integers, compare `rolling_sum(fast) * slow > rolling_sum(slow) *
  fast` instead (still exact on integers) and note it here.
- **The clock in CLI tests.** `make_request` refuses an end date after `loader.utc_now()`;
  the tests must use the `clock` fixture (NOW = 2026-10-03 12:00 UTC) and dates up to
  2026-10-02. `_run` must read the clock through `loader.utc_now()` (the module attribute,
  so the fixture's monkeypatch applies), not a `from ... import utc_now` copy.
- **Bad `--market` exits via argparse** (`SystemExit(2)`, usage plus `error: argument
  --market: invalid choice`), as `download` does; its test uses
  `pytest.raises(SystemExit)` and checks the code is 2 and stderr names the choice.
- **The CLI calls a private engine helper** (`inputs._check_fee`, panel #1). It keeps one
  copy of the fee rule and leaves `inputs.py` unchanged, at the cost of a cross-module call
  to a `_` name inside the same package. A later rename of `_check_fee` breaks the CLI at
  import time, which the CLI tests catch. If the owner overturns panel #1 at the gate, the
  fee check moves back to `run_backtest` after loading and the `calls == []` assertion goes.
- **Candle-count rule** (panel #2): `height <= slow`, the intent's stated reason rather
  than its literal "fewer than". If the owner overturns it, one comparison, the message and
  the boundary test change.
- **CLAUDE.md drift.** Until the owner lands the lines above, the deploy review may raise an
  outdated-CLAUDE.md finding (as on change 0003). The run cannot edit that file.
- **No new dependency** (coding-standards rule 5; security-baseline rule 6): polars and the
  standard library only, no numpy import.

## Options not taken
- **A shared argument helper in `app/data/`** (a function that adds `SYMBOL INTERVAL START
  END --market --cache-dir` to a parser). Not taken: six `add_argument` lines are cheaper
  than a refactor of a module the intent wants unchanged, and the checks themselves are
  already shared through `make_request`.
- **Letting `load_klines` do the request checks** (no `make_request` call in the CLI). Not
  taken: the header needs the normalised symbol and parsed dates, and checking the request
  first refuses a bad symbol before the length checks, the order `download` users expect.
- **argparse `type=int` / `type=float` for `--fast`, `--slow`, `--fee`.** Not taken: argparse
  exits with a usage dump through `SystemExit` instead of one `error:` line and `main`
  returning 2, and `0` or `-5` would still need a second check.
- **A range check of `--fee` written in the CLI.** Not taken: it would copy the engine's
  `0 <= fee < 1` rule; calling `_check_fee` keeps one copy (panel #1).
- **Leaving the fee range check to `run_backtest` after loading.** Not taken (panel #1): a
  bad fee would download and cache the range before being refused.
- **The literal `height < slow`.** Not taken (panel #2): a range of exactly `slow` candles
  can never trade, which the intent's own reason refuses.
- **A strategy class or registry.** Not taken: the intent puts a plug-in mechanism out of
  scope; one function is the smallest API.
- **Positions as a Python list.** Not taken: a polars `Int8` Series matches the frame type
  and `run_backtest` accepts it as is.
- **Bumping the version.** Not taken: the intent keeps `0.1.0` and gives no reason to bump.

Interrogation answers:
1. What could break: nothing existing calls the new modules. Touched shapes: the
   `load_klines` frame (read only), `run_backtest`'s inputs (positions as an `Int8` Series),
   and `app/backtest/__init__.py`'s `__all__` (one name added).
2. Riskiest step: the strategy window and comparison (step 1); mitigated in Risks.
3. Other options: listed above.
4. An engineer who never saw this conversation can implement it from spec R11 (exact
   lines), spec Design (order of checks) and step 3's call sequence. Nothing is missing.
5. Every Proof test is still to be written, in the two new files. The existing tests exist
   and must keep passing.

## Proof
- test: test_positions_match_hand_computed_example
- test: test_warm_up_rows_are_flat
- test: test_equal_smas_give_flat
- test: test_positions_ignore_later_closes
- test: test_positions_accepted_by_run_backtest
- test: test_refuses_bad_lengths
- test: test_refuses_frame_without_close
- test: test_public_api_exports_strategy
- test: test_run_prints_summary_and_buy_and_hold
- test: test_run_uses_cache_without_fetching
- test: test_run_refuses_bad_request
- test: test_run_refuses_bad_market
- test: test_run_refuses_bad_lengths
- test: test_run_refuses_bad_fee
- test: test_run_refuses_too_few_candles
- test: test_run_candle_count_boundary
- test: test_run_refuses_missing_day
- test: test_run_reports_download_error
- `test_run_prints_summary_and_buy_and_hold` runs `run BTC-USDT 1h 2026-10-01 2026-10-01
  --fast 3 --slow 5` against the stub with `SPOT_1H` (24 candles), computes the expected
  numbers in the test with `load_klines`, `sma_cross_positions` and `run_backtest` on the
  same stub, and compares the eight stdout lines exactly, exit 0.
- `test_run_uses_cache_without_fetching` runs it once to fill a `tmp_path` cache, then again
  with a stub that holds no rows, and gets the same output.
- The refusal tests are parametrised: bad symbol, interval, dates (future end, start after
  end, not ISO); `--fast 0`, `--fast x`, `--fast 1.5`, `--fast 50 --slow 20`, `--fast 20
  --slow 20`; `--fee abc`, `--fee 1.5`, `--fee -0.1` (each also asserts the stub's
  `calls == []`: nothing fetched, panel #1); too few candles (`--slow 30` on the 24-candle
  day); a missing day (2026-09-30 .. 2026-10-01 with only the 10-01 fixture); a
  download error (a stub `refuse` answering 503 until retries are exhausted, with the
  `sleeps` fixture so nothing waits). Each asserts stderr starts with `error: ` and exit 2
  (bad market: `SystemExit` with code 2).
- `test_run_candle_count_boundary` (panel #2): on the 24-candle day with `--fast 3`,
  `--slow 24` exits 2 with the candle-count message and `--slow 23` exits 0.
- Every CLI test passes `--cache-dir` under `tmp_path`, so no test reads or writes the
  developer's real cache.
- Target (spec Acceptance): hand-computed positions exact; summary values equal to
  `run_backtest`'s within 1e-9 via the exact printed text.
- `python -m compileall -q .` prints nothing. `python -m pytest` reports every test passed.
  `python -m ruff check .` prints `All checks passed!`.
