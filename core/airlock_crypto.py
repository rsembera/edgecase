"""AirLock submission crypto (EdgeCase side).

AirLock is the online intake & consent service (docs/Intake_Service_Plan.md).
The one rule: the server that receives submissions can never read them. The
client's browser encrypts each completed form to a public key EdgeCase
generated; the private key lives only in EdgeCase's encrypted database.

Scheme (ECIES-style, one ephemeral key per submission), chosen so the browser
side is WebCrypto alone and this side is `cryptography` alone:

    ephemeral P-256 keypair (browser)
    shared  = ECDH(ephemeral_private, recipient_public)   # 32-byte x-coordinate
    key     = HKDF-SHA256(ikm=shared, salt=epk_raw,
                          info=b"AirLock v1 " + key_id, length=32)
    ct      = AES-256-GCM(key, iv=12 random bytes, aad=build_aad(...))

Envelope (JSON, all binary fields base64url without padding):

    {"v": 1, "kid": key_id, "epk": raw uncompressed ephemeral point (65 B),
     "iv": 12 B, "ct": ciphertext || 16-byte tag}

WebCrypto equivalents: deriveBits({name:'ECDH'}, ..., 256) returns the same
x-coordinate as cryptography's ECDH exchange; HKDF and AES-GCM match
byte-for-byte. tests/test_airlock_crypto.py proves this against Node's
WebCrypto when node is installed.

Associated data binds a ciphertext to the invitation, the form, and the exact
form-config and consent versions the client saw, so a blob cannot be replayed
under another invitation or relabelled as another form.

encrypt_for_testing() is the Python mirror of what the browser does. It exists
so the import side can be tested end to end before the AirLock server exists;
EdgeCase itself never encrypts submissions.
"""
import base64
import hashlib
import json
import os
import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

ENVELOPE_VERSION = 1
AAD_PREFIX = "airlock/v1"
HKDF_INFO_PREFIX = b"AirLock v1 "

# A one-page form encrypts to a few KB. Anything far past that is not a form.
MAX_ENVELOPE_BYTES = 64 * 1024

TOKEN_BYTES = 32      # 256-bit link token
PIN_DIGITS = 6
FORMS = ("intake", "consent")


class AirLockDecryptError(Exception):
    """Any reason an envelope cannot be opened. Deliberately one type: the
    import screen reports "could not be decrypted" and never partially
    imports, whatever the cause."""


# ---------------------------------------------------------------------------
# encoding helpers
# ---------------------------------------------------------------------------

def b64u_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64u_decode(text: str) -> bytes:
    if not isinstance(text, str):
        raise ValueError("expected base64url text")
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode((text + pad).encode("ascii"))


# ---------------------------------------------------------------------------
# tokens and PINs
# ---------------------------------------------------------------------------

def new_token() -> str:
    """256-bit random invitation token, URL-safe."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def token_hash(token: str) -> str:
    """What the server stores and what the AAD carries. Plain SHA-256: with
    256 bits of entropy a slow hash buys nothing."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_pin() -> str:
    return f"{secrets.randbelow(10 ** PIN_DIGITS):0{PIN_DIGITS}d}"


# ---------------------------------------------------------------------------
# keypairs
# ---------------------------------------------------------------------------

