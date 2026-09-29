"""AirLock screens, driven end to end against a stand-in airlock_server.

FakeServer implements the admin API from docs/Intake_Service_Plan.md in
memory and plays the browser's part (encrypting submissions to the public key
EdgeCase pushed). Every route runs for real against the test database.
"""
import json
import re
import uuid

import pytest

from core import airlock_client, airlock_config
from core import airlock_crypto as ac
from core.airlock_client import AirLockConnectionError

from tests import test_airlock_import as fx


def _issue(client, name="Ada L.", email="ada@example.com", forms="both", minor=False):
    data = {"display_name": name, "email": email, "forms": forms, "ttl_days": "14"}
    if minor:
        data["is_minor"] = "1"
    return client.post("/airlock/invitations", data=data)


def _latest(app_db):
    return app_db.list_intake_invitations(include_closed=True)[0]


def _submit_both(airlock_server, inv, **intake_overrides):
    airlock_server.submit(inv["token_hash"], "intake", fx.intake_payload(**intake_overrides))
    airlock_server.submit(inv["token_hash"], "consent", fx.consent_payload())


# ---------------------------------------------------------------------------
# dormant until configured
# ---------------------------------------------------------------------------

def test_dormant_without_a_server(client, app_db):
    r = client.get("/airlock")
    assert r.status_code == 302 and "/settings#airlock" in r.headers["Location"]
    assert b"AirLock</a>" not in client.get("/").data
    assert b'href="/airlock"' not in client.get("/").data


def test_menu_item_appears_once_configured(client, airlock_server):
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


def test_turn_off(client, app_db, airlock_server):
    assert client.post("/api/airlock_settings", json={"disable": True}).get_json()["success"]
    assert not airlock_client.is_enabled(app_db)


def test_test_connection_pushes_the_key(client, app_db, airlock_server):
    r = client.post("/api/airlock_test", json={})
    kid = r.get_json()["key_id"]
    assert airlock_server.public_keys == {kid: app_db.airlock_public_key()[1]}
    airlock_server.fail.add("put_public_key")
    r = client.post("/api/airlock_test", json={})
    assert r.status_code == 502 and "Could not reach" in r.get_json()["error"]


# ---------------------------------------------------------------------------
# issuing and revoking
# ---------------------------------------------------------------------------

def test_issue_sends_only_hash_and_pin(client, app_db, airlock_server):
    r = _issue(client)
    inv = _latest(app_db)
    assert r.status_code == 302
    assert r.headers["Location"].endswith(f"/airlock/invitations/{inv['id']}?new=1")
    sent = airlock_server.invitations[inv["token_hash"]]
    assert sent["pin"] == inv["pin"]
    blob = json.dumps(sent)
    assert "Ada" not in blob and "example.com" not in blob and inv["token"] not in blob
    config_blob = json.dumps(airlock_server.config)
    assert "Ada" not in config_blob and inv["token"] not in config_blob

    page = client.get(f"/airlock/invitations/{inv['id']}?new=1").data.decode()
    assert f"https://forms.example.ca/i#{inv['token']}" in page
    assert inv["pin"] in page


def test_issue_failure_leaves_nothing(client, app_db, airlock_server):
    airlock_server.fail.add("create_invitation")
    r = _issue(client)
    assert r.status_code == 502
    assert b"was not created" in r.data
    assert app_db.list_intake_invitations(include_closed=True) == []


def test_issue_validation_error(client, app_db, airlock_server):
    r = _issue(client, name="")
    assert r.status_code == 400 and b"name is required" in r.data
    assert airlock_server.calls == []


def test_revoke(client, app_db, airlock_server):
    _issue(client)
    inv = _latest(app_db)
    r = client.post(f"/airlock/invitations/{inv['id']}/revoke")
    assert "msg=revoked" in r.headers["Location"]
    assert app_db.get_intake_invitation(inv["id"])["status"] == "revoked"
    assert airlock_server.invitations[inv["token_hash"]]["revoked"]


def test_revoke_when_server_unreachable(client, app_db, airlock_server):
    _issue(client)
    inv = _latest(app_db)
    airlock_server.fail.add("revoke_invitation")
    r = client.post(f"/airlock/invitations/{inv['id']}/revoke")
    assert "msg=revoke_remote_failed" in r.headers["Location"]
    assert app_db.get_intake_invitation(inv["id"])["status"] == "revoked"


# ---------------------------------------------------------------------------
# check, review, import, discard
# ---------------------------------------------------------------------------

def test_full_flow(client, app_db, airlock_server):
    app_db.set_setting("file_number_format", "manual")
    _issue(client)
    inv = _latest(app_db)
    _submit_both(airlock_server, inv)

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
    assert airlock_server.submissions == []
    assert app_db.get_intake_invitation(inv["id"])["status"] == "imported"


def test_import_with_automatic_numbering(client, app_db, airlock_server):
    app_db.set_setting("file_number_format", "prefix-counter")
    _issue(client)
    inv = _latest(app_db)
    _submit_both(airlock_server, inv)
    client.post("/airlock/check")
    assert b"Assigned automatically" in client.get(f"/airlock/review/{inv['id']}").data
    r = client.post(f"/airlock/review/{inv['id']}/import", data={"type_id": "1"})
    cid = int(re.search(r"/client/(\d+)", r.headers["Location"]).group(1))
    assert app_db.get_client(cid)["file_number"] == "0001"


