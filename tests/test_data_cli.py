"""Offline tests for `python -m app.data`, driven through main(argv, fetch=stub)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from binance_stub import Binance

from app.data import http, loader
from app.data.__main__ import human_size, main
from app.data.http import HttpResponse

NOW = datetime(2025, 1, 2, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(loader, "utc_now", lambda: NOW)
    monkeypatch.setattr(http, "sleep", lambda seconds: None)


def download(binance: http.Fetch, root: Path, *days: str) -> int:
    return main(["download", "btcusdt", "1h", *days, "--cache-dir", str(root)], fetch=binance)


def test_download_reports_fetched_skipped_rest_and_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    binance = Binance()
    binance.vision("spot", "2025-01-01", "spot-BTCUSDT-1h-2025-01-01.csv")
    binance.rest("rest-spot-BTCUSDT-1h-2024-12-31.json")
    assert download(binance, tmp_path, "2025-01-01", "2025-01-01") == 0
    assert "2025-01-01                fetched from Vision (1 day)" in capsys.readouterr().out

    assert download(binance, tmp_path, "2024-12-30", "2025-01-01") == 1
    no_candles = "not on Vision (404) and REST returned no candles"
    total = "Total for BTCUSDT 1h spot: 0 fetched, 1 skipped, 1 from REST, 1 not found;"
    assert capsys.readouterr().out.splitlines() == [
        f"2024-12-30                not found: {no_candles} (1 day)",
        "2024-12-31                filled from REST (1 day)",
        "2025-01-01                skipped, already cached (1 day)",
        f"{total} 24 candles missing. Cache: {tmp_path}",
    ]


def test_download_reports_candles_missing_inside_a_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    binance = Binance()
    binance.vision("spot", "2024-12-30", "spot-BTCUSDT-1h-2024-12-30-missing-two.csv")
    assert download(binance, tmp_path, "2024-12-30", "2024-12-30") == 1
    assert (
        "2024-12-30 05:00:00 .. 2024-12-30 06:00:00 UTC  2 candles missing: "
        "missing candles in source file" in capsys.readouterr().out
    )


def test_cache_info_shows_sizes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["cache-info", "--cache-dir", str(tmp_path)]) == 0
    assert capsys.readouterr().out.startswith("No cached klines under")

    binance = Binance()
    binance.vision("spot", "2025-01-01", "spot-BTCUSDT-1h-2025-01-01.csv")
    download(binance, tmp_path, "2025-01-01", "2025-01-01")
    capsys.readouterr()
    assert main(["cache-info", "--cache-dir", str(tmp_path)]) == 0
    lines = capsys.readouterr().out.splitlines()
    size = next(tmp_path.rglob("*.parquet")).stat().st_size
    assert lines[0].split() == ["market", "symbol", "interval", "days", "size"]
    assert lines[1].split() == ["spot", "BTCUSDT", "1h", "1", *human_size(size).split()]
    assert lines[2] == f"Total: 1 day file, {human_size(size)} under {tmp_path / 'binance-vision'}"
    assert human_size(1536) == "1.5 KiB"


def test_cache_clear_deletes_only_matching_day_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    directory = tmp_path / "binance-vision" / "spot" / "BTCUSDT" / "1h"
    directory.mkdir(parents=True)
    for name in ("BTCUSDT-1h-2024-12-31.parquet", "BTCUSDT-1h-2025-01-01.parquet", "keep.txt"):
        (directory / name).write_bytes(b"x" * 10)
    other = tmp_path / "binance-vision" / "spot" / "ETHUSDT" / "1h"
    other.mkdir(parents=True)
    (other / "ETHUSDT-1h-2024-12-31.parquet").write_bytes(b"x")

    argv = ["cache-clear", "BTCUSDT", "1h", "--end", "2024-12-31", "--cache-dir", str(tmp_path)]
    assert main(argv) == 0
    assert capsys.readouterr().out == "Deleted 1 day file (10 B) for BTCUSDT 1h spot.\n"
    assert sorted(path.name for path in directory.iterdir()) == [
        "BTCUSDT-1h-2025-01-01.parquet",
        "keep.txt",
    ]
    assert (other / "ETHUSDT-1h-2024-12-31.parquet").is_file()
    assert main(["cache-clear", "BTCUSDT", "--market", "um", "--cache-dir", str(tmp_path)]) == 0
    assert capsys.readouterr().out.startswith("Nothing to delete")


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["download", "BTC/USDT", "1h", "2024-12-31", "2024-12-31"], "invalid symbol"),
        (["download", "BTCUSDT", "1h", "2024-31-12", "2024-12-31"], "invalid start date"),
        (["cache-clear", "BTCUSDT", "7m"], "unknown interval"),
    ],
)
def test_invalid_parameter_prints_one_line_and_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], argv: list[str], message: str
) -> None:
    binance = Binance()
    assert main([*argv, "--cache-dir", str(tmp_path)], fetch=binance) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith(f"error: {message}")
    assert len(captured.err.splitlines()) == 1
    assert binance.calls == []


def test_unusable_cache_dir_prints_one_line_and_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    binance = Binance()
    binance.vision("spot", "2024-12-31", "spot-BTCUSDT-1h-2024-12-31.csv")
    not_a_directory = tmp_path / "file"
    not_a_directory.write_text("")
    assert download(binance, not_a_directory, "2024-12-31", "2024-12-31") == 2
    err = capsys.readouterr().err
    assert len(err.splitlines()) == 1
    assert err.startswith("error: ") and "check the cache directory (--cache-dir)" in err


def test_ban_prints_one_line_and_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert download(lambda url: HttpResponse(418), tmp_path, "2024-12-31", "2024-12-31") == 2
    err = capsys.readouterr().err
    assert len(err.splitlines()) == 1
    assert "HTTP 418" in err and "wait before running again" in err
