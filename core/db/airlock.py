"""AirLock invitations and keypair (EdgeCase side).

See docs/Intake_Service_Plan.md. An invitation is what Richard issues to a
prospective client: a link token plus a PIN, valid for a fixed window, for one
or both forms. EdgeCase is the only place the token-to-person mapping exists;
the AirLock server is told the token's hash and nothing about who it is for.

Keypairs live in the settings table (inside SQLCipher):
    airlock_keys           JSON {key_id: {private_pem, public, created_at,
                                          retired_at}}
    airlock_active_key_id  the key new invitations are issued under
A retired key is kept until no open invitation references it, so rotating
never strands a client halfway through the forms.
"""
import json
import time

from core import airlock_crypto

DEFAULT_TTL_DAYS = 14
MAX_TTL_DAYS = 90
MAX_NAME_LEN = 200
MAX_EMAIL_LEN = 254

OPEN_STATUSES = ("issued", "partial")
CLOSED_STATUSES = ("complete", "imported", "revoked", "expired")

_COLUMNS = ("id, client_id, display_name, email, token, token_hash, pin, "
            "required_forms, forms_done, is_minor, key_id, issued_at, "
            "expires_at, status, imported_at, revoked_at")


class AirLockMixin:

    # ------------------------------------------------------------------
    # keypair
    # ------------------------------------------------------------------

    def _airlock_keys(self) -> dict:
        raw = self.get_setting("airlock_keys", "")
        return json.loads(raw) if raw else {}

    def _save_airlock_keys(self, keys: dict):
        self.set_setting("airlock_keys", json.dumps(keys, sort_keys=True))

    def airlock_ensure_keypair(self) -> str:
        """Active key id, generating the first keypair if there is none."""
        active = self.get_setting("airlock_active_key_id", "")
        if active and active in self._airlock_keys():
            return active
        return self.airlock_rotate_keypair()

    def airlock_rotate_keypair(self) -> str:
        """Generate a new active keypair; the previous one is retired, not
        deleted. Returns the new key id."""
        keys = self._airlock_keys()
        now = int(time.time())
        for meta in keys.values():
            if meta.get("retired_at") is None:
                meta["retired_at"] = now
        kid, private_pem, public = airlock_crypto.generate_keypair()
        keys[kid] = {"private_pem": private_pem, "public": public,
                     "created_at": now, "retired_at": None}
        self._save_airlock_keys(keys)
        self.set_setting("airlock_active_key_id", kid)
        return kid

    def airlock_public_key(self):
        """(key_id, public_b64u) of the active key, for pushing to AirLock."""
        kid = self.airlock_ensure_keypair()
        return kid, self._airlock_keys()[kid]["public"]

    def airlock_private_keys(self) -> dict:
        """{key_id: private_pem} for every key still held, for decryption."""
        return {kid: meta["private_pem"] for kid, meta in self._airlock_keys().items()}

    def airlock_prune_retired_keys(self, now=None) -> list:
        """Drop retired keys that no open, unexpired invitation uses.
        Returns the key ids removed."""
        now = int(time.time()) if now is None else now
        keys = self._airlock_keys()
        conn = self.connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT DISTINCT key_id FROM intake_invitations "
            f"WHERE status IN ({','.join('?' * len(OPEN_STATUSES))}) "
            "AND expires_at > ?",
            (*OPEN_STATUSES, now))
        in_use = {row[0] for row in cur.fetchall()}
        removed = [kid for kid, meta in keys.items()
                   if meta.get("retired_at") is not None and kid not in in_use]
        for kid in removed:
            del keys[kid]
        if removed:
            self._save_airlock_keys(keys)
        return removed

    # ------------------------------------------------------------------
    # invitations: reads
    # ------------------------------------------------------------------

    @staticmethod
    def _invitation_row(cur, row):
        if not row:
            return None
        inv = dict(zip([d[0] for d in cur.description], row))
        inv["required_forms"] = [f for f in inv["required_forms"].split(",") if f]
        inv["forms_done"] = [f for f in (inv["forms_done"] or "").split(",") if f]
        inv["is_minor"] = bool(inv["is_minor"])
        return inv

    @staticmethod
    def invitation_effective_status(inv, now=None) -> str:
        """Stored status, except that an open invitation past its expiry
        reads as 'expired'. Expiry is computed, not swept, so nothing has to
        run on a schedule for a dead link to be dead."""
        now = int(time.time()) if now is None else now
        if inv["status"] in OPEN_STATUSES and now >= inv["expires_at"]:
            return "expired"
        return inv["status"]

    def get_intake_invitation(self, invitation_id):
        cur = self.connect().cursor()
        cur.execute(f"SELECT {_COLUMNS} FROM intake_invitations WHERE id = ?",
                    (invitation_id,))
        return self._invitation_row(cur, cur.fetchone())

    def get_intake_invitation_by_hash(self, token_hash):
        cur = self.connect().cursor()
        cur.execute(f"SELECT {_COLUMNS} FROM intake_invitations WHERE token_hash = ?",
                    (token_hash,))
        return self._invitation_row(cur, cur.fetchone())

    def list_intake_invitations(self, include_closed=False, now=None):
        """Newest first. Open means issued/partial AND not yet expired."""
        cur = self.connect().cursor()
        cur.execute(f"SELECT {_COLUMNS} FROM intake_invitations "
                    "ORDER BY issued_at DESC, id DESC")
        rows = [self._invitation_row(cur, r) for r in cur.fetchall()]
        if include_closed:
            return rows
        return [r for r in rows
                if self.invitation_effective_status(r, now) in OPEN_STATUSES]

    # ------------------------------------------------------------------
    # invitations: writes
    # ------------------------------------------------------------------

    def create_intake_invitation(self, display_name, email=None,
                                 required_forms=airlock_crypto.FORMS,
                                 is_minor=False, ttl_days=DEFAULT_TTL_DAYS,
                                 client_id=None, now=None):
        """Mint an invitation. Returns the full row, including the token and
        PIN Richard gives the client. Invitations are issued from a client
        file (decided 2026-09-29), so client_id names the file the import
        will fill in; the screens always pass it."""
        display_name = (display_name or "").strip()
        if not display_name:
            raise ValueError("A name is required.")
        if len(display_name) > MAX_NAME_LEN:
            raise ValueError("Name is too long.")
        email = (email or "").strip() or None
        if email and len(email) > MAX_EMAIL_LEN:
            raise ValueError("Email is too long.")
        forms = [f for f in airlock_crypto.FORMS if f in set(required_forms or ())]
        if set(required_forms or ()) - set(airlock_crypto.FORMS):
            raise ValueError("Required forms must be intake and/or consent.")
        # The intake is always required: it is what the import applies.
        if "intake" not in forms:
            raise ValueError("An invitation must include the intake form.")
        try:
            ttl_days = int(ttl_days)
        except (TypeError, ValueError):
            raise ValueError("Expiry must be a whole number of days.") from None
        if not 1 <= ttl_days <= MAX_TTL_DAYS:
            raise ValueError(f"Expiry must be between 1 and {MAX_TTL_DAYS} days.")

        now = int(time.time()) if now is None else now
        kid = self.airlock_ensure_keypair()
        token = airlock_crypto.new_token()
        conn = self.connect()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO intake_invitations
                (client_id, display_name, email, token, token_hash, pin, required_forms,
                 forms_done, is_minor, key_id, issued_at, expires_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, '', ?, ?, ?, ?, 'issued')
        """, (client_id, display_name, email, token, airlock_crypto.token_hash(token),
              airlock_crypto.new_pin(), ",".join(forms), int(bool(is_minor)),
              kid, now, now + ttl_days * 86400))
        conn.commit()
        return self.get_intake_invitation(cur.lastrowid)

    def revoke_intake_invitation(self, invitation_id, now=None) -> bool:
        """Close an invitation without importing it: revoking an open one, or
        discarding a complete one on the review screen. Returns False if it
        was already imported or revoked. Revoking an expired one is allowed
        and just records the decision."""
        inv = self.get_intake_invitation(invitation_id)
        if inv is None or inv["status"] not in OPEN_STATUSES + ("complete",):
            return False
        now = int(time.time()) if now is None else now
        conn = self.connect()
        conn.execute("UPDATE intake_invitations SET status = 'revoked', "
                     "revoked_at = ? WHERE id = ?", (now, invitation_id))
        conn.commit()
        return True

    def record_intake_form_received(self, invitation_id, form):
        """Note that a form's submission has been imported or queued.
        Moves issued -> partial -> complete. Idempotent per form."""
        if form not in airlock_crypto.FORMS:
            raise ValueError("unknown form")
        inv = self.get_intake_invitation(invitation_id)
        if inv is None:
            raise ValueError("unknown invitation")
        if form not in inv["required_forms"]:
            raise ValueError("form was not requested on this invitation")
        done = set(inv["forms_done"]) | {form}
        status = inv["status"]
        if status in OPEN_STATUSES:
            status = "complete" if done >= set(inv["required_forms"]) else "partial"
        ordered = ",".join(f for f in airlock_crypto.FORMS if f in done)
        conn = self.connect()
        conn.execute("UPDATE intake_invitations SET forms_done = ?, status = ? "
                     "WHERE id = ?", (ordered, status, invitation_id))
        conn.commit()
        return self.get_intake_invitation(invitation_id)

    def mark_intake_imported(self, invitation_id, client_id, now=None):
        now = int(time.time()) if now is None else now
        conn = self.connect()
        conn.execute("UPDATE intake_invitations SET status = 'imported', "
                     "client_id = ?, imported_at = ? WHERE id = ?",
                     (client_id, now, invitation_id))
        conn.commit()

    def delete_unsent_intake_invitation(self, invitation_id) -> bool:
        """Remove an invitation the server never accepted. Only an 'issued'
        invitation with no forms received qualifies: it was never delivered
        to anyone, so there is nothing to keep a record of."""
        conn = self.connect()
        cur = conn.cursor()
        cur.execute("DELETE FROM intake_invitations WHERE id = ? AND "
                    "status = 'issued' AND forms_done = ''", (invitation_id,))
        conn.commit()
        return cur.rowcount == 1
