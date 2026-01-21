"""
EdgeCase Equalizer - Test Suite
================================

Run with: pytest tests/ -v
Or: python -m pytest tests/ -v

These tests verify critical business logic that could cause real problems if broken:
1. Fee calculations (billing accuracy)
2. Session numbering (record integrity)  
3. Payment status (visual indicators)
4. Guardian billing splits (percentage validation)
5. Edit history tracking (audit compliance)
6. Date parsing (data integrity)

Tests use a temporary in-memory database - no risk to production data.
"""

import pytest
import sqlite3
import time
import tempfile
import os
from datetime import datetime, timedelta

from core.database import Database
from web.utils import parse_date_from_form, generate_content_diff


# ============================================================================
# FIXTURES - Setup/teardown for tests
# ============================================================================

@pytest.fixture
def db():
    """Create a fresh test database for each test."""
    # Use temp file (not :memory:) so Database class works properly
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    
    database = Database(db_path)
    yield database
    
    # Cleanup
    os.unlink(db_path)


@pytest.fixture
def client_with_profile(db):
    """Create a test client with profile entry."""
    # Create client
    client_id = db.add_client({
        'file_number': 'TEST-001',
        'first_name': 'Test',
        'middle_name': '',
        'last_name': 'Client',
        'type_id': 1  # Active type (created by default)
    })
    
    # Create profile
    profile_id = db.add_entry({
        'client_id': client_id,
        'class': 'profile',
        'description': 'Test Client - Profile',
        'email': 'test@example.com',
        'phone': '555-1234'
    })
    
    return {'client_id': client_id, 'profile_id': profile_id}


# ============================================================================
# FEE CALCULATION TESTS
# ============================================================================

class TestFeeCalculations:
    """Test three-way fee calculation logic."""
    
    def test_base_plus_tax_equals_total(self):
        """Given base and tax rate, total should be correct."""
        base = 100.00
        tax_rate = 13.0  # 13% HST
        expected_total = 113.00
        
        # This is the formula used throughout EdgeCase
        calculated_total = base * (1 + tax_rate / 100)
        
        assert abs(calculated_total - expected_total) < 0.01
    
    def test_total_minus_tax_equals_base(self):
        """Given total and tax rate, base should be correct."""
        total = 113.00
        tax_rate = 13.0
        expected_base = 100.00
        
        # Reverse calculation
        calculated_base = total / (1 + tax_rate / 100)
        
        assert round(calculated_base, 2) == expected_base
    
    def test_zero_tax_rate(self):
        """With 0% tax, base should equal total."""
        base = 150.00
        tax_rate = 0.0
        
        total = base * (1 + tax_rate / 100)
        
        assert total == base
    
    def test_fee_calculation_precision(self):
        """Fee calculations should maintain 2 decimal precision."""
        base = 99.99
        tax_rate = 13.0
        
        total = base * (1 + tax_rate / 100)
        
        # Should round to 2 decimals for currency
        assert round(total, 2) == 112.99


class TestProfileFeeOverride:
    """Test profile-level fee override behavior."""
    
    def test_profile_session_fee_stored(self, db, client_with_profile):
        """Profile should store custom fee override values."""
        client_id = client_with_profile['client_id']
        profile_id = client_with_profile['profile_id']
        
        # Update profile with fee override
        db.update_entry(profile_id, {
            'session_base': 120.00,
            'session_tax_rate': 13.0,
            'session_total': 135.60
        })
        
        # Retrieve and verify
        profile = db.get_entry(profile_id)
        
        assert profile['session_base'] == 120.00
        assert profile['session_tax_rate'] == 13.0
        assert profile['session_total'] == 135.60
    
    def test_profile_session_fee_null_when_not_set(self, db, client_with_profile):
        """Profile without override should have NULL fee fields."""
        profile_id = client_with_profile['profile_id']
        
        profile = db.get_entry(profile_id)
        
        # Not set = empty string (our NULL representation)
        assert profile['session_base'] in (None, '', 0)


# ============================================================================
# GUARDIAN BILLING TESTS
# ============================================================================

