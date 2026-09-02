# Future Refinements

Ideas that aren't urgent and aren't scheduled. EdgeCase adds features only when a
real practice workflow demands one, so this list is deliberately short; most of
what lands in it either graduates into the CHANGELOG or gets declined. Completed
items are moved to the bottom rather than deleted.

**Last reviewed:** August 26, 2026, against v2.0.1.

---

## Backup System: External State File

**Priority:** Low
**Effort:** Medium (2-3 hours)
**Status:** Documented, not scheduled

Backup freshness state (`last-backup` hash and check time) still lives in the
manifest alongside backup metadata. EdgeCase's frequency-first checking avoids
the WAL-checkpoint false-positive problem in practice, but the cleaner pattern —
proven in Libram — is a small external state file written after backup creation,
so that checking database state never modifies the database and no
`refresh_hash_baseline()`-style discipline is needed at checkpoint sites (the
discipline MailRepo once missed, February 2026).

Not scheduled because the current approach works and EdgeCase is in production
with real client data. Worth doing if the backup internals are opened up for
some other reason, and worth doing in MailRepo at the same time. Background:
`docs/WAL_Checkpoint_Backup_Issue.md`; reference implementation in Libram's
`core/backup.py`.

---

## Continuing Education Tracker

**Priority:** Idea only
**Effort:** Unknown
**Status:** A thought, not a plan — no use-case pressure yet

CRPO registrants must track professional development, which today means a
spreadsheet or the College's own portal. A small CE log (activity, date, hours,
category, attachment for the certificate) would sit naturally beside the Ledger
and could export a summary for a QA audit. It passes the "practice management,
solo practitioner" test better than most ideas, but nobody has actually needed
it yet — including the author. It stays here until a real renewal cycle makes
the spreadsheet hurt.

---

## Per-Payment Receipt

**Status:** Promoted to a full plan — see `Receipt_Plan.md`. (The August 2026
Canada Life proof-of-payment request turned out not to be answerable by the
Payment Record: that is a tax document with no letterhead or signature. A
summary line added to it was reverted the same day.)

---

## SVG Icon Pipeline (queued for 2.1.0)

**Priority:** Ride along with the next release build
**Effort:** Small
**Status:** Artwork done (2026-09-01); plumbing deliberately deferred to a release week

Canonical vector artwork now lives in `packaging/icons/svg/` — `edgecase-mark.svg`
(the three-bar icon, colours sampled from the original raster: #00A1B3 /
#02B5C1 / #FEA00B) and `edgecase-wordmark.svg` (mark + type; note the wordmark
uses `<text>`, so convert to paths before using it anywhere font-unpredictable).

At 2.1.0 build time: regenerate the five hicolor PNGs from the mark
(`inkscape -w N`), install the SVG to `hicolor/scalable/apps/` in
`build_deb.sh`, use the mark as the website favicon, and note in the packaging
guides that the SVG is the master and rasters are generated. Deferred rather
than done now because packaging changes are only tested by building and
installing a package, which release week does anyway.

---

## CSS Architecture Review

**Priority:** Low
**Effort:** Medium
**Status:** Idea only

28 CSS files, ~7,800 lines, grown organically. The June 2026 pass documented the
architecture (`docs/CSS_Architecture.md`) and removed the worst duplication;
a fuller consolidation (shared component classes, fewer per-page files) remains
possible but has never blocked anything. Two rounds of `!important` display
rules fighting inline styles (AI Scribe, August 2026 Settings) suggest the
utility-class conventions should be applied consistently before more of those
accumulate.

---

# Completed

Kept for the record; details in CHANGELOG.md.

- **Stronger first-run password policy** — done. `MIN_PASSWORD_LENGTH = 12`
  enforced at database creation and password change. The original rationale
  (password entropy dominates every crypto parameter) still holds, though since
  crypto v3 a forgotten password is recoverable via recovery key; the GPU-
  cracking argument for length is unchanged.
- **Argon2id for attachment encryption** — done June 2026; superseded in August
  2026 by crypto v3 envelope encryption (random master key wrapped under
  password- and recovery-key-derived keys, AES-256-GCM attachments, HKDF file
  keys).
- **Test coverage expansion** — 41 tests at the original note, 656 at v2.0.1,
  with red-before-green regression tests and mutation-sealing as standing
  practice.
