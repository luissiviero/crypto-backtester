# Spec: Harden the data layer: redirects, datetime bounds, Windows tzdata
Change id: 0002. Status: proposed. Produced by: sdlc plugin 1.0.51, /sdlc-design prompt v1 (article p.14). Skills: coding-standards, security-baseline, ux-and-brand, data-conventions, definition-of-done (plugin 1.0.51); overrides: none; policy sources: none

## Requirements
Redirects and URL schemes (intent outcome 1):
- R1. `app.data.http.urllib_fetch` never follows a 3xx answer: it returns an `HttpResponse`
  whose `status` is the 3xx code, and opens no second URL.
- R2. A 3xx reaches Vision and REST through their existing refusal paths unchanged:
  `Vision refused (HTTP 3xx)` (`app/data/vision.py:60`) and `REST refused (HTTP 3xx)`
  (`app/data/rest.py:68`). `with_retries` already returns any status below 500 other than 418
  and 429 (`app/data/http.py:114`), so a 3xx is not retried.
- R3. `urllib_fetch` opens only `https://` URLs; `http://`, `ftp://`, `file://`, `data:` and any
  other scheme raise `urllib.error.URLError` ("unknown url type") before any socket opens.
- R4. Every HTTPS connection keeps the existing connect and read timeouts
  (`_HTTPSConnection`, `CONNECT_TIMEOUT`, `READ_TIMEOUT`) and the `MAX_BODY_BYTES` cap.
- R5. A proxy configured in the environment (`https_proxy`, read by `ProxyHandler`) still works
  as it does today with `build_opener` (intent Constraints).

Datetime bounds (intent outcome 2):
- R6. A `datetime` passed as `start` or `end` (naive or aware) to `load_klines` raises
  `InvalidRequestError`, never `TypeError`. The message names the bound and says what to pass
  instead (a `date` or `YYYY-MM-DD`; ux-and-brand rule 4).
- R7. The refusal lives in `parse_date`, so every caller gets it: `make_request` (and through
  it `load_klines` and the `download` CLI) and `clear_cache` (`app/data/cache.py:146`), which
  today has the same `TypeError` when it compares a `datetime` with a cached day's `date`.
- R8. A plain `date` and a `YYYY-MM-DD` string behave exactly as today.

Windows time zones (intent outcome 3):
- R9. `pyproject.toml` declares `tzdata` as a dependency on Windows only (environment marker);
  on Linux and macOS the dependency set is unchanged (`polars>=1.0`).
- R10. `python -m pip install -e . pytest ruff` succeeds from a clean venv: `pyproject.toml`
  names the packages (`app`, `app.data`) so setuptools' flat-layout discovery no longer refuses
  the repository.
- R11. The editable install's `*.egg-info/` directory is ignored by git (`.gitignore`), so the
  tree stays clean after the install.
- R12. The guardrail lines that go out of date are named in `plan.md` for the owner, who edits
  them in a PR merged after this change reaches `main` (intent Constraints; `CLAUDE.md`
  "Things Claude gets wrong"): the Setup line of `CLAUDE.md`, `commands.setup` in `sdlc.yaml`,
  and `CLAUDE.md`'s "the one runtime dependency is `polars>=1.0`". The run edits none of them.
- R13. `.github/workflows/ci.yml` is not changed (intent Constraints).

Policies:
- coding-standards: applies. Rule 1 (`CLAUDE.md` conventions: type hints, ruff line length 100,
  tests in `tests/test_data.py`); rule 2 (match `http.py`'s module-level constants and comment
  density); rule 4 (each behaviour change ships with a test that fails on `main`; as a
  fix-type change, the tests come first and are then locked); rule 5 (`tzdata` is a new
  dependency, Windows only, so `plan.md` Risks carries its line and the owner's merge accepts
  it; no pinned version changes); rule 8 (lint clean).
- security-baseline: applies. Rule 2 (bounded input: the transport refuses URLs it was not
  built for); rule 6 (the new dependency has its Risks line; TLS verification is untouched:
  `_HTTPSHandler` keeps the default SSL context); rule 7 (tests open no socket; no live call
  is made by a run). Rules 1, 3, 4 and 5 do not apply: no endpoint, no secret, no personal
  data, no state-changing action with an audit log.
- ux-and-brand: applies to the one new message (rule 4: what happened, what to do). No screen
  is touched; rules 1–3 and 5–7 do not apply.
- data-conventions: does not apply: no stored field, schema, migration, event or personal
  data changes; the cache layout of change 0001 is untouched.
