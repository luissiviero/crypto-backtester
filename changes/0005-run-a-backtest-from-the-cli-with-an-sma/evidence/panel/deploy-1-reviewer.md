## Verdict
Keep the one-line edit to tests/test_backtest.py and downgrade the finding from Important to a nit; recommend (not require) a spec.md note recording that R14 gives way to R1.

## Why
- The intent contradicts itself, and the spec carries the contradiction forward. Intent l.74-75 says "the strategy function joins the public API in `app/backtest/__init__.py`", and spec R1 and Acceptance ("`sma_cross_positions` is in `app.backtest.__all__`") require it. But `test_public_api` on main pins `__all__` to exactly five names, so R1 cannot pass unless that file changes, which intent l.80/87, R14 and the Acceptance line forbid. One requirement had to give way.
- REVIEW.md "What Important means here": Important is for findings that "break behavior, leak data or breach a policy". This edit only adds a name to an exact-set assertion. The test stays as strict as before, no assertion is weakened or skipped, and it breaks no behavior, leaks no data and breaches no policy skill.
- REVIEW.md framework rules: the test-file freeze applies only to `change_type: fix` changes (l.23-24). status.yaml says `change_type: feature`, so no framework rule is breached. The plan rule (l.25-26) is met: plan.md l.21-22 and l.115-125 record the departure, give the reason and describe the reverse path.
- The edit keeps the outcome the intent states (the strategy is public). The alternative (drop the name from `__all__`) would fail R1, an Acceptance line and the intent's Scope, which is a worse departure than the one-line test edit.
- What remains is a compliance nit: spec.md still states R14 without the exception. The owner sees it at this gate, so it does not block the merge.
