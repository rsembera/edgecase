"""Layout rules that are easy to lose in a CSS edit."""
import re
from pathlib import Path

CSS = Path(__file__).resolve().parent.parent / "web" / "static" / "css"


def test_dropdown_icons_are_centred_on_their_text():
    # Baseline alignment left each menu icon sitting a little low (2026-09-30).
    rule = re.search(r"\n\.dropdown-item\s*{([^}]*)}", (CSS / "shared.css").read_text()).group(1)
    assert re.search(r"display:\s*flex", rule)
    assert re.search(r"align-items:\s*center", rule)
