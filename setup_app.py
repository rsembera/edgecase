"""
py2app build script for EdgeCase Equalizer
Creates a standalone macOS .app bundle

Run with: python setup_app.py py2app
"""

from setuptools import setup

APP = ['desktop.py']
APP_NAME = 'EdgeCase Equalizer'

OPTIONS = {
    'argv_emulation': False,
    'iconfile': 'assets/icon.icns',
    'plist': {
        'CFBundleName': APP_NAME,
        'CFBundleDisplayName': APP_NAME,
        'CFBundleIdentifier': 'ca.lightinextension.edgecase',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '10.15',
        'NSRequiresAquaSystemAppearance': False,
    },
    'packages': [
        'flask',
        'jinja2',
        'werkzeug',
        'waitress',
        'webview',
        'sqlcipher3',
        'cryptography',
        'reportlab',
        'PIL',
        'markdown',
    ],
    'includes': [
        'web.app',
        'web.cli',
        'web.utils',
        'web.blueprints.ai',
        'web.blueprints.auth',
        'web.blueprints.backups',
        'web.blueprints.clients',
        'web.blueprints.entries',
        'web.blueprints.ledger',
        'web.blueprints.links',
        'web.blueprints.scheduler',
        'web.blueprints.settings',
        'web.blueprints.statements',
        'web.blueprints.types',
        'core.database',
        'core.config',
        'core.encryption',
        'utils.backup',
        'utils.formatters',
        'utils.validators',
        'pdf.generator',
        'pdf.ledger_report',
        'pdf.client_export',
        'pdf.formatting',
        'pdf.templates',
        'ai.assistant',
        'ai.model_manager',
        'ai.prompts',
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

setup(
    app=APP,
    name=APP_NAME,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
