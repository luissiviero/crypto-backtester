# Fix round 2 — change 0002, phase deploy (PR #11)

Iteration 2 of 2. The tests were unlocked by luissiviero (`sdlc:unlock-tests`) before this
round.

## Requests

- luissiviero (OWNER), https://github.com/luissiviero/crypto-backtester/pull/11#pullrequestreview-5791049725
  — "add `# noqa: DTZ001` at tests/test_data.py:538, 559 and 561, parametrize values on
  separate lines, change nothing else": **applied in f62fcfd.** The `moment` parametrize
  list now has one value per line, with `# noqa: DTZ001` on the naive `datetime(2024, 1, 1)`,
  and the two `clear_cache` lines have the same comment (100 and 98 characters). Nothing
  else changed.
- luissiviero (OWNER), https://github.com/luissiviero/crypto-backtester/pull/11#issuecomment-6668908102
  — "apply the planned edit in evidence/fix-response.md as written, and nothing else":
  **applied in f62fcfd**: the same edit as above, exactly as round 1 planned it.
- luissiviero (OWNER), https://github.com/luissiviero/crypto-backtester/pull/11#issuecomment-6668928989
  — the same comment again: **applied in f62fcfd**, with the same edit.

Checks on f62fcfd: `python -m pytest` reported 89 passed. Ruff 0.16.9, the version CI pins,
installed in a temp directory, reported `ruff check .`: All checks passed!. Running
`python -m compileall -q app tests scripts` printed nothing. The sandbox mounts `framework/`
read-only, so `compileall .` can't write `__pycache__` there; that is not a code error.

Note on ruff versions: the local ruff 0.17.4 (unpinned) reports RUF100 (unused noqa,
DTZ001 not enabled there) on these three comments, and the edit-time formatter hook strips
them with `ruff check --fix`. So the edit was written with a one-shot Python replacement
rather than the Edit tool. CI pins 0.16.9, which needs the comments. If the pin moves to
0.17.x, these three comments will need to come out again.

## Not applied by the collector

None.
