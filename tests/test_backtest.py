"""Offline tests for the backtest engine, on frames built by hand with hand-computed results."""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import datetime, timezone

import polars as pl
import pytest

from app.backtest.engine import BacktestResult, run_backtest
from app.backtest.inputs import DEFAULT_FEE, BacktestInputError, validate
from app.backtest.summary import Summary, max_drawdown, summarize


def _frame(
    opens: Sequence[float | None],
    closes: Sequence[float | None],
    times: Sequence[object] | None = None,
) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "open_time": list(range(len(opens))) if times is None else list(times),
            "open": pl.Series(list(opens), dtype=pl.Float64),
            "close": pl.Series(list(closes), dtype=pl.Float64),
        }
    )


def test_refuses_length_mismatch() -> None:
    frame = _frame([100, 100, 100], [100, 100, 100])
    with pytest.raises(BacktestInputError, match="positions has 2 values but the frame has 3"):
        validate(frame, [0, 1], 0.001)


@pytest.mark.parametrize("bad", [None, math.nan, 2, -1, 0.5, "1", True])
def test_refuses_bad_position_values(bad: object) -> None:
    frame = _frame([100, 100, 100], [100, 100, 100])
    with pytest.raises(BacktestInputError, match=r"positions\[1\] is .*: each position must be"):
        validate(frame, [0, bad, 0], 0.001)


def test_refuses_bad_position_series() -> None:
    frame = _frame([100, 100], [100, 100])
    for series in (
        pl.Series([0, None], dtype=pl.Int64),
        pl.Series([0.0, 1.0]),
        pl.Series([False, True]),
    ):
        with pytest.raises(BacktestInputError, match="each position must be"):
            validate(frame, series, 0.001)


def test_refuses_empty_frame() -> None:
    with pytest.raises(BacktestInputError, match="frame is empty"):
        validate(_frame([], []), [], 0.001)


@pytest.mark.parametrize("times", [[0, 2, 2], [0, 3, 1]])
def test_refuses_non_increasing_open_time(times: list[int]) -> None:
    frame = _frame([100, 100, 100], [100, 100, 100], times)
    with pytest.raises(BacktestInputError, match=r"open_time\[2\] .* strictly increasing"):
        validate(frame, [0, 0, 0], 0.001)


@pytest.mark.parametrize("fee", [-0.01, 1, 1.5, math.nan, True, "0.001", None])
def test_refuses_fee_out_of_range(fee: object) -> None:
    frame = _frame([100], [100])
    with pytest.raises(BacktestInputError, match="fee"):
        validate(frame, [0], fee)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("frame", "message"),
    [
        ({"open_time": [0], "open": [1.0], "close": [1.0]}, "polars DataFrame"),
        (pl.DataFrame({"open_time": [0], "open": [1.0]}), "lacks the column"),
        (
            pl.DataFrame({"open_time": [None, 1], "open": [1.0, 1.0], "close": [1.0, 1.0]}),
            r"open_time\[0\] is null",
        ),
        (_frame([100, None], [100, 100]), r"open\[1\] is None"),
        (_frame([100, 100], [100, math.inf]), r"close\[1\] is inf"),
        (_frame([100, 100], [math.nan, 100]), r"close\[0\] is nan"),
        (_frame([100, 0], [100, 100]), r"open\[1\] is 0.0"),
        (_frame([100, -5], [100, 100]), r"open\[1\] is -5.0"),
        (
            pl.DataFrame({"open_time": [0, 1], "open": ["10", "11"], "close": [1.0, 1.0]}),
            "prices must be numbers",
        ),
        (
            pl.DataFrame({"open_time": [0, 1], "open": [1.0, 1.0], "close": [True, True]}),
            "prices must be numbers",
        ),
        (
            pl.DataFrame({"open_time": [0, 1], "open": ["a", "b"], "close": [1.0, 1.0]}),
            "prices must be numbers",
        ),
    ],
)
def test_refuses_bad_frame_schema_and_prices(frame: object, message: str) -> None:
    with pytest.raises(BacktestInputError, match=message):
        validate(frame, [0, 0], 0.001)  # type: ignore[arg-type]


def test_validate_reads_the_three_columns() -> None:
    times = [datetime(2024, 1, 1, hour, tzinfo=timezone.utc) for hour in (0, 1)]
    frame = _frame([100, 110], [105, 120], times).with_columns(pl.lit(7.0).alias("volume"))
    inputs = validate(frame, pl.Series([1, 0]), 0)
    assert inputs.opens == [100.0, 110.0]
    assert inputs.closes == [105.0, 120.0]
    assert inputs.positions == [1, 0]
    assert inputs.fee == 0.0
    assert inputs.open_time.to_list() == times


