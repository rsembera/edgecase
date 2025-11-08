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
db_path = Path.home() / "edgecase_data" / "edgecase.db"
db = Database(str(db_path))

# ===== ROUTES =====

@app.route('/')
def index():
    """Main view - client list."""
    # Get filter parameters
    type_filter = request.args.getlist('type')  # Can select multiple types
    sort_by = request.args.get('sort', 'last_name')  # Default sort by last name
    sort_order = request.args.get('order', 'asc')  # Default ascending
    search = request.args.get('search', '')
    
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
    
    # Add type information to each client
    for client in clients:
        client['type'] = db.get_client_type(client['type_id'])
    
    # Sort clients
    reverse = (sort_order == 'desc')
    if sort_by == 'file_number':
        clients.sort(key=lambda c: c['file_number'], reverse=reverse)
    elif sort_by == 'first_name':
        clients.sort(key=lambda c: c['first_name'].lower(), reverse=reverse)
    elif sort_by == 'last_name':
        clients.sort(key=lambda c: c['last_name'].lower(), reverse=reverse)
    elif sort_by == 'created':
        clients.sort(key=lambda c: c['created_at'], reverse=reverse)
    
    return render_template('main_view.html',
                         clients=clients,
                         all_types=all_types,
                         selected_types=type_filter,
                         sort_by=sort_by,
                         sort_order=sort_order,
                         search=search)

@app.route('/client/<int:client_id>')
def client_file(client_id):
    """Client file view - entry timeline."""
    client = db.get_client(client_id)
    if not client:
        return "Client not found", 404
    
    # Get client type
    client['type'] = db.get_client_type(client['type_id'])
    
    # Get all entries for this client
    entries = db.get_client_entries(client_id)
    
    return render_template('client_file.html',
                         client=client,
                         entries=entries)

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