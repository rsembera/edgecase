"""AirLock screens, driven end to end against a stand-in server.

FakeServer implements the admin API from docs/Intake_Service_Plan.md in
memory and plays the browser's part (encrypting submissions to the public key
EdgeCase pushed). Every route runs for real against the test database.
"""
import json
import re
import uuid

import pytest

from core import airlock_client
from core import airlock_crypto as ac
from core.airlock_client import AirLockConnectionError

from tests import test_airlock_import as fx


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


@pytest.fixture
def server(app_db, monkeypatch):
    fake = FakeServer()
    app_db.set_setting("airlock_server_url", "http://sentinel.test:8081")
    app_db.set_setting("airlock_public_url", "https://forms.example.ca")
    app_db.set_setting("airlock_admin_key", "k" * 32)
    monkeypatch.setattr(airlock_client, "client_from_settings", lambda db: fake)
    return fake


def _issue(client, name="Ada L.", email="ada@example.com", forms="both", minor=False):
    data = {"display_name": name, "email": email, "forms": forms, "ttl_days": "14"}
    if minor:
        data["is_minor"] = "1"
    return client.post("/airlock/invitations", data=data)


def _latest(app_db):
    return app_db.list_intake_invitations(include_closed=True)[0]


def _submit_both(server, inv, **intake_overrides):
    server.submit(inv["token_hash"], "intake", fx.intake_payload(**intake_overrides))
    server.submit(inv["token_hash"], "consent", fx.consent_payload())


# ---------------------------------------------------------------------------
# dormant until configured
# ---------------------------------------------------------------------------

def test_dormant_without_a_server(client, app_db):
    r = client.get("/airlock")
    assert r.status_code == 302 and "/settings#airlock" in r.headers["Location"]
    assert b"AirLock</a>" not in client.get("/").data
    assert b'href="/airlock"' not in client.get("/").data


def test_menu_item_appears_once_configured(client, server):
    assert b'href="/airlock"' in client.get("/").data


# ---------------------------------------------------------------------------
# settings
# ---------------------------------------------------------------------------

def test_settings_save_and_key_is_write_only(client, app_db):
    r = client.post("/api/airlock_settings", json={
        "server_url": "http://sentinel:8081/", "public_url": "https://forms.example.ca",
        "admin_key": "secret-key", "ttl_days": "21"})
    assert r.get_json()["success"]
    got = client.get("/api/airlock_settings").get_json()
    assert got == {"server_url": "http://sentinel:8081",
                   "public_url": "https://forms.example.ca",
                   "has_admin_key": True, "ttl_days": "21"}
    assert "secret-key" not in json.dumps(got)
    # blank key keeps the stored one
    client.post("/api/airlock_settings", json={
        "server_url": "http://sentinel:8081", "public_url": "https://forms.example.ca",
        "admin_key": "", "ttl_days": "21"})
    assert app_db.get_setting("airlock_admin_key") == "secret-key"


@pytest.mark.parametrize("body", [
    {"server_url": "ftp://x", "public_url": "https://f.ca", "admin_key": "k"},
    {"server_url": "http://x", "public_url": "javascript:alert(1)", "admin_key": "k"},
    {"server_url": "http://x", "public_url": "https://f.ca?x=1", "admin_key": "k"},
    {"server_url": "http://x", "public_url": "https://f.ca", "admin_key": ""},
    {"server_url": "http://x", "public_url": "https://f.ca", "admin_key": "k", "ttl_days": 0},
])
def test_settings_validation(client, app_db, body):
    r = client.post("/api/airlock_settings", json=body)
    assert r.status_code == 400
    assert app_db.get_setting("airlock_server_url") == ""


def test_turn_off(client, app_db, server):
    assert client.post("/api/airlock_settings", json={"disable": True}).get_json()["success"]
    assert not airlock_client.is_enabled(app_db)


def test_test_connection_pushes_the_key(client, app_db, server):
    r = client.post("/api/airlock_test", json={})
    kid = r.get_json()["key_id"]
    assert server.public_keys == {kid: app_db.airlock_public_key()[1]}
    server.fail.add("put_public_key")
    r = client.post("/api/airlock_test", json={})
    assert r.status_code == 502 and "Could not reach" in r.get_json()["error"]


# ---------------------------------------------------------------------------
# issuing and revoking
# ---------------------------------------------------------------------------

