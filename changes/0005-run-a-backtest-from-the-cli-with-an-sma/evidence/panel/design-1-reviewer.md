## Verdict
Keep the design as written: parse `--fee` text before loading, leave the range check to the engine after `load_klines`. This is not an Important finding and needs no change.

## Why
- The intent defines this refusal by the engine: "a `--fee` that `run_backtest` refuses
  (`BacktestInputError`)" (intent.md:54). It asks only that the refusal come "before any
  backtest" (intent.md:47-48). The design meets that: `validate` checks the fee first
  (`app/backtest/inputs.py:29`, `_check_fee` at :41-50), before any calculation (spec.md:124-125).
- The intent says the engine (`inputs.py`) "is used, not changed" (intent.md:75-76, :92).
  `_check_fee` is private, so a check in the CLI before loading would mean copying
  `0 <= fee < 1` into a second place. coding-standards rule 2 (match the surrounding code)
  and rule 7 (small functions, no dead or duplicate logic) point against two copies of the
  rule that could drift apart.
- REVIEW.md keeps Important for what "would break behavior, leak data or breach a policy".
  Here the only cost is that a mistyped `--fee 1.5` on an uncached range first downloads
  public klines. Those days stay cached and are reused, and the command still prints
  `error:` and exits 2. Nothing breaks, nothing leaks, and no policy is breached.
  security-baseline rule 2 still holds, because the input is checked before it is used.
- The spec flags this trade-off (spec.md:169-176) and so does the plan (plan.md:124-126, :145-147).
  The plan also names the one-line change if the owner wants a check before loading. That
  leaves the choice with the owner, and the design does not need to make it.
- The build must keep `test_run_refuses_bad_fee` (plan.md:179) covering `--fee 1.5` and
  `--fee -0.1` with exit 2 and the engine's message (plan.md:191).
