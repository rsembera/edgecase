# -*- coding: utf-8 -*-
"""
EdgeCase Clients Blueprint
Handles main client management (list, add, view, change type)
"""

from flask import Blueprint, render_template, request, redirect, url_for, session, send_file, jsonify
from pathlib import Path
from datetime import datetime, timedelta
import sqlcipher3 as sqlite3

from core.database import Database

# Initialize blueprint
clients_bp = Blueprint('clients', __name__)

# Database instance (set by init_blueprint)
db = None

def init_blueprint(database):
    """Initialize blueprint with database instance"""
    global db
    db = database


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def parse_time_to_seconds(time_str):
    """
    Parse various time formats into seconds since midnight for sorting.
    Supports: "2:00 PM", "2:00 p.m.", "2:00pm", "14:00", "2 PM", "2pm", "14:30", "1:00" (assumes AM), etc.
    Returns None if parsing fails or time is invalid.
    """
    if not time_str or not isinstance(time_str, str):
        return None
    
    # Normalize: uppercase, remove spaces and periods
    time_str = time_str.strip().upper().replace('.', '').replace(' ', '')
    
    try:
        # Check for AM/PM
        is_pm = 'PM' in time_str
        is_am = 'AM' in time_str
        
        # Remove AM/PM markers
        time_str = time_str.replace('AM', '').replace('PM', '')
        
        # Split hours and minutes
        if ':' in time_str:
            parts = time_str.split(':')
            hours = int(parts[0])
            minutes = int(parts[1]) if len(parts) > 1 else 0
        else:
            hours = int(time_str)
            minutes = 0
        
        # Validate bounds
        if hours < 0 or hours > 23 or minutes < 0 or minutes > 59:
            return None  # Invalid time, will fall back to creation timestamp
        
        # Convert to 24-hour format
        if is_pm and hours != 12:
            hours += 12
        elif is_am and hours == 12:
            hours = 0
        
        return hours * 3600 + minutes * 60
            
    except (ValueError, IndexError):
        # If parsing fails, return None (will sort with creation timestamp)
        return None


def cleanup_inactive_client_links(client_id):
    """Remove inactive client from all link groups and delete groups with <2 members."""
    conn = db.connect()
    cursor = conn.cursor()
    
    # Get all groups this client is in
    cursor.execute("""
        SELECT DISTINCT group_id 
        FROM client_links 
        WHERE client_id_1 = ?
    """, (client_id,))
    
    group_ids = [row[0] for row in cursor.fetchall()]
    
    groups_deleted = 0
    
    for group_id in group_ids:
        # Remove this client from the group
        cursor.execute("""
            DELETE FROM client_links 
            WHERE group_id = ? AND client_id_1 = ?
        """, (group_id, client_id))
        
        # Check how many members remain
        cursor.execute("""
            SELECT COUNT(DISTINCT client_id_1) 
            FROM client_links 
            WHERE group_id = ?
        """, (group_id,))
        
        remaining_members = cursor.fetchone()[0]
        
        # If less than 2 members, delete the entire group
        if remaining_members < 2:
            cursor.execute("DELETE FROM client_links WHERE group_id = ?", (group_id,))
            cursor.execute("DELETE FROM link_groups WHERE id = ?", (group_id,))
            groups_deleted += 1
    
    conn.commit()


# ============================================================================
# CLIENT ROUTES
# ============================================================================

