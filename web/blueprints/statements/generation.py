"""Statement generation: find unbilled entries and create statements.

Extracted from the statements.py blueprint split.
"""
from flask import request, jsonify
from datetime import datetime
import calendar
import time
from core.money import money_float, to_cents, dec, quantize_cents
from core.billing import compute_statement_totals, split_guardian_amounts
from web.blueprints.statements.common import statements_bp, get_db


def _apply_credit(db, cursor, client_id, guardian_number, portion_id,
                  amount_due, statement_total, statement_tax, now):
    """Spend any credit this payer holds against a just-created portion.

    Carry-forward already pulls prior DEBITS onto the next statement
    without asking; a credit is the same thing with the opposite sign, and
    carrying only what the client owes would be asymmetric in the
    practitioner's favour. So credit is applied automatically — and shown
    as its own line on the PDF, never silently.

    Runs on the generation cursor, so a credit cannot be spent twice even
    by two statements generated in the same batch.
    """
    consumed = db.consume_credit(cursor, client_id, guardian_number,
                                 portion_id, amount_due, now,
                                 statement_tax=statement_tax,
                                 statement_total=statement_total)
    if to_cents(consumed) > 0:
        # Status stays 'ready': the statement still has to be sent, even
        # when credit covers all of it. mark-sent settles it on the way out.
        cursor.execute("""
            UPDATE statement_portions SET amount_paid = ? WHERE id = ?
        """, (money_float(consumed), portion_id))
    return consumed


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
    
    # Stragglers: unbilled fee-bearing entries dated BEFORE the range start.
    # Same predicate, earlier dates. Reported, never auto-included: an old
    # unbilled entry may be unbilled on purpose (fee under discussion, pro
    # bono pending), and widening the range is a billing decision that stays
    # with the practitioner. The generator just refuses to be silently
    # incomplete about it.
    cursor.execute("""
        SELECT COUNT(*) AS n,
               MIN(CASE e.class
                   WHEN 'session' THEN e.session_date
                   WHEN 'absence' THEN e.absence_date
                   ELSE e.item_date END) AS earliest
        FROM entries e
        JOIN clients c ON e.client_id = c.id
        JOIN client_types ct ON c.type_id = ct.id
        WHERE e.class IN ('session', 'absence', 'item')
        AND e.statement_id IS NULL
        AND e.locked = 1
        AND ct.name != 'Inactive'
        AND (
            (e.class = 'session' AND e.session_date < ? AND e.fee > 0)
            OR (e.class = 'absence' AND e.absence_date < ? AND (e.fee > 0 OR e.base_fee > 0))
            OR (e.class = 'item' AND e.item_date < ? AND (e.fee != 0 OR e.base_price != 0))
        )
    """, (start_ts, start_ts, start_ts))
    n_before, earliest_ts = cursor.fetchone()
    earlier_unbilled = None
    if n_before:
        earlier_unbilled = {
            'count': n_before,
            'earliest': datetime.fromtimestamp(earliest_ts).strftime('%Y-%m-%d'),
        }

    return jsonify({
        'success': True,
        'clients': list(clients.values()),
        'earlier_unbilled': earlier_unbilled
    })


