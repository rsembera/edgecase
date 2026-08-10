"""Statement delivery: PDF generation/serving, mark-sent, and email.

Extracted from the statements.py blueprint split.
"""
from flask import request, jsonify, after_this_request
from pathlib import Path
from datetime import datetime
import shutil
import time
import tempfile
from flask import send_file
from pdf.generator import generate_statement_pdf
from core.config import ASSETS_DIR, ATTACHMENTS_DIR
from web.blueprints.statements.common import statements_bp, get_db


def _private_pdf_dir() -> Path:
    """Create a private (0700, randomized name) temp dir for a generated PDF.

    Statement PDFs contain PHI, so they must not be written to the shared
    system temp dir under predictable names. mkdtemp gives an
    unguessable, owner-only directory; the user-facing filename
    (Statement_<file#>_<date>.pdf) is kept for the file inside it and for
    send_file's download_name. Callers are responsible for cleanup
    (shutil.rmtree of the returned dir).
    """
    return Path(tempfile.mkdtemp(prefix='edgecase-'))


def _load_portion_and_profile(cursor, portion_id):
    """Fetch a statement portion (joined with client + statement info) and
    the client's profile. Returns (portion, profile) or (None, None).

    Shared by email_preview and mark_sent so the two always see the same
    data — the preview must show exactly what a send would use.
    """
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
        return None, None

    columns = [col[0] for col in cursor.description]
    portion = dict(zip(columns, row))

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

    return portion, profile


def _compose_statement_email(db, portion, profile):
    """Build the default statement email for a portion.

    Returns (recipient_email, subject, body, billing_period). Pure
    composition — the single source of the recipient resolution (guardian 1/2
    vs client) and the templated subject/body, used by both the pre-send
    preview and the actual send so they can never drift apart.
    """
    if portion['guardian_number'] == 1 and profile:
        recipient_first_name = profile.get('guardian1_name', '').split()[0] if profile.get('guardian1_name') else portion['first_name']
        recipient_email = profile.get('guardian1_email', '')
    elif portion['guardian_number'] == 2 and profile:
        recipient_first_name = profile.get('guardian2_name', '').split()[0] if profile.get('guardian2_name') else portion['first_name']
        recipient_email = profile.get('guardian2_email', '')
    else:
        recipient_first_name = portion['first_name']
        recipient_email = profile.get('email', '') if profile else ''

    # Billing period from the statement description (e.g. "Statement Dec 2025")
    statement_description = portion.get('statement_description', '')
    billing_period = statement_description.replace('Statement ', '') if statement_description.startswith('Statement ') else statement_description

    email_body_template = db.get_setting('statement_email_body', '').strip()
    subject = f"Statement for {billing_period}"
    body = f"Dear {recipient_first_name},\n\nPlease find attached your statement for {billing_period}.\n\n{email_body_template}".strip()

    return recipient_email, subject, body, billing_period


@statements_bp.route('/email-preview/<int:portion_id>')
def email_preview(portion_id):
    """Return the composed statement email for review BEFORE sending.

    Read-only: no PDF is generated, no Communication entry is created, and
    the portion stays 'ready'. The frontend shows this in an editable modal;
    whatever the user approves there is posted back to mark-sent, which
    records it verbatim as the Communication entry — so the client file
    always contains the email that was actually sent, not the template.
    """
    db = get_db()
    conn = db.connect()
    cursor = conn.cursor()

    portion, profile = _load_portion_and_profile(cursor, portion_id)
    if not portion:
        return jsonify({'success': False, 'error': 'Statement portion not found'}), 404

    recipient_email, subject, body, _ = _compose_statement_email(db, portion, profile)

    return jsonify({
        'success': True,
        'recipient_email': recipient_email,
        'subject': subject,
        'body': body,
    })


