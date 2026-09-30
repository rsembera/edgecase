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

from flask import (Blueprint, current_app, jsonify, redirect, render_template, request,
                   url_for)

from core import airlock_client, airlock_config, airlock_crypto
from core import airlock_import as ai
from core.config import get_assets_path
from core.airlock_client import AirLockConnectionError
from core.airlock_import import (AirLockImportError, import_client, parse_consent,
                                 parse_intake, review_rows)

airlock_bp = Blueprint('airlock', __name__)

db = None

# Fixed messages for ?msg= after a redirect: nothing user-supplied is ever
# reflected into the page.
MESSAGES = {
    'revoked': ('ok', 'Invitation revoked.'),
    'dismissed': ('ok', 'Expired invitation dismissed.'),
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
    'consent_saved': ('ok', 'Consent text saved and sent to the AirLock server.'),
    'consent_saved_local': ('warn', 'Consent text saved here, but the AirLock server could '
                                    'not be reached. It will be sent before the next '
                                    'invitation.'),
}


def init_blueprint(database):
    global db
    db = database


@airlock_bp.app_context_processor
def _airlock_nav():
    try:
        return {'airlock_enabled': bool(db) and airlock_client.is_enabled(db),
                'airlock_in_progress': db.client_intake_in_progress}
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


def _push_setup(client):
    """Send the public key and the current form bundle. Done before every
    invitation, so the server always has what the new link will need."""
    kid, public = db.airlock_public_key()
    client.put_public_key(kid, public)
    bundle = airlock_config.build_bundle(db, airlock_config.load_config(db),
                                         str(get_assets_path()))
    airlock_config.remember_consent_version(db, bundle['consent_version'])
    client.put_config(bundle)
    return bundle


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
    server, and decryption fails unless they are the ones the browser used.
    A consent is also checked against EdgeCase's own record of the texts it
    has sent out (ai.consent_version_problem); one that fails is still
    returned, so the review can show what it says, but it cannot be imported."""
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
                problem = ai.consent_version_problem(
                    consent, sub['consent_version'],
                    airlock_config.known_consent_versions(db))
                if problem:
                    problems.append(problem)
            received = max(received, sub['received_at'])
        except (airlock_crypto.AirLockDecryptError, ValueError) as e:
            if isinstance(e, AirLockImportError):
                problems.extend(f'{form.capitalize()}: {p}' for p in e.problems)
            else:
                problems.append(f'The {form} form could not be decrypted.')
        except Exception:
            # A submission is hostile input. Whatever it manages to trip, the
            # review screen still has to open: that is where the problem is
            # shown and where Discard is.
            current_app.logger.exception('AirLock: unexpected error opening the %s form', form)
            problems.append(f'The {form} form could not be read.')
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
        # Expired ones stay until dismissed or replaced, so a client who
        # never did their forms doesn't just vanish from the page.
        open_rows=[r for r in rows if r['effective_status'] in ('issued', 'partial', 'expired')],
        message=message, error=error, checked=checked, unmatched=unmatched,
        ttl_days=db.get_setting('airlock_ttl_days', '14')), status


@airlock_bp.route('/airlock')
def invitations():
    redirect_resp = _require_enabled()
    if redirect_resp:
        return redirect_resp
    checked = request.args.get('checked', type=int)
    unmatched = request.args.get('unmatched', type=int) or 0
    error = None
    if checked is None and request.method == 'GET':
        # Check the server on every visit (the ntfy ping says "open AirLock"),
        # quietly: the lists show the result. The button stays for re-checks.
        try:
            _, unmatched_subs = _fetch()
            unmatched = len(unmatched_subs)
        except AirLockConnectionError as e:
            error = f'{e} Showing what was last received.'
    return _render_invitations(message=_message(), error=error, checked=checked,
                               unmatched=unmatched)


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


def _client_name(client):
    return " ".join(p for p in (client.get('first_name'), client.get('last_name')) if p)


@airlock_bp.route('/airlock/invite/<int:client_id>', methods=['GET', 'POST'])
def invite(client_id):
    """Issue an invitation from a client file. The invitation carries the
    client's id, so the import fills in this file."""
    redirect_resp = _require_enabled()
    if redirect_resp:
        return redirect_resp
    client = db.get_client(client_id)
    if client is None:
        return "Client not found", 404
    profile = db.get_profile_entry(client_id) or {}
    in_progress, in_progress_id = db.client_intake_in_progress(client_id)
    ctx = {'client': client, 'name': _client_name(client), 'profile': profile,
           'in_progress': in_progress, 'in_progress_id': in_progress_id,
           'ttl_days': db.get_setting('airlock_ttl_days', '14'),
           'has_consent': bool(airlock_config.load_config(db)['consent_text'])}
    if request.method != 'POST':  # GET, and the HEAD probe base.html sends before navigating
        return render_template('airlock_invite.html', **ctx)
    if in_progress:   # one invitation per client at a time (decided 2026-09-30)
        return render_template('airlock_invite.html', **ctx), 409

    forms = ('intake', 'consent') if request.form.get('forms', 'both') == 'both' else ('intake',)
    if 'consent' in forms and not ctx['has_consent']:
        return render_template('airlock_invite.html', error='Add your consent text on the '
                               'Consent page before inviting a client to sign it.', **ctx), 400
    try:
        inv = db.create_intake_invitation(
            ctx['name'], email=profile.get('email') or '', required_forms=forms,
            is_minor=bool(request.form.get('is_minor')), client_id=client_id,
            ttl_days=request.form.get('ttl_days') or ctx['ttl_days'])
    except ValueError as e:
        return render_template('airlock_invite.html', error=str(e), **ctx), 400
    try:
        ac = airlock_client.client_from_settings(db)
        _push_setup(ac)
        ac.create_invitation(inv)
    except AirLockConnectionError as e:
        db.delete_unsent_intake_invitation(inv['id'])
        return render_template('airlock_invite.html',
                               error=f'{e} The invitation was not created.', **ctx), 502
    # The new invitation replaces any expired one for this client.
    for old in db.list_intake_invitations(include_closed=True):
        if (old['client_id'] == client_id and old['id'] != inv['id']
                and db.invitation_effective_status(old) == 'expired'):
            db.revoke_intake_invitation(old['id'])
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
    msg = 'dismissed' if db.invitation_effective_status(inv) == 'expired' else 'revoked'
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
    client = db.get_client(inv['client_id']) if inv.get('client_id') else None
    if intake and client is None:
        problems = list(problems) + ['This invitation is not linked to a client file, so '
                                     'there is nothing to fill in. Discard it and send a '
                                     'new one from the client file.']
    rows = review_rows(db, client['id'], intake, inv['is_minor']) if intake and client else []
    return render_template(
        'airlock_review.html', inv=inv, intake=intake, consent=consent, client=client,
        rows=rows, changed=sum(r['status'] in ('new', 'changed') for r in rows),
        received_fmt=_fmt(received), problems=problems, error=error,
        can_import=bool(intake) and client is not None and not problems and
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
        client_id = import_client(
            db, invitation_id, intake, consent, received_at=received, versions=versions,
            keep=request.form.getlist('keep'))
    except AirLockImportError as e:
        return _render_review(inv, intake, consent, received, [],
                              error='; '.join(e.problems), status=400)

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
# consent text
# ---------------------------------------------------------------------------

@airlock_bp.route('/airlock/consent', methods=['GET', 'POST'])
def consent():
    redirect_resp = _require_enabled()
    if redirect_resp:
        return redirect_resp
    if request.method != 'POST':  # GET, and the HEAD probe base.html sends before navigating
        return _render_consent(airlock_config.load_config(db)['consent_text'],
                               message=_message())
    text = request.form.get('consent_text', '')
    try:
        cfg = airlock_config.validate_config({'consent_text': text})
    except ValueError as e:
        return _render_consent(text, error=str(e), status=400)
    airlock_config.save_config(db, cfg)
    try:
        _push_setup(airlock_client.client_from_settings(db))
        msg = 'consent_saved'
    except AirLockConnectionError:
        msg = 'consent_saved_local'
    return redirect(url_for('airlock.consent', msg=msg))


def _render_consent(consent_text, message=None, error=None, status=200):
    return render_template('airlock_consent.html', consent_text=consent_text,
                           message=message, error=error), status


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
    if admin_key and not airlock_client.valid_admin_key(admin_key):
        return jsonify({'success': False, 'error': airlock_client.BAD_KEY_MESSAGE}), 400
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
        _push_setup(client)
    except AirLockConnectionError as e:
        return jsonify({'success': False, 'error': str(e)}), 502
    return jsonify({'success': True, 'key_id': db.airlock_public_key()[0]})
