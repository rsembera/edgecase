"""AirLock import: validation, mapping, and the all-or-nothing client import.

Everything in a submission was typed by someone on the internet. These tests
feed parse_* the shapes a hostile or broken page could send, check that the
Profile mapping matches the Profile form, and prove import_client either
creates the whole client file or leaves nothing behind.
"""
import json
import time
import uuid

import pytest

from core import airlock_crypto as ac
from core import airlock_import as ai

RECEIVED = 1_790_000_000


def intake_payload(**overrides):
    fields = {
        "first_name": "Ada", "middle_name": "", "last_name": "Lovelace",
        "date_of_birth": "1990-12-10", "gender": "Woman",
        "address": "12 Analytical Way\nOttawa ON", "phone": "613-555-0101",
        "home_phone": "", "work_phone": "", "email": "ada@example.com",
        "text_number": "cell", "preferred_contact": "text", "ok_to_leave_message": "yes",
        "emergency_contact_name": "Charles Babbage",
        "emergency_contact_relationship": "Friend",
        "emergency_contact_phone": "613-555-0102",
        "referral_source": "Psychology Today", "additional_info": "",
    }
    data = {"form": "intake", "fields": fields,
            "guardians": [], "attestation": {"typed_name": "Ada Lovelace", "agreed": True}}
    for k, v in overrides.items():
        if k in fields:
            fields[k] = v
        else:
            data[k] = v
    return data


def consent_payload(**overrides):
    data = {"form": "consent",
            "consent_text": "# Consent\n\nI agree to psychotherapy.\n\n- Fees apply\n- 24h notice",
            "attestation": {"typed_name": "Ada Lovelace", "agreed": True}}
    data.update(overrides)
    return data


def enc(obj):
    return json.dumps(obj).encode()


def parsed_intake(**kw):
    return ai.parse_intake(enc(intake_payload(**kw)), is_minor=False)


def parsed_consent(**kw):
    return ai.parse_consent(enc(consent_payload(**kw)))


def a_client(db, first="Ada", last="Lovelace", file_number="C-1", **profile):
    """A client file as it exists before intake: created at inquiry, with
    whatever Profile details the practitioner already has."""
    cid = db.add_client({"file_number": file_number, "first_name": first,
                         "last_name": last, "type_id": 1})
    if profile:
        db.add_entry({"client_id": cid, "class": "profile",
                      "description": f"{first} {last} - Profile", **profile})
    return cid


def complete_invitation(db, forms=("intake", "consent"), is_minor=False, client_id=None):
    if client_id is None:
        client_id = a_client(db)
    inv = db.create_intake_invitation("Ada L.", email="ada@example.com",
                                      required_forms=forms, is_minor=is_minor,
                                      client_id=client_id)
    for f in forms:
        db.record_intake_form_received(inv["id"], f)
    return db.get_intake_invitation(inv["id"])


# ---------------------------------------------------------------------------
# parse_intake
# ---------------------------------------------------------------------------

def test_parse_intake_valid():
    out = parsed_intake()
    assert out["fields"]["first_name"] == "Ada"
    assert out["fields"]["address"] == "12 Analytical Way\nOttawa ON"
    assert out["attestation"] == {"typed_name": "Ada Lovelace", "agreed": True}


def test_parse_intake_cleans_text():
    out = parsed_intake(first_name="  A\u200bda\x00 \n  ", last_name="Love\tlace",
                        additional_info="line one\r\n\x07line two  ")
    assert out["fields"]["first_name"] == "Ada"
    assert out["fields"]["last_name"] == "Love lace"
    assert out["fields"]["additional_info"] == "line one\nline two"


def test_unknown_fields_are_ignored():
    data = intake_payload()
    data["fields"]["is_minor"] = "1"
    data["fields"]["session_total"] = "0.01"
    data["fields"]["client_id"] = 99
    out = ai.parse_intake(enc(data), is_minor=False)
    assert set(out["fields"]) == set(ai.INTAKE_FIELDS)


