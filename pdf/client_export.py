"""
Client Export PDF Generator

Generates PDF exports of client files with all entry types.
Each entry starts on a new page, attachments follow their parent entry.
"""

import os
import json
import markdown
import re
from datetime import datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Image, HRFlowable
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from core.encryption import decrypt_file_to_bytes
from core.config import get_assets_path, get_attachments_path

def get_styles():
    """Create custom paragraph styles for the export."""
    styles = getSampleStyleSheet()
    
    # Entry title (e.g., "Session 15" or "Communication")
    styles.add(ParagraphStyle(
        name='EntryTitle',
        parent=styles['Heading1'],
        fontSize=16,
        spaceAfter=12,
        textColor=colors.HexColor('#1F8F74')
    ))
    
    # Section heading within entry
    styles.add(ParagraphStyle(
        name='SectionHeading',
        parent=styles['Heading2'],
        fontSize=12,
        spaceBefore=12,
        spaceAfter=6,
        textColor=colors.HexColor('#2D3748')
    ))
    
    # Field label
    styles.add(ParagraphStyle(
        name='FieldLabel',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor('#718096')
    ))
    
    # Field value
    styles.add(ParagraphStyle(
        name='FieldValue',
        parent=styles['Normal'],
        fontSize=11,
        textColor=colors.HexColor('#1A202C'),
        spaceAfter=8
    ))
    
    # Content text (for notes, etc.)
    styles.add(ParagraphStyle(
        name='ContentText',
        parent=styles['Normal'],
        fontSize=11,
        textColor=colors.HexColor('#1A202C'),
        leading=16,
        spaceAfter=6
    ))
    
    # Edit history
    styles.add(ParagraphStyle(
        name='EditHistory',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor('#718096'),
        leading=12
    ))
    
    # Client header
    styles.add(ParagraphStyle(
        name='ClientHeader',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#4A5568')
    ))
    
    return styles


def markdown_to_paragraphs(md_text, styles):
    """Convert Markdown text to ReportLab Paragraphs."""
    if not md_text:
        return []
    
    # Convert Markdown to HTML
    html = markdown.markdown(md_text, extensions=['extra'])
    
    # Replace common HTML with ReportLab-compatible markup
    html = html.replace('<strong>', '<b>').replace('</strong>', '</b>')
    html = html.replace('<em>', '<i>').replace('</em>', '</i>')
    html = html.replace('<code>', '<font face="Courier">').replace('</code>', '</font>')
    
    # Handle strikethrough - convert to ReportLab strike tag
    html = html.replace('<del>', '<strike>').replace('</del>', '</strike>')
    
    # Handle headers
    html = re.sub(r'<h1>(.*?)</h1>', r'<para><b><font size="14">\1</font></b></para>', html)
    html = re.sub(r'<h2>(.*?)</h2>', r'<para><b><font size="12">\1</font></b></para>', html)
    html = re.sub(r'<h3>(.*?)</h3>', r'<para><b><font size="11">\1</font></b></para>', html)
    
    # Handle lists - convert to indented paragraphs with bullets or numbers
    # Process ordered lists first, replacing <li> with numbered items
    def replace_ol(match):
        ol_content = match.group(1)
        items = re.findall(r'<li>(.*?)</li>', ol_content, flags=re.DOTALL)
        result = ''
        for i, item in enumerate(items, 1):
            result += f'<para>&nbsp;&nbsp;&nbsp;&nbsp;{i}. {item.strip()}</para>'
        return result
    
    html = re.sub(r'<ol>\s*(.*?)\s*</ol>', replace_ol, html, flags=re.DOTALL)
    
    # Process unordered lists, replacing <li> with bullets
    html = re.sub(r'<ul>\s*', '', html)
    html = re.sub(r'</ul>\s*', '', html)
    html = re.sub(r'<li>(.*?)</li>', r'<para>&nbsp;&nbsp;&nbsp;&nbsp;• \1</para>', html, flags=re.DOTALL)
    
    # Handle blockquotes
    html = re.sub(r'<blockquote>(.*?)</blockquote>', 
                  r'<para><font color="#666666"><i>\1</i></font></para>', 
                  html, flags=re.DOTALL)
    
    # Split into paragraphs
    parts = re.split(r'</?p>|</?para>', html)
    
    paragraphs = []
    for part in parts:
        part = part.strip()
        if part:
            # Clean up any remaining HTML artifacts
            part = re.sub(r'<br\s*/?>', '<br/>', part)
            try:
                paragraphs.append(Paragraph(part, styles['ContentText']))
            except:
                # If parsing fails, try plain text
                plain = re.sub(r'<[^>]+>', '', part)
                if plain.strip():
                    paragraphs.append(Paragraph(plain, styles['ContentText']))
    
    return paragraphs


def format_date(timestamp):
    """Format Unix timestamp to readable date."""
    if not timestamp:
        return "N/A"
    try:
        return datetime.fromtimestamp(timestamp).strftime('%B %d, %Y')
    except:
        return "N/A"


def get_currency_symbol(currency_code):
    """Convert currency code to symbol."""
    symbols = {
        'CAD': '$', 'USD': '$', 'EUR': '€', 'GBP': '£',
        'AUD': '$', 'NZD': '$', 'JPY': '¥', 'CNY': '¥',
        'INR': '₹', 'MXN': '$', 'BRL': 'R$', 'CHF': 'CHF'
    }
    return symbols.get(currency_code, '$')


def format_currency(amount, currency_symbol='$'):
    """Format amount as currency."""
    if amount is None:
        return f"{currency_symbol}0.00"
    return f"{currency_symbol}{amount:.2f}"


