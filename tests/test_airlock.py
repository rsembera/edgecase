"""AirLock, EdgeCase side: submission crypto, keypair storage, invitations.

docs/Intake_Service_Plan.md. The property everything rests on is that a
submission can only be opened with EdgeCase's private key and only under the
invitation, form and versions it was encrypted for. The WebCrypto test proves
the browser will produce envelopes this side can open; it runs whenever node
is installed and is skipped otherwise.
"""
import json
import shutil
import subprocess
import time

import pytest

from core import airlock_crypto as ac

AAD = ac.build_aad("a" * 64, "intake", "cfg-1", "consent-1")
PAYLOAD = json.dumps({"first_name": "Ada", "last_name": "Lovelace"}).encode()


@pytest.fixture
def keypair():
    kid, pem, public = ac.generate_keypair()
    return kid, pem, public


# ---------------------------------------------------------------------------
# crypto
# ---------------------------------------------------------------------------

def test_round_trip(keypair):
    kid, pem, public = keypair
    env = ac.encrypt_for_testing(PAYLOAD, public, kid, AAD)
    assert ac.decrypt_envelope(env, {kid: pem}, AAD) == PAYLOAD


def test_envelope_carries_no_plaintext(keypair):
    kid, pem, public = keypair
    env = ac.encrypt_for_testing(PAYLOAD, public, kid, AAD)
    assert b"Lovelace" not in env.encode()
    assert set(json.loads(env)) == {"v", "kid", "epk", "iv", "ct"}


@pytest.mark.parametrize("field", [0, 1, 2, 3])
def test_aad_binds_every_field(keypair, field):
    """Replaying under another invitation, relabelling the form, or claiming
    other config/consent versions must all fail."""
    kid, pem, public = keypair
    env = ac.encrypt_for_testing(PAYLOAD, public, kid, AAD)
    parts = ["a" * 64, "intake", "cfg-1", "consent-1"]
    parts[field] = parts[field] + "x"
    with pytest.raises(ac.AirLockDecryptError):
        ac.decrypt_envelope(env, {kid: pem}, ac.build_aad(*parts))


def test_wrong_private_key_fails(keypair):
    kid, _pem, public = keypair
    _, other_pem, _ = ac.generate_keypair()
    env = ac.encrypt_for_testing(PAYLOAD, public, kid, AAD)
    with pytest.raises(ac.AirLockDecryptError):
        ac.decrypt_envelope(env, {kid: other_pem}, AAD)


def test_unknown_key_id_fails(keypair):
    kid, pem, public = keypair
    env = ac.encrypt_for_testing(PAYLOAD, public, kid, AAD)
    with pytest.raises(ac.AirLockDecryptError):
        ac.decrypt_envelope(env, {"someone-else": pem}, AAD)


def test_key_id_is_bound_into_the_key(keypair):
    """Swapping the kid label on an envelope, even to a key we hold, fails:
    the kid is in the HKDF info."""
    kid, pem, public = keypair
    env = json.loads(ac.encrypt_for_testing(PAYLOAD, public, kid, AAD))
    env["kid"] = "alias"
    with pytest.raises(ac.AirLockDecryptError):
        ac.decrypt_envelope(env, {kid: pem, "alias": pem}, AAD)


@pytest.mark.parametrize("field", ["iv", "ct", "epk"])
def test_tampering_fails(keypair, field):
    kid, pem, public = keypair
    env = json.loads(ac.encrypt_for_testing(PAYLOAD, public, kid, AAD))
    raw = bytearray(ac.b64u_decode(env[field]))
    raw[-1] ^= 0x01
    env[field] = ac.b64u_encode(bytes(raw))
    with pytest.raises(ac.AirLockDecryptError):
        ac.decrypt_envelope(env, {kid: pem}, AAD)


