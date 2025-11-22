# -*- coding: utf-8 -*-
"""
EdgeCase Flask Application
Main web interface for EdgeCase Equalizer
"""

from flask import Flask, render_template, request, redirect, url_for, jsonify, session
from pathlib import Path
import sys, sqlite3
import time
from werkzeug.utils import secure_filename

# Add parent directory to path so we can import core modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database import Database

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'edgecase-dev-key-change-in-production'

# Initialize database
# Get the project root (parent of web/)
project_root = Path(__file__).parent.parent
data_dir = project_root / "data"
data_dir.mkdir(exist_ok=True)  # Create data/ if it doesn't exist

db_path = data_dir / "edgecase.db"
db = Database(str(db_path))

# Add custom Jinja filters
from datetime import datetime

# Color palette for client types
COLOR_PALETTE = [
    # Original 3 (from Active, Assess, Low Fee)
    {'hex': '#9FCFC0', 'name': 'Soft Teal', 'bubble': '#E0F2EE'},
    {'hex': '#B8D4E8', 'name': 'Soft Blue', 'bubble': '#EBF3FA'},
    {'hex': '#D4C5E0', 'name': 'Soft Lavender', 'bubble': '#F3EDF7'},
    
    # Additional muted options
    {'hex': '#C8E6C9', 'name': 'Mint Green', 'bubble': '#EDF7ED'},
    {'hex': '#FFE0B2', 'name': 'Soft Peach', 'bubble': '#FFF5E6'},
    {'hex': '#F8BBD0', 'name': 'Soft Pink', 'bubble': '#FEEEF3'},
    {'hex': '#D7CCC8', 'name': 'Soft Taupe', 'bubble': '#F2EFEE'},
    {'hex': '#CFD8DC', 'name': 'Soft Slate', 'bubble': '#EEF1F3'},
    {'hex': '#E1BEE7', 'name': 'Soft Mauve', 'bubble': '#F7EFF9'},
]

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
        # If no AM/PM and time is 1-11, assume it's meant as entered (ambiguous)
        # If no AM/PM and time is 12-23, treat as 24-hour format
        
        return hours * 3600 + minutes * 60
            
    except (ValueError, IndexError):
        # If parsing fails, return None (will sort with creation timestamp)
        return None

@app.template_filter('timestamp_to_date')
def timestamp_to_date(timestamp):
    """Convert Unix timestamp to readable date."""
    if not timestamp:
        return '-'
    from datetime import datetime
    return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')


# ===== ROUTES =====

def renumber_sessions(client_id):
    """Recalculate session numbers for a client based on chronological order."""
    # Get client to check for session offset
    client = db.get_client(client_id)
    offset = client.get('session_offset', 0)  # Default to 0 if not set
    
    # Get all non-consultation sessions with dates
    all_sessions = db.get_client_entries(client_id, 'session')
    dated_sessions = [s for s in all_sessions if s.get('session_date') and not s.get('is_consultation')]
    
    # Sort by date, then by ID
    dated_sessions.sort(key=lambda s: (s['session_date'], s['id']))
    
    # Renumber sessions starting from (offset + 1)
    for i, session in enumerate(dated_sessions, start=offset + 1):
        if session['session_number'] != i:
            db.update_entry(session['id'], {
                'session_number': i,
                'description': f"Session {i}"
            })

@app.route('/')
def index():
    """Main view - client list with stats cards."""
    # Get filter parameters
    type_filter = request.args.getlist('type')  # Can select multiple types
    sort_by = request.args.get('sort', 'last_name')  # Default sort by last name
    sort_order = request.args.get('order', 'asc')  # Default ascending
    search = request.args.get('search', '')
    # Get view preference - check URL first, then session, then default
    view_mode = request.args.get('view')
    if view_mode:
        # User explicitly changed view - save to session
        session['view_preference'] = view_mode
    else:
        # No URL parameter - use saved preference or default to compact
        view_mode = session.get('view_preference', 'compact')
    
    # Get all client types for filter
    all_types = db.get_all_client_types()
    
    # If no types selected, default to all non-locked types (exclude Inactive, Deleted)
    if not type_filter:
        type_filter = [str(t['id']) for t in all_types if not t.get('is_system_locked')]
        
    # Get clients
    if search:
        clients = db.search_clients(search)
        # Filter by selected types
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
    from datetime import datetime, timedelta
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
    from datetime import datetime
    now = datetime.now()
    month_start = int(datetime(now.year, now.month, 1).timestamp())
    
    billable_this_month = 0
    for client in all_clients:
        # Get all billable entries for this month (sessions and items)
        entries = db.get_client_entries(client['id'])
        for entry in entries:
            if entry.get('created_at', 0) >= month_start:
                # Sessions (non-consultation) and items are billable
                if entry.get('class') == 'session' and not entry.get('is_consultation'):
                    billable_this_month += entry.get('fee', 0) or 0
                elif entry.get('class') == 'item':
                    billable_this_month += entry.get('fee', 0) or 0
                    
    # Get current date and time
    from datetime import datetime
    now = datetime.now()
    current_date = now.strftime('%B %d, %Y')  # "November 9, 2025"
    current_time = now.strftime('%I:%M %p')    # "12:45 PM"
    
    ## Add type information and additional data to each client
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
        client['contact_type'] = 'call'  # Default
        client['contact_icon'] = '📞'
        
        if client['preferred_contact'] == 'call_cell':
            client['display_phone'] = client['phone']
            client['contact_type'] = 'call'
            client['contact_icon'] = '📞'
        elif client['preferred_contact'] == 'call_home':
            client['display_phone'] = client['home_phone']
            client['contact_type'] = 'call'
            client['contact_icon'] = '📞'
        elif client['preferred_contact'] == 'call_work':
            client['display_phone'] = client['work_phone']
            client['contact_type'] = 'call'
            client['contact_icon'] = '📞'
        elif client['preferred_contact'] == 'text':
            # Check text_number preference
            if client['text_number'] == 'none':
                client['display_phone'] = client['phone'] or client['home_phone'] or client['work_phone']
                client['contact_type'] = 'call'
                client['contact_icon'] = '📞'
            elif client['text_number'] == 'cell':
                client['display_phone'] = client['phone']
                client['contact_type'] = 'text'
                client['contact_icon'] = '💬'
            elif client['text_number'] == 'home':
                client['display_phone'] = client['home_phone']
                client['contact_type'] = 'text'
                client['contact_icon'] = '💬'
            elif client['text_number'] == 'work':
                client['display_phone'] = client['work_phone']
                client['contact_type'] = 'text'
                client['contact_icon'] = '💬'
            else:
                client['display_phone'] = client['phone']
                client['contact_type'] = 'text'
                client['contact_icon'] = '💬'
        elif client['preferred_contact'] == 'email':
            client['display_phone'] = client['phone'] or client['home_phone'] or client['work_phone']
            client['contact_type'] = 'call'
            client['contact_icon'] = '📞'
        else:
            # Default: show cell phone for calling
            client['display_phone'] = client['phone']
            client['contact_type'] = 'call'
            client['contact_icon'] = '📞'
        
        # Get last session date (INDENT THIS!)
        last_session = db.get_last_session_date(client['id'])
        client['last_session'] = last_session
        
        # Get payment status (INDENT THIS!)
        client['payment_status'] = db.get_payment_status(client['id'])
        
        # Check if client is linked to others (INDENT THIS!)
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

@app.route('/client/<int:client_id>')
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
    
    # ===== NEW: Get linked clients =====
    linked_groups = []
    
    # Query for all link groups this client is in
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
            # Get type info for each member
            member['type'] = db.get_client_type(member['type_id'])
            members.append(member)
        
        if members:  # Only add group if it has other members
            linked_groups.append({
                'id': group_id,
                'format': format_type,
                'format_display': format_type.capitalize() if format_type else 'Unknown',
                'members': members
            })
    
    conn.close()
    
    # Get ALL entries for this client (not just sessions)
    all_entries = db.get_client_entries(client_id)
    
    # Add attachment counts to upload entries
    for entry in all_entries:
        if entry['class'] == 'upload':
            attachments = db.get_attachments(entry['id'])
            entry['attachment_count'] = len(attachments)
    
    # Get current time for calculations
    from datetime import datetime
    now = datetime.now()
    
    # Filter to get only sessions for counting (always count all, regardless of filter)
    session_entries = [e for e in all_entries if e['class'] == 'session']
    session_count = sum(1 for e in session_entries if not e.get('is_consultation'))
    consultation_count = sum(1 for e in session_entries if e.get('is_consultation'))
    
    # Count absences for this calendar year only
    year_start = int(datetime(now.year, 1, 1).timestamp())
    absence_entries = [e for e in all_entries if e['class'] == 'absence' and (e.get('absence_date') or 0) >= year_start]
    absence_count = len(absence_entries)
    
    # Filter entries by selected classes for display
    # Note: 'consultation' is a special case - it's a session with is_consultation=1
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
    
    # Get current year and month for default expand state (reuse now from above)
    current_year = now.year
    current_month = now.month
    
    # Organize entries by year -> month (using filtered entries)
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
        # Add more entry types here as we implement them
        
        if date_field:
            entry_date = datetime.fromtimestamp(date_field)
            year = entry_date.year
            month = entry_date.month
            year_dict[year][month].append(entry)
    
    # Convert to list structure for template
    entries_by_year = []
    for year in sorted(year_dict.keys(), reverse=True):  # Most recent year first
        months = []
        year_total = 0
        
        for month in sorted(year_dict[year].keys(), reverse=True):  # Most recent month first
            # Sort entries by date, then manual time (if exists), then created_at
            def get_entry_sort_key(e):
                # Primary sort: date field
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
                
                # Secondary sort: manual time (if provided), otherwise use created_at time
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
                
                if time_str:
                    time_val = parse_time_to_seconds(time_str)
                
                # If no manual time, use the time portion of created_at timestamp
                if time_val is None:
                    created_timestamp = e.get('created_at', 0)
                    # Extract time-of-day from timestamp (seconds since midnight)
                    created_dt = datetime.fromtimestamp(created_timestamp)
                    time_val = created_dt.hour * 3600 + created_dt.minute * 60 + created_dt.second
                
                # Tertiary sort: full created_at timestamp (for entries at exact same time)
                created_val = e.get('created_at', 0)
                
                # Return tuple: date, time (manual or from created_at), full timestamp
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
                         linked_groups=linked_groups)  # NEW: Pass linked groups to template

@app.route('/client/<int:client_id>/change_type', methods=['POST'])
def change_client_type(client_id):
    """Change a client's type via dropdown."""
    import time
    
    type_id = request.form.get('type_id')
    
    if not type_id:
        return redirect(url_for('client_file', client_id=client_id))
    
    # Get current client data
    client = db.get_client(client_id)
    if not client:
        return redirect(url_for('index'))
    
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
        return redirect(url_for('edit_profile', client_id=client_id))
    else:
        return redirect(url_for('client_file', client_id=client_id))


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
    
    # You could add flash message here if you want:
    # if groups_deleted > 0:
    #     flash(f"Removed from {len(group_ids)} link group(s). {groups_deleted} group(s) deleted.")

