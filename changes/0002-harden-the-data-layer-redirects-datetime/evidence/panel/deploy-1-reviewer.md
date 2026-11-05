## Verdict
Dismiss the finding (false positive): the only edit to `tests/test_data.py` is the reproducing-test commit the rule itself requires, and it adds lines without modifying any existing test.

## Why
- REVIEW.md, framework rules: "In a fix-type change the diff must not modify test files that
  existed before the fix; the failing test written first is the proof." The rule protects the
  existing tests from being weakened, and it names the first-written failing test as the expected
  exception.
- `git diff --numstat main...HEAD -- tests/` gives `62 0 tests/test_data.py`: 62 lines added and
  0 removed. The additions are 6 imports and 4 new test functions appended after line 500. No
  existing test body, fixture or assertion changes.
- `git log main..HEAD -- tests/test_data.py` shows exactly one commit, `ff61d01 fix(0002):
  reproducing test`. It comes before the three fix commits (047eba1, 564845d, 1fe3f6f), so no fix
  commit touches the test file. That is the "test first, then locked" order the rule describes.
- intent.md "How to check it is done": "Regression tests for 1 and 2 are in
  `tests/test_data.py` ... As a fix-type change, the build run commits them first." plan.md line
  4 says "new regression tests ... no existing test changes", and Order of work step 1 says the
  same. The diff matches both, so the Compliance pass finds no departure from the plan.
- The rule cannot be read as "never add a test to an existing file" in a fix change, because the
  intent requires these tests to go in that file. Read that way, the rule would turn a breach
  into a policy-mandated outcome. REVIEW.md reserves Important for findings that break behavior,
  leak data or breach a policy. Nothing here does.
