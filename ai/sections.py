"""
AI Scribe - working through a long note in sections.

The model's context holds the prompt, the note and the rewritten note
together. On a 16 GB machine that context is 4096 tokens, so a note of more
than about 1,400 words cannot be proofread in one pass: the result came back
cut off mid-sentence. Doubling the context costs memory such a machine does
not have to spare (tried 2026-11-21), so a note that does not fit is split
and each section goes through on its own, with the same prompts.

Everything here is plain text arithmetic: no model, no database. The caller
supplies the token counter.
"""
import math
import re

# How much longer than its input each action's output is expected to run.
# Deliberately generous: an underestimate cuts a section short, an
# overestimate only makes the sections a little smaller.
EXPECTED_GROWTH = {
    'proofread': 1.1,
    'condense': 1.0,
    'writeup': 1.5,
    'expand': 2.0,
}
DEFAULT_GROWTH = 1.5

# Tokens kept free for the chat template's own markers and for counting error
# (sections are measured piece by piece, the model tokenizes them joined).
SAFETY_MARGIN = 64

# Where a note may be divided, best first: blank lines between paragraphs,
# line breaks (point-form notes), sentence ends, and as a last resort spaces.
_BREAKS = [
    re.compile(r'(\n[ \t]*\n\s*)'),
    re.compile(r'(\s*\n\s*)'),
    re.compile(r'((?<=[.!?])\s+)'),
    re.compile(r'(\s+)'),
]


def section_budget(action, n_ctx, max_tokens, overhead):
    """Largest note, in tokens, that one pass can take for this action.

    Two limits apply: the prompt (overhead + note) and the output must fit
    in the context together, and the output must fit in max_tokens.
    """
    growth = EXPECTED_GROWTH.get(action, DEFAULT_GROWTH)
    by_context = (n_ctx - overhead - SAFETY_MARGIN) / (1 + growth)
    by_output = max_tokens / growth
    return max(1, int(min(by_context, by_output)))


def _atoms(text, budget, count, level=0):
    """Cut text into (piece, separator_after) pairs, each piece within budget
    where the text allows, breaking at the gentlest place that works."""
    parts = _BREAKS[level].split(text)
    atoms = []
    for i in range(0, len(parts), 2):
        piece = parts[i]
        sep = parts[i + 1] if i + 1 < len(parts) else ''
        if not piece:
            # Leading separator, or two in a row: keep it with its neighbour.
            if atoms:
                atoms[-1] = (atoms[-1][0], atoms[-1][1] + sep)
            elif sep:
                atoms.append(('', sep))
            continue
        if count(piece) > budget and level + 1 < len(_BREAKS):
            inner = _atoms(piece, budget, count, level + 1)
            inner[-1] = (inner[-1][0], inner[-1][1] + sep)
            atoms.extend(inner)
        else:
            atoms.append((piece, sep))
    return atoms


def split_into_sections(text, budget, count):
    """Split text into sections of at most `budget` tokens.

    Returns [(section_text, separator_after), ...]. Joining every section
    with its separator gives back the text exactly; the last separator is
    ''. Text within budget comes back as a single section. Sections are
    kept to similar sizes so the last one is not a scrap.

    count: callable returning the token count of a string.
    """
    total = count(text)
    if total <= budget:
        return [(text, '')]

    atoms = [(piece, sep, count(piece)) for piece, sep in _atoms(text, budget, count)]
    target = math.ceil(sum(n for _, _, n in atoms) / math.ceil(total / budget))

    sections = []
    current, current_sep, size = '', '', 0
    for piece, sep, n in atoms:
        if current and (size + n > budget or size >= target):
            sections.append((current, current_sep))
            current, current_sep, size = '', '', 0
        current += current_sep + piece
        current_sep, size = sep, size + n
    sections.append((current, ''))
    return sections


def trim_stream(tokens):
    """Pass a token stream through without its leading and trailing
    whitespace, so sections can be joined by the note's own breaks."""
    started = False
    held = ''
    for token in tokens:
        if not started:
            token = token.lstrip()
            if not token:
                continue
            started = True
        body = token.rstrip()
        if body:
            yield held + body
            held = token[len(body):]
        else:
            held += token
