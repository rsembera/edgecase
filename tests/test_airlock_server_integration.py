"""EdgeCase against the real AirLock server, over real HTTP.

Runs only when the AirLock repository is checked out next to this one
(../edgecase-airlock); skipped otherwise, so the EdgeCase suite never depends
on it.

Nothing is stubbed. EdgeCase issues the invitation through its own screen,
which pushes the public key, the form bundle and the invitation to the admin
listener. This test then plays the client's browser against the public
listener (unlock with link and PIN, encrypt, submit), and EdgeCase checks,
reviews and imports through its own screens. It proves the two code bases
agree on the admin API, the bundle format and version hashes, the envelope
shape and the associated data.
"""
import base64
import html
import json
import re
import shutil
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path

import pytest
from reportlab.lib.styles import ParagraphStyle
from werkzeug.serving import make_server

from core import airlock_client, airlock_config
from core import airlock_import as ai
from core import airlock_crypto as ac
from tests import test_airlock_import as fx

AIRLOCK_REPO = Path(__file__).resolve().parents[1].parent / "edgecase-airlock"
pytestmark = pytest.mark.skipif(not (AIRLOCK_REPO / "airlock" / "admin.py").exists(),
                                reason="edgecase-airlock not checked out alongside")


@pytest.fixture
def airlock(tmp_path):
    sys.path.insert(0, str(AIRLOCK_REPO))
    try:
        from airlock.admin import create_admin_app
        from airlock.public import create_public_app
        from airlock.settings import Settings, generate_admin_key
        from airlock.store import Store
    finally:
        sys.path.remove(str(AIRLOCK_REPO))
    settings = Settings(data_dir=tmp_path / "airlock-data")
    key = generate_admin_key(settings)
    store = Store(settings.db_path)
    servers = [make_server("127.0.0.1", 0, create_public_app(settings, store), threaded=True),
               make_server("127.0.0.1", 0, create_admin_app(settings, store), threaded=True)]
    threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in servers]
    for t in threads:
        t.start()
    public_url, admin_url = (f"http://127.0.0.1:{s.server_port}" for s in servers)
    yield {"public": public_url, "admin": admin_url, "key": key, "store": store}
    for s in servers:
        s.shutdown()
        s.server_close()
    for t in threads:
        t.join(timeout=5)


def _post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _browser_submit(public_url, token, pin, form, payload):
    """What the AirLock page will do: unlock, then encrypt to the key the
    server hands out, with AAD built from the token and the versions shown."""
    status, info = _post(public_url + "/i/unlock", {"token": token, "pin": pin})
    assert status == 200, info
    cfg = info["config"]
    token_hash = ac.token_hash(token)
    aad = ac.build_aad(token_hash, form, cfg["config_version"], cfg["consent_version"])
    env = ac.encrypt_for_testing(json.dumps(payload).encode(), info["public_key"],
                                 info["key_id"], aad)
    return _post(public_url + "/i/submit", {
        "token": token, "pin": pin, "form": form, "key_id": info["key_id"],
        "config_version": cfg["config_version"], "consent_version": cfg["consent_version"],
        "envelope": env})


