# Release notes — change 0001: Binance Vision kline data layer

## In plain words

*Written by the model from the diff and the plan; every section below is generated from files and git.*

The backtester can now fetch historical candlestick (kline) data for Binance spot and USD-M futures markets. It downloads the daily archive files from Binance Vision, and when a day is not published there yet it fills the gap from the Binance REST API. The data comes back as polars tables with one fixed set of columns, and each day is cached as a Parquet file outside the repository, so the same day is downloaded only once. A small command line tool (python -m app.data) downloads data, shows what the cache holds and clears it; the cache location can be set with --cache-dir or an environment variable.

<!-- sdlc:plain-words describes 8e1e588ce98e771916f0a348d93fa50f858d3947 -->

## What changed

A data module in `app/` that, for one symbol, one interval and one market at a time, does the following.

## Commits

- ff3515c build(0001): polars dependency; CI install line recorded as a departure
- fa77717 build(0001): params validation
- 85861d0 build(0001): schema and normalisation
- 2461163 build(0001): http transport, retries and weight pause
- 2a829da build(0001): Vision source with checksum and safe extraction
- 3a537ec build(0001): REST fill with paging and shape check
- 53c48f4 build(0001): Parquet cache, info and clear
- d2983e4 build(0001): loader, gaps and public API
- 75a90dc build(0001): CLI download, cache-info, cache-clear
- bd3c49e build(0001): storage measurement script and its output
- 5f7bde6 build(0001): shared test stub split out; build, test and lint run
- c9f99e0 build(0001): simplify
- 7e0f606 build(0001): cache each day as it lands; bound integers; cache-dir errors
- 53d00df build(0001): gate (build) evidence
- 6a949d9 run(build): spend recorded; gate commands run after the session
- e281f5c test(0001): evidence
- 9b6c427 test(0001): gate (test) evidence
- d5e39f0 run(test): spend recorded; gate commands run after the session
- faaad89 run(review): spend recorded
- 71e910d review(0001): gate (deploy) evidence
- 225ea0a run(deploy): spend recorded; gate commands run after the session
- 8e1e588 run(fix): origin/main merged before gate (deploy) is offered (R51)

## Evidence

test green, build green, lint green, verifier.md present, 0 screenshot(s)

## Review findings

0 Important, 3 nits

## Links

- [intent.md](../intent.md)
- [spec.md](../spec.md)
- [plan.md](../plan.md)
