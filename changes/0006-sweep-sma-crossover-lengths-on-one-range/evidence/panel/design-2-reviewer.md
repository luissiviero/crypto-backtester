## Verdict
Uphold the park: fix plan.md Order of work step 1 so the expectation reads `count_pairs([5, 50], [10, 50]) == (2, 2)` (or keep `(1, 3)` with inputs that give it, e.g. `([10, 50], [5, 20])`).

## Why
- spec.md R5: every distinct fast paired with every distinct slow; a pair is kept only when
  fast < slow. Grid of `[5, 50] x [10, 50]`: (5,10) kept, (5,50) kept, (50,10) skipped,
  (50,50) skipped, so (kept, skipped) = (2, 2).
- plan.md line 4-6's own method agrees: per fast, kept = len(slows) - bisect_right(slows, fast);
  fast 5 -> 2 - 0 = 2, fast 50 -> 2 - 2 = 0; total kept 2, skipped 4 - 2 = 2.
- So the planned test `== (1, 3)` (plan.md lines 42-43) fails against a count_pairs that meets
  R5 and the spec's Design ("kept = pairs with fast below slow", spec.md line 77-78).
- REVIEW.md "What Important means here": a finding that would break behavior is Important. The
  plan has the test written first; a build that bends count_pairs to pass it breaks R5, the
  skipped count in the run output and the R6 400-pair cap. A build that quietly changes the
  expectation departs from the plan without the review seeing it. Either way the wrong value
  is a defect in the design artifact, not taste.
- The fix is one line in plan.md, and the build phase is the wrong place to make it, so the
  park stands until the design artifact is corrected.