def generate_statement_for_client(db, cursor, client_id, start_ts, end_ts,
                                  start_dt, end_dt, now):
    """Generate one statement for one client's unbilled entries in a period.

    The single code path for statement creation — the month-end bulk run
    and Bill Now both come through here, so they cannot disagree on what
    gets billed or how. Writes on the caller's cursor and does NOT commit.

    Returns ('generated', info) with statement_id/total/entry_count,
    ('skipped', info) when the period nets negative for the client or for
    one guardian (entries left unbilled to carry the credit forward), or
    (None, None) when the client has nothing fee-bearing in the period.
    """
    # Get client info
    cursor.execute("""
        SELECT c.*, ct.name as type_name
        FROM clients c
        JOIN client_types ct ON c.type_id = ct.id
        WHERE c.id = ?
    """, (client_id,))
    client_row = cursor.fetchone()
    if not client_row:
        return None, None
    client_cols = [col[0] for col in cursor.description]
    client = dict(zip(client_cols, client_row))
    name_parts = [client['first_name']]
    if client['middle_name']:
        name_parts.append(client['middle_name'])
    name_parts.append(client['last_name'])
    client_name = ' '.join(name_parts)
    
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
        return None, None
    
    entry_cols = [col[0] for col in cursor.description]
    entries = [dict(zip(entry_cols, row)) for row in entry_rows]
    
    # Calculate total and total tax (Decimal arithmetic — see core/billing.py)
    total, total_tax = compute_statement_totals(entries)

    # A period whose credits outweigh its charges produces no statement.
    # The item form invites credit lines ("Use negative amounts for
    # credits"), and normally they simply reduce the period's total —
    # but with too few charges to absorb one, the statement total goes
    # negative, and a document telling the client THEY are owed money
    # is not something to send. The entries stay unbilled, so the
    # credit carries forward to the next period that can absorb it.
    # Zero is allowed through: it documents that a credit exactly
    # offset the charges, and marks those entries settled.
    if to_cents(total) < 0:
        return 'skipped', {
            'client_id': client_id,
            'name': client_name,
            'total': money_float(total),
        }

    # The same rule, applied PER PAYER. On a guardian split the
    # statement total can stay positive while ONE guardian's share nets
    # negative — explicit per-item assignments make this easy (sessions
    # to guardian 1, a credit item to guardian 2). A negative portion
    # has no sane life downstream: credit application skips it, and
    # mark-sent's "amount_paid >= amount_due" test settles it on the
    # spot, evaporating money that payer is genuinely owed. So the
    # statement is not generated; the entries stay unbilled until a
    # period whose charges can absorb the credit, exactly as above.
    # The split is computed ONCE here and reused at insertion, so the
    # check and the insert can never disagree.
    split_portions = None
    if profile and profile.get('is_minor') and profile.get('guardian1_name'):
        split_portions = split_guardian_amounts(entries, profile, total)
        negative = [amt for _, amt in split_portions if to_cents(amt) < 0]
        if negative:
            return 'skipped', {
                'client_id': client_id,
                'name': client_name,
                'total': money_float(min(negative)),
            }
    
    # Create statement description
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
    if split_portions is not None:
        # Guardian split logic lives in core/billing.py:
        # explicit per-item amounts honored; percentage pool split with
        # the exact remainder to guardian 2; single guardian (H3) pays
        # the full statement amount. Computed above (negative-portion
        # check) and reused here.
        for guardian_number, amount in split_portions:
            cursor.execute("""
                INSERT INTO statement_portions (
                    statement_entry_id, client_id, guardian_number,
                    amount_due, amount_paid, status, created_at
                ) VALUES (?, ?, ?, ?, 0, 'ready', ?)
            """, (statement_id, client_id, guardian_number,
                  money_float(amount), now))
            _apply_credit(db, cursor, client_id, guardian_number,
                          cursor.lastrowid, amount, total, total_tax, now)
    else:
        # Single portion for client
        cursor.execute("""
            INSERT INTO statement_portions (
                statement_entry_id, client_id, guardian_number,
                amount_due, amount_paid, status, created_at
            ) VALUES (?, ?, NULL, ?, 0, 'ready', ?)
        """, (statement_id, client_id, money_float(total), now))
        _apply_credit(db, cursor, client_id, None, cursor.lastrowid,
                      total, total, total_tax, now)

    return 'generated', {
        'client_id': client_id,
        'statement_id': statement_id,
        'total': money_float(total),
        'entry_count': len(entries),
    }


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
    skipped = []
    
    start_dt = datetime(start_year, start_month, start_day)
    end_dt = datetime(end_year, end_month, end_day)
    for client_id in client_ids:
        outcome, info = generate_statement_for_client(
            db, cursor, client_id, start_ts, end_ts, start_dt, end_dt, now)
        if outcome == 'generated':
            generated.append(info)
        elif outcome == 'skipped':
            skipped.append(info)

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
        'portion_count': portion_count,
        'skipped': skipped,
    })


