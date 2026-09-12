"""Nothing but versioned static assets may be cached by the browser.

Pages and PDFs carry client data; a cached response also replays stale
headers. Static files are safe to cache because every URL carries ?v=.
"""


def test_dynamic_responses_are_no_store(client, app_db):
    cid = app_db.add_client({"file_number": "CC-001", "first_name": "C",
                             "middle_name": "", "last_name": "C", "type_id": 1})
    for url in ("/", f"/client/{cid}", "/statements/",
                f"/client/{cid}/session-report?start_year=2026&start_month=9&start_day=1"
                "&end_year=2026&end_month=9&end_day=30&include_sessions=on"):
        resp = client.get(url)
        assert resp.status_code in (200, 302), url
        assert "no-store" in resp.headers.get("Cache-Control", ""), url
        resp.close()


def test_static_assets_are_still_cacheable(client):
    resp = client.get("/static/js/shared_utils.js?v=1")
    assert resp.status_code == 200
    assert "no-store" not in resp.headers.get("Cache-Control", "")
    resp.close()