@clients_bp.route('/')
def index():
    """Main view - client list with stats cards."""
    # Get filter parameters
    type_filter = request.args.getlist('type')
    sort_by = request.args.get('sort', 'last_name')
    sort_order = request.args.get('order', 'asc')
    search = request.args.get('search', '')
    
    # Get view preference - check URL first, then session, then default
    view_mode = request.args.get('view')
    if view_mode:
        session['view_preference'] = view_mode
    else:
        view_mode = session.get('view_preference', 'compact')
    
    # Get all client types for filter
    all_types = db.get_all_client_types()
    
    # If no types selected, default to all non-locked types
    if not type_filter:
        type_filter = [str(t['id']) for t in all_types if not t.get('is_system_locked')]
        
    # Get clients
    if search:
        clients = db.search_clients(search)
        clients = [c for c in clients if str(c['type_id']) in type_filter]
    else:
        clients = []
        for type_id in type_filter:
            clients.extend(db.get_all_clients(int(type_id)))
    
    # Calculate stats (for all clients, not just filtered)
    all_clients = []
    for client_type in all_types:
        all_clients.extend(db.get_all_clients(client_type['id']))
    
    # Count active clients (all non-inactive clients)
    inactive_type = next((t for t in all_types if t['name'] == 'Inactive'), None)
    active_count = len([c for c in all_clients if c['type_id'] != inactive_type['id']]) if inactive_type else len(all_clients)
    
    # Count sessions this month (lookback from 1st 00:00 to now)
    now = datetime.now()
    now_ts = int(now.timestamp())
    month_start = datetime(now.year, now.month, 1, 0, 0, 0)
    month_start_ts = int(month_start.timestamp())
    
    sessions_this_month = 0
    for client in all_clients:
        entries = db.get_client_entries(client['id'], entry_class='session')
        sessions_this_month += sum(1 for e in entries 
                                   if month_start_ts <= e.get('session_date', 0) <= now_ts
                                   and not e.get('is_consultation'))
    
    # Count pending invoices (statement portions not fully paid)
    pending_invoices = db.count_pending_invoices()
            
    # Calculate unbilled this month
    now = datetime.now()
    month_start = int(datetime(now.year, now.month, 1).timestamp())
    
    billable_this_month = 0
    for client in all_clients:
        entries = db.get_client_entries(client['id'])
        for entry in entries:
            # Skip if already billed or still a draft
            if entry.get('statement_id') is not None:
                continue
            if not entry.get('locked'):
                continue
                
            # Use appropriate date field for each type
            if entry.get('class') == 'session' and not entry.get('is_consultation'):
                entry_date = entry.get('session_date', 0)
                if entry_date >= month_start:
                    billable_this_month += entry.get('fee', 0) or 0
            elif entry.get('class') == 'item':
                entry_date = entry.get('item_date', 0)
                if entry_date >= month_start:
                    billable_this_month += entry.get('fee', 0) or 0
            elif entry.get('class') == 'absence':
                entry_date = entry.get('absence_date', 0)
                if entry_date >= month_start:
                    billable_this_month += entry.get('fee', 0) or 0
                    
    # Get current date and time
    current_date = now.strftime('%B %d, %Y')
    time_format = db.get_setting('time_format', '12h')
    if time_format == '24h':
        current_time = now.strftime('%H:%M')
    else:
        current_time = now.strftime('%I:%M %p').lstrip('0')
    
    # Add type information and additional data to each client
    for client in clients:
        client['type'] = db.get_client_type(client['type_id'])
        
        # Get profile entry for contact info
        profile = db.get_profile_entry(client['id'])
        client['email'] = profile.get('email', '') if profile else ''
        client['phone'] = profile.get('phone', '') if profile else ''
        client['home_phone'] = profile.get('home_phone', '') if profile else ''
        client['work_phone'] = profile.get('work_phone', '') if profile else ''
        client['text_number'] = profile.get('text_number', '') if profile else ''
        client['preferred_contact'] = profile.get('preferred_contact', '') if profile else ''
        client['ok_to_leave_message'] = profile.get('ok_to_leave_message', 'yes') if profile else 'yes'
        
        # Smart phone display based on preferred contact method
        client['display_phone'] = ''
        client['contact_type'] = 'call'
        client['contact_icon'] = '<i data-lucide="phone"></i>'
        
        if client['preferred_contact'] == 'call_cell':
            client['display_phone'] = client['phone']
            client['contact_type'] = 'call'
            client['contact_icon'] = '<i data-lucide="phone"></i>'
        elif client['preferred_contact'] == 'call_home':
            client['display_phone'] = client['home_phone']
            client['contact_type'] = 'call'
            client['contact_icon'] = '<i data-lucide="phone"></i>'
        elif client['preferred_contact'] == 'call_work':
            client['display_phone'] = client['work_phone']
            client['contact_type'] = 'call'
            client['contact_icon'] = '<i data-lucide="phone"></i>'
        elif client['preferred_contact'] == 'text':
            if client['text_number'] == 'none':
                client['display_phone'] = client['phone'] or client['home_phone'] or client['work_phone']
                client['contact_type'] = 'call'
                client['contact_icon'] = '<i data-lucide="phone"></i>'
            elif client['text_number'] == 'cell':
                client['display_phone'] = client['phone']
                client['contact_type'] = 'text'
                client['contact_icon'] = '<i data-lucide="message-circle"></i>'
            elif client['text_number'] == 'home':
                client['display_phone'] = client['home_phone']
                client['contact_type'] = 'text'
                client['contact_icon'] = '<i data-lucide="message-circle"></i>'
            elif client['text_number'] == 'work':
                client['display_phone'] = client['work_phone']
                client['contact_type'] = 'text'
                client['contact_icon'] = '<i data-lucide="message-circle"></i>'
            else:
                client['display_phone'] = client['phone']
                client['contact_type'] = 'text'
                client['contact_icon'] = '<i data-lucide="message-circle"></i>'
        elif client['preferred_contact'] == 'email':
            client['display_phone'] = client['phone'] or client['home_phone'] or client['work_phone']
            client['contact_type'] = 'call'
            client['contact_icon'] = '<i data-lucide="phone"></i>'
        else:
            client['display_phone'] = client['phone']
            client['contact_type'] = 'call'
            client['contact_icon'] = '<i data-lucide="phone"></i>'
        
        # Final fallback if display_phone is still empty but phones exist
        if not client['display_phone']:
            client['display_phone'] = client['phone'] or client['home_phone'] or client['work_phone']
        
        # Get last session date
        last_session = db.get_last_session_date(client['id'])
        client['last_session'] = last_session
        
        # Get payment status
        client['payment_status'] = db.get_payment_status(client['id'])
        
        # Check if client is linked to others
        client['is_linked'] = db.is_client_linked(client['id'])
    
    # Sort clients 
    if sort_by == 'file_number':
        clients.sort(key=lambda c: c['file_number'], reverse=(sort_order == 'desc'))
    elif sort_by == 'last_name':
        clients.sort(key=lambda c: c['last_name'].lower(), reverse=(sort_order == 'desc'))
    elif sort_by == 'first_name':
        clients.sort(key=lambda c: c['first_name'].lower(), reverse=(sort_order == 'desc'))
    elif sort_by == 'created':
        clients.sort(key=lambda c: c['created_at'], reverse=(sort_order == 'desc'))
    elif sort_by == 'last_session':
        clients.sort(key=lambda c: c.get('last_session') or 0, reverse=(sort_order == 'desc'))
    
    # Check for backup warning (pop so it only shows once)
    backup_warning = session.pop('backup_warning', None)
    
    # Get currency for display
    currency = db.get_setting('currency', 'CAD')
    
    return render_template('main_view.html',
                         clients=clients,
                         all_types=all_types,
                         type_filter=type_filter,
                         sort_by=sort_by,
                         sort_order=sort_order,
                         search=search,
                         view_mode=view_mode,
                         active_count=active_count,
                         sessions_this_month=sessions_this_month,
                         pending_invoices=pending_invoices,
                         billable_this_month=billable_this_month,
                         current_date=current_date,
                         current_time=current_time,
                         backup_warning=backup_warning,
                         currency=currency)


