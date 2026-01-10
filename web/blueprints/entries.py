# -*- coding: utf-8 -*-
"""
EdgeCase Entries Blueprint
Handles all entry types (Profile, Session, Communication, Absence, Item, Upload)
"""

from flask import Blueprint, render_template, request, redirect, url_for, send_file
from pathlib import Path
from datetime import datetime
from werkzeug.utils import secure_filename
import sqlcipher3 as sqlite3
import time
import os
import shutil
from web.utils import parse_date_from_form, get_today_date_parts, save_uploaded_files
from core.encryption import decrypt_file_to_bytes
from io import BytesIO

from core.database import Database
from core.config import DATA_ROOT, ATTACHMENTS_DIR, ASSETS_DIR

def resolve_attachment_path(filepath):
    """Resolve attachment filepath, handling both absolute and relative paths."""
    if os.path.isabs(filepath):
        return filepath
    return str(DATA_ROOT / filepath)

# Initialize blueprint
entries_bp = Blueprint('entries', __name__)

# Database instance (set by init_blueprint)
db = None

def init_blueprint(database):
    """Initialize blueprint with database instance"""
    global db
    db = database


# ============================================================================
# HELPER FUNCTION (from app.py)
# ============================================================================

def renumber_sessions(client_id):
    """Recalculate session numbers for a client based on chronological order."""
    # Get client to check for session offset
    client = db.get_client(client_id)
    offset = client.get('session_offset', 0)
    
    # Get all non-consultation, non-redacted sessions with dates
    all_sessions = db.get_client_entries(client_id, 'session')
    dated_sessions = [s for s in all_sessions 
                      if s.get('session_date') 
                      and not s.get('is_consultation')
                      and not s.get('is_redacted')]
    
    # Sort by date, then by ID
    dated_sessions.sort(key=lambda s: (s['session_date'], s['id']))
    
    # Renumber sessions starting from (offset + 1)
    for i, session in enumerate(dated_sessions, start=offset + 1):
        if session['session_number'] != i:
            db.update_entry(session['id'], {
                'session_number': i,
                'description': f"Session {i}"
            })


# ============================================================================
# PROFILE ENTRY ROUTES
# ============================================================================

@entries_bp.route('/client/<int:client_id>/profile', methods=['GET', 'POST'])
def edit_profile(client_id):
    """Create or edit client profile entry."""
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
            
            # Session fee fields
            'session_base': float(request.form.get('session_base')) if request.form.get('session_base') else None,
            'session_tax_rate': float(request.form.get('session_tax_rate')) if request.form.get('session_tax_rate') else None,
            'session_total': float(request.form.get('session_total')) if request.form.get('session_total') else None,
            'default_session_duration': int(request.form.get('default_session_duration')) if request.form.get('default_session_duration') else None,
            
            # Guardian/Billing fields
            'is_minor': 1 if request.form.get('is_minor') else 0,
            'guardian1_name': request.form.get('guardian1_name', ''),
            'guardian1_email': request.form.get('guardian1_email', ''),
            'guardian1_phone': request.form.get('guardian1_phone', ''),
            'guardian1_address': request.form.get('guardian1_address', ''),
            'guardian1_pays_percent': float(request.form.get('guardian1_amount')) if request.form.get('guardian1_amount') else 0,
            'has_guardian2': 1 if request.form.get('has_guardian2') else 0,
            'guardian2_name': request.form.get('guardian2_name', ''),
            'guardian2_email': request.form.get('guardian2_email', ''),
            'guardian2_phone': request.form.get('guardian2_phone', ''),
            'guardian2_address': request.form.get('guardian2_address', ''),
            'guardian2_pays_percent': float(request.form.get('guardian2_amount')) if request.form.get('guardian2_amount') else 0
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
            
            db.update_entry(profile['id'], profile_data)
        else:
            # Create new profile
            entry_id = db.add_entry(profile_data)
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
        
        return redirect(url_for('clients.client_file', client_id=client_id))
    
    # GET request - show form
    all_types = db.get_all_client_types()
    
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
                         retention_info=retention_info)


