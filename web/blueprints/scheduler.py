# -*- coding: utf-8 -*-
"""
EdgeCase Scheduler Blueprint
Handles appointment creation and calendar integration
"""

from flask import Blueprint, render_template, request, redirect, url_for, make_response
from datetime import datetime, timedelta
from core.database import Database
from web.utils import get_today_date_parts
import subprocess
import uuid
import re

scheduler_bp = Blueprint('scheduler', __name__)

# Database instance (set by init_blueprint)
db = None


def init_blueprint(database):
    """Initialize blueprint with database instance"""
    global db
    db = database


def escape_ics_text(text):
    """Escape text for ICS format per RFC 5545.
    
    Must escape: backslash, semicolon, comma, newline
    Order matters: backslash first to avoid double-escaping.
    """
    if not text:
        return ''
    text = text.replace('\\', '\\\\')  # Backslash first!
    text = text.replace(';', '\\;')
    text = text.replace(',', '\\,')
    text = text.replace('\n', '\\n')
    return text


def escape_applescript_text(text):
    """Escape text for AppleScript string literals.
    
    Must escape: backslash, double quote, newline
    Order matters: backslash first to avoid double-escaping.
    """
    if not text:
        return ''
    text = text.replace('\\', '\\\\')  # Backslash first!
    text = text.replace('"', '\\"')
    text = text.replace('\n', '\\n')
    return text


def parse_time_string(time_str):
    """Parse time string like '2:30 PM' or '14:00' into hours and minutes."""
    time_str = time_str.strip().upper()
    
    # Try 12-hour format: 2:30 PM, 2:30PM, 2 PM
    match = re.match(r'(\d{1,2}):?(\d{2})?\s*(AM|PM)', time_str)
    if match:
        hours = int(match.group(1))
        minutes = int(match.group(2)) if match.group(2) else 0
        ampm = match.group(3)
        
        if ampm == 'PM' and hours != 12:
            hours += 12
        elif ampm == 'AM' and hours == 12:
            hours = 0
        
        return hours, minutes
    
    # Try 24-hour format: 14:00, 14:30
    match = re.match(r'(\d{1,2}):(\d{2})', time_str)
    if match:
        return int(match.group(1)), int(match.group(2))
    
    # Default to 10:00 AM
    return 10, 0


def get_contact_info_text(profile):
    """Build contact info string from profile for calendar notes."""
    if not profile:
        return "No contact info on file"
    
    lines = []
    
    preferred = profile.get('preferred_contact', '')
    
    # Add preferred contact first
    if preferred == 'email' and profile.get('email'):
        lines.append(f"Email (preferred): {profile['email']}")
    elif preferred == 'text' and profile.get('text_number'):
        lines.append(f"Text (preferred): {profile['text_number']}")
    elif preferred == 'call_cell' and profile.get('phone'):
        lines.append(f"Cell (preferred): {profile['phone']}")
    elif preferred == 'call_home' and profile.get('home_phone'):
        lines.append(f"Home (preferred): {profile['home_phone']}")
    elif preferred == 'call_work' and profile.get('work_phone'):
        lines.append(f"Work (preferred): {profile['work_phone']}")
    
    # Add other contact methods
    if profile.get('email') and 'Email' not in str(lines):
        lines.append(f"Email: {profile['email']}")
    if profile.get('phone') and 'Cell' not in str(lines):
        lines.append(f"Cell: {profile['phone']}")
    if profile.get('text_number') and 'Text' not in str(lines) and profile.get('text_number') != profile.get('phone'):
        lines.append(f"Text: {profile['text_number']}")
    if profile.get('home_phone') and 'Home' not in str(lines):
        lines.append(f"Home: {profile['home_phone']}")
    if profile.get('work_phone') and 'Work' not in str(lines):
        lines.append(f"Work: {profile['work_phone']}")
    
    return '\n'.join(lines) if lines else "No contact info on file"


