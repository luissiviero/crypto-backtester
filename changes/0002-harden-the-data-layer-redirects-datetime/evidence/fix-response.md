# Fix round 3 — change 0002, phase deploy (PR #11)

`bump-iteration` reported iteration 3 against a cap of 2, so this round changed nothing in the
code. The trigger, issuecomment-6668928989, was already applied in round 2 (f62fcfd).

## Requests

- The gate's park (`commands: not green: lint (exit 1)`): **not applied: iteration cap
  reached.**
  Diagnosis, from `evidence/lint.log`: the runner's ruff is 0.17.4 (unpinned), and it reports
  RUF100 (unused `noqa`, DTZ001 is not enabled in 0.17.x) on the three `# noqa: DTZ001`
  comments f62fcfd added at tests/test_data.py:540, 563 and 565. CI pins ruff 0.16.9, which
  needs those comments. With these comments, no single version of the test file passes both
  rulesets.
  Proposed edit (not made): on each of the three lines, change `# noqa: DTZ001` to
  `# noqa: DTZ001, RUF100`. Ruff does not report RUF100 on a directive that lists RUF100,
  so the line passes both 0.16.9 and 0.17.4. Line 540, the parametrize value, stays short.
  The two `clear_cache` lines (563 and 565) grow from 100 and 98 characters to 108 and 106,
  so each call needs to wrap over several lines to stay within the 100-character limit. The other option is to
  align the ruff that the runner's targets use with the CI pin (`ruff==0.16.9`). The setup
  command is in `sdlc.yaml`, and only you can edit that file.

## What I need from you

1. Choose one fix: the `# noqa: DTZ001, RUF100` edit (with the two `clear_cache` calls
   wrapped), or pinning `ruff==0.16.9` in `sdlc.yaml: commands.setup`, which you edit.
2. Add the `sdlc:reset-iterations` label so another round can apply the edit.

## Not applied by the collector

- luissiviero, https://github.com/luissiviero/crypto-backtester/pull/11#pullrequestreview-5791049725
  — not applied: applied by an earlier round
- luissiviero, https://github.com/luissiviero/crypto-backtester/pull/11#issuecomment-6668908102
  — not applied: applied by an earlier round
- luissiviero, https://github.com/luissiviero/crypto-backtester/pull/11#issuecomment-6668928989
  — not applied: applied by an earlier round
