# -*- coding: utf-8 -*-
"""
EdgeCase Ledger Blueprint
Handles income and expense tracking
"""

from flask import Blueprint, render_template, request, redirect, url_for, jsonify, send_file
from web.utils import parse_date_from_form, get_today_date_parts, save_uploaded_files
from datetime import datetime
from werkzeug.utils import secure_filename
import sqlcipher3 as sqlite3
import os
import shutil
import time
from core.database import Database
import tempfile
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
    
    # Get all ledger entries
    entries = db.get_all_ledger_entries()
    
    # Get currency code from settings
    currency = db.get_setting('currency', 'CAD')
    
    # Calculate YTD and MTD stats
    now = datetime.now()
    current_year = now.year
    current_month = now.month
    
    ytd_income = 0
    ytd_expenses = 0
    mtd_income = 0
    mtd_expenses = 0
    ytd_expenses_by_category = {}
    
    # Organize entries by year and month
    entries_by_year_month = {}
    
    for entry in entries:
        if entry.get('ledger_date'):
            entry_dt = datetime.fromtimestamp(entry['ledger_date'])
            year = entry_dt.year
            month = entry_dt.month
            month_name = entry_dt.strftime('%B')  # "November"
            amount = entry.get('total_amount', 0) or 0
            
            # YTD calculations
            if year == current_year:
                if entry['ledger_type'] == 'income':
                    ytd_income += amount
                elif entry['ledger_type'] == 'expense':
                    ytd_expenses += amount
                    # Track by category
                    cat_id = entry.get('category_id')
                    if cat_id:
                        if cat_id not in ytd_expenses_by_category:
                            ytd_expenses_by_category[cat_id] = 0
                        ytd_expenses_by_category[cat_id] += amount
            
            # MTD calculations
            if year == current_year and month == current_month:
                if entry['ledger_type'] == 'income':
                    mtd_income += amount
                elif entry['ledger_type'] == 'expense':
                    mtd_expenses += amount
            
            # Organize by year/month
            if year not in entries_by_year_month:
                entries_by_year_month[year] = {}
            
            if month not in entries_by_year_month[year]:
                entries_by_year_month[year][month] = {
                    'name': month_name,
                    'entries': []
                }
            
            # Get payee and category names for expenses
            if entry['ledger_type'] == 'expense':
                if entry.get('payee_id'):
                    payee = db.get_payee(entry['payee_id'])
                    entry['payee_name'] = payee['name'] if payee else 'Unknown'
                
                if entry.get('category_id'):
                    category = db.get_expense_category(entry['category_id'])
                    entry['category_name'] = category['name'] if category else 'Unknown'
            
            entries_by_year_month[year][month]['entries'].append(entry)
    
    # Calculate net
    ytd_net = ytd_income - ytd_expenses
    mtd_net = mtd_income - mtd_expenses
    
    # Get category names for YTD breakdown
    ytd_category_breakdown = []
    for cat_id, amount in sorted(ytd_expenses_by_category.items(), key=lambda x: x[1], reverse=True):
        category = db.get_expense_category(cat_id)
        if category:
            ytd_category_breakdown.append({
                'name': category['name'],
                'amount': amount
            })
    
    # Sort years (newest first) and months (newest first within year)
    years = sorted(entries_by_year_month.keys(), reverse=True)
    for year in years:
        entries_by_year_month[year] = dict(
            sorted(entries_by_year_month[year].items(), reverse=True)
        )
        
    # Sort years (newest first) and months (newest first within year)
    years = sorted(entries_by_year_month.keys(), reverse=True)
    for year in years:
        entries_by_year_month[year] = dict(
            sorted(entries_by_year_month[year].items(), reverse=True)
        )
    
    # Sort entries within each month by date DESC, then created_at DESC
    for year in entries_by_year_month:
        for month in entries_by_year_month[year]:
            entries_by_year_month[year][month]['entries'].sort(
                key=lambda e: (e.get('ledger_date', 0), e.get('created_at', 0)),
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
        # Parse date from dropdowns
        ledger_date_timestamp = parse_date_from_form(request.form)
        
        # Prepare income entry data
        income_data = {
            'client_id': None,  # Ledger entries are not tied to clients
            'class': 'income',
            'ledger_type': 'income',
            'ledger_date': ledger_date_timestamp,
            'source': request.form.get('source'),
            'total_amount': float(request.form.get('total_amount', 0)),
            'tax_amount': float(request.form.get('tax_amount') or 0),
            'description': request.form.get('description', ''),
            'content': request.form.get('content', '')
        }
        
        # Save income entry first to get entry_id
        entry_id = db.add_entry(income_data)
        
        # Handle file uploads
        files = request.files.getlist('files[]')
        descriptions = request.form.getlist('file_descriptions[]')
        save_uploaded_files(files, descriptions, entry_id, db)
        
        return redirect(url_for('ledger.ledger'))
    
    # GET - show form
    date_parts = get_today_date_parts()
    
    currency = db.get_setting('currency', '$')
    
    return render_template('entry_forms/income.html',
                         **date_parts,
                         currency=currency,
                         is_edit=False)

@ledger_bp.route('/ledger/income/<int:entry_id>', methods=['GET', 'POST'])
def edit_income(entry_id):
    """Edit existing income entry."""
    income = db.get_entry(entry_id)
    
    if not income or income['ledger_type'] != 'income':
        return "Income entry not found", 404
    
    if request.method == 'POST':
        # Parse date from dropdowns
        ledger_date_timestamp = parse_date_from_form(request.form)
        
        # Prepare updated income data
        income_data = {
            'ledger_date': ledger_date_timestamp,
            'source': request.form.get('source'),
            'total_amount': float(request.form.get('total_amount', 0)),
            'tax_amount': float(request.form.get('tax_amount') or 0),
            'description': request.form.get('description', ''),
            'content': request.form.get('content', '')
        }
        
        # Handle new file uploads
        files = request.files.getlist('files[]')
        descriptions = request.form.getlist('file_descriptions[]')
        
        save_uploaded_files(files, descriptions, entry_id, db)
        
        # Update the income entry
        db.update_entry(entry_id, income_data)
        
        return redirect(url_for('ledger.ledger'))
    
    # GET - show form with existing data
    # Parse income date into year, month, day for dropdowns
    income_year = None
    income_month = None
    income_day = None
    if income.get('ledger_date'):
        income_dt = datetime.fromtimestamp(income['ledger_date'])
        income_year = income_dt.year
        income_month = income_dt.month
        income_day = income_dt.day
    
    # Get attachments for this entry
    attachments = db.get_attachments(entry_id)
    
    currency = db.get_setting('currency', '$')
    
    return render_template('entry_forms/income.html',
                         entry=income,
                         income_year=income_year,
                         income_month=income_month,
                         income_day=income_day,
                         attachments=attachments,
                         currency=currency,
                         is_edit=True)


@ledger_bp.route('/ledger/income/<int:entry_id>/delete', methods=['POST'])
def delete_income_entry(entry_id):
    """Delete income entry and all its attachments."""
    
    # Get the entry
    entry = db.get_entry(entry_id)
    
    if not entry or entry['ledger_type'] != 'income':
        return "Income entry not found", 404
    
    try:
        # Delete attachments from disk first
        upload_dir = os.path.expanduser(f'~/edgecase/attachments/ledger/{entry_id}')
        if os.path.exists(upload_dir):
            shutil.rmtree(upload_dir)
        
        # Delete attachment records from database
        conn = db.connect()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM attachments WHERE entry_id = ?", (entry_id,))
        
        # Delete the entry itself
        cursor.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
        
        conn.commit()
        conn.close()
        
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
        # Handle new payee creation
        payee_id = request.form.get('payee_id')
        if payee_id == 'new':
            new_payee_name = request.form.get('new_payee_name')
            if new_payee_name:
                payee_id = db.add_payee(new_payee_name)
        else:
            payee_id = int(payee_id)
        
        # Handle new category creation
        category_id = request.form.get('category_id')
        if category_id == 'new':
            new_category_name = request.form.get('new_category_name')
            if new_category_name:
                category_id = db.add_expense_category(new_category_name)
        else:
            category_id = int(category_id)
        
        # Parse date from dropdowns
        ledger_date_timestamp = parse_date_from_form(request.form)
        
        # Prepare expense entry data
        expense_data = {
            'client_id': None,  # Ledger entries are not tied to clients
            'class': 'expense',
            'ledger_type': 'expense',
            'ledger_date': ledger_date_timestamp,
            'payee_id': payee_id,
            'category_id': category_id,
            'total_amount': float(request.form.get('total_amount', 0)),
            'tax_amount': float(request.form.get('tax_amount') or 0),
            'description': request.form.get('description', ''),
            'content': request.form.get('content', '')
        }
        
        # Save expense entry first to get entry_id
        entry_id = db.add_entry(expense_data)
        
        # Handle file uploads
        files = request.files.getlist('files[]')
        descriptions = request.form.getlist('file_descriptions[]')
        
        save_uploaded_files(files, descriptions, entry_id, db)
        
        return redirect(url_for('ledger.ledger'))
    
    # GET - show form
    date_parts = get_today_date_parts()
    
    # Get payees and categories for dropdowns
    payees = db.get_all_payees()
    categories = db.get_all_expense_categories()
    
    currency = db.get_setting('currency', '$')
    
    return render_template('entry_forms/expense.html',
                         **date_parts,
                         payees=payees,
                         categories=categories,
                         currency=currency,
                         is_edit=False)


@ledger_bp.route('/ledger/expense/<int:entry_id>', methods=['GET', 'POST'])
def edit_expense(entry_id):
    """Edit existing expense entry."""
    expense = db.get_entry(entry_id)
    
    if not expense or expense['ledger_type'] != 'expense':
        return "Expense entry not found", 404
    
    if request.method == 'POST':
        # Handle new payee creation
        payee_id = request.form.get('payee_id')
        if payee_id == 'new':
            new_payee_name = request.form.get('new_payee_name')
            if new_payee_name:
                payee_id = db.add_payee(new_payee_name)
        else:
            payee_id = int(payee_id)
        
        # Handle new category creation
        category_id = request.form.get('category_id')
        if category_id == 'new':
            new_category_name = request.form.get('new_category_name')
            if new_category_name:
                category_id = db.add_expense_category(new_category_name)
        else:
            category_id = int(category_id)
        
        # Parse date from dropdowns
        ledger_date_timestamp = parse_date_from_form(request.form)
        
        # Prepare updated expense data
        expense_data = {
            'ledger_date': ledger_date_timestamp,
            'payee_id': payee_id,
            'category_id': category_id,
            'total_amount': float(request.form.get('total_amount', 0)),
            'tax_amount': float(request.form.get('tax_amount') or 0),
            'description': request.form.get('description', ''),
            'content': request.form.get('content', '')
        }
        
        # Handle new file uploads
        files = request.files.getlist('files[]')
        descriptions = request.form.getlist('file_descriptions[]')
        
        save_uploaded_files(files, descriptions, entry_id, db)
        
        # Update the expense entry
        db.update_entry(entry_id, expense_data)
        
        return redirect(url_for('ledger.ledger'))
    
    # GET - show form with existing data
    # Parse expense date into year, month, day for dropdowns
    expense_year = None
    expense_month = None
    expense_day = None
    if expense.get('ledger_date'):
        expense_dt = datetime.fromtimestamp(expense['ledger_date'])
        expense_year = expense_dt.year
        expense_month = expense_dt.month
        expense_day = expense_dt.day
    
    # Get payees and categories for dropdowns
    payees = db.get_all_payees()
    categories = db.get_all_expense_categories()
    
    # Get attachments for this entry
    attachments = db.get_attachments(entry_id)
    
    currency = db.get_setting('currency', '$')
    
    return render_template('entry_forms/expense.html',
                         entry=expense,
                         expense_year=expense_year,
                         expense_month=expense_month,
                         expense_day=expense_day,
                         payees=payees,
                         categories=categories,
                         attachments=attachments,
                         currency=currency,
                         is_edit=True)


@ledger_bp.route('/ledger/expense/<int:entry_id>/delete', methods=['POST'])
def delete_expense_entry(entry_id):
    """Delete expense entry and all its attachments."""
    
    # Get the entry
    entry = db.get_entry(entry_id)
    
    if not entry or entry['ledger_type'] != 'expense':
        return "Expense entry not found", 404
    
    try:
        # Delete attachments from disk first
        upload_dir = os.path.expanduser(f'~/edgecase/attachments/ledger/{entry_id}')
        if os.path.exists(upload_dir):
            shutil.rmtree(upload_dir)
        
        # Delete attachment records from database
        conn = db.connect()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM attachments WHERE entry_id = ?", (entry_id,))
        
        # Delete the entry itself
        cursor.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
        
        conn.commit()
        conn.close()
        
        return "", 200
    
    except Exception as e:
        print(f"Error deleting expense entry: {e}")
        return f"Error: {str(e)}", 500
    
# ============================================
# REPORTS
# ============================================

@ledger_bp.route('/ledger/report')
def ledger_report():
    """Display the financial report generator page."""
    from datetime import datetime
    
    # Default to current year
    now = datetime.now()
    
    return render_template('ledger_report.html',
        default_start_year=now.year,
        default_start_month=1,
        default_start_day=1,
        default_end_year=now.year,
        default_end_month=now.month,
        default_end_day=now.day
    )


@ledger_bp.route('/ledger/report/calculate')
def calculate_report():
    """Calculate totals for preview without generating PDF."""
    from datetime import datetime
    
    start_date = request.args.get('start')
    end_date = request.args.get('end')
    
    if not start_date or not end_date:
        return jsonify({'success': False, 'error': 'Missing date range'}), 400
    
    # Convert to timestamps
    start_ts = int(datetime.strptime(start_date, '%Y-%m-%d').timestamp())
    end_ts = int(datetime.strptime(end_date + ' 23:59:59', '%Y-%m-%d %H:%M:%S').timestamp())
    
    conn = db.connect()
    cursor = conn.cursor()
    
    # Get total income
    cursor.execute("""
        SELECT COALESCE(SUM(total_amount), 0) as total
        FROM entries
        WHERE class = 'income' AND ledger_type = 'income'
        AND ledger_date >= ? AND ledger_date <= ?
    """, (start_ts, end_ts))
    total_income = cursor.fetchone()[0] or 0
    
    # Get total expenses
    cursor.execute("""
        SELECT COALESCE(SUM(total_amount), 0) as total
        FROM entries
        WHERE class = 'expense' AND ledger_type = 'expense'
        AND ledger_date >= ? AND ledger_date <= ?
    """, (start_ts, end_ts))
    total_expenses = cursor.fetchone()[0] or 0
    
    # Get expenses by category
    cursor.execute("""
        SELECT ec.name, COALESCE(SUM(e.total_amount), 0) as total
        FROM entries e
        LEFT JOIN expense_categories ec ON e.category_id = ec.id
        WHERE e.class = 'expense' AND e.ledger_type = 'expense'
        AND e.ledger_date >= ? AND e.ledger_date <= ?
        GROUP BY e.category_id
        ORDER BY ec.name
    """, (start_ts, end_ts))
    
    categories = []
    for row in cursor.fetchall():
        categories.append({
            'name': row[0] or 'Uncategorized',
            'total': row[1]
        })
    
    conn.close()
    
    return jsonify({
        'success': True,
        'total_income': total_income,
        'total_expenses': total_expenses,
        'net_income': total_income - total_expenses,
        'categories': categories
    })


@ledger_bp.route('/ledger/report/pdf')
def generate_report_pdf():
    """Generate the PDF financial report."""
    from datetime import datetime
    from pdf.ledger_report import generate_ledger_report_pdf
    import tempfile
    from pathlib import Path
    
    start_date = request.args.get('start')
    end_date = request.args.get('end')
    include_details = request.args.get('details') == '1'
    
    if not start_date or not end_date:
        return jsonify({'success': False, 'error': 'Missing date range'}), 400
    
    # Convert to timestamps
    start_ts = int(datetime.strptime(start_date, '%Y-%m-%d').timestamp())
    end_ts = int(datetime.strptime(end_date + ' 23:59:59', '%Y-%m-%d %H:%M:%S').timestamp())
    
    # Generate filename
    filename = f"Financial_Report_{start_date}_to_{end_date}.pdf"
    
    # Create PDF in temp directory
    temp_dir = tempfile.gettempdir()
    output_path = Path(temp_dir) / filename
    
    try:
        generate_ledger_report_pdf(
            db=db,
            start_ts=start_ts,
            end_ts=end_ts,
            output_path=str(output_path),
            include_details=include_details,
            start_date_str=start_date,
            end_date_str=end_date
        )
        
        return send_file(
            output_path,
            mimetype='application/pdf',
            as_attachment=False,
            download_name=filename
        )
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500