@pytest.mark.parametrize("overrides, fragment", [
    ({"first_name": ""}, "First name is required"),
    ({"last_name": "   "}, "Last name is required"),
    ({"email": "", "phone": ""}, "contact the client"),
    ({"email": "not-an-email"}, "not an email"),
    ({"phone": "call me maybe"}, "not a phone"),
    ({"date_of_birth": "10/12/1990"}, "not a date"),
    ({"date_of_birth": "2999-01-01"}, "out of range"),
    ({"date_of_birth": "1850-01-01"}, "out of range"),
    ({"address": "x" * 501}, "longer than 500"),
    ({"first_name": ["Ada"]}, "not text"),
    ({"preferred_contact": "carrier pigeon"}, "unexpected value"),
    ({"ok_to_leave_message": "maybe"}, "unexpected value"),
    ({"text_number": "fax"}, "unexpected value"),
    ({"text_number": "home"}, "Text Number is Home Phone, but that number is blank"),
    ({"preferred_contact": "call_work"}, "Call Work, but that contact is blank"),
    ({"preferred_contact": "email", "email": ""}, "Email, but that contact is blank"),
    ({"text_number": "none"}, "Text Message, but no Text Number"),
    ({"text_number": ""}, "Text Message, but no Text Number"),
    ({"guardians": [{"name": "Mom"}]}, "not for a minor"),
    ({"attestation": {"typed_name": "Ada", "agreed": "true"}}, "not ticked"),
    ({"attestation": {"typed_name": "", "agreed": True}}, "no typed name"),
    ({"attestation": None}, "missing"),
])
def test_parse_intake_rejects(overrides, fragment):
    with pytest.raises(ai.AirLockImportError) as exc:
        parsed_intake(**overrides)
    assert any(fragment in p for p in exc.value.problems), exc.value.problems


@pytest.mark.parametrize("raw", [b"not json", b"[]", enc({"form": "consent"}),
                                 enc({"form": "intake", "fields": "x"}),
                                 b"\xff\xfe"])
def test_parse_intake_rejects_shapes(raw):
    with pytest.raises(ai.AirLockImportError):
        ai.parse_intake(raw, is_minor=False)


def test_all_problems_reported_together():
    with pytest.raises(ai.AirLockImportError) as exc:
        parsed_intake(first_name="", email="bad", phone="", attestation={})
    assert len(exc.value.problems) >= 4


def test_minor_needs_a_guardian():
    with pytest.raises(ai.AirLockImportError) as exc:
        ai.parse_intake(enc(intake_payload()), is_minor=True)
    assert any("guardian is required" in p for p in exc.value.problems)
    out = ai.parse_intake(enc(intake_payload(guardians=[
        {"name": "Anne Byron", "email": "anne@example.com", "phone": "613-555-0103",
         "address": ""}])), is_minor=True)
    assert out["guardians"][0]["name"] == "Anne Byron"


# ---------------------------------------------------------------------------
# parse_consent
# ---------------------------------------------------------------------------

def test_parse_consent_valid():
    assert parsed_consent()["consent_text"].startswith("# Consent")


@pytest.mark.parametrize("overrides", [
    {"consent_text": ""},
    {"consent_text": "x" * (ai.MAX_CONSENT_TEXT + 1)},
    {"attestation": {"typed_name": "Ada", "agreed": False}},
    {"form": "intake"},
])
def test_parse_consent_rejects(overrides):
    with pytest.raises(ai.AirLockImportError):
        parsed_consent(**overrides)


# ---------------------------------------------------------------------------
# the form mirrors the Profile
# ---------------------------------------------------------------------------

def test_intake_fields_follow_the_client_profile_order():
    import re
    from pathlib import Path
    profile = (Path(__file__).resolve().parent.parent
               / "web/templates/entry_forms/profile.html").read_text()
    names = re.findall(r'<(?:input|select|textarea)[^>]*\bname="([a-z_0-9]+)"', profile)
    assert [n for n in dict.fromkeys(names) if n in ai.INTAKE_FIELDS] == list(ai.INTAKE_FIELDS)