def test_issue_sends_only_hash_and_pin(client, app_db, server):
    r = _issue(client)
    inv = _latest(app_db)
    assert r.status_code == 302
    assert r.headers["Location"].endswith(f"/airlock/invitations/{inv['id']}?new=1")
    sent = server.invitations[inv["token_hash"]]
    assert sent["pin"] == inv["pin"]
    blob = json.dumps(sent)
    assert "Ada" not in blob and "example.com" not in blob and inv["token"] not in blob

    page = client.get(f"/airlock/invitations/{inv['id']}?new=1").data.decode()
    assert f"https://forms.example.ca/i#{inv['token']}" in page
    assert inv["pin"] in page


def test_issue_failure_leaves_nothing(client, app_db, server):
    server.fail.add("create_invitation")
    r = _issue(client)
    assert r.status_code == 502
    assert b"was not created" in r.data
    assert app_db.list_intake_invitations(include_closed=True) == []


def test_issue_validation_error(client, app_db, server):
    r = _issue(client, name="")
    assert r.status_code == 400 and b"name is required" in r.data
    assert server.calls == []


def test_revoke(client, app_db, server):
    _issue(client)
    inv = _latest(app_db)
    r = client.post(f"/airlock/invitations/{inv['id']}/revoke")
    assert "msg=revoked" in r.headers["Location"]
    assert app_db.get_intake_invitation(inv["id"])["status"] == "revoked"
    assert server.invitations[inv["token_hash"]]["revoked"]


def test_revoke_when_server_unreachable(client, app_db, server):
    _issue(client)
    inv = _latest(app_db)
    server.fail.add("revoke_invitation")
    r = client.post(f"/airlock/invitations/{inv['id']}/revoke")
    assert "msg=revoke_remote_failed" in r.headers["Location"]
    assert app_db.get_intake_invitation(inv["id"])["status"] == "revoked"


# ---------------------------------------------------------------------------
# check, review, import, discard
# ---------------------------------------------------------------------------

def test_full_flow(client, app_db, server):
    app_db.set_setting("file_number_format", "manual")
    _issue(client)
    inv = _latest(app_db)
    _submit_both(server, inv)

    r = client.post("/airlock/check")
    assert "checked=2" in r.headers["Location"]
    assert app_db.get_intake_invitation(inv["id"])["status"] == "complete"
    listing = client.get("/airlock").data.decode()
    assert f"/airlock/review/{inv['id']}" in listing

    review = client.get(f"/airlock/review/{inv['id']}").data.decode()
    assert "Lovelace" in review and "I agree to psychotherapy." in review
    assert 'name="file_number"' in review

    r = client.post(f"/airlock/review/{inv['id']}/import",
                    data={"type_id": "1", "file_number": "AL-001"})
    assert r.status_code == 302
    cid = int(re.search(r"/client/(\d+)", r.headers["Location"]).group(1))
    assert app_db.get_client(cid)["file_number"] == "AL-001"
    assert server.submissions == []
    assert app_db.get_intake_invitation(inv["id"])["status"] == "imported"


def test_import_with_automatic_numbering(client, app_db, server):
    app_db.set_setting("file_number_format", "prefix-counter")
    _issue(client)
    inv = _latest(app_db)
    _submit_both(server, inv)
    client.post("/airlock/check")
    assert b"Assigned automatically" in client.get(f"/airlock/review/{inv['id']}").data
    r = client.post(f"/airlock/review/{inv['id']}/import", data={"type_id": "1"})
    cid = int(re.search(r"/client/(\d+)", r.headers["Location"]).group(1))
    assert app_db.get_client(cid)["file_number"] == "0001"


def test_manual_number_collision_is_reported(client, app_db, server):
    app_db.set_setting("file_number_format", "manual")
    app_db.add_client({"file_number": "TAKEN", "first_name": "T", "last_name": "N",
                       "type_id": 1})
    _issue(client)
    inv = _latest(app_db)
    _submit_both(server, inv)
    client.post("/airlock/check")
    r = client.post(f"/airlock/review/{inv['id']}/import",
                    data={"type_id": "1", "file_number": "TAKEN"})
    assert r.status_code == 400 and b"already exists" in r.data
    assert len(server.submissions) == 2
    assert app_db.get_intake_invitation(inv["id"])["status"] == "complete"


