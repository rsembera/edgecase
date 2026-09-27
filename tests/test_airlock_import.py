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
        "preferred_contact": "text", "ok_to_leave_message": "yes",
        "emergency_contact_name": "Charles Babbage",
        "emergency_contact_relationship": "Friend",
        "emergency_contact_phone": "613-555-0102",
        "referral_source": "Psychology Today", "additional_info": "",
    }
    data = {"form": "intake", "fields": fields, "questions": [],
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


def complete_invitation(db, forms=("intake", "consent"), is_minor=False):
    inv = db.create_intake_invitation("Ada L.", email="ada@example.com",
                                      required_forms=forms, is_minor=is_minor)
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
    ({"questions": [{"question": "q", "answer": "a"}] * 6}, "malformed"),
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
# mapping and duplicates
# ---------------------------------------------------------------------------

def test_profile_mapping_matches_the_profile_form():
    p = ai.profile_fields(parsed_intake(), is_minor=False)
    assert p["content"] == "Woman"          # gender lives in content
    assert p["phone"] == "613-555-0101"     # the Profile's "Cell"
    assert p["text_number"] == "cell"       # prefers text, has a cell
    assert p["preferred_contact"] == "text"
    assert p["is_minor"] == 0
    assert "guardian1_name" not in p
    assert "session_total" not in p and "meeting_link" not in p


def test_questions_are_appended_to_additional_info():
    intake = parsed_intake(additional_info="Prefers mornings", questions=[
        {"question": "What brings you here?", "answer": "Stress"},
        {"question": "Seen a therapist before?", "answer": ""}])
    info = ai.profile_fields(intake, is_minor=False)["additional_info"]
    assert info.startswith("Prefers mornings\n\nQuestions from the online intake:")
    assert "What brings you here?\nStress" in info
    assert "Seen a therapist before?\n(no answer)" in info


def test_minor_mapping():
    intake = ai.parse_intake(enc(intake_payload(guardians=[
        {"name": "Anne", "email": "", "phone": "613-555-0103", "address": ""},
        {"name": "George", "email": "g@example.com", "phone": "", "address": ""}])),
        is_minor=True)
    p = ai.profile_fields(intake, is_minor=True)
    assert (p["is_minor"], p["guardian1_name"], p["guardian2_name"]) == (1, "Anne", "George")
    assert (p["guardian1_pays_percent"], p["guardian2_pays_percent"], p["has_guardian2"]) == (100.0, 0.0, 1)


def test_possible_duplicates(app_db):
    existing = app_db.add_client({"file_number": "D-1", "first_name": "ADA",
                                  "last_name": "lovelace", "type_id": 1})
    other = app_db.add_client({"file_number": "D-2", "first_name": "Augusta",
                               "last_name": "King", "type_id": 1})
    app_db.add_entry({"client_id": other, "class": "profile",
                      "email": "Ada@Example.com"})
    ids = [d["id"] for d in ai.possible_duplicates(app_db, parsed_intake())]
    assert ids == [existing, other]
    assert ai.possible_duplicates(app_db, parsed_intake(first_name="Grace",
                                                        email="grace@example.com")) == []


# ---------------------------------------------------------------------------
# import_client
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


def test_import_creates_the_whole_client_file(app_db, tmp_path):
    app_db.set_setting("file_number_format", "prefix-counter")
    app_db.set_setting("file_number_counter", "42")
    inv = complete_invitation(app_db)

    cid = ai.import_client(app_db, inv["id"], parsed_intake(), parsed_consent(),
                           type_id=1, received_at=RECEIVED, versions=VERSIONS,
                           attachments_dir=tmp_path)

    client = app_db.get_client(cid)
    assert (client["file_number"], client["first_name"], client["last_name"]) == \
        ("0042", "Ada", "Lovelace")
    profile = app_db.get_profile_entry(cid)
    assert profile["email"] == "ada@example.com"
    assert profile["content"] == "Woman"
    assert profile["date_of_birth"] == "1990-12-10"

    upload = [e for e in _entries(app_db, cid) if e["class"] == "upload"][0]
    assert upload["description"] == "Intake & consent (AirLock)"
    assert upload["locked"] == 1
    assert upload["upload_date"] == RECEIVED
    assert f"invitation #{inv['id']}".lower() in upload["content"].lower()
    assert "consent version consent-1" in upload["content"]

    atts = app_db.get_attachments(upload["id"])
    assert sorted(a["filename"] for a in atts) == ["Consent_0042.pdf", "Intake_0042.pdf"]
    for a in atts:
        on_disk = tmp_path / str(cid) / str(upload["id"])
        files = list(on_disk.iterdir())
        assert len(files) == 2
        assert all(f.suffix == ".enc" and "0042" not in f.name for f in files)
        assert all(f.read_bytes().startswith(b"%PDF") for f in files)

    inv = app_db.get_intake_invitation(inv["id"])
    assert (inv["status"], inv["client_id"]) == ("imported", cid)


def test_import_intake_only(app_db, tmp_path):
    app_db.set_setting("file_number_format", "manual")
    inv = complete_invitation(app_db, forms=("intake",))
    cid = ai.import_client(app_db, inv["id"], parsed_intake(), None, type_id=1,
                           received_at=RECEIVED, versions={}, manual_file_number="M-7",
                           attachments_dir=tmp_path)
    upload = [e for e in _entries(app_db, cid) if e["class"] == "upload"][0]
    assert upload["description"] == "Intake (AirLock)"
    assert [a["filename"] for a in app_db.get_attachments(upload["id"])] == ["Intake_M-7.pdf"]


def test_import_minor(app_db, tmp_path):
    inv = complete_invitation(app_db, is_minor=True)
    intake = ai.parse_intake(enc(intake_payload(guardians=[
        {"name": "Anne", "email": "", "phone": "613-555-0103", "address": ""}])),
        is_minor=True)
    app_db.set_setting("file_number_format", "date-initials")
    cid = ai.import_client(app_db, inv["id"], intake, parsed_consent(), type_id=1,
                           received_at=RECEIVED, versions=VERSIONS, attachments_dir=tmp_path)
    p = app_db.get_profile_entry(cid)
    assert (p["is_minor"], p["guardian1_name"]) == (1, "Anne")


@pytest.mark.parametrize("setup, fragment", [
    ("issued", "issued"),
    ("partial", "partial"),
    ("revoked", "revoked"),
    ("no_consent", "consent form is missing"),
    ("bad_type", "Unknown client type"),
])
def test_import_refusals_write_nothing(app_db, tmp_path, setup, fragment):
    inv = app_db.create_intake_invitation("Ada")
    consent = parsed_consent()
    type_id = 1
    if setup == "partial":
        app_db.record_intake_form_received(inv["id"], "intake")
    elif setup == "revoked":
        app_db.revoke_intake_invitation(inv["id"])
    elif setup in ("no_consent", "bad_type"):
        inv = complete_invitation(app_db)
        if setup == "no_consent":
            consent = None
        else:
            type_id = 999
    before = _counts(app_db)
    with pytest.raises(ai.AirLockImportError) as exc:
        ai.import_client(app_db, inv["id"], parsed_intake(), consent, type_id=type_id,
                         received_at=RECEIVED, versions=VERSIONS,
                         manual_file_number="X-1", attachments_dir=tmp_path)
    assert any(fragment in p for p in exc.value.problems)
    assert _counts(app_db) == before
    assert list(tmp_path.iterdir()) == []


def test_import_is_all_or_nothing(app_db, tmp_path, monkeypatch):
    """A failure after the first PDF is on disk and the client row written:
    the database rolls back, the file is removed, the invitation is untouched
    and can be imported again."""
    app_db.set_setting("file_number_format", "manual")
    inv = complete_invitation(app_db)
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
        ai.import_client(app_db, inv["id"], parsed_intake(), parsed_consent(),
                         type_id=1, received_at=RECEIVED, versions=VERSIONS,
                         manual_file_number="AON-1", attachments_dir=tmp_path)
    assert calls["n"] == 2
    assert _counts(app_db) == before
    assert not any(p.is_file() for p in tmp_path.rglob("*"))
    assert app_db.get_intake_invitation(inv["id"])["status"] == "complete"

    monkeypatch.setattr(ai.uuid, "uuid4", real)
    cid = ai.import_client(app_db, inv["id"], parsed_intake(), parsed_consent(),
                           type_id=1, received_at=RECEIVED, versions=VERSIONS,
                           manual_file_number="AON-1", attachments_dir=tmp_path)
    assert app_db.get_client(cid)["file_number"] == "AON-1"


def test_import_twice_is_refused(app_db, tmp_path):
    app_db.set_setting("file_number_format", "manual")
    inv = complete_invitation(app_db)
    ai.import_client(app_db, inv["id"], parsed_intake(), parsed_consent(), type_id=1,
                     received_at=RECEIVED, versions=VERSIONS, manual_file_number="T-1",
                     attachments_dir=tmp_path)
    with pytest.raises(ai.AirLockImportError):
        ai.import_client(app_db, inv["id"], parsed_intake(), parsed_consent(), type_id=1,
                         received_at=RECEIVED, versions=VERSIONS, manual_file_number="T-2",
                         attachments_dir=tmp_path)


def test_hostile_text_renders_safely(app_db, tmp_path):
    """ReportLab markup characters in every text field must be escaped, not
    interpreted: an unescaped '<' makes ReportLab raise."""
    app_db.set_setting("file_number_format", "manual")
    inv = complete_invitation(app_db)
    nasty = '<b>&amp; <font size="80">x</font> <script>alert(1)</script>'
    intake = parsed_intake(first_name="Ada<i>", last_name="Love & <lace>",
                           address=nasty, additional_info=nasty,
                           questions=[{"question": nasty, "answer": nasty}])
    consent = parsed_consent(consent_text=f"# {nasty}\n\n{nasty}\n\n- {nasty}")
    cid = ai.import_client(app_db, inv["id"], intake, consent, type_id=1,
                           received_at=RECEIVED, versions=VERSIONS,
                           manual_file_number="H-1", attachments_dir=tmp_path)
    assert app_db.get_client(cid)["last_name"] == "Love & <lace>"


def test_end_to_end_from_encrypted_envelopes(app_db, tmp_path):
    """Invitation -> browser-side encryption -> decrypt with EdgeCase's key and
    EdgeCase's own AAD -> parse -> import. The whole EdgeCase half of the
    pipeline, with only the network missing."""
    app_db.set_setting("file_number_format", "manual")
    inv = app_db.create_intake_invitation("Ada L.")
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
    cid = ai.import_client(app_db, inv["id"], ai.parse_intake(opened["intake"], False),
                           ai.parse_consent(opened["consent"]), type_id=1,
                           received_at=int(time.time()), versions=VERSIONS,
                           manual_file_number="E2E-1", attachments_dir=tmp_path)
    assert app_db.get_client(cid)["first_name"] == "Ada"