def format_edit_history(edit_history_json, styles):
    """Parse and format edit history entries."""
    elements = []
    
    if not edit_history_json:
        return elements
    
    try:
        history = json.loads(edit_history_json)
        for edit in history:
            # Get timestamp - convert Unix timestamp to readable date
            timestamp = edit.get('timestamp', 0)
            if isinstance(timestamp, (int, float)) and timestamp > 0:
                try:
                    timestamp_str = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M')
                except:
                    timestamp_str = 'Unknown date'
            else:
                timestamp_str = str(timestamp) if timestamp else 'Unknown date'
            
            # Get description
            description = edit.get('description', '')
            
            # Format the edit entry
            if description:
                edit_text = f"{timestamp_str}: {description}"
            else:
                edit_text = f"{timestamp_str}: Changes made"
            
            # Convert HTML tags to ReportLab-compatible markup
            edit_text = edit_text.replace('<del>', '<strike>').replace('</del>', '</strike>')
            edit_text = edit_text.replace('<strong>', '<b>').replace('</strong>', '</b>')
            edit_text = edit_text.replace('<em>', '<i>').replace('</em>', '</i>')
            
            # Try to create paragraph with formatting
            try:
                elements.append(Paragraph(edit_text, styles['EditHistory']))
            except:
                # If HTML parsing fails, escape ALL angle brackets and try again
                plain_text = edit_text.replace('<', '&lt;').replace('>', '&gt;')
                try:
                    elements.append(Paragraph(plain_text, styles['EditHistory']))
                except:
                    # Last resort - just show timestamp
                    elements.append(Paragraph(f"{timestamp_str}: [Edit history could not be displayed]", styles['EditHistory']))
                
    except json.JSONDecodeError:
        # If it's not valid JSON, skip it
        pass
    
    return elements

def build_redacted_entry(entry, client, styles, entry_type, entry_date_field):
    """Build PDF elements for a redacted entry - minimal metadata only.
    
    Args:
        entry: The entry dict
        client: The client dict
        styles: PDF styles
        entry_type: Display name (e.g., 'Session', 'Communication', 'Absence', 'Item')
        entry_date_field: Field name for the entry date (e.g., 'session_date', 'comm_date')
    """
    elements = []
    
    # Title: "Redacted [Entry Type]"
    elements.append(Paragraph(f"Redacted {entry_type}", styles['EntryTitle']))
    
    # Client info line
    client_name = f"{client['first_name']} {client.get('middle_name', '') or ''} {client['last_name']}".replace('  ', ' ')
    elements.append(Paragraph(f"{client_name} · File #{client['file_number']}", styles['ClientHeader']))
    elements.append(Spacer(1, 12))
    
    # Metadata table: Entry Type, Entry Date, Created
    entry_date = format_date(entry.get(entry_date_field))
    created_date = format_date(entry.get('created_at'))
    
    info_data = [[
        Paragraph(f'<b>Entry Type:</b> {entry_type}', styles['FieldValue']),
        Paragraph(f'<b>Entry Date:</b> {entry_date}', styles['FieldValue']),
        Paragraph(f'<b>Created:</b> {created_date}', styles['FieldValue']),
    ]]
    
    info_table = Table(info_data, colWidths=[2.2*inch, 2.2*inch, 2.2*inch])
    info_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 12))
    
    # Redaction details
    elements.append(Paragraph("Redaction Details", styles['SectionHeading']))
    
    redacted_date = format_date(entry.get('redacted_at'))
    reason = entry.get('redaction_reason', 'No reason provided')
    
    redaction_data = [[
        Paragraph(f'<b>Redacted On:</b> {redacted_date}', styles['FieldValue']),
        Paragraph(f'<b>Reason:</b> {reason}', styles['FieldValue']),
    ]]
    
    redaction_table = Table(redaction_data, colWidths=[2.2*inch, 4.4*inch])
    redaction_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    elements.append(redaction_table)
    
    return elements

