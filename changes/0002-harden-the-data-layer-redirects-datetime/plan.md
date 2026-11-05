# Plan: Harden the data layer: redirects, datetime bounds, Windows tzdata (from intent.md 2026-11-03, spec.md 2026-11-05)

## Files that change
- `tests/test_data.py` — new regression tests for redirects, URL schemes and datetime bounds
  (plus the imports they need: `email.message`, `io`, `urllib.error`, `urllib.request`,
  `urllib.response`); no existing test changes.
- `app/data/http.py` — `_OPENER` assembled by hand as an `OpenerDirector` with `ProxyHandler`,
  `UnknownHandler`, `_HTTPSHandler`, `HTTPDefaultErrorHandler`, `HTTPErrorProcessor`; one
  comment saying why.
- `app/data/params.py` — `parse_date` refuses a `datetime` with `InvalidRequestError`; import
  `datetime`.
- `pyproject.toml` — `tzdata; sys_platform == 'win32'` in `dependencies`; new
  `[tool.setuptools]` table with `packages = ["app", "app.data"]`.
- `.gitignore` — `*.egg-info/`.
- `changes/0002-harden-the-data-layer-redirects-datetime/plan.md` — this file, if the build
  departs from it.

For the owner, not the run (guardrail files; edit in a PR merged **after** this change reaches
`main`, because the phase jobs run `commands.setup` and `pip install -e .` fails before the
`[tool.setuptools]` table exists):
- `CLAUDE.md` line 11–13 (Commands, Setup): `python -m pip install pytest ruff polars` becomes
  `python -m pip install -e . pytest ruff`, and "the one runtime dependency is `polars>=1.0`"
  becomes "the runtime dependencies are `polars>=1.0` and, on Windows only, `tzdata`".
- `sdlc.yaml` `commands.setup` (line 62): `"python -m pip install pytest ruff polars"` becomes
  `"python -m pip install -e . pytest ruff"`.
- `.github/workflows/ci.yml` stays as it is (intent Constraints).