def test_manual_number_collision_is_reported(client, app_db, airlock_server):
    app_db.set_setting("file_number_format", "manual")
    app_db.add_client({"file_number": "TAKEN", "first_name": "T", "last_name": "N",
                       "type_id": 1})
    _issue(client)
    inv = _latest(app_db)
    _submit_both(airlock_server, inv)
    client.post("/airlock/check")
    r = client.post(f"/airlock/review/{inv['id']}/import",
                    data={"type_id": "1", "file_number": "TAKEN"})
    assert r.status_code == 400 and b"already exists" in r.data
    assert len(airlock_server.submissions) == 2
    assert app_db.get_intake_invitation(inv["id"])["status"] == "complete"


def test_import_cleanup_failure_is_reported_and_healed(client, app_db, airlock_server):
    app_db.set_setting("file_number_format", "manual")
    _issue(client)
    inv = _latest(app_db)
    _submit_both(airlock_server, inv)
    client.post("/airlock/check")
    airlock_server.fail.add("delete_submission")
    r = client.post(f"/airlock/review/{inv['id']}/import",
                    data={"type_id": "1", "file_number": "CF-1"})
    assert "msg=cleanup_failed" in r.headers["Location"]
    assert len(airlock_server.submissions) == 2
    airlock_server.fail.clear()
    client.post("/airlock/check")          # next check removes them
    assert airlock_server.submissions == []


def test_tampered_submission_cannot_be_imported(client, app_db, airlock_server):
    _issue(client)
    inv = _latest(app_db)
    airlock_server.submit(inv["token_hash"], "intake", fx.intake_payload(), tamper=True)
    airlock_server.submit(inv["token_hash"], "consent", fx.consent_payload())
    client.post("/airlock/check")
    page = client.get(f"/airlock/review/{inv['id']}").data.decode()
    assert "could not be decrypted" in page
    assert "/import" not in page
    r = client.post(f"/airlock/review/{inv['id']}/import", data={"type_id": "1"})
    assert r.status_code == 400
    assert app_db.get_intake_invitation(inv["id"])["status"] == "complete"


def test_submission_under_other_versions_fails(client, app_db, airlock_server):
    """The server reports the versions, but they are in the AAD: a server that
    lies about them makes decryption fail rather than mislabel the record."""
    _issue(client)
    inv = _latest(app_db)
    _submit_both(airlock_server, inv)
    airlock_server.submissions[1]["consent_version"] = "consent-2"
    client.post("/airlock/check")
    assert b"consent form could not be decrypted" in client.get(
        f"/airlock/review/{inv['id']}").data


def test_invalid_submission_lists_problems(client, app_db, airlock_server):
    _issue(client)
    inv = _latest(app_db)
    _submit_both(airlock_server, inv, email="nope", phone="")
    client.post("/airlock/check")
    page = client.get(f"/airlock/review/{inv['id']}").data.decode()
    assert "not an email address" in page and "/import" not in page


def test_discard(client, app_db, airlock_server):
    _issue(client)
    inv = _latest(app_db)
    _submit_both(airlock_server, inv)
    client.post("/airlock/check")
    r = client.post(f"/airlock/review/{inv['id']}/discard")
    assert "msg=discarded" in r.headers["Location"]
    assert airlock_server.submissions == []
    assert app_db.get_intake_invitation(inv["id"])["status"] == "revoked"
    assert airlock_server.invitations[inv["token_hash"]]["revoked"]


def test_review_escapes_hostile_text(client, app_db, airlock_server):
    _issue(client)
    inv = _latest(app_db)
    _submit_both(airlock_server, inv, first_name='<img src=x onerror=alert(1)>',
                 additional_info="<script>alert(2)</script>")
    client.post("/airlock/check")
    page = client.get(f"/airlock/review/{inv['id']}").data.decode()
    assert "<script>alert(2)" not in page and "&lt;script&gt;" in page
    assert "<img src=x" not in page


def test_unmatched_submissions(client, app_db, airlock_server):
    airlock_server.invitations["f" * 64] = {"key_id": app_db.airlock_ensure_keypair()}
    airlock_server.public_keys[app_db.airlock_public_key()[0]] = app_db.airlock_public_key()[1]
    airlock_server.submit("f" * 64, "intake", fx.intake_payload())
    r = client.post("/airlock/check")
    assert "unmatched=1" in r.headers["Location"]
    assert b"cannot be opened" in client.get(r.headers["Location"]).data
    client.post("/airlock/unmatched/delete")
    assert airlock_server.submissions == []


def test_check_when_server_unreachable(client, app_db, airlock_server):
    airlock_server.fail.add("list_submissions")
    r = client.post("/airlock/check")
    assert r.status_code == 200 and b"Could not reach the AirLock server" in r.data


def test_every_form_carries_a_csrf_token(client, app_db, airlock_server):
    _issue(client)
    inv = _latest(app_db)
    pages = ["/airlock", f"/airlock/invitations/{inv['id']}"]
    htmls = [client.get(p).data.decode() for p in pages]
    _submit_both(airlock_server, inv)
    client.post("/airlock/check")
    pages.append(f"/airlock/review/{inv['id']}")
    htmls.append(client.get(pages[-1]).data.decode())
    for path, html in zip(pages, htmls):
        forms = len(re.findall(r'<form[^>]*method="post"', html))
        tokens = len(re.findall(r'name="csrf_token"', html))
        assert forms and forms == tokens, path


def test_consent_page_answers_head_probe(client, airlock_server):
    """base.html probes every link with HEAD before navigating; a non-2xx
    answer shows the 'Server Disconnected' overlay. HEAD must not be
    treated as a form submission."""
    assert client.head("/airlock/consent").status_code == 200
