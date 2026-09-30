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


def _issue(client, app_db, forms="both", minor=False, ttl_days="14", client_id=None):
    """Send intake forms from a client file, as the Client File button does."""
    if client_id is None:
        client_id = fx.a_client(app_db, email="ada@example.com")
    data = {"forms": forms, "ttl_days": ttl_days}
    if minor:
        data["is_minor"] = "1"
    return client.post(f"/airlock/invite/{client_id}", data=data)


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
    r = _issue(client, app_db)
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
    assert len(inv["token"]) == 22                        # short link since 2026-09-29
    assert "alCopyAsLink(this)" in page and "Open your forms" in page
    assert f'id="al-pin">{inv["pin"]}<' in page and "alCopy('al-pin', this)" in page


def test_issue_failure_leaves_nothing(client, app_db, airlock_server):
    airlock_server.fail.add("create_invitation")
    r = _issue(client, app_db)
    assert r.status_code == 502
    assert b"was not created" in r.data
    assert app_db.list_intake_invitations(include_closed=True) == []


def test_issue_validation_error(client, app_db, airlock_server):
    r = _issue(client, app_db, ttl_days="0")
    assert r.status_code == 400 and b"Expiry must be between" in r.data
    assert airlock_server.calls == []
    assert client.post("/airlock/invite/9999", data={"forms": "both"}).status_code == 404


def test_invitation_carries_the_client_file(client, app_db, airlock_server):
    cid = fx.a_client(app_db, first="Grace", last="Hopper", email="grace@example.com")
    _issue(client, app_db, client_id=cid)
    inv = _latest(app_db)
    assert (inv["client_id"], inv["display_name"], inv["email"]) == \
        (cid, "Grace Hopper", "grace@example.com")


def test_invite_page(client, app_db, airlock_server):
    cid = fx.a_client(app_db, is_minor=1)
    page = client.get(f"/airlock/invite/{cid}").data.decode()
    assert "Ada Lovelace" in page and "C-1" in page
    assert re.search(r'name="is_minor" value="1"[^>]*\s+checked', page)   # from the Profile


def test_one_invitation_at_a_time(client, app_db, airlock_server):
    cid = fx.a_client(app_db)
    _issue(client, app_db, client_id=cid)
    first = _latest(app_db)

    page = client.get(f"/airlock/invite/{cid}").data.decode()
    assert "already has intake forms out" in page and 'name="forms"' not in page
    assert f"/airlock/invitations/{first['id']}" in page
    r = _issue(client, app_db, client_id=cid)
    assert r.status_code == 409
    assert len(app_db.list_intake_invitations(include_closed=True)) == 1

    _submit_both(airlock_server, first)            # in, awaiting review
    client.post("/airlock/check")
    page = client.get(f"/airlock/invite/{cid}").data.decode()
    assert "waiting for your review" in page and f"/airlock/review/{first['id']}" in page
    assert _issue(client, app_db, client_id=cid).status_code == 409

    client.post(f"/airlock/review/{first['id']}/discard")
    assert _issue(client, app_db, client_id=cid).status_code == 302
    assert _latest(app_db)["id"] != first["id"]


def test_revoking_frees_the_client_for_a_new_invitation(client, app_db, airlock_server):
    cid = fx.a_client(app_db)
    _issue(client, app_db, client_id=cid)
    client.post(f"/airlock/invitations/{_latest(app_db)['id']}/revoke")
    assert _issue(client, app_db, client_id=cid).status_code == 302


def test_client_file_has_the_send_button_only_when_configured(client, app_db, airlock_server):
    cid = fx.a_client(app_db)
    assert f"/airlock/invite/{cid}".encode() in client.get(f"/client/{cid}").data
    client.post("/api/airlock_settings", json={"disable": True})
    assert f"/airlock/invite/{cid}".encode() not in client.get(f"/client/{cid}").data