def build_session_entry(entry, client, styles, signature_path=None, db=None):
    """Build PDF elements for a Session entry."""
    elements = []
    
    # Handle redacted entries with minimal metadata
    if entry.get('is_redacted'):
        return build_redacted_entry(entry, client, styles, 'Session', 'session_date')
    
    # Entry title
    title = entry.get('description', 'Session')
    if entry.get('is_consultation'):
        title = "Consultation"
    elif entry.get('is_pro_bono'):
        title = f"{title} (Pro Bono)"
    
    elements.append(Paragraph(title, styles['EntryTitle']))
    
    # Client info line
    client_name = f"{client['first_name']} {client.get('middle_name', '') or ''} {client['last_name']}".replace('  ', ' ')
    elements.append(Paragraph(f"{client_name} · File #{client['file_number']}", styles['ClientHeader']))
    elements.append(Spacer(1, 12))
    
    # Basic info table
    info_data = []
    
    # Row 1: Date, Time, Duration
    date_str = format_date(entry.get('session_date'))
    time_str = entry.get('session_time') or "—"
    duration = f"{entry.get('duration', 0)} minutes" if entry.get('duration') else "—"
    
    info_data.append([
        Paragraph('<b>Date:</b> ' + date_str, styles['FieldValue']),
        Paragraph('<b>Time:</b> ' + time_str, styles['FieldValue']),
        Paragraph('<b>Duration:</b> ' + duration, styles['FieldValue']),
    ])
    
    # Row 2: Modality, Format, Service
    modality = (entry.get('modality') or "—").replace('-', ' ').title()
    format_val = (entry.get('format') or "—").title()
    service = entry.get('service') or "—"
    
    info_data.append([
        Paragraph('<b>Modality:</b> ' + modality, styles['FieldValue']),
        Paragraph('<b>Format:</b> ' + format_val, styles['FieldValue']),
        Paragraph('<b>Service:</b> ' + service, styles['FieldValue']),
    ])
    
    info_table = Table(info_data, colWidths=[2.2*inch, 2.2*inch, 2.2*inch])
    info_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 12))
    
    # Clinical assessment
    mood = entry.get('mood')
    affect = entry.get('affect')
    risk = entry.get('risk_assessment')
    
    if mood or affect or risk:
        elements.append(Paragraph("Clinical Assessment", styles['SectionHeading']))
        
        assessment_data = [[
            Paragraph(f'<b>Mood:</b> {(mood or "Not assessed").title()}', styles['FieldValue']),
            Paragraph(f'<b>Affect:</b> {(affect or "Not assessed").title()}', styles['FieldValue']),
            Paragraph(f'<b>Risk:</b> {(risk or "Not assessed").replace("_", " ").title()}', styles['FieldValue']),
        ]]
        
        assessment_table = Table(assessment_data, colWidths=[2.2*inch, 2.2*inch, 2.2*inch])
        assessment_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(assessment_table)
        elements.append(Spacer(1, 12))
    
    # Session notes
    if entry.get('content'):
        elements.append(Paragraph("Notes", styles['SectionHeading']))
        elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#E2E8F0')))
        elements.append(Spacer(1, 6))
        
        content_paragraphs = markdown_to_paragraphs(entry.get('content', ''), styles)
        elements.extend(content_paragraphs)
        
        elements.append(Spacer(1, 12))
    
    # Edit history
    if entry.get('edit_history'):
        elements.append(Paragraph("Edit History", styles['SectionHeading']))
        history_elements = format_edit_history(entry.get('edit_history'), styles)
        elements.extend(history_elements)
        elements.append(Spacer(1, 12))
    
    # Signature (above line, left-aligned, fixed size)
    if signature_path and os.path.exists(signature_path):
        elements.append(Spacer(1, 24))
        try:
            # Decrypt if encrypted
            if db and db.password:
                decrypted = decrypt_file_to_bytes(signature_path, db.password)
                sig_img = Image(BytesIO(decrypted))
            else:
                sig_img = Image(signature_path)
            
            # Get original aspect ratio
            aspect = sig_img.imageWidth / sig_img.imageHeight
            
            # Set maximum dimensions
            max_width = 2 * inch
            max_height = 0.75 * inch
            
            # Calculate dimensions that fit within bounds
            if aspect > (max_width / max_height):
                # Width-constrained
                sig_width = max_width
                sig_height = max_width / aspect
            else:
                # Height-constrained
                sig_height = max_height
                sig_width = max_height * aspect
            
            sig_img.drawWidth = sig_width
            sig_img.drawHeight = sig_height
            sig_img.hAlign = 'LEFT'
            elements.append(sig_img)
            elements.append(Spacer(1, 4))
            # Line matches signature width
            elements.append(HRFlowable(width=sig_width, thickness=0.5, color=colors.HexColor('#2D3748'), hAlign='LEFT'))
            elements.append(Paragraph("Therapist Signature", styles['FieldLabel']))
        except Exception as e:
            pass
    
    return elements


def build_communication_entry(entry, client, styles, db=None):
    """Build PDF elements for a Communication entry."""
    elements = []
    
    # Handle redacted entries with minimal metadata
    if entry.get('is_redacted'):
        return build_redacted_entry(entry, client, styles, 'Communication', 'comm_date')
    
    title = entry.get('description', 'Communication')
    elements.append(Paragraph(f"Communication: {title}", styles['EntryTitle']))
    
    client_name = f"{client['first_name']} {client.get('middle_name', '') or ''} {client['last_name']}".replace('  ', ' ')
    elements.append(Paragraph(f"{client_name} · File #{client['file_number']}", styles['ClientHeader']))
    elements.append(Spacer(1, 12))
    
    # Description
    if entry.get('description'):
        elements.append(Paragraph(f"<b>Description:</b> {entry['description']}", styles['FieldValue']))
        elements.append(Spacer(1, 8))
    
    date_str = format_date(entry.get('comm_date'))
    time_str = entry.get('comm_time') or "—"
    
    recipient_map = {
        'to_client': 'To Client',
        'from_client': 'From Client',
        'internal_note': 'Internal Note'
    }
    recipient = recipient_map.get(entry.get('comm_recipient'), entry.get('comm_recipient', '—'))
    
    comm_type = (entry.get('comm_type') or '—').title()
    
    info_data = [[
        Paragraph(f'<b>Date:</b> {date_str}', styles['FieldValue']),
        Paragraph(f'<b>Time:</b> {time_str}', styles['FieldValue']),
    ], [
        Paragraph(f'<b>Recipient:</b> {recipient}', styles['FieldValue']),
        Paragraph(f'<b>Type:</b> {comm_type}', styles['FieldValue']),
    ]]
    
    info_table = Table(info_data, colWidths=[3.3*inch, 3.3*inch])
    info_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 12))
    
    if entry.get('content'):
        elements.append(Paragraph("Content", styles['SectionHeading']))
        elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#E2E8F0')))
        elements.append(Spacer(1, 6))
        content_paragraphs = markdown_to_paragraphs(entry.get('content', ''), styles)
        elements.extend(content_paragraphs)
    
    # Attachments
    if db:
        attachments = db.get_attachments(entry['id'])
        if attachments:
            elements.append(Spacer(1, 12))
            elements.append(Paragraph("Attachments", styles['SectionHeading']))
            elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#E2E8F0')))
            elements.append(Spacer(1, 6))
            elements.append(Paragraph("<i>(Attachments listed below are included in the client file)</i>", styles['FieldValue']))
            elements.append(Spacer(1, 4))
            for att in attachments:
                att_text = f"• {att['filename']}"
                if att.get('description') and att['description'] != att['filename']:
                    att_text += f" — {att['description']}"
                elements.append(Paragraph(att_text, styles['FieldValue']))
    
    if entry.get('edit_history'):
        elements.append(Spacer(1, 12))
        elements.append(Paragraph("Edit History", styles['SectionHeading']))
        history_elements = format_edit_history(entry.get('edit_history'), styles)
        elements.extend(history_elements)
    
    return elements