def generate_ics(file_number, start_dt, duration, meet_link, notes, contact_info, repeat, alert1, alert2):
    """Generate an .ics file content."""
    
    end_dt = start_dt + timedelta(minutes=duration)
    
    # Format dates for iCal (UTC)
    def format_dt(dt):
        return dt.strftime('%Y%m%dT%H%M%S')
    
    uid = str(uuid.uuid4())
    now = datetime.now()
    
    lines = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        'PRODID:-//EdgeCase Equalizer//EN',
        'CALSCALE:GREGORIAN',
        'METHOD:PUBLISH',
        'BEGIN:VEVENT',
        f'UID:{uid}',
        f'DTSTAMP:{format_dt(now)}',
        f'DTSTART:{format_dt(start_dt)}',
        f'DTEND:{format_dt(end_dt)}',
        f'SUMMARY:{file_number}',
    ]
    
    # Add URL for meet link
    if meet_link:
        lines.append(f'URL:{meet_link}')
        # Also add to location for better calendar app support
        lines.append(f'LOCATION:{meet_link}')
    
    # Build description
    desc_parts = []
    if contact_info:
        desc_parts.append(contact_info)
    if notes:
        desc_parts.append(f'\n---\n{notes}')
    
    if desc_parts:
        description = escape_ics_text(''.join(desc_parts))
        lines.append(f'DESCRIPTION:{description}')
    
    # Add recurrence rule
    if repeat == 'weekly':
        lines.append('RRULE:FREQ=WEEKLY')
    elif repeat == 'biweekly':
        lines.append('RRULE:FREQ=WEEKLY;INTERVAL=2')
    elif repeat == 'monthly':
        lines.append('RRULE:FREQ=MONTHLY')
    
    # Add alerts
    for alert_minutes in [alert1, alert2]:
        if alert_minutes is not None and alert_minutes != 'none':
            alert_minutes = int(alert_minutes)
            lines.append('BEGIN:VALARM')
            lines.append('ACTION:DISPLAY')
            lines.append(f'DESCRIPTION:Reminder: {file_number}')
            if alert_minutes == 0:
                lines.append('TRIGGER:PT0M')
            else:
                lines.append(f'TRIGGER:-PT{alert_minutes}M')
            lines.append('END:VALARM')
    
    lines.extend([
        'END:VEVENT',
        'END:VCALENDAR'
    ])
    
    return '\r\n'.join(lines)


