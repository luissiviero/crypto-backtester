# Release notes — change 0001: Binance Vision kline data layer

## In plain words

*Written by the model from the diff and the plan; every section below is generated from files and git.*

The backtester can now fetch historical Binance candles (klines) on its own. You give it a symbol, an interval, a market (spot or USD-M futures) and a date range, and it returns one tidy table with one row per candle in a single UTC time format. Days missing from Binance's public daily archives are filled from Binance's public price API, and any candles still missing are listed as gaps with the reason, so a range never comes back short without warning. Each finished day is downloaded once and kept in a compact local cache, so loading the same range again needs no network. A command-line tool downloads data, shows what is cached and clears the cache.

<!-- sdlc:plain-words describes faaad89ec0930ee4aecd22bd45606d57fc2d9fe0 -->

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

## Evidence

test green, build green, lint green, verifier.md present, 0 screenshot(s)

## Review findings

2 Important, 2 nits

## Links

- [intent.md](../intent.md)
- [spec.md](../spec.md)
- [plan.md](../plan.md)
