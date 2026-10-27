## Verdict
Accept the deferral and close the concern as decided: keep one zstd-3 file per day; the build records the measurement as planned (plan step 10) and the owner judges the figure. Not an Important finding.

## Why
- No rule is breached. REVIEW.md keeps Important for what would "break behavior, leak data or
  breach a policy"; an unmeasured size figure does none of these. definition-of-done (design)
  allows open questions "answered or carried forward". This one is carried forward with a reason
  (spec.md lines 217-225).
- The intent itself fixes the layout. intent.md line 58 sets one `.parquet` per day, written
  atomically, and lines 65-66 cache closed REST days per day. Keeping daily files follows the
  intent. A month or year layout would contradict it and would need a later change.
- The design run could not measure. It writes no code, and `sandbox.allowed_domains` is empty
  (intent line 126), so it could not fetch real BTCUSDT 1m data. Moving the measurement to the
  build is the only feasible path, and spec Acceptance line 258 plus plan step 10 make it a
  checked deliverable (`evidence/storage-measurement.md`).
- zstd is the intent's own expected codec (line 162), and level 3 is the zstd default. That is
  a reasonable choice, open to tuning, and it changes no schema or behaviour.
- One residual gap: the intent said "BTCUSDT 1m", and synthetic random-walk data may compress
  differently from real candles (the adversarial review notes the same). Safest reading: the build's
  evidence file should state that the data is synthetic, so the owner weighs the figure knowing
  that. It may also add a second zstd level as a cheap comparison. Neither is needed to proceed.
