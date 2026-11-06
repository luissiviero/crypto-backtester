# Intent: Replace Binance with KuCoin as the market-data source
Author: owner (product owner), drafted by Claude from the owner's answers of 2026-11-05. Change id: 0003. Entry route: idea.

## Problem
The owner has decided to use KuCoin instead of Binance as the market-data source.

Today `app/data/` can only load Binance candles, so every later backtest would run on the wrong
exchange's prices. The layer cannot simply point at new URLs: KuCoin's history page shows no file
URLs a program can use, its two kline endpoints differ from Binance's and from each other, and it
publishes fewer columns.

## Proposed outcome
`app/data/` loads KuCoin klines and no longer calls Binance. Git history keeps the Binance code.

**Source**
- REST only, with no API key, one call at a time:
  - spot: `https://api.kucoin.com/api/v1/market/candles`;
  - futures: `https://api-futures.kucoin.com/api/v1/kline/query`.
- `app/data/vision.py`, its zip and checksum handling, and the parallel download pass are removed.

**What callers use**
- `load_klines`, `cache_info`, `clear_cache`, `Gap`, `KlineGapError`, `InvalidRequestError`,
  `DownloadError`, `Fetch` and `HttpResponse` keep their names.
- `python -m app.data download | cache-info | cache-clear` keep their names and argument order.
  For example: `python -m app.data download BTC-USDT 1h 2026-10-01 2026-10-31 --market spot`.
- `BinanceBanError` is removed: nothing shows that KuCoin has a ban status.
- CLI messages stop naming Binance or Vision.
- The version stays 0.1.0.

**Markets and symbols**
- `--market` and `market=` take `spot` or `futures`. `um` is gone.
- `futures` means USDT-margined perpetuals only: the symbol must end in `USDTM`. Coin-margined
  and dated contracts are refused.
- Callers type KuCoin's own names, with no mapping: `BTC-USDT` on spot, `XBTUSDTM` on futures.
  Input is upper-cased. The symbol check and the cache file pattern accept the hyphen on spot.

**Intervals**
- Our names stay, translated inside: `1m`, `3m`, `5m`, `15m`, `30m`, `1h`, `2h`, `4h`, `6h`,
  `8h`, `12h`, `1d`.
- `1s` is removed. `6h` is refused on futures with `InvalidRequestError`, before any network call.
- No week or month: they do not fit a per-day cache.

**The DataFrame**
- Columns: `open_time`, `open`, `high`, `low`, `close`, `volume`, `close_time`, `quote_volume`.
  Dtypes are unchanged from today.
- `trades`, `taker_buy_base_volume` and `taker_buy_quote_volume` are removed: KuCoin does not
  publish them.
- `close_time` is computed as open time plus the interval minus 1 ms.
- `quote_volume` comes from KuCoin's turnover.
- Futures `volume` stays KuCoin's number, which is a count of contracts, not coins. This is
  documented where callers will see it. Spot `volume` is in coins. Do not compare the two;
  `quote_volume` is comparable.

**Missing candles**
- KuCoin publishes no candle for an interval with no trades.
- A closed day with at least one candle, from an answer that was not cut short, is complete: no
  row for the quiet intervals, no gap, and the day is cached.
- A day with no candle at all stays a gap and raises `KlineGapError`, as does any day whose answer
  was refused or cut short. A failure part way through a day must not look like quiet minutes.
- A date before KuCoin's oldest candle raises `KlineGapError` with a clear reason. No silent
  trimming, and no oldest date written into the code.

**The cache**
- The layout stays, under a new subtree: `<cache>/kucoin/<market>/<SYMBOL>/<interval>/`.
- Any existing `binance-vision/` subtree is left alone. The owner deletes it by hand.
- The default location, the cache options and the zstd Parquet format are unchanged.

**Rate limits**
- REST calls pause on `gw-ratelimit-remaining` and `gw-ratelimit-reset`, replacing the Binance
  weight header. When the header is absent the run waits 1 s, as it does today.
