"""AirLock import: validate decrypted submissions and create the client.

docs/Intake_Service_Plan.md. Everything in a submission was typed by someone
on the internet, so every field is treated as hostile until it has been
validated here: known keys only, strings only, control characters stripped,
lengths capped, choices checked against the Profile's own values. Nothing is
rendered raw anywhere downstream either (Jinja autoescape; the PDFs escape).

Submission plaintext (inside the encrypted envelope), one JSON object per form:

    intake:  {"form": "intake",
              "fields": {<Profile field>: str, ...},
              "questions": [{"question": str, "answer": str}, ...],   # <= 5
              "guardians": [{"name","email","phone","address"}, ...], # minor only, <= 2
              "attestation": {"typed_name": str, "agreed": true}}
    consent: {"form": "consent",
              "consent_text": str,          # exactly the text the client saw
              "attestation": {"typed_name": str, "agreed": true}}

The config and consent versions travel in the envelope's associated data, so
decryption itself proves them.

import_client() is all-or-nothing: PDFs are rendered and the file number
chosen before the first write; the client, Profile, Upload entry, attachment
rows and the invitation update are then written on one cursor and committed
once. Any failure rolls the database back and deletes files already written.
"""
import json
import os
import re
import shutil
import time
import unicodedata
import uuid
from datetime import date, datetime
from pathlib import Path

from core import config

# field -> (max length, kind)
INTAKE_FIELDS = {
    "first_name": (100, "line"),
    "middle_name": (100, "line"),
    "last_name": (100, "line"),
    "date_of_birth": (10, "date"),
    "gender": (100, "line"),
    "address": (500, "multiline"),
    "phone": (30, "phone"),            # labelled "Cell" in the Profile
    "home_phone": (30, "phone"),
    "work_phone": (30, "phone"),
    "email": (254, "email"),
    "preferred_contact": (20, "choice"),
    "ok_to_leave_message": (20, "choice"),
    "emergency_contact_name": (200, "line"),
    "emergency_contact_relationship": (100, "line"),
    "emergency_contact_phone": (30, "phone"),
    "referral_source": (300, "line"),
    "additional_info": (4000, "multiline"),
}
CHOICES = {
    "preferred_contact": {"", "email", "call_cell", "call_home", "call_work", "text"},
    "ok_to_leave_message": {"", "yes", "no"},
}
GUARDIAN_FIELDS = {
    "name": (200, "line"),
    "email": (254, "email"),
    "phone": (30, "phone"),
    "address": (500, "multiline"),
}
MAX_QUESTIONS = 5
MAX_QUESTION = 300
MAX_ANSWER = 2000
MAX_TYPED_NAME = 200
MAX_CONSENT_TEXT = 50_000

UPLOAD_DESCRIPTION = "Intake & consent (AirLock)"
UPLOAD_DESCRIPTION_INTAKE_ONLY = "Intake (AirLock)"

_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")
_PHONE = re.compile(r"^[0-9+().\-\s]{3,}(?:\s*(?:x|ext\.?)\s*\d{1,6})?$", re.I)
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f\u200b-\u200f\u202a-\u202e\u2066-\u2069]")


class AirLockImportError(ValueError):
    """A submission that cannot be imported. `problems` lists every reason,
    so the review screen can show them all at once."""

    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__("; ".join(self.problems))


# ---------------------------------------------------------------------------
# cleaning
# ---------------------------------------------------------------------------

def _clean(value, max_len, kind, label, problems):
    if value is None:
        return ""
    if not isinstance(value, str):
        problems.append(f"{label}: not text")
        return ""
    text = unicodedata.normalize("NFC", value).replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\t", " ")
    text = _CONTROL.sub("", text)
    if kind != "multiline":
        text = " ".join(text.split())
    else:
        text = "\n".join(line.rstrip() for line in text.split("\n")).strip()
    if len(text) > max_len:
        problems.append(f"{label}: longer than {max_len} characters")
        return ""
    if not text:
        return ""
    if kind == "email" and not _EMAIL.match(text):
        problems.append(f"{label}: not an email address")
        return ""
    if kind == "phone" and not _PHONE.match(text):
        problems.append(f"{label}: not a phone number")
        return ""
    if kind == "date":
        try:
            d = date.fromisoformat(text)
        except ValueError:
            problems.append(f"{label}: not a date (YYYY-MM-DD)")
            return ""
        if d.year < 1900 or d > date.today():
            problems.append(f"{label}: out of range")
            return ""
    return text


