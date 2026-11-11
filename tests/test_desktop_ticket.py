"""The desktop shell's file fetches are authorised by a single-use ticket.

desktop.py opens PDFs and downloads attachments with a plain Python request,
which has no session cookie. After sessions became per-client (2026-06-09)
that request was redirected to the login page and the login page's HTML was
saved/opened as the document. web/session_state.py.
"""
import time

import pytest

from web.app import app as flask_app
from web.session_state import DESKTOP_TICKET_HEADER, issue_desktop_ticket

URL = '/api/restore-message'   # any authenticated GET


def _get(ticket=None, method='get'):
    headers = {DESKTOP_TICKET_HEADER: ticket} if ticket else {}
    return getattr(flask_app.test_client(), method)(URL, headers=headers)


def test_cookieless_fetch_is_refused_without_a_ticket(client, app_db):
    assert _get().status_code in (302, 401)


def test_ticket_authorises_one_cookieless_get(client, app_db):
    ticket = issue_desktop_ticket(flask_app)
    assert _get(ticket).status_code == 200
    assert _get(ticket).status_code in (302, 401)       # spent


def test_ticket_is_get_only(client, app_db):
    ticket = issue_desktop_ticket(flask_app)
    resp = flask_app.test_client().post(
        '/api/time_format', json={'time_format': '24h'},
        headers={DESKTOP_TICKET_HEADER: ticket})
    assert resp.status_code == 401
    assert app_db.get_setting('time_format', '12h') == '12h'


def test_expired_and_invented_tickets_are_refused(client, app_db):
    ticket = issue_desktop_ticket(flask_app)
    flask_app.config['DESKTOP_TICKETS'][ticket] = time.time() - 1
    assert _get(ticket).status_code in (302, 401)
    assert _get('made-up').status_code in (302, 401)


def test_ticket_does_not_open_a_locked_practice(client, app_db):
    ticket = issue_desktop_ticket(flask_app)
    flask_app.config['db'] = None
    assert _get(ticket).status_code in (302, 401)


def test_desktop_api_sends_a_ticket_and_does_not_follow_redirects(monkeypatch):
    monkeypatch.setenv('EDGECASE_DESKTOP', '1')   # desktop.py sets it on import
    import desktop
    import requests

    seen = {}

    class LoginRedirect:
        status_code = 302
        headers = {}
        content = b'<html>login</html>'

    def fake_get(url, **kwargs):
        seen.update(kwargs, url=url)
        return LoginRedirect()

    monkeypatch.setattr(requests, 'get', fake_get)
    api = desktop.Api(8080)

    assert api.open_file('/statements/view-pdf/1') is False
    assert seen['url'] == 'http://localhost:8080/statements/view-pdf/1'
    assert seen['allow_redirects'] is False
    assert seen['headers'][DESKTOP_TICKET_HEADER] in flask_app.config['DESKTOP_TICKETS']
    assert api.download_file('/attachment/1/download') is None