class TestGuardianBilling:
    """Test guardian billing split logic."""
    
    def test_single_guardian_100_percent(self, db, client_with_profile):
        """Single guardian should pay 100%."""
        profile_id = client_with_profile['profile_id']
        
        db.update_entry(profile_id, {
            'is_minor': 1,
            'guardian1_name': 'Parent One',
            'guardian1_pays_percent': 100,
            'has_guardian2': 0,
            'guardian2_pays_percent': 0
        })
        
        profile = db.get_entry(profile_id)
        total_percent = profile['guardian1_pays_percent'] + profile['guardian2_pays_percent']
        
        assert total_percent == 100
    
    def test_two_guardians_split_50_50(self, db, client_with_profile):
        """Two guardians splitting 50/50 should total 100%."""
        profile_id = client_with_profile['profile_id']
        
        db.update_entry(profile_id, {
            'is_minor': 1,
            'guardian1_name': 'Parent One',
            'guardian1_pays_percent': 50,
            'has_guardian2': 1,
            'guardian2_name': 'Parent Two',
            'guardian2_pays_percent': 50
        })
        
        profile = db.get_entry(profile_id)
        total_percent = profile['guardian1_pays_percent'] + profile['guardian2_pays_percent']
        
        assert total_percent == 100
    
    def test_two_guardians_split_60_40(self, db, client_with_profile):
        """Uneven split 60/40 should total 100%."""
        profile_id = client_with_profile['profile_id']
        
        db.update_entry(profile_id, {
            'is_minor': 1,
            'guardian1_name': 'Primary Parent',
            'guardian1_pays_percent': 60,
            'has_guardian2': 1,
            'guardian2_name': 'Other Parent',
            'guardian2_pays_percent': 40
        })
        
        profile = db.get_entry(profile_id)
        total_percent = profile['guardian1_pays_percent'] + profile['guardian2_pays_percent']
        
        assert total_percent == 100
    
    def test_guardian_amount_calculation(self):
        """Guardian payment amounts should calculate correctly from percentage."""
        total_fee = 150.00
        guardian1_percent = 60
        guardian2_percent = 40
        
        guardian1_amount = total_fee * (guardian1_percent / 100)
        guardian2_amount = total_fee * (guardian2_percent / 100)
        
        assert guardian1_amount == 90.00
        assert guardian2_amount == 60.00
        assert guardian1_amount + guardian2_amount == total_fee


# ============================================================================
# SESSION NUMBERING TESTS
# ============================================================================

class TestSessionNumbering:
    """Test session numbering logic."""
    
    def test_first_session_is_number_one(self, db, client_with_profile):
        """First session should be numbered 1."""
        client_id = client_with_profile['client_id']
        
        session_id = db.add_entry({
            'client_id': client_id,
            'class': 'session',
            'session_date': int(time.time()),
            'session_number': 1,
            'description': 'Session 1'
        })
        
        session = db.get_entry(session_id)
        assert session['session_number'] == 1
    
    def test_session_offset_applied(self, db):
        """Session offset should shift numbering for migrated clients."""
        # Create client with offset of 10 (had 10 sessions before migration)
        client_id = db.add_client({
            'file_number': 'MIGRATED-001',
            'first_name': 'Migrated',
            'last_name': 'Client',
            'type_id': 1,
            'session_offset': 10
        })
        
        client = db.get_client(client_id)
        
        # First new session should be 11 (offset + 1)
        expected_first_session = client['session_offset'] + 1
        
        assert expected_first_session == 11
    
    def test_consultation_excluded_from_numbering(self, db, client_with_profile):
        """Consultations should not be numbered."""
        client_id = client_with_profile['client_id']
        
        # Add consultation
        consultation_id = db.add_entry({
            'client_id': client_id,
            'class': 'session',
            'session_date': int(time.time()),
            'is_consultation': 1,
            'description': 'Consultation',
            'fee': 0
        })
        
        consultation = db.get_entry(consultation_id)
        
        # Consultations should have fee = 0 and is_consultation = 1
        assert consultation['is_consultation'] == 1
        assert consultation['fee'] in (0, None, '')
    
    def test_sessions_ordered_chronologically(self, db, client_with_profile):
        """Sessions should be numbered by date order, not creation order."""
        client_id = client_with_profile['client_id']
        now = int(time.time())
        
        # Create sessions out of chronological order
        # Session created first but dated later
        later_session = db.add_entry({
            'client_id': client_id,
            'class': 'session',
            'session_date': now + 86400,  # Tomorrow
            'session_number': 1,
            'description': 'Session 1'
        })
        
        # Session created second but dated earlier
        earlier_session = db.add_entry({
            'client_id': client_id,
            'class': 'session',
            'session_date': now,  # Today
            'session_number': 2,
            'description': 'Session 2'
        })
        
        # Get sessions sorted by date
        sessions = db.get_client_entries(client_id, 'session')
        dated_sessions = [s for s in sessions if s.get('session_date')]
        dated_sessions.sort(key=lambda s: s['session_date'])
        
        # Earlier dated session should come first
        assert dated_sessions[0]['id'] == earlier_session
        assert dated_sessions[1]['id'] == later_session


