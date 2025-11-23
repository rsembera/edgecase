# -*- coding: utf-8 -*-
"""
EdgeCase Link Groups Blueprint
Handles client linking for couples/family/group therapy
"""

from flask import Blueprint, render_template, request, redirect, url_for, jsonify
from pathlib import Path
import sys
import sqlite3
import time

# Add parent directory to path for database import
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from core.database import Database

# Initialize blueprint
links_bp = Blueprint('links', __name__)

# Database instance (set by init_blueprint)
db = None

def init_blueprint(database):
    """Initialize blueprint with database instance"""
    global db
    db = database


# ============================================================================
# LINK GROUP MANAGEMENT
# ============================================================================

@links_bp.route('/links')
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


@links_bp.route('/links/add', methods=['GET', 'POST'])
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


@links_bp.route('/links/<int:group_id>/edit', methods=['GET', 'POST'])
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


@links_bp.route('/links/<int:group_id>/delete', methods=['POST'])
def delete_link_group(group_id):
    """Delete a link group"""
    success = db.delete_link_group(group_id)
    if success:
        return '', 204  # No content, success
    return 'Error deleting group', 500
