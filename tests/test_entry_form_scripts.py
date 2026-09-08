"""Entry-form scripts must load once, and after shared_utils.js.

Regression for the absence/item forms whose {% block extra_js %} sat inside
{% block content %}. Jinja rendered the scripts twice: the mid-page copy ran
before shared_utils.js (autoResizeTextarea undefined, script aborted before
the picker init), and the bottom copy re-declared top-level consts and died
with a SyntaxError. Net effect: date/time pickers rendered as empty divs.
"""

import re

SCRIPT_RE = re.compile(r'<script src="/static/js/([^"?]+)')


def _make_client(db):
    return db.add_client({
        "file_number": "SC-001", "first_name": "Script", "middle_name": "",
        "last_name": "Order", "type_id": 1,
    })


def _scripts(html):
    return SCRIPT_RE.findall(html)


def _assert_scripts_ok(html, own_script):
    scripts = _scripts(html)
    assert scripts.count(own_script) == 1, (
        f"{own_script} loaded {scripts.count(own_script)} times: {scripts}")
    assert scripts.count("pickers.js") <= 1, f"pickers.js loaded twice: {scripts}"
    assert scripts.index("shared_utils.js") < scripts.index(own_script), (
        f"{own_script} loads before shared_utils.js: {scripts}")


def test_absence_form_scripts_load_once_after_shared_utils(client, app_db):
    cid = _make_client(app_db)
    html = client.get(f"/client/{cid}/absence").data.decode()
    _assert_scripts_ok(html, "absence.js")


def test_item_form_scripts_load_once_after_shared_utils(client, app_db):
    cid = _make_client(app_db)
    html = client.get(f"/client/{cid}/item").data.decode()
    _assert_scripts_ok(html, "item.js")


def test_session_form_scripts_load_once_after_shared_utils(client, app_db):
    cid = _make_client(app_db)
    html = client.get(f"/client/{cid}/session").data.decode()
    _assert_scripts_ok(html, "session.js")


def test_communication_form_scripts_load_once_after_shared_utils(client, app_db):
    cid = _make_client(app_db)
    html = client.get(f"/client/{cid}/communication").data.decode()
    _assert_scripts_ok(html, "communication.js")
