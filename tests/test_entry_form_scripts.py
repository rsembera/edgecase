"""Entry-form scripts must load once, and after shared_utils.js.

Regression for the absence/item forms whose {% block extra_js %} sat inside
{% block content %}. Jinja rendered the scripts twice: the mid-page copy ran
before shared_utils.js (autoResizeTextarea undefined, script aborted before
the picker init), and the bottom copy re-declared top-level consts and died
with a SyntaxError. Net effect: date/time pickers rendered as empty divs.
"""

import pathlib
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


# --- Template-level sweep: covers every page, not just the entry forms ---

TEMPLATES = pathlib.Path(__file__).resolve().parent.parent / "web" / "templates"
BLOCK_RE = re.compile(r"{%-?\s*(block\s+(\w+)|endblock)\b|<script[^>]*src=")


def _template_layout(path):
    """Return (nested_blocks, scripts_in_content) for one template."""
    stack, nested, in_content = [], [], 0
    for m in BLOCK_RE.finditer(path.read_text()):
        if m.group(1) == "endblock":
            if stack:
                stack.pop()
        elif m.group(1):
            if stack:
                nested.append(f"{m.group(2)} inside {'>'.join(stack)}")
            stack.append(m.group(2))
        elif "content" in stack:
            in_content += 1
    return nested, in_content


def test_no_template_nests_blocks():
    """A block inside another block renders twice; Jinja does not warn."""
    bad = {str(p.relative_to(TEMPLATES)): n
           for p in TEMPLATES.rglob("*.html")
           for n in [_template_layout(p)[0]] if n}
    assert not bad, bad


def test_no_template_loads_scripts_inside_content():
    """content renders before base.html loads shared_utils.js; page scripts
    belong in extra_js, which renders after it."""
    bad = {str(p.relative_to(TEMPLATES)): n
           for p in TEMPLATES.rglob("*.html")
           for n in [_template_layout(p)[1]] if n}
    assert not bad, bad
