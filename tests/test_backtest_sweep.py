"""Tests for the SMA crossover sweep: the module on frames built by hand, and
`python -m app.backtest sweep` offline, driven through main(argv, fetch=stub)."""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

import polars as pl
import pytest
from kucoin_stub import HOUR_MS, SPOT_1H, KuCoin, utc

import app.backtest.__main__ as cli
from app.backtest.__main__ import SMA_NOTE, SWEEP_WARNING, main
from app.backtest.engine import run_backtest
from app.backtest.strategy import sma_cross_positions
from app.backtest.sweep import count_pairs, pairs, sweep
from app.data import load_klines

DAY = "2026-10-01"
HEADERS = ("fast", "slow", "total return", "max drawdown", "trades", "win rate", "time in market")
VARYING = [10, 12, 11, 14, 13, 9, 8, 12, 15, 14, 16, 11, 10, 13, 17, 18, 14, 12, 15, 19]


def _frame(closes: Sequence[float]) -> pl.DataFrame:
    prices = pl.Series(closes, dtype=pl.Float64)
    return pl.DataFrame({"open_time": list(range(len(closes))), "open": prices, "close": prices})


def test_count_pairs_counts_kept_and_skipped() -> None:
    assert count_pairs([5, 10, 20], [30, 50, 100]) == (9, 0)
    assert count_pairs([5, 50], [10, 50]) == (2, 2)
    assert pairs([5, 50], [10, 50]) == [(5, 10), (5, 50)]
    assert pairs([2, 3, 5], [5, 8]) == [(2, 5), (2, 8), (3, 5), (3, 8), (5, 8)]
    assert count_pairs([2, 3, 5], [5, 8]) == (5, 1)


def test_sweep_rows_match_run_backtest() -> None:
    frame = _frame(VARYING)
    grid = pairs([2, 3, 4], [5, 6, 8])
    rows = sweep(frame, grid, 0.001)
    assert sorted((row.fast, row.slow) for row in rows) == sorted(grid)
    for row in rows:
        positions = sma_cross_positions(frame, row.fast, row.slow)
        assert row.summary == run_backtest(frame, positions, fee=0.001).summary
    returns = [row.summary.total_return for row in rows]
    assert returns == sorted(returns, reverse=True)
    assert len(set(returns)) > 1


def test_sweep_ties_sort_by_fast_then_slow() -> None:
    frame = _frame([5.0] * 12)
    rows = sweep(frame, [(3, 8), (2, 8), (3, 5), (2, 5)], 0.001)
    assert [(row.fast, row.slow) for row in rows] == [(2, 5), (2, 8), (3, 5), (3, 8)]
    assert all(row.summary.total_return == 0.0 for row in rows)


def spot_day() -> KuCoin:
    kucoin = KuCoin()
    kucoin.add_spot(SPOT_1H)
    return kucoin


def run_sweep(kucoin: KuCoin, root: Path, *extra: str, days: tuple[str, str] = (DAY, DAY)) -> int:
    argv = ["sweep", "btc-usdt", "1h", *days, "--cache-dir", str(root), *extra]
    return main(argv, fetch=kucoin)


def expected_lines(grid: list[tuple[int, int]], skipped: int, fee: float) -> list[str]:
    frame = load_klines("BTC-USDT", "1h", DAY, DAY, cache=False, fetch=spot_day())
    rows = []
    for fast, slow in grid:
        summary = run_backtest(frame, sma_cross_positions(frame, fast, slow), fee=fee).summary
        rows.append((-summary.total_return, fast, slow, summary))
    rows.sort(key=lambda row: row[:3])
    cells = [
        (
            str(fast),
            str(slow),
            f"{summary.total_return:.2%}",
            f"{summary.max_drawdown:.2%}",
            str(summary.trade_count),
            f"{summary.win_rate:.2%}",
            f"{summary.time_in_market:.2%}",
        )
        for _, fast, slow, summary in rows
    ]
    widths = [max(len(cell) for cell in column) for column in zip(HEADERS, *cells)]
    table = [
        "  ".join(cell.rjust(width) for cell, width in zip(line, widths))
        for line in (HEADERS, *cells)
    ]
    hold = run_backtest(frame, [1] * frame.height, fee=fee).summary
    return [
        (
            f"BTC-USDT 1h spot, {DAY} .. {DAY}: {frame.height} candles; "
            f"sma-cross, {len(grid)} pairs tried, {skipped} skipped; fee {fee:.2%}"
        ),
        SMA_NOTE,
        *table,
        f"{'buy and hold':<14}{hold.total_return:>8.2%}",
        SWEEP_WARNING,
    ]


