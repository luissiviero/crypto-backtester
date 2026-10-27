# lessons/ — the incident record

<!-- Written by /sdlc-init (build guide step 36; article p.49: the diagnosis "writes the
post-mortem to a version-controlled lessons file that future investigations can read").
Project content: the fix of an incident appends a lesson here; the plugin only creates the
folder, this README and the generated index. -->

One file per incident, **written when its fix ships** (the deploy run of a change whose
entry route is `incident`, `/sdlc-deploy` step 0b), and **read before any diagnosis** (the
maintain run of `/sdlc-maintain` reads `lessons/index.md` first, then only the lessons its
tags name): the second incident of a class is cheaper than the first only if the first was
written down. The file rides in the fix PR and is reviewed like any other file.

## Naming
`lessons/<yyyy-mm>-<slug>.md` — the month the fix shipped and the incident change's slug
(the article's own example, p.49: `lessons/2026-06-checkout-cache.md`). One incident, one
file; a repeat of the same class gets its own file that cites the earlier one with
`supersedes` (which also retires the earlier file in the same commit).

## Shape
```markdown
---
type: "Lesson"
title: "<title of the incident change>"
description: "<one sentence, in the metric's terms>"
tags:
  - <class>          # your own kebab-case word for what broke, e.g. flaky-test
  - <metric>
  - <runbook>        # omitted when no runbook ran
change: "<id>"
detected:
  at: "<ISO timestamp>"
  metric: "<metric>"
  tier: <2 or 3>
  rule: "<the rule that fired>"
fixed:
  pr: <build PR number>
runbook: "<the route that ran>"   # omitted when no runbook ran
supersedes: "<earlier lesson's file name>"  # omitted unless this repeats that lesson's class
generated:
  by: "sdlc-plugin/<version>"
  at: "<ISO timestamp>"
status: "stable"   # or "retired" — set only by the owner or a later superseding lesson
stale_after: "<ISO date>"  # generated.at + 12 months, or sdlc.yaml: lessons.stale_after_months
sources:
  - id: "detection"
    resource: "evidence/detection.json"
  - id: "run-1"
    resource: "<the failed run's URL>"
  - id: "eval"
    resource: "evals/cases/<id>-<slug>/"
  - id: "fix-pr"
    resource: "<the build PR>"
---

## What happened
<the anomaly as the detection record and the diagnosis saw it; the run URLs[^detection]>

## Root cause
<what was actually wrong, in one paragraph; what the diagnosis got wrong, if anything>

## Fix
<what changed and where; the runbook that ran, if one did, and whether it was the right
call[^fix-pr]>

## Prevention
<the eval case added[^eval], the band or the test that would have caught it earlier, the
CLAUDE.md line proposed, if any>

[^detection]: evidence/detection.json
[^eval]: evals/cases/<id>-<slug>/
[^fix-pr]: the build PR
```

One `run-<n>` per failed run `evidence/detection.json` lists; a scan-filed incident has no
failed run and so no `run-<n>` source.

Every nested field (`detected`, `fixed`, `generated`, each item of `sources`) is written in
block style, never a flow mapping (`{a: b}` — the reader, `plugin/state/yamlish.py`, refuses
one); `title` and `description` are always double-quoted, since an unquoted scalar is
truncated at ` #`, the same rule `status.yaml` and `sdlc.yaml` already live with. A footnote
(`[^id]`) ties a sentence of the body to one of `sources`'s entries by its `id`; add one
wherever the body cites a source.

A file here with no frontmatter block (a lesson from before this shape, or a hand-written
one) is still read, never rejected: `plugin/lessons/index.py` lists it under `## Unsorted`
in the generated index, using its first heading as the title, and the maintain phase's diagnosis
still opens it.

## The generated index
`lessons/index.md` is written by `plugin/lessons/index.py build`, run in the same commit as
the lesson and the eval case, in `/sdlc-deploy` step 0b: a heading per first tag, normalised so a
spelling drift cannot split one class across two headings (`flaky-test`, `flaky_test` and
`Flaky Test` all become one `## flaky-test`); one line per lesson, newest first within a
heading; `## Retired` for a lesson whose `status` is `retired`, grouped there regardless of
its tags; `## Unsorted` last, for a file with no parsed frontmatter. A lesson past its
`stale_after` date carries `(stale)` at the end of its line — the file itself is never
rewritten when that date passes. Never edit `lessons/index.md` by hand: the next `build`
undoes a hand edit. `/sdlc-maintain` step 1 reads this file first and opens only the lessons
its tags name, falling back to reading every file under `lessons/` when the index is stale
or missing.

The eval case (article p.44 step 7: "When a fix ships, add an eval for the incident") is
the executable half of the lesson; this file is the half a person reads.
