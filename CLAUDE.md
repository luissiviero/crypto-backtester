# CLAUDE.md

A trial Python project for the SDLC framework plugin: a crypto backtester whose features arrive
as intents (`/sdlc-intent`), one change at a time. Today the package (`app/`) holds one feature,
`app/data/`: Binance spot and USD-M futures klines from Binance Vision (the REST API fills
missing days) as polars frames, cached per day as Parquet outside the repository; its CLI is
`python -m app.data download | cache-info | cache-clear`.

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
- `app/data/` is the market-data layer, one module per job (params, http, vision, rest,
  schema, cache, loader, and the CLI in `__main__.py`); its public API is
  `app/data/__init__.py`. The cache directory is `--cache-dir`, else the environment variable
  `CRYPTO_BACKTESTER_CACHE_DIR`, else the platform default.
- `scripts/measure_storage.py` measured the cache layout for change 0001; it is not part of
  the package.
- `tests/` holds the pytest suite; the data tests run offline against `tests/binance_stub.py`
  and the files in `tests/fixtures/binance/`.
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
