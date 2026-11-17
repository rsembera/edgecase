"""The saved stat-card order must be in place before the page first paints.

Bug (Nov 2026): returning to the main view, the six stat cards appeared in
their default order and then jumped to the order the user had dragged them
into. The order lives in localStorage and was applied by main_view.js on
DOMContentLoaded — after every end-of-body script had loaded, and on the
main view after an awaited fetch of the time format as well — so the
browser had already painted the default order.

The order is now applied by an inline script directly after the container,
which runs while the page is still being parsed. The pin: with every
external script withheld from the browser, the cards are still in the
saved order. The pages are the real server-rendered templates, served
through the Flask test client (no live server).
"""
import json
import time

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


def _card_order_without_external_scripts(browser, client, path, storage_key,
                                         container_id, saved):
    """Load `path` with `saved` stored as the card order and every .js file
    withheld; return the card ids in document order."""
    served = client.application.test_client()
    with served.session_transaction() as sess:
        sess["authenticated"] = True
        sess["login_time"] = time.time()
        sess["last_activity"] = time.time()

    page = browser.new_page()

    def handle(route):
        url = route.request.url
        if not url.startswith(ORIGIN) or url.split("?")[0].endswith(".js"):
            route.abort()
            return
        resp = served.get(url[len(ORIGIN):] or "/")
        route.fulfill(status=resp.status_code, headers=dict(resp.headers),
                      body=resp.data)

    page.route("**/*", handle)
    page.add_init_script(
        f"localStorage.setItem({json.dumps(storage_key)}, {json.dumps(saved)});")
    page.goto(ORIGIN + path, wait_until="domcontentloaded")
    order = page.evaluate(
        "id => Array.from(document.getElementById(id)"
        ".querySelectorAll('.stat-card[data-card-id]'))"
        ".map(c => c.dataset.cardId)", container_id)
    page.close()
    return order


@pytest.mark.parametrize("path,storage_key,container_id,default", [
    ("/", "mainViewCardOrder", "stats-container",
     ["active-clients", "sessions-month", "pending-invoices",
      "billable-month", "current-time", "navigation"]),
    ("/ledger", "ledgerCardOrder", "ledger-stats-container",
     ["ytd-income", "ytd-expenses", "ytd-net",
      "mtd-income", "mtd-expenses", "top-categories"]),
])
def test_saved_card_order_applied_while_parsing(browser, client, path,
                                                storage_key, container_id,
                                                default):
    wanted = list(reversed(default))
    got = _card_order_without_external_scripts(
        browser, client, path, storage_key, container_id, json.dumps(wanted))
    assert got == wanted, (
        "saved card order was not applied by the page itself — it will "
        f"flicker from the default order on load; got {got}")


@pytest.mark.parametrize("saved", ["not json", '{"a": 1}', '["no-such-card"]',
                                   '["navigation"]'])
def test_bad_or_partial_saved_order_keeps_every_card(browser, client, saved):
    got = _card_order_without_external_scripts(
        browser, client, "/", "mainViewCardOrder", "stats-container", saved)
    assert sorted(got) == sorted(
        ["active-clients", "sessions-month", "pending-invoices",
         "billable-month", "current-time", "navigation"])
