"""
py2app build script for EdgeCase Equalizer
Creates a standalone macOS .app bundle

Run with: python setup_app.py py2app

MAINTENANCE NOTE
----------------
First-party code is declared as PACKAGES, not as an enumerated list of
modules. An enumerated list silently rots: core/database.py became a facade
over core/db/, and entries.py and statements.py became blueprint packages,
and none of those submodules were ever added here — so a packaged build would
have shipped without them. Declaring the packages themselves means new
modules are picked up automatically.

tests/test_packaging_manifest.py asserts that everything actually imported by
the running app is covered by the declarations below, so this file cannot
drift out of date again without a test failing.
"""

from setuptools import setup

APP = ['desktop.py']
APP_NAME = 'EdgeCase Equalizer'

# Third-party runtime dependencies.
#
# argon2 (argon2-cffi) is load-bearing and easy to miss: it is imported only
# inside core.encryption_v2, it is a CFFI extension rather than pure Python,
# and without it a packaged build fails at LOGIN — the first moment a key is
# derived — rather than at startup.
THIRD_PARTY_PACKAGES = [
    'flask',
    'flask_wtf',
    'wtforms',
    'jinja2',
    'markupsafe',
    'werkzeug',
    'itsdangerous',
    'blinker',
    'click',
    'waitress',
    'webview',
    'sqlcipher3',
    'cryptography',
    'argon2',
    'defusedxml',
    'reportlab',
    'PIL',
    'markdown',
]

# First-party packages. Everything under these is bundled, so the crypto v2/v3
# modules, the core.db mixins and the blueprint packages are all covered
# without being named individually.
FIRST_PARTY_PACKAGES = [
    'core',
    'web',
    'utils',
    'pdf',
    'ai',
]

OPTIONS = {
    'argv_emulation': False,
    'iconfile': 'assets/icon.icns',
    'plist': {
        'CFBundleName': APP_NAME,
        'CFBundleDisplayName': APP_NAME,
        'CFBundleIdentifier': 'ca.lightinextension.edgecase',
        'CFBundleVersion': '2.0.1',
        'CFBundleShortVersionString': '2.0.1',
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '10.15',
        'NSRequiresAquaSystemAppearance': False,
    },
    'packages': THIRD_PARTY_PACKAGES + FIRST_PARTY_PACKAGES,
    'includes': [
        # Imported lazily from inside functions, so static analysis can miss
        # them even though the packages above are bundled.
        'core.encryption_v2',
        'core.encryption_v3',
        'core.migrate_crypto',
        'web.cli',
    ],
    'excludes': [
        'tkinter',
        'PyQt5',
        'PyQt6',
    ],
    'resources': [
        'web/templates',
        'web/static',
        'assets',
    ],
}

# Guarded so the manifest above can be imported and inspected (by
# tests/test_packaging_manifest.py) without invoking setuptools, which would
# exit the interpreter. py2app runs this file directly, so the build path is
# unaffected.
if __name__ == '__main__':
    # Modern setuptools populates install_requires from pyproject.toml's
    # [project] dependencies table even when this script is run directly —
    # and py2app refuses to build when install_requires is set (it bundles
    # from the live venv and never installs dependencies itself). Clear the
    # attribute before py2app's check runs; the pyproject table stays
    # authoritative for pip installs, which never touch this file.
    from py2app.build_app import py2app as _py2app_cmd

    class py2app_from_venv(_py2app_cmd):
        def finalize_options(self):
            self.distribution.install_requires = None
            super().finalize_options()

    setup(
        app=APP,
        name=APP_NAME,
        options={'py2app': OPTIONS},
        cmdclass={'py2app': py2app_from_venv},
    )
