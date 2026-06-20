"""Attachment download/view/delete routes.

Extracted from the entries.py split (Step B-I).
"""
from io import BytesIO
import os

import sqlcipher3 as sqlite3
from flask import send_file
from core.encryption import decrypt_file_to_bytes
from web.blueprints.entries.common import entries_bp, get_db, resolve_attachment_path


_INLINE_SAFE_MIMETYPES = {
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.gif': 'image/gif',
    '.webp': 'image/webp',
    '.pdf': 'application/pdf',
    '.txt': 'text/plain',
}


@entries_bp.route('/attachment/<int:attachment_id>/download')
def download_attachment(attachment_id):
    """Download an attachment file."""
    db = get_db()
    conn = db.connect()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM attachments WHERE id = ?", (attachment_id,))
    attachment = cursor.fetchone()
    
    if not attachment:
        return "Attachment not found", 404
    
    # Resolve filepath (handles both absolute and relative paths)
    filepath = resolve_attachment_path(attachment['filepath'])
    
    # Check file exists
    if not os.path.exists(filepath):
        return "Attachment file is missing from disk", 404
    
    # Decrypt file if database is encrypted
    if db.password:
        try:
            decrypted = decrypt_file_to_bytes(filepath, db.password)
        except Exception as e:
            return f"Cannot read attachment: file may be corrupted ({type(e).__name__})", 500
        response = send_file(
            BytesIO(decrypted),
            as_attachment=True,
            download_name=attachment['filename']
        )
        # Prevent browser from caching decrypted content to disk
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        return response
    else:
        return send_file(filepath, 
                         as_attachment=True, 
                         download_name=attachment['filename'])


@entries_bp.route('/attachment/<int:attachment_id>/view')
def view_attachment(attachment_id):
    """View an attachment file in browser.

    Inline rendering is only allowed for a safe allowlist of types
    (images, PDF, plain text); everything else is served as a download.
    """
    db = get_db()
    conn = db.connect()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM attachments WHERE id = ?", (attachment_id,))
    attachment = cursor.fetchone()

    if not attachment:
        return "Attachment not found", 404

    # Resolve filepath (handles both absolute and relative paths)
    filepath = resolve_attachment_path(attachment['filepath'])

    # Check file exists
    if not os.path.exists(filepath):
        return "Attachment file is missing from disk", 404

    # Decide inline vs. download from the stored filename's extension (L17)
    ext = os.path.splitext(attachment['filename'] or '')[1].lower()
    inline_mimetype = _INLINE_SAFE_MIMETYPES.get(ext)
    serve_inline = inline_mimetype is not None

    # Decrypt file if database is encrypted
    if db.password:
        try:
            decrypted = decrypt_file_to_bytes(filepath, db.password)
        except Exception as e:
            return f"Cannot read attachment: file may be corrupted ({type(e).__name__})", 500
        if serve_inline:
            mimetype = inline_mimetype
        else:
            # Download-only: never let the browser render it in-origin
            import mimetypes
            mimetype = mimetypes.guess_type(attachment['filename'])[0] or 'application/octet-stream'
        response = send_file(
            BytesIO(decrypted),
            as_attachment=not serve_inline,
            download_name=attachment['filename'],
            mimetype=mimetype
        )
        # Prevent browser from caching decrypted content to disk
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        return response
    else:
        if serve_inline:
            return send_file(filepath, as_attachment=False,
                             download_name=attachment['filename'],
                             mimetype=inline_mimetype)
        return send_file(filepath, as_attachment=True,
                         download_name=attachment['filename'])


@entries_bp.route('/attachment/<int:attachment_id>/delete', methods=['POST'])
def delete_attachment(attachment_id):
    """Delete an attachment file and database record."""
    db = get_db()
    conn = db.connect()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM attachments WHERE id = ?", (attachment_id,))
    attachment = cursor.fetchone()
    
    if not attachment:
        return "Attachment not found", 404
    
    cursor.execute("SELECT * FROM entries WHERE id = ?", (attachment['entry_id'],))
    entry = cursor.fetchone()
    
    # Resolve filepath for later deletion
    filepath = resolve_attachment_path(attachment['filepath'])
    filename = attachment['filename']
    entry_id = attachment['entry_id']
    
    # Delete from database FIRST (so if this fails, file is still intact)
    cursor.execute("DELETE FROM attachments WHERE id = ?", (attachment_id,))
    conn.commit()
    
    # Now delete file from disk (if DB succeeded, safe to remove file)
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
    except OSError as e:
        # Log but don't fail - DB record is already gone, orphan file is acceptable
        print(f"[Attachment] Warning: Could not delete file {filepath}: {e}")
    
    # Add to edit history for any entry type that supports attachments
    if entry and entry['class'] in ('upload', 'communication', 'item'):
        change_desc = f"Deleted file: {filename}"
        db.add_to_edit_history(entry_id, change_desc)
    
    
    return '', 200
