# Per-Payment Receipt — Implementation Plan

**Status:** Planned — build in a fresh session ("implement docs/Receipt_Plan.md")
**Use case:** An insurer (Canada Life, August 2026) asked a client for proof of
payment for an e-transfer claim. The Financial Report / Payment Record is a tax
document — no letterhead, registration, or signature — and is the wrong vehicle
for third parties. A receipt is an identity-bearing, per-payment document, and
per-statement "settled in full" is a computable fact there (unlike on a
date-range report, where it would be an account-state attestation).

## Scope

A **Receipt** action on any recorded payment, producing a one-page PDF:

- Letterhead: logo, practice name/address/contact — same Settings fields the
  statement PDF uses (`pdf/statements.py` is the pattern; reuse its helpers)
- "Received from <client name> (file <n>)"
- Amount, date received, payment notes if any
- Applied to: statement #X ($a) — settled in full / partial; …; credit held $c
  (straight from `payment_allocations`; a NULL-portion row is the credit)
- Registration info and signature image, like a statement
- Footer: "Generated from EdgeCase records on <date>"

**Entry points:** a receipt icon beside the payment in the client file's
payment history, and on the payment's row in the Ledger. GET route
`/statements/payment/<entry_id>/receipt` (statements_bp — it owns payments).

**Out of scope:** emailing receipts (download only; attach manually if
needed); receipts for hand-entered Income rows with no allocation data (the
button appears only on modal-recorded payments — the receipt's substance IS
the allocation record; a hand-entered row would produce an empty shell).

## Tests (~5)

- Receipt PDF contains practice name, client name+file number, amount, date
- Allocation lines: one payment across two statements shows both, with
  "settled in full" only where portion total is fully covered
- Credit remainder line when overpaid
- Hand-entered income (no allocations): route 404s / button absent
- Registration + signature presence when configured

## Docs

- billing.html: proof-of-payment paragraph points at the Receipt (replacing
  the Payment Record framing — see below); note that the Financial Report
  filters on date *received*, so ranges must cover when payments landed, not
  when services were rendered
- CHANGELOG; Route_Reference regen

## Context: what was tried first (August 27, 2026)

A factual received-total summary line was added to the Payment Record and
reverted the same day: dressing a tax report in insurer-facing language was
the wrong direction — third parties need an identity-bearing document, and
the accounting report should stay an accounting report. Revert commit
references this plan.
