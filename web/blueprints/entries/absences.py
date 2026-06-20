"""Absence entry routes.

Extracted from the entries.py split (Step B-I).
"""
from datetime import datetime

from flask import render_template, request, redirect, url_for
from web.utils import get_link_group_fees
from web.blueprints.entries.common import entries_bp, get_db, safe_float, safe_money


@entries_bp.route('/client/<int:client_id>/absence', methods=['GET', 'POST'])
def create_absence(client_id):
    """Create a new absence entry for a client."""
    db = get_db()
    client = db.get_client(client_id)
    if not client:
        return "Client not found", 404
    
    client_type = db.get_client_type(client['type_id'])
    
    if request.method == 'POST':
        absence_date_str = request.form.get('date')
        absence_date_timestamp = None
        if absence_date_str:
            try:
                date_obj = datetime.strptime(absence_date_str, '%Y-%m-%d')
            except ValueError:
                # Malformed date should be a validation error, not a 500 (CODE_REVIEW L12)
                return "Invalid date: please enter the absence date as YYYY-MM-DD.", 400
            absence_date_timestamp = int(date_obj.timestamp())
        
        absence_data = {
            'client_id': client_id,
            'class': 'absence',
            'description': request.form['description'],
            'format': request.form.get('format', ''),
            'absence_date': absence_date_timestamp,
            'absence_time': request.form.get('absence_time', ''),
            'base_fee': safe_money(request.form.get('base_fee'), 0),
            'tax_rate': safe_float(request.form.get('tax_rate'), 0),
            'fee': safe_money(request.form.get('fee'), 0),
            'content': request.form.get('content', '')
        }
        
        entry_id = db.add_entry(absence_data)
        db.lock_entry(entry_id)
        
        return redirect(url_for('clients.client_file', client_id=client_id))
    
    # GET - show form
    from datetime import date
    today = date.today().strftime('%Y-%m-%d')
    
    # Get profile for fee information
    profile = db.get_profile_entry(client_id)
    
    # Build profile fees dict
    if profile:
        profile_fees = {
            'base': profile.get('session_base') or 0,
            'tax': profile.get('session_tax_rate') or 0,
            'total': profile.get('session_total') or 0
        }
    else:
        profile_fees = {
            'base': 0,
            'tax': 0,
            'total': 0
        }
    
    # Get link group fees
    link_group_fees = get_link_group_fees(db, client_id)

    return render_template('entry_forms/absence.html',
                         client=client,
                         client_type=client_type,
                         today=today,
                         profile_fees=profile_fees,
                         link_group_fees=link_group_fees)


