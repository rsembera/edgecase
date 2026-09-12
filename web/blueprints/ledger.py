# -*- coding: utf-8 -*-
"""
EdgeCase Ledger Blueprint
Handles income and expense tracking
"""

from flask import (Blueprint, render_template, request, redirect, url_for,
                   jsonify, send_file, after_this_request)
from web.utils import (parse_date_from_form, get_today_date_parts,
                       save_uploaded_files, private_pdf_dir)
from datetime import datetime
from werkzeug.utils import secure_filename
import sqlcipher3 as sqlite3
import os
import shutil
import time
from core.database import Database
from core.config import ATTACHMENTS_DIR, ASSETS_DIR
from core.money import money_float
from pathlib import Path

ledger_bp = Blueprint('ledger', __name__)

# Database instance (set by init_blueprint)
db = None

def init_blueprint(database):
    """Initialize blueprint with database instance"""
    global db
    db = database


# ============================================================================
# JINJA2 CUSTOM FILTERS
# ============================================================================

@ledger_bp.app_template_filter('timestamp_to_datetime')
def timestamp_to_datetime_filter(timestamp):
    """Convert Unix timestamp to datetime object for Jinja2 templates."""
    if timestamp:
        return datetime.fromtimestamp(timestamp)
    return None


@ledger_bp.app_template_filter('currency_symbol')
def currency_symbol_filter(currency_code):
    """Convert currency code to symbol"""
    symbols = {
        'CAD': '$',
        'USD': '$',
        'EUR': '€',
        'GBP': '£',
        'AUD': '$',
        'INR': '₹',
        'JPY': '¥'
    }
    return symbols.get(currency_code, currency_code)


# ============================================================================
# LEDGER MAIN VIEW
# ============================================================================

@ledger_bp.route('/ledger')
def ledger():
    """Display the ledger with all income and expense entries."""
    
    entries = db.get_all_ledger_entries()
    currency = db.get_setting('currency', 'CAD')
    
    now = datetime.now()
    current_year = now.year
    current_month = now.month
    
    ytd_income = 0
    ytd_expenses = 0
    mtd_income = 0
    mtd_expenses = 0
    ytd_expenses_by_category = {}
    entries_by_year_month = {}
    
    for entry in entries:
        if entry.get('ledger_date'):
            entry_dt = datetime.fromtimestamp(entry['ledger_date'])
            year = entry_dt.year
            month = entry_dt.month
            month_name = entry_dt.strftime('%B')
            amount = entry.get('total_amount', 0) or 0
            
            if year == current_year:
                if entry['ledger_type'] == 'income':
                    ytd_income += amount
                elif entry['ledger_type'] == 'expense':
                    ytd_expenses += amount
                    cat_name = entry.get('category_name') or 'Uncategorized'
                    if cat_name not in ytd_expenses_by_category:
                        ytd_expenses_by_category[cat_name] = 0
                    ytd_expenses_by_category[cat_name] += amount
            
            if year == current_year and month == current_month:
                if entry['ledger_type'] == 'income':
                    mtd_income += amount
                elif entry['ledger_type'] == 'expense':
                    mtd_expenses += amount
            
            if year not in entries_by_year_month:
                entries_by_year_month[year] = {}
            
            if month not in entries_by_year_month[year]:
                entries_by_year_month[year][month] = {
                    'name': month_name,
                    'entries': []
                }
            
            entries_by_year_month[year][month]['entries'].append(entry)
    
    ytd_net = ytd_income - ytd_expenses
    mtd_net = mtd_income - mtd_expenses
    
    ytd_category_breakdown = []
    for cat_name, amount in sorted(ytd_expenses_by_category.items(), key=lambda x: x[1], reverse=True):
        ytd_category_breakdown.append({'name': cat_name, 'amount': amount})
    
    years = sorted(entries_by_year_month.keys(), reverse=True)
    for year in years:
        entries_by_year_month[year] = dict(sorted(entries_by_year_month[year].items(), reverse=True))
    
    for year in entries_by_year_month:
        for month in entries_by_year_month[year]:
            entries_by_year_month[year][month]['entries'].sort(
                key=lambda e: (e.get('ledger_date') or 0,
                               e.get('created_at') or 0,
                               e['id']),
                reverse=True
            )
    
    return render_template('ledger.html',
                         entries_by_year_month=entries_by_year_month,
                         years=years,
                         currency=currency,
                         ytd_income=ytd_income,
                         ytd_expenses=ytd_expenses,
                         ytd_net=ytd_net,
                         mtd_income=mtd_income,
                         mtd_expenses=mtd_expenses,
                         mtd_net=mtd_net,
                         ytd_category_breakdown=ytd_category_breakdown,
                         current_year=current_year)


