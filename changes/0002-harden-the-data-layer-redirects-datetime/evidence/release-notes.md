# Release notes — change 0002: Harden the data layer: redirects, datetime bounds, Windows tzdata

## In plain words

*Written by the model from the diff and the plan; every section below is generated from files and git.*

Downloads from Binance now go only to the HTTPS address the data layer asked for. If a server answers with a redirect, the download no longer follows it. It reports the redirect as an error, and any address that is not https:// is refused before a connection opens. Passing a datetime where a date is expected now gives a clear error instead of quietly picking a day, because a time and time zone do not say which UTC day is meant. On Windows, installing the project with pip install -e . now also installs tzdata, so time-zone handling works there. Until the owner updates the Setup line in CLAUDE.md, that line does not install it yet.

<!-- sdlc:plain-words describes b320e7cec98e0e59f268afb40a663e31c66ab26f -->

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

## Evidence

test green, build green, lint green, verifier.md present, 0 screenshot(s)

## Review findings

2 Important, 3 nits

## Links

- [intent.md](../intent.md)
- [spec.md](../spec.md)
- [plan.md](../plan.md)