def test_edgecase_and_airlock_end_to_end(client, app_db, airlock):
    app_db.set_setting("airlock_server_url", airlock["admin"])
    app_db.set_setting("airlock_public_url", airlock["public"])
    app_db.set_setting("airlock_admin_key", airlock["key"])
    app_db.set_setting("file_number_format", "manual")
    app_db.set_setting("therapist_name", "Jordan Example")
    cfg = airlock_config.default_config()
    cfg["consent_text"] = "# Consent\n\nI agree to psychotherapy."
    airlock_config.save_config(app_db, cfg)

    # Settings -> Test connection: key and bundle accepted by the real server
    r = client.post("/api/airlock_test", json={})
    assert r.get_json()["success"], r.get_json()

    # Issue through EdgeCase's own screen
    cid = fx.a_client(app_db, file_number="E2E-001", email="ada@example.com")
    r = client.post(f"/airlock/invite/{cid}", data={"forms": "both", "ttl_days": "14"})
    assert r.status_code == 302, r.data
    inv = app_db.list_intake_invitations()[0]
    page = client.get(r.headers["Location"]).data.decode()
    link = re.search(r'id="al-link">([^<]+)<', page).group(1).strip()
    token = link.split("#", 1)[1]
    assert token == inv["token"]

    # The server holds no name, email, token or PIN
    with open(airlock["store"].path, "rb") as f:
        raw_db = f.read()
    for secret in (b"Ada", b"ada@example.com", token.encode(), inv["pin"].encode()):
        assert secret not in raw_db

    # The client's browser
    payload = fx.intake_payload(additional_info="Stress at work.")
    assert _browser_submit(airlock["public"], token, inv["pin"], "intake", payload)[0] == 201
    assert _browser_submit(airlock["public"], token, inv["pin"], "consent",
                           fx.consent_payload())[0] == 201
    # the server's copy is ciphertext
    subs = airlock["store"].submissions()
    assert len(subs) == 2 and all(b"Lovelace" not in s["envelope"].encode() for s in subs)

    # Back in EdgeCase: check, review, import
    r = client.post("/airlock/check")
    assert "checked=2" in r.headers["Location"]
    review = client.get(f"/airlock/review/{inv['id']}").data.decode()
    assert "Lovelace" in review and "Stress at work." in review
    r = client.post(f"/airlock/review/{inv['id']}/import")
    assert r.status_code == 302, r.data
    assert r.headers["Location"].endswith(f"/client/{cid}")
    assert app_db.get_client(cid)["file_number"] == "E2E-001"
    assert "Stress at work." in app_db.get_profile_entry(cid)["additional_info"]

    # Submissions removed from the server; the link is dead
    assert airlock["store"].submissions() == []
    status, body = _post(airlock["public"] + "/i/unlock", {"token": token, "pin": inv["pin"]})
    assert status == 410 and body["error"] == "closed"


def test_revoke_reaches_the_real_server(client, app_db, airlock):
    app_db.set_setting("airlock_server_url", airlock["admin"])
    app_db.set_setting("airlock_public_url", airlock["public"])
    app_db.set_setting("airlock_admin_key", airlock["key"])
    cfg = airlock_config.default_config()
    cfg["consent_text"] = "I agree."
    airlock_config.save_config(app_db, cfg)
    client.post(f"/airlock/invite/{fx.a_client(app_db)}",
                data={"forms": "both", "ttl_days": "14"})
    inv = app_db.list_intake_invitations()[0]
    r = client.post(f"/airlock/invitations/{inv['id']}/revoke")
    assert "msg=revoked" in r.headers["Location"]
    status, _ = _post(airlock["public"] + "/i/unlock", {"token": inv["token"], "pin": inv["pin"]})
    assert status == 410


def test_wrong_admin_key_is_reported(client, app_db, airlock):
    app_db.set_setting("airlock_server_url", airlock["admin"])
    app_db.set_setting("airlock_admin_key", "not-the-key")
    r = client.post("/api/airlock_test", json={})
    assert r.status_code == 502 and "refused the admin key" in r.get_json()["error"]


# ---------------------------------------------------------------------------
# The client pages (airlock/static): the real page code against this side
# ---------------------------------------------------------------------------

STATIC = AIRLOCK_REPO / "airlock" / "static"

PAGE_CRYPTO_JS = r"""
import { buildAad, encryptEnvelope, tokenHash } from './crypto.js';
import { consentBlocks } from './consent.js';
const a = JSON.parse(process.argv[2]);
const aad = buildAad(await tokenHash(a.token), a.form, a.cv, a.consentv);
console.log(JSON.stringify({
  hash: await tokenHash(a.token),
  aad: Buffer.from(aad).toString('base64'),
  envelope: await encryptEnvelope(a.plaintext, a.pub, a.kid, aad),
  blocks: consentBlocks(a.consent),
}));
"""


