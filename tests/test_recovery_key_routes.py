"""Recovery-key screens: display, typed acknowledgement, banner, regeneration.

These exercise the routing and acknowledgement logic against the real Flask
app. The on-disk .rk_pending helpers are patched out — whether the flag file
lands correctly is already covered by test_migrate_v3; what matters here is
that the screens read and clear it at the right moments, and that a mistyped
confirmation does not destroy the only copy of the key.
"""
import pytest

from core import encryption_v3 as v3
from web.blueprints import auth as auth_bp


@pytest.fixture
def issued_key(monkeypatch):
    """A recovery key parked in the handoff store, as the migration would."""
    cleared = {"count": 0}
    monkeypatch.setattr("core.migrate_crypto.recovery_key_pending", lambda: True)
    monkeypatch.setattr("core.migrate_crypto.clear_recovery_key_pending",
                        lambda: cleared.__setitem__("count", cleared["count"] + 1))
    key = v3.generate_recovery_key()
    token = auth_bp._store_recovery_handoff(key)
    yield key, token, cleared
    auth_bp._recovery_key_handoff.clear()


def test_display_shows_the_key(client, issued_key):
    key, token, _ = issued_key
    resp = client.get(f"/recovery-key?token={token}", headers={"Host": "localhost"})
    assert resp.status_code == 200
    assert key.encode() in resp.data


@pytest.mark.parametrize("mangle", [
    lambda s: s,
    str.lower,
    lambda s: s.replace("-", ""),
    lambda s: s.replace("-", " "),
    lambda s: f"  {s}  ",
])
def test_acknowledgement_accepts_realistic_typing(client, issued_key, mangle):
    """The user is transcribing from paper; punish only genuine mismatches."""
    key, token, cleared = issued_key
    resp = client.post("/recovery-key", headers={"Host": "localhost"},
                       data={"token": token, "confirm_key": mangle(key)})
    assert resp.status_code == 302
    assert cleared["count"] == 1


def test_wrong_confirmation_keeps_the_key_on_screen(client, issued_key):
    """A mistype must not consume the handoff — the key is unrecoverable once
    it leaves the screen, so the cost of being strict here is total."""
    key, token, cleared = issued_key
    other = v3.generate_recovery_key()

    resp = client.post("/recovery-key", headers={"Host": "localhost"},
                       data={"token": token, "confirm_key": other})

    assert resp.status_code == 200
    assert key.encode() in resp.data, "key was dropped after a mistype"
    assert cleared["count"] == 0
    assert auth_bp._peek_recovery_handoff(token) == key


def test_malformed_confirmation_is_not_a_crash(client, issued_key):
    key, token, cleared = issued_key
    resp = client.post("/recovery-key", headers={"Host": "localhost"},
                       data={"token": token, "confirm_key": "nonsense!!"})
    assert resp.status_code == 200
    assert cleared["count"] == 0


def test_acknowledgement_consumes_the_handoff(client, issued_key):
    key, token, _ = issued_key
    client.post("/recovery-key", headers={"Host": "localhost"},
                data={"token": token, "confirm_key": key})
    assert auth_bp._peek_recovery_handoff(token) is None


def test_stale_token_explains_rather_than_errors(client, monkeypatch):
    monkeypatch.setattr("core.migrate_crypto.recovery_key_pending", lambda: True)
    resp = client.get("/recovery-key?token=nope", headers={"Host": "localhost"})
    assert resp.status_code == 200
    assert b"Settings" in resp.data


def test_expired_handoff_is_treated_as_stale(client, issued_key, monkeypatch):
    """Thirty minutes is generous, but the key must not linger indefinitely."""
    _key, token, _ = issued_key
    entry = auth_bp._recovery_key_handoff[token]
    entry["created"] -= auth_bp._RECOVERY_TTL_SECONDS + 1
    assert auth_bp._peek_recovery_handoff(token) is None


# --- The persistent banner ---

def test_banner_shows_while_a_key_is_unrecorded(client, monkeypatch):
    monkeypatch.setattr("core.migrate_crypto.recovery_key_pending", lambda: True)
    resp = client.get("/settings", headers={"Host": "localhost"})
    assert b"No recovery key recorded" in resp.data


def test_banner_absent_once_acknowledged(client, monkeypatch):
    monkeypatch.setattr("core.migrate_crypto.recovery_key_pending", lambda: False)
    resp = client.get("/settings", headers={"Host": "localhost"})
    assert b"No recovery key recorded" not in resp.data


def test_banner_failure_does_not_break_the_page(client, monkeypatch):
    """A banner that cannot be computed must fail closed, not 500 the app."""
    def boom():
        raise RuntimeError("disk gone")
    monkeypatch.setattr("core.migrate_crypto.recovery_key_pending", boom)
    resp = client.get("/settings", headers={"Host": "localhost"})
    assert resp.status_code == 200
    assert b"No recovery key recorded" not in resp.data


# --- Regeneration ---

def test_regenerate_requires_the_password(client, monkeypatch):
    monkeypatch.setattr("core.migrate_crypto.install_crypto_version", lambda *a, **k: 3)
    called = {"n": 0}
    monkeypatch.setattr("core.migrate_crypto.regenerate_recovery_key",
                        lambda *a, **k: called.__setitem__("n", called["n"] + 1))

    resp = client.post("/recovery-key/regenerate", headers={"Host": "localhost"},
                       data={"password": "definitely-wrong"})

    assert resp.status_code == 200
    assert b"incorrect" in resp.data.lower()
    assert called["n"] == 0, "issued a new credential without the password"


def test_regenerate_form_renders(client, monkeypatch):
    monkeypatch.setattr("core.migrate_crypto.install_crypto_version", lambda *a, **k: 3)
    resp = client.get("/recovery-key/regenerate", headers={"Host": "localhost"})
    assert resp.status_code == 200
    assert b"Issue a new recovery key" in resp.data


def test_regenerate_refused_before_v3(client, monkeypatch):
    monkeypatch.setattr("core.migrate_crypto.install_crypto_version", lambda *a, **k: 2)
    resp = client.get("/recovery-key/regenerate", headers={"Host": "localhost"})
    assert resp.status_code == 200
    assert b"Issue a new recovery key" not in resp.data
