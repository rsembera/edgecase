# Online Intake & Consent — Design Plan

**Status:** DESIGN, 2026-09-24. Not started. Nothing here is built.
**Working name:** `edgecase-intake` (separate repo, deployed to Sentinel).
**Source forms:** `/home/rick/Nexus/intake-consent-forms/Intake.pdf` and
`Consent.pdf` (Apollo). Their wording is the content; this plan is only the
delivery.

## What it does

A prospective client gets a link. They open it on their phone or computer,
fill in the intake form and the consent form, and submit. The next time
Richard imports, EdgeCase creates the client file with the Profile filled in
and the signed consent attached as a PDF. No accounts, no passwords, no
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
   `SHA-256(token)`, `HMAC(pin)`, the expiry, the required forms and the
   minor flag, and shows Richard the link and PIN.
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
   decrypts locally, creates or updates the client, attaches the consent
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
  `invitation_hash || form_name || consent_version`, so a blob cannot be
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

**EdgeCase (new table `intake_invitations`, the 15th):**
`id, client_id (nullable), display_name, email, token, pin, required_forms,
is_minor, key_id, issued_at, expires_at, status
(issued | partial | complete | imported | revoked | expired), imported_at`.
`client_id` is set when the invitation is issued for an existing client
(e.g. re-consent after a fee change) or when import creates one.

**Sentinel:**
- `invitations`: `token_hash, pin_hmac, required_forms, forms_done,
  is_minor, expires_at, failed_pin_attempts, locked`.
- `submissions`: `id, token_hash, form, key_id, consent_version,
  ciphertext, received_at`.
- `public_keys`: `key_id, public_key`.
- Nothing else. No names, no emails, no IPs.

## The forms

Built as plain HTML from the current PDFs. Mobile first.

**Intake → Profile entry** (fields map almost 1:1; the Profile was clearly
designed around this form):

| Form | EdgeCase |
|---|---|
| First / middle / last name (split on the web form) | `clients.first_name / middle_name / last_name` |
| Date of birth | `date_of_birth` |
| Gender (optional) | **open question**, see below |
| Address | `address` |
| Home / Work / Cell | `home_phone / work_phone / phone` |
| Email | `email` |
| Preferred contact (Phone / Email / Text) | `preferred_contact` |
| OK to leave a message | `ok_to_leave_message` |
| Emergency contact name / relationship / phone | `emergency_contact_name / _relationship / _phone` |
| How did you hear about this practice | `referral_source` |
| Additional information | `additional_info` |
| Printed name / signature / date | attestation (typed name + checkbox + server timestamp) |

**Minor invitations** add a guardian section (guardian 1, optional
guardian 2) mapping to the existing `guardian1_*` / `guardian2_*` Profile
fields, and the consent is attested by the guardian. The section appears only
if the invitation was issued with `is_minor`.

**Consent.** The text lives in the Sentinel repo as versioned files
(`consent/v1.md`, …). The version and the full text shown are included
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

## Sentinel service

Flask, small. Two surfaces, separated at the network level:

**Public (nginx vhost, TLS):**
- `GET /i` — static form shell (HTML/CSS/JS, no third-party assets)
- `POST /i/unlock` — `{token, pin}` → outstanding forms, consent text and
  version, public key
- `POST /i/submit` — `{token, pin, form, key_id, consent_version,
  ciphertext}`

**Admin (bound to the Tailscale interface only; not proxied publicly;
bearer key held in EdgeCase settings):**
- `POST /admin/invitations` · `DELETE /admin/invitations/<hash>`
- `GET /admin/submissions` · `DELETE /admin/submissions/<id>`
- `PUT /admin/public-key`

**Hardening:**
- Rate limiting per IP and per token on `/i/unlock` and `/i/submit`. Five
  wrong PINs lock the invitation; Richard reissues from EdgeCase.
- Request size cap (ciphertext for a one-page form is a few KB; cap at
  64 KB).
- Strict CSP (`default-src 'self'`), `Referrer-Policy: no-referrer`,
  `Cache-Control: no-store`, HSTS, no cookies at all.
- nginx access logging off for the `/i` location (the fragment keeps the
  token out of logs anyway; this also keeps client IPs out).
- Housekeeping job (systemd timer): delete expired invitations, and delete
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
   migration, issue/revoke UI, import routine with a local test harness that
   encrypts payloads the way the browser will, Profile mapping, consent PDF,
   Communication entry. Schema doc, Route Reference, CHANGELOG.
3. **Sentinel service** (3 sessions): new repo, routes, forms, WebCrypto
   encryption, nginx and systemd, deploy. A browser-to-EdgeCase round-trip
   test against the testing instance.
4. **Adversarial pass** (2 sessions): every row of the threat table
   attacked; every finding becomes a test. Security page for the website.

Estimate: 8–10 sessions. Phase 2 is independently useful: the import side
can be exercised end to end with the test harness before Sentinel exists.

## Open questions for Richard

1. **Gender:** add a `gender` column to the Profile, or fold the answer into
   `additional_info`?
2. **Existing clients:** should invitations also work for a current client
   (re-consent after a fee or policy change), updating their Profile? The
   table allows it; the import UI would need a "review changes" step.
3. **Expiry:** 14 days right?
4. **Import trigger:** manual button only, or also a check on login?
5. **Text-reminder consent:** add an optional "OK to send appointment
   reminders by text" checkbox to the intake now, so the possible reminder
   service (see `Reminder_Service_Plan.md`) has consent on file from the
   start?
