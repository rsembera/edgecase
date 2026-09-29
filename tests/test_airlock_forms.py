"""AirLock form customization: config rules, versions, logo re-encoding, the
Forms page, and the guard against inviting a client to sign an empty consent.
"""
import base64
import json
from io import BytesIO

import pytest
from PIL import Image

from core import airlock_config as cfgmod


def form_data(cfg=None, **extra):
    cfg = cfg or cfgmod.default_config()
    data = {}
    for name, meta in cfg["fields"].items():
        data[f"label__{name}"] = meta["label"]
        if meta["show"]:
            data[f"show__{name}"] = "1"
        if meta["required"]:
            data[f"required__{name}"] = "1"
    for i, q in enumerate(cfg["questions"], 1):
        data[f"question_{i}"] = q
    data["consent_text"] = cfg["consent_text"]
    data.update(extra)
    return data


# ---------------------------------------------------------------------------
# config rules
# ---------------------------------------------------------------------------

def test_defaults_are_valid_and_cover_every_intake_field():
    from core.airlock_import import INTAKE_FIELDS
    cfg = cfgmod.default_config()
    assert set(cfg["fields"]) == set(INTAKE_FIELDS)
    assert cfgmod.validate_config(cfg)["fields"] == cfg["fields"]


def test_fields_follow_the_client_profile_order():
    """The Forms page and the client's form list fields in the Profile's order."""
    import re
    from pathlib import Path
    profile = (Path(__file__).resolve().parent.parent
               / "web/templates/entry_forms/profile.html").read_text()
    names = re.findall(r'<(?:input|select|textarea)[^>]*\bname="([a-z_0-9]+)"', profile)
    in_profile = [n for n in dict.fromkeys(names) if n in cfgmod.FIELD_NAMES]
    assert in_profile == cfgmod.FIELD_NAMES


def test_profile_dropdowns_are_choices_with_matching_options():
    from core.airlock_import import CHOICES, INTAKE_FIELDS
    choice_fields = {n for n, (_, kind) in INTAKE_FIELDS.items() if kind == "choice"}
    assert set(cfgmod.CHOICE_OPTIONS) == choice_fields
    for name, labels in cfgmod.CHOICE_OPTIONS.items():
        assert len(labels) == len(CHOICES[name] - {""})


def test_names_cannot_be_hidden_or_optional():
    cfg = cfgmod.default_config()
    cfg["fields"]["first_name"].update(show=False, required=False)
    out = cfgmod.validate_config(cfg)
    assert out["fields"]["first_name"] == {"label": "First name", "show": True,
                                           "required": True}


def test_a_contact_method_must_be_required():
    cfg = cfgmod.default_config()
    for c in cfgmod.CONTACT_FIELDS:
        cfg["fields"][c]["required"] = False
    with pytest.raises(ValueError, match="contact method"):
        cfgmod.validate_config(cfg)


def test_hidden_field_cannot_be_required():
    cfg = cfgmod.default_config()
    cfg["fields"]["gender"].update(show=False, required=True)
    assert cfgmod.validate_config(cfg)["fields"]["gender"]["required"] is False


def test_hiding_the_only_required_contact_fails():
    cfg = cfgmod.default_config()
    cfg["fields"]["email"]["show"] = False   # email was the required one
    with pytest.raises(ValueError, match="contact method"):
        cfgmod.validate_config(cfg)


def test_labels_questions_and_consent_are_cleaned_and_capped():
    cfg = cfgmod.default_config()
    cfg["fields"]["gender"]["label"] = "  Pronouns \n "
    cfg["fields"]["address"]["label"] = ""
    cfg["questions"] = ["  What brings you here? ", "", "Seen someone before?"]
    cfg["consent_text"] = "Line one\r\nLine two\r\n"
    out = cfgmod.validate_config(cfg)
    assert out["fields"]["gender"]["label"] == "Pronouns"
    assert out["fields"]["address"]["label"] == "Address"      # blank -> default
    assert out["questions"] == ["What brings you here?", "Seen someone before?"]
    assert out["consent_text"] == "Line one\nLine two"