- definition-of-done: applies as the measure of the design, build and test phases (spec,
  plan, green build/test/lint, verifier report, the owner's Windows check at deploy).
- Risk list (`sdlc.yaml`): none of `auth`, `data migrations`, `money movement`,
  `production config` is touched; `deploy.action` is `none`, so the packaging change is not
  production config.

## Design
- **Transport (`app/data/http.py`).** `_OPENER` stops using `urllib.request.build_opener`,
  which adds the default `HTTPHandler`, `FTPHandler`, `FileHandler`, `DataHandler` and
  `HTTPRedirectHandler`. It becomes an `OpenerDirector` assembled from exactly:
  `ProxyHandler` (environment proxies, as today), `UnknownHandler` (refuses any scheme
  without a handler), `_HTTPSHandler` (the existing timeouts), `HTTPDefaultErrorHandler` and
  `HTTPErrorProcessor` (a non-2xx status becomes `HTTPError`). With no redirect handler, a
  3xx goes from `HTTPErrorProcessor` to `HTTPDefaultErrorHandler`, raises `HTTPError`, and
  `urllib_fetch`'s existing `except urllib.error.HTTPError` turns it into an `HttpResponse`
  with that status. A short comment says why the opener is assembled by hand.
  `urllib_fetch`'s signature, `Fetch`, `HttpResponse`, `with_retries` and `WeightPacer` are
  unchanged. An unknown scheme raises `URLError`, an `OSError`, which `with_retries` treats
  as transient and retries; the layer only builds `https://` URLs (`VISION_BASE`, the REST
  endpoints), so that path is reached only by a direct call of `urllib_fetch`.
- **Dates (`app/data/params.py`).** `parse_date` checks `isinstance(value, datetime)` before
  its `isinstance(value, date)` branch and raises `InvalidRequestError`
  (`invalid start date datetime.datetime(...): pass a date or YYYY-MM-DD, not a datetime`).
  No normalisation (see Open questions). `make_request`, `KlineRequest` and `clear_cache`
  are unchanged; they inherit the refusal.
- **Packaging (`pyproject.toml`, `.gitignore`).** `dependencies` becomes
  `["polars>=1.0", "tzdata; sys_platform == 'win32'"]` (`sys_platform == 'win32'` and
  `platform_system == 'Windows'` select the same interpreters). A `[tool.setuptools]` table
  with `packages = ["app", "app.data"]` makes the editable install build. No
  `[build-system]` table is added: without one pip uses setuptools' default backend in an
  isolated build, which reads `[tool.setuptools]`; the intent's prototype proved this on
  Windows. `.gitignore` gains `*.egg-info/`. The package version stays `0.1.0` in both
  places (see Flagged concerns).
- **Unchanged:** the URLs and hosts called, the cache, the schema, the CLI's commands and
  output, the public API in `app/data/__init__.py`, CI.

## Open questions from intent
- "Refuse redirects, or allow them inside the three Binance hosts over HTTPS? ... Design should
  say whether that risk needs a live check." Answered: refuse all, as proposed (less code, no
  allow-list to keep in step with the hosts in `vision.py` and `rest.py`). No live check is
  needed before the build, and a run may not make one (security-baseline rule 7; the tests are
  offline by the intent's Constraints). The layer requests direct object URLs on
  `data.binance.vision` and API paths on `data-api.binance.vision` and `fapi.binance.com`
  (`app/data/vision.py`, `app/data/rest.py`); if a host ever redirects, the day fails with
  `Vision refused (HTTP 3xx)` or `REST refused (HTTP 3xx)` in the gap report, which is visible
  and recoverable. The owner may add one real `python -m app.data download` to the Windows
  check at the deploy gate; it is not required for acceptance.
- "Refuse a `datetime`, or normalise it with `.date()`?" Answered: refuse with
  `InvalidRequestError`, as proposed. `.date()` drops the time of day and, for an aware value
  outside UTC, can name the wrong UTC day; the layer's days are UTC days
  (`app/data/params.py: day_start_ms`), and refusing keeps the caller's intent explicit.
- "A direct `tzdata` marker, or `polars[timezone]`?" Answered: the direct marker, as proposed.
  It names the actual requirement and does not depend on the extra existing across the whole
  `polars>=1.0` range that `pyproject.toml` allows.

## Flagged concerns
- Package version: the intent is silent on a version bump. `CLAUDE.md` asks only that
  `app/__init__.py` and `pyproject.toml` stay in step, and `sdlc.yaml: deploy.action` is
  `none`, so nothing is published. The design keeps `0.1.0`; a bump to `0.1.1` in both places
  is the alternative if the owner wants each change versioned.

## Acceptance
- Regression tests in `tests/test_data.py`, committed first, fail on `main` and pass with the
  fix:
  - a 301, 302, 303, 307 and 308 answer (to an `http://` and an `https://` target) is returned
    as that status and only the original URL is opened;
  - `http://`, `ftp://` and `file://` URLs raise `URLError` "unknown url type", opening no
    socket;
  - a naive and an aware `datetime` as start, end or both raise `InvalidRequestError` from
    `make_request`, and a `datetime` start or end raises it from `clear_cache`.
- Every existing test still passes; none is skipped, weakened or deleted.
- `python -m compileall -q .` silent with exit 0; `python -m pytest` all passed;
  `python -m ruff check .` "All checks passed!", on CI (Ubuntu, Python 3.12).
- `python -m pip install -e .` succeeds and `git status` stays clean afterwards (Linux, in the
  build or test run's own environment where it can run it).
- At the deploy gate the owner runs, on Windows in a clean venv,
  `python -m pip install -e . pytest ruff` then `python -m pytest`: every test passes and
  `tzdata` was installed by that command.