@pytest.mark.parametrize("bad", [
    "not json",
    "[]",
    json.dumps({"v": 2}),
    json.dumps({"v": 1, "kid": "k"}),
    json.dumps({"v": 1, "kid": "k", "epk": "!!!", "iv": "AAAA", "ct": "AAAA"}),
    json.dumps({"v": 1, "kid": "k", "epk": ac.b64u_encode(b"\x04" + b"\x00" * 64),
                "iv": ac.b64u_encode(b"\x00" * 12), "ct": ac.b64u_encode(b"\x00" * 32)}),
    json.dumps({"v": 1, "kid": "k", "epk": 5, "iv": None, "ct": []}),
    "x" * (ac.MAX_ENVELOPE_BYTES + 1),
    "[" * 40_000,                         # nested too deep: RecursionError inside json
])
def test_malformed_envelopes_raise_the_one_error(keypair, bad):
    """Every hostile shape surfaces as AirLockDecryptError, never as some
    other exception that would escape the import screen. The all-zero epk is
    an off-curve point (the invalid-curve case)."""
    _, pem, _ = keypair
    with pytest.raises(ac.AirLockDecryptError):
        ac.decrypt_envelope(bad, {"k": pem}, AAD)


@pytest.mark.parametrize("version", [True, 1.0, "1"])
def test_envelope_version_must_be_the_integer_one(keypair, version):
    """True == 1 and 1.0 == 1 in Python; neither is version 1."""
    kid, pem, public = keypair
    env = json.loads(ac.encrypt_for_testing(PAYLOAD, public, kid, AAD))
    env["v"] = version
    with pytest.raises(ac.AirLockDecryptError):
        ac.decrypt_envelope(json.dumps(env), {kid: pem}, AAD)


def test_aad_rejects_newlines():
    with pytest.raises(ValueError):
        ac.build_aad("h", "intake\nconsent", "c", "v")


def test_tokens_and_pins():
    tokens = {ac.new_token() for _ in range(200)}
    assert len(tokens) == 200
    assert all(len(ac.b64u_decode(t)) == ac.TOKEN_BYTES for t in tokens)
    assert ac.token_hash("abc") == ac.token_hash("abc") != ac.token_hash("abd")
    pins = [ac.new_pin() for _ in range(200)]
    assert all(len(p) == 6 and p.isdigit() for p in pins)