@pytest.mark.parametrize("mutate, fragment", [
    (lambda c: c["fields"]["gender"].update(label="x" * 101), "too long"),
    (lambda c: c.update(questions=["q"] * 6), "At most 5"),
    (lambda c: c.update(questions=["q" * 301]), "limited to 300"),
    (lambda c: c.update(consent_text="x" * 50_001), "Consent text is too long"),
])
def test_config_limits(mutate, fragment):
    cfg = cfgmod.default_config()
    mutate(cfg)
    with pytest.raises(ValueError, match=fragment):
        cfgmod.validate_config(cfg)


def test_unknown_fields_are_ignored():
    cfg = cfgmod.default_config()
    cfg["fields"]["session_total"] = {"label": "Fee", "show": True, "required": True}
    assert "session_total" not in cfgmod.validate_config(cfg)["fields"]


def test_load_merges_over_defaults(app_db):
    app_db.set_setting(cfgmod.SETTING_KEY, json.dumps({
        "fields": {"gender": {"label": "Pronouns"}, "bogus": {"label": "x"}},
        "questions": ["Q1", 7], "consent_text": "C"}))
    cfg = cfgmod.load_config(app_db)
    assert cfg["fields"]["gender"]["label"] == "Pronouns"
    assert cfg["fields"]["gender"]["show"] is True           # default kept
    assert "bogus" not in cfg["fields"]
    assert cfg["questions"] == ["Q1"]
    app_db.set_setting(cfgmod.SETTING_KEY, "{not json")
    assert cfgmod.load_config(app_db) == cfgmod.default_config()


# ---------------------------------------------------------------------------
# bundle and versions
# ---------------------------------------------------------------------------

def test_versions(app_db, tmp_path):
    cfg = cfgmod.default_config()
    cfg["consent_text"] = "Consent v1"
    a = cfgmod.build_bundle(app_db, cfg, tmp_path)
    assert a == cfgmod.build_bundle(app_db, cfg, tmp_path)          # stable

    cfg["questions"] = ["New question"]
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
# Forms page and invitation guard
# ---------------------------------------------------------------------------

def test_forms_page_saves_and_pushes(client, app_db, airlock_server):
    cfg = cfgmod.default_config()
    cfg["fields"]["gender"]["label"] = "Pronouns"
    cfg["questions"] = ["What brings you here?"]
    cfg["consent_text"] = "# Consent\n\nNew wording."
    r = client.post("/airlock/forms", data=form_data(cfg))
    assert "msg=forms_saved" in r.headers["Location"]
    stored = cfgmod.load_config(app_db)
    assert stored["fields"]["gender"]["label"] == "Pronouns"
    assert stored["questions"] == ["What brings you here?"]
    assert airlock_server.config["consent_text"] == "# Consent\n\nNew wording."
    assert airlock_server.config["questions"] == ["What brings you here?"]
    assert b"Pronouns" in client.get("/airlock/forms").data


def test_forms_page_shows_the_fixed_answers_of_dropdown_fields(client, app_db, airlock_server):
    html = client.get("/airlock/forms").data.decode()
    assert "Client picks one: Email · Call my cell" in html
    assert "Client picks one: Yes · No" in html


def test_forms_page_saves_locally_when_server_unreachable(client, app_db, airlock_server):
    airlock_server.fail.add("put_config")
    cfg = cfgmod.default_config()
    cfg["consent_text"] = "Offline edit"
    r = client.post("/airlock/forms", data=form_data(cfg))
    assert "msg=forms_saved_local" in r.headers["Location"]
    assert cfgmod.load_config(app_db)["consent_text"] == "Offline edit"


def test_forms_page_rejects_invalid(client, app_db, airlock_server):
    before = cfgmod.load_config(app_db)
    cfg = cfgmod.default_config()
    for c in cfgmod.CONTACT_FIELDS:
        cfg["fields"][c]["required"] = False
    r = client.post("/airlock/forms", data=form_data(cfg))
    assert r.status_code == 400 and b"contact method" in r.data
    assert cfgmod.load_config(app_db) == before


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


def test_forms_page_has_csrf_and_escapes(client, app_db, airlock_server):
    cfg = cfgmod.default_config()
    cfg["consent_text"] = "</textarea><script>alert(1)</script>"
    cfgmod.save_config(app_db, cfg)
    html = client.get("/airlock/forms").data.decode()
    assert 'name="csrf_token"' in html
    assert "<script>alert(1)" not in html
