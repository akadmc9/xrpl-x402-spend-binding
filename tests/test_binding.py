"""Approval-signature binding: is the signed Payment exactly what was approved?"""
from __future__ import annotations

import pytest

from xrpl_x402_spend_binding import Approval, check_signed_payment

APPROVAL = Approval(account="rBuyer", pay_to="rSeller", amount_drops=10_000, max_fee_drops=1_000)

# Field set of an XRP Payment as an x402 exact-scheme payer signs it
# (invoice bound via InvoiceID + Memos, SourceTag set).
VALID_TX: dict = {
    "TransactionType": "Payment",
    "Account": "rBuyer",
    "Destination": "rSeller",
    "Amount": "10000",
    "Fee": "12",
    "Sequence": 7,
    "Flags": 0,
    "LastLedgerSequence": 90_000_100,
    "SourceTag": 12345,
    "InvoiceID": "AB" * 32,
    "Memos": [{"Memo": {"MemoData": "696E762D31"}}],
    "SigningPubKey": "ED" + "00" * 32,
    "TxnSignature": "00" * 64,
}


def _tx(**changes) -> dict:  # noqa: ANN003
    """VALID_TX with fields replaced (value) or removed (None)."""
    tx = dict(VALID_TX)
    for key, value in changes.items():
        if value is None:
            tx.pop(key, None)
        else:
            tx[key] = value
    return tx


def test_matching_payment_has_no_breaches() -> None:
    assert check_signed_payment(VALID_TX, APPROVAL) == ()


@pytest.mark.parametrize(("tx", "breach"), [
    pytest.param(_tx(TransactionType="TrustSet"), "transaction_type", id="not-a-payment"),
    pytest.param(_tx(Account="rSomeoneElse"), "account", id="other-signer"),
    pytest.param(_tx(Destination="rAttacker"), "destination", id="other-destination"),
    pytest.param(_tx(Amount="20000"), "amount", id="more-drops"),
    pytest.param(_tx(Amount="5000"), "amount", id="fewer-drops"),
    # A selector that picked a different option than the approved one: an issued-currency
    # amount with the same number as the approved drops.
    pytest.param(_tx(Amount={"currency": "524C555344000000000000000000000000000000",
                             "issuer": "rIssuer", "value": "10000"}), "amount", id="iou-amount"),
    pytest.param(_tx(Amount="10000.5"), "amount", id="non-integer-drops"),
    pytest.param(_tx(Amount=None), "amount", id="amount-missing"),
    pytest.param(_tx(SendMax="10000"), "send_max", id="send-max-present"),
    pytest.param(_tx(Paths=[[{"account": "rHop"}]]), "paths", id="paths-present"),
    pytest.param(_tx(Flags=0x00020000), "partial_payment", id="partial-payment-flag"),
    pytest.param(_tx(Flags=0x80020000), "partial_payment", id="partial-with-other-bits"),
    pytest.param(_tx(Fee="2000000"), "fee", id="fee-at-xrpl-py-default-ceiling"),
    pytest.param(_tx(Fee="1001"), "fee", id="fee-one-over-cap"),
    pytest.param(_tx(Fee="abc"), "fee", id="fee-not-drops"),
    pytest.param(_tx(Fee=None), "fee", id="fee-missing"),
    pytest.param(_tx(LastLedgerSequence=None), "last_ledger_sequence", id="no-expiry"),
])
def test_single_mismatch_is_reported_by_name(tx: dict, breach: str) -> None:
    """One field differing from the approval yields exactly that field's name."""
    assert check_signed_payment(tx, APPROVAL) == (breach,)


def test_fee_exactly_at_cap_is_allowed() -> None:
    """Boundary: equal to the cap passes, one drop above is a breach (same rule as the guard)."""
    assert check_signed_payment(_tx(Fee="1000"), APPROVAL) == ()


def test_unrelated_flags_are_allowed() -> None:
    """Bits unrelated to the amount (e.g. tfFullyCanonicalSig 0x80000000) pass."""
    assert check_signed_payment(_tx(Flags=0x80000000), APPROVAL) == ()


def test_flags_absent_is_allowed() -> None:
    """A signed tx without a Flags field (= 0) is normal."""
    assert check_signed_payment(_tx(Flags=None), APPROVAL) == ()


def test_all_mismatches_are_reported() -> None:
    """Every breach is listed, so one alert shows the whole cause."""
    tx = _tx(Destination="rAttacker", Amount="99999", Fee="5000", SendMax="99999")
    assert set(check_signed_payment(tx, APPROVAL)) == {"destination", "amount", "fee", "send_max"}


def test_binding_module_has_no_io_imports() -> None:
    """Purity invariant: no network, database, or file I/O in the binding module."""
    import xrpl_x402_spend_binding.binding as binding_module
    src = open(binding_module.__file__, encoding="utf-8").read()
    for banned in ("sqlite3", "httpx", "requests", "socket", "open(", "Path(", "os.environ",
                   "xrpl.clients", "JsonRpcClient"):
        assert banned not in src, f"banned import/call in binding.py: {banned}"
