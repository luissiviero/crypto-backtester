# Verifier report: change 0002, build phase (branch `sdlc/0002/build`)

The build matches the plan. Every behaviour I called did what plan.md and spec.md describe, and the code diff touches exactly the files the plan lists.

## Commands run
`SDLC_GATE_COMMANDS=runner` is set, so this is a CI session. I did not run the build, test or lint targets, and I did not start pytest either, even though you offered it: inside the sandbox pytest fails on nested `.env*` files, and the test suite is the runner's job.

I read `evidence/gate-design.json`, the runner's run on commit `690c2125da360da8a5e73aa461a10e7333b7daa9` of 2026-11-05T15:08:09Z. That is the tree this phase started from, not the final one. The final tree's result comes from the runner, which runs the three targets once after this session and shows them in the check run `sdlc/test` (and in `gate-build.json`). A red target there starts the next fix round by itself, and nothing here stands in for it.

`commands` entry (read, not run): `"ok": true`, `"reason": "build, test and lint exit 0"`, `"ran_by": "runner"`, no `deferred` flag.
- `python -m compileall -q .`: exit 0, output `""`
- `python -m pytest`: exit 0, last line `============================== 69 passed in 0.60s ==============================`
- `python -m ruff check .`: exit 0, output `All checks passed!`

`gate-design.json` has no `evidence` check, and `evidence/test.log`, `build.log` and `lint.log` do not exist yet, so there are no log first lines to quote.

## Behavior exercised
All calls were direct `python -` scripts run from the repo root, with no network.

**1. Redirects (R1, R3, R5)**
- I stubbed `http._HTTPSHandler.https_open` and `urllib.request.HTTPHandler.http_open` the way `test_redirect_is_not_followed` does. For each of 301, 302, 303, 307 and 308, with both `http://` and `https://elsewhere.example/x` as the target, `urllib_fetch` returned that status, for example:
  `301 http://elsewhere.example/x -> status 301 Location http://elsewhere.example/x opened ['https://data.binance.vision/data/x.zip']`
  In every case only the original URL was opened.
- A stubbed 200 still comes back normally: `200 -> 200 b'hello'`.

**2. Other URL schemes**
I first replaced `socket.socket.connect` with a function that raises.
- `http://127.0.0.1:9/x` gave `URLError: unknown url type: http`.
- `ftp://`, `file:///etc/hosts`, `data:text/plain,hi`, and (outside the spec's list) `gopher://` and upper-case `HTTP://` all gave the same error with their own scheme.
- Result: `socket connects attempted: []`.

**3. Opener handlers**
`['ProxyHandler', 'UnknownHandler', '_HTTPSHandler', 'HTTPDefaultErrorHandler', 'HTTPErrorProcessor']`, nothing else. `handle_open` also lists `http`, `ftp`, `grpc` and `rsync`. Those are the proxy entries `ProxyHandler` registers from this runner's environment proxies; `http://` is still refused, as above.

**4. Proxy (no connection made)**
With `https_proxy=http://proxy.invalid:3128` set:
- `ProxyHandler.proxies['https'] = http://proxy.invalid:3128`
- The request reached `_HTTPSHandler` as `type 'https', host 'proxy.invalid:3128', tunnel 'data.binance.vision'`. So the tunnel goes through `_HTTPSHandler`, which still uses `_HTTPSConnection` and keeps its timeouts.

**5. Datetime bounds (R6–R8)**
- `make_request` with a naive or an aware datetime, as start, end or both (6 cases), raised `InvalidRequestError` every time, for example:
  `invalid start date datetime.datetime(2024, 1, 1, 0, 0): pass a date or YYYY-MM-DD, not a datetime`
- `load_klines` with a datetime raised the same error, and the fetch was never called.
- `clear_cache(start=naive)` and `clear_cache(end=aware)` raised the same error naming `start` and `end` respectively.
- A plain `date` and a `'YYYY-MM-DD'` string both still give `KlineRequest(... start=datetime.date(2024, 1, 1), end=datetime.date(2024, 1, 2))`. `clear_cache` with a date and a string bound gives `ClearResult(files=0, size=0)`.
- Just outside the accepted inputs: `'2024-1-1'` and `'2024-01-01T00:00'` give `invalid start date '...': use YYYY-MM-DD, for example 2024-01-31`, the same message as before.

**6. Packaging (R9, R11, R13)**
- `dependencies = ["polars>=1.0", "tzdata; sys_platform == 'win32'"]`. Evaluating the marker gives True for win32 and False for linux and darwin.
- `[tool.setuptools] packages = ['app', 'app.data']`.
- `git check-ignore -v crypto_backtester.egg-info/PKG-INFO` gives `.gitignore:5:*.egg-info/`.
- `git diff --stat main...HEAD -- .github CLAUDE.md sdlc.yaml` is empty.

**7. Neighbour: the cache CLI**
I ran it against a temp `--cache-dir` seeded with three days via `binance_stub.cached_days`:
- `cache-info`: exit 0, `spot BTCUSDT 1h 3 300 B`
- `cache-clear BTCUSDT 1h --start 2024-01-02 --end 2024-01-02`: exit 0, `Deleted 1 day file (100 B)`, and the 01 and 03 files are left
- `--start 2024-01-01T00:00`: exit 2, `error: invalid start date '2024-01-01T00:00': use YYYY-MM-DD, ...`
- `cache-clear BTCUSDT`: `Deleted 2 day files (200 B)`
- `cache-info`: `No cached klines under ...`

**8. Neighbour: errors through `urllib_fetch` and `with_retries`**
Stubbed answers went through the real opener, with sleep and jitter patched out:
- 404: returned 404, 1 call, no sleeps
- 429 then 200: returned 200, sleeps `[3.0]` (the Retry-After)
- 503, 500, 200: returned 200, sleeps `[1.0, 2.0]`
- 502 every time: `DownloadError ... HTTP 502 after 3 retries`, 4 calls
- 418: `BinanceBanError`, 1 call

## Not exercised
- The build, test and lint targets on the final tree. That result is the runner's (`sdlc/test`).
- Any real HTTPS connection or real proxy CONNECT, which means the connect and read timeouts and the `MAX_BODY_BYTES` cap (R4) were not checked on a live socket.
- A 3xx reaching the `Vision refused (HTTP 3xx)` and `REST refused (HTTP 3xx)` messages (R2). That code is unchanged, and I did not call it.
- `pip install -e .` (R10). I did not run it; the plan records a partial Linux attempt that hit the read-only sandbox.
- Windows (the tzdata install, R9 and R10) and macOS. I ran only on Linux with Python 3.12.
- The `download` CLI subcommand.
- The four new regression tests themselves. The runner runs them.

## Mismatches with plan.md / spec.md
None.

## Verdict
matches the plan
