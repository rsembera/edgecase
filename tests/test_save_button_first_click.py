"""The dirty-state Save button must survive the blur its own click causes.

Bug (Oct 2026): edit a Communication entry's text, click "Save Edits" —
nothing happens; a second click saves. Pressing the mouse on the button
blurs the textarea, the textarea fires `change` (it was edited), and the
dirty-tracking handler re-wrote the button's label via `textContent` —
same string, but a brand-new text node. WebKit (the desktop shell's
WKWebView, and Safari) only fires `click` when mousedown and mouseup land
on the same node, and the node under the pointer at mousedown was the old
label text node, now detached. So the press-and-release produced
mousedown + mouseup and no click. Clicking the button's padding instead
of its label worked, which is why it looked intermittent; the second
click worked because there was no pending `change` left to fire.

Same pattern, same bug, in two places: form-guard.js (communication,
absence, item, upload, profile) and session.js's bespoke copy (locked
session "Save Changes").

Chromium fires the click either way, so the pin here is the invariant
WebKit actually depends on: the label text node present at mousedown is
still the button's connected child afterwards. The pages are the real
server-rendered forms with their real scripts, served to the browser
through the Flask test client (no live server).
"""
import time
from datetime import datetime

import pytest

ORIGIN = "http://edgecase.test"


@pytest.fixture
def browser():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except sync_api.Error as e:
            pytest.skip(f"Chromium not available: {e}")
        yield b
        b.close()


def _open(browser, client, path):
    """Load `path` in a page whose every request is answered by the Flask
    test client. POSTs are recorded and answered with a stub, so a
    successful Save is observable without following the redirect."""
    # A second, context-free test client for the browser's requests:
    # Playwright runs route handlers in another greenlet, and the
    # fixture's `with`-block client preserves a request context that
    # cannot be popped from there (ContextVar LookupError).
    served = client.application.test_client()
    with served.session_transaction() as sess:
        sess["authenticated"] = True
        sess["login_time"] = time.time()
        sess["last_activity"] = time.time()

    page = browser.new_page()
    posts = []

    def handle(route):
        req = route.request
        if not req.url.startswith(ORIGIN):
            route.abort()
            return
        rel = req.url[len(ORIGIN):] or "/"
        if req.method == "POST":
            posts.append(rel)
            route.fulfill(status=200, content_type="text/html", body="saved")
            return
        resp = served.get(rel)
        route.fulfill(status=resp.status_code, headers=dict(resp.headers),
                      body=resp.data)

    page.route("**/*", handle)
    page.goto(ORIGIN + path)
    page.wait_for_load_state("networkidle")
    return page, posts


def _press_save_after_editing(page, button_selector):
    """Edit the content textarea, then press (mousedown only) on the Save
    button's label. Returns whether the label text node that was under
    the pointer is still the button's connected child."""
    btn = page.locator(button_selector)
    assert btn.is_disabled() and btn.inner_text() == "No Changes"

    page.click("#content")
    page.keyboard.type(" edited")
    assert btn.is_enabled(), "Save button did not activate on edit"

    page.evaluate(
        "sel => { window.__label = document.querySelector(sel).firstChild; }",
        button_selector)
    # The button sits below the fold: without this the press lands on
    # empty viewport (still blurring the field, but not on the button).
    btn.scroll_into_view_if_needed()
    box = btn.bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()  # blurs the textarea -> its `change` fires here
    return page.evaluate(
        "sel => window.__label.isConnected"
        " && document.querySelector(sel).firstChild === window.__label",
        button_selector)


def _client_row(db):
    return db.add_client({"file_number": "SB-001", "first_name": "Save",
                          "middle_name": "", "last_name": "Button", "type_id": 1})


def test_communication_save_label_node_survives_blur(browser, client, app_db):
    cid = _client_row(app_db)
    assert client.post(f"/client/{cid}/communication", data={
        "description": "Call", "recipient": "to_client", "comm_type": "phone",
        "date": "2026-06-19", "content": "x"}).status_code == 302
    eid = app_db.get_client_entries(cid, "communication")[0]["id"]

    page, posts = _open(browser, client, f"/client/{cid}/communication/{eid}")
    sel = "[data-dirty-save]"
    assert _press_save_after_editing(page, sel), (
        "form-guard.js replaced the Save button's label text node during the "
        "blur caused by pressing it — WebKit will not fire click")

    # Wait for the RESPONSE: the request event fires before the route
    # handler has recorded the POST.
    with page.expect_response(lambda r: r.request.method == "POST",
                              timeout=5000):
        page.mouse.up()
    assert posts == [f"/client/{cid}/communication/{eid}"], (
        f"one press-and-release must save exactly once; POSTs: {posts}")


def test_locked_session_save_label_node_survives_blur(browser, client, app_db):
    cid = _client_row(app_db)
    now = int(time.time())
    eid = app_db.add_entry({
        "client_id": cid, "class": "session", "description": "Session",
        "session_date": int(datetime(2026, 6, 10).timestamp()),
        "content": "notes", "base_fee": 100.0, "tax_rate": 0.0, "fee": 100.0,
        "created_at": now, "modified_at": now,
    })
    app_db.lock_entry(eid)

    page, _ = _open(browser, client, f"/client/{cid}/session/{eid}")
    assert _press_save_after_editing(page, "#save-changes-btn"), (
        "session.js replaced the Save button's label text node during the "
        "blur caused by pressing it — WebKit will not fire click")
