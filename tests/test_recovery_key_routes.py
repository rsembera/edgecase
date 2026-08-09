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


# --- The recovery door: routes ---

@pytest.fixture
def recoverable(monkeypatch):
    """An install that reports v3 with a known recovery key."""
    key = v3.generate_recovery_key()
    monkeypatch.setattr("core.migrate_crypto.has_recovery_key", lambda *a, **k: True)
    monkeypatch.setattr("core.migrate_crypto.install_crypto_version", lambda *a, **k: 3)
    monkeypatch.setattr("core.encryption_v3.read_keyinfo", lambda *a, **k: b"blob")

    def fake_unwrap(_blob, candidate):
        if v3.parse_recovery_key(candidate) != v3.parse_recovery_key(key):
            raise ValueError("nope")
        return b"\x00" * 32

    monkeypatch.setattr("core.encryption_v3.unwrap_with_recovery_key", fake_unwrap)
    auth_bp._login_attempts.clear()
    yield key
    auth_bp._recovery_reset_handoff.clear()
    auth_bp._login_attempts.clear()


def test_recover_form_renders(client, recoverable):
    resp = client.get("/recover", headers={"Host": "localhost"})
    assert resp.status_code == 200
    assert b"recovery key" in resp.data.lower()


def test_recover_accepts_the_right_key(client, recoverable):
    resp = client.post("/recover", headers={"Host": "localhost"},
                       data={"recovery_key": recoverable})
    assert resp.status_code == 302
    assert "/recover/reset" in resp.headers["Location"]


def test_recover_rejects_a_wrong_key(client, recoverable):
    resp = client.post("/recover", headers={"Host": "localhost"},
                       data={"recovery_key": v3.generate_recovery_key()})
    assert resp.status_code == 200
    assert b"does not open" in resp.data


def test_malformed_key_does_not_spend_an_attempt(client, recoverable):
    """A typo is not a guess. Burning the lockout budget on mistyping a
    32-character code would make the door useless exactly when it is needed."""
    client.post("/recover", headers={"Host": "localhost"},
                data={"recovery_key": "oops"})
    assert not auth_bp._login_attempts


def test_wrong_key_does_spend_an_attempt(client, recoverable):
    client.post("/recover", headers={"Host": "localhost"},
                data={"recovery_key": v3.generate_recovery_key()})
    assert auth_bp._login_attempts


def test_recover_unavailable_before_v3(client, monkeypatch):
    monkeypatch.setattr("core.migrate_crypto.has_recovery_key", lambda *a, **k: False)
    resp = client.get("/recover", headers={"Host": "localhost"})
    assert b"no recovery key" in resp.data.lower()


def test_reset_requires_a_verified_token(client, recoverable):
    """No token, no reset — the key check cannot be skipped."""
    resp = client.get("/recover/reset", headers={"Host": "localhost"})
    assert resp.status_code == 302
    assert "/recover" in resp.headers["Location"]


def test_reset_rejects_mismatched_passwords(client, recoverable, monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr("core.migrate_crypto.reset_password_with_recovery_key",
                        lambda *a, **k: called.__setitem__("n", called["n"] + 1))
    token = auth_bp._store_recovery_reset_handoff(recoverable)
    resp = client.post("/recover/reset", headers={"Host": "localhost"},
                       data={"token": token, "new_password": "abcdefgh",
                             "confirm_password": "different"})
    assert b"don&#39;t match" in resp.data or b"don't match" in resp.data
    assert called["n"] == 0


def test_reset_rejects_a_short_password(client, recoverable, monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr("core.migrate_crypto.reset_password_with_recovery_key",
                        lambda *a, **k: called.__setitem__("n", called["n"] + 1))
    token = auth_bp._store_recovery_reset_handoff(recoverable)
    resp = client.post("/recover/reset", headers={"Host": "localhost"},
                       data={"token": token, "new_password": "short",
                             "confirm_password": "short"})
    assert b"8 characters" in resp.data
    assert called["n"] == 0


def test_reset_completes_and_does_not_auto_login(client, recoverable, monkeypatch):
    """The user has typed the new password exactly twice; using it once more
    is the cheapest confirmation it is what they think it is."""
    monkeypatch.setattr("core.migrate_crypto.reset_password_with_recovery_key",
                        lambda *a, **k: None)
    token = auth_bp._store_recovery_reset_handoff(recoverable)
    resp = client.post("/recover/reset", headers={"Host": "localhost"},
                       data={"token": token, "new_password": "abcdefgh",
                             "confirm_password": "abcdefgh"})
    assert resp.status_code == 200
    assert b"Sign in" in resp.data
    assert auth_bp._peek_recovery_reset_handoff(token) is None


# --- Regression: the SSE stream and application context ---

def test_migrate_stream_resolves_urls_outside_the_generator():
    """Regression for a real failure on the first live run.

    Flask pops the application context before an SSE generator is consumed, so
    url_for() called INSIDE the generator raises 'Working outside of
    application context' — and it did so AFTER the migration had already
    committed, producing a scary error screen over a perfectly good upgrade.

    Both URLs must therefore be resolved in the request scope, before the
    generator body. Asserting on source is crude, but the alternative is
    driving a full SSE consume against a real v1/v2 install, and the property
    worth pinning is exactly 'no url_for below def generate'.
    """
    import inspect

    from web.blueprints import auth as auth_mod

    src = inspect.getsource(auth_mod.migrate_stream)
    head, _, body = src.partition("def generate():")
    assert body, "migrate_stream no longer has a generate() body"
    assert "url_for" in head, "URLs should be resolved in the request scope"
    assert "url_for" not in body, (
        "url_for() inside the SSE generator will raise 'Working outside of "
        "application context' after the migration has already committed")


def test_stream_failure_after_commit_does_not_claim_data_is_unchanged():
    """The original handler asserted the data was untouched on ANY exception.
    Everything after the commit point can fail with the migration already
    committed, and telling the user nothing happened is the wrong mental
    model — worse than the crash itself."""
    import inspect

    from web.blueprints import auth as auth_mod

    src = inspect.getsource(auth_mod.migrate_stream)
    _, _, handler = src.partition("except Exception as e:")
    assert "install_crypto_version" in handler, (
        "the error path must ask the disk whether the migration committed "
        "rather than assuming it did not")
