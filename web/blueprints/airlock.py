"""AirLock screens: settings, invitations, and the review-and-import screen.

docs/Intake_Service_Plan.md. Everything here is dormant until an AirLock
server is configured (core/airlock_client.is_enabled): the Manage menu shows
no AirLock item and these pages send the practitioner to Settings.

Submissions are never cached in EdgeCase. The review screen fetches them from
the server, decrypts them in memory, and shows them; Import fetches and
decrypts again, writes the client file in one transaction, and only then asks
the server to delete them. A crash anywhere before that leaves the
submissions on the server to be reviewed again.
"""
import time

from flask import Blueprint, jsonify, redirect, render_template, request, url_for

from core import airlock_client, airlock_crypto
from core.airlock_client import AirLockConnectionError
from core.airlock_import import (AirLockImportError, import_client, parse_consent,
                                 parse_intake, possible_duplicates, profile_fields)
from core.file_numbers import FileNumberError, preview_file_number

airlock_bp = Blueprint('airlock', __name__)

db = None

# Fixed messages for ?msg= after a redirect: nothing user-supplied is ever
# reflected into the page.
MESSAGES = {
    'revoked': ('ok', 'Invitation revoked.'),
    'revoke_remote_failed': ('warn', 'Revoked here, but the AirLock server could not be '
                                     'told. The link may keep working until it expires; '
                                     'nothing it submits can be imported.'),
    'discarded': ('ok', 'Submission discarded and removed from the server.'),
    'discard_remote_failed': ('warn', 'Discarded here, but the submission could not be '
                                      'removed from the server. It will be removed at the '
                                      'next check.'),
    'cleanup_failed': ('warn', 'Imported. The submission could not be removed from the '
                               'server yet; it will be removed at the next check.'),
    'deleted': ('ok', 'Removed from the server.'),
    'not_ready': ('warn', 'That invitation has nothing ready to review.'),
}


def init_blueprint(database):
    global db
    db = database


@airlock_bp.app_context_processor
def _airlock_nav():
    try:
        return {'airlock_enabled': bool(db) and airlock_client.is_enabled(db)}
    except Exception:
        return {'airlock_enabled': False}


def _require_enabled():
    if not airlock_client.is_enabled(db):
        return redirect(url_for('settings.settings_page') + '#airlock')
    return None


def _message():
    return MESSAGES.get(request.args.get('msg', ''))


def _fmt(ts):
    from datetime import datetime
    return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M') if ts else ''


# ---------------------------------------------------------------------------
# fetching and opening submissions
# ---------------------------------------------------------------------------

def _fetch():
    """Submissions from the server, grouped by invitation. Records each form
    as received. Submissions for invitations already imported or revoked are
    deleted from the server on the spot: they are either safely in a client
    file or were discarded. Returns (by_invitation_id, unmatched)."""
    client = airlock_client.client_from_settings(db)
    by_inv, unmatched = {}, []
    for sub in client.list_submissions():
        inv = db.get_intake_invitation_by_hash(sub['token_hash'])
        if inv is None:
            unmatched.append(sub)
            continue
        if inv['status'] in ('imported', 'revoked'):
            try:
                client.delete_submission(sub['id'])
            except AirLockConnectionError:
                pass
            continue
        if sub['form'] in inv['required_forms']:
            db.record_intake_form_received(inv['id'], sub['form'])
        by_inv.setdefault(inv['id'], []).append(sub)
    return by_inv, unmatched


