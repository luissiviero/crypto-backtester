# CLAUDE.md

A trial Python project for the SDLC framework plugin: a crypto backtester whose features arrive
as intents (`/sdlc-intent`), one change at a time. Today the package (`app/`) holds two features:
`app/data/`, KuCoin spot and USDT-margined perpetual klines from KuCoin's public REST API
as polars frames, cached per day as Parquet outside the repository, with the CLI
`python -m app.data download | cache-info | cache-clear`; and `app/backtest/`, a long/flat
backtest of one symbol on a klines frame, with an SMA crossover strategy and the CLI
`python -m app.backtest run | sweep`.

## Commands

- Setup: `python -m pip install -e . pytest ruff==0.16.9` (the same as `commands.setup` in
  `sdlc.yaml`; the runtime dependencies are `polars>=1.0` and, on Windows only, `tzdata` in `pyproject.toml`; CI pins
  `pytest==9.1.1 ruff==0.16.9 polars==2.1.0`).
- Build: `python -m compileall -q .` (healthy: no output, exit code 0).
- Test: `python -m pytest` (healthy: every test passes, `N passed`, exit code 0;
  `testpaths = ["tests"]`).
- Lint: `python -m ruff check .` (healthy: `All checks passed!`).

## Conventions

- Python >= 3.10, type hints on public functions (the tests use `-> None`).
- Ruff with `line-length = 100` (`pyproject.toml`); keep lint clean.
- One test module per area under `tests/`, named `test_<area>.py`.
- The package version lives in `app/__init__.py` (`__version__`) and in `pyproject.toml`; keep
  the two in step.

## Architecture

- `app/` is the package; new modules go here.
- `app/data/` is the market-data layer, one module per job (params, http, rest,
  schema, cache, loader, and the CLI in `__main__.py`); its public API is
  `app/data/__init__.py`. The cache directory is `--cache-dir`, else the environment variable
  `CRYPTO_BACKTESTER_CACHE_DIR`, else the platform default.
- `app/backtest/` is the backtest engine, one module per job (inputs, engine, summary,
  strategy, sweep, and the CLI in `__main__.py`); its public API is `app/backtest/__init__.py`
  (`run_backtest`, `sma_cross_positions`). Only the CLI does I/O, through
  `app.data.load_klines`; the engine and strategy tests, `tests/test_backtest.py` and
  `tests/test_strategies.py`, use frames built by hand, and the CLI tests,
  `tests/test_backtest_cli.py` and `tests/test_backtest_sweep.py`, run offline against
  `tests/kucoin_stub.py`.
- `scripts/measure_storage.py` measured the cache layout for change 0001; it is not part of
  the package.
- `tests/` holds the pytest suite; the data tests and the backtest CLI tests run offline
  against `tests/kucoin_stub.py` and the files in `tests/fixtures/kucoin/`.
- `.github/workflows/ci.yml` is the project's own CI (lint then test on push to `main` and on
  pull requests); it is the one workflow the SDLC maintain metric counts.
- `changes/<id>-<slug>/` holds each change's intent, spec, plan and status.

## Things Claude gets wrong
<!-- One line per recurring mistake; added when a review flags the same finding twice. -->
- A change that adds a runtime dependency or tests leaves the Setup and Test lines above and
  the install step of `.github/workflows/ci.yml` outdated; a run can edit neither, so plan.md
  names each line for the owner (change 0001).

## SDLC framework
- Every change lives in `changes/<id>-<slug>/` (intent.md → spec.md + plan.md → evidence/);
  phase branches are `sdlc/<id>/<phase>`; see `changes/README.md`.
- Never edit `.claude/**`, `CLAUDE.md`, `REVIEW.md`, `sdlc.yaml` or `policies/**` in a run:
  they are guardrails the owner changes in a reviewed PR. Never use bypass-permissions mode.
- When a run cannot finish, park: write "what I need from you"; the runner requests the
  owner's review on the waiting PR, and nothing else notifies.

## Verifying your work
<!-- Verbatim structure of the article's verification block (p.28). -->
- Build: `python -m compileall -q .` (must finish with no output and exit code 0)
- Test: `python -m pytest` (all green; never skip or delete a failing test)
- Lint: `python -m ruff check .` (zero warnings)
Run all three before reporting any task complete, and paste the output.
If a test fails, fix the code, not the test.
