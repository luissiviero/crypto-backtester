# Verifier report: change 0003 (test phase), replace Binance with KuCoin

This ran in CI (`SDLC_GATE_COMMANDS=runner`), so I did not run build, test or lint myself. Short version: the build gate's record is green on all three targets, every Proof test in plan.md exists, and the code and tests match spec.md and plan.md. **Verdict: matches the plan.**

## Commands run (read, not run)

I read `evidence/gate-build.json`, the runner's run on commit `4ce80acd9a47527e73b2e3c1e1b94f8081dcaaf8` of 2026-11-07T05:17:28Z. That is the tree this phase started from, not the final one. The final tree's result is the runner's: it runs the three targets once after this session and shows the result in the check run `sdlc/test` and in `gate-test.json`. A red target there starts the next fix round by itself, and nothing here stands in for it.

Between that commit and HEAD (`2180fdc`), `git diff --stat 4ce80ac HEAD` shows changes only under `changes/0003-.../evidence/` and `status.yaml`. No file under `app/`, `tests/` or `scripts/` changed.

The `commands` entry has `ok: true`, `ran_by: runner`, and no `deferred` flag. Its `evidence` check is also `ok: true` and not deferred.
- `python -m compileall -q .`: exit 0, output `""`
- `python -m pytest`: exit 0, last lines:
  ```
  tests/test_data.py ..................................................... [ 50%]
  .............                                                            [ 63%]
  tests/test_data_cache.py .....                                           [ 68%]
  tests/test_data_cli.py ..........                                        [ 77%]
  tests/test_data_rest.py ......................                           [ 99%]
  tests/test_smoke.py .                                                    [100%]
  ============================= 104 passed in 0.35s ==============================
  ```
- `python -m ruff check .`: exit 0, `All checks passed!`

The first line of each log:
- `evidence/test.log`: `# python -m pytest — deferred to the runner — 2026-11-07T05:19:17Z`
- `evidence/build.log`: `# python -m compileall -q . — deferred to the runner — 2026-11-07T05:19:17Z`
- `evidence/lint.log`: `# python -m ruff check . — deferred to the runner — 2026-11-07T05:19:17Z`

These three are not failures. This session wrote them minutes ago, and the runner replaces them with the targets' own output.

## Behavior exercised

**Static checks:**
- **Proof tests:** I compared every `- test:` name in plan.md Proof with the `def test_` names under `tests/`. None is missing.
  - There are three extra tests: `test_page_that_does_not_move_the_window_is_unexpected` and `test_help_notes_short_days_and_lost_futures_days` are both declared in plan.md Risks; `test_package_imports` is the existing smoke test.
  - No `skip` or `xfail` markers are present.
- **Binance names:** `grep -rniE "binance|vision" app scripts` hits only the deprecation notes that R6 and R8 allow: `app/data/__init__.py:4` and `app/data/loader.py:88`.
- **Files:** `app/data/vision.py` is deleted. The source files the build changed (`git diff --name-status 38082bd 4ce80ac`) are exactly the ones plan.md lists. `pyproject.toml` and `.github/` are unchanged, and the version is still `0.1.0` in both places.

**Direct calls through `tests/kucoin_stub.py`**, with sleep stubbed out, clock at `NOW` and no `.env*` read:
- **Package API:** `BinanceBanError` is gone from both `app.data` and `app.data.http` (`False False`).
- **Spot fixture (`btc-usdt 1h 2026-10-01`):** `24` rows, columns `['open_time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_volume']`, time dtype `Datetime(time_unit='ms', time_zone='UTC')`, sorted, 1 call. `high is max: True low is min: True`.
- **Second load:** `second load calls: 0 True`, so no fetch and an equal frame.
- **Futures 1m fixture:** `200` rows in 2 calls, with no gap.
- **Inputs just outside the accepted ones:**

  | Input | Result |
  |---|---|
  | `6h` on futures | refused, 0 calls |
  | `USDTM`, `AUSDTM` (6 characters) | refused, 0 calls |
  | `ABUSDTM` (7 characters, the boundary) | accepted |
  | 31-letter spot symbol | refused |
  | 30-letter spot symbol | accepted |
  | `1w` | refused |
  | `XBTUSDM` | refused |
  | `um` | refused (`unknown market 'um': use 'spot' or 'futures'`) |

