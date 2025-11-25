# -*- coding: utf-8 -*-
"""
EdgeCase Clients Blueprint
Handles main client management (list, add, view, change type)
"""

from flask import Blueprint, render_template, request, redirect, url_for, session
from pathlib import Path
from datetime import datetime, timedelta
import sys
import sqlite3

# Add parent directory to path for database import
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
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
    conn.close()


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
    
    # Count active clients
    active_type = next((t for t in all_types if t['name'] == 'Active'), None)
    active_count = len([c for c in all_clients if c['type_id'] == active_type['id']]) if active_type else 0
    
    # Count sessions this week
    week_ago = int((datetime.now() - timedelta(days=7)).timestamp())
    sessions_this_week = 0
    for client in all_clients:
        entries = db.get_client_entries(client['id'], entry_class='session')
        sessions_this_week += sum(1 for e in entries 
                                  if e.get('created_at', 0) >= week_ago 
                                  and not e.get('is_consultation'))
    
    # Count pending invoices
    pending_invoices = 0
    for client in all_clients:
        if db.get_payment_status(client['id']) == 'pending':
            pending_invoices += 1
            
    # Calculate billable this month
    now = datetime.now()
    month_start = int(datetime(now.year, now.month, 1).timestamp())
    
    billable_this_month = 0
    for client in all_clients:
        entries = db.get_client_entries(client['id'])
        for entry in entries:
            if entry.get('created_at', 0) >= month_start:
                if entry.get('class') == 'session' and not entry.get('is_consultation'):
                    billable_this_month += entry.get('fee', 0) or 0
                elif entry.get('class') == 'item':
                    billable_this_month += entry.get('fee', 0) or 0
                    
    # Get current date and time
    current_date = now.strftime('%B %d, %Y')
    current_time = now.strftime('%I:%M %p')
    
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
    
    return render_template('main_view.html',
                         clients=clients,
                         all_types=all_types,
                         type_filter=type_filter,
                         sort_by=sort_by,
                         sort_order=sort_order,
                         search=search,
                         view_mode=view_mode,
                         active_count=active_count,
                         sessions_this_week=sessions_this_week,
                         pending_invoices=pending_invoices,
                         billable_this_month=billable_this_month,
                         current_date=current_date,
                         current_time=current_time)


@clients_bp.route('/add_client', methods=['GET', 'POST'])
def add_client():
    """Add new client with auto-generated file number support."""
    if request.method == 'POST':
        # Get file number format setting
        format_type = db.get_setting('file_number_format', 'manual')
        
        # Generate file number based on format
        if format_type == 'manual':
            file_number = request.form['file_number']
        
        elif format_type == 'date-initials':
            date_str = datetime.now().strftime('%Y%m%d')
            
            first = request.form['first_name'][0].upper()
            middle = request.form.get('middle_name', '')
            middle = middle[0].upper() if middle else ''
            last = request.form['last_name'][0].upper()
            
            initials = first + middle + last
            file_number = f"{date_str}-{initials}"
        
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
        client_id = db.add_client(client_data)
        
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
    
    conn.close()
    
    # Get ALL entries for this client
    all_entries = db.get_client_entries(client_id)
    
    # Add attachment counts to upload entries
    for entry in all_entries:
        if entry['class'] == 'upload':
            attachments = db.get_attachments(entry['id'])
            entry['attachment_count'] = len(attachments)
    
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
                
                time_val = None
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
                
                if time_str:
                    time_val = parse_time_to_seconds(time_str)
                
                if time_val is None:
                    created_timestamp = e.get('created_at', 0)
                    created_dt = datetime.fromtimestamp(created_timestamp)
                    time_val = created_dt.hour * 3600 + created_dt.minute * 60 + created_dt.second
                
                created_val = e.get('created_at', 0)
                
                return (date_val, time_val, created_val)
            
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
    
    # If changing to Inactive, remove from link groups
    if new_type and new_type['name'] == 'Inactive':
        cleanup_inactive_client_links(client_id)
    
    # Redirect back to where they came from (referrer)
    referrer = request.referrer
    if referrer and 'profile' in referrer:
        return redirect(url_for('entries.edit_profile', client_id=client_id))
    else:
        return redirect(url_for('clients.client_file', client_id=client_id))
