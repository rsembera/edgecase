"""The packaging manifest must cover what the app actually imports.

setup_app.py is only exercised when someone builds a .dmg, so mistakes in it
stay invisible for months and then surface as a packaged app that dies at
login. That is exactly what had happened: core/database.py became a facade
over core/db/, entries.py and statements.py became blueprint packages, and
crypto v2 then v3 were added — none of which reached the manifest.

This test imports the app for real and asserts every top-level package it
pulls in is declared. It is a drift alarm, not a build test: it cannot prove
py2app will succeed, only that the manifest still describes the application.
"""
import importlib
import os
import sys

import pytest


@pytest.fixture(scope="module")
def imported_app_modules():
    """Import the app the way it runs, then report what got loaded."""
    os.environ["EDGECASE_TESTING"] = "1"
    importlib.import_module("web.app")
    # Lazily-imported paths that a bare `import web.app` would not reach.
    for name in ("core.migrate_crypto", "core.encryption_v3", "core.billing",
                 "core.money", "utils.backup", "pdf.generator", "ai.assistant",
                 "web.cli"):
        importlib.import_module(name)
    return dict(sys.modules)


@pytest.fixture(scope="module")
def manifest():
    import setup_app
    return setup_app


FIRST_PARTY_ROOTS = {"core", "web", "utils", "pdf", "ai"}


def test_first_party_roots_are_declared(manifest):
    """Declared as packages, so submodules are covered automatically."""
    declared = set(manifest.FIRST_PARTY_PACKAGES)
    assert FIRST_PARTY_ROOTS <= declared, FIRST_PARTY_ROOTS - declared


def test_every_imported_third_party_package_is_declared(imported_app_modules,
                                                        manifest):
    declared = {p.lower() for p in manifest.OPTIONS["packages"]}
    missing = set()
    for name, module in imported_app_modules.items():
        if "." in name or name.startswith("_") or module is None:
            continue
        path = str(getattr(module, "__file__", "") or "")
        if "site-packages" not in path:
            continue
        if name.lower() not in declared:
            missing.add(name)
    # Test and build tooling, not application runtime dependencies. These are
    # in sys.modules because pytest and setuptools are running, not because
    # EdgeCase imports them.
    missing -= {"pytest", "py", "pluggy", "iniconfig", "setuptools", "pkg_resources",
                "_pytest", "anyio", "sniffio", "attr", "attrs", "cffi", "pycparser",
                "packaging", "exceptiongroup", "idna", "typing_extensions",
                "distutils", "more_itertools", "pygments", "tomli", "jaraco",
                "backports", "importlib_metadata", "zipp", "platformdirs",
                "wheel", "py2app", "macholib", "modulegraph", "altgraph"}
    assert not missing, f"undeclared runtime packages: {sorted(missing)}"


def test_argon2_is_declared(manifest):
    """Load-bearing and easy to miss: imported only inside encryption_v2, a
    CFFI extension rather than pure Python, and its absence would fail at
    login — the first key derivation — not at startup."""
    assert "argon2" in manifest.OPTIONS["packages"]


@pytest.mark.parametrize("module", ["core.encryption_v2", "core.encryption_v3",
                                    "core.migrate_crypto"])
def test_crypto_modules_are_explicitly_included(manifest, module):
    """These are imported from inside functions to avoid circular imports, so
    they are named explicitly rather than trusted to static analysis."""
    assert module in manifest.OPTIONS["includes"]


def test_declared_packages_are_all_importable(manifest):
    """A typo in the manifest should fail here, not during a .dmg build."""
    unimportable = []
    for name in manifest.OPTIONS["packages"]:
        try:
            importlib.import_module(name)
        except Exception:
            unimportable.append(name)
    # webview needs a display and markdown may be optional at test time.
    unimportable = [n for n in unimportable if n not in ("webview", "markdown")]
    assert not unimportable, f"declared but not importable: {unimportable}"


def test_templates_are_bundled(manifest):
    """The recovery-key screens live in web/templates; a build that drops them
    would fail only when a user hits the upgrade path."""
    assert "web/templates" in manifest.OPTIONS["resources"]
