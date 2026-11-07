# Release notes — change 0006: Sweep SMA crossover lengths on one range

## In plain words

*Written by the model from the diff and the plan; every section below is generated from files and git.*

You can now try many SMA crossover settings in one go instead of running the backtest once per setting. The new python -m app.backtest sweep command takes a list of fast lengths and a list of slow lengths and backtests every pair where the fast one is shorter than the slow one. It loads the klines once and prints one row per pair, with the best total return at the top, so you can see which lengths would have worked best on that date range. A grid is capped at 400 pairs, and the command tells you plainly when no pair is valid or the range is too short for any pair to trade. The existing run command prints exactly what it did before.

<!-- sdlc:plain-words describes 77d38d5f7e5ef1245fff0a38e162aa39ed6bfe16 -->

## What changed

A command `python -m app.backtest sweep` runs the SMA crossover for every pair of a grid of fast and slow lengths on one symbol's klines and prints one row per pair, best first.

## Commits

- 69ab10e build(0006): sweep module with its unit tests
- 03fcaf8 build(0006): share the range, fee, load and buy-and-hold helpers in the CLI
- da4a669 build(0006): the sweep sub-command with its CLI tests
- 3220be3 build(0006): simplify
- 369db33 build(0006): gate (build) evidence
- 55d7200 run(build): spend recorded; gate commands run after the session
- ca6b724 test(0006): evidence
- bb5f22d test(0006): gate (test) evidence
- e085aee run(test): spend recorded; gate commands run after the session
- 77d38d5 run(review): spend recorded

## Evidence

test green, build green, lint green, verifier.md present, 0 screenshot(s)

## Review findings

0 Important, 1 nits

## Links

- [intent.md](../intent.md)
- [spec.md](../spec.md)
- [plan.md](../plan.md)
