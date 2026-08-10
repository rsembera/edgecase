"""Payment + write-off routes (and the ledger category/payee helpers they use).

Extracted from the statements.py blueprint split.
"""
from flask import request, jsonify
from datetime import datetime
import calendar
import time
from core.money import dec, quantize_cents, money_float, to_cents
from core.billing import apply_payment, prorata_tax, propose_allocation
from web.blueprints.statements.common import statements_bp, get_db


def _get_or_create_category(cursor, name, now):
    """Get the id of an expense category by name, creating it if missing.

    Shared by the refund and write-off paths (CODE_REVIEW.md M13).
    """
    cursor.execute("SELECT id FROM expense_categories WHERE name = ?", (name,))
    cat_row = cursor.fetchone()
    if cat_row:
        return cat_row[0]
    cursor.execute("""
        INSERT INTO expense_categories (name, created_at)
        VALUES (?, ?)
    """, (name, now))
    return cursor.lastrowid


def _get_or_create_payee(cursor, name, now):
    """Get the id of a payee by name, creating it if missing.

    Shared by the refund and write-off paths (CODE_REVIEW.md M13).
    """
    cursor.execute("SELECT id FROM payees WHERE name = ?", (name,))
    payee_row = cursor.fetchone()
    if payee_row:
        return payee_row[0]
    cursor.execute("""
        INSERT INTO payees (name, created_at)
        VALUES (?, ?)
    """, (name, now))
    return cursor.lastrowid


def _payer_scope(cursor, portion_id):
    """Resolve the payer (client + guardian) a statement portion belongs to.

    Payment is recorded against a PAYER, not a statement — but the UI's
    entry point is a row in the outstanding list, which knows a portion.
    This turns the one into the other.
    """
    cursor.execute("""
        SELECT sp.client_id, sp.guardian_number,
               c.file_number, c.first_name, c.middle_name, c.last_name
        FROM statement_portions sp
        JOIN clients c ON sp.client_id = c.id
        WHERE sp.id = ?
    """, (portion_id,))
    row = cursor.fetchone()
    if not row:
        return None

    columns = [col[0] for col in cursor.description]
    scope = dict(zip(columns, row))

    name_parts = [scope['first_name']]
    if scope['middle_name']:
        name_parts.append(scope['middle_name'])
    name_parts.append(scope['last_name'])
    scope['client_name'] = ' '.join(name_parts)

    guardian = scope['guardian_number']
    scope['payer_label'] = f"Guardian {guardian}" if guardian else None
    return scope


def _parse_payment_date(date_str):
    """'YYYY-MM-DD' -> midnight timestamp. None/empty -> now.

    Midnight rather than the time of entry: the ledger date is the day the
    money arrived, and the financial report's range filter runs to
    23:59:59, so any time within the day falls in the same period.
    """
    if not date_str:
        return int(time.time())
    parts = str(date_str).split('-')
    year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
    day = min(day, calendar.monthrange(year, month)[1])
    return int(datetime(year, month, day).timestamp())


@statements_bp.route('/payment-proposal', methods=['GET'])
def payment_proposal():
    """Open portions for a payer, with a proposed oldest-first split.

    Called on opening the payment modal and again whenever the amount
    changes, so the oldest-first arithmetic has exactly one home
    (core/billing.propose_allocation) instead of a second copy in
    JavaScript that could drift from it.

    `amount` omitted proposes against everything outstanding.
    """
    db = get_db()

    portion_id = request.args.get('portion_id', type=int)
    if not portion_id:
        return jsonify({'success': False, 'error': 'portion_id required'}), 400

    conn = db.connect()
    cursor = conn.cursor()

    scope = _payer_scope(cursor, portion_id)
    if not scope:
        return jsonify({'success': False, 'error': 'Portion not found'}), 404

    portions = db.get_client_outstanding_portions(
        scope['client_id'], scope['guardian_number'])

    total_owing = quantize_cents(
        sum((p['amount_owing'] for p in portions), dec(0)))

    requested = request.args.get('amount', type=float)
    amount = total_owing if requested is None else quantize_cents(requested)

    proposed, remainder = propose_allocation(portions, amount)
    proposed_by_id = {pid: value for pid, value in proposed}

    rows = []
    for portion in portions:
        rows.append({
            'portion_id': portion['id'],
            'description': portion['statement_description'],
            'date': datetime.fromtimestamp(
                portion['statement_date']).strftime('%Y-%m-%d'),
            'amount_due': money_float(portion['amount_due']),
            'amount_paid': money_float(portion['amount_paid']),
            'amount_owing': money_float(portion['amount_owing']),
            'proposed': money_float(
                proposed_by_id.get(portion['id'], dec(0))),
        })

    return jsonify({
        'success': True,
        'client_id': scope['client_id'],
        'client_name': scope['client_name'],
        'file_number': scope['file_number'],
        'guardian_number': scope['guardian_number'],
        'payer_label': scope['payer_label'],
        'total_owing': money_float(total_owing),
        'amount': money_float(amount),
        'credit': money_float(
            db.get_client_credit(scope['client_id'], scope['guardian_number'])),
        'portions': rows,
        'unallocated': money_float(remainder),
    })