@clients_bp.route('/add_client', methods=['GET', 'POST'])
def add_client():
    """Add new client with auto-generated file number support."""
    if request.method == 'POST':
        # Get file number format setting
        format_type = db.get_setting('file_number_format', 'manual')
        
        # Generate file number based on format
        if format_type == 'manual':
            file_number = request.form['file_number'].strip()
            
            # Check for collision on manual entry
            if db.file_number_exists(file_number):
                all_types = db.get_all_client_types()
                return render_template('add_client.html',
                                     all_types=all_types,
                                     file_number_preview='',
                                     file_number_readonly=False,
                                     file_number_format=format_type,
                                     error=f"File number '{file_number}' already exists. Please choose a different one.",
                                     form_data=request.form)
        
        elif format_type == 'date-initials':
            date_str = datetime.now().strftime('%Y%m%d')
            
            first = request.form['first_name'][0].upper()
            middle = request.form.get('middle_name', '')
            middle = middle[0].upper() if middle else ''
            last = request.form['last_name'][0].upper()
            
            initials = first + middle + last
            base_file_number = f"{date_str}-{initials}"
            
            # Handle collisions by adding suffix
            file_number = base_file_number
            suffix = 2
            while db.file_number_exists(file_number):
                file_number = f"{base_file_number}-{suffix}"
                suffix += 1
                # Safety limit to prevent infinite loops
                if suffix > 100:
                    all_types = db.get_all_client_types()
                    return render_template('add_client.html',
                                         all_types=all_types,
                                         file_number_preview=base_file_number,
                                         file_number_readonly=True,
                                         file_number_format=format_type,
                                         error="Too many clients with similar initials today. Please use manual file number.",
                                         form_data=request.form)
        
        elif format_type == 'prefix-counter':
            prefix = db.get_setting('file_number_prefix', '')
            suffix = db.get_setting('file_number_suffix', '')
            counter = int(db.get_setting('file_number_counter', '1'))
            
            parts = []
            if prefix:
                parts.append(prefix)
            parts.append(str(counter).zfill(4))
            if suffix:
                parts.append(suffix)
            
            file_number = '-'.join(parts)
            
            # Handle unlikely collision (if someone manually used a number)
            while db.file_number_exists(file_number):
                counter += 1
                parts = []
                if prefix:
                    parts.append(prefix)
                parts.append(str(counter).zfill(4))
                if suffix:
                    parts.append(suffix)
                file_number = '-'.join(parts)
            
            db.set_setting('file_number_counter', str(counter + 1))
        
        else:
            file_number = request.form['file_number']
        
        # Get form data
        client_data = {
            'file_number': file_number,
            'first_name': request.form['first_name'],
            'middle_name': request.form.get('middle_name', ''),
            'last_name': request.form['last_name'],
            'type_id': int(request.form['type_id']),
            'session_offset': int(request.form.get('session_offset', 0))
        }
        
        # Add client to database
        try:
            client_id = db.add_client(client_data)
        except Exception as e:
            # Catch any remaining database errors
            all_types = db.get_all_client_types()
            return render_template('add_client.html',
                                 all_types=all_types,
                                 file_number_preview='',
                                 file_number_readonly=(format_type != 'manual'),
                                 file_number_format=format_type,
                                 error=f"Error creating client: {str(e)}",
                                 form_data=request.form)
        
        # Redirect to client file to create profile entry
        return redirect(url_for('clients.client_file', client_id=client_id))
    
    # GET request - show form
    all_types = db.get_all_client_types()
    
    # Get file number format for UI
    format_type = db.get_setting('file_number_format', 'manual')
    
    # Generate preview/placeholder based on format
    file_number_preview = ''
    file_number_readonly = False
    
    if format_type == 'date-initials':
        date_str = datetime.now().strftime('%Y%m%d')
        file_number_preview = f"{date_str}-ABC"
        file_number_readonly = True
    
    elif format_type == 'prefix-counter':
        prefix = db.get_setting('file_number_prefix', '')
        suffix = db.get_setting('file_number_suffix', '')
        counter = int(db.get_setting('file_number_counter', '1'))
        
        parts = []
        if prefix:
            parts.append(prefix)
        parts.append(str(counter).zfill(4))
        if suffix:
            parts.append(suffix)
        
        file_number_preview = '-'.join(parts)
        file_number_readonly = True
    
    return render_template('add_client.html', 
                         all_types=all_types,
                         file_number_preview=file_number_preview,
                         file_number_readonly=file_number_readonly,
                         file_number_format=format_type)


