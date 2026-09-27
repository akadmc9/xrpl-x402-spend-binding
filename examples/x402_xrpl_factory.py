"""Example: enforce approval-signature binding through x402-xrpl's ``payment_header_factory`` hook.

Requires ``xrpl-py`` and ``x402-xrpl`` (not dependencies of the core package).

``x402_purchase`` calls the factory with the selected payment requirements and sends whatever
header string it returns. If the factory raises, ``x402_purchase`` returns ``status="failed"``
and the payment header is never sent -- the signed blob stays local, so nothing is spent.

Usage::

    from x402_xrpl import x402_purchase

    factory = bound_header_factory(wallet, RPC_URL, price_drops=10_000)
    result = x402_purchase(url, wallet=wallet, rpc_url=RPC_URL,
                           payment_header_factory=factory)

Pair it with a selector that only accepts the option you approved (same asset and amount):
the selector stops a wrong choice before signing, this check stops a wrong signature before
sending. Neither replaces the other.
"""
from __future__ import annotations

import base64
import json

from x402_xrpl.client import XRPLPresignedPaymentPayer, XRPLPresignedPaymentPayerOptions
from xrpl.core.binarycodec import decode
from xrpl.wallet import Wallet

from xrpl_x402_spend_binding import Approval, check_signed_payment


def signed_tx_from_header(header: str) -> dict:
    """Decode the signed Payment inside a PAYMENT-SIGNATURE header (base64 JSON PaymentPayload)."""
    blob = json.loads(base64.b64decode(header))["payload"]["signedTxBlob"]
    return decode(blob)


def bound_header_factory(wallet: Wallet, rpc_url: str, *, price_drops: int,
                         max_fee_drops: int = 1_000):  # noqa: ANN201
    """Build a payment_header_factory that only returns a header whose signed tx matches.

    Signs with the same payer ``x402_purchase`` uses by default (invoice bound via InvoiceID and
    Memos), then checks the signed tx against: our account -> ``reqs.pay_to``, ``price_drops``,
    fee <= ``max_fee_drops``. The fee cap is the only guard on the ``Fee`` that autofill
    chooses -- pick one that fits your prices.
    """
    def factory(reqs, *, extensions=None):  # noqa: ANN001, ANN202
        payer = XRPLPresignedPaymentPayer(XRPLPresignedPaymentPayerOptions(
            wallet=wallet, network=reqs.network, rpc_url=rpc_url, invoice_binding="both"))
        header = payer.create_payment_header(reqs, extensions=extensions)
        tx = signed_tx_from_header(header)
        breaches = check_signed_payment(tx, Approval(
            account=wallet.classic_address, pay_to=reqs.pay_to,
            amount_drops=price_drops, max_fee_drops=max_fee_drops))
        if breaches:
            raise ValueError(f"signed tx does not match approval {list(breaches)}: "
                             f"Amount={tx.get('Amount')} Fee={tx.get('Fee')} "
                             f"(approved {price_drops} drops, fee cap {max_fee_drops})")
        return header
    return factory