def _run_page_modules(tmp_path, **args):
    for name in ("crypto.js", "consent.js"):
        (tmp_path / name).write_text((STATIC / name).read_text())
    script = tmp_path / "page.mjs"
    script.write_text(PAGE_CRYPTO_JS)
    out = subprocess.run(["node", str(script), json.dumps(args)], capture_output=True,
                         text=True, timeout=30, check=True)
    return json.loads(out.stdout)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_page_crypto_module_is_opened_by_edgecase(app_db, tmp_path):
    """Not a copy of the browser code: the page's own crypto.js file, run in
    Node's WebCrypto. Token hash and AAD bytes must equal this side's, and
    the envelope must open with the private key."""
    kid = app_db.airlock_ensure_keypair()
    _, public = app_db.airlock_public_key()
    token = ac.new_token()
    consent = "# Consent\n\nFirst line\nsecond line\n\n- Fees apply\n* 24h notice\n## Privacy\nKept."
    text = json.dumps(fx.consent_payload(consent_text=consent), ensure_ascii=False)
    out = _run_page_modules(tmp_path, token=token, form="consent", cv="c0ffee",
                            consentv="beef", plaintext=text, pub=public, kid=kid,
                            consent=consent)
    assert out["hash"] == ac.token_hash(token)
    aad = ac.build_aad(ac.token_hash(token), "consent", "c0ffee", "beef")
    assert base64.b64decode(out["aad"]) == aad
    plain = ac.decrypt_envelope(out["envelope"], app_db.airlock_private_keys(), aad)
    assert plain.decode() == text
    # wrong form in the AAD: refused
    with pytest.raises(ac.AirLockDecryptError):
        ac.decrypt_envelope(out["envelope"], app_db.airlock_private_keys(),
                            ac.build_aad(ac.token_hash(token), "intake", "c0ffee", "beef"))

    # The client reads the consent in the same structure the signed PDF shows.
    from pdf.airlock_records import _markdown_flowables
    styles = {name: ParagraphStyle(name) for name in ("ALHeading", "ALBody", "ALBullet")}
    kinds = {"ALHeading": "heading", "ALBody": "para", "ALBullet": "bullet"}
    pdf_blocks = [{"kind": kinds[p.style.name], "text": html.unescape(p.text)}
                  for p in _markdown_flowables(consent, styles)]
    assert out["blocks"] == pdf_blocks


def test_page_validation_matches_import_rules():
    """The page refuses what import would refuse (a sent form cannot be sent
    again), so its rules must not drift from core/airlock_import."""
    from core import airlock_import as ai
    app = (STATIC / "app.js").read_text()

    def js_regex(name):
        m = re.search(rf"const {name} = /(.+)/(i?);\n", app)
        assert m, name
        return m.group(1), m.group(2)

    assert js_regex("EMAIL") == (ai._EMAIL.pattern, "")
    assert js_regex("PHONE") == (ai._PHONE.pattern, "i") and ai._PHONE.flags & re.I
    assert f"const MAX_TYPED_NAME = {ai.MAX_TYPED_NAME};" in app
    assert ("const CONTACT_FIELDS = ['email', 'phone', 'home_phone', 'work_phone'];" in app
            and set(ai.CONTACT_FIELDS) == {"email", "phone", "home_phone", "work_phone"})
    assert "const TEXTABLE = { cell: 'phone', home: 'home_phone', work: 'work_phone' };" in app
    assert ai.TEXTABLE == {"cell": "phone", "home": "home_phone", "work": "work_phone"}
    assert ai.CALLABLE == {"email": "email", "call_cell": "phone", "call_home": "home_phone",
                           "call_work": "work_phone"}
    assert re.search(r"const CALLABLE = \{ email: 'email', call_cell: 'phone', "
                     r"call_home: 'home_phone',\s+call_work: 'work_phone' \};", app)
    for key, (max_len, _kind) in ai.GUARDIAN_FIELDS.items():
        assert re.search(rf"\['{key}', '[^']+', '\w+', {max_len},", app), key