def test_choices_are_the_profile_dropdown_values():
    import re
    from pathlib import Path
    profile = (Path(__file__).resolve().parent.parent
               / "web/templates/entry_forms/profile.html").read_text()
    for name, labels in ai.CHOICE_LABELS.items():
        block = re.search(rf'<select id="{name}".*?</select>', profile, re.S).group(0)
        values = set(re.findall(r'<option value="([^"]*)"', block)) - {""}
        assert values == set(labels), name


# ---------------------------------------------------------------------------
# review: the client's answers beside the file
# ---------------------------------------------------------------------------

def _rows(db, cid, intake, is_minor=False):
    return {r["key"]: r for r in ai.review_rows(db, cid, intake, is_minor)}


def test_review_rows_compare_answers_with_the_file(app_db):
    cid = a_client(app_db, email="old@example.com", phone="613-555-0101",
                   ok_to_leave_message="yes", additional_info="Referred by Dr. B")
    rows = _rows(app_db, cid, parsed_intake())
    assert rows["first_name"]["status"] == "same"
    assert rows["email"]["status"] == "changed"
    assert (rows["email"]["on_file"], rows["email"]["submitted"]) == \
        ("old@example.com", "ada@example.com")
    assert rows["phone"]["status"] == "same"
    assert rows["gender"]["status"] == "new" and rows["gender"]["column"] == "content"
    assert rows["additional_info"]["status"] == "blank"       # client left it empty
    assert rows["middle_name"]["status"] == "blank"
    assert rows["preferred_contact"]["submitted_display"] == "Text Message"
    assert "guardian1_name" not in rows


def test_review_rows_include_guardians_for_a_minor(app_db):
    cid = a_client(app_db)
    intake = ai.parse_intake(enc(intake_payload(guardians=[
        {"name": "Anne", "email": "", "phone": "613-555-0103", "address": ""}])),
        is_minor=True)
    rows = _rows(app_db, cid, intake, is_minor=True)
    assert rows["guardian1_name"]["status"] == "new"
    assert rows["guardian1_email"]["status"] == "blank"


# ---------------------------------------------------------------------------
# import_client: fills in the invitation's client file
# ---------------------------------------------------------------------------

def _entries(db, client_id):
    cur = db.connect().cursor()
    cur.execute("SELECT id, class, description, content, locked, upload_date "
                "FROM entries WHERE client_id = ? ORDER BY id", (client_id,))
    return [dict(zip(("id", "class", "description", "content", "locked", "upload_date"), r))
            for r in cur.fetchall()]


def _counts(db):
    cur = db.connect().cursor()
    out = {}
    for t in ("clients", "entries", "attachments"):
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        out[t] = cur.fetchone()[0]
    return out


VERSIONS = {"config_version": "cfg-1", "consent_version": "consent-1"}


def _import(db, inv, tmp_path, intake=None, consent="default", **kw):
    return ai.import_client(db, inv["id"], intake or parsed_intake(),
                            parsed_consent() if consent == "default" else consent,
                            received_at=RECEIVED, versions=VERSIONS,
                            attachments_dir=tmp_path, **kw)


