# Release notes — change 0003: Replace Binance with KuCoin as the market-data source

## In plain words

*Written by the model from the diff and the plan; every section below is generated from files and git.*

The data layer now downloads candles from KuCoin instead of Binance, for the spot market and for KuCoin's USDT-margined perpetual futures, and caches each day as Parquet as before. Callers use KuCoin's symbol names (BTC-USDT on spot, XBTUSDTM on futures). The market name 'um' becomes 'futures'. The 1s interval and the 6h interval on futures are refused. The frames lose three columns KuCoin does not publish (trade count and the two taker-buy volumes), and a quiet interval with no trades has no row, so a short day is normal rather than a gap. A day is reported as a gap only when KuCoin refused or failed to answer for it, and such days are never cached.

<!-- sdlc:plain-words describes bcbab67a43ea948cf0b0443dec72f16f913fd28e -->

## What changed

`app/data/` loads KuCoin klines and no longer calls Binance.

## Commits

- 1724637 build(0003): KuCoin source (params, schema, transport, REST, cache, loader, CLI, script; Vision removed)
- 7bc3672 build(0003): KuCoin stub, fixtures and tests; Binance stub and fixtures removed
- ade844b build(0003): simplify
- 4ce80ac build(0003): a page that does not move the window is unexpected (review)
- b981009 build(0003): gate (build) evidence
- 2180fdc run(build): spend recorded; gate commands run after the session
- b6dd5cc test(0003): evidence
- be1ecb6 test(0003): gate (test) evidence
- 67759f0 run(test): spend recorded; gate commands run after the session
- bcbab67 run(review): spend recorded

## Evidence

test green, build green, lint green, verifier.md present, 0 screenshot(s)

## Review findings

1 Important, 2 nits

## Links

- [intent.md](../intent.md)
- [spec.md](../spec.md)
- [plan.md](../plan.md)