def test_client_file_links_to_review_while_a_submission_waits(client, app_db, airlock_server):
    cid = fx.a_client(app_db)
    _issue(client, app_db, client_id=cid)
    inv = _latest(app_db)
    page = client.get(f"/client/{cid}").data.decode()
    assert re.search(r'<a href="/airlock"[^>]*>(?:(?!</a>).)*Waiting for client', page, re.S)
    assert f"/airlock/invite/{cid}" not in page
    _submit_both(airlock_server, inv)
    client.post("/airlock/check")
    page = client.get(f"/client/{cid}").data.decode()
    assert f"/airlock/review/{inv['id']}" in page and "Review intake forms" in page
    assert f"/airlock/invite/{cid}" not in page
    client.post(f"/airlock/review/{inv['id']}/import")
    page = client.get(f"/client/{cid}").data.decode()
    assert f"/airlock/invite/{cid}" in page and "Review intake forms" not in page


def test_review_marks_rows_to_reject_and_blanks_one_way(client, app_db, airlock_server):
    cid = fx.a_client(app_db, email="old@example.com", additional_info="On file")
    _issue(client, app_db, client_id=cid)
    inv = _latest(app_db)
    _submit_both(airlock_server, inv)
    client.post("/airlock/check")
    review = client.get(f"/airlock/review/{inv['id']}").data.decode()
    assert re.search(r'name="keep" value="email"[^>]*>\s*Reject', review)
    # an answer for a field empty on file can be rejected too
    assert re.search(r'class="al-new">\s*<td>Gender</td>', review)
    assert re.search(r'name="keep" value="gender"[^>]*>\s*Reject', review)
    assert "Keep on file" not in review and "(left blank)" not in review
    assert "differ from the file" in review and "will change" not in review


def test_no_standalone_invitations(client, app_db, airlock_server):
    """Every client has a file before intake goes out (decided 2026-09-29)."""
    page = client.get("/airlock").data.decode()
    assert "New invitation" not in page and 'name="display_name"' not in page
    assert client.post("/airlock/invitations", data={"display_name": "X"}).status_code == 404


def test_revoke(client, app_db, airlock_server):
    _issue(client, app_db)
    inv = _latest(app_db)
    r = client.post(f"/airlock/invitations/{inv['id']}/revoke")
    assert "msg=revoked" in r.headers["Location"]
    assert app_db.get_intake_invitation(inv["id"])["status"] == "revoked"
    assert airlock_server.invitations[inv["token_hash"]]["revoked"]


def test_revoke_when_server_unreachable(client, app_db, airlock_server):
    _issue(client, app_db)
    inv = _latest(app_db)
    airlock_server.fail.add("revoke_invitation")
    r = client.post(f"/airlock/invitations/{inv['id']}/revoke")
    assert "msg=revoke_remote_failed" in r.headers["Location"]
    assert app_db.get_intake_invitation(inv["id"])["status"] == "revoked"


# ---------------------------------------------------------------------------
# check, review, import, discard
# ---------------------------------------------------------------------------

def test_full_flow(client, app_db, airlock_server):
    cid = fx.a_client(app_db, file_number="AL-001", email="old@example.com",
                      phone="613-555-0000")
    _issue(client, app_db, client_id=cid)
    inv = _latest(app_db)
    _submit_both(airlock_server, inv)

    r = client.post("/airlock/check")
    assert "checked=2" in r.headers["Location"]
    assert app_db.get_intake_invitation(inv["id"])["status"] == "complete"
    listing = client.get("/airlock").data.decode()
    assert f"/airlock/review/{inv['id']}" in listing

    review = client.get(f"/airlock/review/{inv['id']}").data.decode()
    assert "Lovelace" in review and "I agree to psychotherapy." in review
    assert "AL-001" in review and 'name="file_number"' not in review
    assert re.search(r'class="al-changed">\s*<td>Email</td>', review)
    assert 'name="keep" value="email"' in review and 'name="keep" value="phone"' in review

    before = app_db.connect().execute("SELECT COUNT(*) FROM clients").fetchone()[0]
    r = client.post(f"/airlock/review/{inv['id']}/import", data={"keep": ["phone"]})
    assert r.status_code == 302 and r.headers["Location"].endswith(f"/client/{cid}")
    assert app_db.connect().execute("SELECT COUNT(*) FROM clients").fetchone()[0] == before
    profile = app_db.get_profile_entry(cid)
    assert profile["email"] == "ada@example.com"          # client's answer
    assert profile["phone"] == "613-555-0000"             # kept on file
    assert airlock_server.submissions == []
    assert app_db.get_intake_invitation(inv["id"])["status"] == "imported"


