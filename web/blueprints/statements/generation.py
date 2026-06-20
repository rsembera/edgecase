"""Statement generation: find unbilled entries and create statements.

Extracted from the statements.py blueprint split.
"""
from flask import request, jsonify
from datetime import datetime
import calendar
import time
from core.database import Database
from core.money import money_float
from core.billing import compute_statement_totals, split_guardian_amounts
from web.blueprints.statements.common import statements_bp, get_db


@statements_bp.route('/find-unbilled', methods=['GET'])
def find_unbilled():
    """Find all clients with unbilled entries in date range."""
    db = get_db()
    
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
            e.base_fee,
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
        AND e.locked = 1
        AND ct.name != 'Inactive'
        AND (
            (e.class = 'session' AND e.session_date BETWEEN ? AND ? AND e.fee > 0)
            OR (e.class = 'absence' AND e.absence_date BETWEEN ? AND ? AND (e.fee > 0 OR e.base_fee > 0))
            OR (e.class = 'item' AND e.item_date BETWEEN ? AND ? AND (e.fee != 0 OR e.base_price != 0))
        )
        ORDER BY c.last_name, c.first_name, e.client_id
    """, (start_ts, end_ts, start_ts, end_ts, start_ts, end_ts))
    
    columns = [col[0] for col in cursor.description]
    rows = cursor.fetchall()
    
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
        
        # Get the fee (entries should have fee set, but handle old data)
        # Items use base_price, absences use base_fee, sessions use base_fee
        fee = entry['fee']
        if not fee:
            if entry['class'] == 'item':
                fee = entry.get('base_price') or 0
            elif entry['class'] == 'absence':
                fee = entry.get('base_fee') or 0
            else:
                fee = 0
        
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
    db = get_db()
    
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Invalid request data'}), 400
    
    client_ids = data.get('client_ids', [])
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    
    if not client_ids:
        return jsonify({'success': False, 'error': 'No clients selected'}), 400
    
    # Validate and convert date strings
    try:
        start_parts = start_date.split('-')
        start_year, start_month, start_day = int(start_parts[0]), int(start_parts[1]), int(start_parts[2])
        start_day = min(start_day, calendar.monthrange(start_year, start_month)[1])
        start_ts = int(datetime(start_year, start_month, start_day).timestamp())
        
        end_parts = end_date.split('-')
        end_year, end_month, end_day = int(end_parts[0]), int(end_parts[1]), int(end_parts[2])
        end_day = min(end_day, calendar.monthrange(end_year, end_month)[1])
        end_ts = int(datetime(end_year, end_month, end_day, 23, 59, 59).timestamp())
    except (ValueError, IndexError, TypeError, AttributeError) as e:
        return jsonify({'success': False, 'error': f'Invalid date format: {e}'}), 400
    
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
            SELECT id, class, description, fee, base_price, base_fee, tax_rate,
                   session_date, absence_date, item_date,
                   guardian1_amount, guardian2_amount
            FROM entries
            WHERE client_id = ?
            AND class IN ('session', 'absence', 'item')
            AND statement_id IS NULL
            AND locked = 1
            AND (
                (class = 'session' AND session_date BETWEEN ? AND ? AND fee > 0)
                OR (class = 'absence' AND absence_date BETWEEN ? AND ? AND (fee > 0 OR base_fee > 0))
                OR (class = 'item' AND item_date BETWEEN ? AND ? AND (fee != 0 OR base_price != 0))
            )
        """, (client_id, start_ts, end_ts, start_ts, end_ts, start_ts, end_ts))
        
        entry_rows = cursor.fetchall()
        if not entry_rows:
            continue
        
        entry_cols = [col[0] for col in cursor.description]
        entries = [dict(zip(entry_cols, row)) for row in entry_rows]
        
        # Calculate total and total tax (Decimal arithmetic — see core/billing.py)
        total, total_tax = compute_statement_totals(entries)
        
        # Generate statement number: YYYYMMDD-FileNumber
        statement_number = f"{datetime.now().strftime('%Y%m%d')}-{client['file_number']}"
        
        # Create statement description (use already-clamped values)
        start_dt = datetime(start_year, start_month, start_day)
        end_dt = datetime(end_year, end_month, end_day)
        description = f"Statement {start_dt.strftime('%B %Y')}"
        if start_dt.month != end_dt.month:
            description = f"Statement {start_dt.strftime('%B')} - {end_dt.strftime('%B %Y')}"
        
        # Create Statement entry
        cursor.execute("""
            INSERT INTO entries (
                client_id, class, created_at, modified_at,
                description, statement_total, statement_tax_total
            ) VALUES (?, 'statement', ?, ?, ?, ?, ?)
        """, (client_id, now, now, description,
              money_float(total), money_float(total_tax)))
        
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
            # Guardian split logic lives in core/billing.py:
            # explicit per-item amounts honored; percentage pool split with
            # the exact remainder to guardian 2; single guardian (H3) pays
            # the full statement amount.
            for guardian_number, amount in split_guardian_amounts(entries, profile, total):
                cursor.execute("""
                    INSERT INTO statement_portions (
                        statement_entry_id, client_id, guardian_number,
                        amount_due, amount_paid, status, created_at
                    ) VALUES (?, ?, ?, ?, 0, 'ready', ?)
                """, (statement_id, client_id, guardian_number,
                      money_float(amount), now))
        else:
            # Single portion for client
            cursor.execute("""
                INSERT INTO statement_portions (
                    statement_entry_id, client_id, guardian_number,
                    amount_due, amount_paid, status, created_at
                ) VALUES (?, ?, NULL, ?, 0, 'ready', ?)
            """, (statement_id, client_id, money_float(total), now))

        generated.append({
            'client_id': client_id,
            'statement_id': statement_id,
            'total': money_float(total)
        })
    
    try:
        conn.commit()
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': f'Database error: {str(e)}'}), 500
    
    # Count total portions created (M9: guard the empty case — an
    # `IN ()` query raises OperationalError before reaching the ternary)
    if generated:
        cursor.execute("""
            SELECT COUNT(*) FROM statement_portions
            WHERE statement_entry_id IN ({})
        """.format(','.join('?' * len(generated))), [g['statement_id'] for g in generated])
        portion_count = cursor.fetchone()[0]
    else:
        portion_count = 0
    
    return jsonify({
        'success': True,
        'generated': generated,
        'count': len(generated),
        'portion_count': portion_count
    })
