# Intent: Harden the data layer: redirects, datetime bounds, Windows tzdata
Author: owner (product owner), drafted by Claude from the review of PR #6. Change id: 0002. Entry route: idea.

## Problem
The review of change 0001 (PR #6) left two code nits, and running its tests on the owner's
Windows PC found a third problem. The owner chose to fix them in a separate change, so that PR
#6 did not pay for another round. All three were reproduced on `main` at `b9b28f8`.

1. **Redirects can leave Binance.** `app/data/http.py:78` builds its opener with
   `urllib.request.build_opener`, which keeps the default handlers: `HTTPRedirectHandler`,
   `HTTPHandler`, `FTPHandler`, `FileHandler` and `DataHandler`. A 3xx answer is followed to any
   host, including plain `http://`, where the project's connect and read timeouts do not apply
   because they live in `_HTTPSConnection`. Nothing in the data layer needs this.
2. **A datetime bound crashes.** `parse_date` (`app/data/params.py:78`) returns any `date`
   unchanged, and a `datetime` is a `date`. `make_request` then compares it with a plain `date`,
   so `load_klines(..., start=datetime(2024, 1, 1))` raises
   `TypeError: '>' not supported between instances of 'datetime.datetime' and 'datetime.date'`
   instead of the layer's `InvalidRequestError`.
3. **The suite fails on Windows without `tzdata`.** 4 tests of `tests/test_data.py` fail with
   `ZoneInfoNotFoundError` in a clean venv on Windows with Python 3.13 (4 failed, 65 passed):
   polars turns a UTC timestamp into a Python `datetime` through `zoneinfo`, and Windows has no
   system time zone database. This is not only a test problem: any caller that reads a timestamp
   out of a frame on Windows hits it (`frame["open_time"][0]`, `.to_list()`). CI runs on Ubuntu
   with Python 3.12, so it never saw this.

## Proposed outcome
1. A download only ever talks HTTPS to the URL it asked for. A 3xx is not followed and reaches
   the callers as the status it is, so Vision and REST report it through their existing refusal
   paths (`Vision refused (HTTP 302)`, `REST refused (HTTP 302)`). Other URL schemes are refused.
2. A `datetime` start or end never raises `TypeError`: it gives `InvalidRequestError`, or a
   normalised date if design prefers that (see Open questions).
3. On Windows, following the documented Setup line in a clean venv is enough for the whole suite
   to pass. Nobody installs `tzdata` by hand. `pyproject.toml` declares it for Windows only.

How to check it is done:
- Regression tests for 1 and 2 are in `tests/test_data.py`. They fail on `b9b28f8` and pass with
  the fix. As a fix-type change, the build run commits them first.
- Build, test and lint stay green on CI.
- On Windows, the owner runs this in a clean venv at the deploy gate, because no CI job runs on
  Windows: `python -m pip install -e . pytest ruff`, then `python -m pytest`. All tests pass, and
  `tzdata` came from that install.

## Affected users and systems
- The owner, as the person running downloads and tests on Windows.
- `app/data/http.py`, `app/data/params.py`, `tests/test_data.py`, `pyproject.toml`, `.gitignore`
  (an editable install writes `crypto_backtester.egg-info/`, which would otherwise leave the
  tree dirty).
- The hosts the layer calls, unchanged: `data.binance.vision`, `data-api.binance.vision`,
  `fapi.binance.com`.
- **Guardrail files, for the owner to edit; a run cannot** (see Constraints): the Setup line of
  `CLAUDE.md` (lines 11 to 13) and `commands.setup` in `sdlc.yaml`.

## Constraints
- **Declaring `tzdata` in `pyproject.toml` is not enough on its own, for two reasons found while
  checking this.** Nothing installs from `pyproject.toml` today:
  - the Setup line is `python -m pip install pytest ruff polars`, which never reads it;
  - `python -m pip install -e .` fails today with `Multiple top-level packages discovered in a
    flat-layout: ['app', 'evals', 'changes', 'lessons', 'policies']`, so `pyproject.toml` must
    also name the packages (`[tool.setuptools] packages = ["app", "app.data"]`).
- **So `CLAUDE.md` does need to change, and the owner must do it.** The Setup line and
  `commands.setup` become `python -m pip install -e . pytest ruff` (`CLAUDE.md` says the two are
  the same command). Both are guardrails: a run does not edit them, and plan.md names each line
  for the owner, as `CLAUDE.md` asks ("Things Claude gets wrong").
- **Order matters.** The owner's guardrail PR must merge after the packaging fix reaches `main`.
  The phase jobs run `commands.setup`, and `pip install -e .` fails until that fix is there.
- The CI install step (`.github/workflows/ci.yml`) stays as it is: Ubuntu has a system time zone
  database, and the pinned versions keep CI reproducible.
- Tests never touch the network: the redirect test stubs the handlers and opens no socket.
- Proxy support from the environment (`ProxyHandler`) must keep working.
- No new dependency on non-Windows platforms. No secrets, no personal data.
- Out of scope: a Windows CI job, the `plan.md` nit from PR #6 (history only), and any other
  behaviour of the data layer.

## Open questions
- **Refuse redirects, or allow them inside the three Binance hosts over HTTPS?** Proposed: refuse
  all. It is less code and has no allow-list to keep in step. Not checked against the live hosts:
  if one does redirect, that day fails with a clear refusal instead of downloading. Design should
  say whether that risk needs a live check.
- **Refuse a `datetime`, or normalise it with `.date()`?** Proposed: refuse with
  `InvalidRequestError`. `.date()` silently drops the time of day, and for an aware datetime
  outside UTC it can give the wrong UTC day (`23:00-03:00` is already the next day in UTC). If
  design normalises, aware values must be converted to UTC first.
- **A direct `tzdata` marker, or `polars[timezone]`?** polars 2.1.0 has that extra, with
  `tzdata; platform_system == "Windows"`. Proposed: the direct marker, as the requirement names
  it and it does not depend on the extra existing across `polars>=1.0`.

## Examples/References
- `changes/0002-harden-the-data-layer-redirects-datetime/references/prototype.patch`: a prototype
  of the proposed answers, a reference and not a target. It applies to `b9b28f8`. Checked on
  Windows, Python 3.13, polars 2.1.0:
  - with the patch's tests but without its fix: 19 failed, 69 passed;
  - with the fix, in a clean venv from `python -m pip install -e . pytest ruff`: 88 passed, ruff
    clean, `compileall` silent, `tzdata` installed by that command alone;
  - with the fix but the current Setup line (no `-e .`): the same 4 `ZoneInfoNotFoundError`
    failures, which is why the guardrail line has to change.
  It has not been run on Linux or on Python 3.12.
- PR #6, the review of change 0001: https://github.com/luissiviero/crypto-backtester/pull/6
