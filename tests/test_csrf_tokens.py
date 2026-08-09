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
