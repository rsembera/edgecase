"""Layout rules that are easy to lose in a CSS edit."""
import re
from pathlib import Path

CSS = Path(__file__).resolve().parent.parent / "web" / "static" / "css"


def test_dropdown_icons_are_centred_on_their_text():
    # Baseline alignment left each menu icon sitting a little low (2026-09-30).
    rule = re.search(r"\n\.dropdown-item\s*{([^}]*)}", (CSS / "shared.css").read_text()).group(1)
    assert re.search(r"display:\s*flex", rule)
    assert re.search(r"align-items:\s*center", rule)


def test_statements_earlier_unbilled_note_uses_a_defined_class():
    # The "unbilled entries from before this range" note was emitted with
    # .data-loss-notice, which is styled only inside login.html — so on the
    # statements page it rendered as plain text (2026-10-13). Every class
    # the note uses must exist in a stylesheet that page loads.
    js = (CSS.parent / "js" / "outstanding_statements.js").read_text()
    m = re.search(r'beforeNote = `\s*<div class="([^"]+)"', js)
    assert m, "earlier-unbilled note markup not found"
    loaded = (CSS / "shared.css").read_text() + (CSS / "outstanding_statements.css").read_text()
    for cls in m.group(1).split():
        assert re.search(r"\." + re.escape(cls) + r"\b", loaded), f".{cls} is not defined for this page"
