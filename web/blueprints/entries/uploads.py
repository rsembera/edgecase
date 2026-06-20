"""Upload entry routes.

Extracted from the entries.py split (Step B-I).
"""
from datetime import datetime

from flask import render_template, request, redirect, url_for
from web.utils import parse_date_from_form, get_today_date_parts, save_uploaded_files
from web.blueprints.entries.common import entries_bp, get_db


@entries_bp.route('/client/<int:client_id>/upload', methods=['GET', 'POST'])
def create_upload(client_id):
    """Create new upload entry with file attachments."""
    db = get_db()
    client = db.get_client(client_id)
    if not client:
        return "Client not found", 404
    
    client_type = db.get_client_type(client['type_id'])
    
    if request.method == 'POST':
        # Parse date
        upload_date_timestamp = parse_date_from_form(request.form)
        
        upload_data = {
            'client_id': client_id,
            'class': 'upload',
            'description': request.form['description'],
            'upload_date': upload_date_timestamp,
            'upload_time': request.form.get('upload_time', ''),
            'content': request.form.get('content', '')
        }
        
        entry_id = db.add_entry(upload_data)
        
        # Handle file uploads
        files = request.files.getlist('files[]')
        descriptions = request.form.getlist('file_descriptions[]')
        save_uploaded_files(files, descriptions, entry_id, db, client_id=client_id)

        return redirect(url_for('clients.client_file', client_id=client_id))
    
    # GET - show form
    date_parts = get_today_date_parts()

    return render_template('entry_forms/upload.html',
                        client=client,
                        client_type=client_type,
                        **date_parts,
                        is_edit=False)


@entries_bp.route('/client/<int:client_id>/upload/<int:entry_id>', methods=['GET', 'POST'])
def edit_upload(client_id, entry_id):
    """Edit existing upload entry."""
    db = get_db()
    client = db.get_client(client_id)
    if not client:
        return "Client not found", 404
    
    client_type = db.get_client_type(client['type_id'])
    upload = db.get_entry(entry_id)
    
    # Verify entry belongs to this client (CODE_REVIEW M6)
    if not upload or upload['class'] != 'upload' or upload['client_id'] != client_id:
        return "Upload not found", 404
    
    if request.method == 'POST':
        old_upload = upload.copy()
        
        # Parse date
        upload_date_timestamp = parse_date_from_form(request.form)
        
        upload_data = {
            'description': request.form['description'],
            'upload_date': upload_date_timestamp,
            'upload_time': request.form.get('upload_time', ''),
            'content': request.form.get('content', '')
        }
        
        # Handle new file uploads
        files = request.files.getlist('files[]')
        descriptions = request.form.getlist('file_descriptions[]')
        
        added_files = save_uploaded_files(files, descriptions, entry_id, db, client_id=client_id)

        if added_files:
            changes = []
            changes.append(f"Added files: {', '.join(added_files)}")
            db.add_to_edit_history(entry_id, "; ".join(changes))

        db.update_entry(entry_id, upload_data, allow_locked=True)

        return redirect(url_for('clients.client_file', client_id=client_id))
    
    # GET - show form
    upload_year = None
    upload_month = None
    upload_day = None
    if upload.get('upload_date'):
        upload_dt = datetime.fromtimestamp(upload['upload_date'])
        upload_year = upload_dt.year
        upload_month = upload_dt.month
        upload_day = upload_dt.day
    
    attachments = db.get_attachments(entry_id)
    edit_history = db.get_edit_history(entry_id)
    
    return render_template('entry_forms/upload.html',
                        client=client,
                        client_type=client_type,
                        entry=upload,
                        upload_year=upload_year,
                        upload_month=upload_month,
                        upload_day=upload_day,
                        attachments=attachments,
                        is_edit=True,
                        is_locked=False,
                        edit_history=edit_history)
