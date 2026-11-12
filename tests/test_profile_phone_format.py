"""The Client Profile's phone fields (web/static/js/profile.js), run under node.

The Profile reformats every phone field when the page opens and on each
keystroke. It kept digits only and stopped at 12, so a number AirLock had
imported with an extension ("(613) 555-0100 x12") or a long international
number was rewritten the next time the Profile was opened and saved: the
extension ran into the number, the + was lost, the 13th digit cut off.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from core import airlock_import as ai

ROOT = Path(__file__).resolve().parent.parent
PROFILE_JS = ROOT / "web" / "static" / "js" / "profile.js"
SETTINGS_JS = ROOT / "web" / "static" / "js" / "settings.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


def _phone_functions():
    src = PROFILE_JS.read_text()
    start = src.index("/**\n * Format phone number for display")
    end = src.index("// Add event listeners to all phone inputs")
    return src[start:end]


def _run(expr, value):
    script = _phone_functions() + f"\nconsole.log(JSON.stringify({expr}(process.argv[1])));"
    out = subprocess.run(["node", "-e", script, value], capture_output=True, text=True,
                         timeout=30, check=True)
    return json.loads(out.stdout)


@pytest.mark.parametrize("typed, shown", [
    ("6135550100", "(613) 555-0100"),
    ("(613) 555-0100", "(613) 555-0100"),
    ("(613) 555-0100 x12", "(613) 555-0100 x12"),          # as AirLock imports it
    ("613-555-0100 ext. 4", "(613) 555-0100 x4"),
    ("(613) 555-0100x", "(613) 555-0100 x"),               # typing an extension
    ("+49 1512 3456789", "+4915123456789"),
    ("+86 138 0013 8000 x12", "+8613800138000 x12"),
    ("4915123456789", "4915123456789"),
    ("12345678901234567890", "123456789012345"),           # 15 at most
    ("613555", "613555"),
])
def test_profile_phone_field_keeps_extension_plus_and_long_numbers(typed, shown):
    assert _run("formatPhoneNumber", typed) == shown
    assert _run("formatPhoneNumber", shown) == shown         # reopening changes nothing


@pytest.mark.parametrize("value, ok", [
    ("", True), ("(613) 555-0100", True), ("(613) 555-0100 x12", True),
    ("+4915123456789", True), ("123456789012345", True),
    ("613555010", False), ("(613) 555-010 x12", False), ("1234567890123456", False),
])
def test_profile_phone_length_is_counted_without_the_extension(value, ok):
    assert _run("validatePhone", value) is ok


def test_profile_and_practice_phone_limits_match_import():
    """One limit everywhere: the Profile, the practice's own number in
    Settings, the AirLock page and AirLock import."""
    assert (ai.PHONE_MIN_DIGITS, ai.PHONE_MAX_DIGITS) == (10, 15)
    profile = PROFILE_JS.read_text()
    assert re.search(r"const PHONE_MAX_DIGITS = 15;", profile)
    assert "must be 10-15 digits" in profile and "10-12" not in profile
    settings = SETTINGS_JS.read_text()
    assert "cleaned.substring(0, 15)" in settings and "substring(0, 12)" not in settings