@clients_bp.route('/client/<int:client_id>')
def client_file(client_id):
    """Client file view - entry timeline grouped by year/month."""
    client = db.get_client(client_id)
    if not client:
        return "Client not found", 404
    
    # Get client type
    client['type'] = db.get_client_type(client['type_id'])
    
    # Get all client types for the type change dropdown
    all_types = db.get_all_client_types()
    
    # Get class filter from query params
    class_filter = request.args.getlist('class')
    
    # Default: show all classes if none selected
    if not class_filter:
        class_filter = ['session', 'consultation', 'communication', 'absence', 'item', 'upload']
    
    # Get profile entry separately (pinned at top)
    profile_entry = db.get_profile_entry(client_id)
    
    # Get linked clients
    linked_groups = []
    
    conn = db.connect()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get all groups this client belongs to
    cursor.execute("""
        SELECT DISTINCT lg.id, lg.format
        FROM link_groups lg
        JOIN client_links cl ON cl.group_id = lg.id
        WHERE cl.client_id_1 = ?
    """, (client_id,))
    
    group_rows = cursor.fetchall()
    
    for group_row in group_rows:
        group_id = group_row['id']
        format_type = group_row['format']
        
        # Get all members of this group (excluding current client)
        cursor.execute("""
            SELECT DISTINCT c.id, c.file_number, c.first_name, c.middle_name, c.last_name, c.type_id
            FROM clients c
            JOIN client_links cl ON cl.client_id_1 = c.id
            WHERE cl.group_id = ? AND c.id != ?
            ORDER BY c.last_name, c.first_name
        """, (group_id, client_id))
        
        member_rows = cursor.fetchall()
        
        members = []
        for member_row in member_rows:
            member = dict(member_row)
            member['type'] = db.get_client_type(member['type_id'])
            members.append(member)
        
        if members:
            linked_groups.append({
                'id': group_id,
                'format': format_type,
                'format_display': format_type.capitalize() if format_type else 'Unknown',
                'members': members
            })
    
    
    # Get ALL entries for this client
    all_entries = db.get_client_entries(client_id)
    
    # Get current time for calculations
    now = datetime.now()
    
    # Filter to get only sessions for counting
    session_entries = [e for e in all_entries if e['class'] == 'session']
    session_count = sum(1 for e in session_entries if not e.get('is_consultation'))
    consultation_count = sum(1 for e in session_entries if e.get('is_consultation'))
    
    # Count absences for this calendar year only
    year_start = int(datetime(now.year, 1, 1).timestamp())
    absence_entries = [e for e in all_entries if e['class'] == 'absence' and (e.get('absence_date') or 0) >= year_start]
    absence_count = len(absence_entries)
    
    # Filter entries by selected classes for display
    filtered_entries = []
    for entry in all_entries:
        if entry['class'] == 'session':
            if entry.get('is_consultation'):
                if 'consultation' in class_filter:
                    filtered_entries.append(entry)
            else:
                if 'session' in class_filter:
                    filtered_entries.append(entry)
        elif entry['class'] in class_filter:
            filtered_entries.append(entry)
    
    # Group entries by year and month
    from collections import defaultdict
    
    current_year = now.year
    current_month = now.month
    
    year_dict = defaultdict(lambda: defaultdict(list))
    
    for entry in filtered_entries:
        # Determine date field based on entry class
        date_field = None
        if entry['class'] == 'session' and entry.get('session_date'):
            date_field = entry['session_date']
        elif entry['class'] == 'communication' and entry.get('comm_date'):
            date_field = entry['comm_date']
        elif entry['class'] == 'absence' and entry.get('absence_date'):
            date_field = entry['absence_date']
        elif entry['class'] == 'item' and entry.get('item_date'):
            date_field = entry['item_date']
        elif entry['class'] == 'upload' and entry.get('upload_date'):
            date_field = entry['upload_date']
        
        if date_field:
            entry_date = datetime.fromtimestamp(date_field)
            year = entry_date.year
            month = entry_date.month
            year_dict[year][month].append(entry)
    
    # Convert to list structure for template
    entries_by_year = []
    for year in sorted(year_dict.keys(), reverse=True):
        months = []
        year_total = 0
        
        for month in sorted(year_dict[year].keys(), reverse=True):
            # Sort entries by date, then manual time, then created_at
            def get_entry_sort_key(e):
                # Get manual date field if set
                date_val = 0
                if e['class'] == 'session':
                    date_val = e.get('session_date', 0)
                elif e['class'] == 'communication':
                    date_val = e.get('comm_date', 0)
                elif e['class'] == 'absence':
                    date_val = e.get('absence_date', 0)
                elif e['class'] == 'item':
                    date_val = e.get('item_date', 0)
                elif e['class'] == 'upload':
                    date_val = e.get('upload_date', 0)
                
                # Fall back to created_at if no manual date
                created_at = e.get('created_at', 0)
                if not date_val:
                    date_val = created_at
                
                # Normalize date to midnight for consistent comparison
                if date_val:
                    entry_dt = datetime.fromtimestamp(date_val)
                    date_val = int(datetime(entry_dt.year, entry_dt.month, entry_dt.day).timestamp())
                
                # Get manual time field if set
                time_str = None
                if e['class'] == 'session':
                    time_str = e.get('session_time')
                elif e['class'] == 'communication':
                    time_str = e.get('comm_time')
                elif e['class'] == 'absence':
                    time_str = e.get('absence_time')
                elif e['class'] == 'item':
                    time_str = e.get('item_time')
                elif e['class'] == 'upload':
                    time_str = e.get('upload_time')
                
                time_val = None
                if time_str:
                    time_val = parse_time_to_seconds(time_str)
                
                # Fall back to time-of-day from created_at if no manual time
                if time_val is None:
                    created_dt = datetime.fromtimestamp(created_at)
                    time_val = created_dt.hour * 3600 + created_dt.minute * 60 + created_dt.second
                
                return (date_val, time_val, created_at)
            
            month_entries = sorted(year_dict[year][month], 
                                 key=get_entry_sort_key, 
                                 reverse=True)
            
            month_name = datetime(year, month, 1).strftime('%B')
            
            months.append({
                'month_num': month,
                'month_name': month_name,
                'entries': month_entries,
                'is_current': (year == current_year and month == current_month)
            })
            
            year_total += len(month_entries)
        
        entries_by_year.append({
            'year': year,
            'months': months,
            'total': year_total,
            'is_current': (year == current_year)
        })
    
    return render_template('client_file.html',
                         client=client,
                         all_types=all_types,
                         profile_entry=profile_entry,
                         entries_by_year=entries_by_year,
                         session_count=session_count,
                         consultation_count=consultation_count,
                         absence_count=absence_count,
                         class_filter=class_filter,
                         linked_groups=linked_groups)