def test_max_drawdown_from_running_peak() -> None:
    assert max_drawdown([1.0, 1.0, 1.0]) == 0.0
    assert max_drawdown([1.0, 1.2, 1.5]) == 0.0
    assert max_drawdown([1.0, 2.0, 1.5, 1.8, 1.0, 1.9]) == pytest.approx(0.5, abs=1e-9)
    assert max_drawdown([1.0, 0.8, 1.2, 0.9]) == pytest.approx(0.25, abs=1e-9)


def test_summarize_counts_wins_and_rows() -> None:
    summary = summarize([1.0, 1.1, 0.99, 1.21], [0, 1, 0, 1], [0.1, -0.1, 0.0])
    assert summary == Summary(
        total_return=pytest.approx(0.21, abs=1e-9),
        max_drawdown=pytest.approx(0.1, abs=1e-9),
        trade_count=3,
        win_rate=pytest.approx(1 / 3, abs=1e-9),
        time_in_market=0.5,
    )


EXAMPLE_OPENS = [100, 100, 110, 120, 100, 90, 81]
EXAMPLE_CLOSES = [100, 110, 120, 100, 90, 85, 81]
EXAMPLE_POSITIONS = [1, 1, 0, 0, 1, 0, 0]


def _example() -> BacktestResult:
    return run_backtest(_frame(EXAMPLE_OPENS, EXAMPLE_CLOSES), EXAMPLE_POSITIONS, fee=0.001)


def test_two_trade_example_trades() -> None:
    trades = _example().trades
    assert trades["entry_time"].to_list() == [1, 5]
    assert trades["entry_price"].to_list() == [100.0, 90.0]
    assert trades["exit_time"].to_list() == [3, 6]
    assert trades["exit_price"].to_list() == [120.0, 81.0]
    assert trades["return"].to_list() == pytest.approx([0.1976012, -0.1017991], abs=1e-9)
    assert trades["closed_at_end"].to_list() == [False, False]


def test_two_trade_example_equity_curve() -> None:
    equity = _example().equity
    assert equity.columns == ["open_time", "position", "equity"]
    assert equity["open_time"].to_list() == list(range(7))
    assert equity["position"].to_list() == [0, 1, 1, 0, 0, 1, 0]
    assert equity["equity"].to_list() == pytest.approx(
        [1.0, 1.0989, 1.1988, 1.1976012, 1.1976012, 1.1299367322, 1.07568647568108], abs=1e-9
    )


def test_two_trade_example_summary() -> None:
    summary = _example().summary
    assert summary.total_return == pytest.approx(0.07568647568108, abs=1e-9)
    assert summary.total_return == pytest.approx(1.2 * 0.9 * 0.999**4 - 1, abs=1e-9)
    assert summary.max_drawdown == pytest.approx(0.1026973009, abs=1e-9)
    assert summary.trade_count == 2
    assert summary.win_rate == 0.5
    assert summary.time_in_market == pytest.approx(3 / 7, abs=1e-9)


def test_buy_and_hold_equals_price_ratio_less_two_fees() -> None:
    fee = 0.002
    frame = _frame([100, 100, 120, 150], [100, 110, 130, 150])
    result = run_backtest(frame, [1, 1, 0, 0], fee=fee)
    final = result.equity["equity"][-1]
    assert final == pytest.approx((1 - fee) ** 2 * 150 / 100, abs=1e-9)
    assert result.summary.total_return == pytest.approx(final - 1, abs=1e-9)
    assert result.trades["return"].to_list() == pytest.approx([final - 1], abs=1e-9)


def test_no_fill_on_decision_candle() -> None:
    frame = _frame([100, 120, 130], [110, 125, 130])
    result = run_backtest(frame, [1, 0, 0], fee=0.001)
    assert result.trades["entry_time"].to_list() == [1]
    assert result.trades["entry_price"].to_list() == [120.0]
    assert result.equity["position"].to_list() == [0, 1, 0]
    assert result.equity["equity"].to_list() == pytest.approx(
        [1.0, 0.999 / 120 * 125, 0.999**2 / 120 * 130], abs=1e-9
    )


def test_gap_fills_at_next_existing_row() -> None:
    times = [datetime(2024, 1, 1, hour, tzinfo=timezone.utc) for hour in (0, 1, 3, 4)]
    frame = _frame([100, 101, 120, 130], [101, 102, 125, 130], times).with_columns(
        pl.col("open_time").cast(pl.Datetime("ms", "UTC"))
    )
    result = run_backtest(frame, [0, 1, 0, 0], fee=0.001)
    trades = result.trades
    assert trades.schema["entry_time"] == pl.Datetime("ms", "UTC")
    assert trades["entry_time"].to_list() == [times[2]]
    assert trades["entry_price"].to_list() == [120.0]
    assert trades["exit_time"].to_list() == [times[3]]
    assert trades["exit_price"].to_list() == [130.0]
    assert result.equity["position"].to_list() == [0, 0, 1, 0]
    assert result.equity["equity"][1] == 1.0


