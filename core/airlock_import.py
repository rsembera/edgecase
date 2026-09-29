"""AirLock import: validate decrypted submissions and create the client.

docs/Intake_Service_Plan.md. Everything in a submission was typed by someone
on the internet, so every field is treated as hostile until it has been
validated here: known keys only, strings only, control characters stripped,
lengths capped, choices checked against the Profile's own values. Nothing is
rendered raw anywhere downstream either (Jinja autoescape; the PDFs escape).

Submission plaintext (inside the encrypted envelope), one JSON object per form:

    intake:  {"form": "intake",
              "fields": {<Profile field>: str, ...},
              "guardians": [{"name","email","phone","address"}, ...], # minor only, <= 2
              "attestation": {"typed_name": str, "agreed": true}}
    consent: {"form": "consent",
              "consent_text": str,          # exactly the text the client saw
              "attestation": {"typed_name": str, "agreed": true}}

The config and consent versions travel in the envelope's associated data, so
decryption itself proves them.

import_client() fills in the invitation's client file (invitations are issued
from a client file). It is all-or-nothing: PDFs are rendered before the first
write; the name, Profile, Upload entry, attachment rows and the invitation
update are then written on one cursor and committed once. Any failure rolls the database back and deletes files already written.
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

# The intake form is the client-facing part of the Client Profile, fixed, in
# the Profile's order. Must match AirLock's airlock/validation.FIELDS.
# field -> (max length, kind, Profile label)
INTAKE_FIELDS = {
    "first_name": (100, "line", "First Name"),
    "middle_name": (100, "line", "Middle Name"),
    "last_name": (100, "line", "Last Name"),
    "date_of_birth": (10, "date", "Date of Birth"),
    "gender": (100, "line", "Gender"),
    "address": (500, "multiline", "Address"),
    "email": (254, "email", "Email"),
    "phone": (30, "phone", "Cell"),
    "home_phone": (30, "phone", "Home Phone"),
    "work_phone": (30, "phone", "Work Phone"),
    "text_number": (20, "choice", "Text Number"),
    "ok_to_leave_message": (20, "choice", "OK to Leave Message?"),
    "preferred_contact": (20, "choice", "Preferred Contact Method"),
    "emergency_contact_name": (200, "line", "Emergency Contact Name"),
    "emergency_contact_phone": (30, "phone", "Emergency Contact Phone"),
    "emergency_contact_relationship": (100, "line", "Emergency Contact Relationship"),
    "referral_source": (300, "line", "Referral Source"),
    "additional_info": (4000, "multiline", "Additional Information"),
}
# The Profile's dropdown values, with the Profile's wording for each.
CHOICE_LABELS = {
    "text_number": {"none": "None (no texting)", "cell": "Cell", "home": "Home Phone",
                    "work": "Work Phone"},
    "ok_to_leave_message": {"yes": "Yes", "no": "No"},
    "preferred_contact": {"email": "Email", "call_cell": "Call Cell", "call_home": "Call Home",
                          "call_work": "Call Work", "text": "Text Message"},
}
CHOICES = {name: {""} | set(labels) for name, labels in CHOICE_LABELS.items()}
# A choice that names a contact needs that contact filled in.
TEXTABLE = {"cell": "phone", "home": "home_phone", "work": "work_phone"}
CALLABLE = {"email": "email", "call_cell": "phone", "call_home": "home_phone",
            "call_work": "work_phone"}
CONTACT_FIELDS = ("email", "phone", "home_phone", "work_phone")
GUARDIAN_FIELDS = {
    "name": (200, "line"),
    "email": (254, "email"),
    "phone": (30, "phone"),
    "address": (500, "multiline"),
}
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
    for name, (max_len, kind, label) in INTAKE_FIELDS.items():
        value = _clean(raw.get(name), max_len, kind, label, problems)
        if kind == "choice" and value not in CHOICES[name]:
            problems.append(f"{label}: unexpected value")
            value = ""
        fields[name] = value
    if not fields["first_name"]:
        problems.append("First name is required")
    if not fields["last_name"]:
        problems.append("Last name is required")
    if not any(fields[f] for f in CONTACT_FIELDS):
        problems.append("At least one way to contact the client is required")
    tn, pc = fields["text_number"], fields["preferred_contact"]
    if tn in TEXTABLE and not fields[TEXTABLE[tn]]:
        problems.append(f"Text Number is {CHOICE_LABELS['text_number'][tn]}, "
                        "but that number is blank")
    if pc in CALLABLE and not fields[CALLABLE[pc]]:
        problems.append(f"Preferred Contact Method is {CHOICE_LABELS['preferred_contact'][pc]}, "
                        "but that contact is blank")
    if pc == "text" and tn not in TEXTABLE:
        problems.append("Preferred Contact Method is Text Message, but no Text Number was given")

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
    return {"fields": fields, "guardians": guardians, "attestation": attestation}


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

# The client file's own fields the review compares and the import writes:
# (key, label, where it lives, column). Names live on the client row; the
# rest on the Profile entry (gender in its `content`).
NAME_FIELDS = ("first_name", "middle_name", "last_name")
GUARDIAN_LABELS = (("name", "Name"), ("email", "Email"), ("phone", "Phone"),
                   ("address", "Address"))


def _review_fields(intake, is_minor):
    f = intake["fields"]
    out = []
    for name, (_, _, label) in INTAKE_FIELDS.items():
        where = "client" if name in NAME_FIELDS else "profile"
        column = "content" if name == "gender" else name
        out.append((name, label, where, column, f[name]))
    if is_minor:
        for i, g in enumerate(intake["guardians"][:2], 1):
            for key, label in GUARDIAN_LABELS:
                out.append((f"guardian{i}_{key}", f"Guardian {i} {label}", "profile",
                            f"guardian{i}_{key}", g[key]))
    return out


def review_rows(db, client_id, intake, is_minor) -> list:
    """What the client submitted beside what the file holds, one row per
    field. status: 'same', 'new' (file blank), 'changed', or 'blank' (the
    client left it empty: import leaves the file alone)."""
    client = db.get_client(client_id) or {}
    profile = db.get_profile_entry(client_id) or {}
    rows = []
    for key, label, where, column, submitted in _review_fields(intake, is_minor):
        held = (client if where == "client" else profile).get(column)
        held = "" if held is None else str(held)
        if not submitted:
            status = "blank"
        elif held == submitted:
            status = "same"
        elif not held:
            status = "new"
        else:
            status = "changed"
        labels = CHOICE_LABELS.get(key, {})
        rows.append({"key": key, "label": label, "where": where, "column": column,
                     "submitted": submitted, "on_file": held, "status": status,
                     "submitted_display": labels.get(submitted, submitted),
                     "on_file_display": labels.get(held, held)})
    return rows


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
                  received_at: int, versions: dict, keep=(),
                  attachments_dir: Path | None = None, assets_path: str | None = None,
                  now: int | None = None) -> int:
    """Apply validated submissions to the invitation's client file. Returns
    the client id.

    The client's answer replaces what is on file, except for keys in `keep`
    (the practitioner ticked "keep what's on file") and answers left blank,
    which change nothing. The PDFs go into a new locked Upload entry.

    Raises AirLockImportError (nothing written) if the invitation is not
    ready, and re-raises anything else after rolling back.
    """
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
    client_id = inv["client_id"]
    client = db.get_client(client_id) if client_id else None
    if client is None:
        raise AirLockImportError(["This invitation is not linked to a client file"])

    now = int(time.time()) if now is None else now
    attachments_dir = Path(attachments_dir or config.ATTACHMENTS_DIR)
    assets_path = assets_path or str(config.get_assets_path())
    file_number = client["file_number"]
    keep = set(keep)

    # Everything that can fail without side effects, first.
    intake_pdf = render_intake_pdf(db, intake, inv, received_at, assets_path)
    consent_pdf = (render_consent_pdf(db, consent, inv, received_at, versions, assets_path)
                   if consent else None)
    upload_time = _time_string(db, received_at)
    notes = _upload_notes(inv, intake, consent, received_at, versions)
    rows = review_rows(db, client_id, intake, inv["is_minor"])
    apply = [r for r in rows if r["status"] in ("new", "changed") and r["key"] not in keep]
    name_updates = {r["column"]: r["submitted"] for r in apply if r["where"] == "client"}
    profile_updates = {r["column"]: r["submitted"] for r in apply if r["where"] == "profile"}
    existing = db.get_profile_entry(client_id)
    if inv["is_minor"]:
        profile_updates["is_minor"] = 1
        guardians = intake["guardians"]
        if guardians and not (existing or {}).get("guardian1_name"):
            # Guardian 1 pays in full until the practitioner says otherwise;
            # 0 / 0 would bill nobody.
            profile_updates.setdefault("guardian1_pays_percent", 100.0)
            profile_updates.setdefault("guardian2_pays_percent", 0.0)
        if len(guardians) > 1:
            profile_updates["has_guardian2"] = 1
    changed_labels = [r["label"] for r in apply]

    conn = db.connect()
    cur = conn.cursor()
    written = []
    try:
        if name_updates:
            sets = ", ".join(f"{c} = ?" for c in name_updates)
            cur.execute(f"UPDATE clients SET {sets}, modified_at = ? WHERE id = ?",
                        list(name_updates.values()) + [now, client_id])

        history = {"timestamp": now, "description":
                   "Updated from the AirLock intake: " + ", ".join(changed_labels)}
        if existing:
            if profile_updates or changed_labels:
                old = json.loads(existing.get("edit_history") or "[]")
                cols = dict(profile_updates)
                if changed_labels:
                    cols["edit_history"] = json.dumps(old + [history])
                sets = ", ".join(f"{c} = ?" for c in cols)
                cur.execute(f"UPDATE entries SET {sets}, modified_at = ? WHERE id = ?",
                            list(cols.values()) + [now, existing["id"]])
        else:
            first = name_updates.get("first_name", client["first_name"])
            last = name_updates.get("last_name", client["last_name"])
            cols = {"client_id": client_id, "class": "profile", "created_at": now,
                    "modified_at": now, "description": f"{first} {last} - Profile",
                    **profile_updates}
            cur.execute(f"INSERT INTO entries ({', '.join(cols)}) "
                        f"VALUES ({', '.join('?' * len(cols))})", list(cols.values()))

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

        cur.execute("UPDATE intake_invitations SET status = 'imported', imported_at = ? "
                    "WHERE id = ? AND status = 'complete' AND client_id = ?",
                    (now, invitation_id, client_id))
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