def test_old_unlinked_invitation_cannot_be_imported(client, app_db, airlock_server):
    """Invitations from before the Client File button have no client to fill in."""
    inv = app_db.create_intake_invitation("Old standalone")
    airlock_server.invitations[inv["token_hash"]] = {"key_id": inv["key_id"]}
    airlock_server.public_keys[inv["key_id"]] = app_db.airlock_public_key()[1]
    _submit_both(airlock_server, inv)
    client.post("/airlock/check")
    page = client.get(f"/airlock/review/{inv['id']}").data.decode()
    assert "not linked to a client file" in page and "Import into client file" not in page
    r = client.post(f"/airlock/review/{inv['id']}/import")
    assert r.status_code == 400
    assert app_db.get_intake_invitation(inv["id"])["status"] == "complete"


def test_import_cleanup_failure_is_reported_and_healed(client, app_db, airlock_server):
    _issue(client, app_db)
    inv = _latest(app_db)
    _submit_both(airlock_server, inv)
    client.post("/airlock/check")
    airlock_server.fail.add("delete_submission")
    r = client.post(f"/airlock/review/{inv['id']}/import")
    assert "msg=cleanup_failed" in r.headers["Location"]
    assert len(airlock_server.submissions) == 2
    airlock_server.fail.clear()
    client.post("/airlock/check")          # next check removes them
    assert airlock_server.submissions == []


def test_tampered_submission_cannot_be_imported(client, app_db, airlock_server):
    _issue(client, app_db)
    inv = _latest(app_db)
    airlock_server.submit(inv["token_hash"], "intake", fx.intake_payload(), tamper=True)
    airlock_server.submit(inv["token_hash"], "consent", fx.consent_payload())
    client.post("/airlock/check")
    page = client.get(f"/airlock/review/{inv['id']}").data.decode()
    assert "could not be decrypted" in page
    assert "/import" not in page
    r = client.post(f"/airlock/review/{inv['id']}/import")
    assert r.status_code == 400
    assert app_db.get_intake_invitation(inv["id"])["status"] == "complete"


def test_submission_under_other_versions_fails(client, app_db, airlock_server):
    """The server reports the versions, but they are in the AAD: a server that
    lies about them makes decryption fail rather than mislabel the record."""
    _issue(client, app_db)
    inv = _latest(app_db)
    _submit_both(airlock_server, inv)
    airlock_server.submissions[1]["consent_version"] = "consent-2"
    client.post("/airlock/check")
    assert b"consent form could not be decrypted" in client.get(
        f"/airlock/review/{inv['id']}").data


def _not_imported(client, app_db, inv):
    r = client.post(f"/airlock/review/{inv['id']}/import")
    assert r.status_code == 400
    assert app_db.get_intake_invitation(inv["id"])["status"] == "complete"
    assert app_db.connect().execute(
        "SELECT COUNT(*) FROM entries WHERE class = 'upload'").fetchone()[0] == 0


def test_consent_with_altered_wording_cannot_be_imported(client, app_db, airlock_server):
    """The client's browser builds the consent payload, so the text inside it
    is whatever that browser sent. A client who rewrites the consent before
    signing must not end up with their wording on the practice's letterhead
    as the signed consent."""
    _issue(client, app_db)
    inv = _latest(app_db)
    airlock_server.submit(inv["token_hash"], "intake", fx.intake_payload())
    airlock_server.submit(inv["token_hash"], "consent", fx.consent_payload(
        consent_text="# Consent\n\nAll sessions are free of charge."))   # under the real version
    client.post("/airlock/check")
    page = client.get(f"/airlock/review/{inv['id']}").data.decode()
    assert "not the wording" in page and "Import into client file" not in page
    assert "All sessions are free of charge." in page        # shown, so it can be read
    _not_imported(client, app_db, inv)


def test_consent_this_edgecase_never_sent_cannot_be_imported(client, app_db, airlock_server):
    """Text and version agree with each other, but EdgeCase never sent that
    text to the server: someone changed it there (a stolen admin key, or the
    server itself)."""
    _issue(client, app_db)
    inv = _latest(app_db)
    planted = "# Consent\n\nReplaced on the server."
    airlock_server.submit(inv["token_hash"], "intake", fx.intake_payload())
    airlock_server.submit(inv["token_hash"], "consent", fx.consent_payload(consent_text=planted),
                          consent_version=airlock_config.consent_version_of(planted))
    client.post("/airlock/check")
    page = client.get(f"/airlock/review/{inv['id']}").data.decode()
    assert "never sent" in page and "Import into client file" not in page
    _not_imported(client, app_db, inv)