@entries_bp.route('/client/<int:client_id>/absence/<int:entry_id>', methods=['GET', 'POST'])
def edit_absence(client_id, entry_id):
    """Edit existing absence entry."""
    db = get_db()
    client = db.get_client(client_id)
    if not client:
        return "Client not found", 404
    
    client_type = db.get_client_type(client['type_id'])
    absence = db.get_entry(entry_id)
    
    # Verify entry belongs to this client (CODE_REVIEW M6)
    if not absence or absence['class'] != 'absence' or absence['client_id'] != client_id:
        return "Absence not found", 404
    
    # Redirect to redacted view if this entry has been redacted
    if absence.get('is_redacted'):
        return redirect(url_for('entries.view_redacted_entry', 
                                client_id=client_id, entry_id=entry_id))
    
    if request.method == 'POST':
        # Get the old absence data for comparison
        old_absence = absence.copy()
        
        # Check if entry is billed (has statement_id) - billing fields cannot be changed
        is_billed = absence.get('statement_id') is not None
        
        # Convert date string to Unix timestamp
        absence_date_str = request.form.get('date')
        absence_date_timestamp = None
        if absence_date_str:
            try:
                date_obj = datetime.strptime(absence_date_str, '%Y-%m-%d')
            except ValueError:
                # Malformed date should be a validation error, not a 500 (CODE_REVIEW L12)
                return "Invalid date: please enter the absence date as YYYY-MM-DD.", 400
            absence_date_timestamp = int(date_obj.timestamp())
        
        # Prepare updated absence data - preserve billing fields if billed
        absence_data = {
            'description': request.form['description'],
            'format': old_absence.get('format') if is_billed else request.form.get('format', ''),
            'absence_date': old_absence.get('absence_date') if is_billed else absence_date_timestamp,
            'absence_time': request.form.get('absence_time', ''),
            'base_fee': old_absence.get('base_fee') if is_billed else safe_money(request.form.get('base_fee'), 0),
            'tax_rate': old_absence.get('tax_rate') if is_billed else safe_float(request.form.get('tax_rate'), 0),
            'fee': old_absence.get('fee') if is_billed else safe_money(request.form.get('fee'), 0),
            'content': request.form.get('content', '')
        }
        
        # Check if entry is locked - if so, log changes to edit history
        if db.is_entry_locked(entry_id):
            changes = []
            
            # Description (with smart word-level diff)
            if old_absence.get('description') != absence_data.get('description'):
                from web.utils import generate_content_diff
                
                old_desc = old_absence.get('description') or ''
                new_desc = absence_data.get('description') or ''
                
                if old_desc and new_desc:
                    diff_text = generate_content_diff(old_desc, new_desc, max_length=150)
                    changes.append(f"Description: {diff_text}")
                elif old_desc:
                    changes.append("Description: Cleared")
                else:
                    changes.append("Description: Added")
            
            # Date
            if old_absence.get('absence_date') != absence_date_timestamp:
                old_date = datetime.fromtimestamp(old_absence['absence_date']).strftime('%Y-%m-%d') if old_absence.get('absence_date') else 'None'
                new_date = datetime.fromtimestamp(absence_date_timestamp).strftime('%Y-%m-%d') if absence_date_timestamp else 'None'
                changes.append(f"Date: {old_date} → {new_date}")
            
            # Time
            if old_absence.get('absence_time') != absence_data.get('absence_time'):
                old_time = old_absence.get('absence_time') or 'None'
                new_time = absence_data.get('absence_time') or 'None'
                changes.append(f"Time: {old_time} → {new_time}")
            
            # Fee breakdown
            if old_absence.get('base_fee') != absence_data.get('base_fee'):
                old_base = old_absence.get('base_fee')
                new_base = absence_data.get('base_fee')
                old_str = f"${old_base:.2f}" if old_base is not None else "None"
                new_str = f"${new_base:.2f}" if new_base is not None else "None"
                changes.append(f"Base Price: {old_str} → {new_str}")
            
            if old_absence.get('tax_rate') != absence_data.get('tax_rate'):
                old_tax = old_absence.get('tax_rate')
                new_tax = absence_data.get('tax_rate')
                old_str = f"{old_tax:.2f}%" if old_tax is not None else "None"
                new_str = f"{new_tax:.2f}%" if new_tax is not None else "None"
                changes.append(f"Tax Rate: {old_str} → {new_str}")
            
            if old_absence.get('fee') != absence_data.get('fee'):
                old_fee = old_absence.get('fee')
                new_fee = absence_data.get('fee')
                old_str = f"${old_fee:.2f}" if old_fee is not None else "None"
                new_str = f"${new_fee:.2f}" if new_fee is not None else "None"
                changes.append(f"Total Fee: {old_str} → {new_str}")
            
            # Content (with smart word-level diff)
            if old_absence.get('content') != absence_data.get('content'):
                from web.utils import generate_content_diff
                
                old_content = old_absence.get('content') or ''
                new_content = absence_data.get('content') or ''
                
                if old_content and new_content:
                    diff_text = generate_content_diff(old_content, new_content)
                    changes.append(f"Content: {diff_text}")
                elif old_content:
                    changes.append("Content: Cleared")
                else:
                    changes.append("Content: Added")
            
            if changes:
                change_desc = "; ".join(changes)
                db.add_to_edit_history(entry_id, change_desc)
        
        # Save updated absence
        db.update_entry(entry_id, absence_data, allow_locked=True)
        
        return redirect(url_for('clients.client_file', client_id=client_id))
    
    # GET - show form with existing data
    # Convert timestamp back to date string
    absence_date = datetime.fromtimestamp(absence['absence_date']).strftime('%Y-%m-%d') if absence.get('absence_date') else None
    
    # Get lock status and edit history
    is_locked = db.is_entry_locked(entry_id)
    edit_history = db.get_edit_history(entry_id) if is_locked else []
    
    # Get profile for fee information
    profile = db.get_profile_entry(client_id)
    
    # Build profile fees dict
    if profile:
        profile_fees = {
            'base': profile.get('session_base') or 0,
            'tax': profile.get('session_tax_rate') or 0,
            'total': profile.get('session_total') or 0
        }
    else:
        profile_fees = {
            'base': 0,
            'tax': 0,
            'total': 0
        }
    
    # Get link group fees
    link_group_fees = get_link_group_fees(db, client_id)

    return render_template('entry_forms/absence.html',
                        client=client,
                        client_type=client_type,
                        entry=absence,
                        absence_date=absence_date,
                        is_edit=True,
                        is_locked=is_locked,
                        is_billed=absence.get('statement_id') is not None,
                        edit_history=edit_history,
                        profile_fees=profile_fees,
                        link_group_fees=link_group_fees)
