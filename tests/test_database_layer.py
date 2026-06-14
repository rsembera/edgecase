"""
EdgeCase Equalizer - Data-Layer Test Suite
===========================================

Round-trip / behavioural coverage for core.database.Database methods that the
existing test_edgecase.py suite exercises only indirectly, or not at all.

Purpose: a safety net for the planned database.py refactor (splitting the
~2,350-line god object by domain). These tests pin down the *observable
behaviour* of the data layer so a structural refactor that changes behaviour
is caught. Assertions are deliberately round-trip / behavioural rather than
asserting exact full-row dict shapes, so they survive benign refactors.

Covers:
  - Client lifecycle: add / get / get_all (+ type filter, is_deleted exclusion)
    / update (+ column whitelist) / search (+ wildcard escaping) /
    file_number_exists / get_profile_entry / get_last_session_date
  - Client types: CRUD + system-type guards on update and delete
  - Retention & deletion lifecycle (PHIPA): archive_and_delete_client,
    get_deleted_clients, snapshot_retention_on_inactive,
    get_clients_due_for_deletion
  - Ledger queries: get_all_ledger_entries (+ filter, name joins),
    get_ledger_entry, get_ledger_entries_by_date_range

Uses a temporary unencrypted test database - no risk to production data.
"""

import os
import time
import tempfile

import pytest

from core.database import Database


@pytest.fixture
def db():
    """Fresh temp-file database per test."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    database = Database(db_path)
    yield database
    os.unlink(db_path)


def _add_client(db, file_number='F-001', first='Ada', last='Lovelace',
                type_id=1, **extra):
    data = {'file_number': file_number, 'first_name': first,
            'middle_name': '', 'last_name': last, 'type_id': type_id}
    data.update(extra)
    return db.add_client(data)


def _set_modified_at(db, client_id, ts):
    """White-box helper: backdate a client's modified_at (the retention
    sweep's last-contact fallback) so expiry can be exercised."""
    conn = db.connect()
    conn.execute("UPDATE clients SET modified_at = ? WHERE id = ?", (ts, client_id))
    conn.commit()


# ===========================================================================
# CLIENT LIFECYCLE
# ===========================================================================

class TestClientLifecycle:

    def test_add_and_get_roundtrip(self, db):
        cid = _add_client(db, file_number='F-100', first='Ada', last='Byron')
        c = db.get_client(cid)
        assert c is not None
        assert c['file_number'] == 'F-100'
        assert c['first_name'] == 'Ada'
        assert c['last_name'] == 'Byron'
        assert c['is_deleted'] == 0

    def test_get_client_missing_returns_none(self, db):
        assert db.get_client(999999) is None

    def test_file_number_exists(self, db):
        assert db.file_number_exists('F-200') is False
        _add_client(db, file_number='F-200')
        assert db.file_number_exists('F-200') is True

    def test_get_all_clients_and_type_filter(self, db):
        t2 = db.add_client_type({'name': 'Couples', 'color': '#abc'})
        a = _add_client(db, file_number='F-001', type_id=1)
        b = _add_client(db, file_number='F-002', type_id=t2)
        all_ids = {c['id'] for c in db.get_all_clients()}
        assert {a, b} <= all_ids
        type1_ids = {c['id'] for c in db.get_all_clients(type_id=1)}
        assert a in type1_ids
        assert b not in type1_ids

    def test_get_all_clients_excludes_deleted(self, db):
        cid = _add_client(db, file_number='F-DEL')
        db.update_client(cid, {'is_deleted': 1})
        ids = {c['id'] for c in db.get_all_clients()}
        assert cid not in ids

    def test_update_client_roundtrip(self, db):
        cid = _add_client(db, first='Grace', last='Hopper')
        assert db.update_client(cid, {'last_name': 'Murray',
                                      'session_offset': 3}) is True
        c = db.get_client(cid)
        assert c['last_name'] == 'Murray'
        assert c['session_offset'] == 3

    def test_update_client_rejects_unknown_column(self, db):
        cid = _add_client(db)
        with pytest.raises(ValueError):
            db.update_client(cid, {'note': 'not a real column'})

    def test_search_clients_matches_name_and_file_number(self, db):
        _add_client(db, file_number='ABC-1', first='Margaret', last='Hamilton')
        by_name = db.search_clients('Hamilton')
        assert any(c['file_number'] == 'ABC-1' for c in by_name)
        by_file = db.search_clients('ABC-1')
        assert any(c['first_name'] == 'Margaret' for c in by_file)

    def test_search_clients_escapes_wildcards(self, db):
        # A literal '%' search must match the '%' literally, not act as a
        # wildcard that returns everyone (CODE_REVIEW.md L14).
        _add_client(db, file_number='REAL-1', first='Real', last='Person')
        _add_client(db, file_number='100%-OFF', first='Sale', last='Tag')
        files = {c['file_number'] for c in db.search_clients('%')}
        assert '100%-OFF' in files
        assert 'REAL-1' not in files

    def test_search_clients_excludes_deleted(self, db):
        cid = _add_client(db, file_number='GONE-1', first='Vanish', last='Ing')
        db.update_client(cid, {'is_deleted': 1})
        assert db.search_clients('Vanish') == []

    def test_get_profile_entry(self, db):
        cid = _add_client(db)
        assert db.get_profile_entry(cid) is None
        db.add_entry({'client_id': cid, 'class': 'profile',
                      'description': 'Profile', 'email': 'a@b.ca'})
        prof = db.get_profile_entry(cid)
        assert prof is not None
        assert prof['email'] == 'a@b.ca'

    def test_get_last_session_date(self, db):
        cid = _add_client(db)
        assert db.get_last_session_date(cid) == 0
        db.add_entry({'client_id': cid, 'class': 'session',
                      'session_date': 1000, 'description': 's1'})
        db.add_entry({'client_id': cid, 'class': 'session',
                      'session_date': 2000, 'description': 's2'})
        assert db.get_last_session_date(cid) == 2000