def build_absence_entry(entry, client, styles, currency_symbol='$'):
    """Build PDF elements for an Absence entry."""
    elements = []
    
    # Handle redacted entries with minimal metadata
    if entry.get('is_redacted'):
        return build_redacted_entry(entry, client, styles, 'Absence', 'absence_date')
    
    title = entry.get('description', 'Absence')
    elements.append(Paragraph(f"Absence: {title}", styles['EntryTitle']))
    
    client_name = f"{client['first_name']} {client.get('middle_name', '') or ''} {client['last_name']}".replace('  ', ' ')
    elements.append(Paragraph(f"{client_name} · File #{client['file_number']}", styles['ClientHeader']))
    elements.append(Spacer(1, 12))
    
    date_str = format_date(entry.get('absence_date'))
    time_str = entry.get('absence_time') or "—"
    
    elements.append(Paragraph(f'<b>Date:</b> {date_str}', styles['FieldValue']))
    elements.append(Paragraph(f'<b>Time:</b> {time_str}', styles['FieldValue']))
    
    # Fee fields (if present)
    base_fee = entry.get('base_fee')
    tax_rate = entry.get('tax_rate')
    fee = entry.get('fee')
    
    if base_fee is not None or fee is not None:
        base_str = f"{currency_symbol}{base_fee:.2f}" if base_fee is not None else "—"
        tax_str = f"{tax_rate:.1f}%" if tax_rate is not None else "—"
        fee_str = f"{currency_symbol}{fee:.2f}" if fee is not None else "—"
        
        elements.append(Paragraph(f'<b>Base Fee:</b> {base_str}', styles['FieldValue']))
        elements.append(Paragraph(f'<b>Tax Rate:</b> {tax_str}', styles['FieldValue']))
        elements.append(Paragraph(f'<b>Total:</b> {fee_str}', styles['FieldValue']))
    
    elements.append(Spacer(1, 12))
    
    if entry.get('content'):
        elements.append(Paragraph("Notes", styles['SectionHeading']))
        elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#E2E8F0')))
        elements.append(Spacer(1, 6))
        content_paragraphs = markdown_to_paragraphs(entry.get('content', ''), styles)
        elements.extend(content_paragraphs)
    
    if entry.get('edit_history'):
        elements.append(Spacer(1, 12))
        elements.append(Paragraph("Edit History", styles['SectionHeading']))
        history_elements = format_edit_history(entry.get('edit_history'), styles)
        elements.extend(history_elements)
    
    return elements

def build_item_entry(entry, client, styles, currency_symbol='$'):
    """Build PDF elements for an Item entry."""
    elements = []
    
    # Handle redacted entries with minimal metadata
    if entry.get('is_redacted'):
        return build_redacted_entry(entry, client, styles, 'Item', 'item_date')
    
    title = entry.get('description', 'Item')
    elements.append(Paragraph(f"Item: {title}", styles['EntryTitle']))
    
    client_name = f"{client['first_name']} {client.get('middle_name', '') or ''} {client['last_name']}".replace('  ', ' ')
    elements.append(Paragraph(f"{client_name} · File #{client['file_number']}", styles['ClientHeader']))
    elements.append(Spacer(1, 12))
    
    date_str = format_date(entry.get('item_date'))
    
    # Format fee values
    base_price = entry.get('base_price')
    tax_rate = entry.get('tax_rate')
    fee = entry.get('fee')
    
    base_str = f"{currency_symbol}{base_price:.2f}" if base_price is not None else "—"
    tax_str = f"{tax_rate:.1f}%" if tax_rate is not None else "—"
    fee_str = f"{currency_symbol}{fee:.2f}" if fee is not None else "—"
    
    elements.append(Paragraph(f'<b>Date:</b> {date_str}', styles['FieldValue']))
    elements.append(Paragraph(f'<b>Base Price:</b> {base_str}', styles['FieldValue']))
    elements.append(Paragraph(f'<b>Tax Rate:</b> {tax_str}', styles['FieldValue']))
    elements.append(Paragraph(f'<b>Total:</b> {fee_str}', styles['FieldValue']))
    elements.append(Spacer(1, 12))
    
    if entry.get('content'):
        elements.append(Paragraph("Description", styles['SectionHeading']))
        elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#E2E8F0')))
        elements.append(Spacer(1, 6))
        content_paragraphs = markdown_to_paragraphs(entry.get('content', ''), styles)
        elements.extend(content_paragraphs)
    
    if entry.get('edit_history'):
        elements.append(Spacer(1, 12))
        elements.append(Paragraph("Edit History", styles['SectionHeading']))
        history_elements = format_edit_history(entry.get('edit_history'), styles)
        elements.extend(history_elements)
    
    return elements