def _open(inv, subs):
    """Decrypt and parse one invitation's submissions. Returns
    (intake, consent, versions, received_at, problems). The AAD is built from
    EdgeCase's own record of the invitation; only the versions come from the
    server, and decryption fails unless they are the ones the browser used."""
    keys = db.airlock_private_keys()
    intake = consent = None
    versions, received, problems = {}, 0, []
    latest = {}
    for sub in subs:  # newest submission of each form wins
        if sub['form'] not in latest or sub['received_at'] > latest[sub['form']]['received_at']:
            latest[sub['form']] = sub
    for form, sub in latest.items():
        if form not in inv['required_forms']:
            problems.append(f'Unexpected form: {form}')
            continue
        try:
            aad = airlock_crypto.build_aad(inv['token_hash'], form,
                                           sub['config_version'], sub['consent_version'])
            plaintext = airlock_crypto.decrypt_envelope(sub['envelope'], keys, aad)
            if form == 'intake':
                intake = parse_intake(plaintext, inv['is_minor'])
                versions['config_version'] = sub['config_version']
            else:
                consent = parse_consent(plaintext)
                versions['consent_version'] = sub['consent_version']
            received = max(received, sub['received_at'])
        except (airlock_crypto.AirLockDecryptError, ValueError) as e:
            if isinstance(e, AirLockImportError):
                problems.extend(f'{form.capitalize()}: {p}' for p in e.problems)
            else:
                problems.append(f'The {form} form could not be decrypted.')
    for form in inv['required_forms']:
        if form not in latest:
            problems.append(f'The {form} form has not arrived.')
    return intake, consent, versions, received, problems


# ---------------------------------------------------------------------------
# invitations page
# ---------------------------------------------------------------------------

def _render_invitations(message=None, error=None, checked=None, unmatched=0, status=200):
    now = int(time.time())
    rows = db.list_intake_invitations(include_closed=True)
    for r in rows:
        r['effective_status'] = db.invitation_effective_status(r, now)
        r['issued_fmt'] = _fmt(r['issued_at'])
        r['expires_fmt'] = _fmt(r['expires_at'])
    return render_template(
        'airlock.html',
        ready=[r for r in rows if r['effective_status'] == 'complete'],
        open_rows=[r for r in rows if r['effective_status'] in ('issued', 'partial')],
        closed=[r for r in rows if r['effective_status'] in
                ('imported', 'revoked', 'expired')][:25],
        message=message, error=error, checked=checked, unmatched=unmatched,
        ttl_days=db.get_setting('airlock_ttl_days', '14')), status


@airlock_bp.route('/airlock')
def invitations():
    redirect_resp = _require_enabled()
    if redirect_resp:
        return redirect_resp
    return _render_invitations(message=_message(),
                               checked=request.args.get('checked', type=int),
                               unmatched=request.args.get('unmatched', type=int) or 0)


@airlock_bp.route('/airlock/check', methods=['POST'])
def check():
    redirect_resp = _require_enabled()
    if redirect_resp:
        return redirect_resp
    try:
        by_inv, unmatched = _fetch()
    except AirLockConnectionError as e:
        return _invitations_with_error(str(e))
    return redirect(url_for('airlock.invitations', checked=sum(len(v) for v in by_inv.values()),
                            unmatched=len(unmatched)))


def _invitations_with_error(error, status=200):
    return _render_invitations(error=error, status=status)


@airlock_bp.route('/airlock/invitations', methods=['POST'])
def issue():
    redirect_resp = _require_enabled()
    if redirect_resp:
        return redirect_resp
    forms = ('intake', 'consent') if request.form.get('forms', 'both') == 'both' else ('intake',)
    try:
        inv = db.create_intake_invitation(
            request.form.get('display_name', ''), email=request.form.get('email', ''),
            required_forms=forms, is_minor=bool(request.form.get('is_minor')),
            ttl_days=request.form.get('ttl_days') or db.get_setting('airlock_ttl_days', '14'))
    except ValueError as e:
        return _invitations_with_error(str(e), 400)
    try:
        client = airlock_client.client_from_settings(db)
        kid, public = db.airlock_public_key()
        client.put_public_key(kid, public)
        client.create_invitation(inv)
    except AirLockConnectionError as e:
        db.delete_unsent_intake_invitation(inv['id'])
        return _invitations_with_error(f'{e} The invitation was not created.', 502)
    return redirect(url_for('airlock.invitation', invitation_id=inv['id'], new=1))