def test_server_form_is_the_import_field_list():
    """The server renders the form, EdgeCase imports it: same fields, same
    Profile order, same kinds and lengths, same choice values."""
    from core import airlock_import as ai
    sys.path.insert(0, str(AIRLOCK_REPO))
    try:
        from airlock import validation as v
    finally:
        sys.path.remove(str(AIRLOCK_REPO))
    kinds = {"text": "line", "textarea": "multiline", "tel": "phone", "email": "email",
             "date": "date", "choice": "choice"}
    assert [f[0] for f in v.FIELDS] == list(ai.INTAKE_FIELDS)
    for name, kind, max_len, _label, _section in v.FIELDS:
        assert (max_len, kinds[kind]) == ai.INTAKE_FIELDS[name][:2], name
    assert {n: {c for c, _ in opts} for n, opts in v.CHOICES.items()} == \
        {n: set(labels) for n, labels in ai.CHOICE_LABELS.items()}
    assert set(v.REQUIRED) == {"first_name", "last_name"}


# ---------------------------------------------------------------------------
# A real browser: Chromium fills in the forms; EdgeCase imports them
# ---------------------------------------------------------------------------

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


def _page(browser):
    """A page that records every console error and uncaught exception;
    CSP and Trusted Types violations arrive as console errors."""
    page = browser.new_page()
    page.problems = []
    page.on("console", lambda m: page.problems.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: page.problems.append(str(e)))
    return page


def _configure(app_db, airlock, **cfg_changes):
    app_db.set_setting("airlock_server_url", airlock["admin"])
    app_db.set_setting("airlock_public_url", airlock["public"])
    app_db.set_setting("airlock_admin_key", airlock["key"])
    app_db.set_setting("file_number_format", "manual")
    app_db.set_setting("practice_name", "Maple Street Therapy")
    app_db.set_setting("therapist_name", "Jordan Example")
    cfg = airlock_config.default_config()
    cfg["consent_text"] = ("# Consent to Treatment\n\nI agree to psychotherapy.\n\n"
                           "- Fees are due at each session\n- 24 hours' notice to cancel")
    for k, v in cfg_changes.items():
        cfg[k] = v
    airlock_config.save_config(app_db, cfg)
    return cfg


def _issue(client, app_db, file_number="WEB", **form):
    cid = fx.a_client(app_db, first="New", last="Client", file_number=file_number)
    data = {"forms": "both", "ttl_days": "14"}
    data.update(form)
    r = client.post(f"/airlock/invite/{cid}", data=data)
    assert r.status_code == 302, r.data
    return app_db.list_intake_invitations()[0]


def _unlock(page, airlock, inv):
    page.goto(f"{airlock['public']}/i#{inv['token']}")
    page.fill("#pin", inv["pin"])
    page.click("button:has-text('Continue')")


def _fill_adult(page):
    page.fill("#f-first_name", "Ada")
    page.fill("#f-last_name", "Lovelace")
    page.fill("#f-date_of_birth", "1990-12-10")
    page.fill("#f-address", "12 Analytical Way\nOttawa ON")
    page.fill("#f-phone", "613-555-0101")
    page.fill("#f-email", "ada@example.com")
    page.check("#f-text_number-cell")
    page.check("#f-preferred_contact-text")
    page.fill("#f-emergency_contact_name", "Charles Babbage")
    page.fill("#f-emergency_contact_phone", "613-555-0102")


def _import(client, app_db, inv):
    r = client.post("/airlock/check")
    assert r.status_code == 302, r.data
    r = client.post(f"/airlock/review/{inv['id']}/import")
    assert r.status_code == 302, r.data
    cid = int(re.search(r"/client/(\d+)", r.headers["Location"]).group(1))
    assert cid == inv["client_id"]
    return cid


def _open_submissions(app_db, airlock):
    """{form: payload} for what is on the server, opened with EdgeCase's key."""
    out = {}
    for s in airlock["store"].submissions():
        aad = ac.build_aad(s["token_hash"], s["form"], s["config_version"],
                           s["consent_version"])
        out[s["form"]] = json.loads(ac.decrypt_envelope(
            s["envelope"], app_db.airlock_private_keys(), aad))
    return out