def table_pairs(lines: list[str]) -> list[tuple[int, int]]:
    return [(int(line.split()[0]), int(line.split()[1])) for line in lines[3:-2]]


def assert_refused(capsys: pytest.CaptureFixture[str], message: str) -> None:
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith(f"error: {message}")
    assert len(captured.err.splitlines()) == 1


# fasts 2, 3, 5 by slows 5, 8, 12, 24 on 24 candles: (5, 5) is skipped by the order rule and
# the three pairs with slow 24 by the candle count, so eight pairs are tried and four skipped.
GRID = [(2, 5), (2, 8), (2, 12), (3, 5), (3, 8), (3, 12), (5, 8), (5, 12)]
LISTS = ("--fast", "2,3,5", "--slow", "5,8,12,24")


@pytest.mark.usefixtures("clock")
def test_sweep_prints_table(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run_sweep(spot_day(), tmp_path, *LISTS) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines == expected_lines(GRID, 4, 0.001)
    assert lines[2] == "fast  slow  total return  max drawdown  trades  win rate  time in market"
    assert all(len(line) == len(lines[2]) for line in lines[3:-2])
    assert lines[-1] == (
        "The best pair on past data is often luck: check it on another date range before "
        "trusting it."
    )


@pytest.mark.usefixtures("clock")
def test_sweep_skips_and_counts_pairs(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run_sweep(spot_day(), tmp_path, *LISTS, "--fee", "0") == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].endswith("24 candles; sma-cross, 8 pairs tried, 4 skipped; fee 0.00%")
    assert sorted(table_pairs(lines)) == GRID
    assert lines == expected_lines(GRID, 4, 0.0)


@pytest.mark.usefixtures("clock")
def test_sweep_tries_repeats_once(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run_sweep(spot_day(), tmp_path, "--fast", "3,2,3,2", "--slow", "8,5,8") == 0
    repeated = capsys.readouterr().out
    assert run_sweep(spot_day(), tmp_path, "--fast", "2,3", "--slow", "5,8") == 0
    assert repeated == capsys.readouterr().out
    assert repeated.splitlines() == expected_lines([(2, 5), (2, 8), (3, 5), (3, 8)], 0, 0.001)


@pytest.mark.usefixtures("clock")
def test_sweep_loads_klines_once(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    loads: list[tuple[object, ...]] = []

    def counting_load(*args: object, **kwargs: object) -> pl.DataFrame:
        loads.append(args)
        return load_klines(*args, **kwargs)

    monkeypatch.setattr(cli, "load_klines", counting_load)
    swept = spot_day()
    assert run_sweep(swept, tmp_path / "sweep", *LISTS) == 0
    assert len(loads) == 1
    single = spot_day()
    argv = ["run", "btc-usdt", "1h", DAY, DAY, "--cache-dir", str(tmp_path / "run")]
    assert main([*argv, "--fast", "3", "--slow", "5"], fetch=single) == 0
    assert swept.calls == single.calls != []


@pytest.mark.usefixtures("clock")
@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["BTC/USDT", "1h", DAY, DAY], "invalid spot symbol"),
        (["BTC-USDT", "7m", DAY, DAY], "unknown interval"),
        (["BTC-USDT", "1h", "2026-10-04", "2026-10-04"], "end 2026-10-04 is in the future"),
        (["BTC-USDT", "1h", "2026-10-02", DAY], "start 2026-10-02 is after end 2026-10-01"),
        (["BTC-USDT", "1h", "2026-30-09", DAY], "invalid start date"),
    ],
)
def test_sweep_refuses_bad_request(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], argv: list[str], message: str
) -> None:
    kucoin = spot_day()
    assert main(["sweep", *argv, "--cache-dir", str(tmp_path)], fetch=kucoin) == 2
    assert_refused(capsys, message)
    assert kucoin.calls == []


