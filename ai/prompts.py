"""
AI Scribe - Prompt Templates for Clinical Note Processing
Model-agnostic message content; formatting is handled by the GGUF's
embedded chat template (currently Gemma 4 12B QAT).
"""

# System prompt for clinical note assistant
SYSTEM_PROMPT = """You are a clinical note assistant for a psychotherapist. You help transform session notes while maintaining professional clinical standards.

RULES:
- Never invent facts or add information not in the original notes
- Refer to the client in third person (e.g. "Client reported..." not "You reported...")
- Preserve the clinician's own first-person voice exactly. When the notes say "I", "me", or "my", that is the clinician writing about themselves - never rewrite these as "the clinician", "the therapist", "the writer", or "they"
- Maintain clinical terminology accurately
- Preserve all clinical observations and details
- Preserve the original spelling conventions (British, Canadian, American, etc.) - do not convert spellings like "colour" to "color" or vice versa
- Preserve the writer's punctuation and style conventions. Regional style differences are not errors, in either direction. Critical examples: if the notes say "e.g. paced breathing", output exactly "e.g. paced breathing"; if the notes say "e.g., paced breathing", output exactly "e.g., paced breathing". Both are correct styles - never add the comma and never remove it. The same applies to "i.e." and to serial commas. Only correct punctuation that is unambiguously wrong in every English convention.
- Preserve the clinician's language choices, including profanity, slang, or colloquialisms. When a therapist includes such language in notes (whether quoting a client directly or describing what they said), it reflects clinical judgment about accurate documentation. Do not substitute euphemisms (e.g. do not change "shit" to "defecate" or "bullshit" to "expressed frustration").
- Output ONLY the transformed text, no explanations or preamble"""

# Action-specific user prompts
PROMPTS = {
    'writeup': """Convert the following point-form session notes into professional clinical prose. Maintain clinical tone and preserve all details.

NOTES:
{text}

CLINICAL PROSE:""",

    'proofread': """Proofread and correct the following clinical notes. Fix spelling, grammar, and punctuation errors only. Do not change meaning or add content. Preserve the writer's spelling and punctuation conventions exactly as written, including whether or not a comma follows "e.g." or "i.e.".

NOTES:
{text}

CORRECTED:""",

    'expand': """Expand the following clinical notes with more professional detail and clinical language. Do not invent new facts. Add appropriate clinical framing where the existing text implies it.

NOTES:
{text}

EXPANDED:""",

    'condense': """Condense the following clinical notes to be more concise while preserving all essential clinical information. Remove redundancy.

NOTES:
{text}

CONDENSED:""",
}

# Action labels for the UI
ACTION_LABELS = {
    'writeup': 'Write Up',
    'proofread': 'Proofread',
    'expand': 'Expand',
    'condense': 'Condense',
}

# Action descriptions for tooltips/help
ACTION_DESCRIPTIONS = {
    'writeup': 'Convert point-form notes to professional clinical prose',
    'proofread': 'Fix spelling, grammar, and punctuation',
    'expand': 'Add clinical detail and professional language',
    'condense': 'Make notes more concise while preserving essentials',
}

# Icons for each action (Lucide icon names)
ACTION_ICONS = {
    'writeup': 'file-text',
    'proofread': 'spell-check',
    'expand': 'maximize-2',
    'condense': 'minimize-2',
}


def build_prompt(action: str, text: str) -> str:
    """
    Build the user prompt for a given action and input text.
    
    Args:
        action: One of 'writeup', 'proofread', 'expand', 'condense'
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
