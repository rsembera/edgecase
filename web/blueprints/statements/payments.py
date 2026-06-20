"""Payment + write-off routes (and the ledger category/payee helpers they use).

Extracted from the statements.py blueprint split.
"""
from flask import request, jsonify
from datetime import datetime
import time
from core.money import dec, quantize_cents, money_float
from core.billing import apply_payment, prorata_tax
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


@statements_bp.route('/mark-paid', methods=['POST'])
def mark_paid():
    """Mark a statement portion as paid (full or partial)."""
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
