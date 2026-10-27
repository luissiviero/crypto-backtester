# CLAUDE.md

A trial Python project for the SDLC framework plugin: a crypto backtester whose features arrive
as intents (`/sdlc-intent`), one change at a time. Today it is a package skeleton (`app/`) and a
smoke test (`tests/`).

## Commands

- Setup: `python -m pip install pytest ruff` (the project declares no extras; CI pins
  `pytest==9.1.1 ruff==0.16.9`).
- Build: `python -m compileall -q .` (healthy: no output, exit code 0).
- Test: `python -m pytest` (healthy: `1 passed`, exit code 0; `testpaths = ["tests"]`).
- Lint: `python -m ruff check .` (healthy: `All checks passed!`).

## Conventions

- Python >= 3.10, type hints on public functions (the tests use `-> None`).
- Ruff with `line-length = 100` (`pyproject.toml`); keep lint clean.
- One test module per area under `tests/`, named `test_<area>.py`.
- The package version lives in `app/__init__.py` (`__version__`) and in `pyproject.toml`; keep
  the two in step.

## Architecture

- `app/` is the package; new modules go here.
- `tests/` holds the pytest suite.
- `.github/workflows/ci.yml` is the project's own CI (lint then test on push to `main` and on
  pull requests); it is the one workflow the SDLC maintain metric counts.
- `changes/<id>-<slug>/` holds each change's intent, spec, plan and status.