def build_upload_entry(entry, client, styles, attachments):
    """Build PDF elements for an Upload entry."""
    elements = []
    
    title = entry.get('description', 'Upload')
    elements.append(Paragraph(f"Upload: {title}", styles['EntryTitle']))
    
    client_name = f"{client['first_name']} {client.get('middle_name', '') or ''} {client['last_name']}".replace('  ', ' ')
    elements.append(Paragraph(f"{client_name} · File #{client['file_number']}", styles['ClientHeader']))
    elements.append(Spacer(1, 12))
    
    date_str = format_date(entry.get('upload_date'))
    elements.append(Paragraph(f'<b>Date:</b> {date_str}', styles['FieldValue']))
    elements.append(Spacer(1, 12))
    
    if entry.get('content'):
        elements.append(Paragraph("Notes", styles['SectionHeading']))
        elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#E2E8F0')))
        elements.append(Spacer(1, 6))
        content_paragraphs = markdown_to_paragraphs(entry.get('content', ''), styles)
        elements.extend(content_paragraphs)
        elements.append(Spacer(1, 12))
    
    if attachments:
        elements.append(Paragraph("Attachments", styles['SectionHeading']))
        for att in attachments:
            att_text = f"• {att.get('description') or att.get('filename', 'Unknown file')}"
            elements.append(Paragraph(att_text, styles['FieldValue']))
        elements.append(Paragraph("<i>(Attachments follow on subsequent pages)</i>", styles['EditHistory']))
    
    if entry.get('edit_history'):
        elements.append(Spacer(1, 12))
        elements.append(Paragraph("Edit History", styles['SectionHeading']))
        history_elements = format_edit_history(entry.get('edit_history'), styles)
        elements.extend(history_elements)
    
    return elements


def build_profile_entry(entry, client, styles):
    """Build PDF elements for a Profile entry."""
    elements = []
    
    elements.append(Paragraph("Client Profile", styles['EntryTitle']))
    
    client_name = f"{client['first_name']} {client.get('middle_name', '') or ''} {client['last_name']}".replace('  ', ' ')
    elements.append(Paragraph(f"<b>{client_name}</b>", styles['FieldValue']))
    elements.append(Paragraph(f"File #{client['file_number']}", styles['ClientHeader']))
    elements.append(Spacer(1, 16))
    
    # Contact Information
    elements.append(Paragraph("Contact Information", styles['SectionHeading']))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#E2E8F0')))
    elements.append(Spacer(1, 8))
    
    if entry.get('email'):
        elements.append(Paragraph(f"<b>Email:</b> {entry['email']}", styles['FieldValue']))
    
    phones = []
    if entry.get('phone'):
        phones.append(f"Cell: {entry['phone']}")
    if entry.get('home_phone'):
        phones.append(f"Home: {entry['home_phone']}")
    if entry.get('work_phone'):
        phones.append(f"Work: {entry['work_phone']}")
    if phones:
        elements.append(Paragraph(f"<b>Phone:</b> {', '.join(phones)}", styles['FieldValue']))
    
    if entry.get('address'):
        # Replace newlines with " / " for single-line display
        address = entry['address'].replace('\n', ' / ').replace('\r', '')
        elements.append(Paragraph(f"<b>Address:</b> {address}", styles['FieldValue']))
    
    if entry.get('date_of_birth'):
        elements.append(Paragraph(f"<b>Date of Birth:</b> {entry['date_of_birth']}", styles['FieldValue']))
        
    if entry.get('content'):
        elements.append(Paragraph(f"<b>Gender:</b> {entry['content']}", styles['FieldValue']))
    
    if entry.get('preferred_contact'):
        pref_map = {
            'email': 'Email',
            'call_cell': 'Call Cell',
            'call_home': 'Call Home',
            'call_work': 'Call Work',
            'text': 'Text'
        }
        pref = pref_map.get(entry['preferred_contact'], entry['preferred_contact'])
        elements.append(Paragraph(f"<b>Preferred Contact:</b> {pref}", styles['FieldValue']))
    
    if entry.get('ok_to_leave_message'):
        elements.append(Paragraph(f"<b>OK to Leave Message:</b> {entry['ok_to_leave_message'].title()}", styles['FieldValue']))
    
    elements.append(Spacer(1, 12))
    
    # Emergency Contact
    if entry.get('emergency_contact_name'):
        elements.append(Paragraph("Emergency Contact", styles['SectionHeading']))
        elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#E2E8F0')))
        elements.append(Spacer(1, 8))
        
        elements.append(Paragraph(f"<b>Name:</b> {entry['emergency_contact_name']}", styles['FieldValue']))
        if entry.get('emergency_contact_relationship'):
            elements.append(Paragraph(f"<b>Relationship:</b> {entry['emergency_contact_relationship']}", styles['FieldValue']))
        if entry.get('emergency_contact_phone'):
            elements.append(Paragraph(f"<b>Phone:</b> {entry['emergency_contact_phone']}", styles['FieldValue']))
        
        elements.append(Spacer(1, 12))
    
    # Guardian information (if minor)
    if entry.get('is_minor'):
        elements.append(Paragraph("Guardian Information", styles['SectionHeading']))
        elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#E2E8F0')))
        elements.append(Spacer(1, 8))
        
        if entry.get('guardian1_name'):
            elements.append(Paragraph(f"<b>Guardian 1:</b> {entry['guardian1_name']}", styles['FieldValue']))
            if entry.get('guardian1_email'):
                elements.append(Paragraph(f"  Email: {entry['guardian1_email']}", styles['FieldValue']))
            if entry.get('guardian1_phone'):
                elements.append(Paragraph(f"  Phone: {entry['guardian1_phone']}", styles['FieldValue']))
        
        if entry.get('has_guardian2') and entry.get('guardian2_name'):
            elements.append(Spacer(1, 6))
            elements.append(Paragraph(f"<b>Guardian 2:</b> {entry['guardian2_name']}", styles['FieldValue']))
            if entry.get('guardian2_email'):
                elements.append(Paragraph(f"  Email: {entry['guardian2_email']}", styles['FieldValue']))
            if entry.get('guardian2_phone'):
                elements.append(Paragraph(f"  Phone: {entry['guardian2_phone']}", styles['FieldValue']))
        
        elements.append(Spacer(1, 12))
    
    # Referral and additional info
    if entry.get('referral_source'):
        elements.append(Paragraph(f"<b>Referral Source:</b> {entry['referral_source']}", styles['FieldValue']))
    
    if entry.get('additional_info'):
        elements.append(Spacer(1, 8))
        elements.append(Paragraph("Additional Information", styles['SectionHeading']))
        elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#E2E8F0')))
        elements.append(Spacer(1, 6))
        content_paragraphs = markdown_to_paragraphs(entry.get('additional_info', ''), styles)
        elements.extend(content_paragraphs)
    
    # Edit history
    if entry.get('edit_history'):
        elements.append(Spacer(1, 12))
        elements.append(Paragraph("Edit History", styles['SectionHeading']))
        history_elements = format_edit_history(entry.get('edit_history'), styles)
        elements.extend(history_elements)
    
    return elements

