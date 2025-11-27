# -*- coding: utf-8 -*-
"""
EdgeCase Statements Blueprint
Handles statement generation and payment tracking
"""

from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from pathlib import Path
from datetime import datetime, timedelta
import calendar
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


@statements_bp.route('/')
def outstanding_statements():
    """Display statement generation and outstanding statements."""
    
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
            sp.date_sent,
            c.file_number,
            c.first_name,
            c.middle_name,
            c.last_name,
            e.description as statement_description,
            e.created_at as statement_date
        FROM statement_portions sp
        JOIN clients c ON sp.client_id = c.id
        JOIN entries e ON sp.statement_entry_id = e.id
        WHERE sp.status IN ('ready', 'sent', 'partial')
        ORDER BY sp.status ASC, e.created_at DESC
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
            portion['date_display'] = datetime.fromtimestamp(
                portion['statement_date']
            ).strftime('%Y-%m-%d')
        else:
            portion['date_display'] = ''
        
        portions.append(portion)
    
    # Calculate default date range (last month)
    
    # Calculate default date range (last month)
    today = datetime.now()
    first_of_this_month = today.replace(day=1)
    last_month_end = first_of_this_month - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)
    
    return render_template('outstanding_statements.html', 
                          statements=portions,
                          default_start_year=last_month_start.year,
                          default_start_month=last_month_start.month,
                          default_start_day=last_month_start.day,
                          default_end_year=last_month_end.year,
                          default_end_month=last_month_end.month,
                          default_end_day=last_month_end.day)


@statements_bp.route('/find-unbilled', methods=['GET'])
def find_unbilled():
    """Find all clients with unbilled entries in date range."""
    
    start_date = request.args.get('start')
    end_date = request.args.get('end')
    
    if not start_date or not end_date:
        return jsonify({'success': False, 'error': 'Date range required'}), 400
    
    # Convert to timestamps (with day clamping for invalid dates like Nov 31)
    
    start_parts = start_date.split('-')
    start_year, start_month, start_day = int(start_parts[0]), int(start_parts[1]), int(start_parts[2])
    start_day = min(start_day, calendar.monthrange(start_year, start_month)[1])
    start_ts = int(datetime(start_year, start_month, start_day).timestamp())
    
    end_parts = end_date.split('-')
    end_year, end_month, end_day = int(end_parts[0]), int(end_parts[1]), int(end_parts[2])
    end_day = min(end_day, calendar.monthrange(end_year, end_month)[1])
    end_ts = int(datetime(end_year, end_month, end_day, 23, 59, 59).timestamp())
    
    conn = db.connect()
    cursor = conn.cursor()
    
    # Find billable entries (sessions, absences, items) that aren't linked to a statement
    # and fall within the date range
    # Exclude consultations (fee=0) and pro bono sessions
    cursor.execute("""
        SELECT 
            e.id,
            e.client_id,
            e.class,
            e.description,
            e.fee,
            e.base_price,
            e.session_date,
            e.absence_date,
            e.item_date,
            c.file_number,
            c.first_name,
            c.middle_name,
            c.last_name
        FROM entries e
        JOIN clients c ON e.client_id = c.id
        JOIN client_types ct ON c.type_id = ct.id
        WHERE e.class IN ('session', 'absence', 'item')
        AND e.statement_id IS NULL
        AND ct.name != 'Inactive'
        AND (
            (e.class = 'session' AND e.session_date BETWEEN ? AND ? AND e.fee > 0)
            OR (e.class = 'absence' AND e.absence_date BETWEEN ? AND ? AND (e.fee > 0 OR e.base_price > 0))
            OR (e.class = 'item' AND e.item_date BETWEEN ? AND ? AND (e.fee > 0 OR e.base_price > 0))
        )
        ORDER BY c.last_name, c.first_name, e.client_id
    """, (start_ts, end_ts, start_ts, end_ts, start_ts, end_ts))
    
    columns = [col[0] for col in cursor.description]
    rows = cursor.fetchall()
    conn.close()
    
    # Group by client
    clients = {}
    for row in rows:
        entry = dict(zip(columns, row))
        client_id = entry['client_id']
        
        if client_id not in clients:
            name_parts = [entry['first_name']]
            if entry['middle_name']:
                name_parts.append(entry['middle_name'])
            name_parts.append(entry['last_name'])
            
            clients[client_id] = {
                'id': client_id, 
                'file_number': entry['file_number'],
                'name': ' '.join(name_parts),
                'entries': [],
                'unbilled_total': 0
            }
        
        # Get the fee (session uses fee, absence/item may use base_price or fee)
        fee = entry['fee'] or entry['base_price'] or 0
        
        clients[client_id]['entries'].append({
            'id': entry['id'],
            'class': entry['class'],
            'description': entry['description'],
            'fee': fee
        })
        clients[client_id]['unbilled_total'] += fee
    
    return jsonify({
        'success': True,
        'clients': list(clients.values())
    })