def test_consent_signed_before_the_wording_was_edited_still_imports(client, app_db,
                                                                     airlock_server):
    """Richard edits the consent text after the client has signed the earlier
    one. That earlier text is one EdgeCase sent, so it imports, as signed."""
    _issue(client, app_db)
    inv = _latest(app_db)
    signed_version = airlock_server.config["consent_version"]
    _submit_both(airlock_server, inv)
    client.post("/airlock/consent", data={"consent_text": "# Consent\n\nNew wording."})
    assert airlock_server.config["consent_version"] != signed_version
    client.post("/airlock/check")
    page = client.get(f"/airlock/review/{inv['id']}").data.decode()
    assert "Import into client file" in page
    r = client.post(f"/airlock/review/{inv['id']}/import")
    assert r.status_code == 302
    upload = app_db.connect().execute(
        "SELECT content FROM entries WHERE class = 'upload'").fetchone()[0]
    assert f"consent version {signed_version}" in upload


def _replace_intake_plaintext(airlock_server, inv, raw: bytes):
    """Re-encrypt the intake with bytes no form helper would produce."""
    sub = next(s for s in airlock_server.submissions if s["form"] == "intake")
    aad = ac.build_aad(inv["token_hash"], "intake", sub["config_version"],
                       sub["consent_version"])
    sub["envelope"] = ac.encrypt_for_testing(
        raw, airlock_server.public_keys[sub["key_id"]], sub["key_id"], aad)


@pytest.mark.parametrize("raw, shown", [
    (b"[" * 40_000, "not valid JSON"),
    (json.dumps(fx.intake_payload()).replace("Ada", "\\ud800Ada").encode(), "Ada"),
])
def test_hostile_intake_reaches_the_review_screen_not_a_crash(client, app_db, airlock_server,
                                                              raw, shown):
    """Whatever a submission holds, the review screen must open: it is where
    the problem is reported and where Discard lives. Both of these were a 500."""
    _issue(client, app_db)
    inv = _latest(app_db)
    _submit_both(airlock_server, inv)
    _replace_intake_plaintext(airlock_server, inv, raw)
    client.post("/airlock/check")
    r = client.get(f"/airlock/review/{inv['id']}")
    page = r.data.decode()
    assert r.status_code == 200 and shown in page
    assert f"/airlock/review/{inv['id']}/discard" in page


def test_an_unexpected_error_opening_a_form_is_reported_not_raised(client, app_db,
                                                                   airlock_server, monkeypatch):
    from web.blueprints import airlock as bp

    def boom(*_a, **_k):
        raise RuntimeError("anything at all")
    monkeypatch.setattr(bp, "parse_intake", boom)
    _issue(client, app_db)
    inv = _latest(app_db)
    _submit_both(airlock_server, inv)
    client.post("/airlock/check")
    r = client.get(f"/airlock/review/{inv['id']}")
    page = r.data.decode()
    assert r.status_code == 200 and "intake form could not be read" in page
    assert "Import into client file" not in page
    assert f"/airlock/review/{inv['id']}/discard" in page
    assert client.post(f"/airlock/review/{inv['id']}/import").status_code == 400


def test_invalid_submission_lists_problems(client, app_db, airlock_server):
    _issue(client, app_db)
    inv = _latest(app_db)
    _submit_both(airlock_server, inv, email="nope", phone="")
    client.post("/airlock/check")
    page = client.get(f"/airlock/review/{inv['id']}").data.decode()
    assert "not an email address" in page and "/import" not in page


def test_discard(client, app_db, airlock_server):
    _issue(client, app_db)
    inv = _latest(app_db)
    _submit_both(airlock_server, inv)
    client.post("/airlock/check")
    r = client.post(f"/airlock/review/{inv['id']}/discard")
    assert "msg=discarded" in r.headers["Location"]
    assert airlock_server.submissions == []
    assert app_db.get_intake_invitation(inv["id"])["status"] == "revoked"
    assert airlock_server.invitations[inv["token_hash"]]["revoked"]


