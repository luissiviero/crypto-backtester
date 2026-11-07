## Verdict
Accept the spec's decision (leave argparse's refusal, test with `--fast=-5,10`) as a nit, not an Important finding; only correct the aside about `run --fast -5`.

## Why
- Fact: the behaviour depends on the Python version, as the spec says. On 3.10-3.13 argparse's
  `_negative_number_matcher` is `^-\d+$|^-\d*\.\d+$`, so `-5,10` looks like an option and gets
  `error: argument --fast: expected one argument`. On 3.14 (this runner: 3.14.4, matcher
  `-\.?\d`, prefix match) `-5,10` reaches the command and gets the R4 message.
- REVIEW.md "What Important means": nothing breaks. The input is still refused with exit 2, an
  `error:` line on stderr and nothing on stdout (R12), before any fetch, so no backtest runs on a
  bad length. No data leaks and no policy is breached: security-baseline rule 2 (validate
  before use) holds, since argparse refuses it first. ux-and-brand rule 4 is only weakened in
  argparse's own standard form, which is also how `run` handles its argparse errors
  (`--market`, which the spec's Acceptance already says "exits 2 through argparse").
- Rewriting argv would add code and risk to `run`'s shared parser, against R13 and
  coding-standards rule 7. The intent asks for no such thing.
- The test uses `--fast=-5,10` (plan.md lines 103-104, 129, 167), which reaches the command on
  every version from 3.10 up, so the proof does not depend on the version.
- Correction (nit): "`run` has the same behaviour for `--fast -5` on the versions where
  argparse reads it as an option" is wrong. `-5` matches the negative-number pattern on every
  version, so `run` always gets it as a value. Only the comma-list form differs (the
  adversarial review says the same). The build can fix the wording; the decision stands.
