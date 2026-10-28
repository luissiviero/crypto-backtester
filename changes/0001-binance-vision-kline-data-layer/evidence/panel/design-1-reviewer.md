## Verdict
Accept the design as written (close the concern): `data-api.binance.vision` as the fixed spot default and 451/other-4xx refusals reported as gaps with the status.

## Why
- The intent names both spot hosts as acceptable (intent "Affected users and systems": "`api.binance.com`,
  or the market-data-only `data-api.binance.vision`"), so the choice stays inside the owner's own list;
  the mirror is the one refused in fewer regions (intent Open questions), the safer default.
- The refusal behaviour is exactly the intent's proposal ("report those days as gaps, with the
  reason"), and it satisfies the intent's hard rule "never a silently short frame": refused days
  surface through `KlineGapError.gaps` (spec Design § Sources, § Gaps; R5).
- 418 is carved out and still stops the run (spec § Sources; intent "Downloads"), so treating other
  4xx as gaps cannot hide an IP ban, honouring the constraint "must never get the owner's IP banned".
- No switch is not a defect by the rules: the intent asks for no host option, and adding one
  unasked would widen scope (coding-standards rule 3). A fixed host set also keeps
  security-baseline rule 7 tight: the runtime calls only the three hosts spec § Sources lists.
- REVIEW.md "What Important means": nothing here breaks behaviour, leaks data or breaches a policy;
  the adversarial review (evidence/adversarial-review-design.json) found no reason against it either.
- Residual, for the owner only: if a spot fallback to `api.binance.com` is ever wanted, it is a
  small later change; it does not block this design.
