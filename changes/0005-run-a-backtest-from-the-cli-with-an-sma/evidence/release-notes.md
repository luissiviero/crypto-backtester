# Release notes — change 0005: Run a backtest from the CLI with an SMA crossover

## In plain words

*Written by the model from the diff and the plan; every section below is generated from files and git.*

You can now run a backtest straight from the command line: python -m app.backtest run SYMBOL INTERVAL START END loads the KuCoin candles for those days (spot by default, or perpetuals with --market) and prints a summary of how the strategy did. The strategy is a simple moving-average crossover: it holds the coin while the fast average (20 candles by default, --fast) is above the slow one (50 by default, --slow) and stays out otherwise. You can also set the trading fee with --fee and choose where cached candles live with --cache-dir. Bad input, such as a fast length that is not shorter than the slow one or a date range too short for the slow average, gets a clear error message instead of a result. The same strategy is also available to Python code as sma_cross_positions in app.backtest.

<!-- sdlc:plain-words describes cb3027aedb10604ce964a535a0c84a187ef0abc3 -->

## What changed

A command `python -m app.backtest run` backtests one built-in strategy, a simple moving-average (SMA) crossover, on one symbol's cached KuCoin klines and prints the summary.

## Commits

- 2384978 build(0005): strategy module and its tests
- 91dff56 build(0005): export sma_cross_positions from app.backtest
- c60b408 build(0005): python -m app.backtest run and its tests
- 1da2711 build(0005): simplify
- 4103884 build(0005): gate (build) evidence
- eedfb32 run(build): spend recorded; gate commands run after the session
- 5428932 test(0005): evidence
- 965c7ca test(0005): gate (test) evidence
- da868f9 run(test): spend recorded; gate commands run after the session
- e329146 run(review): origin/main merged before gate (deploy) is offered (R51)
- 9b14e3b run(review): spend recorded
- cb3027a review(0005): panel decision 1

## Evidence

test green, build green, lint green, verifier.md present, 0 screenshot(s)

## Review findings

0 Important, 5 nits

## Links

- [intent.md](../intent.md)
- [spec.md](../spec.md)
- [plan.md](../plan.md)