@app.route('/client/<int:client_id>/profile', methods=['GET', 'POST'])
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
            
            # Fee Override fields
            'fee_override_base': float(request.form.get('fee_override_base')) if request.form.get('fee_override_base') else None,
            'fee_override_tax_rate': float(request.form.get('fee_override_tax_rate')) if request.form.get('fee_override_tax_rate') else None,
            'fee_override_total': float(request.form.get('fee_override_total')) if request.form.get('fee_override_total') else None,
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
                import difflib
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
                    old_addr = old_profile.get('address') or ''
                    new_addr = profile_data.get('address') or ''
                    
                    if old_addr and new_addr:
                        old_words = old_addr.split()
                        new_words = new_addr.split()
                        diff = difflib.ndiff(old_words, new_words)
                        
                        formatted_parts = []
                        for item in diff:
                            if item.startswith('  '):
                                formatted_parts.append(item[2:])
                            elif item.startswith('- '):
                                formatted_parts.append(f'<del>{item[2:]}</del>')
                            elif item.startswith('+ '):
                                formatted_parts.append(f'<strong>{item[2:]}</strong>')
                        
                        diff_text = ' '.join(formatted_parts)
                        if len(diff_text) > 100:
                            diff_text = diff_text[:100] + '...'
                        changes.append(f"Address: {diff_text}")
                    elif old_addr:
                        changes.append("Address: Cleared")
                    else:
                        changes.append("Address: Added")
                
                # Additional Info (smart word-level diff)
                if old_profile.get('additional_info') != profile_data.get('additional_info'):
                    old_info = old_profile.get('additional_info') or ''
                    new_info = profile_data.get('additional_info') or ''
                    
                    if old_info and new_info:
                        old_words = old_info.split()
                        new_words = new_info.split()
                        diff = difflib.ndiff(old_words, new_words)
                        
                        formatted_parts = []
                        for item in diff:
                            if item.startswith('  '):
                                formatted_parts.append(item[2:])
                            elif item.startswith('- '):
                                formatted_parts.append(f'<del>{item[2:]}</del>')
                            elif item.startswith('+ '):
                                formatted_parts.append(f'<strong>{item[2:]}</strong>')
                        
                        diff_text = ' '.join(formatted_parts)
                        if len(diff_text) > 150:
                            diff_text = diff_text[:150] + '...'
                        changes.append(f"Additional Info: {diff_text}")
                    elif old_info:
                        changes.append("Additional Info: Cleared")
                    else:
                        changes.append("Additional Info: Added")
                
                # Fee changes - track all three fields
                if old_profile.get('fee_override_base') != profile_data.get('fee_override_base'):
                    old_base = old_profile.get('fee_override_base')
                    new_base = profile_data.get('fee_override_base')
                    # Convert to float if string (database might return string)
                    if old_base is not None and isinstance(old_base, str):
                        old_base = float(old_base) if old_base else None
                    if new_base is not None and isinstance(new_base, str):
                        new_base = float(new_base) if new_base else None
                    old_str = f"${old_base:.2f}" if old_base is not None else "None"
                    new_str = f"${new_base:.2f}" if new_base is not None else "None"
                    changes.append(f"Session Fee Base: {old_str} → {new_str}")
                
                if old_profile.get('fee_override_tax_rate') != profile_data.get('fee_override_tax_rate'):
                    old_tax = old_profile.get('fee_override_tax_rate')
                    new_tax = profile_data.get('fee_override_tax_rate')
                    # Convert to float if string (database might return string)
                    if old_tax is not None and isinstance(old_tax, str):
                        old_tax = float(old_tax) if old_tax else None
                    if new_tax is not None and isinstance(new_tax, str):
                        new_tax = float(new_tax) if new_tax else None
                    old_str = f"{old_tax:.2f}%" if old_tax is not None else "None"
                    new_str = f"{new_tax:.2f}%" if new_tax is not None else "None"
                    changes.append(f"Session Fee Tax: {old_str} → {new_str}")
                
                if old_profile.get('fee_override_total') != profile_data.get('fee_override_total'):
                    old_fee = old_profile.get('fee_override_total')
                    new_fee = profile_data.get('fee_override_total')
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
                    old_addr = old_profile.get('guardian1_address') or ''
                    new_addr = profile_data.get('guardian1_address') or ''
                    
                    if old_addr and new_addr:
                        old_words = old_addr.split()
                        new_words = new_addr.split()
                        diff = difflib.ndiff(old_words, new_words)
                        
                        formatted_parts = []
                        for item in diff:
                            if item.startswith('  '):
                                formatted_parts.append(item[2:])
                            elif item.startswith('- '):
                                formatted_parts.append(f'<del>{item[2:]}</del>')
                            elif item.startswith('+ '):
                                formatted_parts.append(f'<strong>{item[2:]}</strong>')
                        
                        diff_text = ' '.join(formatted_parts)
                        if len(diff_text) > 100:
                            diff_text = diff_text[:100] + '...'
                        changes.append(f"Guardian 1 Address: {diff_text}")
                    elif old_addr:
                        changes.append("Guardian 1 Address: Cleared")
                    else:
                        changes.append("Guardian 1 Address: Added")
                
                if old_profile.get('guardian2_address') != profile_data.get('guardian2_address'):
                    old_addr = old_profile.get('guardian2_address') or ''
                    new_addr = profile_data.get('guardian2_address') or ''
                    
                    if old_addr and new_addr:
                        old_words = old_addr.split()
                        new_words = new_addr.split()
                        diff = difflib.ndiff(old_words, new_words)
                        
                        formatted_parts = []
                        for item in diff:
                            if item.startswith('  '):
                                formatted_parts.append(item[2:])
                            elif item.startswith('- '):
                                formatted_parts.append(f'<del>{item[2:]}</del>')
                            elif item.startswith('+ '):
                                formatted_parts.append(f'<strong>{item[2:]}</strong>')
                        
                        diff_text = ' '.join(formatted_parts)
                        if len(diff_text) > 100:
                            diff_text = diff_text[:100] + '...'
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
        import time
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
        
        return redirect(url_for('client_file', client_id=client_id))
    
    # GET request - show form
    all_types = db.get_all_client_types()
    
    # Get edit history if profile exists and is locked
    is_locked = db.is_entry_locked(profile['id']) if profile else False
    edit_history = db.get_edit_history(profile['id']) if is_locked else []
    
    return render_template('entry_forms/profile.html',
                         client=client,
                         profile=profile,
                         all_types=all_types,
                         is_locked=is_locked,
                         edit_history=edit_history)
    