def test_decision_on_last_row_not_filled() -> None:
    result = run_backtest(_frame([100, 110, 120], [105, 115, 125]), [0, 0, 1])
    assert result.trades.height == 0
    assert result.equity["position"].to_list() == [0, 0, 0]
    assert result.equity["equity"].to_list() == [1.0, 1.0, 1.0]


def test_open_position_closed_at_last_close() -> None:
    result = run_backtest(_frame([100, 100, 110], [100, 105, 121]), [1, 1, 1], fee=0.001)
    trades = result.trades
    assert trades["entry_time"].to_list() == [1]
    assert trades["exit_time"].to_list() == [2]
    assert trades["exit_price"].to_list() == [121.0]
    assert trades["closed_at_end"].to_list() == [True]
    final = 0.999**2 * 121 / 100
    assert trades["return"].to_list() == pytest.approx([final - 1], abs=1e-9)
    assert result.equity["position"].to_list() == [0, 1, 1]
    assert result.equity["equity"][-1] == pytest.approx(final, abs=1e-9)
    assert result.equity["equity"][-1] == pytest.approx(1 + result.summary.total_return, abs=1e-9)
    assert result.summary.trade_count == 1
    assert result.summary.time_in_market == pytest.approx(2 / 3, abs=1e-9)


def test_no_trades_gives_zero_win_rate_and_flat_equity() -> None:
    result = run_backtest(_frame([100, 50, 200], [50, 200, 10]), [0, 0, 0])
    assert result.summary.trade_count == 0
    assert result.summary.win_rate == 0.0
    assert result.summary.total_return == 0.0
    assert result.summary.max_drawdown == 0.0
    assert result.summary.time_in_market == 0.0
    assert result.equity["equity"].to_list() == [1.0, 1.0, 1.0]
    assert result.trades.height == 0
    assert result.trades.schema == pl.Schema(
        {
            "entry_time": pl.Int64,
            "entry_price": pl.Float64,
            "exit_time": pl.Int64,
            "exit_price": pl.Float64,
            "return": pl.Float64,
            "closed_at_end": pl.Boolean,
        }
    )


def test_default_fee_is_one_tenth_percent() -> None:
    assert DEFAULT_FEE == 0.001
    frame = _frame(EXAMPLE_OPENS, EXAMPLE_CLOSES)
    default = run_backtest(frame, EXAMPLE_POSITIONS)
    assert default.summary == _example().summary
    assert default.summary != run_backtest(frame, EXAMPLE_POSITIONS, fee=0.0).summary


def test_positions_accepts_series_and_list() -> None:
    frame = _frame(EXAMPLE_OPENS, EXAMPLE_CLOSES)
    from_list = run_backtest(frame, EXAMPLE_POSITIONS)
    for series in (pl.Series(EXAMPLE_POSITIONS), pl.Series(EXAMPLE_POSITIONS, dtype=pl.Int8)):
        from_series = run_backtest(frame, series)
        assert from_series.summary == from_list.summary
        assert from_series.equity.equals(from_list.equity)
        assert from_series.trades.equals(from_list.trades)
    assert from_list.summary == run_backtest(frame, tuple(EXAMPLE_POSITIONS)).summary


def test_futures_volume_ignored() -> None:
    frame = _frame(EXAMPLE_OPENS, EXAMPLE_CLOSES)
    futures = frame.with_columns(
        pl.Series("high", [1e6] * 7),
        pl.Series("low", [1e-6] * 7),
        pl.Series("volume", [0.0, 5.0, 1e9, 3.0, 0.0, 2.0, 7.0]),
        pl.Series("quote_volume", [1.0] * 7),
    )
    plain = run_backtest(frame, EXAMPLE_POSITIONS)
    result = run_backtest(futures, EXAMPLE_POSITIONS)
    assert result.summary == plain.summary
    assert result.equity.equals(plain.equity)
    assert result.trades.equals(plain.trades)


def test_public_api() -> None:
    import app.backtest as api

    assert set(api.__all__) == {
        "BacktestInputError",
        "BacktestResult",
        "DEFAULT_FEE",
        "Summary",
        "run_backtest",
        "sma_cross_positions",
    }
    assert api.run_backtest is run_backtest
    assert api.BacktestResult is BacktestResult
    assert api.Summary is Summary
    assert api.DEFAULT_FEE == DEFAULT_FEE
    assert issubclass(api.BacktestInputError, ValueError)
    assert isinstance(api.run_backtest(_frame([100], [100]), [0]), api.BacktestResult)


def test_run_backtest_refuses_before_calculating() -> None:
    with pytest.raises(BacktestInputError, match="fee"):
        run_backtest(_frame([100], [100]), [0], fee=1.0)
