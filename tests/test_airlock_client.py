"""AirLockClient over real HTTP, against a throwaway local server.

The route tests use an in-memory stand-in; this covers the transport itself:
the bearer header, JSON bodies, and that every failure mode surfaces as
AirLockConnectionError with a message fit to show, never a raw exception.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from core.airlock_client import (AirLockClient, AirLockConnectionError,
                                 invitation_link, is_enabled, validate_base_url)


class Handler(BaseHTTPRequestHandler):
    routes = {}
    seen = []

    def _handle(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        Handler.seen.append((self.command, self.path,
                             self.headers.get("Authorization"), body))
        status, reply = Handler.routes.get((self.command, self.path), (404, b""))
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(reply)))
        self.end_headers()
        self.wfile.write(reply)

    do_GET = do_POST = do_PUT = do_DELETE = _handle

    def log_message(self, *a):
        pass


@pytest.fixture
def http():
    Handler.routes, Handler.seen = {}, []
    srv = HTTPServer(("127.0.0.1", 0), Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield srv, f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


SUB = {"id": "s1", "token_hash": "h" * 64, "form": "intake", "key_id": "k1",
       "config_version": "c1", "consent_version": "v1", "envelope": "{}",
       "received_at": 1790000000}


def test_bearer_and_json(http):
    _, url = http
    Handler.routes[("POST", "/admin/invitations")] = (201, b"{}")
    AirLockClient(url, "sekret").create_invitation({
        "token_hash": "h" * 64, "pin": "123456", "required_forms": ["intake"],
        "is_minor": False, "expires_at": 1, "key_id": "k1",
        "display_name": "Ada", "email": "ada@example.com", "token": "T"})
    method, path, auth, body = Handler.seen[-1]
    assert (method, path, auth) == ("POST", "/admin/invitations", "Bearer sekret")
    sent = json.loads(body)
    assert set(sent) == {"token_hash", "pin", "required_forms", "is_minor",
                         "expires_at", "key_id"}


@pytest.mark.parametrize("field, value", [
    ("form", "in\ntake"), ("form", "\ud800"), ("id", "../x"), ("key_id", "<b>"),
    ("token_hash", "h" * 200), ("config_version", "a b"), ("envelope", {"v": 1}),
    ("envelope", "x" * 70_000),
])
def test_submission_labels_from_the_server_must_be_plain(http, field, value):
    """ids, hashes, form names and versions are short plain tokens by
    construction. Anything else means the server is not behaving, and it is
    refused here rather than carried into the screens."""
    _, url = http
    Handler.routes[("GET", "/admin/submissions")] = (
        200, json.dumps({"submissions": [dict(SUB, **{field: value})]}).encode())
    with pytest.raises(AirLockConnectionError):
        AirLockClient(url, "k").list_submissions()


def test_list_submissions(http):
    _, url = http
    Handler.routes[("GET", "/admin/submissions")] = (
        200, json.dumps({"submissions": [SUB]}).encode())
    assert AirLockClient(url, "k").list_submissions() == [SUB]


@pytest.mark.parametrize("reply", [
    b"not json", b"[]", json.dumps({"submissions": "nope"}).encode(),
    json.dumps({"submissions": [{"id": "x"}]}).encode(),
    json.dumps({"submissions": [dict(SUB, received_at="soon")]}).encode(),
])
def test_malformed_replies(http, reply):
    _, url = http
    Handler.routes[("GET", "/admin/submissions")] = (200, reply)
    with pytest.raises(AirLockConnectionError):
        AirLockClient(url, "k").list_submissions()


@pytest.mark.parametrize("status, fragment", [(401, "refused the admin key"),
                                              (403, "refused the admin key"),
                                              (500, "error (500)")])
def test_http_errors(http, status, fragment):
    _, url = http
    Handler.routes[("PUT", "/admin/public-key")] = (status, b"")
    with pytest.raises(AirLockConnectionError, match=fragment.replace("(", r"\(").replace(")", r"\)")):
        AirLockClient(url, "k").put_public_key("k1", "pub")


def test_unreachable():
    with pytest.raises(AirLockConnectionError, match="Could not reach"):
        AirLockClient("http://127.0.0.1:9", "k", timeout=2).list_submissions()


def test_oversized_reply(http, monkeypatch):
    from core import airlock_client
    _, url = http
    monkeypatch.setattr(airlock_client, "MAX_RESPONSE_BYTES", 100)
    Handler.routes[("GET", "/admin/submissions")] = (200, b"x" * 500)
    with pytest.raises(AirLockConnectionError, match="too much"):
        AirLockClient(url, "k").list_submissions()


def test_path_components_are_quoted(http):
    _, url = http
    Handler.routes[("DELETE", "/admin/submissions/a%2F..%2Fb")] = (204, b"")
    AirLockClient(url, "k").delete_submission("a/../b")
    assert Handler.seen[-1][1] == "/admin/submissions/a%2F..%2Fb"


@pytest.mark.parametrize("bad", ["", "sentinel:8081", "ftp://x", "http://",
                                 "https://x/?a=1", "https://x/#f", "javascript:alert(1)"])
def test_url_validation(bad):
    with pytest.raises(ValueError):
        validate_base_url(bad, "Address")


def test_enabled_and_link(app_db):
    assert not is_enabled(app_db)
    assert invitation_link(app_db, "TOK") == ""
    app_db.set_setting("airlock_server_url", "http://s:1")
    assert not is_enabled(app_db)            # no key yet
    app_db.set_setting("airlock_admin_key", "k")
    assert is_enabled(app_db)
    app_db.set_setting("airlock_public_url", "https://forms.example.ca/")
    assert invitation_link(app_db, "TOK") == "https://forms.example.ca/i#TOK"
