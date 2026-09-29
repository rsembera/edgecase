"""AirLock form configuration: the consent text, and the bundle pushed to
the server.

docs/Intake_Service_Plan.md, "Customization". The intake form is not
configurable: it is the client-facing part of the Client Profile, fixed on
both sides (core/airlock_import.INTAKE_FIELDS here, airlock/validation.FIELDS
on the server). What the practitioner sets is the consent text. Branding is
the Practice Information EdgeCase already holds for statements.

Stored in settings as `airlock_form_config` (JSON; earlier versions also held
field and question settings, which are now ignored). The bundle built from it
carries two versions, both short content hashes:
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

MAX_CONSENT = 50_000
MAX_LOGO_BYTES = 300 * 1024
LOGO_BOX = (600, 300)

SETTING_KEY = "airlock_form_config"


def default_config():
    return {"consent_text": ""}


def load_config(db):
    cfg = default_config()
    raw = db.get_setting(SETTING_KEY, "")
    if not raw:
        return cfg
    try:
        stored = json.loads(raw)
    except ValueError:
        return cfg
    if isinstance(stored, dict) and isinstance(stored.get("consent_text"), str):
        cfg["consent_text"] = stored["consent_text"]
    return cfg


def validate_config(data):
    """Form input -> clean config. Raises ValueError on a problem."""
    consent = str(data.get("consent_text") or "").replace("\r\n", "\n").strip()
    if len(consent) > MAX_CONSENT:
        raise ValueError("Consent text is too long")
    return {"consent_text": consent}


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
        "consent_text": cfg["consent_text"],
        "consent_version": consent_version,
    }
    bundle["config_version"] = _hash(bundle)
    return bundle
