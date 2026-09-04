"""Profile entry route.

Extracted from the entries.py split (Step B-I).
"""
from datetime import datetime
import time

from flask import render_template, request, redirect, url_for
from web.blueprints.entries.common import entries_bp, get_db, safe_float, safe_money, safe_int


@entries_bp.route('/client/<int:client_id>/profile', methods=['GET', 'POST'])
def edit_profile(client_id):
    """Create or edit client profile entry."""
    db = get_db()
    client = db.get_client(client_id)
    if not client:
        return "Client not found", 404
    
    client['type'] = db.get_client_type(client['type_id'])
    
    # Get existing profile if it exists
    profile = db.get_profile_entry(client_id)
    
    if request.method == 'POST':
        # Prepare profile data
        profile_data = {
            'client_id': client_id,
            'class': 'profile',
            'description': f"{request.form.get('first_name')} {request.form.get('last_name')} - Profile",
            'date_of_birth': request.form.get('date_of_birth', ''),
            'content': request.form.get('gender', ''),
            'address': request.form.get('address', ''),
            'email': request.form.get('email', ''),
            'phone': request.form.get('phone', ''),
            'home_phone': request.form.get('home_phone', ''),
            'work_phone': request.form.get('work_phone', ''),
            'text_number': request.form.get('text_number', ''),
            'preferred_contact': request.form.get('preferred_contact', ''),
            'ok_to_leave_message': request.form.get('ok_to_leave_message', 'yes'),
            'emergency_contact_name': request.form.get('emergency_contact_name', ''),
            'emergency_contact_phone': request.form.get('emergency_contact_phone', ''),
            'emergency_contact_relationship': request.form.get('emergency_contact_relationship', ''),
            'referral_source': request.form.get('referral_source', ''),
            'additional_info': request.form.get('additional_info', ''),
            'meeting_link': request.form.get('meeting_link', ''),
            
            # Session fee fields
            'session_base': safe_money(request.form.get('session_base')),
            'session_tax_rate': safe_float(request.form.get('session_tax_rate')),
            'session_total': safe_money(request.form.get('session_total')),
            'default_session_duration': safe_int(request.form.get('default_session_duration')),

            # Guardian/Billing fields
            'is_minor': 1 if request.form.get('is_minor') else 0,
            'guardian1_name': request.form.get('guardian1_name', ''),
            'guardian1_email': request.form.get('guardian1_email', ''),
            'guardian1_phone': request.form.get('guardian1_phone', ''),
            'guardian1_address': request.form.get('guardian1_address', ''),
            'guardian1_pays_percent': safe_float(request.form.get('guardian1_amount'), 0),
            'has_guardian2': 1 if request.form.get('has_guardian2') else 0,
            'guardian2_name': request.form.get('guardian2_name', ''),
            'guardian2_email': request.form.get('guardian2_email', ''),
            'guardian2_phone': request.form.get('guardian2_phone', ''),
            'guardian2_address': request.form.get('guardian2_address', ''),
            'guardian2_pays_percent': safe_float(request.form.get('guardian2_amount'), 0)
        }
        
        if profile:
            # Lock profile on first edit (if not already locked)
            if not db.is_entry_locked(profile['id']):
                db.lock_entry(profile['id'])
            
            # Update existing profile - track changes (now that it's locked)
            if db.is_entry_locked(profile['id']):
                changes = []
                old_profile = profile.copy()
                
                # Track CLIENT-LEVEL changes (name and file number)
                # These update the client record but we log them in profile history for completeness
                new_first = request.form.get('first_name')
                new_middle = request.form.get('middle_name', '')
                new_last = request.form.get('last_name')
                new_file_number = request.form.get('file_number')
                
                # Build old and new full names for comparison
                old_name_parts = [client['first_name']]
                if client.get('middle_name'):
                    old_name_parts.append(client['middle_name'])
                old_name_parts.append(client['last_name'])
                old_full_name = ' '.join(old_name_parts)
                
                new_name_parts = [new_first]
                if new_middle:
                    new_name_parts.append(new_middle)
                new_name_parts.append(new_last)
                new_full_name = ' '.join(new_name_parts)
                
                if old_full_name != new_full_name:
                    changes.append(f"Client Name: {old_full_name} → {new_full_name}")
                
                if client['file_number'] != new_file_number:
                    changes.append(f"Client File Number: {client['file_number']} → {new_file_number}")
                
                # Smart diff for text fields
                text_fields = {
                    'email': 'Email',
                    'phone': 'Cell Phone',
                    'home_phone': 'Home Phone',
                    'work_phone': 'Work Phone',
                    'emergency_contact_name': 'Emergency Contact',
                    'emergency_contact_phone': 'Emergency Phone',
                    'emergency_contact_relationship': 'Emergency Relationship',
                    'referral_source': 'Referral Source',
                    'meeting_link': 'Meeting Link',
                    'guardian1_name': 'Guardian 1 Name',
                    'guardian1_email': 'Guardian 1 Email',
                    'guardian1_phone': 'Guardian 1 Phone',
                    'guardian2_name': 'Guardian 2 Name',
                    'guardian2_email': 'Guardian 2 Email',
                    'guardian2_phone': 'Guardian 2 Phone'
                }
                
                for field, label in text_fields.items():
                    old_val = old_profile.get(field) or ''
                    new_val = profile_data.get(field) or ''
                    if old_val != new_val:
                        if old_val and new_val:
                            changes.append(f"{label}: {old_val} → {new_val}")
                        elif old_val:
                            changes.append(f"{label}: Cleared")
                        else:
                            changes.append(f"{label}: Added")
                
                # Date of Birth
                if old_profile.get('date_of_birth') != profile_data.get('date_of_birth'):
                    old_dob = old_profile.get('date_of_birth') or 'None'
                    new_dob = profile_data.get('date_of_birth') or 'None'
                    changes.append(f"Date of Birth: {old_dob} → {new_dob}")
                
                # Gender
                if old_profile.get('content') != profile_data.get('content'):
                    old_gender = old_profile.get('content') or 'None'
                    new_gender = profile_data.get('content') or 'None'
                    changes.append(f"Gender: {old_gender} → {new_gender}")
                
                # Dropdowns
                if old_profile.get('text_number') != profile_data.get('text_number'):
                    changes.append(f"Text Number: {old_profile.get('text_number')} → {profile_data.get('text_number')}")
                
                if old_profile.get('preferred_contact') != profile_data.get('preferred_contact'):
                    changes.append(f"Preferred Contact: {old_profile.get('preferred_contact')} → {profile_data.get('preferred_contact')}")
                
                if old_profile.get('ok_to_leave_message') != profile_data.get('ok_to_leave_message'):
                    changes.append(f"Leave Message: {old_profile.get('ok_to_leave_message')} → {profile_data.get('ok_to_leave_message')}")
                
                # Address (smart word-level diff)
                if old_profile.get('address') != profile_data.get('address'):
                    from web.utils import generate_content_diff
                    
                    old_addr = old_profile.get('address') or ''
                    new_addr = profile_data.get('address') or ''
                    
                    if old_addr and new_addr:
                        diff_text = generate_content_diff(old_addr, new_addr, max_length=100)
                        changes.append(f"Address: {diff_text}")
                    elif old_addr:
                        changes.append("Address: Cleared")
                    else:
                        changes.append("Address: Added")
                
                # Additional Info (smart word-level diff)
                if old_profile.get('additional_info') != profile_data.get('additional_info'):
                    from web.utils import generate_content_diff
                    
                    old_info = old_profile.get('additional_info') or ''
                    new_info = profile_data.get('additional_info') or ''
                    
                    if old_info and new_info:
                        diff_text = generate_content_diff(old_info, new_info)
                        changes.append(f"Additional Info: {diff_text}")
                    elif old_info:
                        changes.append("Additional Info: Cleared")
                    else:
                        changes.append("Additional Info: Added")
                
                # Fee changes - track all three fields
                if old_profile.get('session_base') != profile_data.get('session_base'):
                    old_base = old_profile.get('session_base')
                    new_base = profile_data.get('session_base')
                    # Convert to float if string (database might return string)
                    if old_base is not None and isinstance(old_base, str):
                        old_base = float(old_base) if old_base else None
                    if new_base is not None and isinstance(new_base, str):
                        new_base = float(new_base) if new_base else None
                    # Only log if there's an actual change (not None → None)
                    if old_base is not None or new_base is not None:
                        old_str = f"${old_base:.2f}" if old_base is not None else "None"
                        new_str = f"${new_base:.2f}" if new_base is not None else "None"
                        changes.append(f"Session Fee Base: {old_str} → {new_str}")
                
                if old_profile.get('session_tax_rate') != profile_data.get('session_tax_rate'):
                    old_tax = old_profile.get('session_tax_rate')
                    new_tax = profile_data.get('session_tax_rate')
                    # Convert to float if string (database might return string)
                    if old_tax is not None and isinstance(old_tax, str):
                        old_tax = float(old_tax) if old_tax else None
                    if new_tax is not None and isinstance(new_tax, str):
                        new_tax = float(new_tax) if new_tax else None
                    # Only log if there's an actual change (not None → None)
                    if old_tax is not None or new_tax is not None:
                        old_str = f"{old_tax:.2f}%" if old_tax is not None else "None"
                        new_str = f"{new_tax:.2f}%" if new_tax is not None else "None"
                        changes.append(f"Session Fee Tax: {old_str} → {new_str}")
                
                if old_profile.get('session_total') != profile_data.get('session_total'):
                    old_fee = old_profile.get('session_total')
                    new_fee = profile_data.get('session_total')
                    # Convert to float if string
                    if old_fee is not None and isinstance(old_fee, str):
                        old_fee = float(old_fee) if old_fee else None
                    if new_fee is not None and isinstance(new_fee, str):
                        new_fee = float(new_fee) if new_fee else None
                    # Only log if there's an actual change (not None → None)
                    if old_fee is not None or new_fee is not None:
                        old_str = f"${old_fee:.2f}" if old_fee is not None else "None"
                        new_str = f"${new_fee:.2f}" if new_fee is not None else "None"
                        changes.append(f"Session Fee Total: {old_str} → {new_str}")
                
                # Default session duration
                if old_profile.get('default_session_duration') != profile_data.get('default_session_duration'):
                    old_dur = old_profile.get('default_session_duration')
                    new_dur = profile_data.get('default_session_duration')
                    # Convert to int if string
                    if old_dur is not None and isinstance(old_dur, str):
                        old_dur = int(old_dur) if old_dur else None
                    if new_dur is not None and isinstance(new_dur, str):
                        new_dur = int(new_dur) if new_dur else None
                    # Only log if there's an actual change (not None → None)
                    if old_dur is not None or new_dur is not None:
                        old_str = f"{old_dur} min" if old_dur is not None else "None"
                        new_str = f"{new_dur} min" if new_dur is not None else "None"
                        changes.append(f"Default Duration: {old_str} → {new_str}")
                
                # Guardian addresses (smart word-level diff)
                if old_profile.get('guardian1_address') != profile_data.get('guardian1_address'):
                    from web.utils import generate_content_diff
                    
                    old_addr = old_profile.get('guardian1_address') or ''
                    new_addr = profile_data.get('guardian1_address') or ''
                    
                    if old_addr and new_addr:
                        diff_text = generate_content_diff(old_addr, new_addr, max_length=100)
                        changes.append(f"Guardian 1 Address: {diff_text}")
                    elif old_addr:
                        changes.append("Guardian 1 Address: Cleared")
                    else:
                        changes.append("Guardian 1 Address: Added")
                
                if old_profile.get('guardian2_address') != profile_data.get('guardian2_address'):
                    from web.utils import generate_content_diff
                    
                    old_addr = old_profile.get('guardian2_address') or ''
                    new_addr = profile_data.get('guardian2_address') or ''
                    
                    if old_addr and new_addr:
                        diff_text = generate_content_diff(old_addr, new_addr, max_length=100)
                        changes.append(f"Guardian 2 Address: {diff_text}")
                    elif old_addr:
                        changes.append("Guardian 2 Address: Cleared")
                    else:
                        changes.append("Guardian 2 Address: Added")
                
                # Guardian changes
                if old_profile.get('is_minor') != profile_data.get('is_minor'):
                    changes.append(f"Minor Status: {'Yes' if profile_data.get('is_minor') else 'No'}")
                
                if old_profile.get('has_guardian2') != profile_data.get('has_guardian2'):
                    changes.append(f"Has Second Guardian: {'Yes' if profile_data.get('has_guardian2') else 'No'}")
                
                if old_profile.get('guardian1_pays_percent') != profile_data.get('guardian1_pays_percent'):
                    old_pct = old_profile.get('guardian1_pays_percent') or 0
                    new_pct = profile_data.get('guardian1_pays_percent') or 0
                    changes.append(f"Guardian 1 Pays: {old_pct}% → {new_pct}%")
                
                if old_profile.get('guardian2_pays_percent') != profile_data.get('guardian2_pays_percent'):
                    old_pct = old_profile.get('guardian2_pays_percent') or 0
                    new_pct = profile_data.get('guardian2_pays_percent') or 0
                    changes.append(f"Guardian 2 Pays: {old_pct}% → {new_pct}%")
                
                if changes:
                    change_desc = "; ".join(changes)
                    db.add_to_edit_history(profile['id'], change_desc)
            
            db.update_entry(profile['id'], profile_data, allow_locked=True)
        else:
            # Create new profile
            db.add_entry(profile_data)
            # Note: Profile entries are NOT locked on creation (they're meant to be updated)
        
        # Update client record if names or file number changed
        client_updates = {}
        
        if request.form.get('first_name') != client['first_name']:
            client_updates['first_name'] = request.form.get('first_name')
        
        if request.form.get('middle_name', '') != (client.get('middle_name') or ''):
            client_updates['middle_name'] = request.form.get('middle_name') or None
        
        if request.form.get('last_name') != client['last_name']:
            client_updates['last_name'] = request.form.get('last_name')
        
        if request.form.get('file_number') != client['file_number']:
            client_updates['file_number'] = request.form.get('file_number')
        
        if client_updates:
            client_updates['modified_at'] = int(time.time())
            db.update_client(client_id, client_updates)

        # Insurance provider. Absent field means "no change"; an empty value
        # means "no insurer", which is how a client drops or changes cover.
        if 'provider_id' in request.form:
            db.set_client_provider(client_id,
                                   request.form.get('provider_id') or None)

        return redirect(url_for('clients.client_file', client_id=client_id))
    
    # GET request - show form
    all_types = db.get_all_client_types()
    insurance_providers = db.get_insurance_providers()
    current_provider = db.get_client_provider(client_id)
    
    # Get edit history if profile exists and is locked
    is_locked = db.is_entry_locked(profile['id']) if profile else False
    edit_history = db.get_edit_history(profile['id']) if is_locked else []
    
    # Calculate retention info for Inactive clients
    retention_info = None
    if client['type']['name'] == 'Inactive' and client.get('retention_days'):
        # Get last contact (most recent entry, or fall back to modified_at)
        conn = db.connect()
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(created_at) FROM entries WHERE client_id = ?", (client_id,))
        result = cursor.fetchone()
        last_contact = result[0] if result and result[0] else client['modified_at']
        
        retention_days = client['retention_days']
        retain_until = last_contact + (retention_days * 24 * 60 * 60)
        
        retention_info = {
            'retention_days': retention_days,
            'last_contact': datetime.fromtimestamp(last_contact).strftime('%B %d, %Y'),
            'retain_until': datetime.fromtimestamp(retain_until).strftime('%B %d, %Y'),
            'is_due': int(time.time()) >= retain_until
        }
    
    return render_template('entry_forms/profile.html',
                         client=client,
                         profile=profile,
                         all_types=all_types,
                         is_locked=is_locked,
                         edit_history=edit_history,
                         insurance_providers=insurance_providers,
                         current_provider=current_provider,
                         retention_info=retention_info)
