# changes/ — one folder per change

Convention (OPERATING_MODEL section 8; decision 10): `changes/<id>-<slug>/` where `<id>` is a
four-digit sequence (`0000` is the framework's own installation) and `<slug>` is the
kebab-case title.

| File | Written in | By |
|---|---|---|
| `intent.md` | intent | `/sdlc-intent`, with the owner (article p.10–11 template) |
| `spec.md` | design | `/sdlc-design` (B3) |
| `plan.md` | design, the planning run | `/sdlc-design` (B3); kept in sync in build by the plan-sync hook |
| `evidence/` | build, test, deploy | `verifier.md` (verifier agent), `test.log` · `build.log` · `lint.log` · screenshots (the test run, B3), `adversarial-review-<phase>.json` (adversarial reviewer), `review-findings.json` (review pass, B3), `gate-<phase>.json` and `run-<phase>.json` (the gate; `<phase>` is the phase's name, e.g. `gate-build.json`) |
| `status.yaml` | every phase | `plugin/state` — phase (or `abandoned`: the PR was closed without a merge), change type, gate result, parked reason, iteration count, the actors of the owner's un-park labels and of the runbook Go |
| `evidence/detection.json`, `evidence/proposal.json`, `evidence/runbook-<name>.json` | maintain | the detection script (the finding: metric, tier, rule, the numbers), the diagnosis (`/sdlc-maintain`: the proposed route) and the dispatcher (what the runbook did); an incident change is filed by the detection script with `entry_route: incident` and stays at phase `maintain` until its intent PR is merged (= the intent gate) |
| `mock/` | intent or design, optional | the exported design mock for front-end work (build guide step 34): the visual target the build and test phases compare screenshots against, named by `spec.md`'s `Mock:` line; project content, committed with the intent or the spec. Example screens that are not a target go in the intent's Examples/References |

Phases: `intent`, `design`, `build`, `test`, `deploy`, `maintain` (the letters `a` to `f` of
older changes are read as these names). Branches: `sdlc/<id>/intent` (intent PR),
`sdlc/<id>/design` (spec+plan PR), `sdlc/<id>/build` (build PR, kept open through test and
review); since plugin 1.0.48 a run works only on these (a letter branch, `sdlc/<id>/c`, is
history).
Labels: `sdlc:<phase>-ready` (waiting at a human gate, e.g. `sdlc:design-ready`),
`sdlc:release-approved` (the release manager's release
approval on a declared production), `sdlc:needs-human` (parked); the owner's un-park verbs
`sdlc:reset-iterations`, `sdlc:unlock-tests` (read and removed by the next fix round). A
risk-list hit parks nothing: it is a line of the PR's "Needs your close look" banner, and
your merge accepts it, at the deploy gate your approving review as the code owner (decisions 35 and 36; `sdlc:accept-risk` retired). A "Request changes" review on any of these PRs starts a fix round; closing
one without merging abandons the change. The maintain phase: an incident intent PR (head
`sdlc/<id>/intent`, title `maintain(<id>): …`) carries `sdlc:maintain-ready` and `sdlc:triage`; the service owner's
triage is the gate (merge = fix now, label `sdlc:schedule` = later, close with a comment =
dismiss, recorded in `changes/.dismissed.json` through a dismissal PR); `sdlc:go` on it runs
the runbook the diagnosis proposed when its route needs a person (read and removed once).
The post-mortem of a shipped incident fix lives in `lessons/` and its eval in `evals/cases/`.

Nothing here is edited by hand except `intent.md` during the intent phase. The repo is the source
of truth; an external tracker holds only the issue number ↔ commit SHA link (decision 9), the
issue number goes into `status.yaml: external_ref`.
