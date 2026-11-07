# Spec: Replace Binance with KuCoin as the market-data source
Change id: 0003. Status: proposed. Produced by: sdlc plugin 1.0.51, /sdlc-design prompt v1 (article p.14). Skills: coding-standards, security-baseline, ux-and-brand, data-conventions, definition-of-done (plugin 1.0.51); overrides: none; policy sources: none

## Requirements
Source and transport
- R1. `app/data/` gets klines only from `https://api.kucoin.com/api/v1/market/candles` (spot)
  and `https://api-futures.kucoin.com/api/v1/kline/query` (futures), with no API key, one
  call at a time. No module under `app/` names a Binance host.
- R2. `app/data/vision.py`, the zip and checksum handling and the parallel download pass are
  gone. Git history keeps them.
- R3. 0002's transport rules stay: every redirect is refused, only `https` URLs open, the
  connect and read timeouts and the body size bound (`MAX_BODY_BYTES`) stay.
- R4. HTTP 429, 5xx and connection errors keep the existing retries (1, 2, 4 s plus jitter,
  `Retry-After` honoured, a wait over 60 s stops with `DownloadError`). Every other status is
  returned to the caller, HTTP 418 included (it is no longer a ban).
- R5. Before each call after the first, the run pauses on the previous answer's
  `gw-ratelimit-remaining` and `gw-ratelimit-reset` headers; when either is absent or not an
  integer it waits 1 s, as today.

Public interface
- R6. `load_klines`, `cache_info`, `clear_cache`, `Gap`, `KlineGapError`,
  `InvalidRequestError`, `DownloadError`, `Fetch` and `HttpResponse` keep their names and
  signatures. `BinanceBanError` is removed from `app.data` and from `app/data/http.py`.
- R7. `python -m app.data download | cache-info | cache-clear` keep their names, positional
  arguments and options in today's order; `--market` takes `spot` or `futures`.
- R8. No CLI message, help text or docstring names Binance or Vision.
- R9. The version stays 0.1.0 in `app/__init__.py` and `pyproject.toml`.

Inputs (all refused with `InvalidRequestError` before any network call)
- R10. Markets: `spot` and `futures`; `um` and anything else are refused.
- R11. Symbols are upper-cased, then: spot accepts 2 to 30 letters, digits and hyphens
  (`BTC-USDT`); futures accepts 2 to 30 letters and digits ending in `USDTM` (`XBTUSDTM`),
  so coin-margined (`XBTUSDM`) and dated (`XBTMZ25`) contracts are refused. No name mapping.
- R12. Intervals: `1m`, `3m`, `5m`, `15m`, `30m`, `1h`, `2h`, `4h`, `6h`, `8h`, `12h`, `1d`.
  `1s`, weeks and months are refused; `6h` is refused on futures.
- R13. Dates keep 0002's rules: a `datetime` bound is refused, start after end and an end in
  the future are refused.

The frame
- R14. Columns, in order: `open_time`, `open`, `high`, `low`, `close`, `volume`,
  `close_time`, `quote_volume`, with today's dtypes (`Datetime("ms", "UTC")` for the two
  times, `Float64` for the rest). `trades`, `taker_buy_base_volume` and
  `taker_buy_quote_volume` are gone.