def test_browser_fills_both_forms_and_edgecase_imports(client, app_db, airlock, browser):
    cfg = _configure(app_db, airlock)
    inv = _issue(client, app_db)
    page = _page(browser)

    _unlock(page, airlock, inv)
    page.wait_for_selector("#intake-form")
    assert "Maple Street Therapy" in page.inner_text("#letterhead")
    assert "Jordan Example" in page.inner_text("#letterhead")
    headings = page.locator("#intake-form h3").all_inner_texts()
    assert headings[:4] == ["About you", "How to reach you", "Emergency contact",
                            "A little more"]
    assert page.inner_text(".step") == "Form 1 of 2"

    _fill_adult(page)
    page.fill("#f-gender", "she/her")
    page.fill("#f-additional_info", "Stress at work.\nTrouble sleeping.")
    page.check("#agreed")
    page.fill("#typed_name", "Ada Lovelace")
    # An email import would refuse is stopped here, before anything is sent.
    page.fill("#f-email", "ada@example")
    page.click("button:has-text('Send intake form')")
    assert page.eval_on_selector("#f-email", "el => el.validationMessage")
    assert airlock["store"].submissions() == []
    page.fill("#f-email", "ada@example.com")
    page.click("button:has-text('Send intake form')")

    page.wait_for_selector("#consent-form")
    assert page.inner_text(".consent-text h3") == "Consent to Treatment"
    assert page.locator(".consent-text li").count() == 2
    page.check("#agreed")
    page.fill("#typed_name", "Ada Lovelace")
    page.click("button:has-text('Send consent form')")
    page.wait_for_selector("h2:has-text('Thank you')")
    assert "Maple Street Therapy" in page.inner_text("main")
    assert page.problems == []

    # What the browser encrypted is exactly what EdgeCase expects
    subs = _open_submissions(app_db, airlock)
    intake, consent = subs["intake"], subs["consent"]
    assert list(intake["fields"]) == list(ai.INTAKE_FIELDS)
    assert intake["fields"]["work_phone"] == "" and intake["fields"]["gender"] == "she/her"
    assert intake["fields"]["address"] == "12 Analytical Way\nOttawa ON"
    assert intake["fields"]["text_number"] == "cell"
    assert "questions" not in intake
    assert intake["guardians"] == []
    assert intake["attestation"] == {"typed_name": "Ada Lovelace", "agreed": True}
    assert consent["consent_text"] == cfg["consent_text"]

    cid = _import(client, app_db, inv)
    profile = app_db.get_profile_entry(cid)
    assert app_db.get_client(cid)["first_name"] == "Ada"
    assert profile["content"] == "she/her" and profile["preferred_contact"] == "text"
    assert profile["text_number"] == "cell"
    assert "Trouble sleeping." in profile["additional_info"]
    assert airlock["store"].submissions() == []


def test_browser_minor_intake_with_two_guardians(client, app_db, airlock, browser):
    _configure(app_db, airlock)
    inv = _issue(client, app_db, forms="intake", is_minor="1")
    page = _page(browser)
    _unlock(page, airlock, inv)
    page.wait_for_selector("#intake-form")
    assert page.locator(".step").count() == 0          # one form, no "1 of 2"
    assert page.is_hidden("#guardian-2")
    _fill_adult(page)
    page.fill("#f-g1-name", "Grace Hopper")
    page.fill("#f-g1-phone", "613-555-0199")
    page.check("#has-guardian-2")
    assert page.is_visible("#guardian-2")
    page.check("#agreed")
    page.fill("#typed_name", "Grace Hopper")
    page.click("button:has-text('Send intake form')")
    # the second guardian's name becomes required once they are added
    assert page.eval_on_selector("#f-g2-name", "el => el.validationMessage")
    page.fill("#f-g2-name", "Alan Turing")
    page.click("button:has-text('Send intake form')")
    page.wait_for_selector("h2:has-text('Thank you')")
    assert page.problems == []

    intake = _open_submissions(app_db, airlock)["intake"]
    assert [g["name"] for g in intake["guardians"]] == ["Grace Hopper", "Alan Turing"]
    cid = _import(client, app_db, inv)
    profile = app_db.get_profile_entry(cid)
    assert profile["guardian1_name"] == "Grace Hopper" and profile["guardian2_name"] == "Alan Turing"
    assert profile["is_minor"] == 1