@clients_bp.route('/client/<int:client_id>/change_type', methods=['POST'])
def change_client_type(client_id):
    """Change a client's type via dropdown."""
    import time
    
    type_id = request.form.get('type_id')
    
    if not type_id:
        return redirect(url_for('clients.client_file', client_id=client_id))
    
    # Get current client data
    client = db.get_client(client_id)
    if not client:
        return redirect(url_for('clients.index'))
    
    # Get the new type to check if it's "Inactive"
    new_type = db.get_client_type(int(type_id))
    
    # Update client with all fields plus new type
    client_updates = {
        'file_number': client['file_number'],
        'first_name': client['first_name'],
        'middle_name': client.get('middle_name'),
        'last_name': client['last_name'],
        'type_id': int(type_id),
        'modified_at': int(time.time())
    }
    db.update_client(client_id, client_updates)
    
   # If changing to Inactive, remove from link groups AND snapshot retention
    if new_type and new_type['name'] == 'Inactive':
        # Get retention from CURRENT type (before change)
        current_type = db.get_client_type(client['type_id'])
        retention_days = current_type.get('retention_period') if current_type else None
        
        cleanup_inactive_client_links(client_id)
        db.snapshot_retention_on_inactive(client_id, retention_days)
    
    # Redirect back to where they came from (referrer)
    referrer = request.referrer
    if referrer and 'profile' in referrer:
        return redirect(url_for('entries.edit_profile', client_id=client_id))
    else:
        return redirect(url_for('clients.client_file', client_id=client_id))
    
