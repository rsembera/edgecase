"""Item entry routes.

Extracted from the entries.py split (Step B-I).
"""
from datetime import datetime
import time

from flask import render_template, request, redirect, url_for
from core.money import money_float
from web.utils import get_today_date_parts, save_uploaded_files
from web.blueprints.entries.common import entries_bp, get_db, safe_float, safe_money


@entries_bp.route('/client/<int:client_id>/item', methods=['GET', 'POST'])
def create_item(client_id):
    """Create a new item entry for a client."""
    db = get_db()
    client = db.get_client(client_id)
    if not client:
        return "Client not found", 404
    
    client_type = db.get_client_type(client['type_id'])
    profile = db.get_profile_entry(client_id)
    
    if request.method == 'POST':
        item_date_str = request.form.get('item_date')
        item_date_timestamp = None
        if item_date_str:
            try:
                item_date_timestamp = int(datetime.strptime(item_date_str, '%Y-%m-%d').timestamp())
            except ValueError:
                # Malformed date should be a validation error, not a 500 (CODE_REVIEW L12)
                return "Invalid date: please enter the item date as YYYY-MM-DD.", 400
        
        # Parse guardian amounts if provided
        g1_amount = request.form.get('guardian1_amount')
        g2_amount = request.form.get('guardian2_amount')
        
        # Parse guardian amounts - check for empty strings
        g1_parsed = money_float(g1_amount) if g1_amount and g1_amount.strip() else None
        g2_parsed = money_float(g2_amount) if g2_amount and g2_amount.strip() else None
        
        item_data = {
            'client_id': client_id,
            'class': 'item',
            'created_at': int(time.time()),
            'modified_at': int(time.time()),
            
            'description': request.form['description'],
            'item_date': item_date_timestamp,
            'item_time': request.form.get('item_time') or None,
            'base_price': safe_money(request.form.get('base_price'), 0),
            'tax_rate': safe_float(request.form.get('tax_rate'), 0),
            'fee': safe_money(request.form.get('fee'), 0),

            'guardian1_amount': g1_parsed,
            'guardian2_amount': g2_parsed,
            
            'content': request.form.get('content') or None,
        }
        
        entry_id = db.add_entry(item_data)
        
        # Handle file uploads
        files = request.files.getlist('files[]')
        descriptions = request.form.getlist('file_descriptions[]')
        save_uploaded_files(files, descriptions, entry_id, db, client_id)
        
        db.lock_entry(entry_id)
        
        return redirect(url_for('clients.client_file', client_id=client_id))
    
    # GET - show form
    date_parts = get_today_date_parts()

    return render_template('entry_forms/item.html',
                        client=client,
                        client_type=client_type,
                        profile=profile,
                        **date_parts,
                        is_edit=False)


