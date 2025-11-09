# -*- coding: utf-8 -*-
"""
EdgeCase Flask Application
Main web interface for EdgeCase Equalizer
"""

from flask import Flask, render_template, request, redirect, url_for, jsonify
from pathlib import Path
import sys

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

@app.template_filter('timestamp_to_date')
def timestamp_to_date(timestamp):
    """Convert Unix timestamp to readable date."""
    if not timestamp:
        return '-'
    return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')

# ===== ROUTES =====

@app.route('/')
def index():
    """Main view - client list with stats cards."""
    # Get filter parameters
    type_filter = request.args.getlist('type')  # Can select multiple types
    sort_by = request.args.get('sort', 'last_name')  # Default sort by last name
    sort_order = request.args.get('order', 'asc')  # Default ascending
    search = request.args.get('search', '')
    view_mode = request.args.get('view', 'compact')  # 'detailed' or 'compact'
    
    # Get all client types for filter
    all_types = db.get_all_client_types()
    
    # If no types selected, default to Active only
    if not type_filter:
        active_type = next((t for t in all_types if t['name'] == 'Active'), None)
        if active_type:
            type_filter = [str(active_type['id'])]
    
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
        
        # Get last session date
        last_session = db.get_last_session_date(client['id'])
        client['last_session'] = last_session
        
        # Get current date and time
        from datetime import datetime
        now = datetime.now()
        current_date = now.strftime('%B %d, %Y')  # "November 9, 2025"
        current_time = now.strftime('%I:%M %p')    # "12:45 PM"
        
        # Get payment status
        client['payment_status'] = db.get_payment_status(client['id'])
    
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
        clients.sort(key=lambda c: c.get('last_session', 0), reverse=(sort_order == 'desc'))
    
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
    
    # Get profile entry separately (pinned at top)
    profile_entry = db.get_profile_entry(client_id)
    
    # Get all session entries for this client
    all_entries = db.get_client_entries(client_id, entry_class='session')
    
    # Count sessions vs consultations
    session_count = sum(1 for e in all_entries if not e.get('is_consultation'))
    consultation_count = sum(1 for e in all_entries if e.get('is_consultation'))
    
    # Group entries by year and month
    from collections import defaultdict
    from datetime import datetime
    
    # Get current year and month for default expand state
    now = datetime.now()
    current_year = now.year
    current_month = now.month
    
    # Organize entries by year -> month
    year_dict = defaultdict(lambda: defaultdict(list))
    
    for entry in all_entries:
        if entry.get('session_date'):
            entry_date = datetime.fromtimestamp(entry['session_date'])
            year = entry_date.year
            month = entry_date.month
            year_dict[year][month].append(entry)
    
    # Convert to list structure for template
    entries_by_year = []
    for year in sorted(year_dict.keys(), reverse=True):  # Most recent year first
        months = []
        year_total = 0
        
        for month in sorted(year_dict[year].keys(), reverse=True):  # Most recent month first
            month_entries = sorted(year_dict[year][month], 
                                 key=lambda e: e.get('session_date', 0), 
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
                         profile_entry=profile_entry,
                         entries_by_year=entries_by_year,
                         session_count=session_count,
                         consultation_count=consultation_count)

