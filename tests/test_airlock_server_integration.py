"""EdgeCase against the real AirLock server, over real HTTP.

Runs only when the AirLock repository is checked out next to this one
(../edgecase-airlock); skipped otherwise, so the EdgeCase suite never depends
on it.

Nothing is stubbed. EdgeCase issues the invitation through its own screen,
which pushes the public key, the form bundle and the invitation to the admin
listener. This test then plays the client's browser against the public
listener (unlock with link and PIN, encrypt, submit), and EdgeCase checks,
reviews and imports through its own screens. It proves the two code bases
agree on the admin API, the bundle format and version hashes, the envelope
shape and the associated data.
"""
import json
import re
import sys
import threading
import urllib.request
from pathlib import Path

import pytest
from werkzeug.serving import make_server

from core import airlock_config
from core import airlock_crypto as ac
from tests import test_airlock_import as fx

AIRLOCK_REPO = Path(__file__).resolve().parents[1].parent / "edgecase-airlock"
pytestmark = pytest.mark.skipif(not (AIRLOCK_REPO / "airlock" / "admin.py").exists(),
                                reason="edgecase-airlock not checked out alongside")


@pytest.fixture
def airlock(tmp_path):
    sys.path.insert(0, str(AIRLOCK_REPO))
    try:
        from airlock.admin import create_admin_app
        from airlock.public import create_public_app
        from airlock.settings import Settings, generate_admin_key
        from airlock.store import Store
    finally:
        sys.path.remove(str(AIRLOCK_REPO))
    settings = Settings(data_dir=tmp_path / "airlock-data")
    key = generate_admin_key(settings)
    store = Store(settings.db_path)
    servers = [make_server("127.0.0.1", 0, create_public_app(settings, store), threaded=True),
               make_server("127.0.0.1", 0, create_admin_app(settings, store), threaded=True)]
    threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in servers]
    for t in threads:
        t.start()
    public_url, admin_url = (f"http://127.0.0.1:{s.server_port}" for s in servers)
    yield {"public": public_url, "admin": admin_url, "key": key, "store": store}
    for s in servers:
        s.shutdown()
        s.server_close()
    for t in threads:
        t.join(timeout=5)


def _post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _browser_submit(public_url, token, pin, form, payload):
    """What the AirLock page will do: unlock, then encrypt to the key the
    server hands out, with AAD built from the token and the versions shown."""
    status, info = _post(public_url + "/i/unlock", {"token": token, "pin": pin})
    assert status == 200, info
    cfg = info["config"]
    token_hash = ac.token_hash(token)
    aad = ac.build_aad(token_hash, form, cfg["config_version"], cfg["consent_version"])
    env = ac.encrypt_for_testing(json.dumps(payload).encode(), info["public_key"],
                                 info["key_id"], aad)
    return _post(public_url + "/i/submit", {
        "token": token, "pin": pin, "form": form, "key_id": info["key_id"],
        "config_version": cfg["config_version"], "consent_version": cfg["consent_version"],
        "envelope": env})


def test_edgecase_and_airlock_end_to_end(client, app_db, airlock):
    app_db.set_setting("airlock_server_url", airlock["admin"])
    app_db.set_setting("airlock_public_url", airlock["public"])
    app_db.set_setting("airlock_admin_key", airlock["key"])
    app_db.set_setting("file_number_format", "manual")
    app_db.set_setting("therapist_name", "Jordan Example")
    cfg = airlock_config.default_config()
    cfg["questions"] = ["What brings you to therapy?"]
    cfg["consent_text"] = "# Consent\n\nI agree to psychotherapy."
    airlock_config.save_config(app_db, cfg)

    # Settings -> Test connection: key and bundle accepted by the real server
    r = client.post("/api/airlock_test", json={})
    assert r.get_json()["success"], r.get_json()

    # Issue through EdgeCase's own screen
    r = client.post("/airlock/invitations", data={
        "display_name": "Ada L.", "email": "ada@example.com", "forms": "both", "ttl_days": "14"})
    assert r.status_code == 302, r.data
    inv = app_db.list_intake_invitations()[0]
    page = client.get(r.headers["Location"]).data.decode()
    link = re.search(r'id="al-link">([^<]+)<', page).group(1).strip()
    token = link.split("#", 1)[1]
    assert token == inv["token"]

    # The server holds no name, email, token or PIN
    with open(airlock["store"].path, "rb") as f:
        raw_db = f.read()
    for secret in (b"Ada", b"ada@example.com", token.encode(), inv["pin"].encode()):
        assert secret not in raw_db

    # The client's browser
    payload = fx.intake_payload(questions=[{"question": "What brings you to therapy?",
                                            "answer": "Stress at work."}])
    assert _browser_submit(airlock["public"], token, inv["pin"], "intake", payload)[0] == 201
    assert _browser_submit(airlock["public"], token, inv["pin"], "consent",
                           fx.consent_payload())[0] == 201
    # the server's copy is ciphertext
    subs = airlock["store"].submissions()
    assert len(subs) == 2 and all(b"Lovelace" not in s["envelope"].encode() for s in subs)

    # Back in EdgeCase: check, review, import
    r = client.post("/airlock/check")
    assert "checked=2" in r.headers["Location"]
    review = client.get(f"/airlock/review/{inv['id']}").data.decode()
    assert "Lovelace" in review and "Stress at work." in review
    r = client.post(f"/airlock/review/{inv['id']}/import",
                    data={"type_id": "1", "file_number": "E2E-001"})
    assert r.status_code == 302, r.data
    cid = int(re.search(r"/client/(\d+)", r.headers["Location"]).group(1))
    assert app_db.get_client(cid)["file_number"] == "E2E-001"
    assert "Stress at work." in app_db.get_profile_entry(cid)["additional_info"]

    # Submissions removed from the server; the link is dead
    assert airlock["store"].submissions() == []
    status, body = _post(airlock["public"] + "/i/unlock", {"token": token, "pin": inv["pin"]})
    assert status == 410 and body["error"] == "closed"


def test_revoke_reaches_the_real_server(client, app_db, airlock):
    app_db.set_setting("airlock_server_url", airlock["admin"])
    app_db.set_setting("airlock_public_url", airlock["public"])
    app_db.set_setting("airlock_admin_key", airlock["key"])
    cfg = airlock_config.default_config()
    cfg["consent_text"] = "I agree."
    airlock_config.save_config(app_db, cfg)
    client.post("/airlock/invitations", data={"display_name": "B", "forms": "both",
                                              "ttl_days": "14"})
    inv = app_db.list_intake_invitations()[0]
    r = client.post(f"/airlock/invitations/{inv['id']}/revoke")
    assert "msg=revoked" in r.headers["Location"]
    status, _ = _post(airlock["public"] + "/i/unlock", {"token": inv["token"], "pin": inv["pin"]})
    assert status == 410


def test_wrong_admin_key_is_reported(client, app_db, airlock):
    app_db.set_setting("airlock_server_url", airlock["admin"])
    app_db.set_setting("airlock_admin_key", "not-the-key")
    r = client.post("/api/airlock_test", json={})
    assert r.status_code == 502 and "refused the admin key" in r.get_json()["error"]