def test_browser_refusals(client, app_db, airlock, browser):
    """No link, a wrong PIN, and a form changed mid-fill: the client is told
    plainly, and nothing reaches the server."""
    cfg = _configure(app_db, airlock)
    inv = _issue(client, app_db, forms="intake")
    page = _page(browser)

    page.goto(f"{airlock['public']}/i")
    page.wait_for_selector("h2:has-text('Please use your link')")

    page.goto(f"{airlock['public']}/i#{inv['token']}")
    page.fill("#pin", "000000" if inv["pin"] != "000000" else "111111")
    page.click("button:has-text('Continue')")
    page.wait_for_selector(".notice--error:not([hidden])")
    assert "not valid" in page.inner_text(".notice--error")

    page.fill("#pin", inv["pin"])
    page.click("button:has-text('Continue')")
    page.wait_for_selector("#intake-form")
    # The practitioner edits the form while the client is filling it in
    cfg["consent_text"] += "\n\nA new paragraph."
    airlock_config.save_config(app_db, cfg)
    ac_client = airlock_client.client_from_settings(app_db)
    ac_client.put_config(airlock_config.build_bundle(app_db, airlock_config.load_config(app_db),
                                                     str(AIRLOCK_REPO)))
    _fill_adult(page)
    page.check("#agreed")
    page.fill("#typed_name", "Ada Lovelace")
    page.click("button:has-text('Send intake form')")
    page.wait_for_selector("button:has-text('Reload the page')")
    assert "updated while you were filling it in" in page.inner_text(".notice--error")
    assert airlock["store"].submissions() == []
    # console errors here are the 401 and 409 responses themselves
    assert all("status of 40" in p for p in page.problems), page.problems


def test_browser_offers_only_contact_choices_the_client_filled_in(client, app_db, airlock,
                                                                   browser):
    _configure(app_db, airlock)
    inv = _issue(client, app_db, forms="intake")
    page = _page(browser)
    _unlock(page, airlock, inv)
    page.wait_for_selector("#intake-form")

    def offered(field):
        return [el.get_attribute("data-value")
                for el in page.locator(f"#f-{field} label.radio:visible").all()]

    assert offered("text_number") == ["none"]
    assert offered("preferred_contact") == []
    assert page.is_visible("#f-preferred_contact .choice-hint")

    page.fill("#f-home_phone", "613-555-0199")
    page.fill("#f-email", "ada@example.com")
    assert offered("text_number") == ["home", "none"]
    assert offered("preferred_contact") == ["email", "call_home"]
    assert page.is_hidden("#f-preferred_contact .choice-hint")

    page.check("#f-text_number-home")
    assert offered("preferred_contact") == ["email", "call_home", "text"]
    page.check("#f-preferred_contact-text")

    # Clearing the home phone withdraws both choices that depended on it
    page.fill("#f-home_phone", "")
    assert offered("text_number") == ["none"]
    assert not page.is_checked("#f-text_number-home")
    assert offered("preferred_contact") == ["email"]
    assert not page.is_checked("#f-preferred_contact-text")

    page.fill("#f-home_phone", "613-555-0199")
    page.check("#f-text_number-home")
    page.check("#f-preferred_contact-text")
    page.fill("#f-first_name", "Ada")
    page.fill("#f-last_name", "Lovelace")
    page.check("#agreed")
    page.fill("#typed_name", "Ada Lovelace")
    page.click("button:has-text('Send intake form')")
    page.wait_for_selector("h2:has-text('Thank you')")
    assert page.problems == []

    cid = _import(client, app_db, inv)
    profile = app_db.get_profile_entry(cid)
    assert (profile["text_number"], profile["preferred_contact"]) == ("home", "text")
    assert not profile["date_of_birth"] and not profile["emergency_contact_name"]


