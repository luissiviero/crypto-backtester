"""Offline tests for `python -m app.data`, driven through main(argv, fetch=stub)."""

from __future__ import annotations

from pathlib import Path

import pytest
from kucoin_stub import SPOT_1H, KuCoin

from app.data import http
from app.data.__main__ import human_size, main
from app.data.http import HttpResponse

pytestmark = pytest.mark.usefixtures("clock")


def download(kucoin: http.Fetch, root: Path, *days: str) -> int:
    return main(["download", "btc-usdt", "1h", *days, "--cache-dir", str(root)], fetch=kucoin)


def spot_day() -> KuCoin:
    kucoin = KuCoin()
    kucoin.add_spot(SPOT_1H)
    return kucoin


def test_download_reports_fetched_skipped_and_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    kucoin = spot_day()
    assert download(kucoin, tmp_path, "2026-10-01", "2026-10-01") == 0
    total = "Total for BTC-USDT 1h spot: 1 fetched, 0 skipped, 0 not found;"
    assert capsys.readouterr().out.splitlines() == [
        "2026-10-01                fetched from KuCoin (1 day)",
        f"{total} 0 candles missing. Cache: {tmp_path}",
    ]

    assert download(kucoin, tmp_path, "2026-09-30", "2026-10-02") == 1
    no_candles = "no candles; check the symbol exists"
    total = "Total for BTC-USDT 1h spot: 0 fetched, 1 skipped, 2 not found;"
    assert capsys.readouterr().out.splitlines() == [
        f"2026-09-30                not found: {no_candles} (1 day)",
        "2026-10-01                skipped, already cached (1 day)",
        f"2026-10-02                not found: {no_candles} (1 day)",
        f"{total} 48 candles missing. Cache: {tmp_path}",
    ]


def test_help_notes_short_days_and_lost_futures_days(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["download", "--help"])
    text = " ".join(capsys.readouterr().out.split())
    assert "never assume one row per interval" in text
    assert "Futures volume counts contracts" in text and "quote_volume" in text
    with pytest.raises(SystemExit):
        main(["cache-clear", "--help"])
    text = " ".join(capsys.readouterr().out.split())
    assert "a cleared futures day can be lost" in text


def test_cache_info_shows_sizes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["cache-info", "--cache-dir", str(tmp_path)]) == 0
    assert capsys.readouterr().out.startswith("No cached klines under")

    download(spot_day(), tmp_path, "2026-10-01", "2026-10-01")
    capsys.readouterr()
    assert main(["cache-info", "--cache-dir", str(tmp_path)]) == 0
    lines = capsys.readouterr().out.splitlines()
    size = next(tmp_path.rglob("*.parquet")).stat().st_size
    assert lines[0].split() == ["market", "symbol", "interval", "days", "size"]
    assert lines[1].split() == ["spot", "BTC-USDT", "1h", "1", *human_size(size).split()]
    assert lines[2] == f"Total: 1 day file, {human_size(size)} under {tmp_path / 'kucoin'}"
    assert human_size(1536) == "1.5 KiB"


def test_cache_clear_deletes_only_matching_day_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    directory = tmp_path / "kucoin" / "spot" / "BTC-USDT" / "1h"
    directory.mkdir(parents=True)
    for name in ("BTC-USDT-1h-2026-09-30.parquet", "BTC-USDT-1h-2026-10-01.parquet", "keep.txt"):
        (directory / name).write_bytes(b"x" * 10)
    other = tmp_path / "kucoin" / "spot" / "ETH-USDT" / "1h"
    other.mkdir(parents=True)
    (other / "ETH-USDT-1h-2026-09-30.parquet").write_bytes(b"x")

    argv = ["cache-clear", "btc-usdt", "1h", "--end", "2026-09-30", "--cache-dir", str(tmp_path)]
    assert main(argv) == 0
    assert capsys.readouterr().out == "Deleted 1 day file (10 B) for BTC-USDT 1h spot.\n"
    assert sorted(path.name for path in directory.iterdir()) == [
        "BTC-USDT-1h-2026-10-01.parquet",
        "keep.txt",
    ]
    assert (other / "ETH-USDT-1h-2026-09-30.parquet").is_file()
    argv = ["cache-clear", "XBTUSDTM", "--market", "futures", "--cache-dir", str(tmp_path)]
    assert main(argv) == 0
    assert capsys.readouterr().out.startswith("Nothing to delete")


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["download", "BTC/USDT", "1h", "2026-09-30", "2026-09-30"], "invalid spot symbol"),
        (["download", "BTC-USDT", "1h", "2026-30-09", "2026-09-30"], "invalid start date"),
        (
            ["download", "XBTUSDTM", "6h", "2026-09-30", "2026-09-30", "--market", "futures"],
            "interval '6h' is not offered on the futures market",
        ),
        (["cache-clear", "BTC-USDT", "7m"], "unknown interval"),
    ],
)
def test_invalid_parameter_prints_one_line_and_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], argv: list[str], message: str
) -> None:
    kucoin = KuCoin()
    assert main([*argv, "--cache-dir", str(tmp_path)], fetch=kucoin) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith(f"error: {message}")
    assert len(captured.err.splitlines()) == 1
    assert kucoin.calls == []


def test_unusable_cache_dir_prints_one_line_and_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    not_a_directory = tmp_path / "file"
    not_a_directory.write_text("")
    assert download(spot_day(), not_a_directory, "2026-10-01", "2026-10-01") == 2
    err = capsys.readouterr().err
    assert len(err.splitlines()) == 1
    assert err.startswith("error: ") and "check the cache directory (--cache-dir)" in err


def test_download_error_prints_one_line_and_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert download(lambda url: HttpResponse(503), tmp_path, "2026-10-01", "2026-10-01") == 2
    err = capsys.readouterr().err
    assert len(err.splitlines()) == 1
    assert "HTTP 503 after 3 retries" in err and "run again" in err
