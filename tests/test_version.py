"""One version number: core/config.py, checked against pyproject.toml and the
Mac bundle, and shown in the About box."""
import re
import tomllib
from pathlib import Path

from core import config

ROOT = Path(__file__).resolve().parent.parent


def test_pyproject_matches():
    with open(ROOT / "pyproject.toml", "rb") as f:
        assert tomllib.load(f)["project"]["version"] == config.APP_VERSION


def test_mac_bundle_matches():
    setup = (ROOT / "setup_app.py").read_text()
    for key in ("CFBundleVersion", "CFBundleShortVersionString"):
        assert re.search(rf"'{key}':\s*'{re.escape(config.APP_VERSION)}'", setup), key


def test_about_box_shows_the_version(client):
    page = client.get("/settings").data.decode()
    assert f"v{config.APP_VERSION} {config.APP_RELEASE_NAME}" in page
