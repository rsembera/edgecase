"""
Shared utility functions for EdgeCase web application.
Reduces code duplication across blueprints.
"""

from datetime import datetime
from werkzeug.utils import secure_filename
import os
import time
import difflib
import calendar
from core.encryption import encrypt_file

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
        upload_dir = os.path.expanduser(f'~/edgecase/attachments/{client_id}/{entry_id}')
    else:
        upload_dir = os.path.expanduser(f'~/edgecase/attachments/ledger/{entry_id}')
    
    os.makedirs(upload_dir, exist_ok=True)
    
    saved_files = []
    for i, file in enumerate(files):
        if file and file.filename:
            filename = secure_filename(file.filename)
            filepath = os.path.join(upload_dir, filename)
            
            # Save file to disk
            file.save(filepath)
            
            # Encrypt the file
            if db.password:
                encrypt_file(filepath, db.password)
            
            filesize = os.path.getsize(filepath)
            
            # Get description (use filename if not provided)
            description = descriptions[i] if i < len(descriptions) and descriptions[i] else filename
            
            # Save attachment record to database
            conn = db.connect()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO attachments (entry_id, filename, description, filepath, filesize, uploaded_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (entry_id, filename, description, filepath, filesize, int(time.time())))
            conn.commit()
            
            saved_files.append(filename)
    
    return saved_files


def delete_attachment_files(entry_id, client_id=None):
    """
    Delete all attachment files for an entry from disk.
    
    Args:
        entry_id: Entry ID
        client_id: Client ID if client entry, None if ledger entry
        
    Returns:
        bool: True if successful, False if error
    """
    import shutil
    
    try:
        if client_id:
            upload_dir = os.path.expanduser(f'~/edgecase/attachments/{client_id}/{entry_id}')
        else:
            upload_dir = os.path.expanduser(f'~/edgecase/attachments/ledger/{entry_id}')
        
        if os.path.exists(upload_dir):
            shutil.rmtree(upload_dir)
        
        return True
    except Exception as e:
        print(f"Error deleting attachment files: {e}")
        return False
