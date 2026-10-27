# policies/ — the owner's policy sources

<!-- Written by /sdlc-init (ROADMAP R27; article p.21: "One policy with a named owner and a
written source of truth"). Project content, and a guardrail path (decision 40): a run never
edits the policy that judges it. -->

One file per policy skill of the SDLC plugin, written by the owner in their own words, with
no required headings:

| File | Read by the skill |
|---|---|
| `policies/coding-standards.md` | `coding-standards` |
| `policies/security-baseline.md` | `security-baseline` |
| `policies/data-conventions.md` | `data-conventions` |
| `policies/ux-and-brand.md` | `ux-and-brand` |
| `policies/definition-of-done.md` | `definition-of-done` |

The UX file was `policies/ux-conventions.md`, read by the skill `ux-conventions`, before
plugin 1.0.46 (R45 row 80); since 1.0.48 the old file is not read: rename it in a commit of
your own.

**How a run reads them.** Each skill reads its file first. Where the file and the skill
differ, the file wins, over a project override in `.claude/skills/<name>/` too; a rule of the
skill the file does not mention still applies. A missing file means the skill's generic
rules alone, so this folder starts with this README only, and no file is a stub: a stub
would read as a policy.

**How they change.** The owner writes or edits a file in a pull request of their own, as for
`CLAUDE.md` and `REVIEW.md`; Claude may draft one in a session the owner opens, never in a
run. The owner's merge is the policy owner's sign-off (article p.22, step 5), and the next
run reads the new text with no plugin version bump. The protected-path hook, the shell guard,
the gate, the runner and, in CI, the deny rules and the sandbox each refuse a run's edit here.

**The record.** The spec header of each change names the commit of every source that existed
when the design ran, so the record shows which policy text judged the change.
