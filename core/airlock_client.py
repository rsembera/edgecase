"""AirLock admin-channel client (EdgeCase → AirLock server).

The server's admin routes (docs/Intake_Service_Plan.md, "Sentinel service")
are reachable only over the private network (Tailscale or equivalent) and
authenticated with a bearer key held in EdgeCase's encrypted settings.

Nothing sent here identifies a client: invitations go up as token hashes plus
the PIN (which the server stores as an HMAC), and submissions come down as
ciphertext only EdgeCase can open.

Settings:
    airlock_server_url   admin base URL, e.g. http://sentinel.tailnet:8081
    airlock_public_url   the address clients open, e.g. https://forms.example.ca
    airlock_admin_key    bearer key
    airlock_ttl_days     default invitation expiry

Uses urllib only: no new dependency for a handful of JSON calls.
"""
import json
import re
import urllib.error
import urllib.parse
import urllib.request

TIMEOUT_SECONDS = 15
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_ENVELOPE_BYTES = 64 * 1024      # as core/airlock_crypto and the server
# Submission ids, token hashes, form names, key ids and versions are short
# plain tokens by construction. Versions may be empty (no consent text).
_LABEL = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
_VERSION = re.compile(r"[A-Za-z0-9_-]{0,128}\Z")
# The server's admin key is 43 URL-safe characters (secrets.token_urlsafe(32)).
# Anything else pasted into Settings (other text on the clipboard) is refused
# rather than sent, where a non-Latin-1 character would crash the request.
_ADMIN_KEY = re.compile(r"[A-Za-z0-9_-]{1,200}\Z")
BAD_KEY_MESSAGE = ("That isn't an AirLock admin key (it should be letters, digits, "
                   "- and _ only).")


def valid_admin_key(key: str) -> bool:
    return bool(_ADMIN_KEY.match(key or ""))


class AirLockConnectionError(Exception):
    """The server could not be reached or refused the request. The message
    is safe to show to the practitioner."""


def validate_base_url(url: str, label: str) -> str:
    url = (url or "").strip().rstrip("/")
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(f"{label} must start with http:// or https://")
    if parsed.query or parsed.fragment or parsed.params:
        raise ValueError(f"{label} must be a plain address")
    return url


class AirLockClient:

    def __init__(self, base_url: str, admin_key: str, timeout=TIMEOUT_SECONDS):
        self.base_url = validate_base_url(base_url, "AirLock server address")
        if not admin_key:
            raise ValueError("AirLock admin key is not set")
        self.admin_key = admin_key
        self.timeout = timeout

    # -- transport -------------------------------------------------------

    def _request(self, method, path, body=None):
        if not valid_admin_key(self.admin_key):
            raise AirLockConnectionError(
                "The saved AirLock admin key isn't a valid key. Enter it again in "
                "Settings → AirLock.")
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + path, data=data, method=method,
            headers={"Authorization": f"Bearer {self.admin_key}",
                     "Content-Type": "application/json",
                     "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise AirLockConnectionError(
                    "The AirLock server refused the admin key.") from None
            raise AirLockConnectionError(
                f"The AirLock server returned an error ({e.code}).") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise AirLockConnectionError(
                "Could not reach the AirLock server.") from None
        if len(raw) > MAX_RESPONSE_BYTES:
            raise AirLockConnectionError("The AirLock server sent too much data.")
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except ValueError:
            raise AirLockConnectionError(
                "The AirLock server sent an unreadable reply.") from None

    # -- admin API ---------------------------------------------------------

    def put_public_key(self, key_id, public_key):
        self._request("PUT", "/admin/public-key",
                      {"key_id": key_id, "public_key": public_key})

    def put_config(self, bundle):
        """Branding, field settings, questions and consent text (see
        core/airlock_config.build_bundle). Replaces the server's copy."""
        self._request("PUT", "/admin/config", bundle)

    def create_invitation(self, inv):
        self._request("POST", "/admin/invitations", {
            "token_hash": inv["token_hash"],
            "pin": inv["pin"],
            "required_forms": inv["required_forms"],
            "is_minor": inv["is_minor"],
            "expires_at": inv["expires_at"],
            "key_id": inv["key_id"],
        })

    def revoke_invitation(self, token_hash):
        self._request("DELETE", "/admin/invitations/" + urllib.parse.quote(token_hash, safe=""))

    def list_submissions(self):
        """[{id, token_hash, form, key_id, config_version, consent_version,
        envelope, received_at}]. Shape-checked; anything else raises."""
        reply = self._request("GET", "/admin/submissions")
        subs = reply.get("submissions") if isinstance(reply, dict) else None
        if not isinstance(subs, list):
            raise AirLockConnectionError("The AirLock server sent an unreadable reply.")
        out = []
        for s in subs:
            try:
                sub = {
                    "id": str(s["id"]),
                    "token_hash": str(s["token_hash"]),
                    "form": str(s["form"]),
                    "key_id": str(s["key_id"]),
                    "config_version": str(s.get("config_version") or ""),
                    "consent_version": str(s.get("consent_version") or ""),
                    "envelope": s["envelope"],
                    "received_at": int(s["received_at"]),
                }
                if not (all(_LABEL.match(sub[k]) for k in ("id", "token_hash", "form", "key_id"))
                        and all(_VERSION.match(sub[k])
                                for k in ("config_version", "consent_version"))
                        and isinstance(sub["envelope"], str)
                        and len(sub["envelope"]) <= MAX_ENVELOPE_BYTES):
                    raise ValueError("not a submission")
            except (KeyError, TypeError, ValueError):
                raise AirLockConnectionError(
                    "The AirLock server sent an unreadable reply.") from None
            out.append(sub)
        return out

    def delete_submission(self, submission_id):
        self._request("DELETE", "/admin/submissions/" + urllib.parse.quote(str(submission_id), safe=""))


def client_from_settings(db):
    """AirLockClient for this install, or None if AirLock is not configured."""
    url = db.get_setting("airlock_server_url", "")
    key = db.get_setting("airlock_admin_key", "")
    if not url or not key:
        return None
    return AirLockClient(url, key)


def is_enabled(db) -> bool:
    """AirLock screens appear only once a server is configured."""
    return bool(db.get_setting("airlock_server_url", "")
                and db.get_setting("airlock_admin_key", ""))


def invitation_link(db, token) -> str:
    base = db.get_setting("airlock_public_url", "").rstrip("/")
    return f"{base}/i#{token}" if base else ""
