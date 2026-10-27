# Intent: connect the SDLC framework
Author: owner. Change id: 0000. Entry route: idea.
Framework change: yes

## Problem
crypto-backtester has no shared process for taking a change from idea to production
with the agent doing the work and the owner judging at gates.

## Proposed outcome
The SDLC framework plugin `sdlc@sdlc-framework` v1.0.50 is installed:
one-command targets build=`python -m compileall -q .`,
test=`python -m pytest`, lint=`python -m ruff check .`, guardrail hooks and permissions
in place, `changes/` as the home of every change.

## Affected users and systems
The owner; this repository's CLAUDE.md, REVIEW.md, sdlc.yaml and .claude/settings.json.

## Constraints
Only the owner merges to main. No bypass-permissions mode. Guardrail files are protected
paths from this change on. A test that needs a service the CI runner does not start (a
database, a queue) is deselected until the owner adds the service to the phase workflows.
`policies/` starts empty but for its README: the owner's policy sources, one file per policy
skill, are the owner's to write (R27); until one exists, its skill applies its generic rules.

## Open questions
- Detection notes: none
