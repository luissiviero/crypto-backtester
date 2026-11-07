"""Offline tests for `python -m app.backtest run`, driven through main(argv, fetch=stub)."""

from __future__ import annotations

from pathlib import Path

import pytest
from kucoin_stub import SPOT_1H, KuCoin

from app.backtest.__main__ import SMA_NOTE, main
from app.backtest.engine import run_backtest
from app.backtest.strategy import sma_cross_positions
from app.data import load_klines
from app.data.http import HttpResponse

pytestmark = pytest.mark.usefixtures("clock")

DAY = "2026-10-01"


def spot_day() -> KuCoin:
    kucoin = KuCoin()
    kucoin.add_spot(SPOT_1H)
    return kucoin


def run(kucoin: KuCoin, root: Path, *extra: str, days: tuple[str, str] = (DAY, DAY)) -> int:
    argv = ["run", "btc-usdt", "1h", *days, "--cache-dir", str(root), *extra]
    return main(argv, fetch=kucoin)


def expected_lines(fast: int, slow: int, fee: float) -> list[str]:
    frame = load_klines("BTC-USDT", "1h", DAY, DAY, cache=False, fetch=spot_day())
    summary = run_backtest(frame, sma_cross_positions(frame, fast, slow), fee=fee).summary
    hold = run_backtest(frame, [1] * frame.height, fee=fee).summary
    return [
        (
            f"BTC-USDT 1h spot, {DAY} .. {DAY}: {frame.height} candles; "
            f"sma-cross fast {fast} slow {slow}; fee {fee:.2%}"
        ),
        SMA_NOTE,
        f"{'total return':<14}{summary.total_return:>8.2%}",
        f"{'max drawdown':<14}{summary.max_drawdown:>8.2%}",
        f"{'trades':<14}{summary.trade_count:>8}",
        f"{'win rate':<14}{summary.win_rate:>8.2%}",
        f"{'time in market':<14}{summary.time_in_market:>8.2%}",
        f"{'buy and hold':<14}{hold.total_return:>8.2%}",
    ]


def assert_refused(capsys: pytest.CaptureFixture[str], message: str) -> None:
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith(f"error: {message}")
    assert len(captured.err.splitlines()) == 1


def test_run_prints_summary_and_buy_and_hold(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(spot_day(), tmp_path, "--fast", "3", "--slow", "5") == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines == expected_lines(3, 5, 0.001)
    assert lines[0] == (
        "BTC-USDT 1h spot, 2026-10-01 .. 2026-10-01: 24 candles; sma-cross fast 3 slow 5; fee 0.10%"
    )
    assert all(len(line) == 22 for line in lines[2:])


def test_run_uses_cache_without_fetching(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(spot_day(), tmp_path, "--fast", "3", "--slow", "5", "--fee", "0") == 0
    first = capsys.readouterr().out
    empty = KuCoin()
    assert run(empty, tmp_path, "--fast", "3", "--slow", "5", "--fee", "0") == 0
    assert capsys.readouterr().out == first
    assert empty.calls == []
    assert first.splitlines() == expected_lines(3, 5, 0.0)


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
def test_run_refuses_bad_request(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], argv: list[str], message: str
) -> None:
    kucoin = spot_day()
    assert main(["run", *argv, "--cache-dir", str(tmp_path)], fetch=kucoin) == 2
    assert_refused(capsys, message)
    assert kucoin.calls == []


def test_run_refuses_bad_market(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exited:
        run(spot_day(), tmp_path, "--market", "margin")
    assert exited.value.code == 2
    assert "argument --market: invalid choice: 'margin'" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        (["--fast", "0"], "fast 0 is not a whole number of at least 1"),
        (["--fast", "x"], "fast 'x' is not a whole number of at least 1"),
        (["--fast", "1.5"], "fast '1.5' is not a whole number of at least 1"),
        (["--slow", "-5"], "slow -5 is not a whole number of at least 1"),
        (["--fast", "50", "--slow", "20"], "fast 50 is not below slow 20: the fast SMA must be"),
        (["--fast", "20", "--slow", "20"], "fast 20 is not below slow 20: the fast SMA must be"),
    ],
)
def test_run_refuses_bad_lengths(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], extra: list[str], message: str
) -> None:
    kucoin = spot_day()
    assert run(kucoin, tmp_path, *extra) == 2
    assert_refused(capsys, message)
    assert kucoin.calls == []


@pytest.mark.parametrize(
    ("fee", "message"),
    [
        ("abc", "fee 'abc' is not a number: pass a proportional fee, for example 0.001"),
        ("1.5", "fee 1.5 is out of range: it must be at least 0 and below 1"),
        ("-0.1", "fee -0.1 is out of range: it must be at least 0 and below 1"),
        ("nan", "fee nan is out of range"),
    ],
)
def test_run_refuses_bad_fee(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], fee: str, message: str
) -> None:
    kucoin = spot_day()
    assert run(kucoin, tmp_path, "--fast", "3", "--slow", "5", "--fee", fee) == 2
    assert_refused(capsys, message)
    assert kucoin.calls == []


def test_run_refuses_too_few_candles(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(spot_day(), tmp_path, "--fast", "3", "--slow", "30") == 2
    assert_refused(
        capsys,
        "the range has 24 candles, not more than slow 30: the strategy could never take a "
        "position; widen the dates or lower --slow",
    )


def test_run_candle_count_boundary(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(spot_day(), tmp_path, "--fast", "3", "--slow", "24") == 2
    assert_refused(capsys, "the range has 24 candles, not more than slow 24")
    assert run(spot_day(), tmp_path, "--fast", "3", "--slow", "23") == 0
    assert capsys.readouterr().out.splitlines() == expected_lines(3, 23, 0.001)


def test_run_refuses_missing_day(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = run(spot_day(), tmp_path, "--fast", "3", "--slow", "5", days=("2026-09-30", DAY))
    assert code == 2
    assert_refused(capsys, "24 candle(s) missing in 1 gap(s); the first from 2026-09-30 00:00:00")


def test_run_reports_download_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    kucoin = spot_day()
    kucoin.refuse("api.kucoin.com", HttpResponse(503))
    assert run(kucoin, tmp_path, "--fast", "3", "--slow", "5") == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("error: ") and len(captured.err.splitlines()) == 1
    assert "HTTP 503 after 3 retries" in captured.err


def test_run_reports_unusable_cache_dir(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    not_a_directory = tmp_path / "file"
    not_a_directory.write_text("")
    assert run(spot_day(), not_a_directory, "--fast", "3", "--slow", "5") == 2
    err = capsys.readouterr().err
    assert len(err.splitlines()) == 1
    assert err.startswith("error: ") and "check the cache directory (--cache-dir)" in err
