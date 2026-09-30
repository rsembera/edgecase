# AirLock — Online Intake & Consent Design Plan

**Status:** Design approved 2026-09-27. Phase 2 (EdgeCase side) in progress on branch `airlock`:
crypto, keypair storage and invitations done (`core/airlock_crypto.py`,
`core/db/airlock.py`); validation, mapping, PDFs and the all-or-nothing import
done (`core/airlock_import.py`, `pdf/airlock_records.py`); screens and the
admin-channel client done (`web/blueprints/airlock.py`, `core/airlock_client.py`),
tested against an in-memory stand-in server; form customization and the config
bundle done (`core/airlock_config.py`, the Forms page). **Phase 2 complete.**
Phase 3 (the server, repo `edgecase-airlock`): server core and admin API done
and tested end to end against EdgeCase; client form pages done
(`airlock/static/`: WebCrypto in `crypto.js`, tested in Node and in Chromium
through EdgeCase import). Deployed 2026-09-27: running on Sentinel as a
user service (public listener 127.0.0.1:8093 behind nginx; admin listener
100.116.129.95:8094, Tailscale only), deployed by `git push sentinel main`;
deployment files and steps in the AirLock repo's `deploy/` and README.
Pending: public hostname (DNS, then `deploy/setup_nginx.sh`), the real admin
key, and Richard's first live test.

**Admin API as EdgeCase calls it** (the server must match): `PUT
/admin/public-key {key_id, public_key}`; `PUT /admin/config <bundle>` (see
`core/airlock_config.build_bundle`: practice info, `logo_png` as base64 PNG or
null, `fields` [{name, label, show, required}], `questions`, `consent_text`,
`consent_version`, `config_version`; sent before every invitation and on every
save of the Forms page); `POST /admin/invitations {token_hash,
pin, required_forms, is_minor, expires_at, key_id}`; `DELETE
/admin/invitations/<token_hash>`; `GET /admin/submissions → {"submissions":
[{id, token_hash, form, key_id, config_version, consent_version, envelope,
received_at}]}` (`envelope` is the JSON text the browser produced); `DELETE
/admin/submissions/<id>`. Bearer auth; path segments fully percent-encoded.
**Name:** AirLock (repo `edgecase-airlock`, deployed to Sentinel).
**Source forms:** `/home/rick/Nexus/intake-consent-forms/Intake.pdf` and
`Consent.pdf` (Apollo). Their wording is the content; this plan is only the
delivery.

## What it does

A client whose file Richard has already opened (at inquiry) gets a link,
sent from that file. They open it on their phone or computer, fill in the
intake form and the consent form, and submit. Richard reviews their answers
beside what the file already holds; on import EdgeCase fills in the Profile
and attaches the signed consent as a PDF. No accounts, no passwords, no
portal to come back to.

## The one rule everything else follows

**Sentinel can never read a submission.** The browser encrypts each completed
form to a public key that EdgeCase generated. The private key exists only
inside EdgeCase's encrypted database. Sentinel stores ciphertext it cannot
open, plus the minimum metadata to route it.

If Sentinel is fully compromised, the attacker gets: hashes of outstanding
invitation tokens, opaque blobs, and timestamps. No names, no answers, no
mapping from token to person. That keeps the PHIPA weight in EdgeCase, where
it already lives, and makes Sentinel a dumb mailbox.

## Flow

1. **Issue.** In EdgeCase, Richard creates an invitation: the name and email
   he knows from the inquiry, which forms are required (default both), and
   whether the client is a minor. EdgeCase mints:
   - a 256-bit random token (the link), and
   - a 6-digit PIN.
   It stores both in its own database, sends Sentinel only
   `SHA-256(token)`, the PIN, the expiry, the required forms and the minor
   flag (over the admin channel), and shows Richard the link and PIN.
   Sentinel stores the PIN as an HMAC under its own secret, so the hashing
   happens there, not in EdgeCase.
2. **Deliver.** Richard emails the link and gives the PIN on the consult
   call (or by text). Two channels, so a forwarded or misdelivered email is
   not enough to fill in forms as the client.
3. **Unlock.** The link is `https://<host>/i#<token>`. The token is in the
   URL fragment, which browsers never send to the server, so it cannot land
   in nginx logs, proxy logs or a `Referer` header. Page JS reads it and
   POSTs `{token, pin}` to `/i/unlock`. Sentinel returns which forms are
   still outstanding, the current consent text and its version, and the
   public key.
4. **Fill and submit.** Each form is one sitting. On submit the browser
   encrypts the JSON payload and POSTs `{token, pin, form, ciphertext}`.
   Sentinel checks the token and PIN again, stores the blob, and marks that
   form done. No drafts are kept anywhere.
