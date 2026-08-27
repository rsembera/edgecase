# Learning Record — Implementation Plan

**Status:** Planned, queued for the week of August 31, 2026
**Use case:** CRPO Quality Assurance Program requires registrants to log at least
40 hours of learning over each two-year cycle, with at least one didactic and one
experiential activity, documented with evidence and a reflection per activity.
The College's own template is a fillable PDF the registrant must keep themselves.
EdgeCase already stores dated, attachment-bearing, encrypted records — this is
one more record type, for the practitioner instead of a client.
Reference: CRPO QA Program → Professional Development: Learning Record
(template of December 2023, saved alongside this plan if needed).

## Scope

One new practice-level entry type (`learning`), a Learning Record page in the
style of the Ledger, a nav-card button, and a cycle-hours summary. Nothing else.

**In scope for v1: PDF export.** The record exists to be shown to CRPO — the
QA program requires it in the portfolio, producible on request — so an
unexportable tracker wouldn't fulfill its own use case. EdgeCase's own layout
(ledger_report.py as the precedent), not a pixel copy of the College's fillable
template: one block per activity (name, dates, hours, type badge, description,
evidence/attachment list) with the reflection underneath, the cycle summary at
the top, and a "prepared from EdgeCase records on <date>" footer. The
requirement is the fields, not the formatting; the College's template revs
(current one is dated December 2023) and our own layout ages better.
Date-range option like the ledger report, defaulting to the current cycle.

**Explicitly out of scope for v1:** reminders/notifications; multiple
historical cycles UI (old entries remain queryable by date, and the export's
date range covers past cycles; the on-page summary shows the current cycle
only).

## Data model

No new tables. `entries` already supports practice-level rows (`client_id` NULL,
as Income/Expense do). Add one class value and four columns:

- `class = 'learning'`
- `date_begun TEXT` — ISO date (the CRPO template's "date started")
- `date_finished TEXT` — ISO date, nullable ("if applicable, date completed").
  The entry's main date (used for timeline grouping, like the Ledger's) is
  `date_finished` if set, else `date_begun`.
- `hours REAL` — decimal hours (CRPO counts halves)
- `learning_type TEXT` — `didactic` | `experiential`
- `reflection TEXT` — the CRPO "impact on your practice" box, distinct from
  description

Field mapping to the CRPO template: Activity name → `description`; Activity
description → `content`; Documentation → existing encrypted attachments
(certificates, receipts, journal notes); everything else as above.

Migration: plain `ALTER TABLE ... ADD COLUMN` guarded by a PRAGMA check, same
pattern as previous column additions. No backfill needed.

One new settings key: `qa_cycle_start` (ISO date). The CRPO cycle is two years
from this date; the summary computes the window from it.

## Locking

Learning entries are **never locked** (like Upload/Income/Expense): they are the
practitioner's own administrative records with no clinical or financial
implications, and hours/reflections get corrected. Edit history still applies.
Update the "Never lock" list in Architecture_Decisions.md accordingly.

## Blueprint and routes

New `learning_bp` (small, Ledger-shaped), registered in `web/app.py` (count
becomes 12 — update the website generator note and technical.html when this
ships):

- `GET  /learning` — the page
- `GET  /learning/export` — PDF export (date range params, default current cycle)
- `GET/POST /learning/new` — create
- `GET/POST /learning/<id>` — edit
- `POST /learning/<id>/delete` — delete (confirm modal)
- `POST /api/learning/cycle-start` — save `qa_cycle_start`

Attachment upload/download reuses the existing entry-attachment routes; nothing
new needed.

## UI

**Entry point: nav card goes 3×2.** Manage ▾ is supposed to be client
operations, but Logout was wedged into it when the card ran out of room —
adding Learning there too would grow the junk drawer. Instead: six text+icon
buttons on the card (Settings, Backup, Ledger, Statements, Learning, Logout),
three per row, and Manage ▾ shrinks back to purely client operations (Add
Client / Edit Types / Edit Links). Keep text labels — the six words are short,
"Ledger" vs "Statements" is ambiguous as icons alone, and hover-only labels
would be the app's sole hidden-meaning UI. Icon-only 3×2 is the fallback if
three-across doesn't fit the card at real sizes; judge on the testing instance.
Logout takes the bottom-right slot, visually quieter (subdued colour), so the
card doesn't read as six equal destinations when one is an exit. Learning icon
`graduation-cap`.

**Page (`learning.html`):** Ledger layout recycled — year/month groups,
expand/collapse, row = date · name · type badge (Didactic/Experiential) · hours ·
attachment count. Summary card at top:

> **Current cycle:** 23.5 / 40 hours · Didactic ✓ · Experiential ✗
> Cycle began 2025-04-01 [edit]

If `qa_cycle_start` is unset, the summary shows a one-line prompt to set it.
Hours sum entries whose main date falls inside the current two-year window;
the two checkmarks require ≥1 entry of each type in the window.

**Form (`entry_forms/learning.html`):** Name*, Type* (dropdown), Date begun*,
Date finished, Hours*, Description, Reflection (textarea, labelled with the
CRPO wording "impact on your practice"), attachments. Unsaved-changes guard
like every other form.

## Tests (~12–15)

- Migration adds columns; idempotent on re-run
- CRUD round-trip incl. NULL `client_id` and nullable `date_finished`
- Cycle math: window from `qa_cycle_start`; hours sum; per-type presence;
  entry on the window boundary; unset cycle start
- Learning entries never lock; excluded from statements/unbilled and from the
  Ledger page query (class filters — regression, red first, against a planted
  learning entry leaking into the Ledger)
- Attachment on a learning entry encrypts/decrypts round-trip
- Export contains every CRPO field (name, dates, hours, type, description,
  evidence, reflection) and the cycle summary; date-range filter respected

## Documentation

- CHANGELOG entry; Database_Schema.md (+4 columns), Route_Reference.md
  (regenerate), Navigation_Map counts, Architecture_Decisions locking list
- Website: entry-types.html (practice-level entries section), features.html one
  line, docs.html index; regenerate schema/routes pages
- Future_Refinements.md: remove the CE tracker item; keep a note that a second
  practitioner-level record type would justify promoting this into a
  "My Practice" file concept

## Order of work (one session)

1. Migration + model constants, tests red→green
2. Blueprint + form + page, ruff/JS gates
3. Nav card 3×2 (Logout in, quieter styling; Manage ▾ reduced to client ops); review on the testing instance before proceeding
4. Cycle summary + settings key, tests
5. PDF export (ledger_report.py pattern), test asserts all CRPO fields and the
   reflection appear in extracted text
6. Docs + website touch-ups, commit per step

**Estimate:** one focused session (~4–5 h), dominated by template work with
seven precedents.
