# Fix round 1 — change 0002, phase deploy (PR #11)

Iteration 1 of 2.

## Requests

- luissiviero (OWNER), https://github.com/luissiviero/crypto-backtester/pull/11#pullrequestreview-5791049725
  — "add `# noqa: DTZ001` at tests/test_data.py:538, 559 and 561, parametrize values on
  separate lines, change nothing else": **not applied: the test files are locked.** Change
  0002 is a fix-type change, so `status.yaml: tests_locked` is `true` and `sdlc.yaml:
  test_paths` (`tests/**`) covers `tests/test_data.py`; the hook denies the edit and a run
  may not lift the lock itself. The request said to change nothing else, so I did not use a
  workaround such as a `per-file-ignores` entry in `pyproject.toml`. Nothing was changed in
  this round.

## Not applied by the collector

None.

## What I need from you

Unlock the tests so the next round can apply your request as written: add the label
`sdlc:unlock-tests` to PR #11 (or run
`python framework/plugin/state/cli.py unlock-tests --root . --id 0002` by hand), then start
the next round (a new "Request changes" review, an `@claude` comment, or a dispatch of
`sdlc-fix.yml`). The planned edit is this, and nothing else:

```python
@pytest.mark.parametrize(
    "moment",
    [
        datetime(2024, 1, 1),  # noqa: DTZ001
        datetime(2024, 1, 1, 23, tzinfo=timezone(timedelta(hours=-3))),
    ],
)
...
        cache.clear_cache("BTCUSDT", start=datetime(2024, 1, 1), cache_dir=tmp_path)  # noqa: DTZ001
...
        cache.clear_cache("BTCUSDT", end=datetime(2024, 1, 1), cache_dir=tmp_path)  # noqa: DTZ001
```

(The two `clear_cache` lines stay within 100 characters with the comment: 100 and 98.)
