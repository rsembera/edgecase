"""
EdgeCase Flask Application
Main web interface for EdgeCase Equalizer
"""

from flask import Flask, render_template, request, redirect, url_for, jsonify, session
from pathlib import Path
import sys, sqlite3
import time
from werkzeug.utils import secure_filename

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database import Database

from web.blueprints.settings import settings_bp, init_blueprint as init_settings
from web.blueprints.types import types_bp, init_blueprint as init_types
from web.blueprints.links import links_bp, init_blueprint as init_links
from web.blueprints.clients import clients_bp, init_blueprint as init_clients
from web.blueprints.entries import entries_bp, init_blueprint as init_entries
from web.blueprints.ledger import ledger_bp

app = Flask(__name__)
app.config['SECRET_KEY'] = 'edgecase-dev-key-change-in-production'

project_root = Path(__file__).parent.parent
data_dir = project_root / "data"
data_dir.mkdir(exist_ok=True)  # Create data/ if it doesn't exist

db_path = data_dir / "edgecase.db"
db = Database(str(db_path))

init_settings(db)
init_types(db)
init_links(db)
init_clients(db)
init_entries(db)

app.register_blueprint(settings_bp)
app.register_blueprint(types_bp)
app.register_blueprint(links_bp)
app.register_blueprint(clients_bp)
app.register_blueprint(entries_bp)
app.register_blueprint(ledger_bp)

from web.blueprints.ledger import init_blueprint as init_ledger
init_ledger(db)

from datetime import datetime         

@app.template_filter('timestamp_to_date')
def timestamp_to_date(timestamp):
    """Convert Unix timestamp to readable date."""
    if not timestamp:
        return '-'
    from datetime import datetime
    return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')

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