@app.route('/add_client', methods=['GET', 'POST'])
def add_client():
    """Add new client."""
    if request.method == 'POST':
        # Get form data
        client_data = {
            'file_number': request.form['file_number'],
            'first_name': request.form['first_name'],
            'middle_name': request.form.get('middle_name', ''),
            'last_name': request.form['last_name'],
            'type_id': int(request.form['type_id'])
        }
        
        # Add client to database
        client_id = db.add_client(client_data)
        
        # Redirect to client file to create profile entry
        return redirect(url_for('client_file', client_id=client_id))
    
    # GET request - show form
    all_types = db.get_all_client_types()
    return render_template('add_client.html', all_types=all_types)

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
            'additional_info': request.form.get('additional_info', '')
        }
        
        if profile:
            # Update existing profile
            db.update_entry(profile['id'], profile_data)
        else:
            # Create new profile
            db.add_entry(profile_data)
        
        # Update client record if names changed
        import time
        if request.form.get('first_name') != client['first_name'] or \
           request.form.get('middle_name', '') != (client.get('middle_name') or '') or \
           request.form.get('last_name') != client['last_name']:
            
            client_updates = {
                'first_name': request.form.get('first_name'),
                'middle_name': request.form.get('middle_name') or None,
                'last_name': request.form.get('last_name'),
                'modified_at': int(time.time())
            }
            db.update_client(client_id, client_updates)
        
        return redirect(url_for('client_file', client_id=client_id))
    
    # GET request - show form
    return render_template('entry_forms/profile.html',
                         client=client,
                         profile=profile)
    
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
        
        # Auto-generate session number (count of non-consultation sessions + 1)
        session_entries = db.get_client_entries(client_id, 'session')
        non_consultation_count = sum(1 for s in session_entries if not s.get('is_consultation'))
        
        # Get form data
        session_data = {
            'client_id': client_id,
            'class': 'session',
            'created_at': int(time.time()),
            'modified_at': int(time.time()),
            
            # Session fields
            'modality': request.form.get('modality'),
            'format': request.form.get('format'),
            'session_date': int(datetime.strptime(request.form.get('session_date'), '%Y-%m-%d').timestamp()) if request.form.get('session_date') else None,
            'session_time': request.form.get('session_time') or None,
            'duration': int(request.form.get('duration')) if request.form.get('duration') else None,
            'fee': float(request.form.get('fee')) if request.form.get('fee') else None,
            'is_consultation': is_consultation,
            
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
            session_data['description'] = 'Consultation'
        else:
            session_number = non_consultation_count + 1
            session_data['session_number'] = session_number
            session_data['description'] = f"Session {session_number}"
        
        # Save session entry
        db.add_entry(session_data)
        
        return redirect(url_for('client_file', client_id=client_id))
    
    # GET - show form
    # Get existing sessions to calculate next session number
    session_entries = db.get_client_entries(client_id, 'session')
    non_consultation_count = sum(1 for s in session_entries if not s.get('is_consultation'))
    next_session_number = non_consultation_count + 1
    
    # Get today's date for default
    today = datetime.now().strftime('%Y-%m-%d')
    
    return render_template('entry_forms/session.html',
                         client=client,
                         client_type=client_type,
                         next_session_number=next_session_number,
                         today=today)
    
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
        # Check if consultation
        is_consultation = 1 if request.form.get('is_consultation') else 0
        
        # Update session data
        session_data = {
            'modality': request.form.get('modality'),
            'format': request.form.get('format'),
            'session_date': int(datetime.strptime(request.form.get('session_date'), '%Y-%m-%d').timestamp()) if request.form.get('session_date') else None,
            'session_time': request.form.get('session_time') or None,
            'duration': int(request.form.get('duration')) if request.form.get('duration') else None,
            'fee': float(request.form.get('fee')) if request.form.get('fee') else None,
            'is_consultation': is_consultation,
            'modified_at': int(time.time()),
            
            # Clinical fields (optional)
            'mood': request.form.get('mood') or None,
            'affect': request.form.get('affect') or None,
            'risk_assessment': request.form.get('risk_assessment') or None,
            
            # Content
            'content': request.form.get('content') or None,
        }
        
        # Update description based on consultation status
        if is_consultation:
            session_data['fee'] = 0
            session_data['description'] = 'Consultation'
        else:
            # Keep existing session number
            session_data['description'] = f"Session {session['session_number']}"
        
        # Save updated session
        db.update_entry(entry_id, session_data)
        
        return redirect(url_for('client_file', client_id=client_id))
    
    # GET - show form with existing data
    # Convert timestamp back to date string
    session_date = datetime.fromtimestamp(session['session_date']).strftime('%Y-%m-%d') if session.get('session_date') else None
    
    return render_template('entry_forms/session.html',
                         client=client,
                         client_type=client_type,
                         session=session,
                         session_date=session_date,
                         is_edit=True)
    
@app.route('/types')
def manage_types():
    """Manage client types."""
    all_types = db.get_all_client_types()
    return render_template('manage_types.html', all_types=all_types)

@app.route('/add_type', methods=['POST'])
def add_type():
    """Add new client type."""
    type_data = {
        'name': request.form['name'],
        'color': request.form['color'],
        'code': request.form.get('code', ''),
        'file_number_style': request.form['file_number_style'],
        'session_fee': float(request.form.get('session_fee', 0)),
        'session_duration': int(request.form.get('session_duration', 50)),
        'retention_period': int(request.form.get('retention_period', 2555))
    }
    
    db.add_client_type(type_data)
    return redirect(url_for('manage_types'))

# ===== RUN APP =====

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)