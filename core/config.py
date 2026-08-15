"""
EdgeCase Configuration

Provides dynamically-derived paths based on the application's location.

Priority for data location:
1. EDGECASE_DATA environment variable (explicit override)
2. Installed mode (PyApp, /Applications) -> platform user directories
3. Development mode -> relative to app folder
"""

import os
import sys
from pathlib import Path

# App root is the parent of the 'core' directory where this file lives
APP_ROOT = Path(__file__).parent.parent


def _is_installed_mode():
    """
    Detect if we're running as an installed app vs development.
    
    Returns True if:
    - PYAPP environment variable is set (PyApp distribution)
    - Running from /Applications (macOS)
    - Running from Program Files (Windows)
    - EDGECASE_INSTALLED env var is set (manual override)
    """
    # Explicit override
    if os.environ.get('EDGECASE_INSTALLED'):
        return True
    
    # PyApp sets this
    if os.environ.get('PYAPP'):
        return True
    
    # Check if running from an installed app bundle/location
    app_path = str(APP_ROOT)
    
    if sys.platform == 'darwin':
        # macOS: Check if we're inside a .app bundle (PyApp creates this structure)
        # App bundles run from: Something.app/Contents/MacOS/ or Something.app/Contents/Resources/
        if '.app/Contents/' in app_path:
            return True
    elif sys.platform == 'win32':
        # Windows: Program Files
        if 'program files' in app_path.lower():
            return True
    else:
        # Linux: /usr, /opt, or ~/.local/bin
        if app_path.startswith(('/usr/', '/opt/')) or '/.local/bin/' in app_path:
            return True
    
    return False


def _get_user_data_root():
    """
    Get the platform-appropriate user data directory.
    
    macOS:   ~/Library/Application Support/EdgeCase/
    Windows: %APPDATA%/EdgeCase/
    Linux:   ~/.local/share/EdgeCase/
    """
    if sys.platform == 'darwin':
        base = Path.home() / 'Library' / 'Application Support'
    elif sys.platform == 'win32':
        base = Path(os.environ.get('APPDATA', Path.home() / 'AppData' / 'Roaming'))
    else:
        # Linux/Unix - follow XDG spec
        xdg_data = os.environ.get('XDG_DATA_HOME')
        if xdg_data:
            base = Path(xdg_data)
        else:
            base = Path.home() / '.local' / 'share'
    
    return base / 'EdgeCase'


def _get_data_root():
    """
    Determine the data root directory.
    
    Priority:
    1. EDGECASE_DATA env var (explicit override for testing/alternate data)
    2. Installed mode -> platform user directories
    3. Development mode -> relative to app folder
    """
    # Check for explicit override first
    custom_data_path = os.environ.get('EDGECASE_DATA')
    if custom_data_path:
        path = Path(custom_data_path)
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    # Check if installed mode
    if _is_installed_mode():
        path = _get_user_data_root()
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    # Development mode - store relative to app
    return APP_ROOT


# Determine data root based on mode
DATA_ROOT = _get_data_root()

# Key directories
DATA_DIR = DATA_ROOT / 'data'
ASSETS_DIR = DATA_ROOT / 'assets'
ATTACHMENTS_DIR = DATA_ROOT / 'attachments'
BACKUPS_DIR = DATA_ROOT / 'backups'
MODELS_DIR = DATA_ROOT / 'models'


def get_assets_path():
    """Return the path to the assets directory."""
    return str(ASSETS_DIR)


def get_attachments_path():
    """Return the path to the attachments directory."""
    return str(ATTACHMENTS_DIR)


def get_data_path():
    """Return the path to the data directory."""
    return str(DATA_DIR)


def get_backups_path():
    """Return the path to the backups directory."""
    return str(BACKUPS_DIR)


def get_models_path():
    """Return the path to the models directory."""
    return str(MODELS_DIR)


def is_development_mode():
    """Return True if running in development mode (no env override, not installed)."""
    return not os.environ.get('EDGECASE_DATA') and not _is_installed_mode()


def get_data_root():
    """Return the current data root path."""
    return str(DATA_ROOT)


def get_state_dir():
    """Directory for small state files that must survive DATA_ROOT loss.

    The backup-locations record lives here (see utils/backup.py). Its whole
    purpose is disaster recovery — telling EdgeCase where its backups went
    after the data root is gone — so storing it *inside* DATA_ROOT would
    destroy it in exactly the situation it exists for.

    Resolved at CALL time, not import time, so the EDGECASE_DATA override
    keeps the testing instance's state separate from production even though
    both processes import this module the same way.
    """
    custom_data_path = os.environ.get('EDGECASE_DATA')
    if custom_data_path:
        # Explicit data override (testing instance): keep state under it so
        # test and production installs never share a locations record.
        return Path(custom_data_path) / 'state'

    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Preferences' / 'EdgeCase'
    if sys.platform == 'win32':
        base = Path(os.environ.get('LOCALAPPDATA',
                                   Path.home() / 'AppData' / 'Local'))
        return base / 'EdgeCase'
    xdg = os.environ.get('XDG_CONFIG_HOME')
    base = Path(xdg) if xdg else Path.home() / '.config'
    return base / 'edgecase'


def get_backup_locations_file():
    """Where EdgeCase records the folders it has written backups to."""
    return get_state_dir() / 'backup_locations.json'


def resolve_attachment_path(filepath):
    """Resolve a stored attachment path against DATA_ROOT.

    Attachment records in the database store paths relative to DATA_ROOT
    (see web/utils.py save_uploaded_files). Bare relative paths only work
    when CWD == DATA_ROOT, which is true in dev mode but not in installed
    or desktop mode. Always pass attachment filepaths through this helper
    before opening them.
    """
    if os.path.isabs(filepath):
        return filepath
    return str(DATA_ROOT / filepath)