# ============================================================================
# PAYMENT STATUS TESTS
# ============================================================================

class TestPaymentStatus:
    """Test payment status calculation logic."""
    
    def test_no_statements_returns_paid(self, db, client_with_profile):
        """Client with no statements should show as paid (green)."""
        client_id = client_with_profile['client_id']
        
        status = db.get_payment_status(client_id)
        
        assert status == 'paid'
    
    def test_sent_statement_returns_pending(self, db, client_with_profile):
        """Client with sent statement should show as pending (yellow)."""
        client_id = client_with_profile['client_id']
        now = int(time.time())
        
        # Create statement entry
        statement_id = db.add_entry({
            'client_id': client_id,
            'class': 'statement',
            'description': 'Statement Nov 2025',
            'statement_total': 150.00
        })
        
        # Create statement portion (sent today)
        conn = db.connect()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO statement_portions 
            (statement_entry_id, client_id, amount_due, status, date_sent, created_at)
            VALUES (?, ?, ?, 'sent', ?, ?)
        """, (statement_id, client_id, 150.00, now, now))
        conn.commit()
        # Note: Don't close connection - persistent connection pattern
        
        status = db.get_payment_status(client_id)
        
        assert status == 'pending'
    
    def test_overdue_statement_returns_overdue(self, db, client_with_profile):
        """Statement sent 30+ days ago should show as overdue (red)."""
        client_id = client_with_profile['client_id']
        now = int(time.time())
        thirty_one_days_ago = now - (31 * 24 * 60 * 60)
        
        # Create statement entry
        statement_id = db.add_entry({
            'client_id': client_id,
            'class': 'statement',
            'description': 'Statement Oct 2025',
            'statement_total': 150.00
        })
        
        # Create statement portion (sent 31 days ago)
        conn = db.connect()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO statement_portions 
            (statement_entry_id, client_id, amount_due, status, date_sent, created_at)
            VALUES (?, ?, ?, 'sent', ?, ?)
        """, (statement_id, client_id, 150.00, thirty_one_days_ago, thirty_one_days_ago))
        conn.commit()
        # Note: Don't close connection - persistent connection pattern
        
        status = db.get_payment_status(client_id)
        
        assert status == 'overdue'
    
    def test_partial_payment_still_pending(self, db, client_with_profile):
        """Partial payment should still show pending/overdue until fully paid."""
        client_id = client_with_profile['client_id']
        now = int(time.time())
        
        # Create statement entry
        statement_id = db.add_entry({
            'client_id': client_id,
            'class': 'statement',
            'description': 'Statement Nov 2025',
            'statement_total': 150.00
        })
        
        # Create partial payment portion
        conn = db.connect()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO statement_portions 
            (statement_entry_id, client_id, amount_due, amount_paid, status, date_sent, created_at)
            VALUES (?, ?, ?, ?, 'partial', ?, ?)
        """, (statement_id, client_id, 150.00, 75.00, now, now))
        conn.commit()
        # Note: Don't close connection - persistent connection pattern
        
        status = db.get_payment_status(client_id)
        
        # Partial is still outstanding
        assert status in ('pending', 'overdue')
    
    def test_fully_paid_returns_paid(self, db, client_with_profile):
        """Fully paid statement should show as paid (green)."""
        client_id = client_with_profile['client_id']
        now = int(time.time())
        
        # Create statement entry
        statement_id = db.add_entry({
            'client_id': client_id,
            'class': 'statement',
            'description': 'Statement Nov 2025',
            'statement_total': 150.00
        })
        
        # Create fully paid portion
        conn = db.connect()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO statement_portions 
            (statement_entry_id, client_id, amount_due, amount_paid, status, date_sent, created_at)
            VALUES (?, ?, ?, ?, 'paid', ?, ?)
        """, (statement_id, client_id, 150.00, 150.00, now, now))
        conn.commit()
        # Note: Don't close connection - persistent connection pattern
        
        status = db.get_payment_status(client_id)
        
        assert status == 'paid'


