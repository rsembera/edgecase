# -*- coding: utf-8 -*-
"""
EdgeCase Client Types Blueprint
Handles client type management (CRUD operations)
"""

from flask import Blueprint, render_template, request, redirect, url_for, jsonify
from pathlib import Path
import sys

# Add parent directory to path for database import
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from core.database import Database

# Initialize blueprint
types_bp = Blueprint('types', __name__)

# Database instance (set by init_blueprint)
db = None

def init_blueprint(database):
    """Initialize blueprint with database instance"""
    global db
    db = database


# Color palette for client types
COLOR_PALETTE = [
    # Original 3 (from Active, Assess, Low Fee)
    {'hex': '#9FCFC0', 'name': 'Seafoam', 'bubble': '#E0F2EE'},
    {'hex': '#B8D4E8', 'name': 'Sky', 'bubble': '#EBF3FA'},
    {'hex': '#D4C5E0', 'name': 'Wisteria', 'bubble': '#F3EDF7'},
    
    # Additional muted options
    {'hex': '#C8E6C9', 'name': 'Mint', 'bubble': '#EDF7ED'},
    {'hex': '#FFE0B2', 'name': 'Peach', 'bubble': '#FFF5E6'},
    {'hex': '#F8BBD0', 'name': 'Blush', 'bubble': '#FEEEF3'},
    {'hex': '#D7CCC8', 'name': 'Stone', 'bubble': '#F2EFEE'},
    {'hex': '#CFD8DC', 'name': 'Slate', 'bubble': '#EEF1F3'},
    {'hex': '#E1BEE7', 'name': 'Orchid', 'bubble': '#F7EFF9'},
]


# ============================================================================
# CLIENT TYPE MANAGEMENT
# ============================================================================

@types_bp.route('/types')
def manage_types():
    """Display client types with locked and editable sections."""
    all_types = db.get_all_client_types()
    
    # Separate locked (Inactive, Deleted) from editable types
    locked_types = [t for t in all_types if t.get('is_system_locked')]
    editable_types = [t for t in all_types if not t.get('is_system_locked')]
    
    # Sort editable types alphabetically
    editable_types.sort(key=lambda t: t['name'])
    
    return render_template('manage_types.html',
                         locked_types=locked_types,
                         editable_types=editable_types)


@types_bp.route('/add_type', methods=['GET', 'POST'])
def add_type():
    """Add a new client type"""
    if request.method == 'POST':
        # Convert retention value + unit to days
        retention_value = int(request.form.get('retention_value', 0))
        retention_unit = request.form.get('retention_unit', 'months')
        
        if retention_unit == 'days':
            retention_days = retention_value
        elif retention_unit == 'months':
            retention_days = retention_value * 30
        else:  # years
            retention_days = retention_value * 365
        
        type_data = {
            'name': request.form['name'],
            'color': request.form['color'],
            'color_name': request.form['color_name'],
            'bubble_color': request.form['bubble_color'],
            'retention_period': retention_days,
            'is_system': 0,
            'is_system_locked': 0
        }
        
        try:
            db.add_client_type(type_data)
            return redirect(url_for('types.manage_types'))
        except Exception as e:
            error_message = "A type with that name already exists." if "UNIQUE constraint" in str(e) else str(e)
            return render_template('add_edit_type.html', type=None, colors=COLOR_PALETTE, error=error_message)
    
    return render_template('add_edit_type.html', type=None, colors=COLOR_PALETTE)


@types_bp.route('/edit_type/<int:type_id>', methods=['GET', 'POST'])
def edit_type(type_id):
    """Edit an existing client type"""
    type_obj = db.get_client_type(type_id)
    
    if not type_obj:
        return redirect(url_for('types.manage_types'))
    
    # Can't edit locked system types
    if type_obj.get('is_system_locked'):
        return redirect(url_for('types.manage_types'))
    
    if request.method == 'POST':
        # Check for delete action
        if request.form.get('_method') == 'DELETE':
            # Check if this is the last editable type
            all_types = db.get_all_client_types()
            editable_types = [t for t in all_types if not t.get('is_system_locked')]
            if len(editable_types) <= 1:
                return redirect(url_for('types.manage_types'))
            
            # Check if any clients use this type
            clients = db.get_all_clients(type_id=type_id)
            if clients:
                # Can't delete if clients exist
                return redirect(url_for('types.manage_types'))
            
            db.delete_client_type(type_id)
            return redirect(url_for('types.manage_types'))
        
        # Convert retention value + unit to days
        retention_value = int(request.form.get('retention_value', 0))
        retention_unit = request.form.get('retention_unit', 'months')
        
        if retention_unit == 'days':
            retention_days = retention_value
        elif retention_unit == 'months':
            retention_days = retention_value * 30
        else:  # years
            retention_days = retention_value * 365
        
        # Regular update
        type_data = {
            'name': request.form['name'],
            'color': request.form['color'],
            'color_name': request.form['color_name'],
            'bubble_color': request.form['bubble_color'],
            'retention_period': retention_days
        }
        
        db.update_client_type(type_id, type_data)
        return redirect(url_for('types.manage_types'))
    
    # Calculate retention_value and retention_unit for display
    retention_days = type_obj.get('retention_period') or 0
    if retention_days >= 365 and retention_days % 365 == 0:
        retention_value = retention_days // 365
        retention_unit = 'years'
    elif retention_days >= 30 and retention_days % 30 == 0:
        retention_value = retention_days // 30
        retention_unit = 'months'
    else:
        retention_value = retention_days
        retention_unit = 'days'
    
    return render_template('add_edit_type.html', 
                         type=type_obj, 
                         colors=COLOR_PALETTE,
                         retention_value=retention_value,
                         retention_unit=retention_unit)


@types_bp.route('/types/<int:type_id>/delete', methods=['POST'])
def delete_type(type_id):
    """Delete client type (only if no clients assigned and not locked)."""
    type_obj = db.get_client_type(type_id)
    
    if not type_obj:
        return jsonify({'success': False, 'error': 'Type not found'}), 404
    
    # Check if locked
    if type_obj.get('is_system_locked'):
        return jsonify({'success': False, 'error': 'Cannot delete locked system types'}), 403
    
    # Check if this is the last editable type
    all_types = db.get_all_client_types()
    editable_types = [t for t in all_types if not t.get('is_system_locked')]
    
    if len(editable_types) <= 1:
        return jsonify({
            'success': False,
            'error': 'Cannot delete: At least one editable client type must exist'
        }), 400
    
    # Check if any clients are assigned to this type
    clients = db.get_all_clients(type_id=type_id)
    if clients:
        return jsonify({
            'success': False, 
            'error': f'Cannot delete: {len(clients)} client(s) are assigned to this type'
        }), 400
    
    # Delete the type
    success = db.delete_client_type(type_id)
    
    if success:
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': 'Database error'}), 500
