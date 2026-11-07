## Verdict
Close the concern as accepted: the reserve of 100 with the 60 s cap is a design choice within the intent, and no rule asks for more; it is not an Important finding.

## Why
- The intent (Rate limits) fixes only the mechanism: pause on `gw-ratelimit-remaining` and
  `gw-ratelimit-reset`, wait 1 s when the headers are absent, keep the 429/5xx retries. It names
  no threshold, so a number has to be picked. The spec picks one and flags it as a guess, which
  is what the spec template asks for. Spec R5 and plan step 3 implement exactly that mechanism.
- No policy covers rate-limit thresholds. coding-standards, security-baseline and
  data-conventions say nothing about pacing. REVIEW.md keeps Important for findings that break
  behaviour, leak data or breach a policy. This choice does none of these.
- Behaviour is safe either way. A reserve that is too low costs at most a 429, and the
  `with_retries` loop absorbs it (it exists today, keeps its 1/2/4 s delays and its 60 s
  Retry-After cap, and R4 keeps both). A reserve that is too high only costs speed. Plan Risks
  (line 189) records this.
- The numbers hold up against the measured facts in intent.md: a pool of 2000 per 30 s at 3 per
  call leaves 100 as about 33 calls of headroom. `reset` is in ms within a 30 s window, so
  `min(reset/1000, 60)` never cuts a real reset short. The cap only guards against a hostile or
  broken header, which fits security-baseline's rule to treat input as untrusted.
- Side note, not a reason to park: today's `WeightPacer` pauses at 80% used (a 20% reserve),
  and 100 out of 2000 is 5%. The owner can raise `RATE_LIMIT_RESERVE` (one constant) if they run
  other clients on the same IP. test_rate_limit_pacer tests the value both above and below the
  reserve.