def add_to_calendar_applescript(calendar_name, file_number, start_dt, duration, meet_link, notes, contact_info, repeat, alert1, alert2):
    """Add event to Apple Calendar using AppleScript."""
    
    end_dt = start_dt + timedelta(minutes=duration)
    
    # Format dates for AppleScript
    start_str = start_dt.strftime('%B %d, %Y %I:%M:%S %p')
    end_str = end_dt.strftime('%B %d, %Y %I:%M:%S %p')
    
    # Build description
    desc_parts = []
    if contact_info:
        desc_parts.append(contact_info)
    if notes:
        desc_parts.append(f'\n---\n{notes}')
    description = escape_applescript_text(''.join(desc_parts))
    
    # Build recurrence part
    recurrence = ''
    if repeat == 'weekly':
        recurrence = 'recurrence:weekly'
    elif repeat == 'biweekly':
        # AppleScript doesn't directly support biweekly, we'll skip for now
        pass
    elif repeat == 'monthly':
        recurrence = 'recurrence:monthly'
    
    # Build the AppleScript
    script = f'''
    tell application "Calendar"
        tell calendar "{calendar_name}"
            set newEvent to make new event with properties {{summary:"{file_number}", start date:date "{start_str}", end date:date "{end_str}", description:"{description}"'''
    
    if meet_link:
        script += f', url:"{meet_link}"'
    
    script += '}'
    
    # Add alerts
    for alert_minutes in [alert1, alert2]:
        if alert_minutes is not None and alert_minutes != 'none':
            alert_minutes = int(alert_minutes)
            script += f'''
            tell newEvent
                make new display alarm with properties {{trigger interval:-{alert_minutes}}}
            end tell'''
    
    script += '''
        end tell
    end tell
    '''
    
    try:
        subprocess.run(['osascript', '-e', script], check=True, capture_output=True)
        return True, None
    except subprocess.CalledProcessError as e:
        return False, e.stderr.decode() if e.stderr else str(e)


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
        # Parse date from form - supports both new format (date) and legacy (year/month/day)
        date_field = request.form.get('date')
        if date_field:
            date_str = date_field
        else:
            # Legacy format fallback
            year = request.form.get('year')
            month = request.form.get('month')
            day = request.form.get('day')
            if year and month and day:
                date_str = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            else:
                date_str = datetime.now().strftime('%Y-%m-%d')
        
        appointment_time = request.form.get('appointment_time', '10:00 AM')
        hours, minutes = parse_time_string(appointment_time)
        
        # Build datetime
        start_dt = datetime.strptime(date_str, '%Y-%m-%d')
        start_dt = start_dt.replace(hour=hours, minute=minutes)
        
        duration = int(request.form.get('duration', default_duration) or default_duration)
        meet_link = request.form.get('meet_link', '').strip() or None
        notes = request.form.get('notes', '').strip() or ''
        repeat = request.form.get('repeat', 'none')
        alert1 = request.form.get('alert1', 'none')
        alert2 = request.form.get('alert2', 'none')
        
        # Get contact info
        contact_info = get_contact_info_text(profile)
        
        # Get calendar method from settings
        calendar_method = db.get_setting('calendar_method', 'ics')
        calendar_name = db.get_setting('calendar_name', 'Calendar')
        
        if calendar_method == 'applescript' and calendar_name:
            # Use AppleScript
            success, error = add_to_calendar_applescript(
                calendar_name, client['file_number'], start_dt, duration,
                meet_link, notes, contact_info, repeat, alert1, alert2
            )
            
            if success:
                return redirect(url_for('clients.client_file', client_id=client_id))
            else:
                # Fall back to .ics with message
                ics_content = generate_ics(
                    client['file_number'], start_dt, duration,
                    meet_link, notes, contact_info, repeat, alert1, alert2
                )
                
                import base64
                ics_b64 = base64.b64encode(ics_content.encode()).decode()
                
                # Return page that shows message and triggers download
                return f'''<!DOCTYPE html>
<html>
<head>
    <title>Calendar Fallback</title>
    <link href="https://fonts.googleapis.com/css2?family=Lexend:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        body {{ font-family: 'Lexend', sans-serif; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; background: #F2F4F5; }}
        .card {{ background: white; padding: 2rem; border-radius: 1rem; box-shadow: 0 2px 8px rgba(0,0,0,0.1); text-align: center; max-width: 400px; }}
        h2 {{ color: #1F2937; margin-bottom: 0.5rem; }}
        p {{ color: #6B7280; margin-bottom: 1.5rem; }}
        .btn {{ display: inline-block; padding: 0.75rem 1.5rem; background: #BFDCDC; color: #115D4F; border-radius: 0.5rem; text-decoration: none; font-weight: 600; }}
    </style>
</head>
<body>
    <div class="card">
        <h2>Calendar not found</h2>
        <p>Couldn't add to calendar "{calendar_name}".<br>Downloading .ics file instead.</p>
        <a href="{url_for('clients.client_file', client_id=client_id)}" class="btn">Back to Client File</a>
    </div>
    <script>
        const blob = new Blob([atob("{ics_b64}")], {{type: 'text/calendar'}});
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = "{client['file_number']}.ics";
        a.click();
    </script>
</body>
</html>'''
        
        # Generate and download .ics file
        ics_content = generate_ics(
            client['file_number'], start_dt, duration,
            meet_link, notes, contact_info, repeat, alert1, alert2
        )
        
        response = make_response(ics_content)
        response.headers['Content-Type'] = 'text/calendar; charset=utf-8'
        response.headers['Content-Disposition'] = f'attachment; filename="{client["file_number"]}.ics"'
        
        return response
    
    # GET - show form
    date_parts = get_today_date_parts()
    time_format = db.get_setting('time_format', '12h')
    
    return render_template('schedule_form.html',
                         client=client,
                         client_type=client_type,
                         default_duration=default_duration,
                         time_format=time_format,
                         **date_parts)
