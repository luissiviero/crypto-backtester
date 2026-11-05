# Verifier report: change 0002, test phase (CI session, `SDLC_GATE_COMMANDS=runner`)

## Commands run

**Read, not run:** `evidence/gate-build.json`, the runner's run on commit `fa325a51ab068de9f3213002aaf77a51e19dec05` of `2026-11-05T18:06:56Z`. That is the tree this phase started from, not the final one. The final tree's result comes from the runner, which runs the three targets once after this session and shows them in the check run `sdlc/test` (and in `gate-test.json`). Nothing here stands in for that.

Between `fa325a5` and HEAD `71ebd8f`, only files under `changes/0002-…/evidence/` and `status.yaml` changed. No code, test or packaging file changed.

The record's `commands` check is `"ok": true`, `"reason": "build, test and lint exit 0"`, `"ran_by": "runner"`, with no `deferred` flag. Its `evidence` check is `ok: true` with no `deferred` flag either.
- `python -m compileall -q .`: exit 0, output `""`.
- `python -m pytest`: exit 0, tail:
  ```
  collected 89 items
  tests/test_data.py ..................................................... [ 59%]
  ..........................                                               [ 88%]
  tests/test_data_cli.py .........                                         [ 98%]
  tests/test_smoke.py .                                                    [100%]
  ============================== 89 passed in 0.57s ==============================
  ```
- `python -m ruff check .`: exit 0, `All checks passed!`

**Logs (read, not run), first lines:**
- `test.log`: `# python -m pytest — deferred to the runner — 2026-11-05T18:08:29Z`
- `build.log`: `# python -m compileall -q . — deferred to the runner — 2026-11-05T18:08:29Z`
- `lint.log`: `# python -m ruff check . — deferred to the runner — 2026-11-05T18:08:29Z`

These are this session's deferred placeholders, which the runner replaces. They are not failures.

**Earlier failing run:** `evidence/failing-test.log` shows the new tests run on `071cd24` (main) with `app/` unchanged: `20 failed, 59 deselected in 0.21s`. All 10 redirect cases failed (the redirect was followed). The 3 scheme cases failed: http and ftp with a regex mismatch, and file with `DID NOT RAISE URLError`. All 6 datetime cases and the `clear_cache` case failed with `TypeError: can't compare datetime.datetime to datetime.date`.

## Behavior exercised
I made direct calls with `python -B -c` from the project root. I did not use pytest and read no `.env*`.

**Redirects:**
- I stubbed `http._HTTPSHandler.https_open` to answer each status with `Location: https://elsewhere.example/x`. For 301, 302, 303, 307 and 308, `urllib_fetch("https://data.binance.vision/data/x.zip")` returned that same status, and the stub recorded exactly `['https://data.binance.vision/data/x.zip']`.
- Neighbouring statuses come back unchanged too: 200, 404, 418, 429 and 500 each return their own status with the body intact.
- **Vision refusal path:** `vision.fetch_day(with_retries(urllib_fetch), req, 2024-01-01)` with a 302 returned `VisionDay(..., frame=None, reason='Vision refused (HTTP 302)')` and opened one URL, so there was no retry (R1, R2).

**Schemes (R3):** every non-https URL raised `URLError <urlopen error unknown url type: …>`:
- `http://127.0.0.1:9/x` (type `http`)
- `ftp://127.0.0.1/x` (type `ftp`)
- `file:///etc/hosts` (type `file`)
- `data:,hello` (type `data`)
- Just outside the spec's list: `HTTP://127.0.0.1:9/x` (type `http`) and `gopher://x/` (type `gopher`)

This held even though the sandbox sets `http_proxy` and `ftp_proxy`.

**Opener structure (R4, R5):**
- `_OPENER.handle_open["https"]` is `['ProxyHandler', '_HTTPSHandler']`, and no `HTTPRedirectHandler` is present.
- `CONNECT_TIMEOUT 10.0`, `READ_TIMEOUT 60.0` and `MAX_BODY_BYTES 67108864` are unchanged.
- `ProxyHandler()` with `https_proxy` set picks up the https proxy and has `https_open`.