def _attestation(obj, problems, who="Attestation"):
    if not isinstance(obj, dict):
        problems.append(f"{who}: missing")
        return None
    name = _clean(obj.get("typed_name"), MAX_TYPED_NAME, "line", f"{who} name", problems)
    if not name:
        problems.append(f"{who}: no typed name")
    if obj.get("agreed") is not True:
        problems.append(f"{who}: agreement box not ticked")
    return {"typed_name": name, "agreed": obj.get("agreed") is True}


def parse_intake(plaintext: bytes, is_minor: bool) -> dict:
    """Decrypted intake bytes -> cleaned dict. Raises AirLockImportError."""
    problems = []
    try:
        data = json.loads(plaintext)
    except (ValueError, UnicodeDecodeError):
        raise AirLockImportError(["Intake: not valid JSON"]) from None
    if not isinstance(data, dict) or data.get("form") != "intake":
        raise AirLockImportError(["Intake: wrong form type"])

    raw = data.get("fields")
    if not isinstance(raw, dict):
        raise AirLockImportError(["Intake: no fields"])
    fields = {}
    for name, (max_len, kind) in INTAKE_FIELDS.items():
        label = name.replace("_", " ").capitalize()
        value = _clean(raw.get(name), max_len, kind, label, problems)
        if kind == "choice" and value not in CHOICES[name]:
            problems.append(f"{label}: unexpected value")
            value = ""
        fields[name] = value
    if not fields["first_name"]:
        problems.append("First name is required")
    if not fields["last_name"]:
        problems.append("Last name is required")
    if not any(fields[f] for f in ("email", "phone", "home_phone", "work_phone")):
        problems.append("At least one way to contact the client is required")

    questions = []
    raw_q = data.get("questions") or []
    if not isinstance(raw_q, list) or len(raw_q) > MAX_QUESTIONS:
        problems.append("Additional questions: malformed")
        raw_q = []
    for i, qa in enumerate(raw_q, 1):
        if not isinstance(qa, dict):
            problems.append(f"Question {i}: malformed")
            continue
        q = _clean(qa.get("question"), MAX_QUESTION, "line", f"Question {i}", problems)
        a = _clean(qa.get("answer"), MAX_ANSWER, "multiline", f"Answer {i}", problems)
        if q:
            questions.append({"question": q, "answer": a})

    guardians = []
    raw_g = data.get("guardians") or []
    if not isinstance(raw_g, list) or len(raw_g) > 2:
        problems.append("Guardians: malformed")
        raw_g = []
    if raw_g and not is_minor:
        problems.append("Guardians given, but the invitation was not for a minor")
        raw_g = []
    for i, g in enumerate(raw_g, 1):
        if not isinstance(g, dict):
            problems.append(f"Guardian {i}: malformed")
            continue
        guardians.append({k: _clean(g.get(k), n, kind, f"Guardian {i} {k}", problems)
                          for k, (n, kind) in GUARDIAN_FIELDS.items()})
    if is_minor and not (guardians and guardians[0]["name"]):
        problems.append("A guardian is required for a minor")

    attestation = _attestation(data.get("attestation"), problems, "Intake signature")
    if problems:
        raise AirLockImportError(problems)
    return {"fields": fields, "questions": questions, "guardians": guardians,
            "attestation": attestation}


def parse_consent(plaintext: bytes) -> dict:
    problems = []
    try:
        data = json.loads(plaintext)
    except (ValueError, UnicodeDecodeError):
        raise AirLockImportError(["Consent: not valid JSON"]) from None
    if not isinstance(data, dict) or data.get("form") != "consent":
        raise AirLockImportError(["Consent: wrong form type"])
    text = _clean(data.get("consent_text"), MAX_CONSENT_TEXT, "multiline",
                  "Consent text", problems)
    if not text:
        problems.append("Consent: no consent text")
    attestation = _attestation(data.get("attestation"), problems, "Consent signature")
    if problems:
        raise AirLockImportError(problems)
    return {"consent_text": text, "attestation": attestation}


# ---------------------------------------------------------------------------
# mapping and review
# ---------------------------------------------------------------------------

