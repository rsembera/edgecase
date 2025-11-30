"""
PDF Statement Generator for EdgeCase Equalizer

Generates professional invoice/statement PDFs using ReportLab.
"""

import os
import re
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, HRFlowable
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER


class StatementPDFGenerator:
    """Generates PDF statements/invoices."""
    
    def __init__(self, db):
        self.db = db
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()
        
    def _setup_custom_styles(self):
        """Create custom paragraph styles."""
        # Header - therapist name with credentials
        self.styles.add(ParagraphStyle(
            name='TherapistName',
            parent=self.styles['Normal'],
            fontSize=12,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor('#D4A04A'),  # Golden color like your sample
            spaceAfter=2,
            alignment=TA_RIGHT
        ))
        
        # Header info lines
        self.styles.add(ParagraphStyle(
            name='HeaderInfo',
            parent=self.styles['Normal'],
            fontSize=9,
            fontName='Helvetica',
            textColor=colors.HexColor('#333333'),
            spaceAfter=1,
            alignment=TA_RIGHT
        ))
        
        # Bill To name
        self.styles.add(ParagraphStyle(
            name='BillToName',
            parent=self.styles['Normal'],
            fontSize=11,
            fontName='Helvetica-Bold',
            spaceAfter=2
        ))
        
        # Bill To address
        self.styles.add(ParagraphStyle(
            name='BillToAddress',
            parent=self.styles['Normal'],
            fontSize=10,
            fontName='Helvetica',
            spaceAfter=1
        ))
        
        # Attestation text - left aligned to match table
        self.styles.add(ParagraphStyle(
            name='Attestation',
            parent=self.styles['Normal'],
            fontSize=10,
            fontName='Helvetica',
            spaceBefore=20,
            spaceAfter=15,
            alignment=TA_LEFT
        ))
        
        # Payment instructions (italic with non-italic emails handled inline)
        self.styles.add(ParagraphStyle(
            name='PaymentInstructions',
            parent=self.styles['Normal'],
            fontSize=10,
            fontName='Helvetica-Oblique',
            textColor=colors.HexColor('#333333'),
            alignment=TA_CENTER,
            spaceBefore=15
        ))
        
        # Signature label
        self.styles.add(ParagraphStyle(
            name='SignatureLabel',
            parent=self.styles['Normal'],
            fontSize=9,
            fontName='Helvetica',
            textColor=colors.HexColor('#666666')
        ))
        
        # Date label (for alignment)
        self.styles.add(ParagraphStyle(
            name='DateLabel',
            parent=self.styles['Normal'],
            fontSize=9,
            fontName='Helvetica',
            textColor=colors.HexColor('#666666'),
            alignment=TA_LEFT
        ))
    
    def _get_settings(self):
        """Get all relevant settings for the statement."""
        return {
            'practice_name': self.db.get_setting('practice_name', ''),
            'therapist_name': self.db.get_setting('therapist_name', ''),
            'credentials': self.db.get_setting('credentials', ''),
            'registration_info': self.db.get_setting('registration_info', ''),
            'address': self.db.get_setting('address', ''),
            'phone': self.db.get_setting('phone', ''),
            'website': self.db.get_setting('website', ''),
            'email': self.db.get_setting('email', ''),
            'payment_instructions': self.db.get_setting('payment_instructions', ''),
            'include_attestation': self.db.get_setting('include_attestation', 'true') == 'true',
            'attestation_text': self.db.get_setting('attestation_text', 
                'I attest that I have performed the services listed above.'),
            'currency': self.db.get_setting('currency', 'CAD'),
            'logo_filename': self.db.get_setting('logo_filename', ''),
            'signature_filename': self.db.get_setting('signature_filename', '')
        }
    
    def _get_currency_symbol(self, currency_code):
        """Convert currency code to symbol."""
        symbols = {
            'CAD': '$', 'USD': '$', 'EUR': '€', 'GBP': '£',
            'AUD': '$', 'NZD': '$', 'JPY': '¥', 'CNY': '¥',
            'INR': '₹', 'MXN': '$', 'BRL': 'R$', 'CHF': 'CHF'
        }
        return symbols.get(currency_code, '$')
    
    def _format_currency(self, amount, currency_code):
        """Format amount with currency symbol."""
        symbol = self._get_currency_symbol(currency_code)
        if amount is None:
            amount = 0
        return f"{symbol}{amount:,.2f}"
    
    def _format_payment_instructions(self, text):
        """Format payment instructions with emails in non-italic.
        
        Detects email addresses and wraps them to appear non-italic
        while the rest of the text is italic.
        """
        if not text:
            return ''
        
        # Email regex pattern
        email_pattern = r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'
        
        # Split text by emails, keeping the emails
        parts = re.split(email_pattern, text)
        
        # Build formatted string - emails get wrapped in </i><font>...</font><i>
        # But since we're using Helvetica-Oblique as the font, we need to use
        # inline font tags to switch to regular Helvetica for emails
        formatted_parts = []
        for i, part in enumerate(parts):
            if re.match(email_pattern, part):
                # This is an email - use regular (non-italic) font
                formatted_parts.append(f'</i><font face="Helvetica">{part}</font><i>')
            else:
                formatted_parts.append(part)
        
        # Wrap the whole thing in italic tags for Paragraph
        return '<i>' + ''.join(formatted_parts) + '</i>'
    
    def _get_bill_to_info(self, client, profile, guardian_number=None):
        """Get billing recipient name and address.
        
        Args:
            client: Client record
            profile: Profile entry
            guardian_number: 1 or 2 if billing a guardian, None for client
            
        Returns:
            dict with 'name' and 'address'
        """
        if guardian_number == 1 and profile:
            return {
                'name': profile.get('guardian1_name', '') or f"{client['first_name']} {client['last_name']}",
                'address': profile.get('guardian1_address', '') or profile.get('address', '')
            }
        elif guardian_number == 2 and profile:
            return {
                'name': profile.get('guardian2_name', '') or f"{client['first_name']} {client['last_name']}",
                'address': profile.get('guardian2_address', '') or profile.get('address', '')
            }
        else:
            # Bill the client directly
            name_parts = [client.get('first_name', '')]
            if client.get('middle_name'):
                name_parts.append(client['middle_name'])
            name_parts.append(client.get('last_name', ''))
            
            return {
                'name': ' '.join(name_parts),
                'address': profile.get('address', '') if profile else ''
            }
    
    def _scale_image_to_fit(self, img, target_width, target_height):
        """Scale an image to fit within target dimensions, scaling UP or DOWN as needed.
        
        Args:
            img: ReportLab Image object
            target_width: Target width in points
            target_height: Target height in points
            
        Returns:
            Image with drawWidth and drawHeight set
        """
        orig_width = img.imageWidth
        orig_height = img.imageHeight
        
        # Calculate scale factors for both dimensions
        width_scale = target_width / orig_width
        height_scale = target_height / orig_height
        
        # Use the smaller scale to ensure image fits within bounds
        scale = min(width_scale, height_scale)
        
        img.drawWidth = orig_width * scale
        img.drawHeight = orig_height * scale
        
        return img
    
    def _build_header(self, settings, assets_path):
        """Build the header section with logo and practice info."""
        elements = []
        
        # Check for logo
        logo_path = None
        if settings['logo_filename']:
            logo_path = os.path.join(assets_path, settings['logo_filename'])
            if not os.path.exists(logo_path):
                logo_path = None
        
        # Build practice info paragraphs
        info_parts = []
        
        # Therapist name with credentials
        name_line = settings['therapist_name']
        if settings['credentials']:
            name_line += f", {settings['credentials']}"
        if name_line:
            info_parts.append(Paragraph(name_line, self.styles['TherapistName']))
        
        # Registration info
        if settings['registration_info']:
            info_parts.append(Paragraph(settings['registration_info'], self.styles['HeaderInfo']))
        
        # Address - preserve line breaks
        if settings['address']:
            # Replace newlines with <br/> for ReportLab
            address_html = settings['address'].replace('\n', '<br/>')
            info_parts.append(Paragraph(address_html, self.styles['HeaderInfo']))
        
        # Phone and website on same line
        contact_line = []
        if settings['phone']:
            contact_line.append(settings['phone'])
        if settings['website']:
            contact_line.append(settings['website'])
        if contact_line:
            info_parts.append(Paragraph(' | '.join(contact_line), self.styles['HeaderInfo']))
        
        # Create the header layout
        if logo_path:
            try:
                # Logo exists - create two-column layout
                logo = Image(logo_path)
                # Scale logo to fit target size (will scale up or down)
                # Sized to roughly match the height of the address block
                logo = self._scale_image_to_fit(logo, 2.2 * inch, 1.5 * inch)
                
                # Create table with logo and info - info column wider, flush right
                header_data = [[logo, info_parts]]
                header_table = Table(header_data, colWidths=[2.8*inch, 4.2*inch])
                header_table.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('ALIGN', (0, 0), (0, 0), 'LEFT'),
                    ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
                    ('RIGHTPADDING', (1, 0), (1, 0), 0),  # No right padding - flush to margin
                ]))
                elements.append(header_table)
            except Exception:
                # If logo fails to load, just use text
                for p in info_parts:
                    elements.append(p)
        else:
            # No logo - just the info, right-aligned
            for p in info_parts:
                elements.append(p)
        
        elements.append(Spacer(1, 0.4*inch))
        return elements
    
    def _build_bill_to(self, bill_to_info):
        """Build the 'Bill To' section."""
        elements = []
        
        if bill_to_info['name']:
            elements.append(Paragraph(bill_to_info['name'], self.styles['BillToName']))
        
        if bill_to_info['address']:
            # Split address by newlines if present
            for line in bill_to_info['address'].split('\n'):
                if line.strip():
                    elements.append(Paragraph(line.strip(), self.styles['BillToAddress']))
        
        elements.append(Spacer(1, 0.3*inch))
        return elements
    
    def _build_line_items_table(self, entries, currency_code):
        """Build the table of billable line items."""
        # Table header
        data = [['Date', 'Service', 'Duration', 'Fee']]
        
        total = 0
        for entry in entries:
            # Get date based on entry type
            entry_class = entry.get('class', '')
            if entry_class == 'session':
                date_ts = entry.get('session_date', 0)
                service = entry.get('service', 'Session')
                duration = entry.get('duration', 0)
                duration_str = f"{duration} mins." if duration else ''
                fee = entry.get('fee', 0) or 0
            elif entry_class == 'absence':
                date_ts = entry.get('absence_date', 0)
                service = entry.get('description', 'Absence')
                duration_str = '—'
                fee = entry.get('fee', 0) or 0
            elif entry_class == 'item':
                date_ts = entry.get('item_date', 0)
                service = entry.get('description', 'Item')
                duration_str = '—'
                fee = entry.get('fee', 0) or 0
            else:
                continue
            
            # Format date as YYYY-MM-DD
            if date_ts:
                date_str = datetime.fromtimestamp(date_ts).strftime('%Y-%m-%d')
            else:
                date_str = ''
            
            # Format fee
            fee_str = self._format_currency(fee, currency_code)
            total += fee
            
            data.append([date_str, service, duration_str, fee_str])
        
        # Add total row
        data.append(['', '', 'TOTAL', self._format_currency(total, currency_code)])
        
        # Create table - full page width (7 inches with margins)
        # Columns: Date(1.2) + Service(2.8) + Duration(1.5) + Fee(1.5) = 7.0
        table = Table(data, colWidths=[1.2*inch, 2.8*inch, 1.5*inch, 1.5*inch])
        
        # Style the table
        # Row spacing tightened to fit up to 16 line items on one page
        style = TableStyle([
            # Header row
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
            ('LINEBELOW', (0, 0), (-1, 0), 1, colors.black),
            
            # Data rows - tighter padding (3pt top/bottom vs 6pt)
            ('FONTNAME', (0, 1), (-1, -2), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -2), 10),
            ('TOPPADDING', (0, 1), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 3),
            
            # Total row
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, -1), (-1, -1), 10),
            ('LINEABOVE', (2, -1), (-1, -1), 1, colors.black),
            
            # Alignment
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),    # Date left
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),    # Service left
            ('ALIGN', (2, 0), (2, -1), 'LEFT'),    # Duration left
            ('ALIGN', (3, 0), (3, -1), 'RIGHT'),   # Fee right
            
            # Vertical alignment
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ])
        table.setStyle(style)
        
        return table, total
    
    def _build_signature_section(self, settings, assets_path):
        """Build the attestation and signature section."""
        elements = []
        
        # Attestation text
        if settings['include_attestation'] and settings['attestation_text']:
            elements.append(Paragraph(settings['attestation_text'], self.styles['Attestation']))
        
        elements.append(Spacer(1, 0.3*inch))
        
        # Signature and date
        signature_path = None
        if settings['signature_filename']:
            signature_path = os.path.join(assets_path, settings['signature_filename'])
            if not os.path.exists(signature_path):
                signature_path = None
        
        # Current date formatted nicely
        today_str = datetime.now().strftime('%A %B %d, %Y')
        
        # Calculate date width based on actual text width
        date_width = len(today_str) * 5.5
        
        # Build signature with line matching signature width
        sig_width = 2.0 * inch  # Default/max width
        sig_content = ''
        if signature_path:
            try:
                sig_img = Image(signature_path)
                sig_img = self._scale_image_to_fit(sig_img, 2.0 * inch, 0.75 * inch)
                sig_width = sig_img.drawWidth
                sig_content = sig_img
            except Exception:
                sig_content = ''
                sig_width = 2.0 * inch
        
        # Build signature mini-table (image, line, label stacked)
        sig_data = [
            [sig_content],
            [HRFlowable(width=sig_width, thickness=0.5, color=colors.black, hAlign='LEFT')],
            [Paragraph('Therapist Signature', self.styles['SignatureLabel'])]
        ]
        sig_table = Table(sig_data, colWidths=[sig_width + 10])
        sig_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('VALIGN', (0, 0), (0, -1), 'BOTTOM'),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ]))
        
        # Build date mini-table (text, line, label stacked)
        date_data = [
            [Paragraph(today_str, self.styles['Normal'])],
            [HRFlowable(width=date_width, thickness=0.5, color=colors.black, hAlign='LEFT')],
            [Paragraph('Date', self.styles['DateLabel'])]
        ]
        date_table = Table(date_data, colWidths=[date_width + 10])
        date_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('VALIGN', (0, 0), (0, -1), 'BOTTOM'),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ]))
        
        # Combine into outer table for side-by-side layout
        outer_data = [[sig_table, date_table]]
        outer_table = Table(outer_data, colWidths=[4.5*inch, 3.0*inch])
        outer_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, 0), 'LEFT'),
            ('ALIGN', (1, 0), (1, 0), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ]))
        
        elements.append(outer_table)
        
        return elements
    
    def _build_payment_instructions(self, settings):
        """Build the payment instructions footer."""
        elements = []
        
        if settings['payment_instructions']:
            elements.append(Spacer(1, 0.2*inch))
            # Format with non-italic emails
            formatted_text = self._format_payment_instructions(settings['payment_instructions'])
            # Use a modified style that accepts HTML
            elements.append(Paragraph(
                formatted_text, 
                self.styles['PaymentInstructions']
            ))
        
        return elements
    
    def generate_statement_pdf(self, statement_portion_id, output_path, assets_path):
        """Generate a PDF statement for a specific statement portion.
        
        Args:
            statement_portion_id: ID of the statement_portion record
            output_path: Full path where PDF should be saved
            assets_path: Path to assets folder (for logo/signature)
            
        Returns:
            True on success, raises exception on failure
        """
        # Get the statement portion
        conn = self.db.connect()
        conn.row_factory = __import__('sqlite3').Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT sp.*, e.id as entry_id
            FROM statement_portions sp
            JOIN entries e ON sp.statement_entry_id = e.id
            WHERE sp.id = ?
        """, (statement_portion_id,))
        portion = cursor.fetchone()
        
        if not portion:
            raise ValueError(f"Statement portion {statement_portion_id} not found")
        
        # Get the client
        client = self.db.get_client(portion['client_id'])
        if not client:
            raise ValueError(f"Client {portion['client_id']} not found")
        
        # Get the profile
        profile = self.db.get_profile_entry(portion['client_id'])
        
        # Get billable entries linked to this statement
        cursor.execute("""
            SELECT * FROM entries 
            WHERE statement_id = ? 
            AND class IN ('session', 'absence', 'item')
            ORDER BY 
                CASE class 
                    WHEN 'session' THEN session_date 
                    WHEN 'absence' THEN absence_date 
                    WHEN 'item' THEN item_date 
                END ASC
        """, (portion['statement_entry_id'],))
        entries = [dict(row) for row in cursor.fetchall()]
        
        # Get settings
        settings = self._get_settings()
        
        # Determine bill-to info
        guardian_number = portion['guardian_number']  # None, 1, or 2
        bill_to = self._get_bill_to_info(client, profile, guardian_number)
        
        # Create the PDF document
        doc = SimpleDocTemplate(
            output_path,
            pagesize=letter,
            rightMargin=0.75*inch,
            leftMargin=0.75*inch,
            topMargin=0.75*inch,
            bottomMargin=0.75*inch
        )
        
        # Build the document
        story = []
        
        # Header
        story.extend(self._build_header(settings, assets_path))
        
        # Bill To
        story.extend(self._build_bill_to(bill_to))
        
        # Line items table
        table, total = self._build_line_items_table(entries, settings['currency'])
        story.append(table)
        
        # Signature section
        story.extend(self._build_signature_section(settings, assets_path))
        
        # Payment instructions
        story.extend(self._build_payment_instructions(settings))
        
        # Build the PDF
        doc.build(story)
        
        return True


def generate_statement_pdf(db, statement_portion_id, output_path, assets_path):
    """Convenience function to generate a statement PDF.
    
    Args:
        db: Database instance
        statement_portion_id: ID of the statement_portion record
        output_path: Full path where PDF should be saved
        assets_path: Path to assets folder (for logo/signature)
        
    Returns:
        True on success
    """
    generator = StatementPDFGenerator(db)
    return generator.generate_statement_pdf(statement_portion_id, output_path, assets_path)

def generate_session_report_pdf(db, client_id, start_date=None, end_date=None, include_fees=True):
    """
    Generate a session summary report PDF for a client.
    
    Args:
        db: Database instance
        client_id: Client ID
        start_date: Start date filter (Unix timestamp) or None
        end_date: End date filter (Unix timestamp) or None
        include_fees: Whether to include fee column
    
    Returns:
        BytesIO buffer containing the PDF
    """
    from io import BytesIO
    
    # Get client info
    client = db.get_client(client_id)
    if not client:
        raise ValueError(f"Client {client_id} not found")
    
    # Get profile for address
    profile = db.get_profile_entry(client_id)
    
    # Get all sessions for this client
    all_entries = db.get_client_entries(client_id)
    sessions = [e for e in all_entries if e['class'] == 'session' and not e.get('is_consultation')]
    
    # Filter by date range
    if start_date or end_date:
        filtered = []
        for s in sessions:
            session_date = s.get('session_date', 0)
            if start_date and session_date < start_date:
                continue
            if end_date and session_date > end_date:
                continue
            filtered.append(s)
        sessions = filtered
    
    # Sort by date
    sessions.sort(key=lambda s: s.get('session_date', 0))
    
    # Get settings
    settings = {
        'practice_name': db.get_setting('practice_name', ''),
        'therapist_name': db.get_setting('therapist_name', ''),
        'credentials': db.get_setting('credentials', ''),
        'address': db.get_setting('address', ''),
        'phone': db.get_setting('phone', ''),
        'website': db.get_setting('website', ''),
        'registration_info': db.get_setting('registration_info', ''),
        'logo_filename': db.get_setting('logo_filename'),
        'signature_filename': db.get_setting('signature_filename'),
        'include_attestation': db.get_setting('include_attestation', '1') in ['1', 'true', 'True'],
        'attestation_text': db.get_setting('attestation_text', 'I attest that I have performed the services listed above.'),
    }
    
    assets_path = os.path.expanduser('~/edgecase/assets')
    
    # Create PDF generator instance to reuse styles and methods
    generator = StatementPDFGenerator(db)
    
    # Build the document
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.5*inch,
        leftMargin=0.5*inch,
        topMargin=0.5*inch,
        bottomMargin=0.5*inch
    )
    
    story = []
    
    # Header (reuse from statement generator)
    story.extend(generator._build_header(settings, assets_path))
    
    # Client info (bill-to section)
    client_name = f"{client['first_name']} {client.get('middle_name') or ''} {client['last_name']}".replace('  ', ' ')
    story.append(Paragraph(f"<b>{client_name}</b>", generator.styles['Normal']))
    
    if profile and profile.get('address'):
        address_html = profile['address'].replace('\n', '<br/>')
        story.append(Paragraph(address_html, generator.styles['Normal']))
    
    story.append(Spacer(1, 0.2*inch))
    
    # Report title and date range
    story.append(Paragraph("<b>Session Summary Report</b>", generator.styles['Normal']))
    
    if start_date and end_date:
        start_str = datetime.fromtimestamp(start_date).strftime('%B %d, %Y')
        end_str = datetime.fromtimestamp(end_date).strftime('%B %d, %Y')
        story.append(Paragraph(f"For the period: {start_str} to {end_str}", generator.styles['Normal']))
    
    story.append(Spacer(1, 0.3*inch))
    
    # Build session table
    if include_fees:
        header_data = ['Date', 'Service', 'Duration', 'Fee']
        col_widths = [1.2*inch, 3.0*inch, 1.3*inch, 1.0*inch]
    else:
        header_data = ['Date', 'Service', 'Duration']
        col_widths = [1.5*inch, 3.5*inch, 1.5*inch]
    
    table_data = [header_data]
    total_fees = 0
    
    for session in sessions:
        session_date = session.get('session_date', 0)
        date_str = datetime.fromtimestamp(session_date).strftime('%Y-%m-%d') if session_date else ''
        service = session.get('service', 'Psychotherapy')
        duration = session.get('duration', 0)
        duration_str = f"{duration} mins." if duration else ''
        fee = session.get('fee', 0) or 0
        total_fees += fee
        
        if include_fees:
            table_data.append([date_str, service, duration_str, f"${fee:.2f}"])
        else:
            table_data.append([date_str, service, duration_str])
    
    # Add total row if fees included
    if include_fees:
        table_data.append(['', '', 'TOTAL', f"${total_fees:.2f}"])
    
    # Create table
    table = Table(table_data, colWidths=col_widths)
    
    table_style = [
        # Header styling
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F7FAFC')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        
        # Alignment
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),  # Date
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),  # Service
        ('ALIGN', (2, 0), (2, -1), 'LEFT'),  # Duration
        
        # Grid
        ('LINEBELOW', (0, 0), (-1, 0), 1, colors.HexColor('#CBD5E0')),
        ('LINEBELOW', (0, -1), (-1, -1), 1, colors.HexColor('#CBD5E0')),
        
        # Padding
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]
    
    if include_fees:
        table_style.extend([
            ('ALIGN', (3, 0), (3, -1), 'RIGHT'),  # Fee
            ('FONTNAME', (2, -1), (3, -1), 'Helvetica-Bold'),  # Total row
        ])
    
    table.setStyle(TableStyle(table_style))
    story.append(table)
    
    story.append(Spacer(1, 0.4*inch))
    
   # Attestation
    if settings['include_attestation'] and settings['attestation_text']:
        story.append(Paragraph(settings['attestation_text'], generator.styles['Attestation']))
    
    story.append(Spacer(1, 0.3*inch))
    
    # Signature only (no date)
    signature_path = None
    if settings['signature_filename']:
        signature_path = os.path.join(assets_path, settings['signature_filename'])
        if not os.path.exists(signature_path):
            signature_path = None
    
    sig_width = 2.0 * inch
    if signature_path:
        try:
            sig_img = Image(signature_path)
            sig_img = generator._scale_image_to_fit(sig_img, 2.0 * inch, 0.75 * inch)
            sig_width = sig_img.drawWidth
            sig_img.hAlign = 'LEFT'
            story.append(sig_img)
        except Exception:
            pass
    
    story.append(Spacer(1, 4))
    story.append(HRFlowable(width=sig_width, thickness=0.5, color=colors.black, hAlign='LEFT'))
    story.append(Paragraph('Therapist Signature', generator.styles['SignatureLabel']))
    
    # Build PDF
    doc.build(story)
    buffer.seek(0)
    return buffer