5. **Done.** When all required forms are in, the token stops working. The
   client sees a confirmation page and nothing else.
6. **Import.** EdgeCase (Settings → Intake → "Check for submissions", or on
   login if configured) pulls pending blobs over the admin channel,
   decrypts locally, fills in the invitation's client file, attaches the consent
   PDF, and then tells Sentinel to delete each blob it has safely committed.
   Delete only after the EdgeCase transaction commits; a crash mid-import
   means the blob is fetched again next time, and import is idempotent on
   submission ID.

## Crypto

- **Scheme:** ECDH P-256 → HKDF-SHA256 → AES-256-GCM, one ephemeral key per
  submission (ECIES-style). Browser side is WebCrypto only: no JavaScript
  library, nothing loaded from a CDN. Python side is `cryptography`, already
  in `requirements.txt`. No new dependency on either end.
  (libsodium sealed boxes would be equally good but add PyNaCl and a JS
  bundle. P-256 WebCrypto works in every current browser, including old
  iPhones.)
- **Associated data:** the GCM AAD binds the ciphertext to
  the invitation hash, form name, config version and consent version
  (newline-joined; exact bytes in `core/airlock_crypto.build_aad`), so a blob cannot be
  replayed under a different invitation or form.
- **Keys:** EdgeCase generates the keypair on first enabling the feature.
  Private key in the `settings` table (inside SQLCipher). Public key pushed
  to Sentinel with a key ID. Each blob carries its key ID. Rotating the
  keypair keeps the old private key until every invitation issued under it
  has expired.
- **Token:** 256-bit, `secrets.token_urlsafe(32)`. Stored on Sentinel as
  plain SHA-256; with that much entropy a slow hash buys nothing.
- **PIN:** stored on Sentinel as HMAC with a server-side secret. It is only
  6 digits, so this is not protection against a stolen database. It does
  not need to be: without the token the PIN is useless, and the database
  only has token hashes. The PIN exists to stop a forwarded link.
- **Comparisons:** constant-time everywhere (`hmac.compare_digest`).

## What each side stores

**EdgeCase (new table `intake_invitations`, the 16th; built 2026-09-27):**
`id, client_id (nullable), display_name, email, token, token_hash, pin,
required_forms, forms_done, is_minor, key_id, issued_at, expires_at, status
(issued | partial | complete | imported | revoked), imported_at, revoked_at`.
"Expired" is computed from `expires_at`, never stored, so no sweep job is
needed for a dead link to be dead. `client_id` is set when the invitation is
issued from the client file (decision 2), and names the file import fills in. Retention disposal deletes a
client's invitations with the rest of their record.

**Sentinel:**
- `invitations`: `token_hash, pin_hmac, required_forms, forms_done,
  is_minor, expires_at, failed_pin_attempts, locked`.
- `submissions`: `id, token_hash, form, key_id, config_version,
  consent_version, ciphertext, received_at`.
- `config`: the current bundle (branding, logo, field settings, additional
  questions, consent text) and its version.
- `public_keys`: `key_id, public_key`.
- Nothing else. No names, no emails, no IPs.

## The forms

Built as plain HTML from the current PDFs. Mobile first.

**Intake → Profile entry** (1:1, in the Profile's order):

| Form | EdgeCase |
|---|---|
| First / middle / last name (split on the web form) | `clients.first_name / middle_name / last_name` |
| Date of birth | `date_of_birth` |
| Gender (optional) | the Profile's existing Gender field (stored in the Profile entry's `content`) |
| Address | `address` |
| Email | `email` |
| Cell / Home / Work | `phone / home_phone / work_phone` |
| Which number can I text? | `text_number` |
| OK to leave a message | `ok_to_leave_message` |
| Preferred contact (email, call cell/home/work, text) | `preferred_contact` |
| Emergency contact name / phone / relationship | `emergency_contact_name / _phone / _relationship` |
| How did you hear about this practice | `referral_source` |
| Additional information | `additional_info` |
| Printed name / signature / date | attestation (typed name + checkbox + server timestamp) |

**Minor invitations** add a guardian section (guardian 1, optional
guardian 2) mapping to the existing `guardian1_*` / `guardian2_*` Profile
fields, and the consent is attested by the guardian. The section appears only
if the invitation was issued with `is_minor`.

**Consent.** The text is edited in EdgeCase and pushed to AirLock (see
Customization). The version and the full text shown are included
*inside* the encrypted payload, so EdgeCase renders exactly what the client
saw, not whatever the current file says. The client types their full name and
ticks "I have read and agree." EdgeCase renders a PDF (ReportLab, practice
letterhead as on statements) containing the full consent text, typed name,
consent version, submission timestamp and invitation ID, and attaches it to
the client file. A Communication entry records the import.

