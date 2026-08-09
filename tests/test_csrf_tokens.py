"""Every POST form must carry a CSRF token.

CSRFProtect is registered globally, so a form that omits the hidden field does
not fail at render or in any unit test — it fails at the moment a real user
presses the button, with a bare 'Bad Request: The CSRF token is missing.'
That is exactly how four new recovery-key forms shipped broken.

This walks the templates directly rather than exercising routes, so it covers
forms on pages no test happens to visit.
"""
import re
from pathlib import Path

import pytest

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "web" / "templates"
STATIC_CSS = Path(__file__).resolve().parent.parent / "web" / "static" / "css"

FORM_RE = re.compile(r"<form\b[^>]*>.*?</form>", re.IGNORECASE | re.DOTALL)
METHOD_POST_RE = re.compile(r'method\s*=\s*["\']post["\']', re.IGNORECASE)


def _post_forms(path: Path):
    html = path.read_text(encoding="utf-8", errors="replace")
    return [m.group(0) for m in FORM_RE.finditer(html)
            if METHOD_POST_RE.search(m.group(0).split(">", 1)[0])]


def _template_files():
    return sorted(p for p in TEMPLATE_DIR.rglob("*.html"))


def test_templates_are_discoverable():
    """Guard against the walk silently finding nothing and passing."""
    assert len(_template_files()) > 10


@pytest.mark.parametrize("path", _template_files(), ids=lambda p: p.name)
def test_every_post_form_has_a_csrf_token(path):
    offenders = [f for f in _post_forms(path) if "csrf_token" not in f]
    assert not offenders, (
        f"{path.name}: {len(offenders)} POST form(s) without a csrf_token "
        f"hidden field — these fail with 'Bad Request: The CSRF token is "
        f"missing.' only when a user actually submits them."
    )


# --- Auth screens must use the standard button styles ---

AUTH_SCREENS = ["recovery_key.html", "recovery_key_regenerate.html",
                "recovery_key_verify.html", "recover.html",
                "recover_reset.html", "upgrading.html"]


@pytest.mark.parametrize("name", AUTH_SCREENS)
def test_auth_screens_use_the_shared_button_partial(name):
    """These pages are standalone (like login.html) and never load
    static/css/shared.css, so they shipped with hand-rolled dark-green
    buttons that matched nothing else in the app. They now all include one
    partial mirroring .btn / .btn-secondary."""
    html = (TEMPLATE_DIR / name).read_text(encoding="utf-8")
    assert "components/_auth_buttons.html" in html


@pytest.mark.parametrize("name", AUTH_SCREENS)
def test_auth_screens_have_no_hand_rolled_button_fills(name):
    """Guard against a bespoke button creeping back in. #115D4F is the
    primary TEXT colour in the real palette, never a button background."""
    html = (TEMPLATE_DIR / name).read_text(encoding="utf-8")
    assert "background: #115D4F" not in html
    assert "background:#115D4F" not in html


def test_button_partial_matches_shared_css_palette():
    """If shared.css moves, this partial must move with it."""
    partial = (TEMPLATE_DIR / "components" / "_auth_buttons.html").read_text()
    shared = (STATIC_CSS / "shared.css").read_text()
    for var, value in (("--color-primary-lighter", "#BFDCDC"),
                       ("--color-primary-light", "#9FCFC0"),
                       ("--color-primary-dark", "#115D4F"),
                       ("--color-text-light", "#4B5563")):
        assert f"{var}: {value};" in shared, f"{var} changed in shared.css"
        assert value in partial, f"{value} missing from the button partial"
