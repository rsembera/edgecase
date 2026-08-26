# Payment Allocation — Design Plan

> **Historical record** — design for the August 2026 payment allocation system, shipped in v2.0.0. The implementation matches this plan; see Architecture_Decisions.md for the rationale as built.

**Status:** IMPLEMENTED 2026-08-09. Kept as the design record; the built
behaviour is summarised in CHANGELOG.md and Architecture_Decisions.md.
Where the build diverged from this plan, the plan is marked inline.
**Raised:** 2026-08-09 (Rick)
**Prerequisite:** none — independent of the crypto v3 work

---

## Divergences from this plan, and why

- **The column is `entry_id`, not `income_entry_id`** — refunds allocate
  too, and a refund is an expense-class entry.
- **`payment_allocations` also carries `client_id`, `guardian_number` and
  `is_credit`.** The plan's "no extra column needed" holds for computing an
  unallocated amount, but not for *scoping* a credit to a payer: an income
  entry knows its client only by `source`, and its guardian not at all.
  `is_credit` distinguishes a row created by spending credit from one
  created by a payment arriving, which is what lets the PDF show a
  "Credit applied" line.
- **Credit is read from explicit NULL-portion rows, never derived** as
  "total minus allocations" — the derivation invents money for any legacy
  entry that has no rows at all.
- **No refund path was built.** Rick's judgement (2026-08-09) is that a
  credit sitting against the next statement answers every real case, and a
  client insisting on cash is rare enough to handle as a manual Ledger
  expense. The unreachable December 2025 refund branch was deleted with
  `mark_paid`; statement generation now declines to produce the
  net-negative statement that branch existed to settle.

---

## The problem

Carry-forward made statements *present* a balance-forward total while the
system continued to *track* open items per statement. Those two models
disagree at exactly one moment: when the client pays.

Client owes $100 from July and $200 from August. The August statement PDF
says "Previous balance $100 / Current charges $200 / **Total $300**". The
client pays $300 in one transfer on 1 September.

The system has two open `statement_portions` rows. `mark_paid` takes a single
`portion_id`. So Rick has to split the payment by hand and record it twice,
and neither recorded payment matches the amount that actually arrived.

The data is not wrong — its granularity is finer than the demand that was
sent. The fix belongs at the moment of payment entry.

### Confirmed by reading the code

- `statement_portions.amount_due` holds **only that statement's own
  charges**. Carry-forward is presentation only: `PDFGenerator.
  _build_balance_summary` renders "Previous balance / Combined" from
  `db.get_prior_outstanding(...)`, and its docstring already says
  *"Neither figure changes how payments apply."*
- `get_prior_outstanding` (core/db/clients.py:364) sums
  `amount_due - amount_paid` over the client's OTHER portions with status
  `sent` or `partial`, scoped to the same `guardian_number`. Guardian
  scoping and the `ready` exclusion are load-bearing and must be preserved
  by anything that touches allocation ordering.
- `mark_paid` (web/blueprints/statements/payments.py:46) updates one portion
  via `apply_payment`, then inserts ONE ledger entry carrying
  `statement_id`. That single FK is what cannot express one payment against
  two statements.
- `apply_payment` (core/billing.py:110) already handles partials and
  negatives (refunds) in exact Decimal. **It does not need to change** — it
  gets called in a loop instead of once.
- `prorata_tax` pro-rates tax against a statement's own total, so it must be
  computed **per allocation**, not once on the payment total. Two statements
  can have different tax rates.

---

## Decision taken: one payment = one ledger entry

Best practice, and confirmed as the direction: **record what happened.** One
payment arrived, on one date, by one method, for $300. That it settles two
invoices is a receivables fact, not a second income event.

This is how QuickBooks / Xero / Sage all model "Receive Payment": one amount
against the account, ticked off against invoices. The cash book gets one
line; the sub-ledger carries the split.

Practical reason it matters: Rick doesn't reconcile routinely, but a CRA
review is exactly when every ledger line should map one-to-one onto a bank
line without explanation. Splitting a deposit for internal convenience
creates work under time pressure later.

**Rick to confirm with his accountant** before build — orthodox, but worth a
second opinion on presentation of professional income.

---

## Schema change (additive only — NOT a migration in the crypto sense)

```sql
CREATE TABLE IF NOT EXISTS payment_allocations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    income_entry_id INTEGER NOT NULL,   -- entries.id of the payment
    portion_id INTEGER NOT NULL,        -- statement_portions.id settled
    amount REAL NOT NULL,               -- may be negative (refunds)
    tax_amount REAL,                    -- prorata_tax for THIS portion
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_alloc_income ON payment_allocations(income_entry_id);
CREATE INDEX IF NOT EXISTS idx_alloc_portion ON payment_allocations(portion_id);
```

Goes in `_initialize_schema()`, which already runs `CREATE TABLE IF NOT
EXISTS` on every open. **No migration runner, no backup gate, no rollback
window** — it appears on next launch. This is nothing like crypto v1→v2→v3.

`entries.statement_id` **stays**. For single-statement payments it keeps
pointing at the one statement, so nothing that reads it breaks. Treat it as
"the statement this payment primarily relates to" (first/only allocation) and
let `payment_allocations` be authoritative when present.

### Backfill

