"""Communication entry routes.

Extracted from the entries.py split (Step B-I).
"""
from datetime import datetime

from flask import render_template, request, redirect, url_for
from web.utils import parse_date_from_form, get_today_date_parts, save_uploaded_files
from web.blueprints.entries.common import entries_bp, get_db


@entries_bp.route('/client/<int:client_id>/communication', methods=['GET', 'POST'])
def create_communication(client_id):
    """Create new communication entry."""
    db = get_db()
    client = db.get_client(client_id)
    if not client:
        return "Client not found", 404
    
    client_type = db.get_client_type(client['type_id'])
    
    if request.method == 'POST':
        comm_date_timestamp = parse_date_from_form(request.form)
        
        comm_data = {
            'client_id': client_id,
            'class': 'communication',
            'description': request.form['description'],
            'comm_recipient': request.form['recipient'],
            'comm_type': request.form['comm_type'],
            'comm_date': comm_date_timestamp,
            'comm_time': request.form.get('comm_time', ''),
            'content': request.form['content']
        }
        
        entry_id = db.add_entry(comm_data)
        
        # Handle file uploads
        files = request.files.getlist('files[]')
        descriptions = request.form.getlist('file_descriptions[]')
        save_uploaded_files(files, descriptions, entry_id, db, client_id)
        
        db.lock_entry(entry_id)
        
        return redirect(url_for('clients.client_file', client_id=client_id))
    
    # GET - show form
    date_parts = get_today_date_parts()

    return render_template('entry_forms/communication.html',
                        client=client,
                        client_type=client_type,
                        **date_parts,
                        is_edit=False)