def test_review_escapes_hostile_text(client, app_db, airlock_server):
    _issue(client, app_db)
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
    _issue(client, app_db)
    inv = _latest(app_db)
    fresh = fx.a_client(app_db, first="Grace", file_number="C-9")   # nothing out yet
    pages = ["/airlock", f"/airlock/invitations/{inv['id']}",
             f"/airlock/invite/{fresh}"]
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


def test_no_browser_dialogs_in_airlock_pages():
    """The app uses its own confirmation modal, never the browser's
    confirm() / alert() / prompt()."""
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "web/templates"
    for path in [*root.glob("airlock*.html"), root / "partials/airlock_confirm.html"]:
        text = re.sub(r"\{#.*?#\}", "", path.read_text(), flags=re.S)
        assert not re.search(r"(?<![\w.])(confirm|alert|prompt)\(", text), path.name


def test_destructive_buttons_use_the_app_modal(client, app_db, airlock_server):
    _issue(client, app_db)
    inv = _latest(app_db)
    page = client.get(f"/airlock/invitations/{inv['id']}").data.decode()
    assert 'id="al-confirm-modal"' in page and "alConfirm('al-revoke-form'" in page
    _submit_both(airlock_server, inv)
    client.post("/airlock/check")
    page = client.get(f"/airlock/review/{inv['id']}").data.decode()
    assert 'id="al-confirm-modal"' in page and "alConfirm('al-discard-form'" in page


def _expired(app_db, client_id):
    import time
    return app_db.create_intake_invitation("Ada L.", client_id=client_id, ttl_days=1,
                                           now=int(time.time()) - 3 * 86400)


def test_expired_invitations_wait_to_be_dismissed(client, app_db, airlock_server):
    """An expired invitation stays on the page, marked Expired, until dismissed,
    so a client who never did their forms doesn't just drop off the list."""
    inv = _expired(app_db, fx.a_client(app_db))
    page = client.get("/airlock").data.decode()
    assert "Expired</span>" in page and "Dismiss</button>" in page
    assert f"/airlock/invitations/{inv['id']}/revoke" in page
    r = client.post(f"/airlock/invitations/{inv['id']}/revoke")
    assert "msg=dismissed" in r.headers["Location"]
    page = client.get(r.headers["Location"]).data.decode()
    assert "Expired invitation dismissed." in page and "Dismiss</button>" not in page


def test_a_new_invitation_replaces_an_expired_one(client, app_db, airlock_server):
    cid = fx.a_client(app_db)
    old = _expired(app_db, cid)
    other = _expired(app_db, fx.a_client(app_db, first="Grace", file_number="C-2"))
    _issue(client, app_db, client_id=cid)
    assert app_db.get_intake_invitation(old["id"])["status"] == "revoked"
    assert app_db.get_intake_invitation(other["id"])["status"] == "issued"   # other client


def test_closed_invitations_are_not_listed(client, app_db, airlock_server):
    _issue(client, app_db)
    inv = _latest(app_db)
    client.post(f"/airlock/invitations/{inv['id']}/revoke")
    page = client.get("/airlock").data.decode()
    assert "Recent" not in page and "Revoked" not in page and "Ada Lovelace" not in page


def test_opening_the_page_checks_for_submissions(client, app_db, airlock_server):
    """The ntfy ping says "open AirLock": the page fetches on its own."""
    _issue(client, app_db)
    inv = _latest(app_db)
    _submit_both(airlock_server, inv)
    page = client.get("/airlock").data.decode()               # no Check click
    assert f"/airlock/review/{inv['id']}" in page
    assert app_db.get_intake_invitation(inv["id"])["status"] == "complete"


def test_page_still_opens_when_the_server_is_unreachable(client, app_db, airlock_server):
    _issue(client, app_db)
    airlock_server.fail.add("list_submissions")
    r = client.get("/airlock")
    assert r.status_code == 200
    assert b"Showing what was last received." in r.data
    assert b"Waiting for the client" in r.data


def test_head_probe_does_not_contact_the_server(client, app_db, airlock_server):
    airlock_server.calls.clear()
    assert client.head("/airlock").status_code == 200
    assert "list_submissions" not in airlock_server.calls
