# entries.py Refactor Plan

**Status:** Planned (not started)
**Author:** Claude + Richard
**Created:** 2026-06-20
**Context:** Runner-up god-file after the completed `core/database.py` split (Step 3).

---

## 1. Goal & scope

Split `web/blueprints/entries.py` (~1,924 lines, 16 routes) into a `web/blueprints/entries/`
package, one module per entry type, behind the same `entries_bp` blueprint. Pure structural
tidy: **no behaviour change, no URL change, no template change.** Same maintainability win as
the database.py split — find the session routes in `sessions.py` instead of scrolling 1,900
lines, and changing one entry type stops risking the others.

This is optional and has no forcing function. It is a good weekend job because the Step 2
route tests already give it a net.

## 2. Why this is NOT like the database.py split

database.py was a **class**, so mixins worked — every method shared `self`. `entries.py` is a
Flask **blueprint**: route handlers plus a module-level `db` global and shared helper functions.
Mixins do not apply. The pattern here is **split the route functions across modules that all
register onto one shared `entries_bp`**, with the shared `db`/helpers in a `common.py`.

The crux is the module-level `db` global (set by `init_blueprint` at login). Split modules
cannot each keep their own `db = None` — only the one that `init_blueprint` writes to would get
set. Section 6 solves this.

## 3. Current structure (inventory)

Total ~1,924 lines. Sections and routes:

| Section | Lines (approx) | Route functions |
|---------|----------------|-----------------|
| Header: imports, helpers, blueprint, `init_blueprint`, `renumber_sessions` | 1–106 | — |
| Profile | 107–455 | `edit_profile` |
| Session | 456–898 | `create_session`, `edit_session` |
| Communication | 899–1112 | `create_communication`, `edit_communication` |
| Absence | 1113–1353 | `create_absence`, `edit_absence` |
| Item | 1354–1591 | `create_item`, `edit_item` |
| Upload | 1592–1704 | `create_upload`, `edit_upload` |
| Attachment | 1705–1869 | `download_attachment`, `view_attachment`, `delete_attachment` |
| Redaction | 1870–1924 | `redact_entry`, `view_redacted_entry` |

**Shared, module-level (must end up in `common.py`):**
- Pure helpers (no db): `safe_float`, `safe_money`, `safe_int`, `resolve_attachment_path`
- The blueprint: `entries_bp = Blueprint('entries', __name__)`
- The db global + `init_blueprint(database)`
- `renumber_sessions(client_id)` — uses `db`; called by **sessions** AND **redaction**
  (redacting a session triggers a renumber)

**How `app.py` wires it (the contract to preserve):**
- `from web.blueprints.entries import entries_bp`  (line 68)
- `from web.blueprints.entries import init_blueprint as init_entries`  (line 251)
- `init_entries(db)` (262); `app.register_blueprint(entries_bp)` (282)

So **only two names** must remain importable from `web.blueprints.entries`: `entries_bp` and
`init_blueprint`.

## 4. Hard constraints (break any of these and the app breaks)

1. **Blueprint name stays `'entries'`.** Endpoints are `entries.<function_name>`.
2. **Every route function keeps its exact name.** Templates call
   `url_for('entries.create_session')`, `url_for('entries.download_attachment')`, etc. — 16
   functions, ~30 call sites across `web/templates/`. Rename one and that page 500s on render.
3. **`entries_bp` and `init_blueprint` importable from `web.blueprints.entries`.** The package
   `__init__.py` must re-export both so `app.py` is untouched.
4. **All 16 routes still register.** A route only registers if its module is imported, so
   `__init__.py` must import every route module.

## 5. Target structure

```
web/blueprints/entries/
    __init__.py        # re-exports entries_bp + init_blueprint; imports every route module
    common.py          # entries_bp, db state + init_blueprint + get_db(), shared helpers,
                       #   renumber_sessions
    profile.py         # edit_profile
    sessions.py        # create_session, edit_session
    communications.py  # create_communication, edit_communication
    absences.py        # create_absence, edit_absence
    items.py           # create_item, edit_item
    uploads.py         # create_upload, edit_upload
    attachments.py     # download_attachment, view_attachment, delete_attachment
    redaction.py       # redact_entry, view_redacted_entry
```