@entries_bp.route('/client/<int:client_id>/communication/<int:entry_id>', methods=['GET', 'POST'])
def edit_communication(client_id, entry_id):
    """Edit existing communication entry."""
    db = get_db()
    client = db.get_client(client_id)
    if not client:
        return "Client not found", 404
    
    client_type = db.get_client_type(client['type_id'])
    communication = db.get_entry(entry_id)
    
    # Verify entry belongs to this client (CODE_REVIEW M6)
    if not communication or communication['class'] != 'communication' or communication['client_id'] != client_id:
        return "Communication not found", 404
    
    # Redirect to redacted view if this entry has been redacted
    if communication.get('is_redacted'):
        return redirect(url_for('entries.view_redacted_entry', 
                                client_id=client_id, entry_id=entry_id))
    
    if request.method == 'POST':
        # Get the old communication data for comparison
        old_comm = communication.copy()
        
        comm_date_timestamp = parse_date_from_form(request.form)
        
        # Prepare updated communication data
        comm_data = {
            'description': request.form['description'],
            'comm_recipient': request.form['recipient'],
            'comm_type': request.form['comm_type'],
            'comm_date': comm_date_timestamp,
            'comm_time': request.form.get('comm_time', ''),
            'content': request.form['content']
        }
        
        # Check if entry is locked - if so, log changes to edit history
        if db.is_entry_locked(entry_id):
            changes = []
            
            # Description (with smart word-level diff)
            if old_comm.get('description') != comm_data.get('description'):
                from web.utils import generate_content_diff
                
                old_desc = old_comm.get('description') or ''
                new_desc = comm_data.get('description') or ''
                
                if old_desc and new_desc:
                    diff_text = generate_content_diff(old_desc, new_desc, max_length=150)
                    changes.append(f"Description: {diff_text}")
                elif old_desc:
                    changes.append("Description: Cleared")
                else:
                    changes.append("Description: Added")
            
            # Recipient
            if old_comm.get('comm_recipient') != comm_data.get('comm_recipient'):
                changes.append(f"Recipient: {old_comm.get('comm_recipient')} → {comm_data.get('comm_recipient')}")
            
            # Type
            if old_comm.get('comm_type') != comm_data.get('comm_type'):
                changes.append(f"Type: {old_comm.get('comm_type')} → {comm_data.get('comm_type')}")
            
            # Date - compare just the date portion, not full timestamp
            old_date_str = datetime.fromtimestamp(old_comm['comm_date']).strftime('%Y-%m-%d') if old_comm.get('comm_date') else 'None'
            new_date_str = datetime.fromtimestamp(comm_date_timestamp).strftime('%Y-%m-%d') if comm_date_timestamp else 'None'
            if old_date_str != new_date_str:
                changes.append(f"Date: {old_date_str} → {new_date_str}")
            
            # Time
            if old_comm.get('comm_time') != comm_data.get('comm_time'):
                old_time = old_comm.get('comm_time') or 'None'
                new_time = comm_data.get('comm_time') or 'None'
                changes.append(f"Time: {old_time} → {new_time}")
            
            # Content (with smart word-level diff) - normalize line endings
            old_content_normalized = (old_comm.get('content') or '').replace('\r\n', '\n').strip()
            new_content_normalized = (comm_data.get('content') or '').replace('\r\n', '\n').strip()
            if old_content_normalized != new_content_normalized:
                from web.utils import generate_content_diff
                
                if old_content_normalized and new_content_normalized:
                    diff_text = generate_content_diff(old_content_normalized, new_content_normalized)
                    changes.append(f"Content: {diff_text}")
                elif old_content_normalized:
                    changes.append("Content: Cleared")
                else:
                    changes.append("Content: Added")
            
            if changes:
                change_desc = "; ".join(changes)
                db.add_to_edit_history(entry_id, change_desc)
        
        # Handle file uploads
        files = request.files.getlist('files[]')
        descriptions = request.form.getlist('file_descriptions[]')
        added_files = save_uploaded_files(files, descriptions, entry_id, db, client_id)
        
        # Track file additions in edit history
        if added_files and db.is_entry_locked(entry_id):
            file_list = ', '.join(added_files)
            db.add_to_edit_history(entry_id, f"Added files: {file_list}")
        
        # Update the existing communication
        db.update_entry(entry_id, comm_data, allow_locked=True)
        
        return redirect(url_for('clients.client_file', client_id=client_id))
    
    # GET - show form with existing data
    
    # Get all communications for this client (ordered by date, then by ID)
    all_communications = db.get_client_entries(client_id, 'communication')
    # Filter out communications without dates
    dated_communications = [c for c in all_communications if c.get('comm_date')]
    # Sort by date (newest first) to match Client File display
    dated_communications.sort(key=lambda c: (c['comm_date'], c['created_at']), reverse=True)
    
    # Find current communication index
    current_index = None
    for i, c in enumerate(dated_communications):
        if c['id'] == entry_id:
            current_index = i
            break
    
    # Determine prev/next communication IDs
    # Since sorted newest-first (reverse=True):
    # - "Previous" (older) is at higher index (further down the list)
    # - "Next" (newer) is at lower index (further up the list)
    prev_comm_id = dated_communications[current_index + 1]['id'] if current_index is not None and current_index < len(dated_communications) - 1 else None
    next_comm_id = dated_communications[current_index - 1]['id'] if current_index and current_index > 0 else None
    
    # Parse communication date into year, month, day for dropdowns
    comm_year = None
    comm_month = None
    comm_day = None
    if communication.get('comm_date'):
        comm_dt = datetime.fromtimestamp(communication['comm_date'])
        comm_year = comm_dt.year
        comm_month = comm_dt.month
        comm_day = comm_dt.day
    
    # Get lock status and edit history
    is_locked = db.is_entry_locked(entry_id)
    edit_history = db.get_edit_history(entry_id) if is_locked else []
    
    # Get attachments for this entry
    attachments = db.get_attachments(entry_id)
    
    return render_template('entry_forms/communication.html',
                        client=client,
                        client_type=client_type,
                        entry=communication,
                        attachments=attachments, 
                        comm_year=comm_year,
                        comm_month=comm_month,
                        comm_day=comm_day,
                        comm_time=communication.get('comm_time', ''),
                        description=communication.get('description', ''),
                        comm_recipient=communication.get('comm_recipient', ''),
                        comm_type=communication.get('comm_type', ''),
                        content=communication.get('content', ''),
                        is_edit=True,
                        is_locked=is_locked,
                        edit_history=edit_history,
                        prev_comm_id=prev_comm_id,
                        next_comm_id=next_comm_id)
