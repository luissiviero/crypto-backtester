"""Fixtures shared by the data-layer tests: no real sleep, a fixed clock."""

from __future__ import annotations

import pytest
from kucoin_stub import NOW

from app.data import http, loader


@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Record every sleep of the transport instead of waiting; jitter fixed at 0.25 s."""
    recorded: list[float] = []
    monkeypatch.setattr(http, "sleep", recorded.append)
    monkeypatch.setattr(http, "jitter", lambda: 0.25)
    monkeypatch.setattr(http, "wall_clock", lambda: 1_790_812_845.0)
    return recorded


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch, sleeps: list[float]) -> None:
    monkeypatch.setattr(loader, "utc_now", lambda: NOW)
