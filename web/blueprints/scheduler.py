# -*- coding: utf-8 -*-
"""
EdgeCase Scheduler Blueprint
Handles appointment creation and calendar integration
"""

from flask import Blueprint, render_template, request, redirect, url_for, make_response
from datetime import datetime, timedelta
from core.database import Database
from web.utils import get_today_date_parts

scheduler_bp = Blueprint('scheduler', __name__)

# Database instance (set by init_blueprint)
db = None


def init_blueprint(database):
    """Initialize blueprint with database instance"""
    global db
    db = database


@scheduler_bp.route('/client/<int:client_id>/schedule', methods=['GET', 'POST'])
def schedule_for_client(client_id):
    """Create a calendar appointment for a specific client."""
    
    client = db.get_client(client_id)
    if not client:
        return "Client not found", 404
    
    # Get profile for default duration and contact info
    entries = db.get_client_entries(client_id)
    profile = next((e for e in entries if e['class'] == 'profile'), None)
    
    # Get client type for default duration and badge
    client_type = db.get_client_type(client['type_id'])
    default_duration = 50  # fallback
    if profile and profile.get('default_session_duration'):
        default_duration = profile['default_session_duration']
    elif client_type and client_type.get('session_duration'):
        default_duration = client_type['session_duration']
    
    if request.method == 'POST':
        # Parse date from form
        year = request.form.get('year')
        month = request.form.get('month')
        day = request.form.get('day')
        
        if year and month and day:
            date_str = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        else:
            date_str = datetime.now().strftime('%Y-%m-%d')
        
        appointment_time = request.form.get('appointment_time', '10:00 AM')
        duration = int(request.form.get('duration', default_duration) or default_duration)
        meet_link = request.form.get('meet_link', '').strip() or None
        notes = request.form.get('notes', '').strip() or ''
        
        # TODO: Generate .ics file or use AppleScript
        # For now, redirect back
        return redirect(url_for('clients.client_file', client_id=client_id))
    
    # GET - show form
    date_parts = get_today_date_parts()
    
    return render_template('schedule_form.html',
                         client=client,
                         client_type=client_type,
                         default_duration=default_duration,
                         **date_parts)