`web/blueprints/entries.py` (the file) is deleted; `web/blueprints/entries/` (the package)
replaces it. Imports like `from web.blueprints.entries import entries_bp` resolve to the package
`__init__.py` unchanged.

`__init__.py` skeleton:
```python
from web.blueprints.entries.common import entries_bp, init_blueprint  # noqa: F401

# Import route modules for their decorator side effects (registers routes on entries_bp).
from web.blueprints.entries import (  # noqa: F401,E402
    profile, sessions, communications, absences,
    items, uploads, attachments, redaction,
)
```

## 6. The shared-db mechanism (the crux)

Keep the live `db` in `common.py` and expose a **getter**. Route handlers read it once at the
top; the rest of each handler body is unchanged.

`common.py`:
```python
from flask import Blueprint
# ... shared imports (os, time, shutil, Path, etc.) ...

entries_bp = Blueprint('entries', __name__)   # name MUST stay 'entries'

_db = None

def init_blueprint(database):
    global _db
    _db = database

def get_db():
    return _db

# pure helpers: safe_float / safe_money / safe_int / resolve_attachment_path  (moved verbatim)

def renumber_sessions(client_id):
    db = get_db()
    # ... body verbatim ...
```

Each route module:
```python
from web.blueprints.entries.common import (
    entries_bp, get_db, safe_money, safe_int, resolve_attachment_path, renumber_sessions,
)
# ... plus the route's own imports (render_template, request, redirect, url_for, etc.) ...

@entries_bp.route('/client/<int:client_id>/session', methods=['GET', 'POST'])
def create_session(client_id):
    db = get_db()          # <-- the ONE added line per handler
    # ... rest of the body verbatim (still uses bare `db.`) ...
```

**Why the getter and not `from common import db`:** `from common import db` binds the name once
at import time (to `None`) and never updates. `get_db()` reads the live value at call time. The
one-line `db = get_db()` at the top of each handler keeps every handler body byte-identical
below it — minimal churn, low risk.

## 7. Sequencing (incremental, test + commit after each — same discipline as database.py)

Each step keeps the suite green and is its own commit. The app is runnable at every step.

- **Step 0 (optional but recommended): widen the GET-form net first.** The current entries tests
  hit POST paths well but the create/edit **GET form-render** paths are only lightly covered
  (mainly via the breadth smoke). Add a small parametrized test that GETs each create + edit form
  (`/client/<id>/session`, `/client/<id>/communication`, …) with a seeded client and asserts 200.
  This directly guards the `url_for`/endpoint-name risk — if a function gets renamed or a template
  endpoint breaks, the form render fails here. ~30 minutes; do it before touching the blueprint.

- **Step A: create the package skeleton (no route moves yet).** Convert `entries.py` → the
  `entries/` package. Move the shared header (blueprint, `_db`/`init_blueprint`/`get_db`, the four
  pure helpers, `renumber_sessions`) into `common.py`. Put **all 16 route functions, unchanged,**
  into a single temporary `routes.py` that imports from `common` and adds `db = get_db()` at the
  top of each. `__init__.py` re-exports `entries_bp`/`init_blueprint` and imports `routes`. Run
  suite (185). Commit. *This proves the package + getter pattern end-to-end before any domain
  split.*

- **Steps B–I: extract one entry type per commit.** Move that type's routes from `routes.py` into
  its own module (`sessions.py`, etc.), update `__init__.py` to import it instead, run suite,
  commit. Order easy → hard: `redaction` → `attachments` → `uploads` → `items` → `absences` →
  `communications` → `profile` → `sessions` (sessions last; it owns the `renumber_sessions`
  coupling and is the biggest). After the last extraction `routes.py` is empty — delete it.