def build_communication_entry_with_attachments(entry, client, styles, db):
    """Build PDF elements for a Communication entry, returning elements and PDF attachments separately."""
    elements = []
    pdf_attachments = []
    
    # Handle redacted entries with minimal metadata
    if entry.get('is_redacted'):
        return build_redacted_entry(entry, client, styles, 'Communication', 'comm_date'), []
    
    title = entry.get('description', 'Communication')
    elements.append(Paragraph(f"Communication: {title}", styles['EntryTitle']))
    
    client_name = f"{client['first_name']} {client.get('middle_name', '') or ''} {client['last_name']}".replace('  ', ' ')
    elements.append(Paragraph(f"{client_name} · File #{client['file_number']}", styles['ClientHeader']))
    elements.append(Spacer(1, 12))
    
    date_str = format_date(entry.get('comm_date'))
    time_str = entry.get('comm_time') or "—"
    
    recipient_map = {
        'to_client': 'To Client',
        'from_client': 'From Client',
        'internal_note': 'Internal Note'
    }
    recipient = recipient_map.get(entry.get('comm_recipient'), entry.get('comm_recipient', '—'))
    
    comm_type = (entry.get('comm_type') or '—').title()
    
    info_data = [[
        Paragraph(f'<b>Date:</b> {date_str}', styles['FieldValue']),
        Paragraph(f'<b>Time:</b> {time_str}', styles['FieldValue']),
    ], [
        Paragraph(f'<b>Recipient:</b> {recipient}', styles['FieldValue']),
        Paragraph(f'<b>Type:</b> {comm_type}', styles['FieldValue']),
    ]]
    
    info_table = Table(info_data, colWidths=[3.3*inch, 3.3*inch])
    info_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 12))
    
    if entry.get('content'):
        elements.append(Paragraph("Content", styles['SectionHeading']))
        elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#E2E8F0')))
        elements.append(Spacer(1, 6))
        content_paragraphs = markdown_to_paragraphs(entry.get('content', ''), styles)
        elements.extend(content_paragraphs)
    
    # Handle attachments
    if db:
        attachments = db.get_attachments(entry['id'])
        if attachments:
            elements.append(Spacer(1, 12))
            elements.append(Paragraph("Attachments", styles['SectionHeading']))
            elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#E2E8F0')))
            elements.append(Spacer(1, 6))
            
            for att in attachments:
                filename = att['filename'].lower()
                filepath = os.path.join(get_attachments_path(), 
                                       str(client['id']), str(entry['id']), att['filename'])
                
                att_desc = att.get('description') or att['filename']
                
                if filename.endswith(('.png', '.jpg', '.jpeg', '.gif')):
                    # Embed image inline
                    if os.path.exists(filepath):
                        try:
                            elements.append(Paragraph(f"<b>{att_desc}</b>", styles['FieldValue']))
                            elements.append(Spacer(1, 4))
                            img = Image(filepath)
                            # Scale to fit page width (max 6.5 inches) while maintaining aspect ratio
                            max_width = 6.5 * inch
                            max_height = 8 * inch
                            aspect = img.imageWidth / img.imageHeight
                            if aspect > (max_width / max_height):
                                img.drawWidth = max_width
                                img.drawHeight = max_width / aspect
                            else:
                                img.drawHeight = max_height
                                img.drawWidth = max_height * aspect
                            # Don't exceed original size
                            if img.drawWidth > img.imageWidth:
                                img.drawWidth = img.imageWidth
                                img.drawHeight = img.imageHeight
                            img.hAlign = 'LEFT'
                            elements.append(img)
                            elements.append(Spacer(1, 8))
                        except Exception as e:
                            elements.append(Paragraph(f"• {att_desc} <i>(could not embed image)</i>", styles['FieldValue']))
                    else:
                        elements.append(Paragraph(f"• {att_desc} <i>(file not found)</i>", styles['FieldValue']))
                        
                elif filename.endswith('.pdf'):
                    # Add to PDF attachments list for appending at end
                    elements.append(Paragraph(f"• {att_desc} <i>(PDF attached at end of document)</i>", styles['FieldValue']))
                    entry_date = format_date(entry.get('comm_date'))
                    pdf_attachments.append(('Communication', title, entry_date, filepath))
                else:
                    # Other file types - just list them
                    elements.append(Paragraph(f"• {att_desc}", styles['FieldValue']))
    
    if entry.get('edit_history'):
        elements.append(Spacer(1, 12))
        elements.append(Paragraph("Edit History", styles['SectionHeading']))
        history_elements = format_edit_history(entry.get('edit_history'), styles)
        elements.extend(history_elements)
    
    return elements, pdf_attachments