def test_import_fills_the_existing_client_file(app_db, tmp_path):
    cid = a_client(app_db, file_number="0042", email="old@example.com",
                   ok_to_leave_message="no")
    inv = complete_invitation(app_db, client_id=cid)
    before = _counts(app_db)

    assert _import(app_db, inv, tmp_path) == cid
    assert _counts(app_db)["clients"] == before["clients"]          # no new client
    profiles = [e for e in _entries(app_db, cid) if e["class"] == "profile"]
    assert len(profiles) == 1                                        # updated, not added

    profile = app_db.get_profile_entry(cid)
    assert profile["email"] == "ada@example.com"                    # client's answer wins
    assert profile["ok_to_leave_message"] == "yes"
    assert profile["content"] == "Woman"
    assert profile["date_of_birth"] == "1990-12-10"
    assert (profile["text_number"], profile["preferred_contact"]) == ("cell", "text")
    history = app_db.get_edit_history(profile["id"])
    assert "Updated from the AirLock intake" in history[-1]["description"]
    assert "Email" in history[-1]["description"]
    assert "ada@example.com" not in history[-1]["description"]     # names, not values

    upload = [e for e in _entries(app_db, cid) if e["class"] == "upload"][0]
    assert upload["description"] == "Intake & consent (AirLock)"
    assert upload["locked"] == 1 and upload["upload_date"] == RECEIVED
    assert f"invitation #{inv['id']}".lower() in upload["content"].lower()
    assert "consent version consent-1" in upload["content"]
    atts = app_db.get_attachments(upload["id"])
    assert sorted(a["filename"] for a in atts) == ["Consent_0042.pdf", "Intake_0042.pdf"]
    files = list((tmp_path / str(cid) / str(upload["id"])).iterdir())
    assert len(files) == 2
    assert all(f.suffix == ".enc" and f.read_bytes().startswith(b"%PDF") for f in files)

    inv = app_db.get_intake_invitation(inv["id"])
    assert (inv["status"], inv["client_id"]) == ("imported", cid)


def test_review_rows_compare_phone_numbers_by_digits(app_db):
    # Phone autofill writes +1 and no punctuation; the same number is no change.
    cid = a_client(app_db, phone="6132219737", home_phone="(613) 555-0199",
                   work_phone="613-555-0100 x12", emergency_contact_phone="6135550102")
    rows = _rows(app_db, cid, parsed_intake(phone="+16132219737",
                                            home_phone="1 613 555 0199",
                                            work_phone="613-555-0100",
                                            emergency_contact_phone="+1 613-850-9737"))
    assert rows["phone"]["status"] == "same"
    assert rows["home_phone"]["status"] == "same"
    assert rows["work_phone"]["status"] == "changed"          # extension dropped
    assert rows["emergency_contact_phone"]["status"] == "changed"


def test_same_phone_in_another_format_keeps_the_files_format(app_db, tmp_path):
    cid = a_client(app_db, phone="6132219737")
    inv = complete_invitation(app_db, client_id=cid)
    _import(app_db, inv, tmp_path, intake=parsed_intake(phone="+16132219737"))
    assert app_db.get_profile_entry(cid)["phone"] == "6132219737"


def test_keep_on_file_overrides_the_clients_answer(app_db, tmp_path):
    cid = a_client(app_db, email="old@example.com", phone="613-555-0000")
    inv = complete_invitation(app_db, client_id=cid)
    _import(app_db, inv, tmp_path, keep=["email"])
    profile = app_db.get_profile_entry(cid)
    assert profile["email"] == "old@example.com"
    assert profile["phone"] == "613-555-0101"


def test_a_rejected_addition_leaves_the_field_empty(app_db, tmp_path):
    cid = a_client(app_db, email="old@example.com")
    inv = complete_invitation(app_db, client_id=cid)
    _import(app_db, inv, tmp_path, keep=["referral_source"])
    profile = app_db.get_profile_entry(cid)
    assert not profile["referral_source"]
    assert profile["emergency_contact_name"] == "Charles Babbage"


def test_blank_answers_never_erase_the_file(app_db, tmp_path):
    cid = a_client(app_db, additional_info="Referred by Dr. B", work_phone="613-555-0200")
    inv = complete_invitation(app_db, client_id=cid)
    _import(app_db, inv, tmp_path)        # the client left both blank
    profile = app_db.get_profile_entry(cid)
    assert profile["additional_info"] == "Referred by Dr. B"
    assert profile["work_phone"] == "613-555-0200"


def test_a_name_change_updates_the_client_but_not_the_file_number(app_db, tmp_path):
    cid = a_client(app_db, first="Ada", last="Lovelace", file_number="AL-1")
    inv = complete_invitation(app_db, client_id=cid)
    _import(app_db, inv, tmp_path, intake=parsed_intake(first_name="Augusta",
                                                        middle_name="Ada"))
    client = app_db.get_client(cid)
    assert (client["first_name"], client["middle_name"], client["last_name"],
            client["file_number"]) == ("Augusta", "Ada", "Lovelace", "AL-1")