# ============================================================================
# INCOME ENTRY ROUTES
# ============================================================================

@ledger_bp.route('/ledger/income', methods=['GET', 'POST'])
def create_income():
    """Create new income entry."""
    
    if request.method == 'POST':
        # ledger_date is a DATE: local midnight, always. Newest-first within
        # a day comes from created_at (see get_all_ledger_entries), not from
        # smuggling the time of data entry into the transaction date.
        ledger_date_timestamp = parse_date_from_form(request.form)
        source = request.form.get('source', '').strip()
        
        # Add payor to suggestions if new
        if source:
            db.add_income_payor_if_new(source)
        
        income_data = {
            'client_id': None,
            'class': 'income',
            'ledger_type': 'income',
            'ledger_date': ledger_date_timestamp,
            'source': source,
            'total_amount': money_float(request.form.get('total_amount', 0) or 0),
            'tax_amount': money_float(request.form.get('tax_amount') or 0),
            'description': request.form.get('description', ''),
            'content': request.form.get('content', '')
        }
        
        entry_id = db.add_entry(income_data)
        
        files = request.files.getlist('files[]')
        descriptions = request.form.getlist('file_descriptions[]')
        save_uploaded_files(files, descriptions, entry_id, db)
        
        return redirect(url_for('ledger.ledger'))
    
    date_parts = get_today_date_parts()
    currency = db.get_setting('currency', '$')
    payor_suggestions = db.get_distinct_payor_sources()
    
    return render_template('entry_forms/income.html',
                         **date_parts,
                         payor_suggestions=payor_suggestions,
                         currency=currency,
                         is_edit=False)


@ledger_bp.route('/ledger/income/<int:entry_id>', methods=['GET', 'POST'])
def edit_income(entry_id):
    """Edit existing income entry."""
    income = db.get_entry(entry_id)
    
    if not income or income['ledger_type'] != 'income':
        return "Income entry not found", 404
    
    if request.method == 'POST':
        source = request.form.get('source', '').strip()
        
        # Add payor to suggestions if new
        if source:
            db.add_income_payor_if_new(source)
        
        # Midnight, always. The old code preserved the row's original
        # timestamp when the day was unchanged, to stop an edit from moving
        # the entry in the list; with created_at doing the ordering there is
        # nothing left to preserve, and re-saving an old row normalizes it.
        ledger_date_timestamp = parse_date_from_form(request.form)
        
        income_data = {
            'ledger_date': ledger_date_timestamp,
            'source': source,
            'total_amount': money_float(request.form.get('total_amount', 0) or 0),
            'tax_amount': money_float(request.form.get('tax_amount') or 0),
            'description': request.form.get('description', ''),
            'content': request.form.get('content', '')
        }
        
        files = request.files.getlist('files[]')
        descriptions = request.form.getlist('file_descriptions[]')
        save_uploaded_files(files, descriptions, entry_id, db)
        
        db.update_entry(entry_id, income_data, allow_locked=True)
        
        return redirect(url_for('ledger.ledger'))
    
    income_year = income_month = income_day = None
    if income.get('ledger_date'):
        income_dt = datetime.fromtimestamp(income['ledger_date'])
        income_year = income_dt.year
        income_month = income_dt.month
        income_day = income_dt.day
    
    attachments = db.get_attachments(entry_id)
    currency = db.get_setting('currency', '$')
    payor_suggestions = db.get_distinct_payor_sources()
    
    return render_template('entry_forms/income.html',
                         entry=income,
                         income_year=income_year,
                         income_month=income_month,
                         income_day=income_day,
                         payor_suggestions=payor_suggestions,
                         attachments=attachments,
                         currency=currency,
                         is_edit=True)


@ledger_bp.route('/ledger/income/<int:entry_id>/delete', methods=['POST'])
def delete_income_entry(entry_id):
    """Delete income entry and all its attachments."""
    entry = db.get_entry(entry_id)
    
    if not entry or entry['ledger_type'] != 'income':
        return "Income entry not found", 404
    
    try:
        upload_dir = ATTACHMENTS_DIR / 'ledger' / str(entry_id)
        if os.path.exists(upload_dir):
            shutil.rmtree(upload_dir)
        
        conn = db.connect()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM attachments WHERE entry_id = ?", (entry_id,))
        cursor.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
        conn.commit()
        
        return "", 200
    except Exception as e:
        print(f"Error deleting income entry: {e}")
        return f"Error: {str(e)}", 500


# ============================================================================
# EXPENSE ENTRY ROUTES
# ============================================================================