def build_upload_entry_with_attachments(entry, client, styles, db):
    """Build PDF elements for an Upload entry, returning elements and PDF attachments separately."""
    elements = []
    pdf_attachments = []
    
    title = entry.get('description', 'Upload')
    elements.append(Paragraph(f"Upload: {title}", styles['EntryTitle']))
    
    client_name = f"{client['first_name']} {client.get('middle_name', '') or ''} {client['last_name']}".replace('  ', ' ')
    elements.append(Paragraph(f"{client_name} · File #{client['file_number']}", styles['ClientHeader']))
    elements.append(Spacer(1, 12))
    
    date_str = format_date(entry.get('upload_date'))
    elements.append(Paragraph(f"<b>Date:</b> {date_str}", styles['FieldValue']))
    elements.append(Spacer(1, 12))
    
    if entry.get('content'):
        elements.append(Paragraph("Notes", styles['SectionHeading']))
        elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#E2E8F0')))
        elements.append(Spacer(1, 6))
        content_paragraphs = markdown_to_paragraphs(entry.get('content', ''), styles)
        elements.extend(content_paragraphs)
        elements.append(Spacer(1, 12))
    
    # Handle attachments
    if db:
        attachments = db.get_attachments(entry['id'])
        if attachments:
            elements.append(Paragraph("Attachments", styles['SectionHeading']))
            elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#E2E8F0')))
            elements.append(Spacer(1, 6))
            
            for att in attachments:
                filename = att['filename'].lower()
                filepath = os.path.join(get_attachments_path(), 
                                       str(client['id']), str(entry['id']), att['filename'])
                
                att_desc = att.get('description') or att['filename']
                
                if filename.endswith(('.png', '.jpg', '.jpeg', '.gif')):
                    # Embed image inline
                    if os.path.exists(filepath):
                        try:
                            elements.append(Paragraph(f"<b>{att_desc}</b>", styles['FieldValue']))
                            elements.append(Spacer(1, 4))
                            img = Image(filepath)
                            # Scale to fit page width while maintaining aspect ratio
                            max_width = 6.5 * inch
                            max_height = 8 * inch
                            aspect = img.imageWidth / img.imageHeight
                            if aspect > (max_width / max_height):
                                img.drawWidth = max_width
                                img.drawHeight = max_width / aspect
                            else:
                                img.drawHeight = max_height
                                img.drawWidth = max_height * aspect
                            # Don't exceed original size
                            if img.drawWidth > img.imageWidth:
                                img.drawWidth = img.imageWidth
                                img.drawHeight = img.imageHeight
                            img.hAlign = 'LEFT'
                            elements.append(img)
                            elements.append(Spacer(1, 8))
                        except Exception as e:
                            elements.append(Paragraph(f"• {att_desc} <i>(could not embed image)</i>", styles['FieldValue']))
                    else:
                        elements.append(Paragraph(f"• {att_desc} <i>(file not found)</i>", styles['FieldValue']))
                        
                elif filename.endswith('.pdf'):
                    # Add to PDF attachments list for appending at end
                    elements.append(Paragraph(f"• {att_desc} <i>(PDF attached at end of document)</i>", styles['FieldValue']))
                    entry_date = format_date(entry.get('upload_date'))
                    pdf_attachments.append(('Upload', title, entry_date, filepath))
                else:
                    # Other file types - just list them
                    elements.append(Paragraph(f"• {att_desc}", styles['FieldValue']))
    
    if entry.get('edit_history'):
        elements.append(Spacer(1, 12))
        elements.append(Paragraph("Edit History", styles['SectionHeading']))
        history_elements = format_edit_history(entry.get('edit_history'), styles)
        elements.extend(history_elements)
    
    return elements, pdf_attachments