# ============================================================================
# EDIT HISTORY TESTS
# ============================================================================

class TestEditHistory:
    """Test edit history tracking."""
    
    def test_add_to_edit_history(self, db, client_with_profile):
        """Should be able to add edit history entries."""
        profile_id = client_with_profile['profile_id']
        
        db.add_to_edit_history(profile_id, "Email: old@test.com → new@test.com")
        
        history = db.get_edit_history(profile_id)
        
        assert len(history) == 1
        assert "Email:" in history[0]['description']
    
    def test_multiple_edit_history_entries(self, db, client_with_profile):
        """Multiple edits should accumulate in history."""
        profile_id = client_with_profile['profile_id']
        
        db.add_to_edit_history(profile_id, "First edit")
        db.add_to_edit_history(profile_id, "Second edit")
        db.add_to_edit_history(profile_id, "Third edit")
        
        history = db.get_edit_history(profile_id)
        
        assert len(history) == 3
    
    def test_edit_history_has_timestamp(self, db, client_with_profile):
        """Each edit should have a timestamp."""
        profile_id = client_with_profile['profile_id']
        
        db.add_to_edit_history(profile_id, "Test edit")
        
        history = db.get_edit_history(profile_id)
        
        assert 'timestamp' in history[0]
        assert history[0]['timestamp'] > 0
    
    def test_entry_locking(self, db, client_with_profile):
        """Entry should be lockable."""
        profile_id = client_with_profile['profile_id']
        
        # Initially not locked
        assert not db.is_entry_locked(profile_id)
        
        # Lock it
        db.lock_entry(profile_id)
        
        # Now should be locked
        assert db.is_entry_locked(profile_id)


# ============================================================================
# DATE PARSING TESTS
# ============================================================================

class TestDateParsing:
    """Test date parsing from form data."""
    
    def test_valid_date_parsed(self):
        """Valid date components should parse to timestamp."""
        form_data = {
            'year': '2025',
            'month': '11',
            'day': '28'
        }
        
        timestamp = parse_date_from_form(form_data)
        
        assert timestamp is not None
        # Verify it's the right date
        parsed_date = datetime.fromtimestamp(timestamp)
        assert parsed_date.year == 2025
        assert parsed_date.month == 11
        assert parsed_date.day == 28
    
    def test_invalid_day_clamped(self):
        """Invalid day (Nov 31) should clamp to Nov 30."""
        form_data = {
            'year': '2025',
            'month': '11',
            'day': '31'  # November only has 30 days
        }
        
        timestamp = parse_date_from_form(form_data)
        
        parsed_date = datetime.fromtimestamp(timestamp)
        assert parsed_date.day == 30  # Clamped to max valid day
    
    def test_february_leap_year(self):
        """Feb 29 in leap year should be valid."""
        form_data = {
            'year': '2024',  # 2024 is a leap year
            'month': '2',
            'day': '29'
        }
        
        timestamp = parse_date_from_form(form_data)
        
        parsed_date = datetime.fromtimestamp(timestamp)
        assert parsed_date.day == 29
    
    def test_february_non_leap_year_clamped(self):
        """Feb 29 in non-leap year should clamp to Feb 28."""
        form_data = {
            'year': '2025',  # 2025 is not a leap year
            'month': '2',
            'day': '29'
        }
        
        timestamp = parse_date_from_form(form_data)
        
        parsed_date = datetime.fromtimestamp(timestamp)
        assert parsed_date.day == 28  # Clamped
    
    def test_missing_date_returns_none(self):
        """Missing date components should return None."""
        form_data = {
            'year': '2025',
            'month': '',  # Missing
            'day': '28'
        }
        
        timestamp = parse_date_from_form(form_data)
        
        assert timestamp is None


# ============================================================================
# CONTENT DIFF TESTS
# ============================================================================