@ledger_bp.route('/ledger/expense', methods=['GET', 'POST'])
def create_expense():
    """Create new expense entry."""
    
    if request.method == 'POST':
        payee_name = request.form.get('payee_name', '').strip()
        category_name = request.form.get('category_name', '').strip()
        
        # Get or create category and get ID
        category_id = None
        if category_name:
            existing = db.get_expense_category_by_name(category_name)
            if existing:
                category_id = existing['id']
            else:
                category_id = db.add_expense_category(category_name)
        
        # Get or create payee and get ID
        payee_id = None
        if payee_name:
            payee_id = db.add_payee_if_new(payee_name)
        
        # ledger_date is a DATE: local midnight, always. See create_income.
        ledger_date_timestamp = parse_date_from_form(request.form)
        
        expense_data = {
            'client_id': None,
            'class': 'expense',
            'ledger_type': 'expense',
            'ledger_date': ledger_date_timestamp,
            'payee_id': payee_id,
            'category_id': category_id,
            'total_amount': money_float(request.form.get('total_amount', 0) or 0),
            'tax_amount': money_float(request.form.get('tax_amount') or 0),
            'description': request.form.get('description', ''),
            'content': request.form.get('content', '')
        }
        
        entry_id = db.add_entry(expense_data)
        
        files = request.files.getlist('files[]')
        descriptions = request.form.getlist('file_descriptions[]')
        save_uploaded_files(files, descriptions, entry_id, db)
        
        return redirect(url_for('ledger.ledger'))
    
    date_parts = get_today_date_parts()
    categories = db.get_all_expense_categories()
    category_suggestions = [c['name'] for c in categories]
    payee_suggestions = db.get_distinct_payee_names()
    currency = db.get_setting('currency', '$')
    
    return render_template('entry_forms/expense.html',
                         **date_parts,
                         payee_name='',
                         category_name='',
                         payee_suggestions=payee_suggestions,
                         category_suggestions=category_suggestions,
                         currency=currency,
                         is_edit=False)


@ledger_bp.route('/ledger/expense/<int:entry_id>', methods=['GET', 'POST'])
def edit_expense(entry_id):
    """Edit existing expense entry."""
    expense = db.get_entry(entry_id)
    
    if not expense or expense['ledger_type'] != 'expense':
        return "Expense entry not found", 404
    
    if request.method == 'POST':
        payee_name = request.form.get('payee_name', '').strip()
        category_name = request.form.get('category_name', '').strip()
        
        # Get or create category and get ID
        category_id = None
        if category_name:
            existing = db.get_expense_category_by_name(category_name)
            if existing:
                category_id = existing['id']
            else:
                category_id = db.add_expense_category(category_name)
        
        # Get or create payee and get ID
        payee_id = None
        if payee_name:
            payee_id = db.add_payee_if_new(payee_name)
        
        # Midnight, always. See edit_income for why the old preserve-the-
        # original-timestamp dance is gone.
        ledger_date_timestamp = parse_date_from_form(request.form)
        
        expense_data = {
            'ledger_date': ledger_date_timestamp,
            'payee_id': payee_id,
            'category_id': category_id,
            'total_amount': money_float(request.form.get('total_amount', 0) or 0),
            'tax_amount': money_float(request.form.get('tax_amount') or 0),
            'description': request.form.get('description', ''),
            'content': request.form.get('content', '')
        }
        
        files = request.files.getlist('files[]')
        descriptions = request.form.getlist('file_descriptions[]')
        save_uploaded_files(files, descriptions, entry_id, db)
        
        db.update_entry(entry_id, expense_data, allow_locked=True)
        
        return redirect(url_for('ledger.ledger'))
    
    expense_year = expense_month = expense_day = None
    if expense.get('ledger_date'):
        expense_dt = datetime.fromtimestamp(expense['ledger_date'])
        expense_year = expense_dt.year
        expense_month = expense_dt.month
        expense_day = expense_dt.day
    
    # Look up payee and category names from IDs
    payee_name = ''
    if expense.get('payee_id'):
        conn = db.connect()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM payees WHERE id = ?", (expense['payee_id'],))
        row = cursor.fetchone()
        if row:
            payee_name = row[0]
    
    category_name = ''
    if expense.get('category_id'):
        category = db.get_expense_category(expense['category_id'])
        if category:
            category_name = category['name']
    
    categories = db.get_all_expense_categories()
    category_suggestions = [c['name'] for c in categories]
    payee_suggestions = db.get_distinct_payee_names()
    attachments = db.get_attachments(entry_id)
    currency = db.get_setting('currency', '$')
    
    return render_template('entry_forms/expense.html',
                         entry=expense,
                         payee_name=payee_name,
                         category_name=category_name,
                         expense_year=expense_year,
                         expense_month=expense_month,
                         expense_day=expense_day,
                         payee_suggestions=payee_suggestions,
                         category_suggestions=category_suggestions,
                         attachments=attachments,
                         currency=currency,
                         is_edit=True)