def test_a_file_without_a_profile_gets_one(app_db, tmp_path):
    cid = a_client(app_db)                # no Profile yet
    inv = complete_invitation(app_db, client_id=cid)
    _import(app_db, inv, tmp_path)
    profile = app_db.get_profile_entry(cid)
    assert profile["description"] == "Ada Lovelace - Profile"
    assert profile["email"] == "ada@example.com"


def test_text_number_comes_from_the_client_not_a_guess(app_db, tmp_path):
    """The old import guessed "cell" whenever the client preferred texting;
    a client who texts from a home line lost their text number."""
    cid = a_client(app_db)
    inv = complete_invitation(app_db, client_id=cid)
    _import(app_db, inv, tmp_path, intake=parsed_intake(home_phone="613-555-0199",
                                                        text_number="home"))
    assert app_db.get_profile_entry(cid)["text_number"] == "home"


def test_import_intake_only(app_db, tmp_path):
    cid = a_client(app_db, file_number="M-7")
    inv = complete_invitation(app_db, forms=("intake",), client_id=cid)
    _import(app_db, inv, tmp_path, consent=None)
    upload = [e for e in _entries(app_db, cid) if e["class"] == "upload"][0]
    assert upload["description"] == "Intake (AirLock)"
    assert [a["filename"] for a in app_db.get_attachments(upload["id"])] == ["Intake_M-7.pdf"]


def test_import_minor(app_db, tmp_path):
    cid = a_client(app_db)
    inv = complete_invitation(app_db, is_minor=True, client_id=cid)
    intake = ai.parse_intake(enc(intake_payload(guardians=[
        {"name": "Anne", "email": "", "phone": "613-555-0103", "address": ""},
        {"name": "George", "email": "g@example.com", "phone": "", "address": ""}])),
        is_minor=True)
    _import(app_db, inv, tmp_path, intake=intake)
    p = app_db.get_profile_entry(cid)
    assert (p["is_minor"], p["guardian1_name"], p["guardian2_name"]) == (1, "Anne", "George")
    assert (p["guardian1_pays_percent"], p["guardian2_pays_percent"], p["has_guardian2"]) == \
        (100.0, 0.0, 1)


def test_import_minor_keeps_an_existing_payment_split(app_db, tmp_path):
    cid = a_client(app_db, is_minor=1, guardian1_name="Anne", guardian1_pays_percent=60.0,
                   guardian2_pays_percent=40.0)
    inv = complete_invitation(app_db, is_minor=True, client_id=cid)
    intake = ai.parse_intake(enc(intake_payload(guardians=[
        {"name": "Anne B.", "email": "", "phone": "613-555-0103", "address": ""}])),
        is_minor=True)
    _import(app_db, inv, tmp_path, intake=intake)
    p = app_db.get_profile_entry(cid)
    assert (p["guardian1_name"], p["guardian1_pays_percent"]) == ("Anne B.", 60.0)


@pytest.mark.parametrize("setup, fragment", [
    ("issued", "issued"),
    ("partial", "partial"),
    ("revoked", "revoked"),
    ("no_consent", "consent form is missing"),
    ("unlinked", "not linked to a client file"),
])
def test_import_refusals_write_nothing(app_db, tmp_path, setup, fragment):
    inv = app_db.create_intake_invitation("Ada", client_id=a_client(app_db))
    consent = parsed_consent()
    if setup == "partial":
        app_db.record_intake_form_received(inv["id"], "intake")
    elif setup == "revoked":
        app_db.revoke_intake_invitation(inv["id"])
    elif setup == "no_consent":
        inv = complete_invitation(app_db, client_id=inv["client_id"])
        consent = None
    elif setup == "unlinked":
        inv = app_db.create_intake_invitation("Old standalone invitation")
        for f in ("intake", "consent"):
            app_db.record_intake_form_received(inv["id"], f)
    before = _counts(app_db)
    with pytest.raises(ai.AirLockImportError) as exc:
        _import(app_db, inv, tmp_path, consent=consent)
    assert any(fragment in p for p in exc.value.problems)
    assert _counts(app_db) == before
    assert list(tmp_path.iterdir()) == []


