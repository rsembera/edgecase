"""AirLock configuration: the consent text, versions, logo re-encoding, the
Consent page, and the guard against inviting a client to sign an empty consent.

The intake form itself is not configurable: it mirrors the Client Profile
(tests/test_airlock_import.py pins that).
"""
import base64
import json
from io import BytesIO

import pytest
from PIL import Image

from core import airlock_config as cfgmod


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------

def test_consent_text_is_cleaned_and_capped():
    assert cfgmod.validate_config({"consent_text": "  Line one\r\nLine two \n"}) == \
        {"consent_text": "Line one\nLine two"}
    with pytest.raises(ValueError, match="too long"):
        cfgmod.validate_config({"consent_text": "x" * 50_001})


def test_load_keeps_consent_and_ignores_old_field_settings(app_db):
    """Configs saved before the form was fixed held labels, show/required
    flags and questions. Only the consent text survives."""
    app_db.set_setting(cfgmod.SETTING_KEY, json.dumps({
        "fields": {"gender": {"label": "Pronouns"}}, "questions": ["Q1"],
        "consent_text": "C"}))
    assert cfgmod.load_config(app_db) == {"consent_text": "C"}
    app_db.set_setting(cfgmod.SETTING_KEY, "{not json")
    assert cfgmod.load_config(app_db) == cfgmod.default_config()
    app_db.set_setting(cfgmod.SETTING_KEY, "[]")
    assert cfgmod.load_config(app_db) == cfgmod.default_config()


def test_bundle_carries_no_field_settings(app_db, tmp_path):
    bundle = cfgmod.build_bundle(app_db, {"consent_text": "C"}, tmp_path)
    assert set(bundle) == {"practice", "logo_png", "consent_text", "consent_version",
                           "config_version"}


# ---------------------------------------------------------------------------
# bundle and versions
# ---------------------------------------------------------------------------

def test_versions(app_db, tmp_path):
    cfg = cfgmod.default_config()
    cfg["consent_text"] = "Consent v1"
    a = cfgmod.build_bundle(app_db, cfg, tmp_path)
    assert a == cfgmod.build_bundle(app_db, cfg, tmp_path)          # stable

    app_db.set_setting("practice_name", "Example Practice")
    b = cfgmod.build_bundle(app_db, cfg, tmp_path)
    assert b["config_version"] != a["config_version"]
    assert b["consent_version"] == a["consent_version"]             # consent untouched

    cfg["consent_text"] = "Consent v2"
    c = cfgmod.build_bundle(app_db, cfg, tmp_path)
    assert c["consent_version"] != b["consent_version"]

    app_db.set_setting("therapist_name", "Jordan Example")
    d = cfgmod.build_bundle(app_db, cfg, tmp_path)
    assert d["config_version"] != c["config_version"]
    assert d["practice"]["therapist_name"] == "Jordan Example"

    cfg["consent_text"] = ""
    assert cfgmod.build_bundle(app_db, cfg, tmp_path)["consent_version"] == ""


def _png(size=(1200, 800), fmt="PNG"):
    buf = BytesIO()
    Image.new("RGB", size, (17, 93, 79)).save(buf, format=fmt)
    return buf.getvalue()


def test_logo_is_reencoded_and_capped(app_db, tmp_path):
    (tmp_path / "logo.jpg").write_bytes(_png(fmt="JPEG"))
    app_db.set_setting("logo_filename", "logo.jpg")
    bundle = cfgmod.build_bundle(app_db, cfgmod.default_config(), tmp_path)
    logo = base64.b64decode(bundle["logo_png"])
    assert logo.startswith(b"\x89PNG")
    with Image.open(BytesIO(logo)) as img:
        assert img.size[0] <= 600 and img.size[1] <= 300


@pytest.mark.parametrize("setup", ["missing", "not_an_image", "traversal"])
def test_logo_problems_mean_no_logo(app_db, tmp_path, setup):
    if setup == "missing":
        app_db.set_setting("logo_filename", "nope.png")
    elif setup == "not_an_image":
        (tmp_path / "logo.png").write_bytes(b"<svg onload=alert(1)>")
        app_db.set_setting("logo_filename", "logo.png")
    else:
        outside = tmp_path.parent / "secret.png"
        outside.write_bytes(_png())
        app_db.set_setting("logo_filename", "../secret.png")
    assert cfgmod.build_bundle(app_db, cfgmod.default_config(), tmp_path)["logo_png"] is None


# ---------------------------------------------------------------------------
# Consent page and invitation guard
# ---------------------------------------------------------------------------

def test_consent_page_saves_and_pushes(client, app_db, airlock_server):
    r = client.post("/airlock/consent", data={"consent_text": "# Consent\n\nNew wording."})
    assert "msg=consent_saved" in r.headers["Location"]
    assert cfgmod.load_config(app_db)["consent_text"] == "# Consent\n\nNew wording."
    assert airlock_server.config["consent_text"] == "# Consent\n\nNew wording."
    assert "fields" not in airlock_server.config and "questions" not in airlock_server.config
    assert b"New wording." in client.get("/airlock/consent").data


def test_consent_page_saves_locally_when_server_unreachable(client, app_db, airlock_server):
    airlock_server.fail.add("put_config")
    r = client.post("/airlock/consent", data={"consent_text": "Offline edit"})
    assert "msg=consent_saved_local" in r.headers["Location"]
    assert cfgmod.load_config(app_db)["consent_text"] == "Offline edit"


def test_consent_page_rejects_too_long(client, app_db, airlock_server):
    before = cfgmod.load_config(app_db)
    r = client.post("/airlock/consent", data={"consent_text": "x" * 50_001})
    assert r.status_code == 400 and b"too long" in r.data
    assert cfgmod.load_config(app_db) == before


def test_consent_page_has_no_field_settings(client, app_db, airlock_server):
    html = client.get("/airlock/consent").data.decode()
    assert "label__" not in html and "show__" not in html and "question_" not in html


def test_forms_page_is_gone(client, app_db, airlock_server):
    assert client.get("/airlock/forms").status_code == 404


def test_no_consent_invitation_without_consent_text(client, app_db, airlock_server):
    cfgmod.save_config(app_db, cfgmod.default_config())   # empty consent
    r = client.post("/airlock/invitations",
                    data={"display_name": "Ada", "forms": "both", "ttl_days": "14"})
    assert r.status_code == 400 and b"consent text" in r.data
    assert airlock_server.calls == []
    r = client.post("/airlock/invitations",
                    data={"display_name": "Ada", "forms": "intake", "ttl_days": "14"})
    assert r.status_code == 302


def test_invitation_pushes_current_config(client, app_db, airlock_server):
    client.post("/airlock/invitations",
                data={"display_name": "Ada", "forms": "both", "ttl_days": "14"})
    assert airlock_server.calls[:3] == ["put_public_key", "put_config", "create_invitation"]
    assert airlock_server.config["consent_version"]


def test_consent_page_has_csrf_and_escapes(client, app_db, airlock_server):
    cfg = cfgmod.default_config()
    cfg["consent_text"] = "</textarea><script>alert(1)</script>"
    cfgmod.save_config(app_db, cfg)
    html = client.get("/airlock/consent").data.decode()
    assert 'name="csrf_token"' in html
    assert "<script>alert(1)" not in html