# ============================================================================
# SESSION ENTRY ROUTES
# ============================================================================

@entries_bp.route('/client/<int:client_id>/session', methods=['GET', 'POST'])
def create_session(client_id):
    """Create a new session entry for a client."""
    client = db.get_client(client_id)
    if not client:
        return "Client not found", 404
    
    client_type = db.get_client_type(client['type_id'])
    
    if request.method == 'POST':
        # Check if consultation or pro bono
        is_consultation = 1 if request.form.get('is_consultation') else 0
        is_pro_bono = 1 if request.form.get('is_pro_bono') else 0
        
        session_date_timestamp = parse_date_from_form(request.form)
        
        # Get form data
        session_data = {
            'client_id': client_id,
            'class': 'session',
            'created_at': int(time.time()),
            'modified_at': int(time.time()),
            
            'modality': request.form.get('modality'),
            'format': request.form.get('format'),
            'service': request.form.get('service') or None, 
            'session_date': session_date_timestamp,
            'session_time': request.form.get('session_time') or None,
            'duration': int(request.form.get('duration')) if request.form.get('duration') else None,
            'base_fee': float(request.form.get('base_fee')) if request.form.get('base_fee') else None,
            'tax_rate': float(request.form.get('tax_rate')) if request.form.get('tax_rate') else None,
            'fee': float(request.form.get('fee')) if request.form.get('fee') else None,
            'is_consultation': is_consultation,
            'is_pro_bono': is_pro_bono,
            
            'mood': request.form.get('mood') or None,
            'affect': request.form.get('affect') or None,
            'risk_assessment': request.form.get('risk_assessment') or None,
            
            'content': request.form.get('content') or None,
        }
        
        # Set session number and description based on consultation status
        if is_consultation:
            session_data['session_number'] = None
            session_data['fee'] = 0
            session_data['base_fee'] = 0
            session_data['tax_rate'] = 0
            session_data['description'] = 'Consultation'
        else:
            session_data['session_number'] = 999
            session_data['description'] = 'Session 999'
        
        # Save session entry
        entry_id = db.add_entry(session_data)

        # Check if this is a draft save (or AI Scribe - treat as draft)
        is_draft_save = request.form.get('save_draft') == '1' or request.form.get('ai_scribe') == '1'

        # Only lock if NOT a draft save
        if not is_draft_save:
            db.lock_entry(entry_id)

        # Renumber all sessions to maintain chronological order
        renumber_sessions(client_id)
        
        # Check if AI Scribe button was clicked - redirect there instead
        if request.form.get('ai_scribe'):
            return redirect(url_for('ai.scribe_page', entry_id=entry_id))
                
        return redirect(url_for('clients.client_file', client_id=client_id))
    
    # GET - show form
    date_parts = get_today_date_parts()

    # Calculate preview session number
    all_sessions = db.get_client_entries(client_id, 'session')
    dated_sessions = [s for s in all_sessions if s.get('session_date') and not s.get('is_consultation')]
    dated_sessions.sort(key=lambda s: (s['session_date'], s['id']))

    offset = client.get('session_offset', 0)
    today_timestamp = int(datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    sessions_before_today = sum(1 for s in dated_sessions if s['session_date'] <= today_timestamp)
    preview_session_number = sessions_before_today + offset + 1

    prev_session_id = None
    next_session_id = None

    # Prepare fee sources
    profile = db.get_profile_entry(client_id)
    profile_override = None
    if profile and profile.get('session_total'):
        profile_override = {
            'base': profile['session_base'],
            'tax': profile['session_tax_rate'],
            'total': profile['session_total']
        }

    if profile:
        profile_fees = {
            'base': profile.get('session_base') or 0,
            'tax': profile.get('session_tax_rate') or 0,
            'total': profile.get('session_total') or 0,
            'duration': profile.get('default_session_duration') or 50
        }
    else:
        profile_fees = {
            'base': 0,
            'tax': 0,
            'total': 0,
            'duration': 50
        }
        
    link_group_fees = {}
    
    conn = db.connect()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT cl.group_id, cl.member_base_fee, cl.member_tax_rate, cl.member_total_fee, lg.format, lg.session_duration
        FROM client_links cl
        JOIN link_groups lg ON cl.group_id = lg.id
        WHERE cl.client_id_1 = ?
    """, (client_id,))

    for row in cursor.fetchall():
        format_type = row['format']
        if format_type:
            link_group_fees[format_type] = {
                'base': row['member_base_fee'] or 0,
                'tax': row['member_tax_rate'] or 0,
                'total': row['member_total_fee'] or 0,
                'duration': row['session_duration'] or 50
            }
    
    cursor.execute("""
        SELECT service FROM entries
        WHERE client_id = ? AND class = 'session' AND service IS NOT NULL
        ORDER BY session_date DESC, created_at DESC
        LIMIT 1
    """, (client_id,))
    
    last_service_row = cursor.fetchone()
    last_service = last_service_row['service'] if last_service_row else None
    

    return render_template('entry_forms/session.html',
                        client=client,
                        client_type=client_type,
                        profile_override=profile_override,
                        profile_fees=profile_fees,
                        link_group_fees=link_group_fees,
                        last_service=last_service,
                        **date_parts,
                        next_session_number=preview_session_number,
                        is_edit=False,
                        prev_session_id=prev_session_id,
                        next_session_id=next_session_id)


@entries_bp.route('/client/<int:client_id>/session/<int:entry_id>', methods=['GET', 'POST'])
def edit_session(client_id, entry_id):
    """Edit an existing session entry."""
    
    # Get client info
    client = db.get_client(client_id)
    if not client:
        return "Client not found", 404
    
    # Get client type for defaults
    client_type = db.get_client_type(client['type_id'])
    
    # Get existing session entry
    session = db.get_entry(entry_id)
    
    if not session or session['class'] != 'session':
        return "Session not found", 404
    
    # Redirect to redacted view if this entry has been redacted
    if session.get('is_redacted'):
        return redirect(url_for('entries.view_redacted_entry', 
                                client_id=client_id, entry_id=entry_id))
    
    if request.method == 'POST':
        # Get the old session data for comparison
        old_session = session.copy()
        
        # Check if entry is billed (has statement_id) - billing fields cannot be changed
        is_billed = session.get('statement_id') is not None
        
        # Check if consultation
        is_consultation = 1 if request.form.get('is_consultation') else 0
        is_pro_bono = 1 if request.form.get('is_pro_bono') else 0
        
        # If billed, preserve original consultation/pro_bono status
        if is_billed:
            is_consultation = old_session.get('is_consultation', 0)
            is_pro_bono = old_session.get('is_pro_bono', 0)
        
        session_date_timestamp = parse_date_from_form(request.form)
        
        # Update session data - preserve billing fields if entry is billed
        session_data = {
            'modality': request.form.get('modality'),
            'format': request.form.get('format'),
            'service': request.form.get('service') or None,
            'session_date': old_session.get('session_date') if is_billed else session_date_timestamp,
            'session_time': request.form.get('session_time') or None,
            'duration': old_session.get('duration') if is_billed else (int(request.form.get('duration')) if request.form.get('duration') else None),
            'base_fee': old_session.get('base_fee') if is_billed else (float(request.form.get('base_fee')) if request.form.get('base_fee') else None),
            'tax_rate': old_session.get('tax_rate') if is_billed else (float(request.form.get('tax_rate')) if request.form.get('tax_rate') else None),
            'fee': old_session.get('fee') if is_billed else (float(request.form.get('fee')) if request.form.get('fee') else None),
            'is_consultation': is_consultation,
            'is_pro_bono': is_pro_bono,
            'modified_at': int(time.time()),
            
            # Clinical fields (always editable)
            'mood': request.form.get('mood') or None,
            'affect': request.form.get('affect') or None,
            'risk_assessment': request.form.get('risk_assessment') or None,
            
            # Content (always editable)
            'content': request.form.get('content') or None,
        }
        
        # Update description based on consultation/pro bono status
        # If billed, preserve original description
        if is_billed:
            session_data['description'] = old_session.get('description')
        elif is_consultation:
            session_data['fee'] = 0
            session_data['base_fee'] = 0
            session_data['tax_rate'] = 0
            session_data['description'] = 'Consultation'
        elif is_pro_bono:
            session_data['fee'] = 0
            session_data['base_fee'] = 0
            session_data['tax_rate'] = 0
            session_data['description'] = f"Session {session['session_number']} (Pro Bono)"
        else:
            # Keep existing session number
            session_data['description'] = f"Session {session['session_number']}"
        
        # Check if this is a draft save (or AI Scribe - treat as draft)
        is_draft_save = request.form.get('save_draft') == '1' or request.form.get('ai_scribe') == '1'

        # Only lock and track history if NOT a draft save
        if not is_draft_save:
            # Lock the entry if not already locked
            if not db.is_entry_locked(entry_id):
                db.lock_entry(entry_id)
            # If already locked, log changes to edit history
            elif db.is_entry_locked(entry_id):
                changes = []
            
                # Date
                if old_session.get('session_date') != session_date_timestamp:
                    old_date = datetime.fromtimestamp(old_session['session_date']).strftime('%Y-%m-%d') if old_session.get('session_date') else 'None'
                    new_date = datetime.fromtimestamp(session_date_timestamp).strftime('%Y-%m-%d') if session_date_timestamp else 'None'
                    changes.append(f"Date: {old_date} → {new_date}")
                
                # Time
                if old_session.get('session_time') != session_data.get('session_time'):
                    old_time = old_session.get('session_time') or 'None'
                    new_time = session_data.get('session_time') or 'None'
                    changes.append(f"Time: {old_time} → {new_time}")
                
                # Modality
                if old_session.get('modality') != session_data.get('modality'):
                    changes.append(f"Modality: {old_session.get('modality')} → {session_data.get('modality')}")
                
                # Format
                if old_session.get('format') != session_data.get('format'):
                    changes.append(f"Format: {old_session.get('format')} → {session_data.get('format')}")
                    
                # Service
                if old_session.get('service') != session_data.get('service'):
                    old_service = old_session.get('service') or 'Not Set'
                    new_service = session_data.get('service') or 'Not Set'
                    changes.append(f"Service: {old_service} → {new_service}")
                
                # Duration
                if old_session.get('duration') != session_data.get('duration'):
                    changes.append(f"Duration: {old_session.get('duration')}min → {session_data.get('duration')}min")
                
                # Fee breakdown (handle None values explicitly)
                if old_session.get('base_fee') != session_data.get('base_fee'):
                    old_base = old_session.get('base_fee')
                    new_base = session_data.get('base_fee')
                    old_str = f"${old_base:.2f}" if old_base is not None else "None"
                    new_str = f"${new_base:.2f}" if new_base is not None else "None"
                    changes.append(f"Base Fee: {old_str} → {new_str}")
                
                if old_session.get('tax_rate') != session_data.get('tax_rate'):
                    old_tax = old_session.get('tax_rate')
                    new_tax = session_data.get('tax_rate')
                    old_str = f"{old_tax:.2f}%" if old_tax is not None else "None"
                    new_str = f"{new_tax:.2f}%" if new_tax is not None else "None"
                    changes.append(f"Tax Rate: {old_str} → {new_str}")
                
                if old_session.get('fee') != session_data.get('fee'):
                    old_fee = old_session.get('fee')
                    new_fee = session_data.get('fee')
                    old_str = f"${old_fee:.2f}" if old_fee is not None else "None"
                    new_str = f"${new_fee:.2f}" if new_fee is not None else "None"
                    changes.append(f"Total Fee: {old_str} → {new_str}")
                
                # Consultation/Pro Bono
                if old_session.get('is_consultation') != session_data.get('is_consultation'):
                    status = "Enabled" if session_data.get('is_consultation') else "Disabled"
                    changes.append(f"Consultation: {status}")
                
                if old_session.get('is_pro_bono') != session_data.get('is_pro_bono'):
                    status = "Enabled" if session_data.get('is_pro_bono') else "Disabled"
                    changes.append(f"Pro Bono: {status}")
                
                # Clinical fields (normalize both old and new to None if empty/None)
                old_mood = old_session.get('mood') or None
                new_mood = session_data.get('mood') or None
                if old_mood != new_mood:
                    changes.append(f"Mood: {old_mood or 'Not Assessed'} → {new_mood or 'Not Assessed'}")
                
                old_affect = old_session.get('affect') or None
                new_affect = session_data.get('affect') or None
                if old_affect != new_affect:
                    changes.append(f"Affect: {old_affect or 'Not Assessed'} → {new_affect or 'Not Assessed'}")
                
                old_risk = old_session.get('risk_assessment') or None
                new_risk = session_data.get('risk_assessment') or None
                if old_risk != new_risk:
                    changes.append(f"Risk: {old_risk or 'Not Assessed'} → {new_risk or 'Not Assessed'}")
                
                # Notes (with smart word-level diff)
                if old_session.get('content') != session_data.get('content'):
                    from web.utils import generate_content_diff
                    
                    old_content = old_session.get('content') or ''
                    new_content = session_data.get('content') or ''
                    
                    if old_content and new_content:
                        diff_text = generate_content_diff(old_content, new_content)
                        changes.append(f"Notes: {diff_text}")
                    elif old_content:
                        changes.append("Notes: Cleared")
                    else:
                        changes.append("Notes: Added")
            
                if changes:
                    change_desc = "; ".join(changes)
                    db.add_to_edit_history(entry_id, change_desc)
            
        # Save updated session
        db.update_entry(entry_id, session_data)
        
        # Renumber sessions in case consultation status changed
        renumber_sessions(client_id)
        
        # Check if AI Scribe button was clicked - redirect there instead
        if request.form.get('ai_scribe'):
            return redirect(url_for('ai.scribe_page', entry_id=entry_id))
        
        return redirect(url_for('clients.client_file', client_id=client_id))
    
    # GET request - show form with existing data
    
    # Get all sessions for this client (ordered by date, then by ID)
    all_sessions = db.get_client_entries(client_id, 'session')
    # Filter out sessions without dates
    dated_sessions = [s for s in all_sessions if s.get('session_date')]
    # Sort by date (oldest first), then by ID for stable ordering when dates match
    dated_sessions.sort(key=lambda s: (s['session_date'], s['id']))
    
    # Find current session index
    current_index = None
    for i, s in enumerate(dated_sessions):
        if s['id'] == entry_id:
            current_index = i
            break
    
    # Determine prev/next session IDs (prev = older, next = newer)
    prev_session_id = dated_sessions[current_index - 1]['id'] if current_index is not None and current_index > 0 else None
    next_session_id = dated_sessions[current_index + 1]['id'] if current_index is not None and current_index < len(dated_sessions) - 1 else None
    
    # Parse session date into year, month, day for dropdowns
    session_year = None
    session_month = None
    session_day = None
    if session.get('session_date'):
        session_dt = datetime.fromtimestamp(session['session_date'])
        session_year = session_dt.year
        session_month = session_dt.month
        session_day = session_dt.day
    
    # Prepare fee sources for JavaScript (same as create_session)
    # 1. Profile Override (if exists)
    profile = db.get_profile_entry(client_id)
    profile_override = None
    if profile and profile.get('session_total'):
        profile_override = {
            'base': profile['session_base'],
            'tax': profile['session_tax_rate'],
            'total': profile['session_total']
        }

    # 2. Get individual session fees from Profile
    if profile:
        profile_fees = {
            'base': profile.get('session_base') or 0,
            'tax': profile.get('session_tax_rate') or 0,
            'total': profile.get('session_total') or 0,
            'duration': profile.get('default_session_duration') or 50
        }
    else:
        profile_fees = {
            'base': 0,
            'tax': 0,
            'total': 0,
            'duration': 50
        }
    
    # 3. Link Groups (by format)
    link_group_fees = {}
    
    # Get all link groups this client is in
    conn = db.connect()
    conn.row_factory = sqlite3.Row
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
            link_group_fees[format_type] = {
                'base': row['member_base_fee'] or 0,
                'tax': row['member_tax_rate'] or 0,
                'total': row['member_total_fee'] or 0,
                'duration': row['session_duration'] or 50
            }
    
    
    # Check if entry is locked
    is_locked = db.is_entry_locked(entry_id)
    
    # Get edit history if locked
    edit_history = db.get_edit_history(entry_id) if is_locked else []
    
    return render_template('entry_forms/session.html',
                         client=client,
                         client_type=client_type,
                         session=session,
                         profile_override=profile_override,
                         profile_fees=profile_fees,
                         link_group_fees=link_group_fees,
                         session_year=session_year,
                         session_month=session_month,
                         session_day=session_day,
                         is_edit=True,
                         is_locked=is_locked,
                         is_billed=session.get('statement_id') is not None,
                         edit_history=edit_history,
                         prev_session_id=prev_session_id,
                         next_session_id=next_session_id)


# ============================================================================
# COMMUNICATION ENTRY ROUTES
# ============================================================================

@entries_bp.route('/client/<int:client_id>/communication', methods=['GET', 'POST'])
def create_communication(client_id):
    """Create new communication entry."""
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
    client = db.get_client(client_id)
    if not client:
        return "Client not found", 404
    
    client_type = db.get_client_type(client['type_id'])
    communication = db.get_entry(entry_id)
    
    if not communication or communication['class'] != 'communication':
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
        db.update_entry(entry_id, comm_data)
        
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

# ============================================================================
# ABSENCE ENTRY ROUTES  
# ============================================================================

@entries_bp.route('/client/<int:client_id>/absence', methods=['GET', 'POST'])
def create_absence(client_id):
    """Create a new absence entry for a client."""
    client = db.get_client(client_id)
    if not client:
        return "Client not found", 404
    
    client_type = db.get_client_type(client['type_id'])
    
    if request.method == 'POST':
        absence_date_str = request.form.get('date')
        absence_date_timestamp = None
        if absence_date_str:
            date_obj = datetime.strptime(absence_date_str, '%Y-%m-%d')
            absence_date_timestamp = int(date_obj.timestamp())
        
        absence_data = {
            'client_id': client_id,
            'class': 'absence',
            'description': request.form['description'],
            'format': request.form.get('format', ''),
            'absence_date': absence_date_timestamp,
            'absence_time': request.form.get('absence_time', ''),
            'base_fee': float(request.form.get('base_fee', 0)),
            'tax_rate': float(request.form.get('tax_rate', 0)),
            'fee': float(request.form.get('fee', 0)),
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
    link_group_fees = {}
    conn = db.connect()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT cl.group_id, cl.member_base_fee, cl.member_tax_rate, cl.member_total_fee, lg.format
        FROM client_links cl
        JOIN link_groups lg ON cl.group_id = lg.id
        WHERE cl.client_id_1 = ?
    """, (client_id,))

    for row in cursor.fetchall():
        format_type = row['format']
        if format_type:
            link_group_fees[format_type] = {
                'base': row['member_base_fee'] or 0,
                'tax': row['member_tax_rate'] or 0,
                'total': row['member_total_fee'] or 0
            }
    
    return render_template('entry_forms/absence.html',
                         client=client,
                         client_type=client_type,
                         today=today,
                         profile_fees=profile_fees,
                         link_group_fees=link_group_fees)