WEBCRYPTO_JS = r"""
const {subtle} = globalThis.crypto;
const b64u = b => Buffer.from(b).toString('base64url');
const unb64u = s => new Uint8Array(Buffer.from(s, 'base64url'));
let input = '';
process.stdin.on('data', d => input += d);
process.stdin.on('end', async () => {
  const {pub, kid, aad, plaintext} = JSON.parse(input);
  const recipient = await subtle.importKey('raw', unb64u(pub),
      {name: 'ECDH', namedCurve: 'P-256'}, false, []);
  const eph = await subtle.generateKey({name: 'ECDH', namedCurve: 'P-256'},
      true, ['deriveBits']);
  const epk = new Uint8Array(await subtle.exportKey('raw', eph.publicKey));
  const shared = await subtle.deriveBits({name: 'ECDH', public: recipient},
      eph.privateKey, 256);
  const ikm = await subtle.importKey('raw', shared, 'HKDF', false, ['deriveKey']);
  const info = new TextEncoder().encode('AirLock v1 ' + kid);
  const key = await subtle.deriveKey({name: 'HKDF', hash: 'SHA-256', salt: epk, info},
      ikm, {name: 'AES-GCM', length: 256}, false, ['encrypt']);
  const iv = globalThis.crypto.getRandomValues(new Uint8Array(12));
  const ct = await subtle.encrypt({name: 'AES-GCM', iv, additionalData: unb64u(aad)},
      key, new TextEncoder().encode(plaintext));
  process.stdout.write(JSON.stringify({v: 1, kid, epk: b64u(epk), iv: b64u(iv),
      ct: b64u(new Uint8Array(ct))}));
});
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_webcrypto_envelope_opens_here(keypair, tmp_path):
    """The browser half, written the way the AirLock page will write it, in a
    real WebCrypto implementation. If this passes, the two sides agree on
    ECDH output, HKDF parameters, AAD bytes and envelope encoding."""
    kid, pem, public = keypair
    script = tmp_path / "encrypt.js"
    script.write_text(WEBCRYPTO_JS)
    text = "Ada Lovelace — intake ✓"
    out = subprocess.run(
        ["node", str(script)],
        input=json.dumps({"pub": public, "kid": kid,
                          "aad": ac.b64u_encode(AAD), "plaintext": text}),
        capture_output=True, text=True, timeout=30, check=True)
    assert ac.decrypt_envelope(out.stdout, {kid: pem}, AAD).decode() == text


# ---------------------------------------------------------------------------
# keypair storage
# ---------------------------------------------------------------------------

def test_keypair_created_once_and_stable(app_db):
    kid = app_db.airlock_ensure_keypair()
    assert app_db.airlock_ensure_keypair() == kid
    kid2, public = app_db.airlock_public_key()
    assert kid2 == kid
    assert ac.public_from_private_pem(app_db.airlock_private_keys()[kid]) == public


def test_rotation_keeps_old_key_for_open_invitations(app_db):
    old = app_db.create_intake_invitation("Old Key")
    old_kid = old["key_id"]
    _, old_public = app_db.airlock_public_key()
    env = ac.encrypt_for_testing(PAYLOAD, old_public, old_kid, AAD)

    new_kid = app_db.airlock_rotate_keypair()
    assert new_kid != old_kid
    assert app_db.airlock_public_key()[0] == new_kid

    # An open invitation still references the old key: it must survive
    # pruning and still decrypt.
    assert app_db.airlock_prune_retired_keys() == []
    assert ac.decrypt_envelope(env, app_db.airlock_private_keys(), AAD) == PAYLOAD

    # Once the invitation closes, the old key goes.
    app_db.revoke_intake_invitation(old["id"])
    assert app_db.airlock_prune_retired_keys() == [old_kid]
    assert set(app_db.airlock_private_keys()) == {new_kid}


def test_expired_invitation_does_not_pin_a_retired_key(app_db):
    t0 = 1_800_000_000
    inv = app_db.create_intake_invitation("Lapsed", ttl_days=1, now=t0)
    app_db.airlock_rotate_keypair()
    assert app_db.airlock_prune_retired_keys(now=t0 + 2 * 86400) == [inv["key_id"]]


def test_a_submission_waiting_for_review_keeps_its_retired_key(app_db):
    """'complete' means the forms are in and waiting to be reviewed. They can
    only be opened with the key they were encrypted to, so that key must
    survive rotation and pruning until the submission is imported or
    discarded, however long that takes."""
    t0 = 1_800_000_000
    inv = app_db.create_intake_invitation("Waiting", required_forms=("intake",),
                                          ttl_days=1, now=t0)
    app_db.record_intake_form_received(inv["id"], "intake")
    assert app_db.get_intake_invitation(inv["id"])["status"] == "complete"
    app_db.airlock_rotate_keypair()
    assert app_db.airlock_prune_retired_keys(now=t0 + 60 * 86400) == []
    assert inv["key_id"] in app_db.airlock_private_keys()
    app_db.revoke_intake_invitation(inv["id"])              # discarded on review
    assert app_db.airlock_prune_retired_keys(now=t0 + 60 * 86400) == [inv["key_id"]]


# ---------------------------------------------------------------------------
# invitations
# ---------------------------------------------------------------------------

def test_create_invitation(app_db):
    t0 = 1_800_000_000
    inv = app_db.create_intake_invitation("  Ada Lovelace ", email=" ada@example.com ",
                                          now=t0)
    assert inv["display_name"] == "Ada Lovelace"
    assert inv["email"] == "ada@example.com"
    assert inv["required_forms"] == ["intake", "consent"]
    assert inv["forms_done"] == []
    assert inv["status"] == "issued"
    assert inv["is_minor"] is False
    assert inv["client_id"] is None
    assert inv["expires_at"] == t0 + 14 * 86400
    assert inv["token_hash"] == ac.token_hash(inv["token"])
    assert len(inv["pin"]) == 6
    assert app_db.get_intake_invitation_by_hash(inv["token_hash"])["id"] == inv["id"]


@pytest.mark.parametrize("kwargs", [
    {"display_name": ""},
    {"display_name": "   "},
    {"display_name": "x" * 201},
    {"display_name": "A", "required_forms": ()},
    {"display_name": "A", "required_forms": ("intake", "billing")},
    {"display_name": "A", "ttl_days": 0},
    {"display_name": "A", "ttl_days": 91},
    {"display_name": "A", "ttl_days": "soon"},
    {"display_name": "A", "email": "e" * 255},
])
def test_create_invitation_validates(app_db, kwargs):
    with pytest.raises(ValueError):
        app_db.create_intake_invitation(**kwargs)


def test_intake_only_and_minor(app_db):
    inv = app_db.create_intake_invitation("Kid", required_forms=("intake",),
                                          is_minor=True)
    assert inv["required_forms"] == ["intake"]
    assert inv["is_minor"] is True
    with pytest.raises(ValueError):
        app_db.record_intake_form_received(inv["id"], "consent")
    assert app_db.record_intake_form_received(inv["id"], "intake")["status"] == "complete"


def test_consent_only_is_refused(app_db):
    """New clients only: without the intake there is no name to create the
    client from."""
    with pytest.raises(ValueError):
        app_db.create_intake_invitation("A", required_forms=("consent",))


def test_forms_progress_to_complete(app_db):
    inv = app_db.create_intake_invitation("Ada")
    inv = app_db.record_intake_form_received(inv["id"], "consent")
    assert (inv["status"], inv["forms_done"]) == ("partial", ["consent"])
    inv = app_db.record_intake_form_received(inv["id"], "consent")  # idempotent
    assert (inv["status"], inv["forms_done"]) == ("partial", ["consent"])
    inv = app_db.record_intake_form_received(inv["id"], "intake")
    assert (inv["status"], inv["forms_done"]) == ("complete", ["intake", "consent"])


def test_expiry_is_computed_not_swept(app_db):
    t0 = 1_800_000_000
    inv = app_db.create_intake_invitation("Ada", ttl_days=14, now=t0)
    assert app_db.invitation_effective_status(inv, now=t0 + 14 * 86400 - 1) == "issued"
    assert app_db.invitation_effective_status(inv, now=t0 + 14 * 86400) == "expired"
    assert app_db.list_intake_invitations(now=t0 + 15 * 86400) == []
    assert len(app_db.list_intake_invitations(include_closed=True)) == 1


def test_revoke(app_db):
    inv = app_db.create_intake_invitation("Ada")
    assert app_db.revoke_intake_invitation(inv["id"]) is True
    inv = app_db.get_intake_invitation(inv["id"])
    assert inv["status"] == "revoked" and inv["revoked_at"]
    assert app_db.revoke_intake_invitation(inv["id"]) is False
    assert app_db.list_intake_invitations() == []


def test_imported_invitation_cannot_be_revoked(app_db):
    cid = app_db.add_client({"file_number": "AIR-1", "first_name": "Ada",
                             "last_name": "Lovelace", "type_id": 1})
    inv = app_db.create_intake_invitation("Ada")
    app_db.mark_intake_imported(inv["id"], cid)
    assert app_db.revoke_intake_invitation(inv["id"]) is False
    inv = app_db.get_intake_invitation(inv["id"])
    assert (inv["status"], inv["client_id"]) == ("imported", cid)


def test_tokens_are_unique_across_invitations(app_db):
    hashes = {app_db.create_intake_invitation(f"P{i}")["token_hash"] for i in range(20)}
    assert len(hashes) == 20


def test_table_is_additive_on_an_existing_database(app_db):
    """Reopening an existing database must not fail or duplicate anything:
    the CREATE is IF NOT EXISTS, like every other additive table."""
    from core.database import Database
    inv = app_db.create_intake_invitation("Ada")
    path = app_db.db_path
    app_db.close()
    reopened = Database(str(path))
    try:
        assert reopened.get_intake_invitation(inv["id"])["token"] == inv["token"]
    finally:
        reopened.close()


def test_now_defaults_to_the_clock(app_db):
    before = int(time.time())
    inv = app_db.create_intake_invitation("Ada")
    assert before <= inv["issued_at"] <= int(time.time())