def test_import_cleanup_failure_is_reported_and_healed(client, app_db, server):
    app_db.set_setting("file_number_format", "manual")
    _issue(client)
    inv = _latest(app_db)
    _submit_both(server, inv)
    client.post("/airlock/check")
    server.fail.add("delete_submission")
    r = client.post(f"/airlock/review/{inv['id']}/import",
                    data={"type_id": "1", "file_number": "CF-1"})
    assert "msg=cleanup_failed" in r.headers["Location"]
    assert len(server.submissions) == 2
    server.fail.clear()
    client.post("/airlock/check")          # next check removes them
    assert server.submissions == []


def test_tampered_submission_cannot_be_imported(client, app_db, server):
    _issue(client)
    inv = _latest(app_db)
    server.submit(inv["token_hash"], "intake", fx.intake_payload(), tamper=True)
    server.submit(inv["token_hash"], "consent", fx.consent_payload())
    client.post("/airlock/check")
    page = client.get(f"/airlock/review/{inv['id']}").data.decode()
    assert "could not be decrypted" in page
    assert "/import" not in page
    r = client.post(f"/airlock/review/{inv['id']}/import", data={"type_id": "1"})
    assert r.status_code == 400
    assert app_db.get_intake_invitation(inv["id"])["status"] == "complete"


def test_submission_under_other_versions_fails(client, app_db, server):
    """The server reports the versions, but they are in the AAD: a server that
    lies about them makes decryption fail rather than mislabel the record."""
    _issue(client)
    inv = _latest(app_db)
    _submit_both(server, inv)
    server.submissions[1]["consent_version"] = "consent-2"
    client.post("/airlock/check")
    assert b"consent form could not be decrypted" in client.get(
        f"/airlock/review/{inv['id']}").data


def test_invalid_submission_lists_problems(client, app_db, server):
    _issue(client)
    inv = _latest(app_db)
    _submit_both(server, inv, email="nope", phone="")
    client.post("/airlock/check")
    page = client.get(f"/airlock/review/{inv['id']}").data.decode()
    assert "not an email address" in page and "/import" not in page


def test_discard(client, app_db, server):
    _issue(client)
    inv = _latest(app_db)
    _submit_both(server, inv)
    client.post("/airlock/check")
    r = client.post(f"/airlock/review/{inv['id']}/discard")
    assert "msg=discarded" in r.headers["Location"]
    assert server.submissions == []
    assert app_db.get_intake_invitation(inv["id"])["status"] == "revoked"
    assert server.invitations[inv["token_hash"]]["revoked"]


def test_review_escapes_hostile_text(client, app_db, server):
    _issue(client)
    inv = _latest(app_db)
    _submit_both(server, inv, first_name='<img src=x onerror=alert(1)>',
                 additional_info="<script>alert(2)</script>")
    client.post("/airlock/check")
    page = client.get(f"/airlock/review/{inv['id']}").data.decode()
    assert "<script>alert(2)" not in page and "&lt;script&gt;" in page
    assert "<img src=x" not in page


def test_unmatched_submissions(client, app_db, server):
    server.invitations["f" * 64] = {"key_id": app_db.airlock_ensure_keypair()}
    server.public_keys[app_db.airlock_public_key()[0]] = app_db.airlock_public_key()[1]
    server.submit("f" * 64, "intake", fx.intake_payload())
    r = client.post("/airlock/check")
    assert "unmatched=1" in r.headers["Location"]
    assert b"cannot be opened" in client.get(r.headers["Location"]).data
    client.post("/airlock/unmatched/delete")
    assert server.submissions == []


def test_check_when_server_unreachable(client, app_db, server):
    server.fail.add("list_submissions")
    r = client.post("/airlock/check")
    assert r.status_code == 200 and b"Could not reach the AirLock server" in r.data


def test_every_form_carries_a_csrf_token(client, app_db, server):
    _issue(client)
    inv = _latest(app_db)
    pages = ["/airlock", f"/airlock/invitations/{inv['id']}"]
    htmls = [client.get(p).data.decode() for p in pages]
    _submit_both(server, inv)
    client.post("/airlock/check")
    pages.append(f"/airlock/review/{inv['id']}")
    htmls.append(client.get(pages[-1]).data.decode())
    for path, html in zip(pages, htmls):
        forms = len(re.findall(r'<form[^>]*method="post"', html))
        tokens = len(re.findall(r'name="csrf_token"', html))
        assert forms and forms == tokens, path
