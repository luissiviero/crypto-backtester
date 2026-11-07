**Verdict: matches the plan.** In change 0003 (build phase), every behaviour I called through the KuCoin stub matched plan.md and spec.md. This does not prove the change works on the final tree: that result is the runner's, in the check run `sdlc/test`.

## Commands run

All three entries were read from `evidence/gate-design.json`, not run. That file records the runner's run on commit `f7f047d5f17fa4888d8770bc3298736bc71d7395` at 2026-11-07T04:18:59Z, the design-phase commit this build phase started from. It is not the final build tree. The runner runs the three targets once after this session and shows the result in `sdlc/test` and in this phase's own gate record. A red target there starts the next fix round by itself, and nothing in this report stands in for it.

- **Overall:** `commands`: `"ok": true`, `"reason": "build, test and lint exit 0"`, `"ran_by": "runner"`. No `deferred` flag is set.
- **Build:** `python -m compileall -q .` exited 0 with output `""`.
- **Test:** `python -m pytest` exited 0 and ended with `============================== 89 passed in 0.63s ==============================`. That suite is the old Binance one.
- **Lint:** `python -m ruff check .` exited 0 with `All checks passed!`.
- **Logs:** there is no `evidence/build.log`, `test.log` or `lint.log`, so there is no first line to quote.
- **Not started here:** I did not run pytest, even with `-k`, because `SDLC_GATE_COMMANDS=runner` is set. I also did not run `compileall`, because it writes `.pyc` files and this role writes nothing. Instead, an in-memory `compile()` of all 17 `.py` files under `app/`, `tests/` and `scripts/` printed `compiled in memory 17 files, no SyntaxError`.

## Behavior exercised

All calls went through `python -c`, using `tests/kucoin_stub.KuCoin` or a sequence fetch, with temporary cache dirs under `$TMPDIR`. The clock was patched to `NOW` (2026-10-03 12:00 UTC) and `http.sleep` was patched out. Nothing touched the network.

**Fixtures**
- All six files in `tests/fixtures/kucoin/` are byte-identical to their `references/capture/` originals (`True` for each).

**Invalid inputs** — all refused with `calls 0`:
- `um`: `unknown market 'um': use 'spot' or 'futures' (USDT-margined perpetuals)`
- `1s` and `1w`: `unknown interval ...`
- `6h` on futures: `interval '6h' is not offered on the futures market`
- `XBTUSDM` and `XBTMZ25`: `invalid futures symbol ... ending in USDTM, for example XBTUSDTM`
- `BTC/USDT` and `../etc`: `invalid spot symbol ...`
- Just inside the rules, `btc-usdt` at `6h` on spot loaded 4 rows.

**Multi-page loads**
- Spot, 1m over 2 days (2880 rows): `rows 2880 calls 2 sorted True unique True`, and `high`/`low` hold the extremes on every row.
- Futures, 1m over 2 days: `rows 2880 calls 15 sorted True unique True`. The first URL is `from=1790812800000&to=1790985599999`, so `to = end − 1`.
- The schema has the 8 columns of R14 with `Datetime(ms, UTC)` and `Float64`.

**Quiet intervals and the end-of-window row**
- The futures 1m fixture day loaded with no gap: `00:14 present False 02:15 present False`.
- The futures 1h fixture has 25 rows, the last at the next day's 00:00. The load returned `rows 24 max 2026-10-01 23:00`.

**Gaps** — each raised `KlineGapError` and cached nothing for the gap day:
- Empty first day: `no candles before 2026-10-02: the date may be before KuCoin's oldest candle for this symbol`. Only `BTC-USDT-1h-2026-10-02.parquet` was cached.
- Empty later day: `no candles on this day`.
- No rows at all: `no candles; check the symbol exists`.
- HTTP 200 with code 400100: `KuCoin refused (HTTP 200, code 400100): Unsupported trading pair.`
- HTTP 400 with a KuCoin body: `KuCoin refused (HTTP 400, code 300000): Parameter 'from' must be milliseconds`.
- A `msg` carrying an ESC character plus 300 characters came back with the ESC stripped, and the message part cut to 200 characters.

**Second page refused**
- Spot: `2820 candle(s) missing ... KuCoin refused (HTTP 400, code 400000): nope`, with only the fully answered day `BTC-USDT-1m-2026-10-01.parquet` cached.
- Futures: `4120 candle(s) missing`, with nothing cached (no complete day had been answered).

**`DownloadError` on a later page** (503 until retries ran out)
- Spot: raised `... HTTP 503 after 3 retries; check the network and run again`, with `BTC-USDT-1m-2026-10-01.parquet` cached.
- Futures, failing on call 9: raised, with `XBTUSDTM-1m-2026-09-29.parquet` cached holding 1440 rows.

**Cache behaviour**
- A second load made `second-load calls 0`.
- The current day loaded 12 rows and cached nothing.
- Files were laid out as `kucoin/spot/BTC-USDT/1h/BTC-USDT-1h-2026-10-01.parquet`.