@statements_bp.route('/generate', methods=['POST'])
def generate_statements():
    """Generate statements for selected clients."""
    
    data = request.get_json()
    client_ids = data.get('client_ids', [])
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    
    if not client_ids:
        return jsonify({'success': False, 'error': 'No clients selected'}), 400
    
    # Convert to timestamps (with day clamping for invalid dates like Nov 31)
    start_parts = start_date.split('-')
    start_year, start_month, start_day = int(start_parts[0]), int(start_parts[1]), int(start_parts[2])
    start_day = min(start_day, calendar.monthrange(start_year, start_month)[1])
    start_ts = int(datetime(start_year, start_month, start_day).timestamp())
    
    end_parts = end_date.split('-')
    end_year, end_month, end_day = int(end_parts[0]), int(end_parts[1]), int(end_parts[2])
    end_day = min(end_day, calendar.monthrange(end_year, end_month)[1])
    end_ts = int(datetime(end_year, end_month, end_day, 23, 59, 59).timestamp())
    
    now = int(time.time())
    conn = db.connect()
    cursor = conn.cursor()
    
    generated = []
    
    for client_id in client_ids:
        # Get client info
        cursor.execute("""
            SELECT c.*, ct.name as type_name
            FROM clients c
            JOIN client_types ct ON c.type_id = ct.id
            WHERE c.id = ?
        """, (client_id,))
        client_row = cursor.fetchone()
        if not client_row:
            continue
        
        client_cols = [col[0] for col in cursor.description]
        client = dict(zip(client_cols, client_row))
        
        # Get client's profile for guardian info
        cursor.execute("""
            SELECT * FROM entries 
            WHERE client_id = ? AND class = 'profile'
            ORDER BY created_at DESC LIMIT 1
        """, (client_id,))
        profile_row = cursor.fetchone()
        profile = None
        if profile_row:
            profile_cols = [col[0] for col in cursor.description]
            profile = dict(zip(profile_cols, profile_row))
        
        # Get unbilled entries for this client in date range
        cursor.execute("""
            SELECT id, class, description, fee, base_price, session_date, absence_date, item_date
            FROM entries
            WHERE client_id = ?
            AND class IN ('session', 'absence', 'item')
            AND statement_id IS NULL
            AND (
                (class = 'session' AND session_date BETWEEN ? AND ? AND fee > 0)
                OR (class = 'absence' AND absence_date BETWEEN ? AND ? AND (fee > 0 OR base_price > 0))
                OR (class = 'item' AND item_date BETWEEN ? AND ? AND (fee > 0 OR base_price > 0))
            )
        """, (client_id, start_ts, end_ts, start_ts, end_ts, start_ts, end_ts))
        
        entry_rows = cursor.fetchall()
        if not entry_rows:
            continue
        
        entry_cols = [col[0] for col in cursor.description]
        entries = [dict(zip(entry_cols, row)) for row in entry_rows]
        
        # Calculate total
        total = sum(e['fee'] or e['base_price'] or 0 for e in entries)
        
        # Generate statement number: YYYYMMDD-FileNumber
        statement_number = f"{datetime.now().strftime('%Y%m%d')}-{client['file_number']}"
        
        # Create statement description (use already-clamped values)
        start_dt = datetime(start_year, start_month, start_day)
        end_dt = datetime(end_year, end_month, end_day)
        description = f"Statement {start_dt.strftime('%b %Y')}"
        if start_dt.month != end_dt.month:
            description = f"Statement {start_dt.strftime('%b')} - {end_dt.strftime('%b %Y')}"
        
        # Create Statement entry
        cursor.execute("""
            INSERT INTO entries (
                client_id, class, created_at, modified_at,
                description, statement_total
            ) VALUES (?, 'statement', ?, ?, ?, ?)
        """, (client_id, now, now, description, total))
        
        statement_id = cursor.lastrowid
        
        # Mark entries as billed
        entry_ids = [e['id'] for e in entries]
        cursor.execute(f"""
            UPDATE entries SET statement_id = ?
            WHERE id IN ({','.join('?' * len(entry_ids))})
        """, [statement_id] + entry_ids)
        
        # Create statement portions
        # Check if minor with guardian billing
        if profile and profile.get('is_minor') and profile.get('guardian1_name'):
            g1_percent = profile.get('guardian1_pays_percent', 100) or 100
            g1_amount = total * (g1_percent / 100)
            
            cursor.execute("""
                INSERT INTO statement_portions (
                    statement_entry_id, client_id, guardian_number,
                    amount_due, amount_paid, status, created_at
                ) VALUES (?, ?, 1, ?, 0, 'ready', ?)
            """, (statement_id, client_id, g1_amount, now))
            
            # Check for guardian 2
            if profile.get('has_guardian2') and profile.get('guardian2_name'):
                g2_percent = profile.get('guardian2_pays_percent', 0) or 0
                g2_amount = total * (g2_percent / 100)
                
                if g2_amount > 0:
                    cursor.execute("""
                        INSERT INTO statement_portions (
                            statement_entry_id, client_id, guardian_number,
                            amount_due, amount_paid, status, created_at
                        ) VALUES (?, ?, 2, ?, 0, 'ready', ?)
                    """, (statement_id, client_id, g2_amount, now))
        else:
            # Single portion for client
            cursor.execute("""
                INSERT INTO statement_portions (
                    statement_entry_id, client_id, guardian_number,
                    amount_due, amount_paid, status, created_at
                ) VALUES (?, ?, NULL, ?, 0, 'ready', ?)
            """, (statement_id, client_id, total, now))
        
        generated.append({
            'client_id': client_id,
            'statement_id': statement_id,
            'total': total
        })
    
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True,
        'generated': generated,
        'count': len(generated)
    })


@statements_bp.route('/mark-sent/<int:portion_id>', methods=['POST'])
def mark_sent(portion_id):
    """Mark a statement portion as sent (email sent to client)."""
    
    now = int(time.time())
    conn = db.connect()
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE statement_portions
        SET status = 'sent', date_sent = ?
        WHERE id = ? AND status = 'ready'
    """, (now, portion_id))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@statements_bp.route('/mark-paid', methods=['POST'])
def mark_paid():
    """Mark a statement portion as paid (full or partial)."""
    
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

@statements_bp.route('/generate-final/<int:client_id>')
def generate_final_statement(client_id):
    """Generate a final statement showing all amounts owing for a client."""
    # TODO: Implement final statement generation
    # This will create a PDF showing all unpaid amounts
    pass
