"""
Shared utility functions for EdgeCase web application.
Reduces code duplication across blueprints.
"""

from datetime import datetime
from werkzeug.utils import secure_filename
import os
import time


def parse_date_from_form(form_data):
    """
    Parse year/month/day from form dropdowns to Unix timestamp.
    
    Args:
        form_data: Form data dict with 'year', 'month', 'day' keys
        
    Returns:
        int: Unix timestamp or None if incomplete
    """
    year = form_data.get('year')
    month = form_data.get('month')
    day = form_data.get('day')
    
    if year and month and day:
        date_str = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        return int(datetime.strptime(date_str, '%Y-%m-%d').timestamp())
    return None


def get_today_date_parts():
    """
    Get today's date as year, month, day for form defaults.
    
    Returns:
        dict: {'today': 'YYYY-MM-DD', 'year': int, 'month': int, 'day': int}
    """
    today_dt = datetime.now()
    return {
        'today': today_dt.strftime('%Y-%m-%d'),
        'year': today_dt.year,
        'month': today_dt.month,
        'day': today_dt.day
    }


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
            conn.close()
            
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
