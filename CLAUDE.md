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

## Things Claude gets wrong
<!-- One line per recurring mistake; added when a review flags the same finding twice. -->
- (none yet)

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