- **Step J: docs.** Update `EdgeCase_Project_Status.md` + `CHANGELOG.md`.

## 8. The safety net (already mostly built in Step 2)

These existing tests exercise the entries routes end-to-end and will catch regressions:
- `test_entries_lifecycle.py` — session create/lock/no-op/amendment, redaction, consultation
  numbering
- `test_entry_types_roundtrip.py` — communication / absence / item / profile create→edit
- `test_attachments_lifecycle.py` — upload → download → view → delete
- `test_routes_breadth.py` — read-only pages render 200

**Thin spots to know about:** the create/edit **GET form** renders (Step 0 closes this), and the
`edit_upload` path. Net is strong enough to refactor against; Step 0 makes it airtight.

## 9. Risks & gotchas (entries-specific)

1. **Endpoint/function-name preservation (highest risk).** Templates use
   `url_for('entries.<fn>')` for all 16 routes. Moving functions verbatim keeps their names, and
   the blueprint name stays `'entries'`, so endpoints are unchanged — but do not "tidy" a function
   name while moving it. Verify with the endpoint check in Section 10.
2. **Route registration via imports.** A route registers only when its module is imported. If
   `__init__.py` forgets to import a module, those routes silently vanish (404) — the route-count
   check catches this.
3. **The `db` global liveness.** Use `get_db()` inside handlers, never `from common import db`.
   `renumber_sessions` (in common) must also call `get_db()` internally.
4. **Circular imports.** Route modules import *from* `common`; `common` imports *nothing* from
   the route modules. Only `__init__.py` imports the route modules, and it does so after
   `common` is fully defined. Keep this direction strict.
5. **`.py` → package move.** Delete `entries.py` and create `entries/`. Clear stale bytecode
   (`find web/blueprints -name '__pycache__' -prune -exec rm -rf {} +`) so an old `entries.pyc`
   can't shadow the package. Git will record it as delete + adds.
6. **`renumber_sessions` is shared** by sessions and redaction — it lives in `common`, imported by
   both. Don't duplicate it into `sessions.py`.
7. **Per-module imports.** Each route module needs only the imports its handlers actually use
   (e.g., `attachments.py` needs `send_file`, `decrypt_file_to_bytes`, `BytesIO`,
   `resolve_attachment_path`; `uploads.py` needs `save_uploaded_files`, `secure_filename`).
   Copy the imports the moved handlers reference; an unused-import is harmless, a missing one is a
   `NameError` the suite will flag (as it did in the database.py split).

## 10. Verification (run at every step, and a full pass at the end)

- **Suite green:** `venv/bin/python -m pytest -q` — 185 passing throughout.
- **Route count unchanged (16):**
  ```python
  from web.app import app
  n = len([r for r in app.url_map.iter_rules() if r.endpoint.startswith('entries.')])
  assert n == 16, n
  ```
- **Endpoint set unchanged:** snapshot `sorted(r.endpoint for r in app.url_map.iter_rules()
  if r.endpoint.startswith('entries.'))` before starting; assert identical after. This is the
  definitive guard for the `url_for` risk.
- **App boots:** the suite imports `web.app` and drives routes, so green ≈ boots. Before Monday,
  a 60-second live click-through (open a client, add/edit a session, upload + download an
  attachment, redact a test entry) is the human-eyes confirmation.

## 11. Effort

Comparable to the database.py split: ~9 modules (common + 8 type modules), mechanical relocation
with one `db = get_db()` line added per handler, suite after each. Roughly an afternoon. The net
is already there; Step 0 (~30 min) makes it airtight. No behaviour change, fully reversible per
commit, and `entries.py` is not in any critical path the way `database.py` was — lower stakes
than Step 3.

## 12. Out of scope

- No change to route logic, URLs, templates, or the data layer.
- Not touching `statements.py` (the other large blueprint) — separate future candidate if
  desired, same pattern.