# ===========================================================================
# CLIENT TYPES (incl. system-type guards)
# ===========================================================================

class TestClientTypes:

    def test_add_get_roundtrip(self, db):
        tid = db.add_client_type({'name': 'Group', 'color': '#123456',
                                  'retention_period': 1000})
        t = db.get_client_type(tid)
        assert t['name'] == 'Group'
        assert t['color'] == '#123456'
        assert t['retention_period'] == 1000

    def test_get_all_ordered_by_name(self, db):
        db.add_client_type({'name': 'Zeta', 'color': '#000'})
        db.add_client_type({'name': 'Alpha', 'color': '#fff'})
        names = [t['name'] for t in db.get_all_client_types()]
        assert names == sorted(names)

    def test_update_normal_type(self, db):
        tid = db.add_client_type({'name': 'Temp', 'color': '#111'})
        assert db.update_client_type(tid, {'name': 'Renamed',
                                           'color': '#222'}) is True
        assert db.get_client_type(tid)['name'] == 'Renamed'

    def test_update_missing_type_returns_false(self, db):
        assert db.update_client_type(
            999999, {'name': 'X', 'color': '#000'}) is False

    def test_update_refuses_rename_of_locked_type(self, db):
        tid = db.add_client_type({'name': 'Locked', 'color': '#111',
                                  'is_system_locked': 1})
        # Rename refused (retention sweep keys off this flag, CODE_REVIEW.md M10)
        assert db.update_client_type(tid, {'name': 'NewName',
                                           'color': '#111'}) is False
        assert db.get_client_type(tid)['name'] == 'Locked'
        # ...but a same-name update (e.g. colour change) is still allowed
        assert db.update_client_type(tid, {'name': 'Locked',
                                           'color': '#999'}) is True
        assert db.get_client_type(tid)['color'] == '#999'

    def test_delete_normal_type(self, db):
        tid = db.add_client_type({'name': 'Disposable', 'color': '#111'})
        assert db.delete_client_type(tid) is True
        assert db.get_client_type(tid) is None

    def test_delete_refuses_system_type(self, db):
        tid = db.add_client_type({'name': 'SysType', 'color': '#111',
                                  'is_system': 1})
        assert db.delete_client_type(tid) is False
        assert db.get_client_type(tid) is not None

    def test_delete_refuses_type_in_use(self, db):
        tid = db.add_client_type({'name': 'InUse', 'color': '#111'})
        _add_client(db, file_number='USE-1', type_id=tid)
        assert db.delete_client_type(tid) is False
        assert db.get_client_type(tid) is not None


# ===========================================================================
# RETENTION & DELETION LIFECYCLE (PHIPA-critical)
# ===========================================================================

