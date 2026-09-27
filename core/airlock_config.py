"""AirLock form customization: what the online forms show, and the bundle
pushed to the server.

docs/Intake_Service_Plan.md, "Customization". The mapping from intake field
to Profile column never changes; what the practitioner controls is each
field's visibility, whether it is required, and its label, plus up to five
free-text questions of their own and the consent text. Branding is not
configured here: it is the Practice Information EdgeCase already holds for
statements.

The config is stored in settings as `airlock_form_config` (JSON). The bundle
built from it carries two versions, both short content hashes:
    consent_version  changes only when the consent text changes
    config_version   changes when anything in the bundle changes
Both travel in every submission's associated data, so a record always says
exactly which form and which consent wording the client saw.
"""
import base64
import hashlib
import json
from io import BytesIO
from pathlib import Path

# (field, default label, shown by default, required by default)
FIELDS = [
    ("first_name", "First name", True, True),
    ("middle_name", "Middle name", True, False),
    ("last_name", "Last name", True, True),
    ("date_of_birth", "Date of birth", True, True),
    ("gender", "Gender", True, False),
    ("address", "Address", True, True),
    ("phone", "Cell phone", True, False),
    ("home_phone", "Home phone", True, False),
    ("work_phone", "Work phone", True, False),
    ("email", "Email", True, True),
    ("preferred_contact", "Preferred way to contact you", True, False),
    ("ok_to_leave_message", "OK to leave a message?", True, False),
    ("emergency_contact_name", "Emergency contact name", True, True),
    ("emergency_contact_relationship", "Emergency contact relationship", True, False),
    ("emergency_contact_phone", "Emergency contact phone", True, True),
    ("referral_source", "How did you hear about this practice?", True, False),
    ("additional_info", "Anything else you'd like me to know?", True, False),
]
FIELD_NAMES = [f[0] for f in FIELDS]
ALWAYS_REQUIRED = {"first_name", "last_name"}
CONTACT_FIELDS = ("email", "phone", "home_phone", "work_phone")

MAX_LABEL = 100
MAX_QUESTIONS = 5
MAX_QUESTION = 300
MAX_CONSENT = 50_000
MAX_LOGO_BYTES = 300 * 1024
LOGO_BOX = (600, 300)

SETTING_KEY = "airlock_form_config"


def default_config():
    return {
        "fields": {name: {"label": label, "show": show, "required": req}
                   for name, label, show, req in FIELDS},
        "questions": [],
        "consent_text": "",
    }


def load_config(db):
    """Stored config merged over the defaults, so a field added in a later
    version appears with its defaults instead of vanishing."""
    cfg = default_config()
    raw = db.get_setting(SETTING_KEY, "")
    if not raw:
        return cfg
    try:
        stored = json.loads(raw)
    except ValueError:
        return cfg
    for name, meta in (stored.get("fields") or {}).items():
        if name in cfg["fields"] and isinstance(meta, dict):
            cfg["fields"][name].update({k: meta[k] for k in ("label", "show", "required")
                                        if k in meta})
    cfg["questions"] = [q for q in stored.get("questions") or [] if isinstance(q, str)]
    cfg["consent_text"] = stored.get("consent_text") or ""
    return cfg


def _line(value):
    return " ".join(str(value or "").split())


def validate_config(data):
    """Form input -> clean config. Raises ValueError listing every problem.

    Rules: first and last name are always shown and required; at least one
    contact method is shown and required (the import refuses a client it
    cannot reach); a required field must be shown.
    """
    problems = []
    fields = {}
    raw_fields = data.get("fields") or {}
    for name, default_label, _, _ in FIELDS:
        meta = raw_fields.get(name) or {}
        label = _line(meta.get("label")) or default_label
        if len(label) > MAX_LABEL:
            problems.append(f"Label for {default_label.lower()} is too long")
            label = default_label
        show = bool(meta.get("show"))
        required = bool(meta.get("required")) and show
        if name in ALWAYS_REQUIRED:
            show = required = True
        fields[name] = {"label": label, "show": show, "required": required}
    if not any(fields[c]["show"] and fields[c]["required"] for c in CONTACT_FIELDS):
        problems.append("At least one contact method (email or a phone) must be shown "
                        "and required")

    questions = [_line(q) for q in (data.get("questions") or []) if _line(q)]
    if len(questions) > MAX_QUESTIONS:
        problems.append(f"At most {MAX_QUESTIONS} questions")
    if any(len(q) > MAX_QUESTION for q in questions):
        problems.append(f"Questions are limited to {MAX_QUESTION} characters")

    consent = str(data.get("consent_text") or "").replace("\r\n", "\n").strip()
    if len(consent) > MAX_CONSENT:
        problems.append("Consent text is too long")

    if problems:
        raise ValueError("; ".join(problems))
    return {"fields": fields, "questions": questions[:MAX_QUESTIONS],
            "consent_text": consent}


def save_config(db, cfg):
    db.set_setting(SETTING_KEY, json.dumps(cfg, sort_keys=True))


# ---------------------------------------------------------------------------
# bundle
# ---------------------------------------------------------------------------

def _hash(obj) -> str:
    blob = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def reencode_logo(raw: bytes):
    """Any image Pillow can read -> a fresh, size-capped PNG, or None.
    The practitioner's original file is never what the server serves."""
    try:
        from PIL import Image
        with Image.open(BytesIO(raw)) as img:
            img.load()
            img = img.convert("RGBA")
            img.thumbnail(LOGO_BOX)
            out = BytesIO()
            img.save(out, format="PNG", optimize=True)
    except Exception:
        return None
    data = out.getvalue()
    return data if len(data) <= MAX_LOGO_BYTES else None


def _logo_png(db, assets_path):
    name = db.get_setting("logo_filename", "")
    if not name:
        return None
    path = Path(assets_path) / name
    if not path.is_file() or path.parent.resolve() != Path(assets_path).resolve():
        return None
    try:
        if db.password:
            from core.encryption import decrypt_file_to_bytes
            raw = decrypt_file_to_bytes(str(path), db.password)
        else:
            raw = path.read_bytes()
    except Exception:
        return None
    return reencode_logo(raw)


def build_bundle(db, cfg, assets_path):
    practice = {k: db.get_setting(k, "") for k in (
        "practice_name", "therapist_name", "credentials", "registration_info",
        "address", "phone", "website", "email")}
    logo = _logo_png(db, assets_path)
    consent_version = _hash({"consent_text": cfg["consent_text"]}) if cfg["consent_text"] else ""
    bundle = {
        "practice": practice,
        "logo_png": base64.b64encode(logo).decode("ascii") if logo else None,
        "fields": [{"name": n, **cfg["fields"][n]} for n in FIELD_NAMES],
        "questions": list(cfg["questions"]),
        "consent_text": cfg["consent_text"],
        "consent_version": consent_version,
    }
    bundle["config_version"] = _hash(bundle)
    return bundle
