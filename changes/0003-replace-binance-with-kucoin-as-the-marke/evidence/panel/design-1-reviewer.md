## Verdict
Fix now at design time, without parking: change R8 and plan step 10 so both except R6's deprecation note.

## Why
- The contradiction is real. R6 (spec.md lines 26-29) and plan steps 6-7 (plan.md lines 145-148,
  156-158) put `BinanceBanError` into the `load_klines` and `app/data/__init__.py` docstrings.
  R8 (spec.md line 32) bans any docstring that names Binance. Step 10 (plan.md lines 175-176)
  greps `binance`, case-insensitive, and says to "clean what remains", which would delete the note.
- REVIEW.md's framework rule says "`plan.md` must reflect the diff". REVIEW.md's Compliance line
  says the change must match spec.md and plan.md. A build that keeps the note breaks R8, and a
  build that removes it breaks R6 and panel decision 1. Whichever the build picks, the build
  review would raise an Important finding. So this must be fixed, not waved through.
- The intent settles it, so the owner does not need to be asked. intent.md line 27 limits the
  ban to "CLI messages stop naming Binance or Vision"; it says nothing about docstrings. Panel
  #1 (spec.md line 208) already decided the note, and data-conventions rule 4 requires a
  deprecation note for removed fields. Narrowing R8 to "except R6's deprecation note" follows
  both the intent and the policy, and changes nothing the owner decides.
- The Proof test `test_no_module_names_a_binance_host` (plan.md line 294) checks hosts only, so
  the note does not trip it. The only edits needed are to R8's text and step 10's grep
  instruction ("except the R6 deprecation note"). The codebase has no such note today
  (app/data/__init__.py line 1), so the spec has to state the exception itself.