@app.route('/client/<int:client_id>/session', methods=['GET', 'POST'])
def create_session(client_id):
    """Create a new session entry for a client."""
    import time
    from datetime import datetime
    
    # Get client info
    client = db.get_client(client_id)
    if not client:
        return "Client not found", 404
    
    # Get client type for defaults
    client_type = db.get_client_type(client['type_id'])
    
    if request.method == 'POST':
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
        
        # Get form data
        session_data = {
            'client_id': client_id,
            'class': 'session',
            'created_at': int(time.time()),
            'modified_at': int(time.time()),
            
            # Session fields
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
            
            # Clinical fields (optional)
            'mood': request.form.get('mood') or None,
            'affect': request.form.get('affect') or None,
            'risk_assessment': request.form.get('risk_assessment') or None,
            
            # Content
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
            # Temporary number, will be corrected by renumber_sessions()
            session_data['session_number'] = 999
            session_data['description'] = 'Session 999'
        
        # Save session entry
        entry_id = db.add_entry(session_data)

        # Check if this is a draft save
        is_draft_save = request.form.get('save_draft') == '1'

        # Only lock if NOT a draft save
        if not is_draft_save:
            db.lock_entry(entry_id)

        # Renumber all sessions to maintain chronological order
        renumber_sessions(client_id)
                
        return redirect(url_for('client_file', client_id=client_id))
    
    # GET - show form
    # Get today's date for defaults
    today_dt = datetime.now()
    today = today_dt.strftime('%Y-%m-%d')
    today_year = today_dt.year
    today_month = today_dt.month
    today_day = today_dt.day

    # Calculate preview session number
    all_sessions = db.get_client_entries(client_id, 'session')
    dated_sessions = [s for s in all_sessions if s.get('session_date') and not s.get('is_consultation')]
    dated_sessions.sort(key=lambda s: (s['session_date'], s['id']))

    offset = client.get('session_offset', 0)
    today_timestamp = int(today_dt.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    sessions_before_today = sum(1 for s in dated_sessions if s['session_date'] <= today_timestamp)
    preview_session_number = sessions_before_today + offset + 1

    # Get all sessions for navigation
    # Note: prev/next don't apply when creating new session (only when editing)
    prev_session_id = None
    next_session_id = None

    # Prepare fee sources for JavaScript to use
    # 1. Profile Override (if exists)
    profile = db.get_profile_entry(client_id)
    profile_override = None
    if profile and profile.get('fee_override_total'):
        profile_override = {
            'base': profile['fee_override_base'],
            'tax': profile['fee_override_tax_rate'],
            'total': profile['fee_override_total']
        }
    
    # 2. Get individual session fees from Profile
    profile = db.get_profile_entry(client_id)
    profile_fees = {
        'base': profile.get('fee_override_base') or 0,
        'tax': profile.get('fee_override_tax_rate') or 0,
        'total': profile.get('fee_override_total') or 0,
        'duration': profile.get('default_session_duration') or 50  # Default to 50 if not set
    }
        
    # 3. Link Groups (by format)
    link_group_fees = {}  # Format: {'couples': {...}, 'family': {...}, 'group': {...}}
    
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
    
    # 4. Get last session's service value for auto-population
    cursor.execute("""
        SELECT service FROM entries
        WHERE client_id = ? AND class = 'session' AND service IS NOT NULL
        ORDER BY session_date DESC, created_at DESC
        LIMIT 1
    """, (client_id,))
    
    last_service_row = cursor.fetchone()
    last_service = last_service_row['service'] if last_service_row else None
    
    conn.close()

    return render_template('entry_forms/session.html',
                        client=client,
                        client_type=client_type,
                        profile_override=profile_override,
                        profile_fees=profile_fees,
                        link_group_fees=link_group_fees,
                        last_service=last_service,
                        today=today,
                        today_year=today_year,
                        today_month=today_month,
                        today_day=today_day,
                        next_session_number=preview_session_number,
                        is_edit=False,
                        prev_session_id=prev_session_id,
                        next_session_id=next_session_id)
    
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
            'service': request.form.get('service') or None,
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
        
        # Check if this is a draft save
        is_draft_save = request.form.get('save_draft') == '1'

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
                    import difflib
                    old_content = old_session.get('content') or ''
                    new_content = session_data.get('content') or ''
                    
                    if old_content and new_content:
                        # Split into words for word-level diff
                        old_words = old_content.split()
                        new_words = new_content.split()
                        
                        # Generate diff
                        diff = difflib.ndiff(old_words, new_words)
                        
                        # Build HTML formatted diff
                        formatted_parts = []
                        for item in diff:
                            if item.startswith('  '):  # Unchanged
                                formatted_parts.append(item[2:])
                            elif item.startswith('- '):  # Deleted
                                formatted_parts.append(f'<del>{item[2:]}</del>')
                            elif item.startswith('+ '):  # Added
                                formatted_parts.append(f'<strong>{item[2:]}</strong>')
                            # Ignore '?' lines (change indicators)
                        
                        # Limit length for display (keep first ~200 chars of diff)
                        diff_text = ' '.join(formatted_parts)
                        if len(diff_text) > 150:
                            diff_text = diff_text[:150] + '...'
                        
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
    
    # 2. Get individual session fees from Profile
    profile = db.get_profile_entry(client_id)
    profile_fees = {
        'base': profile.get('fee_override_base') or 0,
        'tax': profile.get('fee_override_tax_rate') or 0,
        'total': profile.get('fee_override_total') or 0,
        'duration': profile.get('default_session_duration') or 50
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
    
    conn.close()
    
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
                         edit_history=edit_history,
                         prev_session_id=prev_session_id,
                         next_session_id=next_session_id)

@app.route('/client/<int:client_id>/communication', methods=['GET', 'POST'])
def create_communication(client_id):
    """Create new communication entry."""
    client = db.get_client(client_id)
    if not client:
        return "Client not found", 404
    
    client_type = db.get_client_type(client['type_id'])
    
    if request.method == 'POST':
        # Parse date from dropdowns
        year = request.form.get('year')
        month = request.form.get('month')
        day = request.form.get('day')
        
        comm_date_timestamp = None
        if year and month and day:
            from datetime import datetime
            date_str = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            comm_date_timestamp = int(datetime.strptime(date_str, '%Y-%m-%d').timestamp())
        
        # Prepare communication data
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
        
        # Save communication
        entry_id = db.add_entry(comm_data)
        db.lock_entry(entry_id)
        
        return redirect(url_for('client_file', client_id=client_id))
    
    # GET - show form
    from datetime import datetime
    today_dt = datetime.now()
    today = today_dt.strftime('%Y-%m-%d')
    today_year = today_dt.year
    today_month = today_dt.month
    today_day = today_dt.day

    return render_template('entry_forms/communication.html',
                        client=client,
                        client_type=client_type,
                        today=today,
                        today_year=today_year,
                        today_month=today_month,
                        today_day=today_day,
                        is_edit=False)

@app.route('/client/<int:client_id>/communication/<int:entry_id>', methods=['GET', 'POST'])
def edit_communication(client_id, entry_id):
    """Edit existing communication entry."""
    client = db.get_client(client_id)
    if not client:
        return "Client not found", 404
    
    client_type = db.get_client_type(client['type_id'])
    communication = db.get_entry(entry_id)
    
    if not communication or communication['class'] != 'communication':
        return "Communication not found", 404
    
    if request.method == 'POST':
        # Get the old communication data for comparison
        old_comm = communication.copy()
        
        # Parse date from dropdowns
        year = request.form.get('year')
        month = request.form.get('month')
        day = request.form.get('day')
        
        comm_date_timestamp = None
        if year and month and day:
            from datetime import datetime
            date_str = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            comm_date_timestamp = int(datetime.strptime(date_str, '%Y-%m-%d').timestamp())
        
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
            import difflib
            changes = []
            
            # Description (with smart word-level diff)
            if old_comm.get('description') != comm_data.get('description'):
                old_desc = old_comm.get('description') or ''
                new_desc = comm_data.get('description') or ''
                
                if old_desc and new_desc:
                    # Split into words for word-level diff
                    old_words = old_desc.split()
                    new_words = new_desc.split()
                    
                    # Generate diff
                    diff = difflib.ndiff(old_words, new_words)
                    
                    # Build HTML formatted diff
                    formatted_parts = []
                    for item in diff:
                        if item.startswith('  '):  # Unchanged
                            formatted_parts.append(item[2:])
                        elif item.startswith('- '):  # Deleted
                            formatted_parts.append(f'<del>{item[2:]}</del>')
                        elif item.startswith('+ '):  # Added
                            formatted_parts.append(f'<strong>{item[2:]}</strong>')
                        # Ignore '?' lines (change indicators)
                    
                    # Limit length for display
                    diff_text = ' '.join(formatted_parts)
                    if len(diff_text) > 150:
                        diff_text = diff_text[:150] + '...'
                    
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
            
            # Date
            if old_comm.get('comm_date') != comm_date_timestamp:
                from datetime import datetime
                old_date = datetime.fromtimestamp(old_comm['comm_date']).strftime('%Y-%m-%d') if old_comm.get('comm_date') else 'None'
                new_date = datetime.fromtimestamp(comm_date_timestamp).strftime('%Y-%m-%d') if comm_date_timestamp else 'None'
                changes.append(f"Date: {old_date} → {new_date}")
            
            # Time
            if old_comm.get('comm_time') != comm_data.get('comm_time'):
                old_time = old_comm.get('comm_time') or 'None'
                new_time = comm_data.get('comm_time') or 'None'
                changes.append(f"Time: {old_time} → {new_time}")
            
            # Content (with smart word-level diff)
            if old_comm.get('content') != comm_data.get('content'):
                old_content = old_comm.get('content') or ''
                new_content = comm_data.get('content') or ''
                
                if old_content and new_content:
                    # Split into words for word-level diff
                    old_words = old_content.split()
                    new_words = new_content.split()
                    
                    # Generate diff
                    diff = difflib.ndiff(old_words, new_words)
                    
                    # Build HTML formatted diff
                    formatted_parts = []
                    for item in diff:
                        if item.startswith('  '):  # Unchanged
                            formatted_parts.append(item[2:])
                        elif item.startswith('- '):  # Deleted
                            formatted_parts.append(f'<del>{item[2:]}</del>')
                        elif item.startswith('+ '):  # Added
                            formatted_parts.append(f'<strong>{item[2:]}</strong>')
                        # Ignore '?' lines (change indicators)
                    
                    # Limit length for display
                    diff_text = ' '.join(formatted_parts)
                    if len(diff_text) > 150:
                        diff_text = diff_text[:150] + '...'
                    
                    changes.append(f"Content: {diff_text}")
                elif old_content:
                    changes.append("Content: Cleared")
                else:
                    changes.append("Content: Added")
            
            if changes:
                change_desc = "; ".join(changes)
                db.add_to_edit_history(entry_id, change_desc)
        
        # Update the existing communication
        db.update_entry(entry_id, comm_data)
        
        return redirect(url_for('client_file', client_id=client_id))
    
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
    from datetime import datetime
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
    
    return render_template('entry_forms/communication.html',
                        client=client,
                        client_type=client_type,
                        entry=communication,
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
    
@app.route('/client/<int:client_id>/absence', methods=['GET', 'POST'])
def create_absence(client_id):
    """Create a new absence entry for a client."""
    client = db.get_client(client_id)
    if not client:
        return "Client not found", 404
    
    client_type = db.get_client_type(client['type_id'])
    
    if request.method == 'POST':
        # Convert date string to Unix timestamp
        absence_date_str = request.form.get('absence_date')
        absence_date_timestamp = None
        if absence_date_str:
            from datetime import datetime
            date_obj = datetime.strptime(absence_date_str, '%Y-%m-%d')
            absence_date_timestamp = int(date_obj.timestamp())
        
        # Prepare absence data with three-way fee calculation
        absence_data = {
            'client_id': client_id,
            'class': 'absence',
            'description': request.form['description'],
            'absence_date': absence_date_timestamp,
            'absence_time': request.form.get('absence_time', ''),
            'base_price': float(request.form.get('base_price', 0)),
            'tax_rate': float(request.form.get('tax_rate', 0)),
            'fee': float(request.form.get('fee', 0)),
            'content': request.form.get('content', '')
        }
        
        # Save absence
        entry_id = db.add_entry(absence_data)
        db.lock_entry(entry_id)
        
        # TODO: Handle link_entry checkbox when linking is implemented
        
        return redirect(url_for('client_file', client_id=client_id))
    
    # GET - show form
    from datetime import date
    today = date.today().strftime('%Y-%m-%d')
    
    return render_template('entry_forms/absence.html',
                         client=client,
                         client_type=client_type,
                         today=today)

@app.route('/client/<int:client_id>/absence/<int:entry_id>', methods=['GET', 'POST'])
def edit_absence(client_id, entry_id):
    """Edit existing absence entry."""
    client = db.get_client(client_id)
    if not client:
        return "Client not found", 404
    
    client_type = db.get_client_type(client['type_id'])
    absence = db.get_entry(entry_id)
    
    if not absence or absence['class'] != 'absence':
        return "Absence not found", 404
    
    if request.method == 'POST':
        # Get the old absence data for comparison
        old_absence = absence.copy()
        
        # Convert date string to Unix timestamp
        absence_date_str = request.form.get('absence_date')
        absence_date_timestamp = None
        if absence_date_str:
            from datetime import datetime
            date_obj = datetime.strptime(absence_date_str, '%Y-%m-%d')
            absence_date_timestamp = int(date_obj.timestamp())
        
        # Prepare updated absence data
        absence_data = {
            'description': request.form['description'],
            'absence_date': absence_date_timestamp,
            'absence_time': request.form.get('absence_time', ''),
            'base_price': float(request.form.get('base_price', 0)),
            'tax_rate': float(request.form.get('tax_rate', 0)),
            'fee': float(request.form.get('fee', 0)),
            'content': request.form.get('content', '')
        }
        
        # Check if entry is locked - if so, log changes to edit history
        if db.is_entry_locked(entry_id):
            import difflib
            changes = []
            
            # Description (with smart word-level diff)
            if old_absence.get('description') != absence_data.get('description'):
                old_desc = old_absence.get('description') or ''
                new_desc = absence_data.get('description') or ''
                
                if old_desc and new_desc:
                    # Split into words for word-level diff
                    old_words = old_desc.split()
                    new_words = new_desc.split()
                    
                    # Generate diff
                    diff = difflib.ndiff(old_words, new_words)
                    
                    # Build HTML formatted diff
                    formatted_parts = []
                    for item in diff:
                        if item.startswith('  '):  # Unchanged
                            formatted_parts.append(item[2:])
                        elif item.startswith('- '):  # Deleted
                            formatted_parts.append(f'<del>{item[2:]}</del>')
                        elif item.startswith('+ '):  # Added
                            formatted_parts.append(f'<strong>{item[2:]}</strong>')
                        # Ignore '?' lines (change indicators)
                    
                    # Limit length for display
                    diff_text = ' '.join(formatted_parts)
                    if len(diff_text) > 150:
                        diff_text = diff_text[:150] + '...'
                    
                    changes.append(f"Description: {diff_text}")
                elif old_desc:
                    changes.append("Description: Cleared")
                else:
                    changes.append("Description: Added")
            
            # Date
            if old_absence.get('absence_date') != absence_date_timestamp:
                from datetime import datetime
                old_date = datetime.fromtimestamp(old_absence['absence_date']).strftime('%Y-%m-%d') if old_absence.get('absence_date') else 'None'
                new_date = datetime.fromtimestamp(absence_date_timestamp).strftime('%Y-%m-%d') if absence_date_timestamp else 'None'
                changes.append(f"Date: {old_date} → {new_date}")
            
            # Time
            if old_absence.get('absence_time') != absence_data.get('absence_time'):
                old_time = old_absence.get('absence_time') or 'None'
                new_time = absence_data.get('absence_time') or 'None'
                changes.append(f"Time: {old_time} → {new_time}")
            
            # Fee breakdown
            if old_absence.get('base_price') != absence_data.get('base_price'):
                old_base = old_absence.get('base_price')
                new_base = absence_data.get('base_price')
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
                old_content = old_absence.get('content') or ''
                new_content = absence_data.get('content') or ''
                
                if old_content and new_content:
                    # Split into words for word-level diff
                    old_words = old_content.split()
                    new_words = new_content.split()
                    
                    # Generate diff
                    diff = difflib.ndiff(old_words, new_words)
                    
                    # Build HTML formatted diff
                    formatted_parts = []
                    for item in diff:
                        if item.startswith('  '):  # Unchanged
                            formatted_parts.append(item[2:])
                        elif item.startswith('- '):  # Deleted
                            formatted_parts.append(f'<del>{item[2:]}</del>')
                        elif item.startswith('+ '):  # Added
                            formatted_parts.append(f'<strong>{item[2:]}</strong>')
                        # Ignore '?' lines (change indicators)
                    
                    # Limit length for display
                    diff_text = ' '.join(formatted_parts)
                    if len(diff_text) > 150:
                        diff_text = diff_text[:150] + '...'
                    
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
        
        return redirect(url_for('client_file', client_id=client_id))
    
    # GET - show form with existing data
    # Convert timestamp back to date string
    from datetime import datetime
    absence_date = datetime.fromtimestamp(absence['absence_date']).strftime('%Y-%m-%d') if absence.get('absence_date') else None
    
    # Get lock status and edit history
    is_locked = db.is_entry_locked(entry_id)
    edit_history = db.get_edit_history(entry_id) if is_locked else []
    
    return render_template('entry_forms/absence.html',
                         client=client,
                         client_type=client_type,
                         entry=absence,
                         absence_date=absence_date,
                         is_edit=True,
                         is_locked=is_locked,
                         edit_history=edit_history)
    
@app.route('/client/<int:client_id>/item', methods=['GET', 'POST'])
def create_item(client_id):
    """Create a new item entry for a client."""
    import time
    from datetime import datetime
    
    # Get client info
    client = db.get_client(client_id)
    if not client:
        return "Client not found", 404
    
    # Get client type
    client_type = db.get_client_type(client['type_id'])
    
    if request.method == 'POST':
        # Parse date from hidden field (set by JavaScript)
        item_date_str = request.form.get('item_date')
        item_date_timestamp = None
        if item_date_str:
            item_date_timestamp = int(datetime.strptime(item_date_str, '%Y-%m-%d').timestamp())
        
        # Get form data
        item_data = {
            'client_id': client_id,
            'class': 'item',
            'created_at': int(time.time()),
            'modified_at': int(time.time()),
            
            # Item fields
            'description': request.form['description'],
            'item_date': item_date_timestamp,
            'item_time': request.form.get('item_time') or None,
            'base_price': float(request.form.get('base_price', 0)),
            'tax_rate': float(request.form.get('tax_rate', 0)),
            'fee': float(request.form.get('fee', 0)),
            
            # Content
            'content': request.form.get('content') or None,
        }
        
        # Save item entry
        entry_id = db.add_entry(item_data)
        
        # Lock entry immediately (items are always locked on creation)
        db.lock_entry(entry_id)
        
        return redirect(url_for('client_file', client_id=client_id))
    
    # GET - show form
    # Get today's date for defaults
    today_dt = datetime.now()
    today = today_dt.strftime('%Y-%m-%d')
    
    return render_template('entry_forms/item.html',
                        client=client,
                        client_type=client_type,
                        today=today,
                        is_edit=False)
    
@app.route('/client/<int:client_id>/item/<int:entry_id>', methods=['GET', 'POST'])
def edit_item(client_id, entry_id):
    """Edit existing item entry."""
    client = db.get_client(client_id)
    if not client:
        return "Client not found", 404
    
    client_type = db.get_client_type(client['type_id'])
    item = db.get_entry(entry_id)
    
    if not item or item['class'] != 'item':
        return "Item not found", 404
    
    if request.method == 'POST':
        # Get the old item data for comparison
        old_item = item.copy()
        
        # Convert date string to Unix timestamp (optional for items)
        item_date_str = request.form.get('item_date')
        item_date_timestamp = None
        if item_date_str:
            from datetime import datetime
            date_obj = datetime.strptime(item_date_str, '%Y-%m-%d')
            item_date_timestamp = int(date_obj.timestamp())
        
        # Prepare updated item data
        item_data = {
            'description': request.form['description'],
            'item_date': item_date_timestamp,
            'item_time': request.form.get('item_time', ''),
            'base_price': float(request.form.get('base_price', 0)) if request.form.get('base_price') else None,
            'tax_rate': float(request.form.get('tax_rate', 0)) if request.form.get('tax_rate') else 0,
            'fee': float(request.form.get('fee', 0)),
            'content': request.form.get('content', '')
        }
        
        # Check if entry is locked - if so, log changes to edit history
        if db.is_entry_locked(entry_id):
            import difflib
            changes = []
            
            # Description (with smart word-level diff)
            if old_item.get('description') != item_data.get('description'):
                old_desc = old_item.get('description') or ''
                new_desc = item_data.get('description') or ''
                
                if old_desc and new_desc:
                    # Split into words for word-level diff
                    old_words = old_desc.split()
                    new_words = new_desc.split()
                    
                    # Generate diff
                    diff = difflib.ndiff(old_words, new_words)
                    
                    # Build HTML formatted diff
                    formatted_parts = []
                    for item in diff:
                        if item.startswith('  '):  # Unchanged
                            formatted_parts.append(item[2:])
                        elif item.startswith('- '):  # Deleted
                            formatted_parts.append(f'<del>{item[2:]}</del>')
                        elif item.startswith('+ '):  # Added
                            formatted_parts.append(f'<strong>{item[2:]}</strong>')
                        # Ignore '?' lines (change indicators)
                    
                    # Limit length for display
                    diff_text = ' '.join(formatted_parts)
                    if len(diff_text) > 150:
                        diff_text = diff_text[:150] + '...'
                    
                    changes.append(f"Description: {diff_text}")
                elif old_desc:
                    changes.append("Description: Cleared")
                else:
                    changes.append("Description: Added")
            
            # Date
            if old_item.get('item_date') != item_date_timestamp:
                from datetime import datetime
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
                old_content = old_item.get('content') or ''
                new_content = item_data.get('content') or ''
                
                if old_content and new_content:
                    # Split into words for word-level diff
                    old_words = old_content.split()
                    new_words = new_content.split()
                    
                    # Generate diff
                    diff = difflib.ndiff(old_words, new_words)
                    
                    # Build HTML formatted diff
                    formatted_parts = []
                    for item in diff:
                        if item.startswith('  '):  # Unchanged
                            formatted_parts.append(item[2:])
                        elif item.startswith('- '):  # Deleted
                            formatted_parts.append(f'<del>{item[2:]}</del>')
                        elif item.startswith('+ '):  # Added
                            formatted_parts.append(f'<strong>{item[2:]}</strong>')
                        # Ignore '?' lines (change indicators)
                    
                    # Limit length for display
                    diff_text = ' '.join(formatted_parts)
                    if len(diff_text) > 150:
                        diff_text = diff_text[:150] + '...'
                    
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
        
        return redirect(url_for('client_file', client_id=client_id))
    
    # GET - show form with existing data
    # Convert timestamp back to date string
    from datetime import datetime
    item_date = datetime.fromtimestamp(item['item_date']).strftime('%Y-%m-%d') if item.get('item_date') else None
    
    # Get lock status and edit history
    is_locked = db.is_entry_locked(entry_id)
    edit_history = db.get_edit_history(entry_id) if is_locked else []
    
    return render_template('entry_forms/item.html',
                         client=client,
                         client_type=client_type,
                         entry=item,
                         item_date=item_date,
                         is_edit=True,
                         is_locked=is_locked,
                         edit_history=edit_history)
    
@app.route('/client/<int:client_id>/upload', methods=['GET', 'POST'])
def create_upload(client_id):
    """Create new upload entry with file attachments."""
    client = db.get_client(client_id)
    if not client:
        return "Client not found", 404
    
    client_type = db.get_client_type(client['type_id'])
    
    if request.method == 'POST':
        
        # Parse date from dropdowns
        year = request.form.get('year')
        month = request.form.get('month')
        day = request.form.get('day')
        
        upload_date_timestamp = None
        if year and month and day:
            from datetime import datetime
            date_str = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            upload_date_timestamp = int(datetime.strptime(date_str, '%Y-%m-%d').timestamp())
        
        # Prepare upload entry data
        upload_data = {
            'client_id': client_id,
            'class': 'upload',
            'description': request.form['description'],
            'upload_date': upload_date_timestamp,
            'upload_time': request.form.get('upload_time', ''),
            'content': request.form.get('content', '')
        }
        
        # Save upload entry first to get entry_id
        entry_id = db.add_entry(upload_data)
        
        # Handle file uploads
        files = request.files.getlist('files[]')
        descriptions = request.form.getlist('file_descriptions[]')
        
        if files and files[0].filename:  # Check if at least one file was selected
            from werkzeug.utils import secure_filename
            import os
            import time
            
            # Create upload directory for this client and entry
            upload_dir = os.path.expanduser(f'~/edgecase/attachments/{client_id}/{entry_id}')
            os.makedirs(upload_dir, exist_ok=True)
            
            # Process each file
            for i, file in enumerate(files):
                if file and file.filename:
                    # Secure the filename
                    filename = secure_filename(file.filename)
                    filepath = os.path.join(upload_dir, filename)
                    
                    # Save file to disk
                    file.save(filepath)
                    
                    # Get file size
                    filesize = os.path.getsize(filepath)
                    
                    # Get description (use filename if not provided)
                    description = descriptions[i] if i < len(descriptions) and descriptions[i] else filename
                    
                    # Save attachment record to database
                    conn = db.connect()
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO attachments (entry_id, filename, description, filepath, filesize, uploaded_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (entry_id, filename, description, filepath, filesize, int(time.time())))
                    conn.commit()
                    conn.close()
        
        return redirect(url_for('client_file', client_id=client_id))
    
    # GET - show form
    from datetime import datetime
    today_dt = datetime.now()
    today = today_dt.strftime('%Y-%m-%d')
    today_year = today_dt.year
    today_month = today_dt.month
    today_day = today_dt.day

    return render_template('entry_forms/upload.html',
                        client=client,
                        client_type=client_type,
                        today=today,
                        today_year=today_year,
                        today_month=today_month,
                        today_day=today_day,
                        is_edit=False)

@app.route('/client/<int:client_id>/upload/<int:entry_id>', methods=['GET', 'POST'])
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
        # Get the old upload data for comparison
        old_upload = upload.copy()
        
        # Parse date from dropdowns
        year = request.form.get('year')
        month = request.form.get('month')
        day = request.form.get('day')
        
        upload_date_timestamp = None
        if year and month and day:
            from datetime import datetime
            date_str = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            upload_date_timestamp = int(datetime.strptime(date_str, '%Y-%m-%d').timestamp())
        
        # Prepare updated upload data
        upload_data = {
            'description': request.form['description'],
            'upload_date': upload_date_timestamp,
            'upload_time': request.form.get('upload_time', ''),
            'content': request.form.get('content', '')
        }
        
        # Generate edit history (Upload entries are NOT locked, but we still track changes)
        import difflib
        changes = []
        
        # Description (with smart word-level diff)
        if old_upload.get('description') != upload_data.get('description'):
            old_desc = old_upload.get('description') or ''
            new_desc = upload_data.get('description') or ''
            
            if old_desc and new_desc:
                old_words = old_desc.split()
                new_words = new_desc.split()
                diff = difflib.ndiff(old_words, new_words)
                
                formatted_parts = []
                for item in diff:
                    if item.startswith('  '):
                        formatted_parts.append(item[2:])
                    elif item.startswith('- '):
                        formatted_parts.append(f'<del>{item[2:]}</del>')
                    elif item.startswith('+ '):
                        formatted_parts.append(f'<strong>{item[2:]}</strong>')
                
                diff_text = ' '.join(formatted_parts)
                if len(diff_text) > 150:
                    diff_text = diff_text[:150] + '...'
                
                changes.append(f"Description: {diff_text}")
            elif old_desc:
                changes.append("Description: Cleared")
            else:
                changes.append("Description: Added")
        
        # Date
        if old_upload.get('upload_date') != upload_date_timestamp:
            from datetime import datetime
            old_date = datetime.fromtimestamp(old_upload['upload_date']).strftime('%Y-%m-%d') if old_upload.get('upload_date') else 'None'
            new_date = datetime.fromtimestamp(upload_date_timestamp).strftime('%Y-%m-%d') if upload_date_timestamp else 'None'
            changes.append(f"Date: {old_date} → {new_date}")
        
        # Time
        if old_upload.get('upload_time') != upload_data.get('upload_time'):
            old_time = old_upload.get('upload_time') or 'None'
            new_time = upload_data.get('upload_time') or 'None'
            changes.append(f"Time: {old_time} → {new_time}")
        
        # Content (with smart word-level diff)
        if old_upload.get('content') != upload_data.get('content'):
            old_content = old_upload.get('content') or ''
            new_content = upload_data.get('content') or ''
            
            if old_content and new_content:
                old_words = old_content.split()
                new_words = new_content.split()
                diff = difflib.ndiff(old_words, new_words)
                
                formatted_parts = []
                for item in diff:
                    if item.startswith('  '):
                        formatted_parts.append(item[2:])
                    elif item.startswith('- '):
                        formatted_parts.append(f'<del>{item[2:]}</del>')
                    elif item.startswith('+ '):
                        formatted_parts.append(f'<strong>{item[2:]}</strong>')
                
                diff_text = ' '.join(formatted_parts)
                if len(diff_text) > 150:
                    diff_text = diff_text[:150] + '...'
                
                changes.append(f"Content: {diff_text}")
            elif old_content:
                changes.append("Content: Cleared")
            else:
                changes.append("Content: Added")
        
        # Handle new file uploads
        files = request.files.getlist('files[]')
        descriptions = request.form.getlist('file_descriptions[]')
        
        if files and files[0].filename:  # Check if at least one file was selected
            from werkzeug.utils import secure_filename
            import os
            import time
            
            # Create upload directory for this client and entry (if doesn't exist)
            upload_dir = os.path.expanduser(f'~/edgecase/attachments/{client_id}/{entry_id}')
            os.makedirs(upload_dir, exist_ok=True)
            
            # Track added files for edit history
            added_files = []
            
            # Process each file
            for i, file in enumerate(files):
                if file and file.filename:
                    filename = secure_filename(file.filename)
                    filepath = os.path.join(upload_dir, filename)
                    
                    file.save(filepath)
                    filesize = os.path.getsize(filepath)
                    description = descriptions[i] if i < len(descriptions) and descriptions[i] else filename
                    
                    conn = db.connect()
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO attachments (entry_id, filename, description, filepath, filesize, uploaded_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (entry_id, filename, description, filepath, filesize, int(time.time())))
                    conn.commit()
                    conn.close()
                    
                    added_files.append(filename)
            
            if added_files:
                changes.append(f"Added files: {', '.join(added_files)}")
        
        if changes:
            change_desc = "; ".join(changes)
            db.add_to_edit_history(entry_id, change_desc)
        
        # Update the upload entry
        db.update_entry(entry_id, upload_data)
        
        return redirect(url_for('client_file', client_id=client_id))
    
    # GET - show form with existing data
    
    # Parse upload date into year, month, day for dropdowns
    from datetime import datetime
    upload_year = None
    upload_month = None
    upload_day = None
    if upload.get('upload_date'):
        upload_dt = datetime.fromtimestamp(upload['upload_date'])
        upload_year = upload_dt.year
        upload_month = upload_dt.month
        upload_day = upload_dt.day
    
    # Get attachments for this entry
    attachments = db.get_attachments(entry_id)
    
    # Get edit history (Upload entries are NOT locked, but we still show history)
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
                        is_locked=False,  # Upload entries are never locked
                        edit_history=edit_history)
    
@app.route('/attachment/<int:attachment_id>/download')
def download_attachment(attachment_id):
    """Download an attachment file."""
    import sqlite3
    conn = db.connect()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM attachments WHERE id = ?", (attachment_id,))
    attachment = cursor.fetchone()
    conn.close()
    
    if not attachment:
        return "Attachment not found", 404
    
    from flask import send_file
    return send_file(attachment['filepath'], 
                     as_attachment=True, 
                     download_name=attachment['filename'])
    
@app.route('/attachment/<int:attachment_id>/view')
def view_attachment(attachment_id):
    """View an attachment file in browser."""
    import sqlite3
    conn = db.connect()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM attachments WHERE id = ?", (attachment_id,))
    attachment = cursor.fetchone()
    conn.close()
    
    if not attachment:
        return "Attachment not found", 404
    
    from flask import send_file
    return send_file(attachment['filepath'], 
                     as_attachment=False)  # Opens in browser

@app.route('/attachment/<int:attachment_id>/delete', methods=['POST'])
def delete_attachment(attachment_id):
    """Delete an attachment file and database record."""
    import sqlite3
    import os
    
    conn = db.connect()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get attachment info
    cursor.execute("SELECT * FROM attachments WHERE id = ?", (attachment_id,))
    attachment = cursor.fetchone()
    
    if not attachment:
        conn.close()
        return "Attachment not found", 404
    
    # Get entry info for edit history
    cursor.execute("SELECT * FROM entries WHERE id = ?", (attachment['entry_id'],))
    entry = cursor.fetchone()
    
    # Delete file from disk
    if os.path.exists(attachment['filepath']):
        os.remove(attachment['filepath'])
    
    # Delete from database
    cursor.execute("DELETE FROM attachments WHERE id = ?", (attachment_id,))
    conn.commit()
    
    # Add to edit history (for Upload entries)
    if entry and entry['class'] == 'upload':
        change_desc = f"Deleted file: {attachment['filename']}"
        db.add_to_edit_history(attachment['entry_id'], change_desc)
    
    conn.close()
    
    # Return success for AJAX call
    return '', 200


# EdgeCase Ledger - Flask Routes
# Add these routes to ~/edgecase/web/app.py

# ============================================================================
# LEDGER MAIN VIEW
# ============================================================================

@app.route('/ledger')
def ledger():
    """Display the ledger with all income and expense entries."""
    from datetime import datetime
    
    # Get all ledger entries
    entries = db.get_all_ledger_entries()
    
    # Get currency from settings
    currency = db.get_setting('currency', '$')
    
    # Organize entries by year and month
    entries_by_year_month = {}
    
    for entry in entries:
        if entry.get('ledger_date'):
            entry_dt = datetime.fromtimestamp(entry['ledger_date'])
            year = entry_dt.year
            month = entry_dt.month
            month_name = entry_dt.strftime('%B')  # "November"
            
            if year not in entries_by_year_month:
                entries_by_year_month[year] = {}
            
            if month not in entries_by_year_month[year]:
                entries_by_year_month[year][month] = {
                    'name': month_name,
                    'entries': []
                }
            
            # Get payee and category names for expenses
            if entry['ledger_type'] == 'expense':
                if entry.get('payee_id'):
                    payee = db.get_payee(entry['payee_id'])
                    entry['payee_name'] = payee['name'] if payee else 'Unknown'
                
                if entry.get('category_id'):
                    category = db.get_expense_category(entry['category_id'])
                    entry['category_name'] = category['name'] if category else 'Unknown'
            
            entries_by_year_month[year][month]['entries'].append(entry)
    
    # Sort years (newest first) and months (newest first within year)
    years = sorted(entries_by_year_month.keys(), reverse=True)
    for year in years:
        entries_by_year_month[year] = dict(
            sorted(entries_by_year_month[year].items(), reverse=True)
        )
    
    return render_template('ledger.html',
                         entries_by_year_month=entries_by_year_month,
                         years=years,
                         currency=currency)


# ============================================================================
# INCOME ENTRY ROUTES
# ============================================================================

@app.route('/ledger/income', methods=['GET', 'POST'])
def create_income():
    """Create new income entry."""
    if request.method == 'POST':
        from datetime import datetime
        
        # Parse date from dropdowns
        year = request.form.get('year')
        month = request.form.get('month')
        day = request.form.get('day')
        
        ledger_date_timestamp = None
        if year and month and day:
            date_str = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            ledger_date_timestamp = int(datetime.strptime(date_str, '%Y-%m-%d').timestamp())
        
        # Prepare income entry data
        income_data = {
            'client_id': None,  # Ledger entries are not tied to clients
            'class': 'income',
            'ledger_type': 'income',
            'ledger_date': ledger_date_timestamp,
            'source': request.form.get('source'),
            'total_amount': float(request.form.get('total_amount', 0)),
            'tax_amount': float(request.form.get('tax_amount') or 0),
            'description': request.form.get('description', ''),
            'content': request.form.get('content', '')
        }
        
        # Save income entry first to get entry_id
        entry_id = db.add_entry(income_data)
        
        # Handle file uploads (same as Upload entry)
        files = request.files.getlist('files[]')
        descriptions = request.form.getlist('file_descriptions[]')
        
        if files and files[0].filename:
            from werkzeug.utils import secure_filename
            import os
            import time
            
            # Create upload directory for ledger entry
            upload_dir = os.path.expanduser(f'~/edgecase/attachments/ledger/{entry_id}')
            os.makedirs(upload_dir, exist_ok=True)
            
            # Process each file
            for i, file in enumerate(files):
                if file and file.filename:
                    filename = secure_filename(file.filename)
                    filepath = os.path.join(upload_dir, filename)
                    
                    file.save(filepath)
                    filesize = os.path.getsize(filepath)
                    description = descriptions[i] if i < len(descriptions) and descriptions[i] else filename
                    
                    conn = db.connect()
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO attachments (entry_id, filename, description, filepath, filesize, uploaded_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (entry_id, filename, description, filepath, filesize, int(time.time())))
                    conn.commit()
                    conn.close()
        
        return redirect(url_for('ledger'))
    
    # GET - show form
    from datetime import datetime
    today_dt = datetime.now()
    today = today_dt.strftime('%Y-%m-%d')
    today_year = today_dt.year
    today_month = today_dt.month
    today_day = today_dt.day
    
    currency = db.get_setting('currency', '$')
    
    return render_template('entry_forms/income.html',
                         today=today,
                         today_year=today_year,
                         today_month=today_month,
                         today_day=today_day,
                         currency=currency,
                         is_edit=False)


# Replace the edit_income route in app.py with this version (NO EDIT HISTORY)

@app.route('/ledger/income/<int:entry_id>', methods=['GET', 'POST'])
def edit_income(entry_id):
    """Edit existing income entry."""
    income = db.get_entry(entry_id)
    
    if not income or income['ledger_type'] != 'income':
        return "Income entry not found", 404
    
    if request.method == 'POST':
        from datetime import datetime
        
        # Parse date from dropdowns
        year = request.form.get('year')
        month = request.form.get('month')
        day = request.form.get('day')
        
        ledger_date_timestamp = None
        if year and month and day:
            date_str = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            ledger_date_timestamp = int(datetime.strptime(date_str, '%Y-%m-%d').timestamp())
        
        # Prepare updated income data
        income_data = {
            'ledger_date': ledger_date_timestamp,
            'source': request.form.get('source'),
            'total_amount': float(request.form.get('total_amount', 0)),
            'tax_amount': float(request.form.get('tax_amount') or 0),
            'description': request.form.get('description', ''),
            'content': request.form.get('content', '')
        }
        
        # Handle new file uploads
        files = request.files.getlist('files[]')
        descriptions = request.form.getlist('file_descriptions[]')
        
        if files and files[0].filename:
            from werkzeug.utils import secure_filename
            import os
            import time
            
            upload_dir = os.path.expanduser(f'~/edgecase/attachments/ledger/{entry_id}')
            os.makedirs(upload_dir, exist_ok=True)
            
            for i, file in enumerate(files):
                if file and file.filename:
                    filename = secure_filename(file.filename)
                    filepath = os.path.join(upload_dir, filename)
                    
                    file.save(filepath)
                    filesize = os.path.getsize(filepath)
                    description = descriptions[i] if i < len(descriptions) and descriptions[i] else filename
                    
                    conn = db.connect()
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO attachments (entry_id, filename, description, filepath, filesize, uploaded_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (entry_id, filename, description, filepath, filesize, int(time.time())))
                    conn.commit()
                    conn.close()
        
        # Update the income entry
        db.update_entry(entry_id, income_data)
        
        return redirect(url_for('ledger'))
    
    # GET - show form with existing data
    from datetime import datetime
    
    # Parse income date into year, month, day for dropdowns
    income_year = None
    income_month = None
    income_day = None
    if income.get('ledger_date'):
        income_dt = datetime.fromtimestamp(income['ledger_date'])
        income_year = income_dt.year
        income_month = income_dt.month
        income_day = income_dt.day
    
    # Get attachments for this entry
    attachments = db.get_attachments(entry_id)
    
    currency = db.get_setting('currency', '$')
    
    return render_template('entry_forms/income.html',
                         entry=income,
                         income_year=income_year,
                         income_month=income_month,
                         income_day=income_day,
                         attachments=attachments,
                         currency=currency,
                         is_edit=True)

# Add this route to app.py after the edit_income route

@app.route('/ledger/income/<int:entry_id>/delete', methods=['POST'])
def delete_income_entry(entry_id):
    """Delete income entry and all its attachments."""
    import os
    import shutil
    
    # Get the entry
    entry = db.get_entry(entry_id)
    
    if not entry or entry['ledger_type'] != 'income':
        return "Income entry not found", 404
    
    try:
        # Delete attachments from disk first
        upload_dir = os.path.expanduser(f'~/edgecase/attachments/ledger/{entry_id}')
        if os.path.exists(upload_dir):
            shutil.rmtree(upload_dir)
        
        # Delete attachment records from database
        conn = db.connect()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM attachments WHERE entry_id = ?", (entry_id,))
        
        # Delete the entry itself
        cursor.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
        
        conn.commit()
        conn.close()
        
        return "", 200
    
    except Exception as e:
        print(f"Error deleting income entry: {e}")
        return f"Error: {str(e)}", 500


# ============================================================================
# EXPENSE ENTRY ROUTES
# ============================================================================

@app.route('/ledger/expense', methods=['GET', 'POST'])
def create_expense():
    """Create new expense entry."""
    if request.method == 'POST':
        from datetime import datetime
        
        # Handle new payee creation
        payee_id = request.form.get('payee_id')
        if payee_id == 'new':
            new_payee_name = request.form.get('new_payee_name')
            if new_payee_name:
                payee_id = db.add_payee(new_payee_name)
        else:
            payee_id = int(payee_id)
        
        # Handle new category creation
        category_id = request.form.get('category_id')
        if category_id == 'new':
            new_category_name = request.form.get('new_category_name')
            if new_category_name:
                category_id = db.add_expense_category(new_category_name)
        else:
            category_id = int(category_id)
        
        # Parse date from dropdowns
        year = request.form.get('year')
        month = request.form.get('month')
        day = request.form.get('day')
        
        ledger_date_timestamp = None
        if year and month and day:
            date_str = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            ledger_date_timestamp = int(datetime.strptime(date_str, '%Y-%m-%d').timestamp())
        
        # Prepare expense entry data
        expense_data = {
            'client_id': None,  # Ledger entries are not tied to clients
            'class': 'expense',
            'ledger_type': 'expense',
            'ledger_date': ledger_date_timestamp,
            'payee_id': payee_id,
            'category_id': category_id,
            'total_amount': float(request.form.get('total_amount', 0)),
            'tax_amount': float(request.form.get('tax_amount') or 0),
            'description': request.form.get('description', ''),
            'content': request.form.get('content', '')
        }
        
        # Save expense entry first to get entry_id
        entry_id = db.add_entry(expense_data)
        
        # Handle file uploads (same as Upload/Income)
        files = request.files.getlist('files[]')
        descriptions = request.form.getlist('file_descriptions[]')
        
        if files and files[0].filename:
            from werkzeug.utils import secure_filename
            import os
            import time
            
            upload_dir = os.path.expanduser(f'~/edgecase/attachments/ledger/{entry_id}')
            os.makedirs(upload_dir, exist_ok=True)
            
            for i, file in enumerate(files):
                if file and file.filename:
                    filename = secure_filename(file.filename)
                    filepath = os.path.join(upload_dir, filename)
                    
                    file.save(filepath)
                    filesize = os.path.getsize(filepath)
                    description = descriptions[i] if i < len(descriptions) and descriptions[i] else filename
                    
                    conn = db.connect()
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO attachments (entry_id, filename, description, filepath, filesize, uploaded_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (entry_id, filename, description, filepath, filesize, int(time.time())))
                    conn.commit()
                    conn.close()
        
        return redirect(url_for('ledger'))
    
    # GET - show form
    from datetime import datetime
    today_dt = datetime.now()
    today = today_dt.strftime('%Y-%m-%d')
    today_year = today_dt.year
    today_month = today_dt.month
    today_day = today_dt.day
    
    # Get payees and categories for dropdowns
    payees = db.get_all_payees()
    categories = db.get_all_expense_categories()
    
    currency = db.get_setting('currency', '$')
    
    return render_template('entry_forms/expense.html',
                         today=today,
                         today_year=today_year,
                         today_month=today_month,
                         today_day=today_day,
                         payees=payees,
                         categories=categories,
                         currency=currency,
                         is_edit=False)


@app.route('/ledger/expense/<int:entry_id>', methods=['GET', 'POST'])
def edit_expense(entry_id):
    """Edit existing expense entry."""
    expense = db.get_entry(entry_id)
    
    if not expense or expense['ledger_type'] != 'expense':
        return "Expense entry not found", 404
    
    if request.method == 'POST':
        from datetime import datetime
        
        # Get old entry for edit history comparison
        old_expense = expense.copy()
        
        # Handle new payee creation
        payee_id = request.form.get('payee_id')
        if payee_id == 'new':
            new_payee_name = request.form.get('new_payee_name')
            if new_payee_name:
                payee_id = db.add_payee(new_payee_name)
        else:
            payee_id = int(payee_id)
        
        # Handle new category creation
        category_id = request.form.get('category_id')
        if category_id == 'new':
            new_category_name = request.form.get('new_category_name')
            if new_category_name:
                category_id = db.add_expense_category(new_category_name)
        else:
            category_id = int(category_id)
        
        # Parse date from dropdowns
        year = request.form.get('year')
        month = request.form.get('month')
        day = request.form.get('day')
        
        ledger_date_timestamp = None
        if year and month and day:
            date_str = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            ledger_date_timestamp = int(datetime.strptime(date_str, '%Y-%m-%d').timestamp())
        
        # Prepare updated expense data
        expense_data = {
            'ledger_date': ledger_date_timestamp,
            'payee_id': payee_id,
            'category_id': category_id,
            'total_amount': float(request.form.get('total_amount', 0)),
            'tax_amount': float(request.form.get('tax_amount') or 0),
            'description': request.form.get('description', ''),
            'content': request.form.get('content', '')
        }
        
        # Generate edit history (Expense entries NOT locked, but track changes)
        import difflib
        changes = []
        
        # Date
        if old_expense.get('ledger_date') != ledger_date_timestamp:
            old_date = datetime.fromtimestamp(old_expense['ledger_date']).strftime('%Y-%m-%d') if old_expense.get('ledger_date') else 'None'
            new_date = datetime.fromtimestamp(ledger_date_timestamp).strftime('%Y-%m-%d') if ledger_date_timestamp else 'None'
            changes.append(f"Date: {old_date} → {new_date}")
        
        # Payee
        if old_expense.get('payee_id') != payee_id:
            old_payee = db.get_payee(old_expense['payee_id']) if old_expense.get('payee_id') else None
            new_payee = db.get_payee(payee_id)
            old_name = old_payee['name'] if old_payee else 'None'
            new_name = new_payee['name'] if new_payee else 'None'
            changes.append(f"Payee: {old_name} → {new_name}")
        
        # Category
        if old_expense.get('category_id') != category_id:
            old_cat = db.get_expense_category(old_expense['category_id']) if old_expense.get('category_id') else None
            new_cat = db.get_expense_category(category_id)
            old_name = old_cat['name'] if old_cat else 'None'
            new_name = new_cat['name'] if new_cat else 'None'
            changes.append(f"Category: {old_name} → {new_name}")
        
        # Total Amount
        old_total = float(old_expense.get('total_amount') or 0)
        new_total = float(expense_data.get('total_amount') or 0)
        if old_total != new_total:
            changes.append(f"Total Amount: ${old_total:.2f} → ${new_total:.2f}")
        
        # Tax Amount
        old_tax = float(old_expense.get('tax_amount') or 0)
        new_tax = float(expense_data.get('tax_amount') or 0)
        if old_tax != new_tax:
            changes.append(f"Tax: ${old_tax:.2f} → ${new_tax:.2f}")
        
        # Description (with smart diff)
        if old_expense.get('description') != expense_data.get('description'):
            old_desc = old_expense.get('description') or ''
            new_desc = expense_data.get('description') or ''
            
            if old_desc and new_desc:
                old_words = old_desc.split()
                new_words = new_desc.split()
                diff = difflib.ndiff(old_words, new_words)
                
                formatted_parts = []
                for item in diff:
                    if item.startswith('  '):
                        formatted_parts.append(item[2:])
                    elif item.startswith('- '):
                        formatted_parts.append(f'<del>{item[2:]}</del>')
                    elif item.startswith('+ '):
                        formatted_parts.append(f'<strong>{item[2:]}</strong>')
                
                diff_text = ' '.join(formatted_parts)
                if len(diff_text) > 100:
                    diff_text = diff_text[:100] + '...'
                
                changes.append(f"Description: {diff_text}")
            elif old_desc:
                changes.append("Description: Cleared")
            else:
                changes.append("Description: Added")
        
        # Content (with smart diff)
        if old_expense.get('content') != expense_data.get('content'):
            old_content = old_expense.get('content') or ''
            new_content = expense_data.get('content') or ''
            
            if old_content and new_content:
                old_words = old_content.split()
                new_words = new_content.split()
                diff = difflib.ndiff(old_words, new_words)
                
                formatted_parts = []
                for item in diff:
                    if item.startswith('  '):
                        formatted_parts.append(item[2:])
                    elif item.startswith('- '):
                        formatted_parts.append(f'<del>{item[2:]}</del>')
                    elif item.startswith('+ '):
                        formatted_parts.append(f'<strong>{item[2:]}</strong>')
                
                diff_text = ' '.join(formatted_parts)
                if len(diff_text) > 150:
                    diff_text = diff_text[:150] + '...'
                
                changes.append(f"Content: {diff_text}")
            elif old_content:
                changes.append("Content: Cleared")
            else:
                changes.append("Content: Added")
        
        # Handle new file uploads (same as Upload/Income)
        files = request.files.getlist('files[]')
        descriptions = request.form.getlist('file_descriptions[]')
        
        if files and files[0].filename:
            from werkzeug.utils import secure_filename
            import os
            import time
            
            upload_dir = os.path.expanduser(f'~/edgecase/attachments/ledger/{entry_id}')
            os.makedirs(upload_dir, exist_ok=True)
            
            added_files = []
            
            for i, file in enumerate(files):
                if file and file.filename:
                    filename = secure_filename(file.filename)
                    filepath = os.path.join(upload_dir, filename)
                    
                    file.save(filepath)
                    filesize = os.path.getsize(filepath)
                    description = descriptions[i] if i < len(descriptions) and descriptions[i] else filename
                    
                    conn = db.connect()
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO attachments (entry_id, filename, description, filepath, filesize, uploaded_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (entry_id, filename, description, filepath, filesize, int(time.time())))
                    conn.commit()
                    conn.close()
                    
                    added_files.append(filename)
            
            if added_files:
                changes.append(f"Added files: {', '.join(added_files)}")
        
        if changes:
            change_desc = "; ".join(changes)
            db.add_to_edit_history(entry_id, change_desc)
        
        # Update the expense entry
        db.update_entry(entry_id, expense_data)
        
        return redirect(url_for('ledger'))
    
    # GET - show form with existing data
    from datetime import datetime
    
    # Parse expense date into year, month, day for dropdowns
    expense_year = None
    expense_month = None
    expense_day = None
    if expense.get('ledger_date'):
        expense_dt = datetime.fromtimestamp(expense['ledger_date'])
        expense_year = expense_dt.year
        expense_month = expense_dt.month
        expense_day = expense_dt.day
    
    # Get payees and categories for dropdowns
    payees = db.get_all_payees()
    categories = db.get_all_expense_categories()
    
    # Get attachments for this entry
    attachments = db.get_attachments(entry_id)
    
    # Get edit history
    edit_history_raw = db.get_edit_history(entry_id)
    edit_history = []
    for edit in edit_history_raw:
        edit_dt = datetime.fromtimestamp(edit['timestamp'])
        edit['timestamp_formatted'] = edit_dt.strftime('%B %d, %Y at %I:%M %p')
        edit_history.append(edit)
    
    currency = db.get_setting('currency', '$')
    
    return render_template('entry_forms/expense.html',
                         entry=expense,
                         expense_year=expense_year,
                         expense_month=expense_month,
                         expense_day=expense_day,
                         payees=payees,
                         categories=categories,
                         attachments=attachments,
                         edit_history=edit_history,
                         currency=currency,
                         is_edit=True)


# ============================================================================
# NOTES
# ============================================================================

# These routes integrate with existing attachment routes:
# - /attachment/<id>/download (already exists)
# - /attachment/<id>/view (already exists)
# - /attachment/<id>/delete (already exists)

# Attachment storage:
# - Income/Expense: ~/edgecase/attachments/ledger/{entry_id}/
# - Upload entries: ~/edgecase/attachments/{client_id}/{entry_id}/

# Edit history:
# - Uses existing edit_history functions in database.py
# - Income/Expense entries NOT locked (editable accounting records)
# - All changes tracked with smart word-level diff

# EdgeCase Ledger - Jinja2 Filter for Timestamp Conversion
# Add this code to ~/edgecase/web/app.py after the Flask app initialization

# Add this AFTER the line: app = Flask(__name__)

# ============================================================================
# JINJA2 CUSTOM FILTERS
# ============================================================================

@app.template_filter('timestamp_to_datetime')
def timestamp_to_datetime_filter(timestamp):
    """Convert Unix timestamp to datetime object for Jinja2 templates."""
    from datetime import datetime
    if timestamp:
        return datetime.fromtimestamp(timestamp)
    return None

# Now you can use this filter in templates like:
# {{ entry.ledger_date | timestamp_to_datetime }}
# And then call strftime on it:
# {% set entry_dt = entry.ledger_date | timestamp_to_datetime %}
# {{ entry_dt.strftime('%b %d') }}

# Add this near line 3280 in app.py with other Jinja2 filters

@app.template_filter('currency_symbol')
def currency_symbol_filter(currency_code):
    """Convert currency code to symbol"""
    symbols = {
        'CAD': '$',
        'USD': '$',
        'EUR': '€',
        'GBP': '£',
        'AUD': '$',
        'INR': '₹',
        'JPY': '¥'
    }
    return symbols.get(currency_code, currency_code)

# ===== CLIENT TYPE MANAGEMENT =====

@app.route('/types')
def manage_types():
    """Display client types with locked and editable sections."""
    all_types = db.get_all_client_types()
    
    # Separate locked (Inactive, Deleted) from editable types
    locked_types = [t for t in all_types if t.get('is_system_locked')]
    editable_types = [t for t in all_types if not t.get('is_system_locked')]
    
    # Sort editable types alphabetically
    editable_types.sort(key=lambda t: t['name'])
    
    return render_template('manage_types.html',
                         locked_types=locked_types,
                         editable_types=editable_types)
    
@app.route('/add_type', methods=['GET', 'POST'])
def add_type():
    """Add a new client type"""
    if request.method == 'POST':
        # Convert retention value + unit to days
        retention_value = int(request.form.get('retention_value', 0))
        retention_unit = request.form.get('retention_unit', 'months')
        
        if retention_unit == 'days':
            retention_days = retention_value
        elif retention_unit == 'months':
            retention_days = retention_value * 30
        else:  # years
            retention_days = retention_value * 365
        
        type_data = {
            'name': request.form['name'],
            'color': request.form['color'],
            'color_name': request.form['color_name'],
            'bubble_color': request.form['bubble_color'],
            'retention_period': retention_days,
            'is_system': 0,
            'is_system_locked': 0
        }
        
        try:
            db.add_client_type(type_data)
            return redirect(url_for('manage_types'))
        except Exception as e:
            error_message = "A type with that name already exists." if "UNIQUE constraint" in str(e) else str(e)
            return render_template('add_edit_type.html', type=None, colors=COLOR_PALETTE, error=error_message)
    
    return render_template('add_edit_type.html', type=None, colors=COLOR_PALETTE)

@app.route('/edit_type/<int:type_id>', methods=['GET', 'POST'])
def edit_type(type_id):
    """Edit an existing client type"""
    type_obj = db.get_client_type(type_id)
    
    if not type_obj:
        return redirect(url_for('manage_types'))
    
    # Can't edit locked system types
    if type_obj.get('is_system_locked'):
        return redirect(url_for('manage_types'))
    
    if request.method == 'POST':
        # Check for delete action
        if request.form.get('_method') == 'DELETE':
            # Check if any clients use this type
            clients = db.get_all_clients(type_id=type_id)
            if clients:
                # Can't delete if clients exist
                return redirect(url_for('manage_types'))
            
            db.delete_client_type(type_id)
            return redirect(url_for('manage_types'))
        
        # Convert retention value + unit to days
        retention_value = int(request.form.get('retention_value', 0))
        retention_unit = request.form.get('retention_unit', 'months')
        
        if retention_unit == 'days':
            retention_days = retention_value
        elif retention_unit == 'months':
            retention_days = retention_value * 30
        else:  # years
            retention_days = retention_value * 365
        
        # Regular update
        type_data = {
            'name': request.form['name'],
            'color': request.form['color'],
            'color_name': request.form['color_name'],
            'bubble_color': request.form['bubble_color'],
            'retention_period': retention_days
        }
        
        db.update_client_type(type_id, type_data)
        return redirect(url_for('manage_types'))
    
    # Calculate retention_value and retention_unit for display
    retention_days = type_obj.get('retention_period') or 0
    if retention_days >= 365 and retention_days % 365 == 0:
        retention_value = retention_days // 365
        retention_unit = 'years'
    elif retention_days >= 30 and retention_days % 30 == 0:
        retention_value = retention_days // 30
        retention_unit = 'months'
    else:
        retention_value = retention_days
        retention_unit = 'days'
    
    return render_template('add_edit_type.html', 
                         type=type_obj, 
                         colors=COLOR_PALETTE,
                         retention_value=retention_value,
                         retention_unit=retention_unit)


@app.route('/types/<int:type_id>/delete', methods=['POST'])
def delete_type(type_id):
    """Delete client type (only if no clients assigned and not locked)."""
    type_obj = db.get_client_type(type_id)
    
    if not type_obj:
        return jsonify({'success': False, 'error': 'Type not found'}), 404
    
    # Check if locked
    if type_obj.get('is_system_locked'):
        return jsonify({'success': False, 'error': 'Cannot delete locked system types'}), 403
    
    # Check if this is the last editable type
    all_types = db.get_all_client_types()
    editable_types = [t for t in all_types if not t.get('is_system_locked')]
    
    if len(editable_types) <= 1:
        return jsonify({
            'success': False,
            'error': 'Cannot delete: At least one editable client type must exist'
        }), 400
    
    # Check if any clients are assigned to this type
    clients = db.get_all_clients(type_id=type_id)
    if clients:
        return jsonify({
            'success': False, 
            'error': f'Cannot delete: {len(clients)} client(s) are assigned to this type'
        }), 400
    
    # Delete the type
    success = db.delete_client_type(type_id)
    
    if success:
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': 'Database error'}), 500
    
# ===========================

@app.route('/links')
def manage_links():
    """Manage client linking groups"""
    link_groups = db.get_all_link_groups()
    all_clients = db.get_all_clients()
    
    # Add type info to all clients for display
    for client in all_clients:
        client['type'] = db.get_client_type(client['type_id'])
    
    # Add type info to members in each link group
    for group in link_groups:
        for member in group.get('members', []):
            member['type'] = db.get_client_type(member['type_id'])
    
    return render_template('manage_links.html', 
                         link_groups=link_groups,
                         all_clients=all_clients)

@app.route('/settings')
def settings_page():
    """Settings page."""
    return render_template('settings.html')

@app.route('/financials')
def financials():
    """Financial tracking - Income and Expense ledger"""
    return render_template('financials.html')

@app.route('/scheduler')
def scheduler():
    """Scheduler page - placeholder for future calendar/appointment features"""
    return render_template('scheduler.html')

@app.route('/billing')
def billing():
    """Billing page - placeholder for future invoicing/statement features"""
    return render_template('billing.html')

@app.route('/api/backgrounds')
def list_backgrounds():
    """Return list of available backgrounds separated by system and user"""
    import os
    
    # System backgrounds (bundled)
    system_dir = Path(__file__).parent / 'static' / 'img'
    system_backgrounds = []
    
    if system_dir.exists():
        for file in system_dir.iterdir():
            if file.is_file() and file.suffix.lower() in ['.png', '.jpg', '.jpeg', '.gif', '.webp']:
                system_backgrounds.append(file.name)
    
    # User backgrounds (uploaded)
    user_dir = Path(__file__).parent / 'static' / 'user_backgrounds'
    user_backgrounds = []
    
    if user_dir.exists():
        for file in user_dir.iterdir():
            if file.is_file() and file.suffix.lower() in ['.png', '.jpg', '.jpeg', '.gif', '.webp']:
                user_backgrounds.append(file.name)
    
    return jsonify({
        'system': sorted(system_backgrounds),
        'user': sorted(user_backgrounds)
    })


@app.route('/upload_background', methods=['POST'])
def upload_background():
    """Handle background image upload to user_backgrounds directory"""
    if 'background' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'})
    
    file = request.files['background']
    
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'})
    
    # Validate file type
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
    
    if file_ext not in allowed_extensions:
        return jsonify({'success': False, 'error': 'Invalid file type. Use: png, jpg, jpeg, gif, or webp'})
    
    # Create safe filename
    from werkzeug.utils import secure_filename
    filename = secure_filename(file.filename)
    
    # Create user_backgrounds directory if it doesn't exist
    upload_dir = Path(__file__).parent / 'static' / 'user_backgrounds'
    upload_dir.mkdir(exist_ok=True)
    
    # Save to user_backgrounds directory
    upload_path = upload_dir / filename
    
    try:
        file.save(str(upload_path))
        return jsonify({'success': True, 'filename': filename})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/delete_background', methods=['POST'])
def delete_background():
    """Delete a user-uploaded background"""
    import os
    
    data = request.get_json()
    filename = data.get('filename')
    
    if not filename:
        return jsonify({'success': False, 'error': 'No filename provided'})
    
    # Only allow deleting from user_backgrounds directory
    user_dir = Path(__file__).parent / 'static' / 'user_backgrounds'
    file_path = user_dir / filename
    
    # Security check: ensure the file is actually in user_backgrounds
    try:
        file_path = file_path.resolve()
        user_dir = user_dir.resolve()
        
        if not str(file_path).startswith(str(user_dir)):
            return jsonify({'success': False, 'error': 'Invalid file path'})
        
        if file_path.exists():
            os.remove(file_path)
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'File not found'})
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/practice_info', methods=['GET', 'POST'])
def practice_info():
    """Get or save practice information"""
    if request.method == 'GET':
        # Fetch all practice info from settings table
        # Get all the specific keys we need
        keys = [
            'practice_name', 'therapist_name', 'credentials', 'email', 'phone',
            'address', 'website',
            'consultation_base_price', 'consultation_tax_rate', 'consultation_fee', 'consultation_duration',
            'logo_filename', 'signature_filename',
            'currency'
        ]
        
        placeholders = ','.join(['?' for _ in keys])
        query = f"SELECT key, value FROM settings WHERE key IN ({placeholders})"
        
        with sqlite3.connect(db.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, keys)
            rows = cursor.fetchall()
        
        info = {}
        for row in rows:
            info[row[0]] = row[1]
        
        return jsonify({'success': True, 'info': info})
    
    else:  # POST
        data = request.get_json()
        
        # Save each field to settings table
        settings_map = {
            'practice_name': data.get('practice_name', ''),
            'therapist_name': data.get('therapist_name', ''),
            'credentials': data.get('credentials', ''),
            'email': data.get('email', ''),
            'phone': data.get('phone', ''),
            'address': data.get('address', ''),  # CHANGED: single address field
            'website': data.get('website', ''),
            'currency': data.get('currency', 'CAD'),
            'consultation_base_price': data.get('consultation_base_price', '0.00'),
            'consultation_tax_rate': data.get('consultation_tax_rate', '0.00'),
            'consultation_fee': data.get('consultation_fee', '0.00'),
            'consultation_duration': data.get('consultation_duration', '20')
        }
        
        import time
        modified_at = int(time.time())
        
        with sqlite3.connect(db.db_path) as conn:
            cursor = conn.cursor()
            for key, value in settings_map.items():
                cursor.execute("""
                    INSERT INTO settings (key, value, modified_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = ?, modified_at = ?
                """, (key, value, modified_at, value, modified_at))
            conn.commit()
        
        return jsonify({'success': True})


