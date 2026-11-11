"""The client file's New menu must never end up partly off screen.

It used to flip above its button whenever it did not fit below, even when
there was no room above either, which cut off the top of the menu. The
placement logic in web/static/js/client_file.js is run here under node with
a stand-in for the browser's geometry.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

JS = Path(__file__).resolve().parent.parent / "web/static/js/client_file.js"

HARNESS = r"""
const [file, json] = process.argv.slice(-2);
const src = require('fs').readFileSync(file, 'utf8');
const m = src.match(/function keepDropdownOnScreen[\s\S]*?\n}\n/);
const c = JSON.parse(json);
const scrolls = [];
const window = { innerHeight: c.viewport, scrollY: c.scrollY,
                 scrollBy: (o) => scrolls.push(o.top) };
const classes = new Set();
const dropdown = {
    classList: { add: (x) => classes.add(x), remove: (x) => classes.delete(x) },
    // The button sits at c.button (its top edge), 38px tall; the menu is
    // c.menu tall and hangs 8px below it, or sits 8px above it when flipped.
    getBoundingClientRect: () => classes.has('dropdown-menu-up')
        ? { top: c.button - 8 - c.menu, bottom: c.button - 8 }
        : { top: c.button + 46, bottom: c.button + 46 + c.menu },
};
if (!m) { console.log(JSON.stringify({ missing: true })); process.exit(0); }
eval(m[0] + '; keepDropdownOnScreen(dropdown);');
console.log(JSON.stringify({ up: classes.has('dropdown-menu-up'), scrolls }));
"""


def _place(**case):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    out = subprocess.run([node, "-e", HARNESS, str(JS), json.dumps(case)],
                         capture_output=True, text=True, check=True)
    result = json.loads(out.stdout)
    assert not result.get("missing"), "keepDropdownOnScreen not found in client_file.js"
    return result


def _visible(case, result):
    """Where the menu ends up after any scroll, in window coordinates."""
    shift = sum(result["scrolls"])
    if result["up"]:
        top, bottom = case["button"] - 8 - case["menu"], case["button"] - 8
    else:
        top, bottom = case["button"] + 46, case["button"] + 46 + case["menu"]
    return top - shift, bottom - shift


def test_menu_that_fits_below_is_left_alone():
    r = _place(viewport=800, scrollY=0, button=100, menu=400)
    assert r == {"up": False, "scrolls": []}


def test_menu_opens_above_when_only_that_fits():
    r = _place(viewport=800, scrollY=300, button=600, menu=400)
    assert r == {"up": True, "scrolls": []}


@pytest.mark.parametrize("case", [
    # Short page, nothing to scroll back to: the old code flipped the menu
    # up and cut its top off.
    dict(viewport=600, scrollY=0, button=300, menu=400),
    # Scrolled a little, but not far enough to make room above.
    dict(viewport=600, scrollY=40, button=300, menu=400),
    # Scrolled well down: room can be made above by scrolling up.
    dict(viewport=600, scrollY=900, button=300, menu=400),
])
def test_menu_is_fully_visible_when_it_fits_neither_way(case):
    r = _place(**case)
    assert len(r["scrolls"]) == 1
    top, bottom = _visible(case, r)
    assert top >= 0 and bottom <= case["viewport"]
    # never asks to scroll above the top of the page
    assert case["scrollY"] + r["scrolls"][0] >= 0


def test_toggle_uses_the_placement_helper():
    src = JS.read_text()
    body = re.search(r"function toggleDropdown[\s\S]*?\n}\n", src).group(0)
    assert "keepDropdownOnScreen(dropdown)" in body
