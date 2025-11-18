@app.route('/client/<int:client_id>/session/<int:entry_id>', methods=['GET', 'POST'])
def edit_session(client_id, entry_id):
    """Edit an existing session entry."""
    import time
    from datetime import datetime
    
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
    
    if request.method == 'POST':
        # Get the old session data for comparison
        old_session = session.copy()
        
        # Check if consultation
        is_consultation = 1 if request.form.get('is_consultation') else 0
        is_pro_bono = 1 if request.form.get('is_pro_bono') else 0
        
        # Parse date from dropdowns
        year = request.form.get('year')
        month = request.form.get('month')
        day = request.form.get('day')
        
        session_date_timestamp = None
        if year and month and day:
            date_str = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            session_date_timestamp = int(datetime.strptime(date_str, '%Y-%m-%d').timestamp())
        
        # Update session data
        session_data = {
            'modality': request.form.get('modality'),
            'format': request.form.get('format'),
            'session_date': session_date_timestamp,
            'session_time': request.form.get('session_time') or None,
            'duration': int(request.form.get('duration')) if request.form.get('duration') else None,
            'base_fee': float(request.form.get('base_fee')) if request.form.get('base_fee') else None,
            'tax_rate': float(request.form.get('tax_rate')) if request.form.get('tax_rate') else None,
            'fee': float(request.form.get('fee')) if request.form.get('fee') else None,
            'is_consultation': is_consultation,
            'is_pro_bono': is_pro_bono,
            'modified_at': int(time.time()),
            
            # Clinical fields (optional)
            'mood': request.form.get('mood') or None,
            'affect': request.form.get('affect') or None,
            'risk_assessment': request.form.get('risk_assessment') or None,
            
            # Content
            'content': request.form.get('content') or None,
        }
        
        # Update description based on consultation/pro bono status
        if is_consultation:
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
        
        # Check if entry is locked - if so, log changes to edit history
        if db.is_entry_locked(entry_id):
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
            
            # Clinical fields
            if old_session.get('mood') != session_data.get('mood'):
                changes.append(f"Mood: {old_session.get('mood') or 'None'} → {session_data.get('mood') or 'None'}")
            
            if old_session.get('affect') != session_data.get('affect'):
                changes.append(f"Affect: {old_session.get('affect') or 'None'} → {session_data.get('affect') or 'None'}")
            
            if old_session.get('risk_assessment') != session_data.get('risk_assessment'):
                changes.append(f"Risk: {old_session.get('risk_assessment') or 'None'} → {session_data.get('risk_assessment') or 'None'}")
            
            # Notes (with smart truncated diff)
            if old_session.get('content') != session_data.get('content'):
                old_content = old_session.get('content') or ''
                new_content = session_data.get('content') or ''
                
                # Find where they differ
                if old_content and new_content:
                    # Find first difference
                    diff_start = 0
                    for i in range(min(len(old_content), len(new_content))):
                        if old_content[i] != new_content[i]:
                            diff_start = i
                            break
                    
                    # Show context around the change (50 chars before/after)
                    context_start = max(0, diff_start - 25)
                    context_end = min(len(old_content), diff_start + 75)
                    
                    old_snippet = old_content[context_start:context_end]
                    new_snippet = new_content[context_start:min(len(new_content), context_start + 100)]
                    
                    # Add ellipsis if truncated
                    if context_start > 0:
                        old_snippet = '...' + old_snippet
                        new_snippet = '...' + new_snippet
                    if context_end < len(old_content):
                        old_snippet = old_snippet + '...'
                    if context_start + 100 < len(new_content):
                        new_snippet = new_snippet + '...'
                    
                    changes.append(f"Notes: '{old_snippet}' → '{new_snippet}'")
                elif old_content:
                    changes.append("Notes: Cleared")
                else:
                    changes.append("Notes: Added")
            
            if changes:
                change_desc = "; ".join(changes)
                db.add_to_edit_history(entry_id, change_desc)
        
        # Save updated session
        db.update_entry(entry_id, session_data)
        
        return redirect(url_for('client_file', client_id=client_id))
    
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
    if profile and profile.get('fee_override_total'):
        profile_override = {
            'base': profile['fee_override_base'],
            'tax': profile['fee_override_tax_rate'],
            'total': profile['fee_override_total']
        }
    
    # 2. Client Type
    client_type_fees = {
        'base': client_type.get('session_base_price') or 0,
        'tax': client_type.get('session_tax_rate') or 0,
        'total': client_type.get('session_fee') or 0
    }
    
    # 3. Link Groups (by format)
    link_group_fees = {}
    
    # Get all link groups this client is in
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
    
    conn.close()
    
    # Check if entry is locked
    is_locked = db.is_entry_locked(entry_id)
    
    # Get edit history if locked
    edit_history = db.get_edit_history(entry_id) if is_locked else []
    
    return render_template('entry_forms/session.html',
                         client=client,
                         client_type=client_type,
                         session=session,  # Pass the actual session data
                         profile_override=profile_override,
                         client_type_fees=client_type_fees,
                         link_group_fees=link_group_fees,
                         session_year=session_year,
                         session_month=session_month,
                         session_day=session_day,
                         is_edit=True,
                         is_locked=is_locked,
                         edit_history=edit_history,
                         prev_session_id=prev_session_id,
                         next_session_id=next_session_id)