**CLI** (`main(argv, fetch=stub)`)
- A download with a gap printed `not found: no candles before ...`, then `fetched from KuCoin (2 days)`, then `Total for BTC-USDT 1h spot: 2 fetched, 0 skipped, 1 not found; 24 candles missing. Cache: ...`, and exited 1.
- A cached rerun printed `skipped, already cached (1 day)` and exited 0.
- A futures download exited 0.
- `cache-info` listed `BTC-USDT`, `ETH-USDT` and `XBTUSDTM` (`Total: 5 day files, 10.7 KiB under .../kucoin`). `--symbol xbtusdtm` with no market was accepted, and `--symbol BTC/USDT` printed one line and exited 2.
- `cache-clear eth-usdt 1m --end 2026-09-01` printed `Deleted 1 day file (100 B) for ETH-USDT 1m spot.`. `XBTUSDM --market futures` exited 2.
- Afterwards, `binance-vision/...parquet` and `kucoin/spot/ETH-USDT/1m/notes.txt` were still in place.
- `--market um` is refused by argparse with exit 2.
- `6h` on futures printed `error: ...` and exited 2 without calling the fetch.
- A 500 answer on every try printed `error: ... HTTP 500 after 3 retries ...` and exited 2.
- The help texts carry the plan's description and epilogs. Top-level help reads `KuCoin kline data and its local cache.`; `download --help` ends with the short-day and contract-volume note; `cache-clear --help` ends with `KuCoin may not serve old futures days again: a cleared futures day can be lost.`

**Transport**
- Retries:
  - 429, 503, then 200 retried with sleeps `[1.0, 2.0]`.
  - 404 and 418 were returned on the first call with no retry.
  - `Retry-After: 5` slept `[5.0]`.
  - A 429 with only the reset header: 20000 ms slept `[20.0]`, 90000 ms slept `[60.0]`, and a non-numeric value slept `[1.0]`.
  - Four 500s raised `DownloadError` after sleeps `[1.0, 2.0, 4.0]`.
  - `Retry-After: 61` stopped at once.
- Pacer:
  - No previous answer: no sleep.
  - Remaining 1997, and remaining exactly 100: no sleep.
  - Remaining 50 with reset 12000 slept 12.0; with reset 999999 it slept 60.0; with reset −5 it slept 0.0.
  - Remaining 99 with reset 1000 slept 1.0.
  - A missing header, or a non-integer one, slept 1.0.
- Opener and redirects:
  - The opener's handlers are `ProxyHandler, UnknownHandler, _HTTPSHandler, HTTPDefaultErrorHandler, HTTPErrorProcessor`, with no redirect handler.
  - A faked 302 was returned as `status 302`, and only the original URL was opened.
  - `http://` and `file://` URLs were refused with `URLError unknown url type`.

**Leftover names and Proof tests**
- A search of `app/` and `scripts/` for `binance`, `vision` and `um` finds only the two deprecation notes the plan allows (`app/data/loader.py:88`, `app/data/__init__.py:4`).
- Every Proof test name is present, plus `test_help_notes_short_days_and_lost_futures_days`.

## Not exercised

- The test suite itself, and all three targets on the final build tree. That is the runner's job, shown in `sdlc/test`.
- Windows. I ran on Linux only.
- Real KuCoin. Whether its paging matches the stub is left to the owner's two downloads at the deploy gate.
- The futures current-day forward window against a live API.
- The `scripts/measure_storage.py` run itself. I only checked the lines changed for step 8.
- The real network paths: an actual HTTPS redirect from a server, the connect and read timeouts, and the body-size cap on a real stream.
- Intervals other than 1m, 1h and 6h; symbols at the 30-character limit; and the malformed-row variants (bool, NaN, wrong length), which I did not call directly.
- An old Binance-schema Parquet file placed under `kucoin/`.

## Mismatches with plan.md / spec.md

None.

One note that is not a mismatch: plan.md step 4 asks for an explicit "strictly smaller, else `UNEXPECTED_RESPONSE`" guard on spot paging. `app/data/rest.py:135` filters out rows at or after `window_end` before taking the minimum, so the window always moves and the guard can never fire. The behaviour is the same.

## Verdict

`matches the plan`

Two things were blocked or skipped:
- A shell `cmp` loop over the fixtures was denied, because a variable in it could not be checked before it ran and approval cannot be given in this session. I did the same comparison in Python instead.
- I did not run the `pytest -k` commands your prompt suggested. My instructions forbid starting the test runner when `SDLC_GATE_COMMANDS=runner` is set, so the runner judges the suite.

Files:
- /home/runner/work/crypto-backtester/crypto-backtester/changes/0003-replace-binance-with-kucoin-as-the-marke/plan.md
- /home/runner/work/crypto-backtester/crypto-backtester/changes/0003-replace-binance-with-kucoin-as-the-marke/spec.md
- /home/runner/work/crypto-backtester/crypto-backtester/changes/0003-replace-binance-with-kucoin-as-the-marke/evidence/gate-design.json
- /home/runner/work/crypto-backtester/crypto-backtester/app/data/rest.py
- /home/runner/work/crypto-backtester/crypto-backtester/app/data/loader.py
- /home/runner/work/crypto-backtester/crypto-backtester/tests/kucoin_stub.py