def generate_client_export_pdf(db, client_id, entry_types, start_date=None, end_date=None, output_path=None):
    """
    Generate a PDF export of a client's file.
    
    Args:
        db: Database instance
        client_id: Client ID
        entry_types: List of entry types to include ('profile', 'session', etc.)
        start_date: Start date filter (Unix timestamp) or None for all time
        end_date: End date filter (Unix timestamp) or None for all time
        output_path: Path to save PDF, or None to return BytesIO
    
    Returns:
        Path to generated PDF or BytesIO buffer
    """
    from pypdf import PdfReader, PdfWriter
    
    # Get client info
    client = db.get_client(client_id)
    if not client:
        raise ValueError(f"Client {client_id} not found")
    
    # Get signature path
    signature_filename = db.get_setting('signature_filename')
    assets_path = get_assets_path()
    signature_path = None
    if signature_filename:
        signature_path = os.path.join(assets_path, signature_filename)
        if not os.path.exists(signature_path):
            signature_path = None
    
    # Get currency symbol
    currency_code = db.get_setting('currency', 'CAD')
    currency_symbol = get_currency_symbol(currency_code)
    
    # Track PDF attachments to append at end
    pdf_attachments = []  # List of (entry_description, filepath) tuples
    
    styles = get_styles()
    elements = []
    
    # Get profile entry if requested
    if 'profile' in entry_types:
        profile = db.get_profile_entry(client_id)
        if profile:
            elements.extend(build_profile_entry(profile, client, styles))
            elements.append(PageBreak())
    
    # Get all other entries
    all_entries = db.get_client_entries(client_id)
    
    # Filter by date range if specified
    if start_date or end_date:
        filtered_entries = []
        for entry in all_entries:
            entry_date = None
            if entry['class'] == 'session':
                entry_date = entry.get('session_date')
            elif entry['class'] == 'communication':
                entry_date = entry.get('comm_date')
            elif entry['class'] == 'absence':
                entry_date = entry.get('absence_date')
            elif entry['class'] == 'item':
                entry_date = entry.get('item_date')
            elif entry['class'] == 'upload':
                entry_date = entry.get('upload_date')
            
            if entry_date:
                if start_date and entry_date < start_date:
                    continue
                if end_date and entry_date > end_date:
                    continue
            
            filtered_entries.append(entry)
        all_entries = filtered_entries
    
    # Sort entries by date (oldest first for chronological export)
    def get_entry_sort_key(e):
        entry_class = e['class']
        
        if entry_class == 'session':
            date_val = e.get('session_date', 0)
            session_num = e.get('session_number', 0) or 0
            return (date_val, session_num, e.get('created_at', 0))
        elif entry_class == 'communication':
            date_val = e.get('comm_date', 0)
        elif entry_class == 'absence':
            date_val = e.get('absence_date', 0)
        elif entry_class == 'item':
            date_val = e.get('item_date', 0)
        elif entry_class == 'upload':
            date_val = e.get('upload_date', 0)
        else:
            date_val = e.get('created_at', 0)
        
        return (date_val, 0, e.get('created_at', 0))
    
    all_entries.sort(key=get_entry_sort_key)
    
    # Build entries
    for entry in all_entries:
        entry_class = entry['class']
        
        if entry_class not in entry_types:
            continue
        
        if entry_class == 'profile':
            continue
        
        if entry_class == 'session':
            elements.extend(build_session_entry(entry, client, styles, signature_path, db))
        elif entry_class == 'communication':
            entry_elements, entry_pdfs = build_communication_entry_with_attachments(entry, client, styles, db)
            elements.extend(entry_elements)
            pdf_attachments.extend(entry_pdfs)
        elif entry_class == 'absence':
            elements.extend(build_absence_entry(entry, client, styles, currency_symbol))
        elif entry_class == 'item':
            elements.extend(build_item_entry(entry, client, styles, currency_symbol))
        elif entry_class == 'upload':
            entry_elements, entry_pdfs = build_upload_entry_with_attachments(entry, client, styles, db)
            elements.extend(entry_elements)
            pdf_attachments.extend(entry_pdfs)
        
        elements.append(PageBreak())
    
    # Remove last page break if present
    if elements and isinstance(elements[-1], PageBreak):
        elements.pop()
    
    # Build main PDF
    main_buffer = BytesIO()
    doc = SimpleDocTemplate(
        main_buffer,
        pagesize=letter,
        rightMargin=0.75*inch,
        leftMargin=0.75*inch,
        topMargin=0.75*inch,
        bottomMargin=0.75*inch
    )
    
    if elements:
        doc.build(elements)
    else:
        # Build a friendly message listing the selected types
        type_names = [t.capitalize() for t in entry_types]
        if len(type_names) == 1:
            type_str = type_names[0]
        elif len(type_names) == 2:
            type_str = f"{type_names[0]} or {type_names[1]}"
        else:
            type_str = ", ".join(type_names[:-1]) + f", or {type_names[-1]}"
        elements.append(Paragraph(f"No {type_str} entries found for the selected date range.", styles['FieldValue']))
        doc.build(elements)
    
    main_buffer.seek(0)
    
    # If no PDF attachments, return the main PDF
    if not pdf_attachments:
        if output_path:
            with open(output_path, 'wb') as f:
                f.write(main_buffer.read())
            return output_path
        else:
            return main_buffer
    
    # Merge PDF attachments
    pdf_writer = PdfWriter()
    
    # Add main PDF pages
    main_reader = PdfReader(main_buffer)
    for page in main_reader.pages:
        pdf_writer.add_page(page)
    
    # Add each PDF attachment with a header page
    for att_entry_type, att_title, att_date, att_filepath in pdf_attachments:
        if os.path.exists(att_filepath):
            try:
                # Create header page for this attachment
                header_buffer = BytesIO()
                header_doc = SimpleDocTemplate(
                    header_buffer,
                    pagesize=letter,
                    rightMargin=0.75*inch,
                    leftMargin=0.75*inch,
                    topMargin=2*inch,
                    bottomMargin=0.75*inch
                )
                header_elements = [
                    Paragraph("Attachment", styles['EntryTitle']),
                    Spacer(1, 12),
                    Paragraph(f"<b>{att_entry_type}:</b> {att_title}", styles['FieldValue']),
                    Spacer(1, 6),
                    Paragraph(f"<b>Date:</b> {att_date}", styles['FieldValue']),
                    Spacer(1, 24),
                    Paragraph(f"<i>Original filename: {os.path.basename(att_filepath)}</i>", styles['FieldValue']),
                ]
                header_doc.build(header_elements)
                header_buffer.seek(0)
                
                # Add header page
                header_reader = PdfReader(header_buffer)
                for page in header_reader.pages:
                    pdf_writer.add_page(page)
                
                # Add attachment pages (decrypt if needed)
                if db.password:
                    from core.encryption import decrypt_file_to_bytes
                    decrypted_data = decrypt_file_to_bytes(att_filepath, db.password)
                    att_buffer = BytesIO(decrypted_data)
                    att_reader = PdfReader(att_buffer)
                else:
                    att_reader = PdfReader(att_filepath)
                for page in att_reader.pages:
                    pdf_writer.add_page(page)
                    
            except Exception as e:
                # If we can't read the PDF, skip it
                print(f"Warning: Could not include attachment {att_filepath}: {e}")
    
    # Write final merged PDF
    if output_path:
        with open(output_path, 'wb') as f:
            pdf_writer.write(f)
        return output_path
    else:
        final_buffer = BytesIO()
        pdf_writer.write(final_buffer)
        final_buffer.seek(0)
        return final_buffer