def test_browser_revoke_uses_the_app_modal(client, app_db, airlock, browser):
    """EdgeCase's own invitation page, with its real stylesheets, in Chromium:
    Revoke opens the app's modal (no browser dialog), Cancel and Escape close
    it, and confirming submits the revoke."""
    _configure(app_db, airlock)
    inv = _issue(client, app_db)
    page = _page(browser)
    dialogs = []
    page.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))

    # Chromium's route callbacks run outside Flask's context, so the page and
    # every file it loads are fetched first, and the form post it makes is
    # recorded here and replayed to EdgeCase afterwards.
    path = f"/airlock/invitations/{inv['id']}"
    html = client.get(path).data.decode()
    files = {path: (html.encode(), "text/html; charset=utf-8")}
    for ref in set(re.findall(r'(?:href|src)="(/static/[^"]+)"', html)):
        r = client.get(ref)
        files[ref] = (r.data, r.headers.get("Content-Type"))
    posts = []

    def serve(route):
        req = route.request
        url_path = req.url.removeprefix("http://edgecase.test")
        if req.method == "HEAD":        # base.html checks the server is up first
            route.fulfill(status=200, body="")
        elif req.method == "POST":
            posts.append((url_path, req.post_data, req.headers.get("content-type")))
            route.fulfill(status=200, body="posted", content_type="text/plain")
        elif url_path in files:
            body, ctype = files[url_path]
            route.fulfill(status=200, body=body, content_type=ctype)
        else:
            route.fulfill(status=404, body="")

    page.route("http://edgecase.test/**", serve)
    page.goto(f"http://edgecase.test{path}")
    assert page.is_hidden("#al-confirm-modal")

    page.click("button:has-text('Revoke')")
    assert page.is_visible("#al-confirm-modal")
    assert page.inner_text("#al-confirm-title") == "Revoke Invitation"
    page.click("#al-confirm-modal button:has-text('Cancel')")
    assert page.is_hidden("#al-confirm-modal")
    page.click("button:has-text('Revoke')")
    page.keyboard.press("Escape")
    assert page.is_hidden("#al-confirm-modal")
    page.wait_for_timeout(200)
    assert posts == []

    page.click("button:has-text('Revoke')")
    with page.expect_response(lambda r: r.request.method == "POST"):
        page.click("#al-confirm-ok")
    assert [p[0] for p in posts] == [f"/airlock/invitations/{inv['id']}/revoke"]
    r = client.post(posts[0][0], data=posts[0][1], content_type=posts[0][2])
    assert "msg=revoked" in r.headers["Location"]
    assert app_db.get_intake_invitation(inv["id"])["status"] == "revoked"
    assert dialogs == []


def test_browser_marks_required_fields_not_optional_ones(client, app_db, airlock, browser):
    _configure(app_db, airlock)
    inv = _issue(client, app_db, file_number="WEB-R")
    page = _page(browser)
    page.goto(f"{airlock['public']}/i#{inv['token']}")
    page.wait_for_selector("#pin")
    assert page.inner_text(".brand").lower() == "secure client forms"
    assert "separately" not in page.inner_text("#pin-help")
    page.fill("#pin", inv["pin"])
    page.click("button:has-text('Continue')")
    page.wait_for_selector("#intake-form")
    for name in ("first_name", "last_name"):
        assert page.inner_text(f"label[for=f-{name}]").endswith("(required)")
    for name in ("middle_name", "date_of_birth", "gender", "email", "emergency_contact_name"):
        label = page.inner_text(f"label[for=f-{name}]")
        assert "(required)" not in label and "(optional)" not in label, name
    assert page.inner_text("label[for=typed_name]").endswith("(required)")
    assert "at least one way to reach you" in page.inner_text("#intake-form")
    assert page.problems == []