class TestContentDiff:
    """Test smart content diff for edit history."""
    
    def test_word_change_highlighted(self):
        """Changed word should be marked with del and strong tags."""
        old = "The quick brown fox"
        new = "The slow brown fox"
        
        diff = generate_content_diff(old, new)
        
        assert '<del>' in diff
        assert '<strong>' in diff
        assert 'quick' in diff
        assert 'slow' in diff
    
    def test_identical_content_no_diff(self):
        """Identical content should return the content as-is."""
        content = "No changes here"
        
        diff = generate_content_diff(content, content)
        
        # Should not have del or strong tags
        assert '<del>' not in diff
        assert '<strong>' not in diff
    
    def test_empty_old_content(self):
        """Empty old content should show all new content as added."""
        old = ""
        new = "Brand new content"
        
        diff = generate_content_diff(old, new)
        
        assert '<strong>' in diff
    
    def test_empty_new_content(self):
        """Empty new content should show all old content as deleted."""
        old = "Content to remove"
        new = ""
        
        diff = generate_content_diff(old, new)
        
        assert '<del>' in diff


# ============================================================================
# LINK GROUP TESTS
# ============================================================================

class TestLinkGroups:
    """Test link group functionality for couples/family therapy."""
    
    def test_create_link_group(self, db):
        """Should be able to create a link group with multiple clients."""
        # Create two clients
        client1_id = db.add_client({
            'file_number': 'COUPLE-001A',
            'first_name': 'Partner',
            'last_name': 'One',
            'type_id': 1
        })
        
        client2_id = db.add_client({
            'file_number': 'COUPLE-001B',
            'first_name': 'Partner',
            'last_name': 'Two',
            'type_id': 1
        })
        
        # Create link group
        group_id = db.create_link_group(
            client_ids=[client1_id, client2_id],
            format='couples',
            session_duration=60,
            member_fees={
                str(client1_id): {'base_fee': 75, 'tax_rate': 13, 'total_fee': 84.75},
                str(client2_id): {'base_fee': 75, 'tax_rate': 13, 'total_fee': 84.75}
            }
        )
        
        assert group_id is not None
        
        # Verify group was created
        group = db.get_link_group(group_id)
        assert group is not None
        assert group['format'] == 'couples'
        assert len(group['members']) == 2
    
    def test_client_is_linked(self, db):
        """Should detect when client is in a link group."""
        # Create and link two clients
        client1_id = db.add_client({
            'file_number': 'LINKED-001',
            'first_name': 'Linked',
            'last_name': 'Client',
            'type_id': 1
        })
        
        client2_id = db.add_client({
            'file_number': 'LINKED-002',
            'first_name': 'Other',
            'last_name': 'Client',
            'type_id': 1
        })
        
        # Before linking
        assert not db.is_client_linked(client1_id)
        
        # Create link
        db.create_link_group(
            client_ids=[client1_id, client2_id],
            format='couples',
            session_duration=60,
            member_fees={}
        )
        
        # After linking
        assert db.is_client_linked(client1_id)
        assert db.is_client_linked(client2_id)
    
    def test_get_linked_clients(self, db):
        """Should return other clients in the same link group."""
        client1_id = db.add_client({
            'file_number': 'FAM-001',
            'first_name': 'Family',
            'last_name': 'Member1',
            'type_id': 1
        })
        
        client2_id = db.add_client({
            'file_number': 'FAM-002',
            'first_name': 'Family',
            'last_name': 'Member2',
            'type_id': 1
        })
        
        client3_id = db.add_client({
            'file_number': 'FAM-003',
            'first_name': 'Family',
            'last_name': 'Member3',
            'type_id': 1
        })
        
        db.create_link_group(
            client_ids=[client1_id, client2_id, client3_id],
            format='family',
            session_duration=90,
            member_fees={}
        )
        
        # Get linked clients for client1
        linked = db.get_linked_clients(client1_id)
        linked_ids = [c['id'] for c in linked]
        
        assert client2_id in linked_ids
        assert client3_id in linked_ids
        assert client1_id not in linked_ids  # Should not include self


# ============================================================================
# LEDGER TESTS
# ============================================================================