@ledger_bp.route('/ledger/expense/<int:entry_id>/delete', methods=['POST'])
def delete_expense_entry(entry_id):
    """Delete expense entry and all its attachments."""
    entry = db.get_entry(entry_id)
    
    if not entry or entry['ledger_type'] != 'expense':
        return "Expense entry not found", 404
    
    try:
        upload_dir = ATTACHMENTS_DIR / 'ledger' / str(entry_id)
        if os.path.exists(upload_dir):
            shutil.rmtree(upload_dir)
        
        conn = db.connect()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM attachments WHERE entry_id = ?", (entry_id,))
        cursor.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
        conn.commit()
        
        return "", 200
    except Exception as e:
        print(f"Error deleting expense entry: {e}")
        return f"Error: {str(e)}", 500


# ============================================================================
# SUGGESTION MANAGEMENT
# ============================================================================

@ledger_bp.route('/ledger/suggestion/payee/remove', methods=['POST'])
def remove_payee_suggestion():
    """Remove a payee from the suggestions list."""
    data = request.get_json()
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'No name provided'}), 400
    
    try:
        conn = db.connect()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM payees WHERE name = ?", (name,))
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@ledger_bp.route('/ledger/suggestion/category/remove', methods=['POST'])
def remove_category_suggestion():
    """Remove a category from the suggestions list."""
    data = request.get_json()
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'No name provided'}), 400
    
    try:
        conn = db.connect()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM expense_categories WHERE name = ?", (name,))
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@ledger_bp.route('/ledger/suggestion/payor/remove', methods=['POST'])
def remove_payor_suggestion():
    """Remove a payor from the suggestions list."""
    data = request.get_json()
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'No name provided'}), 400
    
    try:
        db.delete_income_payor(name)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================================
# REPORTS
# ============================================================================

@ledger_bp.route('/ledger/report')
def ledger_report():
    """Display the financial report generator page."""
    now = datetime.now()

    # Client dropdown for per-client payment records, grouped so the
    # active roster stays one glance long (Rick, 2026-08-05). "Inactive"
    # is a client type, not a status column.
    all_clients = db.get_all_clients()
    all_types = db.get_all_client_types()
    inactive_type = next((t for t in all_types if t['name'] == 'Inactive'), None)
    inactive_id = inactive_type['id'] if inactive_type else None

    def _label(c):
        return f"{c['file_number']} — {c['last_name']}, {c['first_name']}"

    active_clients = [{'id': c['id'], 'label': _label(c)}
                      for c in all_clients if c['type_id'] != inactive_id]
    inactive_clients = [{'id': c['id'], 'label': _label(c)}
                        for c in all_clients if c['type_id'] == inactive_id]

    return render_template('ledger_report.html',
        default_start_year=now.year,
        default_start_month=1,
        default_start_day=1,
        default_end_year=now.year,
        default_end_month=now.month,
        default_end_day=now.day,
        active_clients=active_clients,
        inactive_clients=inactive_clients
    )


def _client_filter_sql():
    """Shared per-client payment/refund filters (see pdf/ledger_report.py).

    Returns (income_condition, refund_condition); both use the statement
    subquery so payments AND refunds are caught regardless of how the
    file number was stored (income: source column; refunds: payee name).
    """
    stmt_subq = "(SELECT id FROM entries WHERE class = 'statement' AND client_id = ?)"
    return (f"AND (source = ? OR statement_id IN {stmt_subq})",
            f"AND statement_id IN {stmt_subq}")


