## Verdict
Keep the design: add `"app.backtest"` to `[tool.setuptools] packages` and close the concern as decided.

## Why
- Fact: `pyproject.toml` lists packages explicitly (`packages = ["app", "app.data"]`), so
  setuptools ships only those two; a regular (wheel) install would ship `app/backtest/` without
  its code, and `from app.backtest import ...` would raise ImportError.
- REVIEW.md, "What Important means here": a finding that "would break behavior" is Important.
  Leaving the line out ships a package whose headline feature cannot be imported once installed.
  The editable install in `commands.setup` hides this from CI and the tests, so no gate would
  catch it later.
- The intent's line 72 ("`pyproject.toml` ... need no change") sits under "no new dependency":
  its purpose is no new runtime dependency and no CI change. The edit adds no dependency
  (`dependencies` is untouched) and leaves `ci.yml` alone, so the goal holds. Only the wording
  was wrong about the package list.
- `pyproject.toml` is not a guardrail file (REVIEW.md framework rules; CLAUDE.md lists only
  `.claude/**`, `CLAUDE.md`, `REVIEW.md`, `sdlc.yaml` and `policies/**`). The version stays `0.1.0` (spec R19).
- REVIEW.md, "plan.md must reflect the diff": plan.md already names the file (Files, step 5,
  Risks), so the edit is compliant. If the owner rejects it, plan.md says to drop step 5.
- Safest reading: the one-line edit is low risk, since step 6's setup and test run catches a
  typo. A silently broken install is the real failure, so the spec should flag the deviation
  from the intent for the owner rather than follow the intent's literal wording.