def test_import_is_all_or_nothing(app_db, tmp_path, monkeypatch):
    """A failure after the first PDF is on disk and the Profile updated: the
    database rolls back, the file is removed, the invitation is untouched and
    can be imported again."""
    cid = a_client(app_db, email="old@example.com")
    inv = complete_invitation(app_db, client_id=cid)
    before = _counts(app_db)

    calls = {"n": 0}
    real = uuid.uuid4

    def flaky():
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("disk full")
        return real()

    monkeypatch.setattr(ai.uuid, "uuid4", flaky)
    with pytest.raises(OSError):
        _import(app_db, inv, tmp_path, intake=parsed_intake(first_name="Augusta"))
    assert calls["n"] == 2
    assert _counts(app_db) == before
    assert app_db.get_profile_entry(cid)["email"] == "old@example.com"
    assert app_db.get_client(cid)["first_name"] == "Ada"
    assert not any(p.is_file() for p in tmp_path.rglob("*"))
    assert app_db.get_intake_invitation(inv["id"])["status"] == "complete"

    monkeypatch.setattr(ai.uuid, "uuid4", real)
    _import(app_db, inv, tmp_path)
    assert app_db.get_profile_entry(cid)["email"] == "ada@example.com"


def test_import_twice_is_refused(app_db, tmp_path):
    inv = complete_invitation(app_db)
    _import(app_db, inv, tmp_path)
    with pytest.raises(ai.AirLockImportError):
        _import(app_db, inv, tmp_path)


def test_hostile_text_renders_safely(app_db, tmp_path):
    """ReportLab markup characters in every text field must be escaped, not
    interpreted: an unescaped '<' makes ReportLab raise."""
    inv = complete_invitation(app_db)
    nasty = '<b>&amp; <font size="80">x</font> <script>alert(1)</script>'
    intake = parsed_intake(first_name="Ada<i>", last_name="Love & <lace>",
                           address=nasty, additional_info=nasty, gender=nasty,
                           referral_source=nasty)
    consent = parsed_consent(consent_text=f"# {nasty}\n\n{nasty}\n\n- {nasty}")
    cid = _import(app_db, inv, tmp_path, intake=intake, consent=consent)
    assert app_db.get_client(cid)["last_name"] == "Love & <lace>"


def test_end_to_end_from_encrypted_envelopes(app_db, tmp_path):
    """Invitation -> browser-side encryption -> decrypt with EdgeCase's key and
    EdgeCase's own AAD -> parse -> import. The whole EdgeCase half of the
    pipeline, with only the network missing."""
    cid = a_client(app_db)
    inv = app_db.create_intake_invitation("Ada L.", client_id=cid)
    kid, public = app_db.airlock_public_key()
    envelopes = {}
    for form, payload in (("intake", intake_payload()), ("consent", consent_payload())):
        aad = ac.build_aad(inv["token_hash"], form, "cfg-1", "consent-1")
        envelopes[form] = ac.encrypt_for_testing(enc(payload), public, kid, aad)
        app_db.record_intake_form_received(inv["id"], form)

    keys = app_db.airlock_private_keys()
    opened = {form: ac.decrypt_envelope(
        env, keys, ac.build_aad(inv["token_hash"], form, "cfg-1", "consent-1"))
        for form, env in envelopes.items()}
    ai.import_client(app_db, inv["id"], ai.parse_intake(opened["intake"], False),
                     ai.parse_consent(opened["consent"]), received_at=int(time.time()),
                     versions=VERSIONS, attachments_dir=tmp_path)
    assert app_db.get_profile_entry(cid)["email"] == "ada@example.com"