## Order of work
1. Write the reproducing tests in `tests/test_data.py` and see them fail on the current code
   (fix-type change: this commit comes first and locks the test files):
   - `test_redirect_is_not_followed`, parametrized over status 301, 302, 303, 307, 308 and
     target `http://elsewhere.example/x`, `https://elsewhere.example/x`: monkeypatch
     `http._HTTPSHandler.https_open` and `urllib.request.HTTPHandler.http_open` with a stub that
     records `request.full_url` and returns a `urllib.response.addinfourl` with the status, a
     `Location` header and `msg` set; assert `http.urllib_fetch(origin).status == status` and
     that only `origin` (`https://data.binance.vision/data/x.zip`) was opened. On `main` it
     fails (the redirect is followed and returns the stub's second answer).
   - `test_only_https_urls_are_opened`, parametrized over `http://127.0.0.1:9/x`,
     `ftp://127.0.0.1/x`, `file:///etc/hosts`: `pytest.raises(urllib.error.URLError,
     match="unknown url type")`. On `main` the `http`/`ftp` cases fail with a connection error
     and `file` reads the file; port 9 on loopback and ftp to loopback open no external
     connection.
   - `test_datetime_bound_is_refused_not_a_type_error`, parametrized over a naive
     `datetime(2024, 1, 1)` and an aware `datetime(2024, 1, 1, 23, tzinfo=timezone(timedelta(hours=-3)))`,
     each as start, end and both: `pytest.raises(InvalidRequestError, match="not a datetime")`
     from `make_request("BTCUSDT", "1h", start, end, "spot", date(2025, 1, 1))`. Type the
     parameters (`moment: datetime`, `dates: Callable[...]`) per `CLAUDE.md`.
   - `test_clear_cache_refuses_a_datetime_bound`, `tmp_path`: `cache.clear_cache("BTCUSDT",
     start=datetime(2024, 1, 1), cache_dir=tmp_path)` and the same with `end=` raise
     `InvalidRequestError` matching "not a datetime". (On `main` this passes for an empty
     cache, because no day is compared; write one day file first with the stub's
     `cached_days(tmp_path, "spot", "BTCUSDT", "1h", ["2024-01-01"])`, as
     `test_cache_info_and_clear_touch_only_day_files` does, so it fails with `TypeError` on
     `main`; assert the day file is still there afterwards.)
   Run `python -m pytest` and record the failures.
2. Fix `app/data/params.py`: in `parse_date`, before the `isinstance(value, date)` branch,
   `if isinstance(value, datetime): raise InvalidRequestError(f"invalid {name} date {value!r}:
   pass a date or YYYY-MM-DD, not a datetime")`, with a one-line comment (a datetime is a date,
   but its time and zone do not say which UTC day is meant). The datetime tests pass.
3. Fix `app/data/http.py`: replace `_OPENER = urllib.request.build_opener(_HTTPSHandler())`
   with an `urllib.request.OpenerDirector()` and `add_handler` for each of `ProxyHandler()`,
   `UnknownHandler()`, `_HTTPSHandler()`, `HTTPDefaultErrorHandler()`, `HTTPErrorProcessor()`;
   a two-line comment that `build_opener` would add the HTTP, FTP, file, data and redirect
   handlers, and that without them a 3xx returns as its status and other schemes are refused.
   The redirect and scheme tests pass.
4. Packaging: `pyproject.toml` `dependencies = ["polars>=1.0", "tzdata; sys_platform ==
   'win32'"]` and `[tool.setuptools]` `packages = ["app", "app.data"]` after `[project]`;
   `.gitignore` adds `*.egg-info/`. Where the environment allows, run
   `python -m pip install -e .` and confirm it succeeds and `git status` is clean.
5. Run build, test and lint (`python -m compileall -q .`, `python -m pytest`,
   `python -m ruff check .`) and paste the output.

## Risks
- **Riskiest step: the hand-built opener (step 3).** Leaving out a handler `build_opener`
  added silently changes behaviour. Checked against what the layer needs: `ProxyHandler`
  keeps environment proxies (intent Constraints; an `https` proxy tunnels through
  `_HTTPSConnection`, so the timeouts still apply); `HTTPErrorProcessor` +
  `HTTPDefaultErrorHandler` keep "an error status becomes `HTTPError`", which `urllib_fetch`
  already converts to a response (418, 429, 404, 5xx paths unchanged and covered by the
  existing `with_retries`, Vision and REST tests). Not added on purpose: `HTTPRedirectHandler`,
  `HTTPHandler`, `FTPHandler`, `FileHandler`, `DataHandler`. Cookie and auth handlers were never
  in the default opener.
- **A Binance host that redirects** would now fail that day with `Vision refused (HTTP 3xx)` /
  `REST refused (HTTP 3xx)` in the gap report instead of downloading. Not checked live (a run
  may not; security-baseline rule 7). Mitigation: the refusal is explicit; the owner may run one
  real download at the deploy gate.
- **`URLError` for a non-https URL is an `OSError`**, so `with_retries` would retry it three
  times with backoff. The layer only builds `https://` URLs, so this is reached only by a
  direct call; left as is to keep the change to the intent's scope.
- **New dependency (coding-standards rule 5, security-baseline rule 6):** `tzdata`, Windows
  only, unpinned, the IANA database the Python docs name for `zoneinfo` on systems without one.
  No change on Linux/macOS or in CI. The owner's merge accepts it.
- **Packaging:** no `[build-system]` table, so pip uses setuptools' default backend in an
  isolated build (current setuptools, which supports `[tool.setuptools]` and PEP 660
  editable installs). Proven on Windows by the intent's prototype; not yet run on Linux or
  Python 3.12 — the build run checks `pip install -e .` where its sandbox allows.
- **Guardrail order:** if the owner changes `commands.setup` before this change is on `main`,
  every phase job's setup fails. Named above for the owner.
- **Test lock:** after step 1 the test files are locked; every test this change needs is in
  step 1, including the `clear_cache` one.
- Callers touched: `make_request` (`load_klines`, the `download` CLI), `clear_cache` (the
  `cache-clear` CLI passes strings, unaffected), `urllib_fetch` (`load_klines` default fetch,
  the CLI). Data shapes, cache layout, public API: unchanged.

## Options not taken
- **Allow redirects within the three Binance hosts over HTTPS:** an allow-list to keep in step
  with `vision.py`/`rest.py` and a custom redirect handler; more code for a case never seen.
- **Normalise a `datetime` with `.date()` (UTC-converting aware values):** silently drops the
  time and invites wrong-day surprises; the intent proposed refusal.
- **`polars[timezone]` extra instead of the direct `tzdata` marker:** depends on the extra
  existing across `polars>=1.0`.
- **Keep `build_opener` and only pass a redirect handler that refuses:** still leaves
  `HTTPHandler`, `FTPHandler`, `FileHandler`, `DataHandler` in place, so plain `http://` without
  the project's timeouts remains reachable.
- **Add a `[build-system]` table:** not needed for the install (prototype proved it); a
  separate packaging decision.
- **Bump the version to 0.1.1:** see spec.md Flagged concerns; kept at 0.1.0.
- **A Windows CI job:** out of scope (intent).

## Proof
- test: test_redirect_is_not_followed
- test: test_only_https_urls_are_opened
- test: test_datetime_bound_is_refused_not_a_type_error
- test: test_clear_cache_refuses_a_datetime_bound
- All four are still to be written (step 1); they fail on `main` and pass after steps 2–3.
  Every existing test in `tests/` keeps passing.
- `python -m compileall -q .` silent, exit 0; `python -m pytest` all passed;
  `python -m ruff check .` "All checks passed!".
- Deploy gate, by the owner on Windows in a clean venv: `python -m pip install -e . pytest ruff`
  then `python -m pytest`, all passed, `tzdata` installed by that command.

Interrogation (plan-template):
1. Breaks: `urllib_fetch` callers (loader, CLI), `parse_date` callers (`make_request`,
   `clear_cache`); folded into Risks.
2. Riskiest: the hand-built opener; Risks.
3. Options: Options not taken.
4. Implementable cold: yes — each step names the function, the exact handler list, the
   message text and the test parameters.
5. Proof items: all four tests are to be written in step 1; none exists yet.
