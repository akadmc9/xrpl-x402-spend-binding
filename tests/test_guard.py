"""Spend guard: three caps, boundary values, determinism, purity."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from xrpl_x402_spend_binding import GuardLimits, decide

NOW = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)
LIMITS = GuardLimits(per_call_drops=10_000, daily_drops=30_000, total_drops=100_000)


def _hist(*items: tuple[int, int]) -> list[tuple[datetime, int]]:
    """(hours ago, drops) pairs -> history."""
    return [(NOW - timedelta(hours=h), d) for h, d in items]


def test_allows_within_all_limits() -> None:
    d = decide(amount_drops=10_000, now=NOW, history=_hist((1, 10_000)), limits=LIMITS)
    assert d.allowed and d.breaches == ()


def test_per_call_breach() -> None:
    d = decide(amount_drops=10_001, now=NOW, history=[], limits=LIMITS)
    assert not d.allowed and "per_call" in d.breaches


def test_daily_breach_rolling_24h() -> None:
    """Rolling 24h: a spend 23 hours ago counts, one 25 hours ago does not."""
    hist = _hist((23, 15_000), (25, 15_000))
    blocked = decide(amount_drops=10_000, now=NOW, history=hist + _hist((2, 10_000)), limits=LIMITS)
    assert not blocked.allowed and "daily" in blocked.breaches  # 15k + 10k + 10k > 30k
    ok = decide(amount_drops=5_000, now=NOW, history=hist, limits=LIMITS)
    assert ok.allowed  # 15k (23h) + 5k = 20k <= 30k; the 15k from 25h ago is outside


def test_total_breach_ignores_time() -> None:
    hist = _hist((100, 50_000), (200, 45_000))  # old spends still count toward the total
    d = decide(amount_drops=6_000, now=NOW, history=hist, limits=LIMITS)
    assert not d.allowed and d.breaches == ("total",)


def test_boundary_exact_limit_allowed() -> None:
    """Boundary: exactly at a cap is allowed; one drop above is blocked."""
    assert decide(amount_drops=10_000, now=NOW, history=[], limits=LIMITS).allowed
    hist = _hist((1, 20_000))
    assert decide(amount_drops=10_000, now=NOW, history=hist, limits=LIMITS).allowed  # daily = 30k
    assert not decide(amount_drops=10_000, now=NOW, history=_hist((1, 20_001)), limits=LIMITS).allowed


def test_multiple_breaches_all_reported() -> None:
    hist = _hist((1, 25_000), (50, 70_000))
    d = decide(amount_drops=12_000, now=NOW, history=hist, limits=LIMITS)
    assert set(d.breaches) == {"per_call", "daily", "total"}


def test_deterministic_same_input_same_output() -> None:
    hist = _hist((3, 7_000))
    assert decide(amount_drops=1, now=NOW, history=hist, limits=LIMITS) == \
           decide(amount_drops=1, now=NOW, history=hist, limits=LIMITS)


def test_invalid_amount_is_caller_bug() -> None:
    with pytest.raises(ValueError):
        decide(amount_drops=0, now=NOW, history=[], limits=LIMITS)


def test_invalid_limits_are_rejected() -> None:
    """Caps must be ordered: 0 < per_call <= daily <= total."""
    with pytest.raises(ValueError):
        GuardLimits(per_call_drops=20_000, daily_drops=10_000, total_drops=100_000)


def test_guard_module_has_no_io_imports() -> None:
    """Purity invariant: no network, database, or file I/O in the guard module."""
    import xrpl_x402_spend_binding.guard as guard_module
    src = open(guard_module.__file__, encoding="utf-8").read()
    for banned in ("sqlite3", "httpx", "requests", "socket", "open(", "Path(", "os.environ"):
        assert banned not in src, f"banned import/call in guard.py: {banned}"