class TestRetentionLifecycle:

    def test_archive_and_delete_removes_client_and_archives(self, db):
        cid = _add_client(db, file_number='ARCH-1', first='Del', last='Eted')
        db.add_entry({'client_id': cid, 'class': 'session',
                      'session_date': 1000, 'description': 's'})
        assert db.archive_and_delete_client(cid) is True
        # Client and its entries are gone...
        assert db.get_client(cid) is None
        assert db.get_profile_entry(cid) is None
        # ...and a redacted archive record remains for the deletion log.
        archived = db.get_deleted_clients()
        rec = next((a for a in archived if a['file_number'] == 'ARCH-1'), None)
        assert rec is not None
        assert rec['full_name'] == 'Del Eted'
        assert rec['deleted_at'] > 0

    def test_archive_missing_client_returns_false(self, db):
        assert db.archive_and_delete_client(999999) is False

    def test_snapshot_retention_sets_days(self, db):
        cid = _add_client(db, file_number='RET-1')
        db.snapshot_retention_on_inactive(cid, 2555)
        assert db.get_client(cid)['retention_days'] == 2555

    def test_due_for_deletion_includes_expired_inactive(self, db):
        # The Inactive workflow type is identified by is_system_locked = 1.
        tid = db.add_client_type({'name': 'InactiveTest', 'color': '#888',
                                  'is_system_locked': 1})
        cid = _add_client(db, file_number='DUE-1', first='Past', last='Due',
                          type_id=tid)
        db.snapshot_retention_on_inactive(cid, 1)  # 1-day retention
        _set_modified_at(db, cid, int(time.time()) - 30 * 86400)
        due_ids = {d['id'] for d in db.get_clients_due_for_deletion()}
        assert cid in due_ids

    def test_zero_retention_means_keep_forever(self, db):
        tid = db.add_client_type({'name': 'InactiveTest', 'color': '#888',
                                  'is_system_locked': 1})
        cid = _add_client(db, file_number='KEEP-1', type_id=tid)
        db.snapshot_retention_on_inactive(cid, 0)  # 0 == keep forever
        _set_modified_at(db, cid, int(time.time()) - 9999 * 86400)
        due_ids = {d['id'] for d in db.get_clients_due_for_deletion()}
        assert cid not in due_ids

    def test_within_window_not_due(self, db):
        tid = db.add_client_type({'name': 'InactiveTest', 'color': '#888',
                                  'is_system_locked': 1})
        cid = _add_client(db, file_number='FRESH-1', type_id=tid)
        db.snapshot_retention_on_inactive(cid, 3650)  # 10 years, modified now
        due_ids = {d['id'] for d in db.get_clients_due_for_deletion()}
        assert cid not in due_ids


# ===========================================================================
# LEDGER QUERIES
# ===========================================================================

class TestLedgerQueries:

    def _add_income(self, db, amount, date, **extra):
        data = {'client_id': None, 'class': 'income', 'ledger_type': 'income',
                'ledger_date': date, 'total_amount': amount, 'tax_amount': 0}
        data.update(extra)
        return db.add_entry(data)

    def _add_expense(self, db, amount, date, **extra):
        data = {'client_id': None, 'class': 'expense', 'ledger_type': 'expense',
                'ledger_date': date, 'total_amount': amount, 'tax_amount': 0}
        data.update(extra)
        return db.add_entry(data)

    def test_get_all_ledger_entries_returns_both(self, db):
        now = int(time.time())
        self._add_income(db, 100.0, now)
        self._add_expense(db, 40.0, now)
        all_e = db.get_all_ledger_entries()
        assert len(all_e) == 2
        assert {e['ledger_type'] for e in all_e} == {'income', 'expense'}

    def test_get_all_ledger_entries_filtered(self, db):
        now = int(time.time())
        self._add_income(db, 100.0, now)
        self._add_expense(db, 40.0, now)
        income = db.get_all_ledger_entries('income')
        assert len(income) == 1
        assert income[0]['ledger_type'] == 'income'

    def test_get_all_ledger_entries_joins_names(self, db):
        now = int(time.time())
        cat = db.add_expense_category('Rent')
        pay = db.add_payee('Landlord Co')
        self._add_expense(db, 1200.0, now, category_id=cat, payee_id=pay)
        e = db.get_all_ledger_entries('expense')[0]
        assert e['category_name'] == 'Rent'
        assert e['payee_name'] == 'Landlord Co'
        assert e['attachment_count'] == 0

    def test_get_ledger_entry_matches_get_entry(self, db):
        eid = self._add_income(db, 250.0, int(time.time()))
        assert db.get_ledger_entry(eid) == db.get_entry(eid)

    def test_get_ledger_entries_by_date_range(self, db):
        base = 1_600_000_000
        day = 86400
        self._add_income(db, 10.0, base)             # in range
        self._add_income(db, 20.0, base + 5 * day)   # in range
        self._add_income(db, 30.0, base + 60 * day)  # out of range
        got = db.get_ledger_entries_by_date_range(base, base + 10 * day)
        assert sorted(e['total_amount'] for e in got) == [10.0, 20.0]