**Dates (R6–R8):**
- `parse_date` raises `InvalidRequestError` for a naive `datetime(2024,1,1)` and for an aware `datetime(2024,1,1,23,tz=-3h)`, with the message `invalid start date datetime.datetime(2024, 1, 1, 0, 0): pass a date or YYYY-MM-DD, not a datetime`.
- `date(2024,1,1)` and `"2024-01-01"` both return `2024-01-01`.
- Just outside: `"2024-01-01T00:00"` and `"2024-13-01"` raise the existing `use YYYY-MM-DD, for example 2024-01-31`.
- `make_request` with a datetime as start, as end, or as both raises `InvalidRequestError`, and the message names the right bound (`start`, or `end` when only the end is a datetime).
- `clear_cache(start=datetime)` and `clear_cache(end=aware)` raise `InvalidRequestError`. `clear_cache(start="2024-01-01", end=date(2024,1,2))` returns `ClearResult(files=0, size=0)`.
- `load_klines("BTCUSDT","1h",datetime(2024,1,1),date(2024,1,2), fetch=<raises if called>)` raises `InvalidRequestError` before any fetch.

**Packaging (R9–R11):**
- `pyproject.toml` has dependencies `['polars>=1.0', "tzdata; sys_platform == 'win32'"]` and `[tool.setuptools] packages = ['app', 'app.data']`. The version is `0.1.0`, and `app.__version__` is also `0.1.0`.
- The marker evaluates to True on `win32` and False on `linux` and `darwin`.
- `python -m pip wheel --no-deps --no-build-isolation -w $TMPDIR/whl .` exited 0. The wheel holds only `app/` and `app/data/*.py`, and its METADATA reads `Requires-Dist: polars >=1.0` and `Requires-Dist: tzdata ; sys_platform == "win32"`.
- `crypto_backtester.egg-info/` shows as ignored (`!!`).
- The wheel build left an untracked `build/` directory (setuptools output: copies of `app/`, nothing else). The test session removed it before committing. `.gitignore` does not ignore `build/`, so a local non-editable build dirties `git status`; this is outside the change's scope (R11 covers egg-info only), so it is noted here and not acted on.

**Guardrail files (R12, R13):** `git diff 071cd24..HEAD -- .github CLAUDE.md sdlc.yaml` is empty. plan.md lines 18–26 name the owner's edits to `CLAUDE.md` and `sdlc.yaml`.

**Proof items in plan.md:** all four named tests exist in `tests/test_data.py` on HEAD, and none of them is skipped:
- `test_redirect_is_not_followed`, with 10 parameter sets
- `test_only_https_urls_are_opened`, with 3
- `test_datetime_bound_is_refused_not_a_type_error`, with 6
- `test_clear_cache_refuses_a_datetime_bound`

The tests were committed first, in `ff61d01 fix(0002): reproducing test`. The `test_lock` check in `gate-build.json` passed with lock commit `047eba1565`. The diff from `071cd24` to HEAD only adds to `tests/test_data.py`; no existing test changed.

## Not exercised
- The test runner and the three targets on the final tree. The runner judges these in `sdlc/test`.
- A real `python -m pip install -e .` into an environment. I built a wheel instead and did not install anything, so "git status stays clean after the editable install" is only partly checked: egg-info is ignored, but I did not run an editable install.
- Windows: the `tzdata` install and `python -m pytest` there. That is the owner's check at the deploy gate.
- macOS.
- A real HTTPS connection through an actual proxy (R5). I checked handler order and that the https proxy is picked up, nothing more.
- A real network redirect from any Binance host. Every redirect answer was stubbed.
- The REST refusal path (`REST refused (HTTP 3xx)`, `app/data/rest.py:68`). I read the code but did not call it.
- The `download`, `cache-clear` and `cache-info` CLI commands.
- Python versions other than the sandbox interpreter.

## UI / screenshots
No UI step: neither spec.md Acceptance nor plan.md Proof names a mock, screen or screenshot.

## Mismatches with plan.md / spec.md
None.

## Verdict
matches the plan