@app.route('/upload_logo', methods=['POST'])
def upload_logo():
    """Handle practice logo upload"""
    if 'logo' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'})
    
    file = request.files['logo']
    
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'})
    
    # Validate file type
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
    file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
    
    if file_ext not in allowed_extensions:
        return jsonify({'success': False, 'error': 'Invalid file type. Use: png, jpg, jpeg, or gif'})
    
    # Save as 'logo.png' (or whatever extension)
    from werkzeug.utils import secure_filename
    filename = f'logo.{file_ext}'
    
    # Save to assets directory
    assets_dir = Path(__file__).parent.parent / 'assets'
    assets_dir.mkdir(exist_ok=True)
    
    upload_path = assets_dir / filename
    
    try:
        file.save(str(upload_path))
        
        # Save filename to settings using proper connection
        import time
        modified_at = int(time.time())
        
        with sqlite3.connect(db.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO settings (key, value, modified_at)
                VALUES ('logo_filename', ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = ?, modified_at = ?
            """, (filename, modified_at, filename, modified_at))
            conn.commit()
        
        return jsonify({'success': True, 'filename': filename})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/upload_signature', methods=['POST'])
def upload_signature():
    """Handle signature upload"""
    if 'signature' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'})
    
    file = request.files['signature']
    
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'})
    
    # Validate file type
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
    file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
    
    if file_ext not in allowed_extensions:
        return jsonify({'success': False, 'error': 'Invalid file type. Use: png, jpg, jpeg, or gif'})
    
    # Save as 'signature.png' (or whatever extension)
    from werkzeug.utils import secure_filename
    filename = f'signature.{file_ext}'
    
    # Save to assets directory
    assets_dir = Path(__file__).parent.parent / 'assets'
    assets_dir.mkdir(exist_ok=True)
    
    upload_path = assets_dir / filename
    
    try:
        file.save(str(upload_path))
        
        # Save filename to settings using proper connection
        import time
        modified_at = int(time.time())
        
        with sqlite3.connect(db.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO settings (key, value, modified_at)
                VALUES ('signature_filename', ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = ?, modified_at = ?
            """, (filename, modified_at, filename, modified_at))
            conn.commit()
        
        return jsonify({'success': True, 'filename': filename})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    
@app.route('/delete_logo', methods=['POST'])
def delete_logo():
    """Delete practice logo"""
    try:
        # Get current logo filename from settings
        with sqlite3.connect(db.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = 'logo_filename'")
            row = cursor.fetchone()
            
            if row:
                filename = row[0]
                
                # Delete file from assets directory
                assets_dir = Path(__file__).parent.parent / 'assets'
                logo_path = assets_dir / filename
                
                if logo_path.exists():
                    logo_path.unlink()
                
                # Remove from settings
                cursor.execute("DELETE FROM settings WHERE key = 'logo_filename'")
                conn.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/delete_signature', methods=['POST'])
def delete_signature():
    """Delete digital signature"""
    try:
        # Get current signature filename from settings
        with sqlite3.connect(db.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = 'signature_filename'")
            row = cursor.fetchone()
            
            if row:
                filename = row[0]
                
                # Delete file from assets directory
                assets_dir = Path(__file__).parent.parent / 'assets'
                signature_path = assets_dir / filename
                
                if signature_path.exists():
                    signature_path.unlink()
                
                # Remove from settings
                cursor.execute("DELETE FROM settings WHERE key = 'signature_filename'")
                conn.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    
    # Add these routes to app.py

@app.route('/settings/file-number', methods=['GET', 'POST'])
def file_number_settings():
    """Get or save file number format settings."""
    if request.method == 'POST':
        data = request.json
        
        # Save settings to database
        db.set_setting('file_number_format', data['format'])
        db.set_setting('file_number_prefix', data.get('prefix', ''))
        db.set_setting('file_number_suffix', data.get('suffix', ''))
        db.set_setting('file_number_counter', str(data.get('counter', 1)))
        
        return jsonify({'success': True})
    
    # GET - return current settings
    counter_value = db.get_setting('file_number_counter', '1')
    # Handle None case (setting doesn't exist yet)
    if counter_value is None or counter_value == 'None':
        counter_value = '1'
    
    settings = {
        'format': db.get_setting('file_number_format', 'manual'),
        'prefix': db.get_setting('file_number_prefix', ''),
        'suffix': db.get_setting('file_number_suffix', ''),
        'counter': int(counter_value)
    }
    
    return jsonify(settings)

@app.route('/add_client', methods=['GET', 'POST'])
def add_client():
    """Add new client with auto-generated file number support."""
    if request.method == 'POST':
        # Get file number format setting
        format_type = db.get_setting('file_number_format', 'manual')
        
        # Generate file number based on format
        if format_type == 'manual':
            # User-provided file number
            file_number = request.form['file_number']
        
        elif format_type == 'date-initials':
            # YYYYMMDD-ABC format
            from datetime import datetime
            date_str = datetime.now().strftime('%Y%m%d')
            
            first = request.form['first_name'][0].upper()
            middle = request.form.get('middle_name', '')
            middle = middle[0].upper() if middle else ''
            last = request.form['last_name'][0].upper()
            
            initials = first + middle + last
            file_number = f"{date_str}-{initials}"
        
        elif format_type == 'prefix-counter':
            # Prefix-Counter-Suffix format
            prefix = db.get_setting('file_number_prefix', '')
            suffix = db.get_setting('file_number_suffix', '')
            counter = int(db.get_setting('file_number_counter', '1'))
            
            # Build file number
            parts = []
            if prefix:
                parts.append(prefix)
            parts.append(str(counter).zfill(4))  # 4-digit padded number
            if suffix:
                parts.append(suffix)
            
            file_number = '-'.join(parts)
            
            # Increment counter for next time
            db.set_setting('file_number_counter', str(counter + 1))
        
        else:
            # Fallback to manual
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
        return redirect(url_for('client_file', client_id=client_id))
    
    # GET request - show form
    all_types = db.get_all_client_types()
    
    # Get file number format for UI
    format_type = db.get_setting('file_number_format', 'manual')
    
    # Generate preview/placeholder based on format
    file_number_preview = ''
    file_number_readonly = False
    
    if format_type == 'date-initials':
        from datetime import datetime
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

@app.route('/links/<int:group_id>/delete', methods=['POST'])
def delete_link_group(group_id):
    """Delete a link group"""
    success = db.delete_link_group(group_id)
    if success:
        return '', 204  # No content, success
    return 'Error deleting group', 500

@app.route('/links/add', methods=['GET', 'POST'])
def add_link_group():
    """Add a new link group"""
    if request.method == 'POST':
        data = request.json
        
        # Validate
        if not data.get('client_ids'):
            return 'Missing client IDs', 400
        
        if len(data['client_ids']) < 2:
            return 'At least 2 clients required', 400
        
        if not data.get('format'):
            return 'Missing session format', 400
        
        if not data.get('member_fees'):
            return 'Missing member fees', 400
        
        # Get duration (default to 50 if not provided)
        session_duration = int(data.get('session_duration', 50))

        # Create link group with format, duration, and member fees
        # Retry once if database is locked
        for attempt in range(2):
            try:
                group_id = db.create_link_group(
                    client_ids=data['client_ids'],
                    format=data['format'],
                    session_duration=session_duration,
                    member_fees=data['member_fees']
                )
                return '', 204
                
            except sqlite3.OperationalError as e:
                if attempt == 0:
                    time.sleep(0.1)  # Wait 100ms and retry
                    continue
                return 'Database is temporarily locked. Please try again.', 503
            except sqlite3.IntegrityError as e:
                return f'Database error: {str(e)}', 400
            except ValueError as e:
                return str(e), 400
    
    # GET: Show the form - exclude Inactive and Deleted clients
    all_clients = db.get_all_clients()
    
    # GET: Show the form - exclude Inactive and Deleted clients
    all_clients = db.get_all_clients()
    
    # Filter out Inactive and Deleted clients and add type info + Profile fees
    active_clients = []
    for client in all_clients:
        client_type = db.get_client_type(client['type_id'])
        client['type'] = client_type
        if client_type['name'] not in ['Inactive', 'Deleted']:
            # Get Profile entry for fee defaults
            profile = db.get_profile_entry(client['id'])
            if profile:
                client['profile_base_fee'] = profile.get('fee_override_base', 0)
                client['profile_tax_rate'] = profile.get('fee_override_tax_rate', 0)
                client['profile_total_fee'] = profile.get('fee_override_total', 0)
                client['profile_duration'] = profile.get('default_session_duration', 50)
            else:
                # Defaults if no profile
                client['profile_base_fee'] = 0
                client['profile_tax_rate'] = 0
                client['profile_total_fee'] = 0
                client['profile_duration'] = 50
            active_clients.append(client)
    
    return render_template('add_edit_link_group.html',
                         all_clients=active_clients,
                         group=None)

@app.route('/links/<int:group_id>/edit', methods=['GET', 'POST'])
def edit_link_group(group_id):
    """Edit an existing link group"""
    if request.method == 'POST':
        data = request.json
        
        # Validate
        if not data.get('client_ids'):
            return 'Missing client IDs', 400
        
        if len(data['client_ids']) < 2:
            return 'At least 2 clients required', 400
        
        if not data.get('format'):
            return 'Missing session format', 400
        
        if not data.get('member_fees'):
            return 'Missing member fees', 400
        
        # Get duration (default to 50 if not provided)
        session_duration = int(data.get('session_duration', 50))
        
        # Update link group
        success = db.update_link_group(
            group_id=group_id,
            client_ids=data['client_ids'],
            format=data['format'],
            session_duration=session_duration,
            member_fees=data['member_fees']
        )
        
        if success:
            return '', 204
        else:
            return 'Error updating link group', 500
    
    # GET: Show the form with existing group data
    group = db.get_link_group(group_id)
    
    # Exclude Inactive and Deleted clients
    all_clients = db.get_all_clients()
    
    # Filter out Inactive and Deleted clients and add type info
    active_clients = []
    for client in all_clients:
        client_type = db.get_client_type(client['type_id'])
        client['type'] = client_type
        if client_type['name'] not in ['Inactive', 'Deleted']:
            active_clients.append(client)
    
    # Add type info to group members
    if group and 'members' in group:
        for member in group['members']:
            member['type'] = db.get_client_type(member['type_id'])
    
    return render_template('add_edit_link_group.html',
                         all_clients=active_clients,
                         group=group)
    
# Also need to add these helper methods to database.py:

def set_setting(self, key: str, value: str):
    """Set a setting value."""
    import time
    conn = self.connect()
    cursor = conn.cursor()
    
    now = int(time.time())
    cursor.execute("""
        INSERT INTO settings (key, value, modified_at) 
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value=?, modified_at=?
    """, (key, value, now, value, now))
    
    conn.commit()
    conn.close()


def get_setting(self, key: str, default: str = '') -> str:
    """Get a setting value."""
    conn = self.connect()
    cursor = conn.cursor()
    
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    
    return row[0] if row else default
    
# ===== RUN APP =====

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)