- HTTP 429 and 5xx keep the existing retries.

How to check it is done:
- Tests run offline against fixtures made from the captured answers named in Examples/References.
- The tests show that:
  - spot and futures rows land in the right columns: on every fixture row, `high` is the largest
    price and `low` the smallest;
  - a spot range longer than 1500 candles and a futures range longer than 200 load completely,
    sorted, with no duplicates;
  - the futures row at the window's end does not add a candle from the next day;
  - the futures fixture with no 00:14 and 02:15 candles loads with no gap;
  - an empty day, a refused page and a page cut short each raise `KlineGapError` with the reason,
    and are not cached;
  - HTTP 200 with a KuCoin error code is treated as a refusal, with KuCoin's message in the reason;
  - `6h` on futures, `1s`, `um` and a futures symbol not ending in `USDTM` are refused with no fetch;
  - a second load makes no fetch, and the cache holds Parquet only, under `kucoin/`;
  - no module under `app/` names a Binance host.
- `download`, `cache-info` and `cache-clear` work against the stubbed transport.
- The owner runs one real download of each market at the deploy gate, because CI and the runs have
  no network: `python -m app.data download BTC-USDT 1h 2026-10-01 2026-10-03 --market spot` and
  `python -m app.data download XBTUSDTM 1m 2026-10-01 2026-10-03 --market futures`.
- Build, test and lint stay green.

## Affected users and systems
- The owner, as the person running downloads and later backtests.
- `app/data/`: `params.py`, `http.py`, `rest.py`, `schema.py`, `cache.py`, `loader.py`,
  `__main__.py`, `__init__.py`; `vision.py` is deleted.
- `scripts/measure_storage.py`: it builds rows with the removed columns and uses the cache
  layout, so it must change or stop working.
- `tests/`: `tests/test_data.py` and `tests/test_data_cli.py` are rewritten.
  `tests/binance_stub.py` and `tests/fixtures/binance/` are replaced by KuCoin versions.
- External services, public and read-only, with no account: `api.kucoin.com` and
  `api-futures.kucoin.com`. The Binance hosts are no longer called.
- The owner's disk: a new cache subtree. No migration: old files stay where they are, unread.
- No new dependency. `pyproject.toml` and `.github/workflows/ci.yml` need no KuCoin change.

## Constraints
- **This change builds on change 0002** (merged to `main` on 2026-11-05): its redirect, datetime
  and `tzdata` fixes. Those stay: all redirects refused, `datetime` bounds refused. The 0002
  regression test that uses a Binance URL moves to a KuCoin URL and keeps checking the same thing.
- **Deleting the Binance tests is deliberate and approved by the owner.** `CLAUDE.md` says never
  to delete a failing test. Here they go because the behaviour they check is removed. Behaviours
  that stay (retries, gaps, cache, CLI, input checks) keep equivalent tests. This is a
  feature-type change, and `plan.md`'s Proof section declares the drop
  (`- ratchet: tests may fall, because the Binance behaviour they check is removed`) and names
  every deleted test file and fixture.
- **Use the measured behaviour below, not KuCoin's docs.** The docs summaries were wrong or in
  conflict on spot column order, futures page size and the futures time unit. Measured on
  2026-11-05:

  | | Spot | Futures |
  |---|---|---|
  | Row | strings: time, open, **close, high, low**, volume, turnover | numbers: time, open, high, low, close, volume, turnover |
  | Time in rows | seconds | milliseconds |
  | Window | `startAt`, `endAt` in seconds; end not returned | `from`, `to` in milliseconds; end returned |
  | Order | newest first | oldest first |
  | Rows per call | 1500; a longer window keeps the newest | 200 at 1m, 3m, 5m; a longer window keeps the oldest |
  | Interval parameter | `type`: `1min` ... `1day` | `granularity` in minutes; 360 refused |
  | Unknown symbol | HTTP 200, code 400100 | HTTP 200, code 200000, empty list |