# ---------------------------------------------------------------------------
# Bill Now — one client, billed on demand from an entry form
# ---------------------------------------------------------------------------

_DATE_FIELD = {'session': 'session_date', 'absence': 'absence_date',
               'item': 'item_date'}


def _bill_now_scope(cursor, entry):
    """Work out what a Bill Now on this entry would bill.

    Scope is the client's fee-bearing, locked, unbilled entries dated up to
    and including this entry — everything they owe as of it. The start of
    the period is the earliest such entry, so the statement's month label
    is honest and nothing older is stranded to be billed alone later.

    Returns (start_ts, end_ts, start_dt, end_dt, entries) using exactly the
    predicate generation uses, or None when the entry is not billable.
    """
    cls = entry.get('class')
    date_field = _DATE_FIELD.get(cls)
    if not date_field or not entry.get(date_field):
        return None
    if entry.get('statement_id') is not None or not entry.get('locked'):
        return None
    if cls == 'session' and not (entry.get('fee') or 0) > 0:
        return None
    if cls == 'absence' and not ((entry.get('fee') or 0) > 0
                                 or (entry.get('base_fee') or 0) > 0):
        return None
    if cls == 'item' and not ((entry.get('fee') or 0) > 0
                              or (entry.get('base_price') or 0) > 0):
        return None

    end_day = datetime.fromtimestamp(entry[date_field])
    end_dt = datetime(end_day.year, end_day.month, end_day.day)
    end_ts = int(datetime(end_dt.year, end_dt.month, end_dt.day,
                          23, 59, 59).timestamp())

    cursor.execute("""
        SELECT id, class, description, fee, base_fee, base_price,
               session_date, absence_date, item_date
        FROM entries
        WHERE client_id = ?
        AND class IN ('session', 'absence', 'item')
        AND statement_id IS NULL
        AND locked = 1
        AND (
            (class = 'session' AND session_date <= ? AND fee > 0)
            OR (class = 'absence' AND absence_date <= ? AND (fee > 0 OR base_fee > 0))
            OR (class = 'item' AND item_date <= ? AND (fee != 0 OR base_price != 0))
        )
        ORDER BY COALESCE(session_date, absence_date, item_date)
    """, (entry['client_id'], end_ts, end_ts, end_ts))
    cols = [c[0] for c in cursor.description]
    entries = [dict(zip(cols, r)) for r in cursor.fetchall()]
    if not entries:
        return None

    first = min(e[_DATE_FIELD[e['class']]] for e in entries)
    first_day = datetime.fromtimestamp(first)
    start_dt = datetime(first_day.year, first_day.month, first_day.day)
    start_ts = int(start_dt.timestamp())
    return start_ts, end_ts, start_dt, end_dt, entries


def _scope_summary(entries):
    lines = []
    for e in entries:
        d = datetime.fromtimestamp(e[_DATE_FIELD[e['class']]]).strftime('%b %-d')
        amount = e['fee'] if e['class'] == 'session' else (
            e['fee'] or (e['base_fee'] if e['class'] == 'absence' else e['base_price']) or 0)
        lines.append({'id': e['id'], 'class': e['class'], 'date': d,
                      'description': e['description'] or '',
                      'amount': money_float(amount)})
    return lines


@statements_bp.route('/bill-now/preview/<int:entry_id>', methods=['GET'])
def bill_now_preview(entry_id):
    """What Bill Now would bill from this entry — for the confirm dialog."""
    db = get_db()
    entry = db.get_entry(entry_id)
    if not entry:
        return jsonify({'success': False, 'error': 'Entry not found'}), 404
    cursor = db.connect().cursor()
    scope = _bill_now_scope(cursor, entry)
    if scope is None:
        return jsonify({'success': False,
                        'error': 'This entry cannot be billed'}), 400
    start_ts, end_ts, start_dt, end_dt, entries = scope
    total, _ = compute_statement_totals(entries)
    return jsonify({
        'success': True,
        'entries': _scope_summary(entries),
        'total': money_float(total),
        'period': (start_dt.strftime('%b %-d') if start_dt != end_dt else '')
                  + (' – ' if start_dt != end_dt else '')
                  + end_dt.strftime('%b %-d, %Y'),
    })