# ============================================================
# RETENTION ROUTES
# Add these routes to clients.py (web/blueprints/clients.py)
# ============================================================

@clients_bp.route('/api/retention-check')
def retention_check():
    """Check for clients due for deletion. Returns JSON."""
    clients_due = db.get_clients_due_for_deletion()
    
    # Format dates for display
    from datetime import datetime
    for client in clients_due:
        client['first_contact_display'] = datetime.fromtimestamp(client['first_contact']).strftime('%Y-%m-%d')
        client['last_contact_display'] = datetime.fromtimestamp(client['last_contact']).strftime('%Y-%m-%d')
        client['retain_until_display'] = datetime.fromtimestamp(client['retain_until']).strftime('%Y-%m-%d')
    
    return jsonify({'clients_due': clients_due})


@clients_bp.route('/api/retention-delete', methods=['POST'])
def retention_delete():
    """Delete selected clients that are due for retention deletion."""
    data = request.get_json()
    client_ids = data.get('client_ids', [])
    
    if not client_ids:
        return jsonify({'success': False, 'error': 'No clients selected'}), 400
    
    # Verify all clients are actually due for deletion (security check)
    clients_due = db.get_clients_due_for_deletion()
    due_ids = {c['id'] for c in clients_due}
    
    results = {'deleted': [], 'failed': [], 'skipped': []}
    
    for client_id in client_ids:
        if client_id not in due_ids:
            results['skipped'].append(client_id)
            continue
        
        success = db.archive_and_delete_client(client_id)
        if success:
            results['deleted'].append(client_id)
        else:
            results['failed'].append(client_id)
    
    return jsonify({
        'success': True,
        'results': results
    })


