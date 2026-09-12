"""Statements index / outstanding view.

Extracted from the statements.py blueprint split.
"""
from flask import render_template
from datetime import datetime, timedelta
from core.money import dec, money_float
from web.blueprints.statements.common import statements_bp, get_db


@statements_bp.route('/')
def outstanding_statements():
    """Display statement generation and outstanding statements."""
    db = get_db()
    
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
        portion['amount_owing'] = money_float(
            dec(portion['amount_due']) - dec(portion['amount_paid']))
        
        # Format dates
        if portion['statement_date']:
            portion['date_display'] = datetime.fromtimestamp(
                portion['statement_date']
            ).strftime('%Y-%m-%d')
        else:
            portion['date_display'] = ''
        
        portions.append(portion)
    
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