@airlock_bp.route('/airlock/invitations/<int:invitation_id>')
def invitation(invitation_id):
    redirect_resp = _require_enabled()
    if redirect_resp:
        return redirect_resp
    inv = db.get_intake_invitation(invitation_id)
    if inv is None:
        return "Invitation not found", 404
    inv['effective_status'] = db.invitation_effective_status(inv)
    inv['issued_fmt'] = _fmt(inv['issued_at'])
    inv['expires_fmt'] = _fmt(inv['expires_at'])
    link = airlock_client.invitation_link(db, inv['token'])
    return render_template('airlock_invitation.html', inv=inv, link=link,
                           is_new=bool(request.args.get('new')), message=_message())


@airlock_bp.route('/airlock/invitations/<int:invitation_id>/revoke', methods=['POST'])
def revoke(invitation_id):
    redirect_resp = _require_enabled()
    if redirect_resp:
        return redirect_resp
    inv = db.get_intake_invitation(invitation_id)
    if inv is None or not db.revoke_intake_invitation(invitation_id):
        return redirect(url_for('airlock.invitations'))
    msg = 'revoked'
    try:
        airlock_client.client_from_settings(db).revoke_invitation(inv['token_hash'])
    except AirLockConnectionError:
        msg = 'revoke_remote_failed'
    return redirect(url_for('airlock.invitations', msg=msg))


# ---------------------------------------------------------------------------
# review, import, discard
# ---------------------------------------------------------------------------

@airlock_bp.route('/airlock/review/<int:invitation_id>')
def review(invitation_id):
    redirect_resp = _require_enabled()
    if redirect_resp:
        return redirect_resp
    inv = db.get_intake_invitation(invitation_id)
    if inv is None:
        return "Invitation not found", 404
    try:
        by_inv, _ = _fetch()
    except AirLockConnectionError as e:
        return _invitations_with_error(str(e))
    inv = db.get_intake_invitation(invitation_id)
    if inv['status'] != 'complete' or invitation_id not in by_inv:
        return redirect(url_for('airlock.invitations', msg='not_ready'))
    intake, consent, versions, received, problems = _open(inv, by_inv[invitation_id])
    return _render_review(inv, intake, consent, received, problems)


def _render_review(inv, intake, consent, received, problems, error=None, status=200):
    fmt = db.get_setting('file_number_format', 'manual')
    profile = profile_fields(intake, inv['is_minor']) if intake else None
    preview = ''
    if intake:
        f = intake['fields']
        preview = preview_file_number(db, f['first_name'], f['middle_name'], f['last_name'])
    return render_template(
        'airlock_review.html', inv=inv, intake=intake, consent=consent,
        profile=profile, received_fmt=_fmt(received), problems=problems, error=error,
        duplicates=possible_duplicates(db, intake) if intake else [],
        client_types=db.get_all_client_types(), file_number_format=fmt,
        file_number_preview=preview,
        can_import=bool(intake) and not problems and
        (consent is not None or 'consent' not in inv['required_forms'])), status


@airlock_bp.route('/airlock/review/<int:invitation_id>/import', methods=['POST'])
def do_import(invitation_id):
    redirect_resp = _require_enabled()
    if redirect_resp:
        return redirect_resp
    inv = db.get_intake_invitation(invitation_id)
    if inv is None:
        return "Invitation not found", 404
    try:
        by_inv, _ = _fetch()
    except AirLockConnectionError as e:
        return _invitations_with_error(str(e))
    inv = db.get_intake_invitation(invitation_id)
    subs = by_inv.get(invitation_id, [])
    if inv['status'] != 'complete' or not subs:
        return redirect(url_for('airlock.invitations', msg='not_ready'))
    intake, consent, versions, received, problems = _open(inv, subs)
    if problems or not intake:
        return _render_review(inv, intake, consent, received, problems, status=400)
    try:
        type_id = int(request.form.get('type_id', ''))
    except ValueError:
        type_id = 0
    try:
        client_id = import_client(
            db, invitation_id, intake, consent, type_id=type_id, received_at=received,
            versions=versions, manual_file_number=request.form.get('file_number', ''))
    except (AirLockImportError, FileNumberError) as e:
        msg = '; '.join(e.problems) if isinstance(e, AirLockImportError) else str(e)
        return _render_review(inv, intake, consent, received, [], error=msg, status=400)

    cleanup_ok = True
    client = airlock_client.client_from_settings(db)
    for sub in subs:
        try:
            client.delete_submission(sub['id'])
        except AirLockConnectionError:
            cleanup_ok = False
    target = url_for('clients.client_file', client_id=client_id)
    return redirect(target if cleanup_ok else
                    url_for('airlock.invitations', msg='cleanup_failed'))