@clients_bp.route('/deleted-clients')
def deleted_clients():
    """View deleted client records."""
    deleted = db.get_deleted_clients()
    
    # Format dates for display
    from datetime import datetime
    for client in deleted:
        client['first_contact_display'] = datetime.fromtimestamp(client['first_contact']).strftime('%Y-%m-%d') if client['first_contact'] else '-'
        client['last_contact_display'] = datetime.fromtimestamp(client['last_contact']).strftime('%Y-%m-%d') if client['last_contact'] else '-'
        client['retain_until_display'] = datetime.fromtimestamp(client['retain_until']).strftime('%Y-%m-%d') if client['retain_until'] else '-'
        client['deleted_at_display'] = datetime.fromtimestamp(client['deleted_at']).strftime('%Y-%m-%d %H:%M')
    
    return render_template('deleted_clients.html', deleted=deleted)

@clients_bp.route('/client/<int:client_id>/export')
def export_client(client_id):
    """Show the export page for a client."""
    client = db.get_client(client_id)
    if not client:
        return "Client not found", 404
    
    client_type = db.get_client_type(client['type_id'])
    
    # Default date range (current year)
    now = datetime.now()
    
    return render_template('export.html',
                         client=client,
                         client_type=client_type,
                         default_start_year=now.year,
                         default_start_month=1,
                         default_start_day=1,
                         default_end_year=now.year,
                         default_end_month=now.month,
                         default_end_day=now.day)

@clients_bp.route('/client/<int:client_id>/session-report', methods=['GET'])
def session_report(client_id):
    """Generate a client report (sessions, items, absences)."""
    client = db.get_client(client_id)
    if not client:
        return "Client not found", 404
    
    # Check if this is a generate request (has date params) or form display
    if request.args.get('start_year'):
        # Generate the PDF
        from pdf.generator import generate_client_report_pdf
        
        # Parse date range
        start_year = request.args.get('start_year')
        start_month = request.args.get('start_month')
        start_day = request.args.get('start_day')
        end_year = request.args.get('end_year')
        end_month = request.args.get('end_month')
        end_day = request.args.get('end_day')
        
        # Entry type options
        include_sessions = request.args.get('include_sessions') == 'on'
        include_items = request.args.get('include_items') == 'on'
        include_absences = request.args.get('include_absences') == 'on'
        include_fees = request.args.get('include_fees') == 'on'
        
        # Convert to timestamps
        start_date = None
        end_date = None
        
        if start_year and start_month and start_day:
            start_str = f"{start_year}-{start_month.zfill(2)}-{start_day.zfill(2)}"
            start_date = int(datetime.strptime(start_str, '%Y-%m-%d').timestamp())
        
        if end_year and end_month and end_day:
            end_str = f"{end_year}-{end_month.zfill(2)}-{end_day.zfill(2)}"
            # End of day
            end_date = int(datetime.strptime(end_str, '%Y-%m-%d').timestamp()) + 86399
        
        try:
            pdf_buffer = generate_client_report_pdf(
                db=db,
                client_id=client_id,
                start_date=start_date,
                end_date=end_date,
                include_sessions=include_sessions,
                include_items=include_items,
                include_absences=include_absences,
                include_fees=include_fees
            )
            
            # Generate filename
            filename = f"Report_{client['file_number']}"
            if start_date and end_date:
                start_dt = datetime.fromtimestamp(start_date)
                end_dt = datetime.fromtimestamp(end_date)
                filename += f"_{start_dt.strftime('%Y%m')}_to_{end_dt.strftime('%Y%m')}"
            filename += ".pdf"
            
            return send_file(
                pdf_buffer,
                mimetype='application/pdf',
                as_attachment=False,
                download_name=filename
            )
        except Exception as e:
            print(f"Error generating report: {e}")
            import traceback
            traceback.print_exc()
            return f"Error generating report: {str(e)}", 500
    
    # Show the form
    today = datetime.now()
    client_type = db.get_client_type(client['type_id'])
    return render_template('session_report.html',
                         client=client,
                         client_type=client_type,
                         today_year=today.year,
                         today_month=today.month,
                         today_day=today.day)