def profile_fields(intake: dict, is_minor: bool) -> dict:
    """The Profile entry columns an intake fills. Fees, session defaults and
    the meeting link are left for the practitioner, as with a manual client."""
    f = intake["fields"]
    info = f["additional_info"]
    if intake["questions"]:
        block = "\n\n".join(f"{qa['question']}\n{qa['answer'] or '(no answer)'}"
                            for qa in intake["questions"])
        info = (info + "\n\n" if info else "") + "Questions from the online intake:\n\n" + block
    out = {
        "description": f"{f['first_name']} {f['last_name']} - Profile",
        "content": f["gender"],            # the Profile keeps gender here
        "date_of_birth": f["date_of_birth"],
        "address": f["address"],
        "email": f["email"],
        "phone": f["phone"],
        "home_phone": f["home_phone"],
        "work_phone": f["work_phone"],
        "text_number": "cell" if f["preferred_contact"] == "text" and f["phone"] else "",
        "preferred_contact": f["preferred_contact"],
        "ok_to_leave_message": f["ok_to_leave_message"],
        "emergency_contact_name": f["emergency_contact_name"],
        "emergency_contact_phone": f["emergency_contact_phone"],
        "emergency_contact_relationship": f["emergency_contact_relationship"],
        "referral_source": f["referral_source"],
        "additional_info": info,
        "is_minor": 1 if is_minor else 0,
    }
    g = intake["guardians"]
    if is_minor and g:
        out.update({
            "guardian1_name": g[0]["name"], "guardian1_email": g[0]["email"],
            "guardian1_phone": g[0]["phone"], "guardian1_address": g[0]["address"],
            # Guardian 1 pays in full until the practitioner says otherwise;
            # 0 / 0 would bill nobody.
            "guardian1_pays_percent": 100.0,
            "has_guardian2": 1 if len(g) > 1 else 0,
            "guardian2_pays_percent": 0.0,
        })
        if len(g) > 1:
            out.update({"guardian2_name": g[1]["name"], "guardian2_email": g[1]["email"],
                        "guardian2_phone": g[1]["phone"], "guardian2_address": g[1]["address"]})
    return out


