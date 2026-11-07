## Verdict
Keep the literal `<` rule as designed; leave the concern open for the owner as a non-blocking note, not an Important finding.

## Why
- The intent's refusal list says, word for word, "a date range with fewer candles than `--slow`"
  (intent.md, "Inputs it must refuse"). Spec R12 and plan.md step (`frame.height < slow`) match it, so
  REVIEW.md's Compliance pass (diff matches spec and plan) is met. Switching to `<=` would depart
  from the intent's literal rule without the owner saying so.
- The fact in the concern holds: `app/backtest/engine.py` fills each decision at the next row's
  open (lines 1, 45, 63-70), so the only possible long signal of an exactly-`slow`-row frame, on
  the last row, never fills, and the run prints 0 trades.
- That outcome does not "break behavior, leak data or breach a policy" (REVIEW.md, "What
  Important means here"): the command exits 0 with a correct, if uninformative, summary (0 trades,
  0% time in market, buy-and-hold line still useful). No coding-standards, ux-and-brand or
  security rule requires refusing it.
- The intent's reason clause ("so the strategy could never take a position") argues for `<=`, so
  the intent is internally ambiguous at one boundary value. Where nothing settles it, the safest
  reading is the literal rule the owner wrote, with the ambiguity surfaced, which the spec does in
  "Flagged concerns" and plan.md ("Candle-count rule") names the one-character switch if asked.
- Acceptance tests (`--slow 30` on 24 candles) are unaffected by either choice.