@entries_bp.route('/client/<int:client_id>/absence/<int:entry_id>', methods=['GET', 'POST'])
def edit_absence(client_id, entry_id):
    """Edit existing absence entry."""
    client = db.get_client(client_id)
    if not client:
        return "Client not found", 404
    
    client_type = db.get_client_type(client['type_id'])
    absence = db.get_entry(entry_id)
    
    if not absence or absence['class'] != 'absence':
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
            date_obj = datetime.strptime(absence_date_str, '%Y-%m-%d')
            absence_date_timestamp = int(date_obj.timestamp())
        
        # Prepare updated absence data - preserve billing fields if billed
        absence_data = {
            'description': request.form['description'],
            'format': old_absence.get('format') if is_billed else request.form.get('format', ''),
            'absence_date': old_absence.get('absence_date') if is_billed else absence_date_timestamp,
            'absence_time': request.form.get('absence_time', ''),
            'base_fee': old_absence.get('base_fee') if is_billed else float(request.form.get('base_fee', 0)),
            'tax_rate': old_absence.get('tax_rate') if is_billed else float(request.form.get('tax_rate', 0)),
            'fee': old_absence.get('fee') if is_billed else float(request.form.get('fee', 0)),
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
        db.update_entry(entry_id, absence_data)
        
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
    link_group_fees = {}
    conn = db.connect()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT cl.group_id, cl.member_base_fee, cl.member_tax_rate, cl.member_total_fee, lg.format
        FROM client_links cl
        JOIN link_groups lg ON cl.group_id = lg.id
        WHERE cl.client_id_1 = ?
    """, (client_id,))

    for row in cursor.fetchall():
        format_type = row['format']
        if format_type:
            link_group_fees[format_type] = {
                'base': row['member_base_fee'] or 0,
                'tax': row['member_tax_rate'] or 0,
                'total': row['member_total_fee'] or 0
            }
    
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


# ============================================================================
# ITEM ENTRY ROUTES
# ============================================================================

@entries_bp.route('/client/<int:client_id>/item', methods=['GET', 'POST'])
def create_item(client_id):
    """Create a new item entry for a client."""
    client = db.get_client(client_id)
    if not client:
        return "Client not found", 404
    
    client_type = db.get_client_type(client['type_id'])
    profile = db.get_profile_entry(client_id)
    
    if request.method == 'POST':
        item_date_str = request.form.get('item_date')
        item_date_timestamp = None
        if item_date_str:
            item_date_timestamp = int(datetime.strptime(item_date_str, '%Y-%m-%d').timestamp())
        
        # Parse guardian amounts if provided
        g1_amount = request.form.get('guardian1_amount')
        g2_amount = request.form.get('guardian2_amount')
        
        # Parse guardian amounts - check for empty strings
        g1_parsed = float(g1_amount) if g1_amount and g1_amount.strip() else None
        g2_parsed = float(g2_amount) if g2_amount and g2_amount.strip() else None
        
        item_data = {
            'client_id': client_id,
            'class': 'item',
            'created_at': int(time.time()),
            'modified_at': int(time.time()),
            
            'description': request.form['description'],
            'item_date': item_date_timestamp,
            'item_time': request.form.get('item_time') or None,
            'base_price': float(request.form.get('base_price', 0)),
            'tax_rate': float(request.form.get('tax_rate', 0)),
            'fee': float(request.form.get('fee', 0)),
            
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
    client = db.get_client(client_id)
    if not client:
        return "Client not found", 404
    
    client_type = db.get_client_type(client['type_id'])
    profile = db.get_profile_entry(client_id)
    item = db.get_entry(entry_id)
    
    if not item or item['class'] != 'item':
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
            date_obj = datetime.strptime(item_date_str, '%Y-%m-%d')
            item_date_timestamp = int(date_obj.timestamp())
        
        # Parse guardian amounts if provided
        g1_amount = request.form.get('guardian1_amount')
        g2_amount = request.form.get('guardian2_amount')
        
        # Prepare updated item data - preserve billing fields if billed
        item_data = {
            'description': request.form['description'],
            'item_date': old_item.get('item_date') if is_billed else item_date_timestamp,
            'item_time': request.form.get('item_time', ''),
            'base_price': old_item.get('base_price') if is_billed else (float(request.form.get('base_price', 0)) if request.form.get('base_price') else None),
            'tax_rate': old_item.get('tax_rate') if is_billed else (float(request.form.get('tax_rate', 0)) if request.form.get('tax_rate') else 0),
            'fee': old_item.get('fee') if is_billed else float(request.form.get('fee', 0)),
            'guardian1_amount': old_item.get('guardian1_amount') if is_billed else (float(g1_amount) if g1_amount else None),
            'guardian2_amount': old_item.get('guardian2_amount') if is_billed else (float(g2_amount) if g2_amount else None),
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
        db.update_entry(entry_id, item_data)
        
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


# ============================================================================
# UPLOAD ENTRY ROUTES
# ============================================================================

@entries_bp.route('/client/<int:client_id>/upload', methods=['GET', 'POST'])
def create_upload(client_id):
    """Create new upload entry with file attachments."""
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
    client = db.get_client(client_id)
    if not client:
        return "Client not found", 404
    
    client_type = db.get_client_type(client['type_id'])
    upload = db.get_entry(entry_id)
    
    if not upload or upload['class'] != 'upload':
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

        db.update_entry(entry_id, upload_data)

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


# ============================================================================
# ATTACHMENT ROUTES
# ============================================================================

@entries_bp.route('/attachment/<int:attachment_id>/download')
def download_attachment(attachment_id):
    """Download an attachment file."""
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
        return send_file(
            BytesIO(decrypted),
            as_attachment=True,
            download_name=attachment['filename']
        )
    else:
        return send_file(filepath, 
                         as_attachment=True, 
                         download_name=attachment['filename'])


@entries_bp.route('/attachment/<int:attachment_id>/view')
def view_attachment(attachment_id):
    """View an attachment file in browser."""
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
        # Guess mimetype from filename
        import mimetypes
        mimetype = mimetypes.guess_type(attachment['filename'])[0] or 'application/octet-stream'
        return send_file(
            BytesIO(decrypted),
            as_attachment=False,
            download_name=attachment['filename'],
            mimetype=mimetype
        )
    else:
        return send_file(filepath, as_attachment=False)


@entries_bp.route('/attachment/<int:attachment_id>/delete', methods=['POST'])
def delete_attachment(attachment_id):
    """Delete an attachment file and database record."""
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


# ============================================================================
# ENTRY REDACTION ROUTES
# ============================================================================

@entries_bp.route('/client/<int:client_id>/redact')
def redact_entries_page(client_id):
    """Show page listing locked entries that can be redacted."""
    client = db.get_client(client_id)
    if not client:
        return "Client not found", 404
    
    client['type'] = db.get_client_type(client['type_id'])
    
    conn = db.connect()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get all locked, non-redacted, non-billed entries for this client
    # Only entry types that lock immediately: session, communication, absence, item
    cursor.execute("""
        SELECT * FROM entries 
        WHERE client_id = ? 
          AND locked = 1 
          AND is_redacted = 0
          AND statement_id IS NULL
          AND class IN ('session', 'communication', 'absence', 'item')
        ORDER BY created_at DESC
    """, (client_id,))
    
    entries = [dict(row) for row in cursor.fetchall()]
    
    return render_template('redact_entries.html', 
                          client=client, 
                          entries=entries)


@entries_bp.route('/client/<int:client_id>/redact/<int:entry_id>', methods=['POST'])
def redact_entry(client_id, entry_id):
    """Perform redaction on a specific entry."""
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