Every existing income entry with a non-null `statement_id` gets one
allocation row for its full amount. Idempotent, runs once, guarded by a
`NOT EXISTS` check. Cheap — this is a solo practice, not millions of rows.

Write it as a standalone function with its own test rather than inline in
schema init, so it can be re-run and verified.

---

## Behaviour

### Recording a payment

1. Rick opens the client's statements and clicks Record Payment (entry point
   moves from a single portion to the **client**).
2. Enters total received, date, method, notes.
3. App proposes an **oldest-first** allocation across open portions
   (`sent` and `partial`, same guardian scoping as `get_prior_outstanding`).
4. Rick sees the proposed split and can **override** any line — "this cheque
   is for August only" must be expressible.
5. On save: one income entry for the full amount; one `payment_allocations`
   row per portion touched; `apply_payment` per portion to update
   `amount_paid` / `status`; `prorata_tax` computed **per allocation** and
   summed into the entry's `tax_amount`.

Oldest-first is the standard default and matches what a client believes they
are paying off. Override exists because that belief is sometimes wrong.

### Overpayment / credit

$350 against $300 outstanding. Do **not** over-pay the last portion — that
makes `amount_paid > amount_due` and corrupts every outstanding calculation.

Simplest correct handling: allocate $300, leave $50 unallocated on the income
entry, and surface it as a **credit on the client's account** — shown on the
client file and offered as a pre-fill against the next statement.

Requires: a way to read "unallocated = entry.total_amount - SUM(allocations)".
No extra column needed.

### Refunds

`apply_payment` already takes negatives. A refund allocates negatively
against a specific portion. Keep refunds single-portion at first — a refund
spanning statements is not a real use case yet, and inventing one violates
the no-features-without-use-cases rule.

### Write-offs

`write_off_statement` (payments.py:176) is untouched — it settles a portion
without a payment, so it creates no allocation.

---

## What else has to change

| Area | Change |
|---|---|
| `core/db/` | new `payment_allocations` accessors; `get_client_outstanding_portions(client_id, guardian_number)` for the allocation proposal |
| `statements/payments.py` | `mark_paid` becomes `record_payment` taking an amount + allocation list; keep the old single-portion path working during transition |
| Statements UI | payment modal moves from per-portion to per-client with an editable split table |
| `pdf/ledger_report.py` | Payment Record currently matches income by `source` file number OR the `statement_id` chain — should prefer `payment_allocations` when present. **Re-verify the per-client filter still selects exactly the right rows.** |
| Client file | show credit balance if any unallocated amount exists |
| `get_prior_outstanding` | no change expected, but re-test — it is what the PDF's Previous balance depends on |

---

## Testing

- Lump sum across two statements → one income entry, two allocations,
  both portions correct, tax pro-rated per statement (**different tax rates
  on the two statements** — this is where a single prorata call would be
  silently wrong)
- Partial lump sum ($150 against $300) → oldest fully paid, next partial
- Manual override ignoring oldest-first
- Overpayment → credit, and `amount_paid` never exceeds `amount_due`
- Credit auto-applied to the next statement, shown as an explicit line
- **A credit cannot be spent twice** — generating two statements in the same
  batch must not both consume the same unallocated amount
- Credit scoped to the same guardian: guardian 1's overpayment must not
  reduce guardian 2's statement
- Guardian-split statements: allocation must not cross payers
- Refund against an allocated portion
- Backfill idempotent; running twice creates no duplicates
- Payment Record report unchanged for legacy single-statement payments and
  correct for allocated ones
- `get_prior_outstanding` unchanged for `ready` exclusion and guardian
  scoping

---

## Decisions taken (2026-08-09)

**Credit balance: auto-apply to the next statement, as an explicit line.**

Rendered next to "Previous balance" as `Credit applied  -$50.00`, using the
same `_build_balance_summary` machinery. Not silent, not a surprise.

The argument is symmetry. Carry-forward already pulls prior *debits* onto the
next statement without asking. A credit is the same thing with the opposite
sign. Auto-carrying what the client owes while making credits wait for the
practitioner to remember them is asymmetric — and asymmetric in the
practitioner's favour, which is the wrong direction on a clinical bill.

Consequence for build: statement generation must consult unallocated credit
for that client + guardian scope and consume it by writing allocation rows,
so a credit cannot be spent twice.

**Payment entry: per-client only. The per-portion path is retired.**

A single-statement payment is not a separate case, it is the degenerate one:
one open portion, the proposal allocates 100% to it, Rick confirms. Same
number of clicks.

Keeping both would mean two UIs and two code paths, and the per-portion path
IS the defect being fixed — it records a payment against one statement when
the money settled several. Two doors here is exactly the scope creep the
project's restraint rule exists to prevent.

The `mark_paid` backend entry point may remain briefly so existing tests keep
passing, but nothing in the UI should reach it once `record_payment` lands,
and it should be removed in the same release rather than left as a second way
to do the same thing.

**One entry per deposit** is settled — orthodox, not a blocker. Worth Rick
mentioning to his accountant in passing; not a gate on building.

---

## Deliberately NOT doing

- **Balance-forward client account.** Conceptually cleaner but breaks the
  `statement_id` linkage the Payment Record depends on and loses the ability
  to say which month's fees a payment settled.
- **Supersession** (August absorbs July's portion). Tidy, but destroys
  per-month history and makes cross-boundary partials messy.
- Multi-portion refunds, until a real case appears.
