# -*- coding: utf-8 -*-
"""
EdgeCase Scheduler Blueprint
Handles appointments and calendar integration
"""

from flask import Blueprint, render_template, request, jsonify
from datetime import datetime, timedelta
from core.database import Database

scheduler_bp = Blueprint('scheduler', __name__)

# Database instance (set by init_blueprint)
db = None


def init_blueprint(database):
    """Initialize blueprint with database instance"""
    global db
    db = database

@scheduler_bp.route('/scheduler')
def scheduler():
    """Display appointments for a given date (defaults to today)."""
    
    # Get date from query param or default to today
    date_str = request.args.get('date')
    
    if date_str:
        try:
            view_date = datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            view_date = datetime.now()
    else:
        view_date = datetime.now()
    
    # Get start of day timestamp
    start_of_day = int(datetime(view_date.year, view_date.month, view_date.day, 0, 0, 0).timestamp())
    
    # Get appointments for this date
    appointments = db.get_appointments_for_date(start_of_day)
    
    # Get contact info for each appointment
    for appt in appointments:
        client_id = appt['client_id']
        # Get profile entry for contact details
        entries = db.get_client_entries(client_id)
        profile = next((e for e in entries if e['class'] == 'profile'), None)
        
        if profile:
            appt['email'] = profile.get('email')
            appt['phone'] = profile.get('phone')
            appt['home_phone'] = profile.get('home_phone')
            appt['work_phone'] = profile.get('work_phone')
            appt['text_number'] = profile.get('text_number')
            appt['preferred_contact'] = profile.get('preferred_contact')
        
        # Get client type for color
        client_type = db.get_client_type(appt['type_id'])
        if client_type:
            appt['type_color'] = client_type.get('color', '#9FCFC0')
            appt['bubble_color'] = client_type.get('bubble_color', '#E6F5F1')
    
    # Calculate prev/next dates
    prev_date = (view_date - timedelta(days=1)).strftime('%Y-%m-%d')
    next_date = (view_date + timedelta(days=1)).strftime('%Y-%m-%d')
    today = datetime.now().strftime('%Y-%m-%d')
    
    # Format display date
    if view_date.date() == datetime.now().date():
        display_date = "Today"
    elif view_date.date() == (datetime.now() + timedelta(days=1)).date():
        display_date = "Tomorrow"
    elif view_date.date() == (datetime.now() - timedelta(days=1)).date():
        display_date = "Yesterday"
    else:
        display_date = view_date.strftime('%A, %B %d, %Y')
    
    return render_template('scheduler.html',
                         appointments=appointments,
                         view_date=view_date.strftime('%Y-%m-%d'),
                         display_date=display_date,
                         prev_date=prev_date,
                         next_date=next_date,
                         today=today,
                         appointment_count=len(appointments))


@scheduler_bp.route('/scheduler/delete/<int:appointment_id>', methods=['POST'])
def delete_appointment(appointment_id):
    """Delete an appointment."""
    
    success = db.delete_appointment(appointment_id)
    
    if success:
        return jsonify({'success': True})
    else:
        return jsonify({'error': 'Appointment not found'}), 404
    