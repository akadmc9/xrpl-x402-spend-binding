"""Spend guard: a pure decision over three caps -- per call, rolling 24 hours, lifetime total.

Invariant: no network, database, file, or clock I/O. The caller injects the current time and
the spend history -- same input, same output. tests/test_guard.py enforces purity.

The daily cap is a **rolling 24 hours**, not a calendar day: spending just before and just
after midnight cannot reach twice the daily cap. Boundary rule: equal to a cap is allowed,
anything above is blocked.

Amounts are XRP drops. The history should contain every spend that can still land on the
ledger; if it only holds validated spends, callers must serialize purchases (see README).
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

_DAY = timedelta(hours=24)


@dataclass(frozen=True)
class GuardLimits:
    """Three spend caps in drops. Exceeding any one blocks the payment."""

    per_call_drops: int
    daily_drops: int
    total_drops: int

    def __post_init__(self) -> None:
        if not (0 < self.per_call_drops <= self.daily_drops <= self.total_drops):
            raise ValueError(
                f"caps must satisfy 0 < per_call({self.per_call_drops}) <= daily({self.daily_drops})"
                f" <= total({self.total_drops})")


@dataclass(frozen=True)
class GuardDecision:
    """Guard verdict. Allowed when ``breaches`` is empty; every breached cap is listed."""

    allowed: bool
    breaches: tuple[str, ...]
    amount_drops: int
    daily_spent_drops: int
    total_spent_drops: int
    reason: str


def decide(*, amount_drops: int, now: datetime,
           history: Sequence[tuple[datetime, int]],
           limits: GuardLimits) -> GuardDecision:
    """Decide one proposed spend. Pure and deterministic.

    history: (spend time, drops) pairs, any order. Future timestamps count toward the daily
    window (conservative). ``amount_drops <= 0`` is a caller bug -- ValueError.
    """
    if amount_drops <= 0:
        raise ValueError(f"amount_drops must be positive: {amount_drops}")

    daily_spent = sum(d for t, d in history if now - t < _DAY)
    total_spent = sum(d for _, d in history)

    breaches: list[str] = []
    if amount_drops > limits.per_call_drops:
        breaches.append("per_call")
    if daily_spent + amount_drops > limits.daily_drops:
        breaches.append("daily")
    if total_spent + amount_drops > limits.total_drops:
        breaches.append("total")

    allowed = not breaches
    reason = ("ok" if allowed else
              f"blocked {breaches}: proposed {amount_drops}, 24h spent {daily_spent}, "
              f"total spent {total_spent}, "
              f"caps {limits.per_call_drops}/{limits.daily_drops}/{limits.total_drops}")
    return GuardDecision(
        allowed=allowed,
        breaches=tuple(breaches),
        amount_drops=amount_drops,
        daily_spent_drops=daily_spent,
        total_spent_drops=total_spent,
        reason=reason,
    )
