"""Session entry routes (create + edit, with numbering/amendment).

Extracted from the entries.py split (Step B-I).
"""
from datetime import datetime
import time

import sqlcipher3 as sqlite3
from flask import render_template, request, redirect, url_for
from web.utils import parse_date_from_form, get_today_date_parts, get_link_group_fees
from web.blueprints.entries.common import entries_bp, get_db, safe_float, safe_money, safe_int, renumber_sessions


def _two_note_enabled():
    """Whether the Reflections field is offered.

    Off hides the control; it does not delete anything. Existing reflections
    stay in the database and reappear when it is switched back on.
    """
    return get_db().get_setting('two_note_system', 'false') == 'true'


@entries_bp.route('/client/<int:client_id>/session', methods=['GET', 'POST'])
def create_session(client_id):
    """Create a new session entry for a client."""
    db = get_db()
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
            'duration': safe_int(request.form.get('duration')),
            'base_fee': safe_money(request.form.get('base_fee')),
            'tax_rate': safe_float(request.form.get('tax_rate')),
            'fee': safe_money(request.form.get('fee')),
            'is_consultation': is_consultation,
            'is_pro_bono': is_pro_bono,
            
            'mood': request.form.get('mood') or None,
            'affect': request.form.get('affect') or None,
            'risk_assessment': request.form.get('risk_assessment') or None,
            
            'content': request.form.get('content') or None,
            # Two-note system. Absent field means no change / not enabled;
            # the toggle hides the control, so a hidden field must never
            # overwrite what is already stored.
            **({'reflections': request.form.get('reflections') or None}
               if 'reflections' in request.form else {}),
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
        
    link_group_fees = get_link_group_fees(db, client_id, include_duration=True)

    conn = db.connect()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

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
                        two_note_system=_two_note_enabled(),
                        prev_session_id=prev_session_id,
                        next_session_id=next_session_id)


@entries_bp.route('/client/<int:client_id>/session/<int:entry_id>', methods=['GET', 'POST'])
def edit_session(client_id, entry_id):
    """Edit an existing session entry."""
    db = get_db()
    
    # Get client info
    client = db.get_client(client_id)
    if not client:
        return "Client not found", 404
    
    # Get client type for defaults
    client_type = db.get_client_type(client['type_id'])
    
    # Get existing session entry
    session_entry = db.get_entry(entry_id)
    
    # Verify entry belongs to this client (CODE_REVIEW M6)
    if not session_entry or session_entry['class'] != 'session' or session_entry['client_id'] != client_id:
        return "Session not found", 404
    
    # Redirect to redacted view if this entry has been redacted
    if session_entry.get('is_redacted'):
        return redirect(url_for('entries.view_redacted_entry', 
                                client_id=client_id, entry_id=entry_id))
    
    if request.method == 'POST':
        # Get the old session data for comparison
        old_session = session_entry.copy()
        
        # Check if entry is billed (has statement_id) - billing fields cannot be changed
        is_billed = session_entry.get('statement_id') is not None
        
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
            'duration': old_session.get('duration') if is_billed else safe_int(request.form.get('duration')),
            'base_fee': old_session.get('base_fee') if is_billed else safe_money(request.form.get('base_fee')),
            'tax_rate': old_session.get('tax_rate') if is_billed else safe_float(request.form.get('tax_rate')),
            'fee': old_session.get('fee') if is_billed else safe_money(request.form.get('fee')),
            'is_consultation': is_consultation,
            'is_pro_bono': is_pro_bono,
            'modified_at': int(time.time()),
            
            # Clinical fields (always editable)
            'mood': request.form.get('mood') or None,
            'affect': request.form.get('affect') or None,
            'risk_assessment': request.form.get('risk_assessment') or None,
            
            # Content (always editable)
            'content': request.form.get('content') or None,
            **({'reflections': request.form.get('reflections') or None}
               if 'reflections' in request.form else {}),
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
            session_data['description'] = f"Session {session_entry['session_number']} (Pro Bono)"
        else:
            # Keep existing session number
            session_data['description'] = f"Session {session_entry['session_number']}"
        
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
                else:
                    # No-change save on a locked entry: make it a true no-op.
                    # Writing would bump modified_at past the last amendment,
                    # asserting an edit the amendment trail doesn't show.
                    # (The form disables Save until dirty; this guards stale
                    # tabs and double-submits at the data layer.)
                    return redirect(url_for('clients.client_file', client_id=client_id))
            
        # Save updated session
        db.update_entry(entry_id, session_data, allow_locked=True)
        
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
    if session_entry.get('session_date'):
        session_dt = datetime.fromtimestamp(session_entry['session_date'])
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
    link_group_fees = get_link_group_fees(db, client_id, include_duration=True)

    # Check if entry is locked
    is_locked = db.is_entry_locked(entry_id)
    
    # Get edit history if locked
    edit_history = db.get_edit_history(entry_id) if is_locked else []
    
    return render_template('entry_forms/session.html',
                         two_note_system=_two_note_enabled(),
                         client=client,
                         client_type=client_type,
                         session=session_entry,
                         profile_override=profile_override,
                         profile_fees=profile_fees,
                         link_group_fees=link_group_fees,
                         session_year=session_year,
                         session_month=session_month,
                         session_day=session_day,
                         is_edit=True,
                         is_locked=is_locked,
                         is_billed=session_entry.get('statement_id') is not None,
                         edit_history=edit_history,
                         prev_session_id=prev_session_id,
                         next_session_id=next_session_id)
