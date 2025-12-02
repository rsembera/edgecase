"""
EdgeCase Authentication Blueprint
Handles login/logout and database encryption
"""

from flask import Blueprint, render_template, request, redirect, url_for, session, current_app, flash
from pathlib import Path
from functools import wraps

auth_bp = Blueprint('auth', __name__)

def login_required(f):
    """Decorator to require login for routes."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_app.config.get('db'):
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def is_first_run():
    """Check if this is first run (no database exists)."""
    project_root = Path(__file__).parent.parent.parent
    db_path = project_root / "data" / "edgecase.db"
    return not db_path.exists()

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login page - unlock the encrypted database."""
    from core.database import Database
    
    first_run = is_first_run()
    
    if request.method == 'POST':
        password = request.form.get('password', '')
        
        if first_run:
            # Creating new database - verify password confirmation
            confirm = request.form.get('confirm_password', '')
            if password != confirm:
                return render_template('login.html', 
                                     first_run=True, 
                                     error="Passwords don't match")
            if len(password) < 8:
                return render_template('login.html', 
                                     first_run=True, 
                                     error="Password must be at least 8 characters")
        
        # Try to open/create database with this password
        project_root = Path(__file__).parent.parent.parent
        db_path = project_root / "data" / "edgecase.db"
        
        try:
            db = Database(str(db_path), password=password)
            # Test that password works by running a query
            conn = db.connect()
            conn.execute("SELECT count(*) FROM client_types")
            
            # Success! Store db in app config
            current_app.config['db'] = db
            session['authenticated'] = True
            
            # Initialize all blueprints with the database
            from web.app import init_all_blueprints
            init_all_blueprints(db)
            
            return redirect(url_for('clients.index'))
            
        except Exception as e:
            error_msg = str(e)
            if 'file is not a database' in error_msg or 'encrypted' in error_msg.lower():
                error = "Incorrect password"
            else:
                error = f"Database error: {error_msg}"
            return render_template('login.html', first_run=first_run, error=error)
    
    return render_template('login.html', first_run=first_run)

@auth_bp.route('/logout')
def logout():
    """Logout - close database connection."""
    current_app.config['db'] = None
    session.clear()
    return redirect(url_for('auth.login'))

@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Change the master password."""
    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if new_password != confirm_password:
            return render_template('change_password.html', error="New passwords don't match")
        
        if len(new_password) < 8:
            return render_template('change_password.html', error="Password must be at least 8 characters")
        
        db = current_app.config.get('db')
        if not db:
            return redirect(url_for('auth.login'))
        
        try:
            # Step 1: Open connection and verify current password
            conn = db.connect()
            conn.execute("SELECT 1")  # Verify we can read with current password
            
            # Step 2: Rekey the database
            conn.execute(f"PRAGMA rekey = '{new_password}'")
            
            # Step 3: Close the old connection completely
            
            # Step 4: Update the Database object's password
            db.password = new_password
            
            # Step 5: Verify new password works by opening fresh connection
            test_conn = db.connect()
            test_conn.execute("SELECT 1")  # This confirms rekey worked
            
            flash("Password changed successfully", "success")
            return redirect(url_for('settings.settings_page'))
            
        except Exception as e:
            return render_template('change_password.html', error=f"Error changing password: {str(e)}")
    
    return render_template('change_password.html')