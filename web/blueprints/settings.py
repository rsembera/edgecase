# -*- coding: utf-8 -*-
"""
EdgeCase Settings Blueprint
Handles practice settings, uploads, and configuration
"""

from flask import Blueprint, render_template, request, jsonify, send_file, Response
from pathlib import Path
from werkzeug.utils import secure_filename
import time
import io
from core.encryption import encrypt_file, decrypt_file_to_bytes

from core.database import Database

# Initialize blueprint
settings_bp = Blueprint('settings', __name__)

# Database instance (set by init_blueprint)
db = None


def init_blueprint(database):
    """Initialize blueprint with database instance"""
    global db
    db = database


# ============================================================================
# SETTINGS PAGE
# ============================================================================

@settings_bp.route('/settings')
def settings_page():
    """Settings page."""
    return render_template('settings.html')


# ============================================================================
# FILE NUMBER SETTINGS
# ============================================================================

@settings_bp.route('/settings/file-number', methods=['GET', 'POST'])
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


# ============================================================================
# PRACTICE INFORMATION
# ============================================================================

@settings_bp.route('/api/practice_info', methods=['GET', 'POST'])
def practice_info():
    """Get or save practice information"""
    if request.method == 'GET':
        # Fetch all practice info from settings table
        keys = [
            'practice_name', 'therapist_name', 'credentials', 'email', 'phone',
            'address', 'website',
            'consultation_base_price', 'consultation_tax_rate', 'consultation_fee', 'consultation_duration',
            'logo_filename', 'signature_filename',
            'currency'
        ]
        
        placeholders = ','.join(['?' for _ in keys])
        query = f"SELECT key, value FROM settings WHERE key IN ({placeholders})"
        
        conn = db.connect()
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
            'address': data.get('address', ''),
            'website': data.get('website', ''),
            'currency': data.get('currency', 'CAD'),
            'consultation_base_price': data.get('consultation_base_price', '0.00'),
            'consultation_tax_rate': data.get('consultation_tax_rate', '0.00'),
            'consultation_fee': data.get('consultation_fee', '0.00'),
            'consultation_duration': data.get('consultation_duration', '20')
        }
        
        modified_at = int(time.time())
        
        conn = db.connect()
        cursor = conn.cursor()
        for key, value in settings_map.items():
            cursor.execute("""
                INSERT INTO settings (key, value, modified_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = ?, modified_at = ?
            """, (key, value, modified_at, value, modified_at))
        conn.commit()
        
        return jsonify({'success': True})


# ============================================================================
# BACKGROUND IMAGES
# ============================================================================

@settings_bp.route('/api/backgrounds')
def list_backgrounds():
    """Return list of available backgrounds separated by system and user"""
    # System backgrounds (bundled)
    system_dir = Path(__file__).parent.parent / 'static' / 'img'
    system_backgrounds = []
    
    if system_dir.exists():
        for file in system_dir.iterdir():
            if file.is_file() and file.suffix.lower() in ['.png', '.jpg', '.jpeg', '.gif', '.webp']:
                system_backgrounds.append(file.name)
    
    # User backgrounds (uploaded)
    user_dir = Path(__file__).parent.parent / 'static' / 'user_backgrounds'
    user_backgrounds = []
    
    if user_dir.exists():
        for file in user_dir.iterdir():
            if file.is_file() and file.suffix.lower() in ['.png', '.jpg', '.jpeg', '.gif', '.webp']:
                user_backgrounds.append(file.name)
    
    return jsonify({
        'system': sorted(system_backgrounds),
        'user': sorted(user_backgrounds)
    })


@settings_bp.route('/upload_background', methods=['POST'])
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
    filename = secure_filename(file.filename)
    
    # Create user_backgrounds directory if it doesn't exist
    upload_dir = Path(__file__).parent.parent / 'static' / 'user_backgrounds'
    upload_dir.mkdir(exist_ok=True)
    
    # Save to user_backgrounds directory
    upload_path = upload_dir / filename
    
    try:
        file.save(str(upload_path))
        return jsonify({'success': True, 'filename': filename})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@settings_bp.route('/delete_background', methods=['POST'])
