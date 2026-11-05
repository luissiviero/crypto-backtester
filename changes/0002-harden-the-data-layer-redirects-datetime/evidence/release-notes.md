# Release notes — change 0002: Harden the data layer: redirects, datetime bounds, Windows tzdata

## In plain words

*Written by the model from the diff and the plan; every section below is generated from files and git.*

This change makes the market-data layer safer and more predictable. Downloads no longer follow HTTP redirects, and only HTTPS addresses are opened, so a request cannot be quietly sent somewhere else. Passing a date-and-time where a plain date is expected, to a download or to a cache clear, now gives a clear error instead of a confusing type error or a wrong day. On Windows the package now installs the time-zone data it needs, so the test suite can pass there after an editable install.

<!-- sdlc:plain-words describes f62fcfdc31604835f46b6e80cb1817b65ce88fdd -->

## What changed

A download only ever talks HTTPS to the URL it asked for.

## Commits

- ff61d01 fix(0002): reproducing test
- 047eba1 build(0002): parse_date refuses a datetime
- 564845d build(0002): HTTPS-only opener that does not follow redirects
- 1fe3f6f build(0002): packaging: tzdata on Windows, named packages, ignore egg-info
- e4eb448 build(0002): gate (build) evidence
- 71ebd8f run(build): spend recorded; gate commands run after the session
- 06a096c test(0002): evidence
- 8d21e21 test(0002): gate (test) evidence
- a4940f4 run(test): spend recorded; gate commands run after the session
- 5719666 run(review): spend recorded
- 5282254 review(0002): panel decision 1
- b320e7c review(0002): panel decision 2
- 9b5871f review(0002): gate (deploy) evidence
- 81ecfeb run(deploy): spend recorded; gate commands run after the session
- 6172b37 fix(0002): round 1 parked, CI lint noqa request needs the test lock lifted
- 4256131 park: fix: the session ended without reaching its gate
- ee063ed owner labels applied: sdlc:unlock-tests
- f62fcfd fix(0002): noqa DTZ001 on the three deliberate naive datetimes in tests/test_data.py (CI lint, ruff 0.16.9)

## Evidence

test green, build green, lint green, verifier.md present, 0 screenshot(s)

## Review findings

2 Important, 3 nits

## Links

- [intent.md](../intent.md)
- [spec.md](../spec.md)
- [plan.md](../plan.md)
