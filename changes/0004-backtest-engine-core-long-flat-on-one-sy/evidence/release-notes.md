# Release notes — change 0004: Backtest engine core: long/flat on one symbol

## In plain words

*Written by the model from the diff and the plan; every section below is generated from files and git.*

You can now test a simple trading idea on one coin. You give the backtester the price candles you downloaded with app.data and, for each candle, whether you want to be in the market (1) or out of it (0). It buys or sells at the next candle's open price, charges a fee of 0.1% per fill by default, and closes any position still open at the last close. You get back the equity curve, the list of closed trades and a summary: total return, maximum drawdown, number of trades, win rate and the share of time spent in the market. Bad input, such as missing columns, out-of-order times, positions other than 0 or 1, or a negative fee, is refused with an error message that says what was wrong.

<!-- sdlc:plain-words describes d254b780cc6412aa868347ea59c930d007bf8be4 -->

## What changed

A new package `app/backtest/` runs a long/flat backtest of one symbol on a klines frame from `app.data.load_klines`, spot or futures.

## Commits

- fe970ee build(0004): input validation and refusal tests
- 585482f build(0004): summary and its tests
- 1719ac0 build(0004): engine pass and its tests
- 5440de4 build(0004): public API and its test
- 03e042f build(0004): ship app.backtest in the wheel
- f049d76 build(0004): simplify
- a9f33f3 build(0004): refuse price columns that are not numeric
- 2190147 build(0004): gate (build) evidence
- d52aba0 build(0004): build PR recorded
- 302d77d run(build): spend recorded; gate commands run after the session
- 4b6a69c test(0004): evidence
- 3292c32 test(0004): gate (test) evidence
- 8b00e5a run(test): spend recorded; gate commands run after the session
- 83cb251 run(review): origin/main merged before gate (deploy) is offered (R51)
- d254b78 run(review): spend recorded

## Evidence

test green, build green, lint green, verifier.md present, 0 screenshot(s)

## Review findings

0 Important, 3 nits

## Links

- [intent.md](../intent.md)
- [spec.md](../spec.md)
- [plan.md](../plan.md)