@clients_bp.route('/client/<int:client_id>/export/calculate')
def calculate_export(client_id):
    """Calculate what will be exported (returns JSON)."""
    client = db.get_client(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    # Get parameters
    entry_types = request.args.getlist('types')
    all_time = request.args.get('all_time') == '1'
    
    # Parse date range
    start_date = None
    end_date = None
    
    if not all_time:
        try:
            start_year = int(request.args.get('start_year', 0))
            start_month = int(request.args.get('start_month', 1))
            start_day = int(request.args.get('start_day', 1))
            end_year = int(request.args.get('end_year', 0))
            end_month = int(request.args.get('end_month', 12))
            end_day = int(request.args.get('end_day', 31))
            
            if start_year:
                start_date = int(datetime(start_year, start_month, start_day).timestamp())
            if end_year:
                # End of day
                end_date = int(datetime(end_year, end_month, end_day, 23, 59, 59).timestamp())
        except (ValueError, TypeError):
            pass
    
    # Count entries by type
    counts = {
        'profile': 0,
        'session': 0,
        'communication': 0,
        'absence': 0,
        'item': 0,
        'upload': 0
    }
    
    # Check profile
    if 'profile' in entry_types:
        profile = db.get_profile_entry(client_id)
        if profile:
            counts['profile'] = 1
    
    # Get all entries
    all_entries = db.get_client_entries(client_id)
    
    # Count attachments
    attachment_count = 0
    
    for entry in all_entries:
        entry_class = entry['class']
        
        # Skip if not in requested types
        if entry_class not in entry_types:
            continue
        
        # Skip profile (counted above)
        if entry_class == 'profile':
            continue
        
        # Check date range
        if start_date or end_date:
            entry_date = None
            if entry_class == 'session':
                entry_date = entry.get('session_date')
            elif entry_class == 'communication':
                entry_date = entry.get('comm_date')
            elif entry_class == 'absence':
                entry_date = entry.get('absence_date')
            elif entry_class == 'item':
                entry_date = entry.get('item_date')
            elif entry_class == 'upload':
                entry_date = entry.get('upload_date')
            
            if entry_date:
                if start_date and entry_date < start_date:
                    continue
                if end_date and entry_date > end_date:
                    continue
        
        # Count it
        if entry_class in counts:
            counts[entry_class] += 1
        
        # Count attachments for upload entries
        if entry_class == 'upload':
            attachment_count += entry.get('attachment_count', 0)
    
    total = sum(counts.values())
    
    return jsonify({
        'counts': counts,
        'total': total,
        'attachments': attachment_count
    })


@clients_bp.route('/client/<int:client_id>/export/pdf')
def export_client_pdf(client_id):
    """Generate and serve the export PDF."""
    from pdf.client_export import generate_client_export_pdf
    
    client = db.get_client(client_id)
    if not client:
        return "Client not found", 404
    
    # Get parameters
    entry_types = request.args.getlist('types')
    all_time = request.args.get('all_time') == '1'
    
    if not entry_types:
        return "No entry types selected", 400
    
    # Parse date range
    start_date = None
    end_date = None
    
    if not all_time:
        try:
            start_year = int(request.args.get('start_year', 0))
            start_month = int(request.args.get('start_month', 1))
            start_day = int(request.args.get('start_day', 1))
            end_year = int(request.args.get('end_year', 0))
            end_month = int(request.args.get('end_month', 12))
            end_day = int(request.args.get('end_day', 31))
            
            if start_year:
                start_date = int(datetime(start_year, start_month, start_day).timestamp())
            if end_year:
                end_date = int(datetime(end_year, end_month, end_day, 23, 59, 59).timestamp())
        except (ValueError, TypeError):
            pass
    
    # Generate PDF
    try:
        pdf_buffer = generate_client_export_pdf(
            db=db,
            client_id=client_id,
            entry_types=entry_types,
            start_date=start_date,
            end_date=end_date
        )
        
        # Create filename
        file_number = client['file_number'].replace(' ', '_').replace('/', '-')
        if all_time:
            filename = f"{file_number}_export.pdf"
        else:
            filename = f"{file_number}_export_{start_year}-{start_month:02d}_to_{end_year}-{end_month:02d}.pdf"
        
        return send_file(
            pdf_buffer,
            mimetype='application/pdf',
            as_attachment=False,
            download_name=filename
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"Error generating PDF: {str(e)}", 500
