# -*- coding: utf-8 -*-
"""
EdgeCase Statements Blueprint
Handles statement generation and payment tracking
"""

from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from pathlib import Path
from datetime import datetime
import sys
import time

# Add parent directory to path for database import
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from core.database import Database

# Initialize blueprint
statements_bp = Blueprint('statements', __name__)

# Database instance (set by init_blueprint)
db = None

def init_blueprint(database):
    """Initialize blueprint with database instance"""
    global db
    db = database

@statements_bp.route('/statements')
def outstanding_statements():
    """Display all outstanding (unpaid/partial) statement portions."""
    
    # Get all non-paid statement portions with client and statement info
    conn = db.connect()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            sp.id,
            sp.statement_entry_id,
            sp.client_id,
            sp.guardian_number,
            sp.amount_due,
            sp.amount_paid,
            sp.status,
            sp.created_at,
            c.file_number,
            c.first_name,
            c.middle_name,
            c.last_name,
            e.description as statement_description,
            e.created_at as statement_date
        FROM statement_portions sp
        JOIN clients c ON sp.client_id = c.id
        JOIN entries e ON sp.statement_entry_id = e.id
        WHERE sp.status IN ('pending', 'partial')
        ORDER BY e.created_at DESC
    """)
    
    columns = [col[0] for col in cursor.description]
    rows = cursor.fetchall()
    conn.close()
    
    portions = []
    for row in rows:
        portion = dict(zip(columns, row))
        
        # Build display name
        name_parts = [portion['first_name']]
        if portion['middle_name']:
            name_parts.append(portion['middle_name'])
        name_parts.append(portion['last_name'])
        portion['client_name'] = ' '.join(name_parts)
        
        # Add guardian label if applicable
        if portion['guardian_number'] == 1:
            portion['payer_label'] = 'Guardian 1'
        elif portion['guardian_number'] == 2:
            portion['payer_label'] = 'Guardian 2'
        else:
            portion['payer_label'] = None
        
        # Calculate amount owing
        portion['amount_owing'] = portion['amount_due'] - portion['amount_paid']
        
        # Format dates
        if portion['statement_date']:
            portion['statement_date_formatted'] = datetime.fromtimestamp(
                portion['statement_date']
            ).strftime('%Y-%m-%d')
        
        portions.append(portion)
    
    return render_template('outstanding_statements.html', portions=portions)


@statements_bp.route('/statements/mark-paid', methods=['POST'])
def mark_paid():
    """Mark a statement portion as paid (full or partial)."""
    from web.app import get_db
    db = get_db()
    
    data = request.get_json()
    portion_id = data.get('portion_id')
    payment_amount = data.get('payment_amount')
    payment_type = data.get('payment_type')  # 'full' or 'partial'
    notes = data.get('notes', '')
    
    if not portion_id or payment_amount is None:
        return jsonify({'success': False, 'error': 'Missing required fields'}), 400
    
    conn = db.connect()
    cursor = conn.cursor()
    
    # Get current portion data
    cursor.execute("""
        SELECT sp.*, c.file_number, c.first_name, c.last_name
        FROM statement_portions sp
        JOIN clients c ON sp.client_id = c.id
        WHERE sp.id = ?
    """, (portion_id,))
    
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({'success': False, 'error': 'Portion not found'}), 404
    
    columns = [col[0] for col in cursor.description]
    portion = dict(zip(columns, row))
    
    now = int(time.time())
    payment_amount = float(payment_amount)
    
    # Update portion
    new_amount_paid = portion['amount_paid'] + payment_amount
    amount_owing = portion['amount_due'] - new_amount_paid
    
    if amount_owing <= 0.01:  # Account for floating point
        new_status = 'paid'
    else:
        new_status = 'partial'
    
    cursor.execute("""
        UPDATE statement_portions
        SET amount_paid = ?, status = ?
        WHERE id = ?
    """, (new_amount_paid, new_status, portion_id))
    
    # Create Income entry
    # Build description
    client_name = f"{portion['first_name']} {portion['last_name']}"
    description = f"Payment from {portion['file_number']}"
    if portion['guardian_number']:
        description += f" (Guardian {portion['guardian_number']})"
    
    cursor.execute("""
        INSERT INTO entries (
            client_id, class, ledger_type, created_at, modified_at,
            description, content, ledger_date, source, total_amount,
            tax_amount, statement_id
        ) VALUES (?, 'income', 'income', ?, ?, ?, ?, ?, ?, ?, 0, ?)
    """, (
        None,  # Income entries don't have client_id
        now,
        now,
        description,
        notes if notes else None,
        now,  # ledger_date = today
        client_name,  # source = who paid
        payment_amount,
        portion['statement_entry_id']  # Link to statement
    ))
    
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True,
        'new_status': new_status,
        'amount_owing': amount_owing
    })


@statements_bp.route('/statements/generate-final/<int:client_id>')
def generate_final_statement(client_id):
    """Generate a final statement showing all amounts owing for a client."""
    # TODO: Implement final statement generation
    # This will create a PDF showing all unpaid amounts
    pass
