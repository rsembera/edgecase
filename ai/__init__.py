"""
AI Scribe - Local LLM Assistant for EdgeCase Equalizer
"""

from ai.assistant import (
    is_model_downloaded,
    is_model_loaded,
    get_model_info,
    check_system_capability,
    download_model,
    delete_model,
    load_model,
    unload_model,
    generate,
    # Constants needed by blueprint
    MODEL_REPO,
    MODEL_FILENAME,
    MODEL_DIR,
)

from ai.prompts import (
    build_prompt,
    get_system_prompt,
    get_actions,
    ACTION_LABELS,
    ACTION_DESCRIPTIONS,
    ACTION_ICONS,
)

__all__ = [
    'is_model_downloaded',
    'is_model_loaded',
    'get_model_info',
    'check_system_capability',
    'download_model',
    'delete_model',
    'load_model',
    'unload_model',
    'generate',
    'build_prompt',
    'get_system_prompt',
    'get_actions',
    'ACTION_LABELS',
    'ACTION_DESCRIPTIONS',
    'ACTION_ICONS',
    'MODEL_REPO',
    'MODEL_FILENAME',
    'MODEL_DIR',
]
