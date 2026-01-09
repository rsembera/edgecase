# -*- coding: utf-8 -*-
"""
EdgeCase Statements Blueprint
Handles statement generation and payment tracking
"""

from flask import Blueprint, render_template, request, jsonify, redirect, url_for, after_this_request
from pathlib import Path
from datetime import datetime, timedelta
import calendar
import time
import tempfile
from flask import send_file
from pdf.generator import generate_statement_pdf

from core.database import Database
from core.config import ASSETS_DIR, ATTACHMENTS_DIR

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
        
        # Calculate total and total tax
        total = 0
        total_tax = 0
        for e in entries:
            # Get fee (entries should have fee set, but handle old data)
            fee = e['fee']
            if not fee:
                if e['class'] == 'item':
                    fee = e.get('base_price') or 0
                elif e['class'] == 'absence':
                    fee = e.get('base_fee') or 0
                else:
                    fee = 0
            total += fee
            
            # Calculate tax for this entry
            if e['class'] == 'session':
                # Session: tax = fee - base_fee
                entry_tax = fee - (e['base_fee'] or 0)
            elif e['class'] == 'absence':
                # Absence: tax = fee - base_fee (new) or base_price (old)
                base = e.get('base_fee') or e.get('base_price') or 0
                entry_tax = fee - base
            elif e['class'] == 'item':
                # Item: tax = fee - base_price
                entry_tax = fee - (e['base_price'] or 0)
            else:
                entry_tax = 0
            total_tax += max(0, entry_tax)  # Don't allow negative tax
        
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
                description, statement_total, statement_tax_total
            ) VALUES (?, 'statement', ?, ?, ?, ?, ?)
        """, (client_id, now, now, description, total, total_tax))
        
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
            # For items with explicit guardian amounts, use those
            # For other entries, calculate using profile percentages
            g1_explicit = 0
            g2_explicit = 0
            percentage_total = 0
            
            for e in entries:
                fee = e['fee'] or e['base_price'] or 0
                if e['class'] == 'item' and e.get('guardian1_amount') is not None:
                    # Item with explicit guardian amounts
                    g1_explicit += e['guardian1_amount'] or 0
                    g2_explicit += e['guardian2_amount'] or 0
                else:
                    # Session, absence, or item without explicit amounts - use percentage
                    percentage_total += fee
            
            # Calculate percentage-based amounts
            g1_percent = profile.get('guardian1_pays_percent', 100) or 100
            g1_from_percent = round(percentage_total * g1_percent / 100, 2)
            
            # Sanity check: g1 can't exceed percentage_total
            g1_from_percent = min(g1_from_percent, percentage_total)
            
            # Total guardian amounts
            g1_amount = round(g1_explicit + g1_from_percent, 2)
            
            # Check for guardian 2
            if profile.get('has_guardian2') and profile.get('guardian2_name'):
                # G2 gets remainder of percentage_total plus explicit g2
                g2_from_percent = round(percentage_total - g1_from_percent, 2)
                g2_amount = round(g2_explicit + g2_from_percent, 2)
                
                # Sanity check: g2 can't go negative
                g2_amount = max(0, g2_amount)
                
                cursor.execute("""
                    INSERT INTO statement_portions (
                        statement_entry_id, client_id, guardian_number,
                        amount_due, amount_paid, status, created_at
                    ) VALUES (?, ?, 1, ?, 0, 'ready', ?)
                """, (statement_id, client_id, g1_amount, now))
                
                if g2_amount > 0:
                    cursor.execute("""
                        INSERT INTO statement_portions (
                            statement_entry_id, client_id, guardian_number,
                            amount_due, amount_paid, status, created_at
                        ) VALUES (?, ?, 2, ?, 0, 'ready', ?)
                    """, (statement_id, client_id, g2_amount, now))
            else:
                # Single guardian pays full amount
                cursor.execute("""
                    INSERT INTO statement_portions (
                        statement_entry_id, client_id, guardian_number,
                        amount_due, amount_paid, status, created_at
                    ) VALUES (?, ?, 1, ?, 0, 'ready', ?)
                """, (statement_id, client_id, total, now))
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
    
    try:
        conn.commit()
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': f'Database error: {str(e)}'}), 500
    
    # Count total portions created
    cursor.execute("""
        SELECT COUNT(*) FROM statement_portions 
        WHERE statement_entry_id IN ({})
    """.format(','.join('?' * len(generated))), [g['statement_id'] for g in generated])
    portion_count = cursor.fetchone()[0] if generated else 0
    
    return jsonify({
        'success': True,
        'generated': generated,
        'count': len(generated),
        'portion_count': portion_count
    })


@statements_bp.route('/mark-sent/<int:portion_id>', methods=['POST'])
def mark_sent(portion_id):
    """Mark a statement portion as sent - generates PDF, creates Communication entry, triggers email."""
    
    import subprocess
    import shutil
    from urllib.parse import quote
    
    # Check if we should skip email (generate-only mode)
    skip_email = request.args.get('skip_email') == '1'
    
    now = int(time.time())
    conn = db.connect()
    cursor = conn.cursor()
    
    # Get portion with client info and statement description
    cursor.execute("""
        SELECT sp.*, c.id as client_id, c.file_number, c.first_name, c.middle_name, c.last_name,
               e.created_at as statement_date, e.description as statement_description
        FROM statement_portions sp
        JOIN clients c ON sp.client_id = c.id
        JOIN entries e ON sp.statement_entry_id = e.id
        WHERE sp.id = ?
    """, (portion_id,))
    
    row = cursor.fetchone()
    if not row:
        return jsonify({'success': False, 'error': 'Statement portion not found'}), 404
    
    columns = [col[0] for col in cursor.description]
    portion = dict(zip(columns, row))
    
    # Get profile for guardian info if needed
    cursor.execute("""
        SELECT * FROM entries 
        WHERE client_id = ? AND class = 'profile'
        ORDER BY created_at DESC LIMIT 1
    """, (portion['client_id'],))
    profile_row = cursor.fetchone()
    profile = None
    if profile_row:
        profile_cols = [col[0] for col in cursor.description]
        profile = dict(zip(profile_cols, profile_row))
    
    # Determine recipient name and email
    if portion['guardian_number'] == 1 and profile:
        recipient_first_name = profile.get('guardian1_name', '').split()[0] if profile.get('guardian1_name') else portion['first_name']
        recipient_email = profile.get('guardian1_email', '')
    elif portion['guardian_number'] == 2 and profile:
        recipient_first_name = profile.get('guardian2_name', '').split()[0] if profile.get('guardian2_name') else portion['first_name']
        recipient_email = profile.get('guardian2_email', '')
    else:
        recipient_first_name = portion['first_name']
        recipient_email = profile.get('email', '') if profile else ''
    
    # Get statement billing period from statement description (e.g., "Statement Dec 2025" or "Statement Nov - Dec 2025")
    statement_description = portion.get('statement_description', '')
    billing_period = statement_description.replace('Statement ', '') if statement_description.startswith('Statement ') else statement_description
    
    # Get email settings
    email_method = db.get_setting('email_method', 'mailto')
    email_from = db.get_setting('email_from_address', '')
    email_body_template = db.get_setting('statement_email_body', '')
    
    # Build email text
    email_subject = f"Statement for {billing_period}"
    email_body = f"Dear {recipient_first_name},\n\nPlease find attached your statement for {billing_period}.\n\n{email_body_template}"
    
    # Generate PDF to temp location
    temp_dir = tempfile.gettempdir()
    date_str = datetime.now().strftime('%Y%m%d')
    pdf_filename = f"Statement_{portion['file_number']}_{date_str}.pdf"
    temp_pdf_path = Path(temp_dir) / pdf_filename
    
    try:
        generate_statement_pdf(db, portion_id, str(temp_pdf_path), str(ASSETS_DIR))
    except Exception as e:
        return jsonify({'success': False, 'error': f'PDF generation failed: {str(e)}'}), 500
    
    # Create Communication entry - description varies based on skip_email
    if skip_email:
        comm_description = f"Statement Generated - {billing_period}"
        comm_content = f"Statement generated for {billing_period}."
    else:
        comm_description = f"Statement Sent - {billing_period}"
        comm_content = email_body
    
    # Get time format preference
    time_format = db.get_setting('time_format', '12h')
    if time_format == '24h':
        comm_time = datetime.now().strftime('%H:%M')
    else:
        comm_time = datetime.now().strftime('%I:%M %p').lstrip('0')
    
    cursor.execute("""
        INSERT INTO entries (
            client_id, class, created_at, modified_at,
            description, content, comm_recipient, comm_type, comm_date, comm_time,
            locked
        ) VALUES (?, 'communication', ?, ?, ?, ?, 'to_client', 'email', ?, ?, 1)
    """, (
        portion['client_id'],
        now,
        now,
        comm_description,
        comm_content,
        now,
        comm_time
    ))
    
    comm_entry_id = cursor.lastrowid
    
    # Copy PDF to attachments folder and create attachment record
    attachment_dir = ATTACHMENTS_DIR / str(portion['client_id']) / str(comm_entry_id)
    attachment_dir.mkdir(parents=True, exist_ok=True)
    
    final_pdf_path = attachment_dir / pdf_filename
    shutil.copy2(temp_pdf_path, final_pdf_path)
    
    # Encrypt the attachment if database is encrypted
    if db.password:
        from core.encryption import encrypt_file
        encrypt_file(str(final_pdf_path), db.password)
    
    cursor.execute("""
        INSERT INTO attachments (entry_id, filename, description, filepath, filesize, uploaded_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        comm_entry_id,
        pdf_filename,
        f"Statement for {billing_period}",
        str(final_pdf_path),
        final_pdf_path.stat().st_size,
        now
    ))
    
    # Update statement portion status
    cursor.execute("""
        UPDATE statement_portions
        SET status = 'sent', date_sent = ?
        WHERE id = ? AND status = 'ready'
    """, (now, portion_id))
    
    conn.commit()
    
    # Return different response based on skip_email
    if skip_email:
        return jsonify({
            'success': True,
            'skip_email': True
        })
    else:
        return jsonify({
            'success': True,
            'email_method': email_method,
            'recipient_email': recipient_email,
            'subject': email_subject,
            'body': email_body,
            'pdf_path': str(temp_pdf_path),
            'email_from': email_from
        })

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
    
    # Get current portion data with statement info for tax calculation
    cursor.execute("""
        SELECT sp.*, c.file_number, c.first_name, c.last_name,
               e.statement_total, e.statement_tax_total
        FROM statement_portions sp
        JOIN clients c ON sp.client_id = c.id
        JOIN entries e ON sp.statement_entry_id = e.id
        WHERE sp.id = ?
    """, (portion_id,))
    
    row = cursor.fetchone()
    if not row:
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
    
    # Create ledger entry - Income for positive, Expense for negative (refunds)
    if payment_amount >= 0:
        # Normal payment - create Income entry
        # Calculate proportional tax for this payment
        statement_total = portion.get('statement_total') or 0
        statement_tax = portion.get('statement_tax_total') or 0
        
        if statement_total > 0 and statement_tax > 0:
            # Pro-rata tax: payment × (total_tax / total_amount)
            tax_collected = round(payment_amount * (statement_tax / statement_total), 2)
        else:
            tax_collected = 0
        
        description = "Client Payment"
        if portion['guardian_number']:
            description += f" (Guardian {portion['guardian_number']})"
        source = portion['file_number']
        
        cursor.execute("""
            INSERT INTO entries (
                client_id, class, ledger_type, created_at, modified_at,
                description, content, ledger_date, source, total_amount,
                tax_amount, statement_id
            ) VALUES (?, 'income', 'income', ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            None,
            now,
            now,
            description,
            notes if notes else None,
            now,
            source,
            payment_amount,
            tax_collected,
            portion['statement_entry_id']
        ))
    else:
        # Refund - create Expense entry with positive amount
        refund_amount = abs(payment_amount)
        
        # Get or create "Client Refund" category
        cursor.execute("SELECT id FROM expense_categories WHERE name = 'Client Refund'")
        cat_row = cursor.fetchone()
        if cat_row:
            category_id = cat_row[0]
        else:
            cursor.execute("""
                INSERT INTO expense_categories (name, created_at)
                VALUES ('Client Refund', ?)
            """, (now,))
            category_id = cursor.lastrowid
        
        # Get or create payee with file number
        cursor.execute("SELECT id FROM payees WHERE name = ?", (portion['file_number'],))
        payee_row = cursor.fetchone()
        if payee_row:
            payee_id = payee_row[0]
        else:
            cursor.execute("""
                INSERT INTO payees (name, created_at)
                VALUES (?, ?)
            """, (portion['file_number'], now))
            payee_id = cursor.lastrowid
        
        description = "Client Refund"
        if portion['guardian_number']:
            description += f" (Guardian {portion['guardian_number']})"
        
        cursor.execute("""
            INSERT INTO entries (
                client_id, class, ledger_type, created_at, modified_at,
                description, content, ledger_date, category_id, payee_id,
                total_amount, tax_amount, statement_id
            ) VALUES (?, 'expense', 'expense', ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
        """, (
            None,
            now,
            now,
            description,
            notes if notes else None,
            now,
            category_id,
            payee_id,
            refund_amount,
            portion['statement_entry_id']
        ))
    
    conn.commit()
    
    return jsonify({
        'success': True,
        'new_status': new_status,
        'amount_owing': amount_owing
    })

@statements_bp.route('/pdf/<int:portion_id>')
def download_statement_pdf(portion_id):
    """Generate and download a PDF statement for a portion."""
    
    temp_dir = tempfile.gettempdir()
    
    conn = db.connect()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT sp.*, c.file_number
        FROM statement_portions sp
        JOIN clients c ON sp.client_id = c.id
        WHERE sp.id = ?
    """, (portion_id,))
    row = cursor.fetchone()
    
    if not row:
        return jsonify({'success': False, 'error': 'Statement not found'}), 404
    
    columns = [col[0] for col in cursor.description]
    portion = dict(zip(columns, row))
    
    date_str = datetime.now().strftime('%Y%m%d')
    filename = f"Statement_{portion['file_number']}_{date_str}.pdf"
    output_path = Path(temp_dir) / filename
    
    try:
        generate_statement_pdf(db, portion_id, str(output_path), str(ASSETS_DIR))
        
        @after_this_request
        def cleanup(response):
            try:
                if output_path.exists():
                    output_path.unlink()
            except OSError:
                pass
            return response
        
        return send_file(
            output_path,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@statements_bp.route('/view-pdf/<int:portion_id>')
def view_statement_pdf(portion_id):
    """Generate and view a PDF statement in browser."""
    
    temp_dir = tempfile.gettempdir()
    
    conn = db.connect()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT sp.*, c.file_number
        FROM statement_portions sp
        JOIN clients c ON sp.client_id = c.id
        WHERE sp.id = ?
    """, (portion_id,))
    row = cursor.fetchone()
    
    if not row:
        return jsonify({'success': False, 'error': 'Statement not found'}), 404
    
    columns = [col[0] for col in cursor.description]
    portion = dict(zip(columns, row))
    
    date_str = datetime.now().strftime('%Y%m%d')
    filename = f"Statement_{portion['file_number']}_{date_str}.pdf"
    output_path = Path(temp_dir) / filename
    
    try:
        generate_statement_pdf(db, portion_id, str(output_path), str(ASSETS_DIR))
        
        @after_this_request
        def cleanup(response):
            try:
                if output_path.exists():
                    output_path.unlink()
            except OSError:
                pass
            return response
        
        return send_file(
            output_path,
            mimetype='application/pdf',
            as_attachment=False,
            download_name=filename
        )
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    
@statements_bp.route('/send-applescript-email', methods=['POST'])
def send_applescript_email():
    """Send email via AppleScript (Mac Mail.app)."""
    
    import subprocess
    
    data = request.get_json()
    recipient = data.get('recipient_email', '')
    subject = data.get('subject', '')
    body = data.get('body', '')
    pdf_path = data.get('pdf_path', '')
    email_from = data.get('email_from', '')
    
    # Escape double quotes and backslashes for AppleScript
    def escape_for_applescript(s):
        return s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
    
    subject_escaped = escape_for_applescript(subject)
    body_escaped = escape_for_applescript(body)
    
    # Build AppleScript
    applescript = f'''
    tell application "Mail"
        set newMessage to make new outgoing message with properties {{subject:"{subject_escaped}", content:"{body_escaped}", visible:true}}
        
        tell newMessage
            make new to recipient at end of to recipients with properties {{address:"{recipient}"}}
            
            if "{pdf_path}" is not "" then
                make new attachment with properties {{file name:POSIX file "{pdf_path}"}} at after last paragraph
            end if
        end tell
        
        activate
    end tell
    '''
    
    # Add sender account if specified
    if email_from:
        applescript = f'''
        tell application "Mail"
            set senderAccount to null
            repeat with acct in accounts
                if (email addresses of acct) contains "{email_from}" then
                    set senderAccount to acct
                    exit repeat
                end if
            end repeat
            
            set newMessage to make new outgoing message with properties {{subject:"{subject_escaped}", content:"{body_escaped}", visible:true}}
            
            if senderAccount is not null then
                set sender of newMessage to "{email_from}"
            end if
            
            tell newMessage
                make new to recipient at end of to recipients with properties {{address:"{recipient}"}}
                
                if "{pdf_path}" is not "" then
                    make new attachment with properties {{file name:POSIX file "{pdf_path}"}} at after last paragraph
                end if
            end tell
            
            activate
        end tell
        '''
    
    try:
        result = subprocess.run(
            ['osascript', '-e', applescript],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        # Clean up temp PDF after AppleScript has attached it
        if pdf_path:
            try:
                pdf_path_obj = Path(pdf_path)
                if pdf_path_obj.exists() and str(tempfile.gettempdir()) in str(pdf_path_obj):
                    pdf_path_obj.unlink()
            except OSError:
                pass  # Non-critical, OS will eventually clean temp
        
        if result.returncode != 0:
            return jsonify({'success': False, 'error': result.stderr})
        
        return jsonify({'success': True})
        
    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'error': 'AppleScript timed out'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ============================================
# ADD THIS ROUTE TO THE END OF statements.py
# (before the last line if there is one)
# ============================================

@statements_bp.route('/write-off', methods=['POST'])
def write_off_statement():
    """Write off a statement portion."""
    
    data = request.get_json()
    portion_id = data.get('portion_id')
    reason = data.get('reason')  # 'uncollectible', 'waived', 'billing_error', 'other'
    note = data.get('note', '')
    amount = data.get('amount', 0)
    
    if not portion_id or not reason:
        return jsonify({'success': False, 'error': 'Missing required fields'}), 400
    
    conn = db.connect()
    cursor = conn.cursor()
    
    now = int(time.time())
    
    # Get portion and client info
    cursor.execute("""
        SELECT sp.*, c.file_number, c.first_name, c.middle_name, c.last_name, c.id as client_id,
               e.description as statement_description
        FROM statement_portions sp
        JOIN clients c ON sp.client_id = c.id
        JOIN entries e ON sp.statement_entry_id = e.id
        WHERE sp.id = ?
    """, (portion_id,))
    
    row = cursor.fetchone()
    if not row:
        return jsonify({'success': False, 'error': 'Statement portion not found'}), 404
    
    columns = [col[0] for col in cursor.description]
    portion = dict(zip(columns, row))
    
    # Build client name
    name_parts = [portion['first_name']]
    if portion['middle_name']:
        name_parts.append(portion['middle_name'])
    name_parts.append(portion['last_name'])
    client_name = ' '.join(name_parts)
    
    # Update statement_portions with write-off info
    cursor.execute("""
        UPDATE statement_portions
        SET status = 'written_off',
            write_off_reason = ?,
            write_off_date = ?,
            write_off_note = ?
        WHERE id = ?
    """, (reason, now, note if note else None, portion_id))
    
    # If billing error, unlink entries so they can be edited and re-billed
    if reason == 'billing_error':
        cursor.execute("""
            UPDATE entries 
            SET statement_id = NULL 
            WHERE statement_id = ?
        """, (portion['statement_entry_id'],))
    
    # Build description for Communication entry
    reason_labels = {
        'uncollectible': 'Uncollectible',
        'waived': 'Waived',
        'billing_error': 'Billing Error',
        'other': 'Other'
    }
    reason_label = reason_labels.get(reason, reason)
    
    comm_description = f"Statement Written Off - {reason_label}"
    
    # Build content for Communication entry
    amount_owing = portion['amount_due'] - portion['amount_paid']
    content_parts = [
        f"**Statement:** {portion['statement_description']}",
        f"**Amount Written Off:** ${amount_owing:.2f}",
        f"**Reason:** {reason_label}"
    ]
    if note:
        content_parts.append(f"**Note:** {note}")
    
    comm_content = '\n\n'.join(content_parts)
    
    # Format current time for comm_time
    from datetime import datetime
    now_dt = datetime.fromtimestamp(now)
    comm_time = now_dt.strftime('%I:%M %p').lstrip('0')
    
    # Create Communication entry in client file
    cursor.execute("""
        INSERT INTO entries (
            client_id, class, created_at, modified_at,
            description, content, comm_recipient, comm_type,
            comm_date, comm_time, locked, locked_at
        ) VALUES (?, 'communication', ?, ?, ?, ?, 'internal_note', 'administrative', ?, ?, 1, ?)
    """, (
        portion['client_id'],
        now,
        now,
        comm_description,
        comm_content,
        now,
        comm_time,
        now
    ))
    
    # If uncollectible, create Bad Debt expense entry
    if reason == 'uncollectible':
        # Check if "Bad Debt" category exists, create if not
        cursor.execute("SELECT id FROM expense_categories WHERE name = 'Bad Debt'")
        cat_row = cursor.fetchone()
        
        if cat_row:
            category_id = cat_row[0]
        else:
            cursor.execute("""
                INSERT INTO expense_categories (name, created_at)
                VALUES ('Bad Debt', ?)
            """, (now,))
            category_id = cursor.lastrowid
        
        # Check if payee with file number exists, create if not
        cursor.execute("SELECT id FROM payees WHERE name = ?", (portion['file_number'],))
        payee_row = cursor.fetchone()
        
        if payee_row:
            payee_id = payee_row[0]
        else:
            cursor.execute("""
                INSERT INTO payees (name, created_at)
                VALUES (?, ?)
            """, (portion['file_number'], now))
            payee_id = cursor.lastrowid
        
        # Create expense entry
        expense_description = "Uncollectible"
        expense_content = f"Written off statement for {client_name}"
        if portion['guardian_number']:
            expense_content += f" (Guardian {portion['guardian_number']})"
        
        cursor.execute("""
            INSERT INTO entries (
                client_id, class, ledger_type, created_at, modified_at,
                description, content, ledger_date, category_id, payee_id,
                total_amount, tax_amount, statement_id
            ) VALUES (?, 'expense', 'expense', ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
        """, (
            None,
            now,
            now,
            expense_description,
            expense_content,
            now,
            category_id,
            payee_id,
            amount_owing,
            portion['statement_entry_id']
        ))
    
    conn.commit()
    
    return jsonify({'success': True})