def generate_keypair():
    """Returns (key_id, private_pem, public_b64u).

    public_b64u is the raw uncompressed point, which WebCrypto imports with
    importKey('raw', ..., {name:'ECDH', namedCurve:'P-256'}, ...)."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    return secrets.token_hex(8), private_pem, public_key_b64u(private_key.public_key())


def public_key_b64u(public_key) -> str:
    return b64u_encode(public_key.public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    ))


def public_from_private_pem(private_pem: str) -> str:
    return public_key_b64u(_load_private(private_pem).public_key())


def _load_private(private_pem: str):
    key = serialization.load_pem_private_key(private_pem.encode("ascii"), password=None)
    if not isinstance(key, ec.EllipticCurvePrivateKey) or key.curve.name != "secp256r1":
        raise ValueError("not a P-256 private key")
    return key


# ---------------------------------------------------------------------------
# associated data and key derivation
# ---------------------------------------------------------------------------

def build_aad(invitation_hash: str, form: str, config_version: str,
              consent_version: str) -> bytes:
    """Newline-joined, so both sides can build it without a JSON canonicaliser.
    Fields may not contain newlines, which keeps the join unambiguous."""
    fields = [invitation_hash, form, config_version, consent_version]
    for f in fields:
        if not isinstance(f, str) or "\n" in f or "\r" in f:
            raise ValueError("AAD fields must be single-line strings")
    return "\n".join([AAD_PREFIX] + fields).encode("utf-8")


def _derive_key(shared: bytes, epk_raw: bytes, key_id: str) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=epk_raw,
        info=HKDF_INFO_PREFIX + key_id.encode("utf-8"),
    ).derive(shared)


# ---------------------------------------------------------------------------
# decrypt (the only direction EdgeCase needs in production)
# ---------------------------------------------------------------------------

def decrypt_envelope(envelope, private_keys: dict, aad: bytes) -> bytes:
    """Open one submission.

    envelope: the JSON text (or already-parsed dict) received from AirLock.
    private_keys: {key_id: private_pem}; retired keys stay here until every
        invitation issued under them has closed.
    aad: build_aad(...) from EdgeCase's OWN record of the invitation, never
        from anything the server says about it.

    Raises AirLockDecryptError on every failure.
    """
    try:
        if isinstance(envelope, (str, bytes)):
            raw = envelope.encode("utf-8") if isinstance(envelope, str) else envelope
            if len(raw) > MAX_ENVELOPE_BYTES:
                raise AirLockDecryptError("envelope too large")
            envelope = json.loads(raw)
        if not isinstance(envelope, dict):
            raise AirLockDecryptError("envelope is not an object")
        if envelope.get("v") != ENVELOPE_VERSION:
            raise AirLockDecryptError("unsupported envelope version")

        kid = envelope.get("kid")
        if not isinstance(kid, str) or kid not in private_keys:
            raise AirLockDecryptError("unknown key id")

        epk_raw = b64u_decode(envelope.get("epk"))
        iv = b64u_decode(envelope.get("iv"))
        ct = b64u_decode(envelope.get("ct"))
        if len(epk_raw) != 65 or epk_raw[0] != 0x04:
            raise AirLockDecryptError("malformed ephemeral key")
        if len(iv) != 12:
            raise AirLockDecryptError("malformed iv")
        if len(ct) < 16 or len(ct) > MAX_ENVELOPE_BYTES:
            raise AirLockDecryptError("malformed ciphertext")

        # from_encoded_point rejects points not on the curve, which is what
        # stops invalid-curve attacks on the static key.
        epk = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), epk_raw)
        shared = _load_private(private_keys[kid]).exchange(ec.ECDH(), epk)
        key = _derive_key(shared, epk_raw, kid)
        return AESGCM(key).decrypt(iv, ct, aad)
    except AirLockDecryptError:
        raise
    except (InvalidTag, ValueError, TypeError, KeyError, UnicodeError) as exc:
        # ValueError covers json.JSONDecodeError, binascii.Error (bad
        # base64) and off-curve points.
        raise AirLockDecryptError(type(exc).__name__) from None


# ---------------------------------------------------------------------------
# test-side mirror of the browser
# ---------------------------------------------------------------------------

def encrypt_for_testing(plaintext: bytes, public_b64u: str, key_id: str,
                        aad: bytes) -> str:
    """What the AirLock page does in WebCrypto, in Python. Tests only."""
    recipient = ec.EllipticCurvePublicKey.from_encoded_point(
        ec.SECP256R1(), b64u_decode(public_b64u))
    ephemeral = ec.generate_private_key(ec.SECP256R1())
    epk_raw = ephemeral.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    shared = ephemeral.exchange(ec.ECDH(), recipient)
    iv = os.urandom(12)
    ct = AESGCM(_derive_key(shared, epk_raw, key_id)).encrypt(iv, plaintext, aad)
    return json.dumps({
        "v": ENVELOPE_VERSION,
        "kid": key_id,
        "epk": b64u_encode(epk_raw),
        "iv": b64u_encode(iv),
        "ct": b64u_encode(ct),
    })
