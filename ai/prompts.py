"""
AI Scribe - Prompt Templates for Clinical Note Processing
Uses ChatML format compatible with Hermes 3.
"""

# System prompt for clinical note assistant
SYSTEM_PROMPT = """You are a clinical note assistant for a psychotherapist. You help transform session notes while maintaining professional clinical standards.

RULES:
- Never invent facts or add information not in the original notes
- Use third person (e.g., "Client reported..." not "You reported...")
- Maintain clinical terminology accurately
- Preserve all clinical observations and details
- Output ONLY the transformed text, no explanations or preamble"""

# Action-specific user prompts
PROMPTS = {
    'writeup': """Convert the following point-form session notes into professional clinical prose. Maintain clinical tone and preserve all details.

NOTES:
{text}

CLINICAL PROSE:""",

    'proofread': """Proofread and correct the following clinical notes. Fix spelling, grammar, and punctuation errors only. Do not change meaning or add content.

NOTES:
{text}

CORRECTED:""",

    'expand': """Expand the following clinical notes with more professional detail and clinical language. Do not invent new facts. Add appropriate clinical framing where the existing text implies it.

NOTES:
{text}

EXPANDED:""",

    'contract': """Condense the following clinical notes to be more concise while preserving all essential clinical information. Remove redundancy.

NOTES:
{text}

CONDENSED:""",
}

# Action labels for the UI
ACTION_LABELS = {
    'writeup': 'Write Up',
    'proofread': 'Proofread',
    'expand': 'Expand',
    'contract': 'Contract',
}

# Action descriptions for tooltips/help
ACTION_DESCRIPTIONS = {
    'writeup': 'Convert point-form notes to professional clinical prose',
    'proofread': 'Fix spelling, grammar, and punctuation',
    'expand': 'Add clinical detail and professional language',
    'contract': 'Make notes more concise while preserving essentials',
}

# Icons for each action (Lucide icon names)
ACTION_ICONS = {
    'writeup': 'file-text',
    'proofread': 'spell-check',
    'expand': 'maximize-2',
    'contract': 'minimize-2',
}


def build_prompt(action: str, text: str) -> str:
    """
    Build the user prompt for a given action and input text.
    
    Args:
        action: One of 'writeup', 'proofread', 'expand', 'contract'
        text: The clinical notes to process
    
    Returns:
        The formatted user prompt string
    """
    if action not in PROMPTS:
        raise ValueError(f"Unknown action: {action}. Must be one of: {list(PROMPTS.keys())}")
    
    return PROMPTS[action].format(text=text.strip())


def get_system_prompt() -> str:
    """Get the system prompt for clinical note processing."""
    return SYSTEM_PROMPT


def get_actions() -> list[dict]:
    """Get list of available actions with labels, descriptions, and icons."""
    return [
        {
            'id': action_id,
            'label': ACTION_LABELS[action_id],
            'description': ACTION_DESCRIPTIONS[action_id],
            'icon': ACTION_ICONS[action_id],
        }
        for action_id in PROMPTS.keys()
    ]
