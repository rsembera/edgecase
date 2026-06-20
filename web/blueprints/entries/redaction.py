"""Entry redaction routes.

Extracted from the entries.py split (Step B-I).
"""
from flask import render_template, request, redirect, url_for
from web.blueprints.entries.common import entries_bp, get_db, renumber_sessions


@entries_bp.route('/client/<int:client_id>/redact/<int:entry_id>', methods=['POST'])
def redact_entry(client_id, entry_id):
    """Perform redaction on a specific entry."""
    db = get_db()
    client = db.get_client(client_id)
    if not client:
        return "Client not found", 404
    
    # Verify entry belongs to this client
    entry = db.get_entry(entry_id)
    if not entry or entry['client_id'] != client_id:
        return "Entry not found", 404
    
    reason = request.form.get('reason', '').strip()
    if not reason:
        return "Redaction reason is required", 400
    
    # Check if this is a session (for renumbering after redaction)
    is_session = entry.get('class') == 'session'
    
    success = db.redact_entry(entry_id, reason)
    
    if not success:
        return "Entry cannot be redacted (not locked or invalid type)", 400
    
    # Renumber sessions if we redacted a session
    if is_session:
        renumber_sessions(client_id)
    
    return redirect(url_for('clients.client_file', client_id=client_id))


@entries_bp.route('/client/<int:client_id>/redacted/<int:entry_id>')
def view_redacted_entry(client_id, entry_id):
    """View metadata for a redacted entry (no content shown)."""
    db = get_db()
    client = db.get_client(client_id)
    if not client:
        return "Client not found", 404
    
    client['type'] = db.get_client_type(client['type_id'])
    
    entry = db.get_entry(entry_id)
    if not entry or entry['client_id'] != client_id:
        return "Entry not found", 404
    
    if not entry.get('is_redacted'):
        # Redirect to normal edit page if not redacted
        return redirect(url_for(f'entries.edit_{entry["class"]}', 
                                client_id=client_id, entry_id=entry_id))
    
    return render_template('view_redacted.html',
                          client=client,
                          entry=entry)