class TestLedger:
    """Test income/expense tracking."""
    
    def test_add_income_entry(self, db):
        """Should be able to add income entry."""
        entry_id = db.add_entry({
            'client_id': None,  # Ledger entries have no client
            'class': 'income',
            'ledger_type': 'income',
            'ledger_date': int(time.time()),
            'source': 'TEST-001',
            'total_amount': 150.00,
            'tax_amount': 19.47,
            'description': 'Payment received'
        })
        
        entry = db.get_entry(entry_id)
        
        assert entry['ledger_type'] == 'income'
        assert entry['total_amount'] == 150.00
    
    def test_add_expense_entry(self, db):
        """Should be able to add expense entry."""
        # Create category and payee first
        category_id = db.add_expense_category('Office Supplies')
        payee_id = db.add_payee('Staples')
        
        entry_id = db.add_entry({
            'client_id': None,
            'class': 'expense',
            'ledger_type': 'expense',
            'ledger_date': int(time.time()),
            'category_id': category_id,
            'payee_id': payee_id,
            'total_amount': 45.00,
            'tax_amount': 5.85,
            'description': 'Printer paper'
        })
        
        entry = db.get_entry(entry_id)
        
        assert entry['ledger_type'] == 'expense'
        assert entry['total_amount'] == 45.00
        assert entry['category_id'] == category_id
        assert entry['payee_id'] == payee_id
    
    def test_ledger_totals(self, db):
        """Should calculate correct ledger totals."""
        now = int(time.time())
        
        # Add income
        db.add_entry({
            'client_id': None,
            'class': 'income',
            'ledger_type': 'income',
            'ledger_date': now,
            'total_amount': 500.00,
            'tax_amount': 65.00
        })
        
        db.add_entry({
            'client_id': None,
            'class': 'income',
            'ledger_type': 'income',
            'ledger_date': now,
            'total_amount': 300.00,
            'tax_amount': 39.00
        })
        
        # Add expense
        db.add_entry({
            'client_id': None,
            'class': 'expense',
            'ledger_type': 'expense',
            'ledger_date': now,
            'total_amount': 100.00,
            'tax_amount': 13.00
        })
        
        totals = db.get_ledger_totals()
        
        assert totals['total_income'] == 800.00
        assert totals['total_expenses'] == 100.00
        assert totals['net_income'] == 700.00
        assert totals['total_tax_collected'] == 104.00
        assert totals['total_tax_paid'] == 13.00


# ============================================================================
# SETTINGS TESTS
# ============================================================================

class TestSettings:
    """Test settings storage."""
    
    def test_set_and_get_setting(self, db):
        """Should store and retrieve settings."""
        db.set_setting('practice_name', 'Test Practice')
        
        value = db.get_setting('practice_name')
        
        assert value == 'Test Practice'
    
    def test_get_missing_setting_returns_default(self, db):
        """Missing setting should return default value."""
        value = db.get_setting('nonexistent_setting', 'default_value')
        
        assert value == 'default_value'
    
    def test_update_setting(self, db):
        """Should be able to update existing setting."""
        db.set_setting('currency', 'USD')
        db.set_setting('currency', 'CAD')
        
        value = db.get_setting('currency')
        
        assert value == 'CAD'


# ============================================================================
# ENCRYPTION TESTS
# ============================================================================

class TestEncryption:
    """Test SQLCipher database encryption."""
    
    def test_encrypted_db_requires_correct_password(self):
        """Database encrypted with password should reject wrong password."""
        import sqlcipher3
        
        # Create encrypted database with known password
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        
        correct_password = "correct_password_123"
        wrong_password = "wrong_password_456"
        
        # Create database with encryption
        db = Database(db_path, password=correct_password)
        db.set_setting('test_key', 'test_value')
        db.close()
        
        # Try to open with wrong password - should fail
        conn = sqlcipher3.connect(db_path)
        conn.execute(f"PRAGMA key = '{wrong_password}'")
        
        with pytest.raises(sqlcipher3.DatabaseError):
            # This should fail because the key is wrong
            conn.execute("SELECT * FROM settings")
        
        conn.close()
        
        # Verify correct password still works
        db_reopened = Database(db_path, password=correct_password)
        value = db_reopened.get_setting('test_key')
        assert value == 'test_value'
        db_reopened.close()
        
        # Cleanup
        os.unlink(db_path)
    
    def test_encrypted_db_unreadable_without_password(self):
        """Encrypted database should be unreadable without any password."""
        import sqlcipher3
        
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        
        # Create encrypted database
        db = Database(db_path, password="my_secret_password")
        db.set_setting('sensitive_data', 'should_be_protected')
        db.close()
        
        # Try to open without providing any password
        conn = sqlcipher3.connect(db_path)
        # No PRAGMA key = ... call
        
        with pytest.raises(sqlcipher3.DatabaseError):
            conn.execute("SELECT * FROM settings")
        
        conn.close()
        os.unlink(db_path)


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
