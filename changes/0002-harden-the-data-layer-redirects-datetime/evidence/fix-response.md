# Fix round 4 — change 0002, phase deploy (PR #11)

The owner added `sdlc:reset-iterations` (luissiviero, 2026-11-05T21:41:10Z). `bump-iteration`
now reports iteration 1 of a cap of 2. `evidence/fix-requests.json` holds no new request, so
the one request this round carries is the park left by round 3.

## Requests

- The gate's park (`limits: iteration cap reached`, behind it
  `commands: not green: lint (exit 1)`). The owner chose the second option of round 3:
  `ruff==0.16.9` is pinned in `sdlc.yaml: commands.setup` (PR #12, e8ad833). It reached this
  branch through the runner's merge of origin/main (0d27039).
  **Applied with no code change:** the three `# noqa: DTZ001` comments stay as f62fcfd wrote
  them. In this session, with ruff 0.16.9: `python -m compileall -q .` printed nothing (exit 0),
  `python -m pytest` reported 89 passed, and `python -m ruff check .` reported
  `All checks passed!`. The runner runs the gate's targets again after this session.
  For this HEAD, `evidence/collect.py` reset the three logs to the deferred mark. The deploy
  review pass ran again (`review-findings.json`: 0 Important from the model, 2 nits). The
  framework's own Important finding on `tests/test_data.py` has signature c3b73ce1597573be,
  which panel decision 1 already settled. The adversarial verdict is `continue`
  (non-routine).

## For your follow-up guardrail PR (not applied: guardrail files)

Panel decision 2 quotes the new Setup line as `python -m pip install -e . pytest ruff` in two
places: `CLAUDE.md` and `sdlc.yaml: commands.setup`. Since PR #12, that line carries the pin,
so keep the pin in both edits: `python -m pip install -e . pytest ruff==0.16.9`. If the pin is
dropped, this park comes back. The adversarial reviewer and this round's review pass both
noted this.

## Not applied by the collector

- luissiviero, https://github.com/luissiviero/crypto-backtester/pull/11#pullrequestreview-5791049725
  — not applied: applied by an earlier round
- luissiviero, https://github.com/luissiviero/crypto-backtester/pull/11#issuecomment-6668908102
  — not applied: applied by an earlier round
- luissiviero, https://github.com/luissiviero/crypto-backtester/pull/11#issuecomment-6668928989
  — not applied: applied by an earlier round
