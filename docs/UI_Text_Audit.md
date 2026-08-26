# EdgeCase — UI Text Audit

> **Historical record** — August 2026 copy audit, applied in the v2.0.0 release cycle.

**Date:** 2026-08-22
**Scope:** Helper text, hints, tooltips, empty states, confirmation dialogs, and error/status messages across `web/templates/`, `web/static/js/`, and the Flask blueprints (`web/blueprints/`, `core/`).
**Method:** Targeted sweep for the classes and patterns EdgeCase actually uses for user-facing copy (`helper-text`, `help-text`, `hint`, `note`, `subtitle`, `empty-state`, `text-muted`, `title="…"`, `placeholder="…"`, `alert()`, `confirm()`, and the `'error'`/`'message'` keys returned by the JSON endpoints), then a close read of every hit.

**Overall impression:** the copy is in good shape. Placeholders, form-field help text, and the JSON error strings returned by the blueprints are almost all short and specific — someone was clearly deliberate about this (the comment block in `_password_policy.html` is a good example of that care). The issues below are the exceptions, not the pattern. They fall into four small groups: one badly overloaded helper-text block, a couple of sentences doing two jobs at once, a pair of genuinely empty error messages, and one place where two flows describe the same instruction two different ways.

---

## 1. Overloaded helper text

### `web/templates/add_edit_type.html:70–71` — Retention Period

**Current:**
> How long to keep inactive client records after last contact. Enter 0 for indefinite retention (no auto-deletion prompts). For minors, records are retained until the longer of: this period after last contact, OR this period after the client's 18th birthday. If your jurisdiction uses age 21 as the age of majority, add 3 years to your retention period.

This is four separate facts run into one paragraph inside a single `<small>` tag: what the field does, what 0 means, the minor-client exception, and a jurisdiction-specific adjustment. It's the single densest piece of copy in the app, and it's exactly the kind of text a therapist needs to actually read and get right.

**Suggested revision** (splits the general case from the minor exception, which is the natural reading order):
> How long to keep inactive records after last contact. Enter 0 to keep indefinitely.
> For minors: whichever is longer — this period after last contact, or after they turn 18 (add 3 years if your jurisdiction sets majority at 21).

Same information, but the two audiences (general case vs. minors) are visually separate, and "no auto-deletion prompts" — which just restates what "indefinite" means — is dropped.

---

## 2. Helper text doing two unrelated jobs in one sentence

### `web/templates/entry_forms/profile.html:299` — Fee fields

**Current:**
> Fill any two fields and the third calculates automatically. Leave blank if client only attends couples/family/group sessions.

The auto-calc mechanic and the "this whole section is optional for group clients" caveat are unrelated facts stapled together with a period. A reader skimming for "how do I fill this in" gets the caveat as an afterthought, or misses it.

**Suggested revision:**
> Fill any two fields — the third calculates automatically.

...and move "Leave blank if client only attends couples/family/group sessions" to sit above the field group as its own line, or into the section label, since it's really a "does this section apply to you" question, not a fee-calculation instruction.

### `web/templates/entry_forms/item.html:114` — Guardian split

**Current:**
> Specify how this item should be split between guardians. Must equal the total above.

**Suggested revision:**
> How this item splits between guardians — must total the amount above.

Minor, but "Specify how... should be split" is a wordy way to say "how it splits," and joining the two sentences with a dash reads faster than a period does for a single-thought hint.

### `web/templates/add_client.html:39` — Starting Session Number

**Current:**
> For new clients, leave at 0.<br />For migrated clients: if they've had 15 sessions elsewhere, enter 15 (next session will be #16)

**Suggested revision:**
> For new clients, leave at 0.<br />For migrated clients, enter their most recent session count (e.g. 15 → next session is #16).

The existing version works, but "if they've had 15 sessions elsewhere, enter 15" is circular phrasing (it uses the example number as if it were a variable). The revision states the rule once and lets the example illustrate it.

---

## 3. Error messages with no actual information

### `web/static/js/expense.js:252–253` and `web/static/js/income.js:244–245` — Delete-entry failure

**Current:**
```js
.then(r => r.ok ? window.location.href = '/ledger' : alert('Error'))
.catch(() => alert('Error'))
```

Both the ledger-expense and ledger-income "delete entry" handlers show a bare `alert('Error')` on any failure — no indication that a *delete* failed, let alone why. Every other delete handler in the app is more specific: `file-upload.js` says "Error deleting attachment," `manage_links.js` says "Error deleting link group." These two are the outliers.

**Suggested revision:**
```js
.then(r => r.ok ? window.location.href = '/ledger' : alert('Could not delete this entry. Please try again.'))
.catch(() => alert('Could not delete this entry. Please try again.'))
```

Matches the phrasing pattern already used elsewhere for delete failures.

---

## 4. Same instruction, two different wordings

### `core/database.py`-adjacent restore flows: `web/blueprints/backups.py:185` vs. `web/static/js/backups.js:562`

Two different restore paths tell the user to restart the app to finish, in two different phrasings:

- Backend (`backups.py:185`, used by the restore-point flow in `restore.html`): *"Restore prepared. Close EdgeCase and reopen to complete."*
- Frontend fallback (`backups.js:562`, used by the Settings-page restore flow): *"Restore prepared. Please restart EdgeCase to complete the restore."*

Neither is wrong, but a user who hits both screens (or remembers one and reads the other) will notice the app describes the same required action two ways — "close and reopen" vs. "restart" — which reads as unclear rather than deliberate.

**Suggested revision:** pick one phrasing and use it in both places. Since "reopen" is more literal for a desktop app whose window doesn't necessarily fully quit, e.g.:
> Restore prepared. Close EdgeCase and reopen it to finish.

---

## What did *not* make this list

For context on how the sweep went: 101 `placeholder="…"` attributes, 120 `helper-text`/`hint`/`note`/`subtitle` blocks, 37 `<small>` tags, 19 tooltip `title="…"` attributes, and 127 JSON `'error'`/`'message'` strings across the blueprints were read in full. The large majority — things like "Total amount received," "Person or organization who paid," "Statement is not open for this payer," the recovery-key and encryption-upgrade screens, the password-policy hint, and the delete-confirmation modals ("Are you sure you want to delete this file? This cannot be undone.") — are already short, specific, and consistent, and don't need touching.

One thing that looked like a bug but isn't: `settings.html`'s confirmation-modal template defaults to the placeholder text "Are you sure?" — but that default is never actually shown; `showConfirmModal()` always passes a specific message ("Delete practice logo?" etc.) before the modal opens. No change needed there.

---

## Suggested priority

1. `add_edit_type.html` retention text — highest value, most-read compliance-relevant field.
2. The two bare `alert('Error')` calls — quick fix, real user confusion on failure.
3. `profile.html` / `item.html` helper-text splits — small clarity wins.
4. Restore-message wording — cosmetic consistency, no urgency.