**Signature:** typed name plus checkbox. No drawn signatures: they add
complexity on phones and no legal weight.

**Earlier idea dropped:** hashing the client's IP into the consent record.
IPv4 hashes are trivially reversible, and the invitation token plus PIN is
stronger evidence of who submitted than an address anyway.

## Customization

Other therapists will need their own logo, letterhead and consent wording.
The intake form itself is **not** customizable (decided 2026-09-29): it is
the client-facing part of the Client Profile, and nothing else. Every answer
lands in a Profile field, so import is a lookup table and there is no form
builder, no second product.

**The intake form mirrors the Profile.** Same fields, same order, same
dropdown values (Text Number, OK to Leave Message, Preferred Contact). Labels
are fixed, worded for the client ("Which number can I text?" for Text
Number). Fields the practitioner fills in (file number, insurer, fees,
session defaults, meeting link, the guardians' payment split) are not on the
form. Required: first and last name and one phone or email; everything else
is optional. Text Number and Preferred Contact only offer choices the
client's own answers support (no "call my work phone" without one), and
import refuses a mismatch. The field list lives in
`core/airlock_import.INTAKE_FIELDS` and the server's
`airlock/validation.FIELDS`; a cross-repo test keeps them identical.

Earlier design (dropped 2026-09-29): per-field show/hide, required and
label settings, plus up to five free-text questions appended to Additional
Information. Removed because the form should be the Profile, filled in
remotely.

**Branding.** Practice name, credentials, address, phone, website and logo,
the same values EdgeCase already holds for statements. Rendered as the form
header, matching the paper forms.

**Consent text.** Plain text with headings, bullets and paragraphs, edited on
EdgeCase's AirLock Consent page.

**Everything is edited in EdgeCase, not on the server.** The
AirLock Consent page holds the consent text; branding is reused from
Practice Info. On save,
EdgeCase pushes a config bundle to AirLock over the admin channel
(`PUT /admin/config`), the same way it pushes the public key. AirLock has no
admin UI of its own to secure, there is one place to edit, and a
self-hosting therapist never touches the server after setup. Branding and
form layout are not sensitive, so storing them on Sentinel is fine.

**Versioning.** Each pushed bundle gets a version (content hash). The config
version and consent version are both included in each encrypted
submission's associated data, and the consent text as shown is inside it. Import
therefore knows exactly what the client saw even if the therapist changed
the form while an invitation was open. Because the payload carries what was
shown, AirLock only ever needs the current bundle.

**Safety of therapist-edited text.** The consent text is
rendered as text (consent Markdown through a sanitizing renderer, no raw
HTML). The logo is re-encoded on the EdgeCase side before upload (PNG,
size-capped), never served as the therapist's original file.

## Sentinel service

Flask, small. Two surfaces, separated at the network level:

**Public (nginx vhost, TLS):**
- `GET /i` — static form shell (HTML/CSS/JS, no third-party assets)
- `POST /i/unlock` — `{token, pin}` → outstanding forms, current config
  bundle (branding, fields, questions, consent text) and its version,
  public key
- `POST /i/submit` — `{token, pin, form, key_id, config_version,
  consent_version, ciphertext}`

**Admin (bound to the Tailscale interface only; not proxied publicly;
bearer key held in EdgeCase settings):**
- `POST /admin/invitations` · `DELETE /admin/invitations/<hash>`
- `GET /admin/submissions` · `DELETE /admin/submissions/<id>`
- `PUT /admin/public-key` · `PUT /admin/config`

**Hardening:**
- Rate limiting per IP and per token on `/i/unlock` and `/i/submit`. Five
  wrong PINs lock the invitation; Richard reissues from EdgeCase.
- Request size cap (ciphertext for a one-page form is a few KB; cap at
  64 KB).
- Strict CSP (`default-src 'self'`, no inline code, Trusted Types required), `Referrer-Policy: no-referrer`,
  `Cache-Control: no-store`, HSTS, no cookies at all.
- nginx access logging off for the whole AirLock vhost (the fragment keeps
  the token out of logs anyway; this also keeps client IPs out). nginx
  proxies only `/i`, `/i/unlock`, `/i/submit` and `/static/<file>`.
- Housekeeping (hourly, inside the service): delete expired invitations, and delete
  any submission older than 30 days that was never imported.
- Deploy: `git push` to Sentinel like the website; systemd unit;
  SQLite for the tables above.

**Self-hosting by other therapists:** everything Richard-specific (host,
Tailscale, letterhead) is configuration. The admin-channel requirement is
"reachable from the EdgeCase machine, not from the internet": Tailscale,
WireGuard, or an SSH tunnel all satisfy it. Documented, not automated.

## Lifecycle rules

- Invitations expire after **14 days** (configurable). Revocable any time
  from EdgeCase.
- A token dies when all required forms are in, when it expires, when it is
  revoked, or when it is locked by failed PINs.
- Re-sending: revoke and reissue. There is no "resend the same link."
- No drafts. Leaving the page loses the form. Both forms fit one sitting.

## Threat model (summary; the adversarial pass expands it)

| Threat | Mitigation |
|---|---|
| Sentinel compromised | Ciphertext only; no names; token hashes only |
| Link forwarded or misdelivered | PIN via second channel; lockout |
| Token brute force | 256-bit token; rate limiting |
| Replay a blob under another invitation/form | GCM associated data |
| Oversized or malformed ciphertext | Size cap; EdgeCase rejects on decrypt failure and reports, never partially imports |
| Hostile field content (script, huge strings, control chars) | Server never parses plaintext; EdgeCase validates and length-limits every field on import, escapes on render, same as manual entry |
| Admin API exposed | Not proxied publicly; Tailscale-only bind; bearer key |
| Token in logs / referrers | URL fragment; no-referrer; access log off |
| Import interrupted | Delete-after-commit; idempotent on submission ID |
| Laptop lost | Unchanged from today: the private key is inside SQLCipher |

## Phases

1. **This doc + threat model review.** Done when Richard signs off on the
   open questions.
2. **EdgeCase side** (3–4 sessions): keypair, `intake_invitations` table and
   migration, issue/revoke UI, Settings → AirLock (field toggles, labels,
   additional questions, consent text, config push), import routine with a
   local test harness that
   encrypts payloads the way the browser will, Profile mapping, consent PDF,
   Communication entry. Schema doc, Route Reference, CHANGELOG.
3. **Sentinel service** (3 sessions): new repo, routes, forms, WebCrypto
   encryption, nginx and systemd, deploy. A browser-to-EdgeCase round-trip
   test against the testing instance.
4. **Adversarial pass** (2 sessions): every row of the threat table
   attacked; every finding becomes a test. Security page for the website.

Estimate: 8–10 sessions. Phase 2 is independently useful: the import side
can be exercised end to end with the test harness before Sentinel exists.

## Considered and deferred

- **Client receipt downloads (2026-09-27).** A portal where clients log in to
  fetch receipts is rejected: it needs readable PHI or per-client keys on
  Sentinel, i.e. accounts. The compatible variant is one-time outbound
  delivery (EdgeCase encrypts the PDF with a fresh key carried in the link
  fragment; Sentinel stores ciphertext; deleted after download or a few
  days). Deferred: receipts are emailed today and no client has asked for
  anything else. Revisit if one does.

## Decisions (2026-09-27)

Phase 1 closed. Richard's answers to the open questions:

1. **Gender:** *(revised in build)* the Profile already has a Gender field
   (kept in the Profile entry's `content`), so no new column; the web label
   is editable
   (e.g. "Pronouns").
2. **Existing clients:** *(revised 2026-09-29)* invitations are sent from
   the client file, which Richard creates at inquiry (workflow: inquiry →
   client file → consult → intake and consent → first appointment). There is
   no standalone "new client" invitation and import never creates a client.
   Clients already in therapy have consent on file; no re-consent flow.
   Every invitation includes the intake: intake + consent, or intake only.
   *(2026-09-30)* One invitation per client at a time: while one is out or
   its forms await review, the client file shows "Waiting for client" (to the
   AirLock page) or "Review intake forms" instead of Send, and a new
   invitation is refused. Revoke, import or discard frees the client; an
   expired invitation is replaced by the next one.
3. **Expiry:** 14 days (configurable).
4. **Import trigger:** manual button only.
5. **Text-reminder checkbox:** not added. Consent text is versioned, so it
   can be added if the reminder service is ever built.
6. **Consent placement and import:** *(revised in build)* the Profile
   screen cannot show attachments, so import creates a locked **Upload**
   entry, "Intake & consent (AirLock)", carrying the intake PDF and the
   signed consent PDF, with provenance notes (invitation, typed names,
   versions). Each submission is shown on a review screen (Import / Discard)
   before anything is written, each answer beside what the file holds. The
   client's answer replaces the file's unless Richard ticks "Reject"
   for that field; an answer left blank never erases anything. A changed
   name updates the client; the file number never changes.
7. **Publication:** the AirLock repo stays private until the adversarial
   pass is done, then goes public. The EdgeCase side ships dormant (no UI
   beyond an "AirLock server" setting) until a server is configured.
