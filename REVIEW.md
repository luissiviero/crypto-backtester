# Review instructions

<!-- Structure from the article's REVIEW.md example (p.34); the rules under "Framework
rules" come from the build guide (steps 7, 15, 25, 26) and OPERATING_MODEL section 3. -->

## Passes
Run three passes and tag each finding with its pass:
- Bugs: logic errors, broken edge cases, subtle regressions
- Security: injection risks, authentication gaps, PII in logs, credentials in the diff
- Compliance: the change matches `changes/<id>-<slug>/spec.md`, `plan.md` and our design
  principles

## What Important means here
Reserve Important for findings that would break behavior, leak data or breach a policy.
Style and naming are nits.

## Cap the nits
Report at most five nits per review; summarize the rest as a count.

## Framework rules (each is an Important finding)
- The diff must not touch `.claude/**`, `CLAUDE.md`, `REVIEW.md`, `sdlc.yaml` or
  `policies/**` unless the change is the framework itself (its intent.md says so).
- In a fix-type change (`change_type: fix` in status.yaml) the diff must not modify test
  files that existed before the fix; the failing test written first is the proof.
- `plan.md` must reflect the diff: files that change, order of work, risks, proof. A diff
  that departs from the plan without a plan.md update in the same commit is non-compliant.
- Each added skip marker the gate's `ratchets` check listed at the deploy gate
  (`evidence/gate-deploy.json`'s `details.skip_markers`) must be declared in `plan.md` or
  explained in the PR; an undeclared one quietly narrowing what the suite actually runs is
  non-compliant.
- The second occurrence of the same finding across changes produces a one-line entry in
  `CLAUDE.md` under "Things Claude gets wrong", proposed in the review for the owner (the
  framework counts repeats in `changes/.review-seen.json` and writes the proposal; a
  repeated finding keeps its own severity).
- Flag when the change has made `CLAUDE.md` outdated.

## Do not report
Generated files, anything under `changes/*/evidence/`, and anything CI already enforces
(formatting, import order, lint rules that run in the hooks).