@entries_bp.route('/client/<int:client_id>/item/<int:entry_id>', methods=['GET', 'POST'])
def edit_item(client_id, entry_id):
    """Edit existing item entry."""
    db = get_db()
    client = db.get_client(client_id)
    if not client:
        return "Client not found", 404
    
    client_type = db.get_client_type(client['type_id'])
    profile = db.get_profile_entry(client_id)
    item = db.get_entry(entry_id)
    
    # Verify entry belongs to this client (CODE_REVIEW M6)
    if not item or item['class'] != 'item' or item['client_id'] != client_id:
        return "Item not found", 404
    
    # Redirect to redacted view if this entry has been redacted
    if item.get('is_redacted'):
        return redirect(url_for('entries.view_redacted_entry', 
                                client_id=client_id, entry_id=entry_id))
    
    if request.method == 'POST':
        # Get the old item data for comparison
        old_item = item.copy()
        
        # Check if entry is billed (has statement_id) - billing fields cannot be changed
        is_billed = item.get('statement_id') is not None
        
        # Convert date string to Unix timestamp (optional for items)
        item_date_str = request.form.get('item_date')
        item_date_timestamp = None
        if item_date_str:
            try:
                date_obj = datetime.strptime(item_date_str, '%Y-%m-%d')
            except ValueError:
                # Malformed date should be a validation error, not a 500 (CODE_REVIEW L12)
                return "Invalid date: please enter the item date as YYYY-MM-DD.", 400
            item_date_timestamp = int(date_obj.timestamp())
        
        # Parse guardian amounts if provided
        g1_amount = request.form.get('guardian1_amount')
        g2_amount = request.form.get('guardian2_amount')
        
        # Prepare updated item data - preserve billing fields if billed
        item_data = {
            'description': request.form['description'],
            'item_date': old_item.get('item_date') if is_billed else item_date_timestamp,
            'item_time': request.form.get('item_time', ''),
            'base_price': old_item.get('base_price') if is_billed else safe_money(request.form.get('base_price')),
            'tax_rate': old_item.get('tax_rate') if is_billed else safe_float(request.form.get('tax_rate'), 0),
            'fee': old_item.get('fee') if is_billed else safe_float(request.form.get('fee'), 0),
            'guardian1_amount': old_item.get('guardian1_amount') if is_billed else safe_float(g1_amount),
            'guardian2_amount': old_item.get('guardian2_amount') if is_billed else safe_float(g2_amount),
            'content': request.form.get('content', '')
        }
        
        # Check if entry is locked - if so, log changes to edit history
        if db.is_entry_locked(entry_id):
            changes = []
            
            # Description (with smart word-level diff)
            if old_item.get('description') != item_data.get('description'):
                from web.utils import generate_content_diff
                
                old_desc = old_item.get('description') or ''
                new_desc = item_data.get('description') or ''
                
                if old_desc and new_desc:
                    diff_text = generate_content_diff(old_desc, new_desc, max_length=150)
                    changes.append(f"Description: {diff_text}")
                elif old_desc:
                    changes.append("Description: Cleared")
                else:
                    changes.append("Description: Added")
            
            # Date
            if old_item.get('item_date') != item_date_timestamp:
                old_date = datetime.fromtimestamp(old_item['item_date']).strftime('%Y-%m-%d') if old_item.get('item_date') else 'None'
                new_date = datetime.fromtimestamp(item_date_timestamp).strftime('%Y-%m-%d') if item_date_timestamp else 'None'
                changes.append(f"Date: {old_date} → {new_date}")
            
            # Time
            if old_item.get('item_time') != item_data.get('item_time'):
                old_time = old_item.get('item_time') or 'None'
                new_time = item_data.get('item_time') or 'None'
                changes.append(f"Time: {old_time} → {new_time}")
            
            # Fee breakdown
            if old_item.get('base_price') != item_data.get('base_price'):
                old_base = old_item.get('base_price')
                new_base = item_data.get('base_price')
                old_str = f"${old_base:.2f}" if old_base is not None else "None"
                new_str = f"${new_base:.2f}" if new_base is not None else "None"
                changes.append(f"Base Price: {old_str} → {new_str}")
            
            if old_item.get('tax_rate') != item_data.get('tax_rate'):
                old_tax = old_item.get('tax_rate')
                new_tax = item_data.get('tax_rate')
                old_str = f"{old_tax:.2f}%" if old_tax is not None else "None"
                new_str = f"{new_tax:.2f}%" if new_tax is not None else "None"
                changes.append(f"Tax Rate: {old_str} → {new_str}")
            
            if old_item.get('fee') != item_data.get('fee'):
                old_fee = old_item.get('fee')
                new_fee = item_data.get('fee')
                old_str = f"${old_fee:.2f}" if old_fee is not None else "None"
                new_str = f"${new_fee:.2f}" if new_fee is not None else "None"
                changes.append(f"Total Fee: {old_str} → {new_str}")
            
            # Content (with smart word-level diff)
            if old_item.get('content') != item_data.get('content'):
                from web.utils import generate_content_diff
                
                old_content = old_item.get('content') or ''
                new_content = item_data.get('content') or ''
                
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
        
        # Save updated item
        db.update_entry(entry_id, item_data, allow_locked=True)
        
        # Handle file uploads
        files = request.files.getlist('files[]')
        descriptions = request.form.getlist('file_descriptions[]')
        added_files = save_uploaded_files(files, descriptions, entry_id, db, client_id)
        
        # Track file additions in edit history
        if added_files and db.is_entry_locked(entry_id):
            file_list = ', '.join(added_files)
            db.add_to_edit_history(entry_id, f"Added files: {file_list}")
        
        return redirect(url_for('clients.client_file', client_id=client_id))
    
    # GET - show form with existing data
    # Convert timestamp back to date string
    item_date = datetime.fromtimestamp(item['item_date']).strftime('%Y-%m-%d') if item.get('item_date') else None
    
    # Get lock status and edit history
    is_locked = db.is_entry_locked(entry_id)
    edit_history = db.get_edit_history(entry_id) if is_locked else []
    
    # Get attachments
    attachments = db.get_attachments(entry_id)
    
    return render_template('entry_forms/item.html',
                         client=client,
                         client_type=client_type,
                         profile=profile,
                         entry=item,
                         item_date=item_date,
                         is_edit=True,
                         is_locked=is_locked,
                         is_billed=item.get('statement_id') is not None,
                         edit_history=edit_history,
                         attachments=attachments)
