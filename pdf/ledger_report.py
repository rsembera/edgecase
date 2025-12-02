"""
Ledger Report PDF Generator

Generates income and expense reports for tax filing.
"""

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from datetime import datetime


def generate_ledger_report_pdf(db, start_ts, end_ts, output_path, include_details=True, 
                                start_date_str='', end_date_str=''):
    """
    Generate a PDF financial report.
    
    Args:
        db: Database instance
        start_ts: Start timestamp
        end_ts: End timestamp  
        output_path: Where to save the PDF
        include_details: Whether to include transaction detail pages
        start_date_str: Start date string for display
        end_date_str: End date string for display
    """
    
    # Get practice info
    practice_name = db.get_setting('practice_name', 'Practice Name')
    
    # Fetch all data
    conn = db.connect()
    cursor = conn.cursor()
    
    # Get income entries
    cursor.execute("""
        SELECT ledger_date, total_amount, source, description
        FROM entries
        WHERE class = 'income' AND ledger_type = 'income'
        AND ledger_date >= ? AND ledger_date <= ?
        ORDER BY ledger_date
    """, (start_ts, end_ts))
    income_entries = cursor.fetchall()
    
    # Get expense entries with category names and payee names
    cursor.execute("""
        SELECT e.ledger_date, e.total_amount, e.description, ec.name as category, p.name as payee_name
        FROM entries e
        LEFT JOIN expense_categories ec ON e.category_id = ec.id
        LEFT JOIN payees p ON e.payee_id = p.id
        WHERE e.class = 'expense' AND e.ledger_type = 'expense'
        AND e.ledger_date >= ? AND e.ledger_date <= ?
        ORDER BY e.ledger_date
    """, (start_ts, end_ts))
    expense_entries = cursor.fetchall()
    
    # Get category totals
    cursor.execute("""
        SELECT ec.name, COALESCE(SUM(e.total_amount), 0) as total
        FROM entries e
        LEFT JOIN expense_categories ec ON e.category_id = ec.id
        WHERE e.class = 'expense' AND e.ledger_type = 'expense'
        AND e.ledger_date >= ? AND e.ledger_date <= ?
        GROUP BY e.category_id
        ORDER BY ec.name
    """, (start_ts, end_ts))
    category_totals = cursor.fetchall()
    
    
    # Calculate totals
    total_income = sum(e[1] for e in income_entries) if income_entries else 0
    total_expenses = sum(e[1] for e in expense_entries) if expense_entries else 0
    
    # Create document
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        rightMargin=0.75*inch,
        leftMargin=0.75*inch,
        topMargin=0.75*inch,
        bottomMargin=0.75*inch
    )
    
    # Styles
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'Title',
        parent=styles['Heading1'],
        fontSize=16,
        alignment=TA_CENTER,
        spaceAfter=6
    )
    
    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Normal'],
        fontSize=11,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#64748B'),
        spaceAfter=20
    )
    
    section_style = ParagraphStyle(
        'Section',
        parent=styles['Heading2'],
        fontSize=12,
        spaceBefore=20,
        spaceAfter=10,
        textColor=colors.HexColor('#1E293B')
    )
    
    # Build content
    story = []
    
    # Title
    story.append(Paragraph(practice_name.upper(), title_style))
    
    # Format date range for display
    start_dt = datetime.strptime(start_date_str, '%Y-%m-%d')
    end_dt = datetime.strptime(end_date_str, '%Y-%m-%d')
    date_range = f"INCOME AND EXPENSE RECORD ({start_dt.strftime('%b %d, %Y')} - {end_dt.strftime('%b %d, %Y')})"
    story.append(Paragraph(date_range, subtitle_style))
    
    # Transaction Details (if requested)
    if include_details:
        story.append(Paragraph("Transaction Details", section_style))
        
        # Combine income and expenses into one list, sorted by date
        all_transactions = []
        
        for entry in income_entries:
            all_transactions.append({
                'date': entry[0],
                'income': entry[1],
                'expense': None,
                'description': entry[3] or '',  # description field
                'payor_payee': entry[2] or '',  # source field (who paid)
                'category': ''
            })
        
        for entry in expense_entries:
            all_transactions.append({
                'date': entry[0],
                'income': None,
                'expense': entry[1],
                'description': entry[2] or '',  # description field
                'payor_payee': entry[4] or '',  # payee_name (who was paid)
                'category': entry[3] or 'Uncategorized'
            })
        
        # Sort by date
        all_transactions.sort(key=lambda x: x['date'])
        
        # Build table - 6 columns
        table_data = [['Date', 'Income', 'Expense', 'Description', 'Payor/Payee', 'Category']]
        
        for t in all_transactions:
            date_str = datetime.fromtimestamp(t['date']).strftime('%d-%b')
            income_str = f"$ {t['income']:,.2f}" if t['income'] else ''
            expense_str = f"$ {t['expense']:,.2f}" if t['expense'] else ''
            desc = t['description'][:30] + ('...' if len(t['description']) > 30 else '')
            payor_payee = t['payor_payee'][:25] + ('...' if len(t['payor_payee']) > 25 else '')
            category = t['category'][:20] + ('...' if len(t['category']) > 20 else '')
            
            table_data.append([
                date_str,
                income_str,
                expense_str,
                desc,
                payor_payee,
                category
            ])
        
        # Add totals row
        table_data.append([
            'TOTALS',
            f"$ {total_income:,.2f}",
            f"$ {total_expenses:,.2f}",
            '',
            '',
            ''
        ])
        
        # Create table - 6 columns
        # Date | Income | Expense | Description | Payor/Payee | Category
        col_widths = [0.6*inch, 0.85*inch, 0.85*inch, 1.8*inch, 1.5*inch, 1.4*inch]
        
        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        
        # First setStyle: Everything EXCEPT left padding
        table.setStyle(TableStyle([
            # Header
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F1F5F9')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#475569')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 5),
            ('TOPPADDING', (0, 0), (-1, 0), 5),
            
            # Body
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('TOPPADDING', (0, 1), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 2),
            
            # Totals row
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#F8FAFC')),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('LINEABOVE', (0, -1), (-1, -1), 1, colors.HexColor('#CBD5E1')),
            
            # Alignment
            ('ALIGN', (1, 0), (2, -1), 'RIGHT'),  # Income, Expense right-aligned
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),   # Date left-aligned
            ('ALIGN', (3, 1), (3, -1), 'LEFT'),   # Description left-aligned
            ('ALIGN', (4, 1), (4, -1), 'LEFT'),   # Payor/Payee left-aligned
            ('ALIGN', (5, 1), (5, -1), 'LEFT'),   # Category left-aligned
            
            # Grid
            ('LINEBELOW', (0, 0), (-1, 0), 1, colors.HexColor('#CBD5E1')),
            ('LINEBELOW', (0, 1), (-1, -2), 0.5, colors.HexColor('#E2E8F0')),
            
            # Borders
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#CBD5E1')),
            
            # Right padding for all
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        
        # Second setStyle: Default left padding
        table.setStyle(TableStyle([
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ]))
        
        # Third setStyle: Override Description, Payor/Payee, and Category columns with larger padding
        table.setStyle(TableStyle([
            ('LEFTPADDING', (3, 0), (3, -1), 30),  # Description column
            ('LEFTPADDING', (4, 0), (4, -1), 30),  # Payor/Payee column
            ('LEFTPADDING', (5, 0), (5, -1), 30),  # Category column
        ]))
        
        story.append(table)
        story.append(Spacer(1, 30))
    
    # Category Summary (always included) - wrapped in KeepTogether
    summary_elements = []
    
    summary_elements.append(Paragraph("Expense Summary by Category", section_style))
    
    summary_data = [['Expense Category', 'Total Amount']]
    
    for cat in category_totals:
        cat_name = cat[0] or 'Uncategorized'
        cat_total = cat[1]
        summary_data.append([cat_name, f"$ {cat_total:,.2f}"])
    
    # Add total row
    summary_data.append(['TOTAL', f"$ {total_expenses:,.2f}"])
    
    summary_table = Table(summary_data, colWidths=[4*inch, 2*inch])
    summary_table.setStyle(TableStyle([
        # Header
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F1F5F9')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#475569')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('TOPPADDING', (0, 0), (-1, 0), 10),
        
        # Body
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('TOPPADDING', (0, 1), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        
        # Totals row
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#F8FAFC')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('LINEABOVE', (0, -1), (-1, -1), 1, colors.HexColor('#CBD5E1')),
        
        # Alignment
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        
        # Grid
        ('LINEBELOW', (0, 0), (-1, 0), 1, colors.HexColor('#CBD5E1')),
        ('LINEBELOW', (0, 1), (-1, -2), 0.5, colors.HexColor('#E2E8F0')),
        
        # Borders
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#CBD5E1')),
    ]))
    
    summary_elements.append(summary_table)
    
    # Net Income Summary
    summary_elements.append(Spacer(1, 20))
    
    net_income = total_income - total_expenses
    
    net_data = [
        ['Total Income', f"$ {total_income:,.2f}"],
        ['Total Expenses', f"$ {total_expenses:,.2f}"],
        ['Net Income', f"$ {net_income:,.2f}"]
    ]
    
    net_table = Table(net_data, colWidths=[4*inch, 2*inch])
    net_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        
        # Net income row
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, -1), (-1, -1), 11),
        ('LINEABOVE', (0, -1), (-1, -1), 1, colors.HexColor('#CBD5E1')),
        ('TOPPADDING', (0, -1), (-1, -1), 10),
        
        # Colors for income/expense
        ('TEXTCOLOR', (1, 0), (1, 0), colors.HexColor('#059669')),  # Income green
        ('TEXTCOLOR', (1, 1), (1, 1), colors.HexColor('#DC2626')),  # Expense red
        ('TEXTCOLOR', (1, 2), (1, 2), colors.HexColor('#059669') if net_income >= 0 else colors.HexColor('#DC2626')),
        
        # Alignment
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
    ]))
    
    summary_elements.append(net_table)
    
    # Add all summary elements wrapped in KeepTogether
    story.append(KeepTogether(summary_elements))
    
    # Build PDF
    doc.build(story)