@statements_bp.route('/mark-sent/<int:portion_id>', methods=['POST'])
def mark_sent(portion_id):
    """Mark a statement portion as sent - generates PDF, creates Communication entry, triggers email."""
    db = get_db()
    

    # Check if we should skip email (generate-only mode)
    skip_email = request.args.get('skip_email') == '1'

    # Optional user-edited subject/body from the pre-send review modal.
    # When present they are used verbatim for BOTH the outgoing email and
    # the Communication entry, so the record matches what was really sent.
    # Absent (skip_email / older callers) the composed defaults apply.
    payload = request.get_json(silent=True) or {}
    subject_override = (payload.get('subject') or '').strip()
    body_override = (payload.get('body') or '').strip()

    now = int(time.time())
    conn = db.connect()
    cursor = conn.cursor()

    portion, profile = _load_portion_and_profile(cursor, portion_id)
    if not portion:
        return jsonify({'success': False, 'error': 'Statement portion not found'}), 404

    recipient_email, email_subject, email_body, billing_period = \
        _compose_statement_email(db, portion, profile)
    if not skip_email:
        if subject_override:
            email_subject = subject_override
        if body_override:
            email_body = body_override

    # Get email settings
    email_method = db.get_setting('email_method', 'mailto')
    email_from = db.get_setting('email_from_address', '')
    
    # Generate PDF to a private temp dir (0700, randomized path). When the
    # email path is used, the path is handed to the frontend for the
    # AppleScript attach step, which deletes it afterwards.
    date_str = datetime.now().strftime('%Y%m%d')
    pdf_filename = f"Statement_{portion['file_number']}_{date_str}.pdf"
    temp_pdf_path = _private_pdf_dir() / pdf_filename

    try:
        generate_statement_pdf(db, portion_id, str(temp_pdf_path), str(ASSETS_DIR))
    except Exception as e:
        shutil.rmtree(temp_pdf_path.parent, ignore_errors=True)
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
    
    # Update statement portion status.
    #
    # A statement whose balance was already covered by credit at generation
    # goes straight to 'paid': it still had to be issued (the client gets a
    # document showing the credit applied), but there is nothing left to
    # collect, and leaving it 'sent' would park a $0.00 row in Outstanding
    # Statements forever with no action that clears it.
    cursor.execute("""
        UPDATE statement_portions
        SET status = CASE
                WHEN amount_paid >= amount_due THEN 'paid'
                ELSE 'sent'
            END,
            date_sent = ?
        WHERE id = ? AND status = 'ready'
    """, (now, portion_id))
    
    conn.commit()
    
    # Return different response based on skip_email
    if skip_email:
        # No email step needs the temp PDF (it was copied to attachments),
        # so clean it up now.
        shutil.rmtree(temp_pdf_path.parent, ignore_errors=True)
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


def _serve_statement_pdf(portion_id, *, as_attachment):
    """Generate a portion's PDF into a private temp dir and serve it.

    Shared by download_statement_pdf (as_attachment=True) and
    view_statement_pdf (as_attachment=False). The portion's PDF is rendered
    into a private (0700, randomized) temp dir that is removed once the
    response has been sent; the browser sees `filename` via download_name.
    """
    db = get_db()

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
    output_path = _private_pdf_dir() / filename

    try:
        generate_statement_pdf(db, portion_id, str(output_path), str(ASSETS_DIR))

        @after_this_request
        def cleanup(response):
            shutil.rmtree(output_path.parent, ignore_errors=True)
            return response

        return send_file(
            output_path,
            mimetype='application/pdf',
            as_attachment=as_attachment,
            download_name=filename
        )
    except Exception as e:
        shutil.rmtree(output_path.parent, ignore_errors=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@statements_bp.route('/pdf/<int:portion_id>')
def download_statement_pdf(portion_id):
    """Generate and download a PDF statement for a portion."""
    return _serve_statement_pdf(portion_id, as_attachment=True)


@statements_bp.route('/view-pdf/<int:portion_id>')
def view_statement_pdf(portion_id):
    """Generate and view a PDF statement in browser."""
    return _serve_statement_pdf(portion_id, as_attachment=False)


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
    
    # Escape for AppleScript string and handle newlines
    # AppleScript doesn't interpret \n - need to use return character
    def escape_for_applescript(s):
        if not s:
            return ''
        return s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '" & return & "')
    
    subject_escaped = escape_for_applescript(subject)
    body_escaped = escape_for_applescript(body)
    recipient_escaped = escape_for_applescript(recipient)
    pdf_path_escaped = escape_for_applescript(pdf_path)
    email_from_escaped = escape_for_applescript(email_from)
    
    # Build AppleScript - use plain text content
    applescript = f'''
    tell application "Mail"
        set newMessage to make new outgoing message with properties {{subject:"{subject_escaped}", content:"{body_escaped}", visible:true}}
        
        tell newMessage
            make new to recipient at end of to recipients with properties {{address:"{recipient_escaped}"}}
            
            if "{pdf_path_escaped}" is not "" then
                make new attachment with properties {{file name:POSIX file "{pdf_path_escaped}"}} at after last paragraph
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
                if (email addresses of acct) contains "{email_from_escaped}" then
                    set senderAccount to acct
                    exit repeat
                end if
            end repeat
            
            set newMessage to make new outgoing message with properties {{subject:"{subject_escaped}", content:"{body_escaped}", visible:true}}
            
            if senderAccount is not null then
                set sender of newMessage to "{email_from_escaped}"
            end if
            
            tell newMessage
                make new to recipient at end of to recipients with properties {{address:"{recipient_escaped}"}}
                
                if "{pdf_path_escaped}" is not "" then
                    make new attachment with properties {{file name:POSIX file "{pdf_path_escaped}"}} at after last paragraph
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
        
        # Clean up temp PDF after AppleScript has attached it. Only ever
        # delete paths under the system temp dir (the path comes from the
        # client); PDFs now live in a private edgecase- mkdtemp dir, so
        # remove that whole dir, not just the file.
        if pdf_path:
            try:
                pdf_path_obj = Path(pdf_path).resolve()
                tmp_root = Path(tempfile.gettempdir()).resolve()
                if pdf_path_obj.exists() and tmp_root in pdf_path_obj.parents:
                    parent = pdf_path_obj.parent
                    if parent != tmp_root and parent.name.startswith('edgecase-'):
                        shutil.rmtree(parent, ignore_errors=True)
                    else:
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
