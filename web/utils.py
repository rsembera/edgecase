"""
Shared utility functions for EdgeCase web application.
Reduces code duplication across blueprints.
"""

from datetime import datetime
from werkzeug.utils import secure_filename
from pathlib import Path
import os
import time
import difflib
import calendar
import uuid
import sqlcipher3
from markupsafe import escape
from core.encryption import encrypt_file
from core.config import DATA_ROOT, ATTACHMENTS_DIR


def get_link_group_fees(db, client_id, include_duration=False):
    """Get per-format fee overrides from the link groups a client belongs to.

    Returns a dict keyed by link-group format, e.g.
    {'Couple': {'base': .., 'tax': .., 'total': ..[, 'duration': ..]}}.
    Groups without a format are skipped. Shared by the session/absence
    create and edit routes (CODE_REVIEW.md M13).

    Args:
        db: Database instance
        client_id: client whose link groups to look up
        include_duration: also include the group's session duration
            (defaulting to 50) — used by session forms but not absences.
    """
    link_group_fees = {}

    conn = db.connect()
    conn.row_factory = sqlcipher3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT cl.group_id, cl.member_base_fee, cl.member_tax_rate, cl.member_total_fee, lg.format, lg.session_duration
        FROM client_links cl
        JOIN link_groups lg ON cl.group_id = lg.id
        WHERE cl.client_id_1 = ?
    """, (client_id,))

    for row in cursor.fetchall():
        format_type = row['format']
        if format_type:  # Only if format is set
            fees = {
                'base': row['member_base_fee'] or 0,
                'tax': row['member_tax_rate'] or 0,
                'total': row['member_total_fee'] or 0
            }
            if include_duration:
                fees['duration'] = row['session_duration'] or 50
            link_group_fees[format_type] = fees

    return link_group_fees


def parse_date_from_form(form_data, year_key='year', month_key='month', day_key='day', date_key='date'):
    """Convert date form data to Unix timestamp.
    
    Accepts either:
    - Single 'date' field in YYYY-MM-DD format (from new pickers)
    - Separate year/month/day dropdowns (legacy forms)
    
    Automatically clamps invalid days (e.g., Nov 31 → Nov 30)."""
    
    # Check for single date field first (new picker format)
    date_str = form_data.get(date_key)
    if date_str:
        try:
            parts = date_str.split('-')
            if len(parts) == 3:
                year = int(parts[0])
                month = int(parts[1])
                day = int(parts[2])
                max_day = calendar.monthrange(year, month)[1]
                day = min(day, max_day)
                return int(datetime(year, month, day).timestamp())
        except (ValueError, IndexError):
            pass
    
    # Fall back to separate fields (legacy format)
    year = form_data.get(year_key)
    month = form_data.get(month_key)
    day = form_data.get(day_key)
    
    if year and month and day:
        year = int(year)
        month = int(month)
        day = int(day)
        # Clamp day to valid range for the month
        max_day = calendar.monthrange(year, month)[1]
        day = min(day, max_day)
        return int(datetime(year, month, day).timestamp())
    return None


def get_today_date_parts():
    """
    Get today's date as year, month, day for form defaults.
    
    Returns:
        dict: {'today': 'YYYY-MM-DD', 'today_year': int, 'today_month': int, 'today_day': int}
    """
    today_dt = datetime.now()
    return {
        'today': today_dt.strftime('%Y-%m-%d'),
        'today_year': today_dt.year,
        'today_month': today_dt.month,
        'today_day': today_dt.day
    }


def generate_content_diff(old_content, new_content, max_length=500):
    """
    Generate smart diff for content changes.
    Shows deletions with <del> tags and additions with <strong> tags.
    Only changes are highlighted - unchanged text is plain.
    
    Args:
        old_content: Original content string
        new_content: New content string
        max_length: Maximum character length before truncation (default 500)
        
    Returns:
        str: Formatted diff string with HTML tags
    """
    # Handle empty cases
    if not old_content and not new_content:
        return ""
    
    # Normalize whitespace and line endings
    old_content = ' '.join(old_content.split())
    new_content = ' '.join(new_content.split())

    # HTML-escape user content BEFORE any <del>/<strong> wrapping below
    # (CODE_REVIEW M17). The diff output is rendered with |safe in the
    # edit-history templates, so unescaped note text containing markup
    # would corrupt the display or execute in-origin. Plain text escapes
    # to itself; only the diff tags generated here remain real HTML.
    old_content = str(escape(old_content))
    new_content = str(escape(new_content))
    
    if not old_content:
        # Everything is new
        preview = new_content[:max_length] + '...' if len(new_content) > max_length else new_content
        return f"<strong>{preview}</strong>"
    
    if not new_content:
        # Everything deleted
        preview = old_content[:max_length] + '...' if len(old_content) > max_length else old_content
        return f"<del>{preview}</del>"
    
    # Use word-level diff
    old_words = old_content.split()
    new_words = new_content.split()
    
    return _word_level_diff_with_context(old_words, new_words, max_length)


def generate_full_content_diff(old_content, new_content):
    """
    Full-text word-level diff with no truncation or context elision.

    Unlike generate_content_diff (which abbreviates unchanged runs to fit
    edit-history rows), this returns the COMPLETE text in reading order
    with deletions (<del>) and insertions (<strong>) marked in place.
    Built for the AI Scribe change-review overlay, where the question is
    "what did the model touch?" and the surrounding context must stay
    readable. Same word-level SequenceMatcher core and the same
    escape-before-tagging rule (CODE_REVIEW M17) as the history diff.

    Returns:
        str: HTML-safe diff string containing only <del>/<strong> tags.
    """
    old_content = ' '.join((old_content or '').split())
    new_content = ' '.join((new_content or '').split())

    if not old_content and not new_content:
        return ""

    old_content = str(escape(old_content))
    new_content = str(escape(new_content))

    if not old_content:
        return f"<strong>{new_content}</strong>"
    if not new_content:
        return f"<del>{old_content}</del>"

    old_words = old_content.split()
    new_words = new_content.split()
    matcher = difflib.SequenceMatcher(None, old_words, new_words)
    parts = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            parts.extend(new_words[j1:j2])
        elif tag == 'delete':
            parts.append(f"<del>{' '.join(old_words[i1:i2])}</del>")
        elif tag == 'insert':
            parts.append(f"<strong>{' '.join(new_words[j1:j2])}</strong>")
        elif tag == 'replace':
            parts.append(
                f"<del>{' '.join(old_words[i1:i2])}</del> "
                f"<strong>{' '.join(new_words[j1:j2])}</strong>"
            )
    return ' '.join(parts)


def _word_level_diff_with_context(old_words, new_words, max_length=None):
    """Helper function for word-level diff with context limiting."""
    matcher = difflib.SequenceMatcher(None, old_words, new_words)
    opcodes = list(matcher.get_opcodes())
    formatted_parts = []
    
    # Count how many non-equal operations we have
    change_count = sum(1 for tag, _, _, _, _ in opcodes if tag != 'equal')
    
    for idx, (tag, i1, i2, j1, j2) in enumerate(opcodes):
        is_first = (idx == 0)
        is_last = (idx == len(opcodes) - 1)
        
        if tag == 'equal':
            equal_words = old_words[i1:i2]
            
            if len(equal_words) <= 5:
                # Short: show all
                formatted_parts.extend(equal_words)
            elif is_first and change_count > 0:
                # Beginning with changes after: show "..." and last 3 words
                formatted_parts.append('...')
                formatted_parts.extend(equal_words[-3:])
            elif is_last and change_count > 0:
                # End with changes before: show first 3 words and "..."
                formatted_parts.extend(equal_words[:3])
                formatted_parts.append('...')
            else:
                # Middle: show first 3, [...], last 3
                formatted_parts.extend(equal_words[:3])
                formatted_parts.append('[...]')
                formatted_parts.extend(equal_words[-3:])
        elif tag == 'delete':
            deleted = ' '.join(old_words[i1:i2])
            formatted_parts.append(f'<del>{deleted}</del>')
        elif tag == 'insert':
            inserted = ' '.join(new_words[j1:j2])
            formatted_parts.append(f'<strong>{inserted}</strong>')
        elif tag == 'replace':
            deleted = ' '.join(old_words[i1:i2])
            inserted = ' '.join(new_words[j1:j2])
            formatted_parts.append(f'<del>{deleted}</del> <strong>{inserted}</strong>')
    
    result = ' '.join(formatted_parts)
    
    if max_length and len(result) > max_length:
        # Find a safe truncation point that doesn't break HTML tags
        truncate_at = max_length
        
        # First, try to find a space to truncate at
        space_pos = result[:max_length].rfind(' ')
        if space_pos > max_length // 2:
            truncate_at = space_pos
        
        # Check if we're inside an HTML tag and adjust
        result_truncated = result[:truncate_at]
        
        # Count unclosed tags
        open_strong = result_truncated.count('<strong>') - result_truncated.count('</strong>')
        open_del = result_truncated.count('<del>') - result_truncated.count('</del>')
        
        # Close any unclosed tags
        result_truncated += '...'
        if open_strong > 0:
            result_truncated += '</strong>'
        if open_del > 0:
            result_truncated += '</del>'
        
        result = result_truncated
    
    return result


def save_uploaded_files(files, descriptions, entry_id, db, client_id=None):
    """
    Save uploaded files and create attachment records.
    Used by both client entries and ledger entries.
    
    Args:
        files: List of FileStorage objects from request.files.getlist('files[]')
        descriptions: List of description strings from request.form.getlist('file_descriptions[]')
        entry_id: Entry ID to attach files to
        db: Database instance (for saving attachment records)
        client_id: Client ID if client entry, None if ledger entry
        
    Returns:
        list: Filenames of saved files (empty list if no files)
    """
    if not files or not files[0].filename:
        return []
    
    # Determine upload directory based on entry type
    if client_id:
        upload_dir = ATTACHMENTS_DIR / str(client_id) / str(entry_id)
    else:
        upload_dir = ATTACHMENTS_DIR / 'ledger' / str(entry_id)
    
    os.makedirs(upload_dir, exist_ok=True)
    
    saved_files = []
    for i, file in enumerate(files):
        if file and file.filename:
            # Keep original filename for display/download
            original_filename = secure_filename(file.filename)
            
            # Use UUID for stored filename (privacy: no client info in filesystem)
            stored_filename = f"{uuid.uuid4()}.enc"
            filepath = os.path.join(upload_dir, stored_filename)
            
            # Save file to disk and encrypt
            try:
                file.save(filepath)
                
                if db.password:
                    encrypt_file(filepath, db.password)
            except (IOError, OSError) as e:
                # Clean up partial file if it exists
                if os.path.exists(filepath):
                    try:
                        os.remove(filepath)
                    except OSError:
                        pass
                raise IOError(f"Failed to save file '{original_filename}': {e}")
            
            filesize = os.path.getsize(filepath)
            
            # Get description (use filename if not provided)
            description = descriptions[i] if i < len(descriptions) and descriptions[i] else original_filename
            
            # Store relative path (from data root) for portability
            relative_filepath = str(Path(filepath).relative_to(DATA_ROOT))
            
            # Save attachment record to database
            conn = db.connect()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO attachments (entry_id, filename, description, filepath, filesize, uploaded_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (entry_id, original_filename, description, relative_filepath, filesize, int(time.time())))
            conn.commit()
            
            saved_files.append(original_filename)
    
    return saved_files
