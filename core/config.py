"""
EdgeCase Configuration

Provides dynamically-derived paths based on the application's location.
This allows the app to be moved to any directory without breaking.
"""

import os
from pathlib import Path

# App root is the parent of the 'core' directory where this file lives
APP_ROOT = Path(__file__).parent.parent

# Key directories
DATA_DIR = APP_ROOT / 'data'
ASSETS_DIR = APP_ROOT / 'assets'
ATTACHMENTS_DIR = APP_ROOT / 'attachments'
BACKUPS_DIR = APP_ROOT / 'backups'
MODELS_DIR = APP_ROOT / 'models'


def get_assets_path():
    """Return the path to the assets directory."""
    return str(ASSETS_DIR)


def get_attachments_path():
    """Return the path to the attachments directory."""
    return str(ATTACHMENTS_DIR)


def get_data_path():
    """Return the path to the data directory."""
    return str(DATA_DIR)
