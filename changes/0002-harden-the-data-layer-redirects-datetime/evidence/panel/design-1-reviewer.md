## Verdict
Keep `0.1.0` as the spec decides; the concern is not Important and may close as accepted, with the bump left to the owner.

## Why
- No rule requires a version bump. `CLAUDE.md` Conventions only requires that `__version__`
  in `app/__init__.py` and `version` in `pyproject.toml` "keep the two in step"; both read
  `0.1.0` today and the spec (line 89) keeps both unchanged, so that rule holds.
- The policy skills say nothing about package versioning: coding-standards rule 5 is about
  dependency pins (not bumping them as a side effect), and data-conventions rule 4 is about
  event/API contract versions. Neither applies. There is no `policies/<name>.md` override
  (only `policies/README.md`) and no project skill override under `.claude/skills/`.
- REVIEW.md reserves Important for what would "break behavior, leak data or breach a
  policy". An unchanged version string does none of these. `sdlc.yaml: deploy.action` is
  `none`, so nothing is published under a stale version.
- The intent does not ask for a bump, and the spec says the public API, CLI and outputs are
  unchanged. A patch bump is therefore optional, not required.
- Compliance holds: plan.md line 117 records the rejected alternative ("Bump the version to
  0.1.1 ... kept at 0.1.0"), so plan and spec agree and the build diff must leave both
  version lines alone.
- Safest reading: change nothing, which follows the scope rule of doing only what the intent
  asks. If the owner wants each change versioned, a `0.1.1` bump in both files is a
  two-line edit at the deploy gate.
