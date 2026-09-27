"""Approval-signature binding: check that a signed XRPL Payment is exactly what was approved.

Spend guards and option selectors decide on the 402 payment requirements *before* signing.
The signer fills more fields afterwards -- e.g. xrpl-py ``autofill`` sets ``Fee`` via
``get_fee``, whose documented default ceiling is 2 XRP and which scales with network load --
and a selector can pick an option other than the one the guard approved. This module checks
the decoded signed transaction, right before it is sent, against the approval, field by
field. Whatever was selected, a signed result that differs from the approval is a breach.

Invariant: no network, database, file, or clock I/O. Same input, same output.
tests/test_binding.py enforces purity (banned imports).

Field rules (xrpl.org Payment reference): an XRP-to-XRP payment omits ``SendMax`` and
``Paths``; ``tfPartialPayment`` (0x00020000) allows the delivered amount to shrink.
XRP amounts are integer strings in drops.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

TF_PARTIAL_PAYMENT = 0x00020000


@dataclass(frozen=True)
class Approval:
    """One payment the signer may produce: from whom, to whom, how many drops, fee cap in drops."""

    account: str
    pay_to: str
    amount_drops: int
    max_fee_drops: int


def _drops(value: Any) -> int | None:
    """Return the int for an XRP drops string, else None (IOU objects, decimals, missing)."""
    if isinstance(value, str) and value.isascii() and value.isdigit():
        return int(value)
    return None


def check_signed_payment(tx: Mapping[str, Any], approval: Approval) -> tuple[str, ...]:
    """Compare a decoded signed tx with the approval; return every breached field name.

    An empty tuple means the signed tx matches. Boundary rule matches the guard: a fee
    equal to the cap is allowed, one drop above is a breach. ``LastLedgerSequence`` is only
    required to be present -- without it the tx stays valid forever, and "the payment can
    no longer land" can never be established after an unclear settlement.
    """
    breaches: list[str] = []
    if tx.get("TransactionType") != "Payment":
        breaches.append("transaction_type")
    if tx.get("Account") != approval.account:
        breaches.append("account")
    if tx.get("Destination") != approval.pay_to:
        breaches.append("destination")
    if _drops(tx.get("Amount")) != approval.amount_drops:
        breaches.append("amount")
    if "SendMax" in tx:
        breaches.append("send_max")
    if "Paths" in tx:
        breaches.append("paths")
    flags = tx.get("Flags", 0)
    if not isinstance(flags, int) or flags & TF_PARTIAL_PAYMENT:
        breaches.append("partial_payment")
    fee = _drops(tx.get("Fee"))
    if fee is None or fee > approval.max_fee_drops:
        breaches.append("fee")
    if not isinstance(tx.get("LastLedgerSequence"), int):
        breaches.append("last_ledger_sequence")
    return tuple(breaches)