- R15. Spot rows map as time, open, close, high, low, volume, turnover; futures rows as time,
  open, high, low, close, volume, turnover (the intent's measured table). On every row `high`
  is the largest price and `low` the smallest.
- R16. `close_time` = `open_time` + interval − 1 ms; `quote_volume` = KuCoin's turnover.
- R17. Futures `volume` is KuCoin's contract count, not coins; the `load_klines` docstring
  and the `download` help say so, and that only `quote_volume` compares across markets.
- R18. The frame is sorted by `open_time`, with no duplicate open time, and holds only rows
  of the asked UTC days.

Completeness
- R19. A day is complete when it has at least one candle and every page that covered it was
  answered successfully; its quiet intervals have no row and raise nothing. The
  `load_klines` docstring and the CLI help say that a short frame is normal and that callers
  must not assume a row per interval.
- R20. `KlineGapError` is raised, with `.frame` holding the rows found, for: a day with no
  candle; a day any page of which was refused (HTTP status or KuCoin code other than
  `200000`), malformed, or never asked because paging stopped earlier; a day before
  KuCoin's oldest candle. Each gap's reason says which, with KuCoin's own message for a
  refusal. No oldest date is written into the code.
- R21. Paging never treats a quiet stretch inside the range as its end, and does not depend
  on a fixed page size.

The cache
- R22. Day files live at `<cache>/kucoin/<market>/<SYMBOL>/<interval>/<SYMBOL>-<interval>-<YYYY-MM-DD>.parquet`
  (zstd level 3, atomic write); the default location, `--cache-dir` and
  `CRYPTO_BACKTESTER_CACHE_DIR` are unchanged. Only complete closed days are written; a
  second load of them makes no fetch. Nothing under `binance-vision/` is read, written or
  deleted.
- R23. `cache-info` and `cache-clear` list and delete only files under `kucoin/` that match
  the day-file pattern, hyphenated spot symbols included; the `cache-clear` help notes that
  KuCoin may not serve old futures days again.

Policies
- R24. coding-standards applies: `CLAUDE.md` conventions (rule 1: Python >= 3.10, type hints
  on public functions, ruff at 100 columns, one test module per area), the surrounding
  style (rule 2: one module per job, frozen dataclasses, module constants for messages),
  behaviour changes ship with tests (rule 4), no new dependency (rule 5; `polars` only),
  no dead code (rule 7: the Vision code and the `trades` handling go entirely).
- R25. security-baseline applies: rule 2, every KuCoin answer is untrusted, so the
  envelope (`code`, `data`), each row's length and types, finite numbers and the body size
  are checked before use, URLs are built with `urlencode` from validated values and fixed
  hosts, and cache paths stay under the subtree; KuCoin's `msg` is shortened and stripped of
  control characters before it enters a reason; rule 3, no key or secret exists; rule 7,
  tests make no network call and `sandbox.allowed_domains` stays empty. Rules 1 and 5 do not
  apply: there is no endpoint, login or audit log. Losing Vision's checksum is accepted by
  the owner in intent.md (Constraints).
- R26. data-conventions: rule 1, no personal or sensitive field exists (public market
  prices, classified public); rule 2, the schema stays defined once in
  `app/data/schema.py`; rule 3 does not apply: no migration, old cache files stay unread
  where they are; rule 5, only the eight columns callers use are stored; rule 4 applies to
  the frame contract (see Flagged concerns); rule 6, the dataset's owner is the owner and its
  freshness is per request.
- R27. ux-and-brand applies to CLI output only (no screen): rule 4, messages say what
  happened and what to do next, with no stack trace (`error: <one line>`, exit 2, as today);
  rule 6, copy stays in module constants as today. Rules 1, 2, 3, 5 and 7 have no screen to
  act on.
- R28. definition-of-done applies as written for each phase; the tests dropped with the
  Binance behaviour are declared in plan.md's Proof (`ratchet:`).
- R29. Risk list: none of `auth`, `data migrations`, `money movement`, `production config`
  is touched (no login, no migration of stored data, no orders, no deployment config).

## Design
Same modules, one job each (`CLAUDE.md` Architecture); `vision.py` is deleted.

- `params.py` — `MARKETS = ("spot", "futures")`; `INTERVAL_MS` without `1s`;
  `FUTURES_REFUSED_INTERVALS = {"6h"}`; `validate_symbol(symbol, market)` with one pattern
  per market (R11); `KlineRequest`, `parse_date`, `day_start_ms` unchanged. The KuCoin names
  of each interval live here beside `INTERVAL_MS`: spot `type` (`1min` ... `1day`), futures
  `granularity` in minutes.
- `http.py` — `BinanceBanError` and the 418 branch go. `WeightPacer` becomes a
  `RateLimitPacer` with the same `wait()` / `record()` shape: missing or non-integer headers
  wait `UNKNOWN_WEIGHT_WAIT` (1 s); `remaining` below a reserve waits the `reset`
  milliseconds, bounded to 0..60 s (an untrusted header never sleeps longer). One pacer per
  run: both hosts share one pool.
- `schema.py` — `SCHEMA` of the eight columns (R14). Two row parsers replace the CSV and
  Binance REST ones, each taking the rows and the interval:
  `frame_from_spot_rows` (7 strings; time in seconds, prices in the order of R15) and
  `frame_from_futures_rows` (7 JSON numbers, bools refused; time in milliseconds). Both
  require exactly 7 items per row, integer times inside the 64-bit range, finite numbers,
  and compute `close_time`; any other shape raises `MalformedDataError`. The microsecond
  detection goes (Vision-only).
- `rest.py` — `ENDPOINTS` keyed by market (URL plus builder of the query). A shared
  `parse_answer(response)` returns rows or a failure reason: not HTTP 200, body over
  `MAX_BODY_BYTES`, not JSON, `code` not `"200000"` (reason `KuCoin refused (code <c>):
  <msg>`; for a non-200 with a parseable body `KuCoin refused (HTTP <n>): <msg>`), `data`
  not a list, or a row that fails the schema (`unexpected KuCoin response`).
  `fetch_range(fetch, pacer, request, start_ms, end_ms) -> RestRange` pages one call at a
  time and works from the rows returned, never from a page size:
  - spot asks `startAt`/`endAt` in seconds over `[start, end)`; KuCoin keeps the newest rows,
    so the next window ends at the oldest open time returned; an empty answer means the
    window holds no candle, which ends the range;
  - futures asks `from`/`to` in milliseconds with `to = end − 1`; KuCoin keeps the oldest
    rows, so the next window starts one interval after the newest open time returned; rows at
    or after `end` (the measured end-of-window row) are dropped; an empty answer ends the
    range;
  - a page whose rows do not move the window is an unexpected response.
  `RestRange` carries the frame, the failure reason (or none) and the covered span
  `[covered_from, covered_until)`: the part of the range every answered page vouches for
  (spot grows it downwards from `end`, futures upwards from `start`; with no failure it is
  the whole range).
- `loader.py` — `sync_days` reads cached closed days, then runs `fetch_range` once per run
  of consecutive uncached days, in order. Each day becomes one `DayOutcome`:
  `rest` when the day lies inside the covered span and has a candle; otherwise `missing`
  with a reason: the range's failure for a day outside the covered span; for an empty
  covered day, `no candles before <first candle day>: the date may be before KuCoin's oldest
  candle for this symbol` when a later day of the range has candles and no earlier one does,
  `no candles on this day` when candles exist before it, and `no candles; check the symbol
  exists` when the range has none at all. `_worth_caching` writes a `rest` closed day
  whatever its row count. `find_gaps` reports gaps only for `missing` days (their grid open
  times with no row, the current day's grid ending at the last closed interval);
  `KlineGapError` and `Gap` are unchanged. `load_klines`'s docstring states R17 and R19.
  The thread pool, `_vision_pass`, `MISSING_IN_FILE` and `MISSING_IN_REST` go.
- `cache.py` — `SUBTREE = "kucoin"`; `file_name` moves here from `vision.py`; the day-file
  pattern's symbol part admits hyphens (the interval and the date anchor the match, and the
  symbol must still equal its directory's name); `cache_info` checks a `--symbol` against the
  given market, or against either market when none is given.
- `__main__.py` — the description names KuCoin; `--market` choices `spot`, `futures`;
  `download` help (an epilog) states R17 and R19; `cache-clear` help states R23's note;
  source labels `skipped, already cached` and `fetched from KuCoin`; the total line drops
  the Vision count: `<n> fetched, <n> skipped, <n> not found; <n> candles missing`. Exit
  codes stay (0, 1 when gaps, 2 on a refused input, `DownloadError` or `OSError`).
- `__init__.py` — the docstring names KuCoin; `BinanceBanError` leaves `__all__`.
- `scripts/measure_storage.py` — builds synthetic rows of the eight columns, reads the
  `kucoin/` subtree and validates symbols per market, so it keeps working.
- Tests — a KuCoin stub replaces `tests/binance_stub.py`: it answers both endpoints from
  fixtures cut from the captured answers in `references/capture/`, honours each endpoint's
  window rules, order and page cap (1500 spot, 200 futures), and records every URL.
  Fixtures live in `tests/fixtures/kucoin/`. 0002's redirect test keeps its checks with a
  KuCoin URL.
- Unchanged: the cache location rules, the atomic write, `read_day`'s schema check (a file
  of another schema is fetched again), the CLI's argument order, `Gap` and `KlineGapError`.

## Open questions from intent
- "A mistyped futures symbol looks like no data." — answered by the owner in intent.md: no
  contract lookup; the gap reason of a range with no candle at all reads `no candles; check
  the symbol exists` (Design, `loader.py`). Spot needs nothing extra: KuCoin refuses an
  unknown pair with code 400100, which becomes a refusal reason with KuCoin's message.
- "How do we show that a short frame is normal?" — answered by the owner in intent.md: the
  `load_klines` docstring and the `download` help say so (R19).
- "Is the futures history limit a rolling window?" — answered by the owner in intent.md: a
  note in the `cache-clear` help, nothing more (R23). The fact itself stays unknown: the
  runs have no network, and the owner's deploy-gate downloads do not settle it either.
- "Does the futures page stay 200 at longer intervals?" — answered by the owner in
  intent.md: page from the last row returned; the design never uses a page size (R21,
  Design, `rest.py`).

## Flagged concerns
- decided (by panel #1): Keep version 0.1.0 as intent.md directs, and add a deprecation note naming the removed columns (trades, taker_buy_*), BinanceBanError, the um market and the 1s interval, with the reason (KuCoin does not publish them), to the load_klines docstring and the app/data/__init__.py module docstring; the version half of rule 4 stays the owner's call, to confirm at the merge gate. — data-conventions rule 4 ("a removed or renamed field is a new version with a deprecation
  note") meets the intent's frame and API changes: three columns, `BinanceBanError`, the
  `um` market and the `1s` interval are removed, and intent.md keeps the version at 0.1.0
  with no deprecation step. The design follows the intent (the package is pre-1.0 and its
  one caller is the owner); the policy text does not settle which wins.
- Rate-limit reserve (a guess; the intent names the headers but no threshold): the design
  pauses until `gw-ratelimit-reset` when `gw-ratelimit-remaining` falls below 100 (about 33
  calls at the measured cost of 3 from the measured pool of 2000 per 30 s, left for anything
  else the owner runs on the same IP), and bounds that pause to 60 s.
- [x] Deleting the Binance tests: decided allowed per coding-standards rule 4 (it forbids
  deleting a *failing* test; these pass and check behaviour this change removes) and the
  plan-template skill (a dropped test file the plan's own work requires is declared in Proof
  with `- ratchet: tests may fall, because ...`); behaviours that stay keep equivalent tests.

## Acceptance
- Build `python -m compileall -q .` prints nothing and exits 0; lint `python -m ruff check .`
  prints `All checks passed!`; test `python -m pytest` passes every test, offline, with no
  network call.
- The tests show, against fixtures cut from `references/capture/`:
  - on every spot and futures fixture row `high` is the largest price and `low` the smallest,
    and the frame has the eight columns and dtypes of R14, `close_time` per R16;
  - a spot range of more than 1500 candles and a futures range of more than 200 load
    completely, sorted, with no duplicate;
  - the futures end-of-window row adds no candle of the next day;
  - the futures one-day fixture without 00:14 and 02:15 loads with no gap;
  - an empty day, a refused page and a page cut short each raise `KlineGapError` with their
    reason and are not cached; a day before the first candle names the oldest-candle reason;
  - HTTP 200 with a KuCoin error code is a refusal whose reason holds KuCoin's message;
  - `6h` on futures, `1s`, `um`, and a futures symbol not ending in `USDTM` are refused with
    no fetch;
  - the pacer waits on the two KuCoin headers and 1 s without them; 429 and 5xx retry;
    redirects are not followed;
  - a second load makes no fetch, and the cache holds Parquet files only, under `kucoin/`;
    `cache-info` and `cache-clear` handle a hyphenated spot symbol;
  - no module under `app/` names a Binance host;
  - `download`, `cache-info` and `cache-clear` work against the stubbed transport.
- At the deploy gate the owner runs
  `python -m app.data download BTC-USDT 1h 2026-10-01 2026-10-03 --market spot` and
  `python -m app.data download XBTUSDTM 1m 2026-10-01 2026-10-03 --market futures`; both exit 0.
- No screen is touched (CLI only), so no `Mock:` line.