- **Spot page fails mid-range** (1h, 3 days, page size 30, second page malformed): one gap `('2026-09-28 00:00', '2026-09-29 17:00', 42, 'unexpected KuCoin response')`. The frame holds 30 rows; 2026-09-30 is complete and 2026-09-29 is a gap even though it is partly covered, as planned.
- **Futures `1d` with page size 2:** 5 rows in 3 calls.
- **Current day, spot, at 05:30 UTC:** hours `[0, 1, 2, 3, 4]` and no file written.
- **Transport:**
  - A 429 with `gw-ratelimit-reset: 45000` and then one with `abc`: sleeps `[45.0, 2.25]`, then status 200.
  - A 418 is returned, not retried.

**CLI** (`python -m app.data`, offline, in a temporary cache directory):
- **`cache-info`:** both the plain form and `--symbol btc-usdt` list `spot BTC-USDT 1h 1 10 B`, exit 0.
- **`cache-clear btc-usdt 1h`:** `Deleted 1 day file (10 B) for BTC-USDT 1h spot.`, exit 0. The `binance-vision/` file is left alone (`True`).
- **Refused inputs:**
  - `download XBTUSDTM 6h ... --market futures` prints `error: interval '6h' is not offered on the futures market`, exit 2.
  - `--market um` gets argparse's `invalid choice: 'um' (choose from spot, futures)`, exit 2.
- **Help text:**
  - `download --help` ends with the R17/R19 note: `... a short day is normal, never assume one row per interval. Futures volume counts contracts, spot volume coins; only quote_volume compares across markets.`
  - `cache-clear --help` ends with `KuCoin may not serve old futures days again: a cleared futures day can be lost.`

**Reading the code and tests against spec.md Acceptance:**
- Every Acceptance bullet maps to at least one test in `tests/test_data.py`, `tests/test_data_rest.py`, `tests/test_data_cache.py` or `tests/test_data_cli.py`.
- R1–R27 are each covered as plan.md steps 1–10 describe.
- `test_page_cut_short_is_a_gap_and_not_cached` covers both spot and futures. So does `test_days_fetched_before_a_download_error_stay_cached`.

## Not exercised

- **Targets on the final tree:** I did not run build, test or lint on any tree. The result above is the runner's run on `4ce80ac`; the final tree's result is in the check run `sdlc/test`.
- **Live KuCoin:** nothing here confirms the real endpoints' window rules, page caps, error codes or rate-limit headers. The stub encodes the measured rules, and the owner's two deploy-gate downloads are the only live check.
- **Fixture provenance:** I could not check that `tests/fixtures/kucoin/*.json` are byte copies of `references/capture/`. The comparison command was denied in this session (a shell variable cannot be approved here).
- **Real network transport:** I did not call `urllib_fetch` against a real HTTPS host. Redirects and only-https are covered only by the suite's monkeypatched tests.
- **Platform:** I ran on Linux only, not Windows, so the Windows cache root and `tzdata` path were not run.
- **Futures on the current day:** the last window KuCoin may refuse is not exercised by the stub; plan.md Risks names this.
- **Extreme inputs:** I tried no very long ranges (months at 1m), no real `Retry-After` HTTP-date values, and nothing beyond the parser rows already in `test_malformed_rows_are_rejected`.
- **`scripts/measure_storage.py`:** I only read it (`validate_symbol(symbol, market)`, `cache.SUBTREE`); I did not run it.

## Mismatches with plan.md / spec.md

None.

One observation that is not a mismatch: `app/data/cache.py:122` checks the `--interval` of `cache_info` against `"spot"`. So `cache-info --market futures --interval 6h` is accepted and simply lists nothing. That is harmless, and no spec line covers it.

## Verdict

matches the plan
