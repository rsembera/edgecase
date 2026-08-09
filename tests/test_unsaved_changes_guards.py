"""Pages holding unsaved clinical text must guard against navigating away.

The AI Scribe page had no protection of any kind: generated text lives only
in its textarea until Keep Changes POSTs it, so clicking Back discarded a
proofread note silently. It was missed because both existing guards key off
a form — form-guard.js binds form[data-dirty-guard], session.js binds
#session-entry-form — and the Scribe page has no form at all, just a bare
textarea. Reported by Rick 2026-08-09.

These assert on markup and source rather than driving a browser. Crude, but
the properties worth pinning are structural, and the alternative is no
coverage at all for a whole class of silent data loss.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "web" / "templates"
JS = ROOT / "web" / "static" / "js"

MODAL_IDS = ("unsaved-changes-modal", "unsaved-stay-btn", "unsaved-leave-btn")


def test_scribe_page_includes_the_unsaved_changes_modal():
    html = (TEMPLATES / "ai_scribe.html").read_text()
    assert "components/unsaved_changes_modal.html" in html


def test_scribe_back_link_is_addressable():
    """The guard intercepts by id; without it the link cannot be caught."""
    html = (TEMPLATES / "ai_scribe.html").read_text()
    assert 'id="btn-back-to-session"' in html


def test_scribe_guard_arms_beforeunload_and_the_back_link():
    src = (JS / "ai_scribe.js").read_text()
    assert "beforeunload" in src
    assert "btn-back-to-session" in src
    assert "unsaved-changes-modal" in src


def test_scribe_guard_listens_in_the_capture_phase():
    """The base layout's liveness handler preventDefaults link clicks and
    navigates programmatically, so a bubble-phase listener cannot stop it.
    Same constraint documented in form-guard.js and session.js."""
    src = (JS / "ai_scribe.js").read_text()
    click_guard = src[src.index("btn-back-to-session"):]
    assert "stopPropagation" in click_guard
    # The capture flag on the window click listener.
    assert re.search(r"addEventListener\(\s*'click'[\s\S]{0,900}?\}\s*,\s*true\s*\)", src)


def test_keep_changes_disarms_the_guard():
    """Saving is a deliberate leave and must not warn — the content is in
    the database by the time the redirect fires."""
    src = (JS / "ai_scribe.js").read_text()
    save_block = src[src.index("async function saveContent"):]
    save_block = save_block[:save_block.index("function revertContent")]
    assert "disarmScribeGuard" in save_block
    disarm = save_block.index("disarmScribeGuard")
    redirect = save_block.index("window.location.href")
    assert disarm < redirect, "guard must be disarmed BEFORE the redirect"


@pytest.mark.parametrize("element_id", MODAL_IDS)
def test_shared_modal_still_provides_expected_ids(element_id):
    """All three guards (form-guard.js, session.js, ai_scribe.js) look these
    up by id; renaming one silently disarms every guard that uses it."""
    html = (TEMPLATES / "components" / "unsaved_changes_modal.html").read_text()
    assert f'id="{element_id}"' in html