@airlock_bp.route('/airlock/review/<int:invitation_id>/discard', methods=['POST'])
def discard(invitation_id):
    redirect_resp = _require_enabled()
    if redirect_resp:
        return redirect_resp
    inv = db.get_intake_invitation(invitation_id)
    if inv is None:
        return "Invitation not found", 404
    db.revoke_intake_invitation(invitation_id)
    msg = 'discarded'
    try:
        client = airlock_client.client_from_settings(db)
        for sub in client.list_submissions():
            if sub['token_hash'] == inv['token_hash']:
                client.delete_submission(sub['id'])
        client.revoke_invitation(inv['token_hash'])
    except AirLockConnectionError:
        msg = 'discard_remote_failed'
    return redirect(url_for('airlock.invitations', msg=msg))


@airlock_bp.route('/airlock/unmatched/delete', methods=['POST'])
def delete_unmatched():
    """Submissions under a token EdgeCase has no record of (for example an
    invitation from a database since restored from backup). They cannot be
    opened without the invitation, so the only thing to do is remove them."""
    redirect_resp = _require_enabled()
    if redirect_resp:
        return redirect_resp
    try:
        _, unmatched = _fetch()
        client = airlock_client.client_from_settings(db)
        for sub in unmatched:
            client.delete_submission(sub['id'])
    except AirLockConnectionError as e:
        return _invitations_with_error(str(e))
    return redirect(url_for('airlock.invitations', msg='deleted'))


# ---------------------------------------------------------------------------
# settings API (Settings → AirLock)
# ---------------------------------------------------------------------------

@airlock_bp.route('/api/airlock_settings', methods=['GET', 'POST'])
def airlock_settings():
    if request.method == 'GET':
        return jsonify({
            'server_url': db.get_setting('airlock_server_url', ''),
            'public_url': db.get_setting('airlock_public_url', ''),
            'has_admin_key': bool(db.get_setting('airlock_admin_key', '')),
            'ttl_days': db.get_setting('airlock_ttl_days', '14'),
        })
    data = request.get_json(silent=True) or {}
    if data.get('disable'):
        for key in ('airlock_server_url', 'airlock_admin_key'):
            db.set_setting(key, '')
        return jsonify({'success': True})
    try:
        server = airlock_client.validate_base_url(data.get('server_url', ''),
                                                  'AirLock server address')
        public = airlock_client.validate_base_url(data.get('public_url', ''),
                                                  'Client form address')
        raw_ttl = data.get('ttl_days')
        ttl = 14 if raw_ttl in (None, '') else int(raw_ttl)
        if not 1 <= ttl <= 90:
            raise ValueError('Expiry must be between 1 and 90 days')
    except (TypeError, ValueError) as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    admin_key = (data.get('admin_key') or '').strip()
    if not admin_key and not db.get_setting('airlock_admin_key', ''):
        return jsonify({'success': False, 'error': 'An admin key is required'}), 400
    db.set_setting('airlock_server_url', server)
    db.set_setting('airlock_public_url', public)
    db.set_setting('airlock_ttl_days', str(ttl))
    if admin_key:
        db.set_setting('airlock_admin_key', admin_key)
    return jsonify({'success': True})


@airlock_bp.route('/api/airlock_test', methods=['POST'])
def airlock_test():
    """Connect and push the current public key: proves the address, the admin
    key and the private network path in one go."""
    client = None
    try:
        client = airlock_client.client_from_settings(db)
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    if client is None:
        return jsonify({'success': False, 'error': 'AirLock is not configured'}), 400
    try:
        kid, public = db.airlock_public_key()
        client.put_public_key(kid, public)
    except AirLockConnectionError as e:
        return jsonify({'success': False, 'error': str(e)}), 502
    return jsonify({'success': True, 'key_id': kid})