@ledger_bp.route('/ledger/report/calculate')
def calculate_report():
    """Calculate totals for preview without generating PDF."""
    start_date = request.args.get('start')
    end_date = request.args.get('end')
    client_id = request.args.get('client', type=int)
    
    if not start_date or not end_date:
        return jsonify({'success': False, 'error': 'Missing date range'}), 400
    
    start_ts = int(datetime.strptime(start_date, '%Y-%m-%d').timestamp())
    end_ts = int(datetime.strptime(end_date + ' 23:59:59', '%Y-%m-%d %H:%M:%S').timestamp())
    
    conn = db.connect()
    cursor = conn.cursor()

    # Per-client mode: income = the client's payments, expenses = their
    # refunds only; category breakdown is meaningless and returned empty.
    client = db.get_client(client_id) if client_id else None
    if client_id and not client:
        return jsonify({'success': False, 'error': 'Client not found'}), 404
    income_cond, refund_cond = _client_filter_sql() if client else ('', '')
    income_params = (client['file_number'], client['id']) if client else ()
    refund_params = (client['id'],) if client else ()
    
    cursor.execute(f"""
        SELECT COALESCE(SUM(total_amount), 0) as total,
               COALESCE(SUM(tax_amount), 0) as tax
        FROM entries
        WHERE class = 'income' AND ledger_type = 'income'
        AND ledger_date >= ? AND ledger_date <= ?
        {income_cond}
    """, (start_ts, end_ts) + income_params)
    row = cursor.fetchone()
    total_income = row[0] or 0
    tax_collected = row[1] or 0
    
    cursor.execute(f"""
        SELECT COALESCE(SUM(total_amount), 0) as total,
               COALESCE(SUM(tax_amount), 0) as tax
        FROM entries
        WHERE class = 'expense' AND ledger_type = 'expense'
        AND ledger_date >= ? AND ledger_date <= ?
        {refund_cond}
    """, (start_ts, end_ts) + refund_params)
    row = cursor.fetchone()
    total_expenses = row[0] or 0
    tax_paid = row[1] or 0
    
    categories = []
    if not client:
        cursor.execute("""
            SELECT COALESCE(ec.name, 'Uncategorized') as cat_name, 
                   COALESCE(SUM(e.total_amount), 0) as total
            FROM entries e
            LEFT JOIN expense_categories ec ON e.category_id = ec.id
            WHERE e.class = 'expense' AND e.ledger_type = 'expense'
            AND e.ledger_date >= ? AND e.ledger_date <= ?
            GROUP BY ec.name
            ORDER BY cat_name
        """, (start_ts, end_ts))
        
        for row in cursor.fetchall():
            categories.append({
                'name': row[0] or 'Uncategorized',
                'total': row[1]
            })
    
    return jsonify({
        'success': True,
        'client_mode': bool(client),
        'total_income': total_income,
        'total_expenses': total_expenses,
        'net_income': total_income - total_expenses,
        'tax_collected': tax_collected,
        'tax_paid': tax_paid,
        'categories': categories
    })


@ledger_bp.route('/ledger/report/pdf')
def generate_report_pdf():
    """Generate the PDF financial report."""
    from pdf.ledger_report import generate_ledger_report_pdf
    
    start_date = request.args.get('start')
    end_date = request.args.get('end')
    client_id = request.args.get('client', type=int)
    include_details = request.args.get('details') == '1'
    include_taxes = request.args.get('taxes') == '1'
    include_attachments = request.args.get('attachments') == '1'
    
    if not start_date or not end_date:
        return jsonify({'success': False, 'error': 'Missing date range'}), 400
    
    start_ts = int(datetime.strptime(start_date, '%Y-%m-%d').timestamp())
    end_ts = int(datetime.strptime(end_date + ' 23:59:59', '%Y-%m-%d %H:%M:%S').timestamp())
    
    # Client mode: Payment Record for one client. Details ARE the point,
    # so force them on; attachments are suppressed inside the generator.
    client = None
    if client_id:
        c = db.get_client(client_id)
        if not c:
            return jsonify({'success': False, 'error': 'Client not found'}), 404
        client = {
            'id': c['id'],
            'file_number': c['file_number'],
            'name': f"{c['last_name']}, {c['first_name']}",
        }
        include_details = True
        filename = f"Payment_Record_{c['file_number']}_{start_date}_to_{end_date}.pdf"
    else:
        filename = f"Financial_Report_{start_date}_to_{end_date}.pdf"
    # Private (0700, randomized) dir: this PDF holds PHI in the clear and
    # must not sit in the shared temp dir under a predictable name. Removed
    # once the response has been sent; the browser still sees `filename`
    # via send_file's download_name.
    output_path = private_pdf_dir() / filename
    
    try:
        generate_ledger_report_pdf(
            db=db,
            start_ts=start_ts,
            end_ts=end_ts,
            output_path=str(output_path),
            include_details=include_details,
            include_taxes=include_taxes,
            include_attachments=include_attachments,
            start_date_str=start_date,
            end_date_str=end_date,
            client=client
        )
        
        @after_this_request
        def cleanup(response):
            shutil.rmtree(output_path.parent, ignore_errors=True)
            return response
        
        return send_file(
            output_path,
            mimetype='application/pdf',
            as_attachment=False,
            download_name=filename
        )
    except Exception as e:
        shutil.rmtree(output_path.parent, ignore_errors=True)
        return jsonify({'success': False, 'error': str(e)}), 500