@statements_bp.route('/bill-now/<int:entry_id>', methods=['POST'])
def bill_now(entry_id):
    """Generate a statement for this entry's client, on demand.

    Same generator as the month-end run — just a period that ends on this
    entry's date. By itself records nothing about payment: that is Record
    Payment's job, and the statement PDF becomes the receipt once done.

    JSON body `{"paid_now": true, "note": "e-transfer"}` is the pay-at-desk
    shortcut: the money is in hand as the user clicks, so the same
    transaction also marks the statement sent (handed over) and records the
    full payment through write_payment — the identical path Record Payment
    takes, income entry and allocation included. Refused for guardian-split
    statements: two payers, two payments, recorded individually.
    """
    from web.blueprints.statements.payments import (
        write_payment, _payer_scope, _parse_payment_date)

    db = get_db()
    entry = db.get_entry(entry_id)
    if not entry:
        return jsonify({'success': False, 'error': 'Entry not found'}), 404
    body = request.get_json(silent=True) or {}
    paid_now = bool(body.get('paid_now'))
    note = (body.get('note') or '').strip()

    conn = db.connect()
    cursor = conn.cursor()
    scope = _bill_now_scope(cursor, entry)
    if scope is None:
        return jsonify({'success': False,
                        'error': 'This entry cannot be billed'}), 400
    start_ts, end_ts, start_dt, end_dt, _ = scope
    now = int(time.time())

    outcome, info = generate_statement_for_client(
        db, cursor, entry['client_id'], start_ts, end_ts,
        start_dt, end_dt, now)
    if outcome != 'generated':
        conn.rollback()
        if outcome == 'skipped':
            return jsonify({'success': False, 'error': (
                'Credits in this period outweigh the charges, so no '
                'statement can be produced; the entries stay unbilled and '
                'the credit carries forward.')}), 400
        return jsonify({'success': False,
                        'error': 'Nothing to bill'}), 400

    payment = None
    if paid_now:
        cursor.execute("""
            SELECT sp.id, sp.statement_entry_id, sp.client_id,
                   sp.guardian_number, sp.amount_due, sp.amount_paid,
                   sp.status, e.statement_total, e.statement_tax_total
            FROM statement_portions sp
            JOIN entries e ON sp.statement_entry_id = e.id
            WHERE sp.statement_entry_id = ?
        """, (info['statement_id'],))
        cols = [c[0] for c in cursor.description]
        portions = [dict(zip(cols, r)) for r in cursor.fetchall()]
        if len(portions) != 1:
            conn.rollback()
            return jsonify({'success': False, 'error': (
                'This statement splits between two guardians; generate it '
                'without "Paid now" and record each payment separately.'
            )}), 400
        portion = portions[0]
        owing = quantize_cents(dec(portion['amount_due']) - dec(portion['amount_paid']))
        if to_cents(owing) > 0:
            # Handed over at the desk: sent as of now, with no email.
            cursor.execute("""
                UPDATE statement_portions SET status = 'sent', date_sent = ?
                WHERE id = ? AND status = 'ready'
            """, (now, portion['id']))
            payer = _payer_scope(cursor, portion['id'])
            try:
                entry_id_income, results, _ = write_payment(
                    db, cursor, payer, [(portion, owing)], owing, note,
                    _parse_payment_date(None), now)
            except Exception as e:
                conn.rollback()
                return jsonify({'success': False,
                                'error': f'Database error: {e}'}), 500
            payment = {'income_entry_id': entry_id_income,
                       'status': results[0]['status']}
        else:
            # Credit covered the whole statement at generation; already paid.
            payment = {'income_entry_id': None, 'status': 'paid'}

    try:
        conn.commit()
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False,
                        'error': f'Database error: {e}'}), 500
    return jsonify({'success': True, 'statement_id': info['statement_id'],
                    'total': info['total'],
                    'entry_count': info['entry_count'],
                    'payment': payment})