@statements_bp.route('/record-payment', methods=['POST'])
def record_payment():
    """Record ONE payment against one payer, settling one or more statements.

    The deposit is one financial event: one income entry for the amount
    that actually arrived, on the date it arrived. Which statements it
    settles is a receivables fact, carried by payment_allocations — so a
    $300 transfer covering July and August produces one ledger line that
    maps onto one bank line, not two invented halves.

    Everything here is one transaction: the entry, every allocation row,
    and every portion's amount_paid/status move together or not at all.
    """
    db = get_db()

    data = request.get_json() or {}
    portion_id = data.get('portion_id')          # any portion of the payer
    payment_amount = data.get('payment_amount')
    allocations = data.get('allocations')
    notes = (data.get('notes') or '').strip()

    if not portion_id or payment_amount is None:
        return jsonify({'success': False, 'error': 'Missing required fields'}), 400

    try:
        payment_amount = quantize_cents(payment_amount)
    except Exception:
        return jsonify({'success': False, 'error': 'Invalid payment amount'}), 400

    if to_cents(payment_amount) <= 0:
        return jsonify({'success': False,
                        'error': 'Payment amount must be positive'}), 400

    try:
        ledger_date = _parse_payment_date(data.get('payment_date'))
    except (ValueError, IndexError, TypeError):
        return jsonify({'success': False, 'error': 'Invalid payment date'}), 400

    conn = db.connect()
    cursor = conn.cursor()

    scope = _payer_scope(cursor, portion_id)
    if not scope:
        return jsonify({'success': False, 'error': 'Portion not found'}), 404

    open_portions = db.get_client_outstanding_portions(
        scope['client_id'], scope['guardian_number'])
    by_id = {p['id']: p for p in open_portions}

    # Absent an explicit split, propose one — a single-statement payment is
    # the degenerate case of the same operation, not a separate path.
    if allocations is None:
        proposed, _ = propose_allocation(open_portions, payment_amount)
        allocations = [{'portion_id': pid, 'amount': money_float(value)}
                       for pid, value in proposed if to_cents(value) > 0]

    # ---- validate before writing anything -------------------------------
    cleaned = []
    allocated_total = dec(0)
    seen = set()

    for allocation in allocations:
        target_id = allocation.get('portion_id')
        try:
            amount = quantize_cents(allocation.get('amount'))
        except Exception:
            return jsonify({'success': False,
                            'error': 'Invalid allocation amount'}), 400

        if to_cents(amount) == 0:
            continue
        if to_cents(amount) < 0:
            return jsonify({'success': False,
                            'error': 'Allocation amounts cannot be negative'}), 400
        if target_id in seen:
            return jsonify({'success': False,
                            'error': 'Duplicate allocation for one statement'}), 400
        seen.add(target_id)

        portion = by_id.get(target_id)
        if not portion:
            # Wrong client, wrong guardian, or not open: guardian scoping is
            # load-bearing here — one payer's money must never settle
            # another's portion.
            return jsonify({
                'success': False,
                'error': 'Statement is not open for this payer'}), 400

        if to_cents(amount) > to_cents(portion['amount_owing']):
            # amount_paid must never exceed amount_due; every outstanding
            # calculation downstream depends on it.
            return jsonify({
                'success': False,
                'error': 'Allocation exceeds the amount outstanding on a '
                         'statement'}), 400

        cleaned.append((portion, amount))
        allocated_total += amount

    if to_cents(allocated_total) > to_cents(payment_amount):
        return jsonify({'success': False,
                        'error': 'Allocations exceed the payment amount'}), 400

    remainder = quantize_cents(payment_amount - allocated_total)

    # ---- write ----------------------------------------------------------
    now = int(time.time())

    description = "Client Payment"
    if scope['guardian_number']:
        description += f" (Guardian {scope['guardian_number']})"

    # Tax is pro-rated PER allocation: the statements settled by one
    # payment can carry different tax rates. The entry's tax_amount is the
    # sum of those, not one call against the payment total.
    tax_total = dec(0)
    for portion, amount in cleaned:
        tax_total += prorata_tax(amount, portion['statement_tax_total'],
                                 portion['statement_total'])

    # entries.statement_id stays populated for the first (or only)
    # statement settled, so everything that reads it keeps working;
    # payment_allocations is authoritative when present.
    primary_statement_id = cleaned[0][0]['statement_entry_id'] if cleaned else None

    try:
        cursor.execute("""
            INSERT INTO entries (
                client_id, class, ledger_type, created_at, modified_at,
                description, content, ledger_date, source, total_amount,
                tax_amount, statement_id
            ) VALUES (?, 'income', 'income', ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            None, now, now, description, notes if notes else None,
            ledger_date, scope['file_number'], money_float(payment_amount),
            money_float(tax_total), primary_statement_id
        ))
        entry_id = cursor.lastrowid

        results = []
        for portion, amount in cleaned:
            new_amount_paid, amount_owing, new_status = apply_payment(
                portion['amount_due'], portion['amount_paid'], amount)

            cursor.execute("""
                UPDATE statement_portions
                SET amount_paid = ?, status = ?
                WHERE id = ?
            """, (money_float(new_amount_paid), new_status, portion['id']))

            db.insert_allocation(
                cursor, entry_id, portion['id'], scope['client_id'],
                scope['guardian_number'], amount,
                prorata_tax(amount, portion['statement_tax_total'],
                            portion['statement_total']),
                now)

            results.append({
                'portion_id': portion['id'],
                'amount': money_float(amount),
                'status': new_status,
                'amount_owing': money_float(amount_owing),
            })

        # Anything left over is held as credit rather than forced onto the
        # last statement. The NULL-portion row keeps the invariant
        # SUM(allocations) == entry.total_amount true.
        if to_cents(remainder) > 0:
            db.insert_allocation(
                cursor, entry_id, None, scope['client_id'],
                scope['guardian_number'], remainder, None, now)

        conn.commit()
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False,
                        'error': f'Database error: {str(e)}'}), 500

    return jsonify({
        'success': True,
        'entry_id': entry_id,
        'allocations': results,
        'credit': money_float(remainder),
    })


@statements_bp.route('/mark-paid', methods=['POST'])
def mark_paid():
    """Mark a statement portion as paid (full or partial)."""
    db = get_db()
    
    data = request.get_json()
    portion_id = data.get('portion_id')
    payment_amount = data.get('payment_amount')
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
    payment_amount = quantize_cents(payment_amount)

    # Update portion — exact Decimal arithmetic; status is 'paid' when
    # the owing balance is zero cents (the old `<= 0.01` float fudge is
    # no longer needed; see core/billing.py and CODE_REVIEW.md M1)
    new_amount_paid, amount_owing, new_status = apply_payment(
        portion['amount_due'], portion['amount_paid'], payment_amount)

    cursor.execute("""
        UPDATE statement_portions
        SET amount_paid = ?, status = ?
        WHERE id = ?
    """, (money_float(new_amount_paid), new_status, portion_id))
    
    # Create ledger entry - Income for positive, Expense for negative (refunds)
    if payment_amount >= 0:
        # Normal payment - create Income entry
        # Pro-rata tax for this payment (Decimal; see core/billing.py)
        tax_collected = prorata_tax(payment_amount,
                                    portion.get('statement_tax_total'),
                                    portion.get('statement_total'))

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
            money_float(payment_amount),
            money_float(tax_collected),
            portion['statement_entry_id']
        ))
    else:
        # Refund - create Expense entry with positive amount
        refund_amount = abs(payment_amount)

        # L11: reverse tax proportionally on refunds. The original payment
        # recorded pro-rata tax collected; the refund must record the same
        # proportion as tax paid back, or net tax-collected figures are
        # overstated after refunds.
        refund_tax = prorata_tax(refund_amount,
                                 portion.get('statement_tax_total'),
                                 portion.get('statement_total'))
        
        # Get or create "Client Refund" category
        category_id = _get_or_create_category(cursor, 'Client Refund', now)

        # Get or create payee with file number
        payee_id = _get_or_create_payee(cursor, portion['file_number'], now)

        description = "Client Refund"
        if portion['guardian_number']:
            description += f" (Guardian {portion['guardian_number']})"
        
        cursor.execute("""
            INSERT INTO entries (
                client_id, class, ledger_type, created_at, modified_at,
                description, content, ledger_date, category_id, payee_id,
                total_amount, tax_amount, statement_id
            ) VALUES (?, 'expense', 'expense', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            None,
            now,
            now,
            description,
            notes if notes else None,
            now,
            category_id,
            payee_id,
            money_float(refund_amount),
            money_float(refund_tax),
            portion['statement_entry_id']
        ))

    conn.commit()

    return jsonify({
        'success': True,
        'new_status': new_status,
        'amount_owing': money_float(amount_owing)
    })


@statements_bp.route('/write-off', methods=['POST'])
def write_off_statement():
    """Write off a statement portion."""
    db = get_db()
    
    data = request.get_json()
    portion_id = data.get('portion_id')
    reason = data.get('reason')  # 'uncollectible', 'waived', 'billing_error', 'other'
    note = data.get('note', '')
    
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
    amount_owing = quantize_cents(
        dec(portion['amount_due']) - dec(portion['amount_paid']))
    content_parts = [
        f"**Statement:** {portion['statement_description']}",
        f"**Amount Written Off:** ${amount_owing:.2f}",
        f"**Reason:** {reason_label}"
    ]
    if note:
        content_parts.append(f"**Note:** {note}")
    
    comm_content = '\n\n'.join(content_parts)
    
    # Format current time for comm_time
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
        category_id = _get_or_create_category(cursor, 'Bad Debt', now)

        # Check if payee with file number exists, create if not
        payee_id = _get_or_create_payee(cursor, portion['file_number'], now)

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
            money_float(amount_owing),
            portion['statement_entry_id']
        ))
    
    conn.commit()
    
    return jsonify({'success': True})