def possible_duplicates(db, intake: dict) -> list:
    """Existing clients who might be this person: same first and last name,
    or the same email on their Profile. For the review screen to show; it
    never blocks an import."""
    f = intake["fields"]
    cur = db.connect().cursor()
    cur.execute("""
        SELECT DISTINCT c.id, c.file_number, c.first_name, c.last_name
        FROM clients c
        LEFT JOIN entries e ON e.client_id = c.id AND e.class = 'profile'
        WHERE (LOWER(c.first_name) = LOWER(?) AND LOWER(c.last_name) = LOWER(?))
           OR (? != '' AND LOWER(e.email) = LOWER(?))
        ORDER BY c.id
    """, (f["first_name"], f["last_name"], f["email"], f["email"]))
    return [dict(zip(("id", "file_number", "first_name", "last_name"), r))
            for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# import
# ---------------------------------------------------------------------------

def _time_string(db, ts):
    dt = datetime.fromtimestamp(ts)
    if db.get_setting("time_format", "12h") == "24h":
        return dt.strftime("%H:%M")
    return dt.strftime("%I:%M %p").lstrip("0")


def _upload_notes(invitation, intake, consent, received_at, versions):
    when = datetime.fromtimestamp(received_at).strftime("%Y-%m-%d %H:%M")
    issued = datetime.fromtimestamp(invitation["issued_at"]).strftime("%Y-%m-%d")
    lines = [
        f"Submitted online through AirLock, received {when}.",
        f"Invitation #{invitation['id']} issued {issued} to {invitation['display_name']}.",
        f"Intake signed (typed name): {intake['attestation']['typed_name']}.",
    ]
    if consent:
        lines.append(f"Consent signed (typed name): {consent['attestation']['typed_name']}.")
    lines.append(f"Form version {versions.get('config_version') or 'n/a'}; "
                 f"consent version {versions.get('consent_version') or 'n/a'}.")
    return "\n".join(lines)


def import_client(db, invitation_id, intake: dict, consent: dict | None, *,
                  type_id: int, received_at: int, versions: dict,
                  manual_file_number: str | None = None,
                  attachments_dir: Path | None = None, assets_path: str | None = None,
                  now: int | None = None) -> int:
    """Create the client from validated submissions. Returns the client id.

    Raises AirLockImportError (nothing written) if the invitation is not
    ready, and re-raises anything else after rolling back.
    """
    from core.file_numbers import generate_file_number
    from core.encryption import encrypt_file
    from pdf.airlock_records import render_consent_pdf, render_intake_pdf

    inv = db.get_intake_invitation(invitation_id)
    if inv is None:
        raise AirLockImportError(["Unknown invitation"])
    status = db.invitation_effective_status(inv, now)
    if status != "complete":
        raise AirLockImportError([f"Invitation is {status}, not complete"])
    if "consent" in inv["required_forms"] and consent is None:
        raise AirLockImportError(["The consent form is missing"])
    if db.get_client_type(type_id) is None:
        raise AirLockImportError(["Unknown client type"])

    now = int(time.time()) if now is None else now
    attachments_dir = Path(attachments_dir or config.ATTACHMENTS_DIR)
    assets_path = assets_path or str(config.get_assets_path())
    f = intake["fields"]

    # Everything that can fail without side effects, first.
    intake_pdf = render_intake_pdf(db, intake, inv, received_at, assets_path)
    consent_pdf = (render_consent_pdf(db, consent, inv, received_at, versions, assets_path)
                   if consent else None)
    profile = profile_fields(intake, inv["is_minor"])
    upload_time = _time_string(db, received_at)
    notes = _upload_notes(inv, intake, consent, received_at, versions)
    # Last, because prefix-counter advances (and commits) its counter.
    file_number = generate_file_number(db, f["first_name"], f["middle_name"],
                                       f["last_name"], manual=manual_file_number)

    conn = db.connect()
    cur = conn.cursor()
    written = []
    try:
        cur.execute("""
            INSERT INTO clients (file_number, first_name, middle_name, last_name,
                                 type_id, session_offset, created_at, modified_at)
            VALUES (?, ?, ?, ?, ?, 0, ?, ?)
        """, (file_number, f["first_name"], f["middle_name"] or None, f["last_name"],
              type_id, now, now))
        client_id = cur.lastrowid

        cols = ["client_id", "class", "created_at", "modified_at"] + list(profile)
        vals = [client_id, "profile", now, now] + [
            (None if v == "" and k in db.TYPED_ENTRY_COLUMNS else v)
            for k, v in profile.items()]
        cur.execute(f"INSERT INTO entries ({', '.join(cols)}) "
                    f"VALUES ({', '.join('?' * len(vals))})", vals)

        cur.execute("""
            INSERT INTO entries (client_id, class, created_at, modified_at,
                                 description, content, upload_date, upload_time,
                                 locked, locked_at)
            VALUES (?, 'upload', ?, ?, ?, ?, ?, ?, 1, ?)
        """, (client_id, now, now,
              UPLOAD_DESCRIPTION if consent else UPLOAD_DESCRIPTION_INTAKE_ONLY,
              notes, received_at, upload_time, now))
        upload_id = cur.lastrowid

        target = attachments_dir / str(client_id) / str(upload_id)
        target.mkdir(parents=True, exist_ok=True)
        docs = [(f"Intake_{file_number}.pdf", "Intake form (AirLock)", intake_pdf)]
        if consent_pdf:
            docs.append((f"Consent_{file_number}.pdf", "Signed consent (AirLock)", consent_pdf))
        for display, description, pdf_bytes in docs:
            path = target / f"{uuid.uuid4()}.enc"
            path.write_bytes(pdf_bytes)
            written.append(path)
            if db.password:
                encrypt_file(str(path), db.password)
            try:
                stored = str(path.relative_to(config.DATA_ROOT))
            except ValueError:
                stored = str(path)
            cur.execute("""
                INSERT INTO attachments (entry_id, filename, description, filepath,
                                         filesize, uploaded_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (upload_id, display, description, stored, path.stat().st_size, now))

        cur.execute("UPDATE intake_invitations SET status = 'imported', "
                    "client_id = ?, imported_at = ? WHERE id = ? AND status = 'complete'",
                    (client_id, now, invitation_id))
        if cur.rowcount != 1:
            raise AirLockImportError(["Invitation changed during import"])
        conn.commit()
        return client_id
    except BaseException:
        conn.rollback()
        for path in written:
            try:
                os.remove(path)
            except OSError:
                pass
        if written:
            shutil.rmtree(written[0].parent, ignore_errors=True)
        raise