- The rate limit was 2000 per 30 s. Each call took 3, from one pool shared by both hosts.
- No captured call to either host redirected, so 0002's refuse-all rule fits these endpoints.
- Treat REST answers as untrusted: check the envelope (`code`, `data`) and the row shape before use,
  and keep the size bound. REST has no checksum, so this change gives up the integrity check that
  Vision files had. The owner accepts that.
- Paging must not end early: a quiet stretch inside a range is not the end of the range.
- Tests never touch the network. `sandbox.allowed_domains` stays empty.
- No secrets, no API key, no personal data.
- Do not commit cached data or write data into the repository by default.
- Python >= 3.10, type hints on public functions, ruff clean at line length 100.
- **Guardrail lines for the owner.** A run cannot edit `CLAUDE.md`, so `plan.md` names these for the
  owner's own PR, after this change merges:
  - lines 5 and 6: `` `app/data/`: KuCoin spot and USDT-margined perpetual klines from KuCoin's public REST API `` / `as polars frames, cached per day as Parquet outside the repository; its CLI is`;
  - line 30: remove `vision, `;
  - lines 36 and 37: name the new stub and fixture paths.
- Out of scope: other exchanges, keeping Binance beside KuCoin, KuCoin's bulk files, its unified
  endpoint, coin-margined and dated futures, converting futures volume to coins, filling quiet
  intervals with invented candles, resampling, several symbols per call, a console script.

## Open questions
- **A mistyped futures symbol looks like no data.** KuCoin answers with an empty list. Owner's answer: no
  extra call; the gap reason says "no candles; check the symbol exists". The alternative is one
  lookup at `/api/v1/contracts/{symbol}` per request, for a clearer error.
- **How do we show that a short frame is normal?** Quiet intervals now return fewer rows with no
  error, which changes 0001's promise of "never a silently short frame". Owner's answer: say so in the
  `load_klines` docstring and the CLI help. Later strategies must not assume every interval has a
  row.
- **Is the futures history limit a rolling window?** Unknown, and the runs have no network to check.
  Futures candles were found from 2024-08-05 at 1h and 2024-12-01 at 1m, against a 2020 listing. If
  the limit rolls, clearing the cache loses days that cannot be fetched again. Owner's answer: a note in
  the `cache-clear` help, nothing more.
- **Does the futures page stay 200 at longer intervals?** Measured only at 1m, 3m and 5m, where the
  window held more than 200 candles. Owner's answer: page from the last row returned, not from an assumed
  size, so the code does not depend on the number.

## Examples/References
- `changes/0003-replace-binance-with-kucoin-as-the-marke/references/capture/`: real answers
  captured on 2026-11-05 from the owner's PC, with `summary.json` and the script that made them
  (`kucoin_capture.py`; edited since the capture only to pass the project's ruff). They are
  references and the source for test fixtures:
  - `spot-BTC-USDT-1hour.json`, `futures-XBTUSDTM-60-from-to-in-ms.json`: one day at 1h;
  - `futures-XBTUSDTM-1-one-day.json`: 200 rows, with the candles at 00:14 and 02:15 absent;
  - `spot-unknown-symbol.json`, `futures-unknown-symbol.json`,
    `futures-XBTUSDTM-60-from-to-in-seconds.json`: refusals;
  - `futures-contract-XBTUSDTM.json`: the contract size, 0.001.
- Limits of the capture: BTC only, one location, and no quiet symbol. The oldest dates come from a
  bisect that assumes no long holes in the data.
- KuCoin docs, for reference only:
  - spot klines: https://www.kucoin.com/docs-new/rest/spot-trading/market-data/get-klines
  - futures klines: https://www.kucoin.com/docs-new/rest/futures-trading/market-data/get-klines
  - rate limits: https://www.kucoin.com/docs-new/rate-limit-rule-classic
  - unified endpoint, announced as the replacement with no shutdown date found:
    https://www.kucoin.com/announcement/en-kucoin-unified-api-announcement
- The change this replaces: `changes/0001-binance-vision-kline-data-layer/`.
