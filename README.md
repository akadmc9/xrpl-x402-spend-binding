# xrpl-x402-spend-binding

Pure spend checks for x402 buyers paying on the XRP Ledger (exact scheme, presigned `Payment`):

- **`check_signed_payment`** — *approval-signature binding*. Right before the payment header is
  sent, decode the signed transaction and compare it with what you approved, field by field.
- **`decide`** — a three-cap spend guard: per call, rolling 24 hours, lifetime total.

No dependencies, no I/O. Same input, same output.

## Why check the signed transaction

Spend guards decide on the 402 payment requirements **before** signing. Two things happen
after that decision, and a guard never sees them:

1. **The signer fills fields you did not approve.** xrpl-py's `autofill` sets `Fee` through
   `get_fee`, whose documented default ceiling is **2 XRP** and which scales with network load
   (the "open ledger" fee reported by whichever RPC node you use). For a 0.01 XRP API call,
   that is up to 200x the price in fees.
2. **A selector can pick an option other than the one you approved.** When a 402 response lists
   several `accepts` options, the one your guard judged and the one that reaches the signer are
   not guaranteed to be the same — for example, an issued-currency option whose number equals
   the approved drops.

Checking the signed result closes both gaps, whatever the selector chose. None of the public
x402 spend guards we reviewed in September 2026 compared the signed payload with the approval;
they all decide at the requirements stage. (Reviewed: README-level for most, so treat this as
"not found", not "does not exist".)

## What `check_signed_payment` enforces

| Field | Rule |
|---|---|
| `TransactionType` | `Payment` |
| `Account` | your wallet |
| `Destination` | the approved `payTo` |
| `Amount` | an XRP drops string equal to the approved drops (issued-currency amounts are rejected) |
| `SendMax`, `Paths` | absent (XRP-to-XRP payments omit them) |
| `Flags` | no `tfPartialPayment` (0x00020000) |
| `Fee` | ≤ your fee cap (equal is allowed) |
| `LastLedgerSequence` | present (without it the tx stays valid forever) |

Every breached field is returned, so one alert shows the whole cause.

```python
from xrpl_x402_spend_binding import Approval, check_signed_payment

breaches = check_signed_payment(decoded_tx, Approval(
    account=wallet.classic_address, pay_to=reqs.pay_to,
    amount_drops=10_000, max_fee_drops=1_000))
if breaches:
    raise ValueError(f"signed tx does not match approval: {breaches}")  # do not send
```

For [x402-xrpl](https://pypi.org/project/x402-xrpl/), `examples/x402_xrpl_factory.py` wires this
into the `payment_header_factory` hook: if the check fails, `x402_purchase` returns
`status="failed"` and never sends the header.

## What `decide` enforces

```python
from datetime import datetime, timezone
from xrpl_x402_spend_binding import GuardLimits, decide

limits = GuardLimits(per_call_drops=100_000, daily_drops=200_000, total_drops=1_000_000)
d = decide(amount_drops=10_000, now=datetime.now(timezone.utc),
           history=[(spent_at, drops), ...], limits=limits)
if not d.allowed:
    ...  # stop and alert; d.breaches lists every cap that was exceeded
```

- The daily cap is a **rolling 24 hours**, not a calendar day — spending on both sides of
  midnight cannot reach twice the cap.
- A value equal to a cap is allowed; anything above is blocked.

## Threat model

**Protects against:** a signer or selector producing a transaction that differs from your
approval — amount, asset, destination, fee, partial payment, missing expiry; and spending past
your per-call, daily, or lifetime caps.

**Does not protect against:**

- **A compromised agent process.** These are in-process checks. Code that can read the seed can
  sign without them. The hard bound is the wallet balance — keep it at an amount you can lose.
- **Concurrent purchases.** `decide` only knows the history you pass in. If that history holds
  validated spends only, two overlapping purchases can both pass. Serialize purchases (one at a
  time) or include pending spends.
- **Issued-currency spending.** XRP only, by design.
- **A price you approved.** The seller sets the price; your guard decides whether to accept it.
- **Non-delivery after payment.** If the seller settles but returns no data, that is outside
  these checks — record the settlement transaction and follow up.

## Provenance and status

Extracted from a small live experiment (a buyer agent on XRPL mainnet with a few XRP, running
since July 2026). What has been exercised: the guard blocked a real mainnet purchase at its
daily cap; all three caps were fired on testnet; the binding check ran on a testnet round trip
and is covered by field-level mutation tests. **Not exercised:** concurrency, adversarial
sellers at scale, mainnet fee spikes.

Version 0.1 — a reference implementation with no support commitment. Not on PyPI; install from
GitHub:

```bash
pip install "git+https://github.com/akadmc9/xrpl-x402-spend-binding"
```

Tests: `pip install pytest && pytest`.

## License

MIT
