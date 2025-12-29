"""
EdgeCase Configuration

Provides dynamically-derived paths based on the application's location.

In development mode (running from source), data is stored relative to the app.
In installed mode (PyApp or /Applications), data is stored in platform-appropriate
user directories to survive app updates.
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
    
    # Check common install locations
    app_path = str(APP_ROOT).lower()
    
    if sys.platform == 'darwin':
        # macOS: /Applications or ~/Applications
        if '/applications/' in app_path:
            return True
    elif sys.platform == 'win32':
        # Windows: Program Files
        if 'program files' in app_path:
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


# Determine data root based on mode
if _is_installed_mode():
    DATA_ROOT = _get_user_data_root()
    # Ensure directory exists
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
else:
    # Development mode - store relative to app
    DATA_ROOT = APP_ROOT

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
    """Return True if running in development mode."""
    return not _is_installed_mode()