def delete_background():
    """Delete a user-uploaded background"""
    data = request.get_json()
    filename = data.get('filename')
    
    if not filename:
        return jsonify({'success': False, 'error': 'No filename provided'})
    
    # Only allow deletion from user_backgrounds directory
    user_dir = Path(__file__).parent.parent / 'static' / 'user_backgrounds'
    file_path = user_dir / filename
    
    # Security check: ensure the path is within user_backgrounds
    try:
        file_path.resolve().relative_to(user_dir.resolve())
    except ValueError:
        return jsonify({'success': False, 'error': 'Invalid file path'})
    
    if not file_path.exists():
        return jsonify({'success': False, 'error': 'File not found'})
    
    try:
        file_path.unlink()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ============================================================================
# LOGO & SIGNATURE
# ============================================================================

@settings_bp.route('/view_logo')
def view_logo():
    """Serve the practice logo (decrypted if needed)"""
    try:
        conn = db.connect()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = 'logo_filename'")
        row = cursor.fetchone()
        
        if not row:
            return Response('No logo uploaded', status=404)
        
        filename = row[0]
        assets_dir = Path(__file__).parent.parent.parent / 'assets'
        logo_path = assets_dir / filename
        
        if not logo_path.exists():
            return Response('Logo file not found', status=404)
        
        # Determine content type
        ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else 'png'
        content_types = {'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'gif': 'image/gif'}
        content_type = content_types.get(ext, 'image/png')
        
        # Decrypt if password is set
        if db.password:
            decrypted_data = decrypt_file_to_bytes(str(logo_path), db.password)
            return Response(decrypted_data, mimetype=content_type)
        else:
            return send_file(str(logo_path), mimetype=content_type)
    except Exception as e:
        return Response(f'Error: {str(e)}', status=500)


@settings_bp.route('/view_signature')
def view_signature():
    """Serve the digital signature (decrypted if needed)"""
    try:
        conn = db.connect()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = 'signature_filename'")
        row = cursor.fetchone()
        
        if not row:
            return Response('No signature uploaded', status=404)
        
        filename = row[0]
        assets_dir = Path(__file__).parent.parent.parent / 'assets'
        sig_path = assets_dir / filename
        
        if not sig_path.exists():
            return Response('Signature file not found', status=404)
        
        # Determine content type
        ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else 'png'
        content_types = {'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'gif': 'image/gif'}
        content_type = content_types.get(ext, 'image/png')
        
        # Decrypt if password is set
        if db.password:
            decrypted_data = decrypt_file_to_bytes(str(sig_path), db.password)
            return Response(decrypted_data, mimetype=content_type)
        else:
            return send_file(str(sig_path), mimetype=content_type)
    except Exception as e:
        return Response(f'Error: {str(e)}', status=500)


@settings_bp.route('/upload_logo', methods=['POST'])
def upload_logo():
    """Handle logo upload"""
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
    filename = f'logo.{file_ext}'
    
    # Save to assets directory
    assets_dir = Path(__file__).parent.parent.parent / 'assets'
    assets_dir.mkdir(exist_ok=True)
    
    upload_path = assets_dir / filename
    
    try:
        file.save(str(upload_path))
        
        # Encrypt the file
        if db.password:
            encrypt_file(str(upload_path), db.password)
        
        # Save filename to settings
        modified_at = int(time.time())
        
        conn = db.connect()
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


@settings_bp.route('/upload_signature', methods=['POST'])
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
    filename = f'signature.{file_ext}'
    
    # Save to assets directory
    assets_dir = Path(__file__).parent.parent.parent / 'assets'
    assets_dir.mkdir(exist_ok=True)
    
    upload_path = assets_dir / filename
    
    try:
        file.save(str(upload_path))
        
        # Encrypt the file
        if db.password:
            encrypt_file(str(upload_path), db.password)
        
        # Save filename to settings
        modified_at = int(time.time())
        
        conn = db.connect()
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


@settings_bp.route('/delete_logo', methods=['POST'])
def delete_logo():
    """Delete practice logo"""
    try:
        # Get current logo filename from settings
        conn = db.connect()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = 'logo_filename'")
        row = cursor.fetchone()
        
        if row:
            filename = row[0]
            
            # Delete file from assets directory
            assets_dir = Path(__file__).parent.parent.parent / 'assets'
            logo_path = assets_dir / filename
            
            if logo_path.exists():
                logo_path.unlink()
            
            # Remove from settings
            cursor.execute("DELETE FROM settings WHERE key = 'logo_filename'")
            conn.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@settings_bp.route('/delete_signature', methods=['POST'])
def delete_signature():
    """Delete digital signature"""
    try:
        # Get current signature filename from settings
        conn = db.connect()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = 'signature_filename'")
        row = cursor.fetchone()
        
        if row:
            filename = row[0]
            
            # Delete file from assets directory
            assets_dir = Path(__file__).parent.parent.parent / 'assets'
            signature_path = assets_dir / filename
            
            if signature_path.exists():
                signature_path.unlink()
            
            # Remove from settings
            cursor.execute("DELETE FROM settings WHERE key = 'signature_filename'")
            conn.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ============================================================================
# CALENDAR SETTINGS
# ============================================================================

@settings_bp.route('/api/calendar_settings', methods=['GET', 'POST'])
def calendar_settings():
    """Get or save calendar settings"""
    if request.method == 'GET':
        settings = {
            'calendar_method': db.get_setting('calendar_method', 'ics'),
            'calendar_name': db.get_setting('calendar_name', '')
        }
        return jsonify(settings)
    
    else:  # POST
        data = request.get_json()
        
        db.set_setting('calendar_method', data.get('calendar_method', 'ics'))
        db.set_setting('calendar_name', data.get('calendar_name', ''))
        
        return jsonify({'success': True})


# ============================================================================
# STATEMENT SETTINGS
# ============================================================================

@settings_bp.route('/api/statement_settings', methods=['GET', 'POST'])
def statement_settings():
    """Get or save statement settings."""
    if request.method == 'POST':
        data = request.get_json()
        db.set_setting('currency', data.get('currency', 'CAD'))
        db.set_setting('registration_info', data.get('registration_info', ''))
        db.set_setting('payment_instructions', data.get('payment_instructions', ''))
        db.set_setting('include_attestation', 'true' if data.get('include_attestation', False) else 'false')
        db.set_setting('attestation_text', data.get('attestation_text', ''))
        db.set_setting('email_method', data.get('email_method', 'mailto'))
        db.set_setting('email_from_address', data.get('email_from_address', ''))
        db.set_setting('statement_email_body', data.get('statement_email_body', ''))
        return jsonify({'success': True})
    else:
        return jsonify({
            'currency': db.get_setting('currency', 'CAD'),
            'registration_info': db.get_setting('registration_info', ''),
            'payment_instructions': db.get_setting('payment_instructions', ''),
            'include_attestation': db.get_setting('include_attestation', 'false') == 'true',
            'attestation_text': db.get_setting('attestation_text', 'I attest that I have performed the services listed above.'),
            'email_method': db.get_setting('email_method', 'mailto'),
            'email_from_address': db.get_setting('email_from_address', ''),
            'statement_email_body': db.get_setting('statement_email_body', '')
        })


# ============================================================================
# SECURITY SETTINGS
# ============================================================================

@settings_bp.route('/api/security_settings', methods=['GET', 'POST'])
def security_settings():
    """Get or save security settings."""
    if request.method == 'POST':
        data = request.get_json()
        db.set_setting('session_timeout', str(data.get('session_timeout', '30')))
        return jsonify({'success': True})
    else:
        return jsonify({
            'session_timeout': db.get_setting('session_timeout', '30')
        })


# ============================================================================
# TIME FORMAT SETTINGS
# ============================================================================

@settings_bp.route('/api/time_format', methods=['GET', 'POST'])
def time_format():
    """Get or save time format setting (12h or 24h)."""
    if request.method == 'POST':
        data = request.get_json()
        db.set_setting('time_format', data.get('time_format', '12h'))
        return jsonify({'success': True})
    else:
        return jsonify({
            'time_format': db.get_setting('time_format', '12h')
        })
