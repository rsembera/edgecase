"""
EdgeCase Flask Application
Main web interface for EdgeCase Equalizer
"""

from flask import Flask, render_template, request, redirect, url_for, jsonify, session
from pathlib import Path
import sys
import time
from werkzeug.utils import secure_filename

sys.path.insert(0, str(Path(__file__).parent.parent))

from web.blueprints.auth import auth_bp
from web.blueprints.settings import settings_bp
from web.blueprints.types import types_bp
from web.blueprints.links import links_bp
from web.blueprints.clients import clients_bp
from web.blueprints.entries import entries_bp
from web.blueprints.ledger import ledger_bp
from web.blueprints.scheduler import scheduler_bp
from web.blueprints.statements import statements_bp

app = Flask(__name__)
app.config['SECRET_KEY'] = 'edgecase-dev-key-change-in-production'

# Database will be set after login
app.config['db'] = None

def init_all_blueprints(db):
    """Initialize all blueprints with database instance after login."""
    from web.blueprints.clients import init_blueprint as init_clients
    from web.blueprints.entries import init_blueprint as init_entries
    from web.blueprints.ledger import init_blueprint as init_ledger
    from web.blueprints.statements import init_blueprint as init_statements
    from web.blueprints.scheduler import init_blueprint as init_scheduler
    from web.blueprints.types import init_blueprint as init_types
    from web.blueprints.settings import init_blueprint as init_settings
    from web.blueprints.links import init_blueprint as init_links
    
    init_clients(db)
    init_entries(db)
    init_ledger(db)
    init_statements(db)
    init_scheduler(db)
    init_types(db)
    init_settings(db)
    init_links(db)

# Ensure data directory exists
project_root = Path(__file__).parent.parent
data_dir = project_root / "data"
data_dir.mkdir(exist_ok=True)

# Register blueprints (but don't initialize with db yet - that happens after login)
app.register_blueprint(auth_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(types_bp)
app.register_blueprint(links_bp)
app.register_blueprint(clients_bp)
app.register_blueprint(entries_bp)
app.register_blueprint(ledger_bp)
app.register_blueprint(scheduler_bp)
app.register_blueprint(statements_bp, url_prefix='/statements')

from datetime import datetime         

@app.template_filter('timestamp_to_date')
def timestamp_to_date(timestamp):
    """Convert Unix timestamp to readable date."""
    if not timestamp:
        return '-'
    from datetime import datetime
    return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')

@app.before_request
def require_login():
    """Redirect to login if not authenticated."""
    # Allow access to login page and static files without auth
    allowed_endpoints = ['auth.login', 'auth.logout', 'static']
    if request.endpoint in allowed_endpoints:
        return
    
    # Check if database is connected (user is logged in)
    if not app.config.get('db'):
        return redirect(url_for('auth.login'))

@app.route('/scheduler')
def scheduler():
    """Scheduler page - placeholder for future calendar/appointment features"""
    return render_template('scheduler.html')

@app.route('/billing')
def billing():
    """Billing page - placeholder for future invoicing/statement features"""
    return render_template('billing.html')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)