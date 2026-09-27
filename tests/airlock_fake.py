"""In-memory stand-in for the AirLock server's admin API, shared by the AirLock
route and forms tests (the `airlock_server` fixture lives in conftest.py).

It implements the admin API as docs/Intake_Service_Plan.md records it and
plays the browser's part, encrypting submissions to the public key EdgeCase
pushed.
"""
import json
import uuid

from core import airlock_crypto as ac
from core.airlock_client import AirLockConnectionError


class FakeServer:
    def __init__(self):
        self.public_keys = {}
        self.invitations = {}
        self.submissions = []
        self.fail = set()          # method names that should raise
        self.calls = []

    def _maybe_fail(self, name):
        self.calls.append(name)
        if name in self.fail:
            raise AirLockConnectionError("Could not reach the AirLock server.")

    # admin API -------------------------------------------------------------
    def put_public_key(self, key_id, public_key):
        self._maybe_fail("put_public_key")
        self.public_keys[key_id] = public_key

    def put_config(self, bundle):
        self._maybe_fail("put_config")
        self.config = bundle

    def create_invitation(self, inv):
        self._maybe_fail("create_invitation")
        self.invitations[inv["token_hash"]] = {
            "token_hash": inv["token_hash"], "pin": inv["pin"],
            "required_forms": inv["required_forms"], "is_minor": inv["is_minor"],
            "expires_at": inv["expires_at"], "key_id": inv["key_id"], "revoked": False}

    def revoke_invitation(self, token_hash):
        self._maybe_fail("revoke_invitation")
        if token_hash in self.invitations:
            self.invitations[token_hash]["revoked"] = True

    def list_submissions(self):
        self._maybe_fail("list_submissions")
        return [dict(s) for s in self.submissions]

    def delete_submission(self, submission_id):
        self._maybe_fail("delete_submission")
        self.submissions = [s for s in self.submissions if s["id"] != submission_id]

    # the browser's part ------------------------------------------------------
    def submit(self, token_hash, form, payload, config_version="cfg-1",
               consent_version="consent-1", received_at=1_790_000_000, tamper=False):
        server_inv = self.invitations[token_hash]
        kid = server_inv["key_id"]
        aad = ac.build_aad(token_hash, form, config_version, consent_version)
        env = ac.encrypt_for_testing(json.dumps(payload).encode(),
                                     self.public_keys[kid], kid, aad)
        if tamper:
            e = json.loads(env)
            ct = bytearray(ac.b64u_decode(e["ct"]))
            ct[0] ^= 1
            e["ct"] = ac.b64u_encode(bytes(ct))
            env = json.dumps(e)
        self.submissions.append({
            "id": uuid.uuid4().hex, "token_hash": token_hash, "form": form,
            "key_id": kid, "config_version": config_version,
            "consent_version": consent_version, "envelope": env,
            "received_at": received_at})