@pytest.mark.usefixtures("clock")
def test_sweep_refuses_bad_market(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    kucoin = spot_day()
    with pytest.raises(SystemExit) as exited:
        run_sweep(kucoin, tmp_path, "--market", "margin")
    assert exited.value.code == 2
    assert "argument --market: invalid choice: 'margin'" in capsys.readouterr().err
    assert kucoin.calls == []


@pytest.mark.usefixtures("clock")
@pytest.mark.parametrize(
    ("extra", "message"),
    [
        (
            ["--fast", ""],
            "--fast is empty: pass comma-separated whole numbers, for example 5,10,20",
        ),
        (
            ["--slow", " "],
            "--slow is empty: pass comma-separated whole numbers, for example 30,50,100",
        ),
        (["--fast", "5,,10"], "fast '' is not a whole number of at least 1"),
        (["--fast", "x"], "fast 'x' is not a whole number of at least 1"),
        (["--fast", "1.5"], "fast '1.5' is not a whole number of at least 1"),
        (["--fast=-5,10"], "fast -5 is not a whole number of at least 1"),
        (["--fast", "-5"], "fast -5 is not a whole number of at least 1"),
        (["--slow", "0"], "slow 0 is not a whole number of at least 1"),
        (["--slow", "30,x,50"], "slow 'x' is not a whole number of at least 1"),
    ],
)
def test_sweep_refuses_bad_lengths(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], extra: list[str], message: str
) -> None:
    kucoin = spot_day()
    assert run_sweep(kucoin, tmp_path, *extra) == 2
    assert_refused(capsys, message)
    assert kucoin.calls == []


@pytest.mark.usefixtures("clock")
def test_sweep_refuses_two_word_negative_list(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # argparse refuses `--fast -5,10` itself on Python 3.10 to 3.13; on 3.14 the command does.
    kucoin = spot_day()
    try:
        code = run_sweep(kucoin, tmp_path, "--fast", "-5,10")
    except SystemExit as exited:
        code = exited.code
    assert code == 2
    assert capsys.readouterr().out == ""
    assert kucoin.calls == []


@pytest.mark.usefixtures("clock")
@pytest.mark.parametrize(
    ("fee", "message"),
    [
        ("abc", "fee 'abc' is not a number: pass a proportional fee, for example 0.001"),
        ("1.5", "fee 1.5 is out of range: it must be at least 0 and below 1"),
    ],
)
def test_sweep_refuses_bad_fee(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], fee: str, message: str
) -> None:
    kucoin = spot_day()
    assert run_sweep(kucoin, tmp_path, "--fee", fee) == 2
    assert_refused(capsys, message)
    assert kucoin.calls == []


@pytest.mark.usefixtures("clock")
def test_sweep_refuses_empty_grid(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    kucoin = spot_day()
    assert run_sweep(kucoin, tmp_path, "--fast", "50", "--slow", "10,20") == 2
    assert_refused(capsys, "no pair has fast below slow: pass a --fast value below a --slow value")
    assert kucoin.calls == []


@pytest.mark.usefixtures("clock")
def test_sweep_refuses_grid_over_cap(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    kucoin = spot_day()
    fasts = ",".join(str(length) for length in range(1, 22))
    slows = ",".join(str(length) for length in range(22, 43))
    assert run_sweep(kucoin, tmp_path, "--fast", fasts, "--slow", slows) == 2
    assert_refused(
        capsys,
        "the grid has 441 pairs with fast below slow, more than 400: "
        "pass shorter --fast or --slow lists",
    )
    assert kucoin.calls == []


@pytest.mark.usefixtures("clock")
def test_sweep_refuses_range_with_every_pair_skipped(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_sweep(spot_day(), tmp_path) == 2
    assert_refused(
        capsys,
        "the range has 24 candles, not more than any slow length with a smaller fast: no pair "
        "could take a position; widen the dates or lower --slow",
    )


@pytest.mark.usefixtures("clock")
def test_sweep_defaults_give_nine_pairs(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    kucoin = KuCoin()
    kucoin.add_spot_synthetic(utc(2026, 9, 28), 120, HOUR_MS)
    assert run_sweep(kucoin, tmp_path, days=("2026-09-28", "2026-10-02")) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].endswith("120 candles; sma-cross, 9 pairs tried, 0 skipped; fee 0.10%")
    assert sorted(table_pairs(lines)) == [(f, s) for f in (5, 10, 20) for s in (30, 50, 100)]


def test_run_help_keeps_option_order(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exited:
        main(["run", "--help"])
    assert exited.value.code == 0
    options = re.findall(r"^  (--[a-z-]+)", capsys.readouterr().out, flags=re.MULTILINE)
    assert options == ["--market", "--fast", "--slow", "--fee", "--cache-dir"]
