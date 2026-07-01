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
import time
import tempfile
import os
from datetime import datetime, timedelta

from core.database import Database
from web.utils import parse_date_from_form, generate_content_diff, generate_full_content_diff


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

class TestClientBalances:
    """Client-file financial summary: unbilled owing + outstanding statements."""

    def _add_billable_session(self, db, client_id, fee, locked=1, statement_id=None):
        return db.add_entry({
            'client_id': client_id,
            'class': 'session',
            'session_date': int(time.time()),
            'session_number': 1,
            'description': 'Session',
            'fee': fee,
            'locked': locked,
            'statement_id': statement_id,
        })

    # --- get_unbilled_total ---

    def test_unbilled_zero_with_no_entries(self, db, client_with_profile):
        assert db.get_unbilled_total(client_with_profile['client_id']) == 0

    def test_unbilled_sums_locked_billable_sessions(self, db, client_with_profile):
        client_id = client_with_profile['client_id']
        self._add_billable_session(db, client_id, 150.00)
        self._add_billable_session(db, client_id, 90.50)
        assert db.get_unbilled_total(client_id) == Decimal('240.50')

    def test_unbilled_excludes_drafts(self, db, client_with_profile):
        """Unlocked drafts aren't billable, so they don't count."""
        client_id = client_with_profile['client_id']
        self._add_billable_session(db, client_id, 150.00, locked=0)
        assert db.get_unbilled_total(client_id) == 0

    def test_unbilled_excludes_already_billed(self, db, client_with_profile):
        """Entries attached to a statement are billed, not unbilled."""
        client_id = client_with_profile['client_id']
        stmt_id = db.add_entry({
            'client_id': client_id, 'class': 'statement',
            'description': 'Statement', 'statement_total': 150.00,
        })
        self._add_billable_session(db, client_id, 150.00, statement_id=stmt_id)
        assert db.get_unbilled_total(client_id) == 0

    def test_unbilled_excludes_consultation_and_pro_bono(self, db, client_with_profile):
        """fee = 0 entries (consultations, pro bono) never bill."""
        client_id = client_with_profile['client_id']
        db.add_entry({
            'client_id': client_id, 'class': 'session',
            'session_date': int(time.time()), 'is_consultation': 1,
            'description': 'Consultation', 'fee': 0, 'locked': 1,
        })
        db.add_entry({
            'client_id': client_id, 'class': 'session',
            'session_date': int(time.time()), 'is_pro_bono': 1,
            'description': 'Pro bono', 'fee': 0, 'locked': 1,
        })
        self._add_billable_session(db, client_id, 100.00)
        assert db.get_unbilled_total(client_id) == Decimal('100.00')

    def test_unbilled_item_uses_base_price_fallback(self, db, client_with_profile):
        """Items with no `fee` fall back to base_price, mirroring find_unbilled."""
        client_id = client_with_profile['client_id']
        db.add_entry({
            'client_id': client_id, 'class': 'item',
            'item_date': int(time.time()), 'description': 'Report',
            'base_price': 75.00, 'locked': 1,
        })
        assert db.get_unbilled_total(client_id) == Decimal('75.00')

    # --- get_outstanding_balance ---

    def _add_portion(self, db, client_id, amount_due, status, amount_paid=0):
        now = int(time.time())
        stmt_id = db.add_entry({
            'client_id': client_id, 'class': 'statement',
            'description': 'Statement', 'statement_total': amount_due,
        })
        conn = db.connect()
        conn.cursor().execute("""
            INSERT INTO statement_portions
            (statement_entry_id, client_id, amount_due, amount_paid, status, date_sent, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (stmt_id, client_id, amount_due, amount_paid, status, now, now))
        conn.commit()

    def test_outstanding_zero_with_no_portions(self, db, client_with_profile):
        assert db.get_outstanding_balance(client_with_profile['client_id']) == 0

    def test_outstanding_sums_sent_portions(self, db, client_with_profile):
        client_id = client_with_profile['client_id']
        self._add_portion(db, client_id, 150.00, 'sent')
        self._add_portion(db, client_id, 50.00, 'sent')
        assert db.get_outstanding_balance(client_id) == Decimal('200.00')

    def test_outstanding_subtracts_partial_payment(self, db, client_with_profile):
        client_id = client_with_profile['client_id']
        self._add_portion(db, client_id, 150.00, 'partial', amount_paid=40.00)
        assert db.get_outstanding_balance(client_id) == Decimal('110.00')

    def test_outstanding_excludes_paid_and_written_off(self, db, client_with_profile):
        client_id = client_with_profile['client_id']
        self._add_portion(db, client_id, 150.00, 'paid', amount_paid=150.00)
        self._add_portion(db, client_id, 80.00, 'written_off')
        self._add_portion(db, client_id, 25.00, 'sent')
        assert db.get_outstanding_balance(client_id) == Decimal('25.00')


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
# MONEY ARITHMETIC (CODE_REVIEW.md M1 / L11)
# ============================================================================
# These tests exercise the REAL production code in core.money and
# core.billing (used by web/blueprints/statements.py) — unlike the older
# fee tests, they do not re-implement the formulas they verify.

from decimal import Decimal

from core.money import dec, quantize_cents, to_cents, money_float
from core.billing import (
    entry_fee, entry_tax, compute_statement_totals,
    split_guardian_amounts, apply_payment, prorata_tax,
)


def _session(fee, base_fee):
    return {'class': 'session', 'fee': fee, 'base_fee': base_fee}


def _item(fee, base_price, g1=None, g2=None):
    e = {'class': 'item', 'fee': fee, 'base_price': base_price}
    if g1 is not None:
        e['guardian1_amount'] = g1
        e['guardian2_amount'] = g2
    return e


class TestMoneyPrimitives:
    """core.money: quantization, cents, storage round-trip."""

    def test_dec_handles_db_and_form_values(self):
        assert dec(None) == Decimal('0')
        assert dec('') == Decimal('0')
        assert dec(113.0) == Decimal('113')
        assert dec('33.33') == Decimal('33.33')

    def test_quantize_rounds_half_up(self):
        assert quantize_cents('1.005') == Decimal('1.01')
        assert quantize_cents('1.004') == Decimal('1.00')

    def test_storage_round_trip_is_exact_cents(self):
        # Every value stored via money_float recovers exact cents
        for raw in ('0.01', '33.33', '99.99', '12345.67', '0.10'):
            stored = money_float(raw)          # float in the REAL column
            assert to_cents(stored) == to_cents(raw)

    def test_float_accumulation_bug_does_not_survive(self):
        # 10 × $0.10 in floats is 0.9999999999999999; in our pipeline
        # it's exactly $1.00
        total = sum((quantize_cents('0.10') for _ in range(10)), dec(0))
        assert to_cents(total) == 100


class TestStatementTotals:
    """compute_statement_totals against entry fee/tax fallbacks."""

    def test_totals_and_tax(self):
        entries = [
            _session(113.0, 100.0),     # $13 tax
            _session(56.50, 50.0),      # $6.50 tax
            _item(22.60, 20.0),         # $2.60 tax
        ]
        total, tax = compute_statement_totals(entries)
        assert total == Decimal('192.10')
        assert tax == Decimal('22.10')

    def test_legacy_fallbacks_and_negative_tax_clamp(self):
        # absence with no fee falls back to base_fee; fee < base clamps tax to 0
        entries = [
            {'class': 'absence', 'fee': None, 'base_fee': 75.0},
            _session(90.0, 100.0),      # discounted below base: no negative tax
        ]
        total, tax = compute_statement_totals(entries)
        assert total == Decimal('165.00')
        assert tax == Decimal('0.00')


class TestGuardianSplitRounding:
    """split_guardian_amounts: the odd-cent cases that matter for billing."""

    def test_single_guardian_pays_full_total(self):
        # Percent is ignored without a second guardian (H3)
        profile = {'is_minor': 1, 'guardian1_name': 'G1',
                   'guardian1_pays_percent': 60,
                   'has_guardian2': 0, 'guardian2_name': None}
        entries = [_session(113.0, 100.0)]
        total, _ = compute_statement_totals(entries)
        portions = split_guardian_amounts(entries, profile, total)
        assert portions == [(1, Decimal('113.00'))]

    def test_two_guardian_odd_cent_remainder_goes_to_g2(self):
        # $33.33 at 50%: G1 gets 16.67 (half-up), G2 the exact remainder
        profile = {'is_minor': 1, 'guardian1_name': 'G1',
                   'guardian1_pays_percent': 50,
                   'has_guardian2': 1, 'guardian2_name': 'G2'}
        entries = [_session(33.33, 33.33)]
        total, _ = compute_statement_totals(entries)
        portions = dict(split_guardian_amounts(entries, profile, total))
        assert portions[1] == Decimal('16.67')
        assert portions[2] == Decimal('16.66')
        assert portions[1] + portions[2] == total

    def test_portions_always_sum_to_total_across_many_lines(self):
        profile = {'is_minor': 1, 'guardian1_name': 'G1',
                   'guardian1_pays_percent': 33,
                   'has_guardian2': 1, 'guardian2_name': 'G2'}
        entries = [_session(33.33, 30.0), _session(77.77, 70.0),
                   _session(101.01, 90.0), _item(0.05, 0.05)]
        total, _ = compute_statement_totals(entries)
        portions = dict(split_guardian_amounts(entries, profile, total))
        assert portions[1] + portions[2] == total

    def test_explicit_item_amounts_honored(self):
        profile = {'is_minor': 1, 'guardian1_name': 'G1',
                   'guardian1_pays_percent': 50,
                   'has_guardian2': 1, 'guardian2_name': 'G2'}
        entries = [
            _item(100.0, 100.0, g1=70.0, g2=30.0),  # explicit split
            _session(50.0, 50.0),                    # percentage split
        ]
        total, _ = compute_statement_totals(entries)
        portions = dict(split_guardian_amounts(entries, profile, total))
        assert portions[1] == Decimal('70.00') + Decimal('25.00')
        assert portions[2] == Decimal('30.00') + Decimal('25.00')
        assert portions[1] + portions[2] == total

    def test_hundred_percent_g1_leaves_no_g2_portion(self):
        profile = {'is_minor': 1, 'guardian1_name': 'G1',
                   'guardian1_pays_percent': 100,
                   'has_guardian2': 1, 'guardian2_name': 'G2'}
        entries = [_session(113.0, 100.0)]
        total, _ = compute_statement_totals(entries)
        portions = split_guardian_amounts(entries, profile, total)
        assert portions == [(1, Decimal('113.00'))]


class TestPaymentApplication:
    """apply_payment: exact-cent status decisions, no epsilon fudge."""

    def test_exact_payment_is_paid(self):
        paid, owing, status = apply_payment(113.0, 0, 113.0)
        assert status == 'paid'
        assert to_cents(owing) == 0

    def test_one_cent_short_is_partial_not_paid(self):
        # The old `<= 0.01` float fudge wrongly marked this 'paid'
        paid, owing, status = apply_payment(100.0, 0, 99.99)
        assert status == 'partial'
        assert owing == Decimal('0.01')

    def test_partial_payments_accumulate_to_exactly_paid(self):
        due = 100.30
        paid = 0
        for amount, expected in ((33.43, 'partial'), (33.43, 'partial'),
                                 (33.44, 'paid')):
            paid, owing, status = apply_payment(due, paid, amount)
            assert status == expected
        assert to_cents(owing) == 0

    def test_ten_dimes_pay_a_dollar(self):
        # Classic float-accumulation failure case
        due = 1.00
        paid = 0
        for i in range(10):
            paid, owing, status = apply_payment(due, paid, 0.10)
        assert status == 'paid'
        assert to_cents(owing) == 0

    def test_overpayment_is_paid(self):
        _, owing, status = apply_payment(100.0, 0, 120.0)
        assert status == 'paid'
        assert owing == Decimal('-20.00')


class TestProrataTaxAndRefunds:
    """prorata_tax for payments and refund reversal (L11)."""

    def test_full_payment_collects_full_tax(self):
        assert prorata_tax(113.0, 13.0, 113.0) == Decimal('13.00')

    def test_partial_payment_collects_proportional_tax(self):
        # Half the statement -> half the tax
        assert prorata_tax(56.50, 13.0, 113.0) == Decimal('6.50')

    def test_refund_reverses_tax_proportionally(self):
        # L11: a full refund must reverse exactly what was collected
        collected = prorata_tax(113.0, 13.0, 113.0)
        reversed_tax = prorata_tax(abs(-113.0), 13.0, 113.0)
        assert reversed_tax == collected == Decimal('13.00')

    def test_no_tax_statement_yields_zero(self):
        assert prorata_tax(100.0, 0, 100.0) == Decimal('0.00')
        assert prorata_tax(100.0, 13.0, 0) == Decimal('0.00')


# ============================================================================
# FOREIGN KEY ENFORCEMENT (CODE_REVIEW.md M2)
# ============================================================================

class TestForeignKeyEnforcement:
    """PRAGMA foreign_keys=ON is set per connection (enabled after the
    production-DB orphan audit came back clean)."""

    def test_pragma_is_on(self, db):
        cursor = db.connect().cursor()
        cursor.execute("PRAGMA foreign_keys")
        assert cursor.fetchone()[0] == 1

    def test_orphan_insert_is_rejected(self, db):
        import sqlcipher3
        conn = db.connect()
        cursor = conn.cursor()
        with pytest.raises(sqlcipher3.IntegrityError):
            cursor.execute(
                "INSERT INTO attachments (entry_id, filename, filepath, uploaded_at) "
                "VALUES (99999, 'x.enc', 'attachments/x.enc', 0)")
        conn.rollback()

    def test_parent_delete_with_children_is_rejected(self, db):
        import sqlcipher3, time as _time
        conn = db.connect()
        cursor = conn.cursor()
        now = int(_time.time())
        cursor.execute("SELECT id FROM client_types LIMIT 1")
        type_id = cursor.fetchone()[0]
        cursor.execute(
            "INSERT INTO clients (file_number, first_name, last_name, type_id, "
            "session_offset, created_at, modified_at) VALUES ('FK-1', 'A', 'B', ?, 0, ?, ?)",
            (type_id, now, now))
        client_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO entries (client_id, class, created_at, modified_at) "
            "VALUES (?, 'session', ?, ?)", (client_id, now, now))
        conn.commit()
        with pytest.raises(sqlcipher3.IntegrityError):
            cursor.execute("DELETE FROM clients WHERE id = ?", (client_id,))
        conn.rollback()


# ============================================================================
# LEGACY-DATABASE STARTUP MIGRATIONS (distribution support)
# ============================================================================
# EdgeCase ships as source/.deb/.dmg — other installs never ran the manual
# orphan audit or typed-columns --fix, so startup must handle legacy data.

class TestLegacyDatabaseMigrations:

    def _raw_insert(self, db_path, sql, params=()):
        """Insert into a closed DB with FK enforcement OFF (legacy writer)."""
        import sqlcipher3
        conn = sqlcipher3.connect(db_path)
        conn.execute(sql, params)
        conn.commit()
        conn.close()

    def test_orphaned_db_disables_enforcement_but_still_works(self, tmp_path):
        db_path = str(tmp_path / 'legacy.db')
        db = Database(db_path)  # creates clean schema, enforcement on
        assert db._enforce_foreign_keys is True
        db.close()

        # Simulate a legacy install: orphan row written with FK off
        self._raw_insert(
            db_path,
            "INSERT INTO attachments (entry_id, filename, filepath, uploaded_at) "
            "VALUES (99999, 'x.enc', 'attachments/x.enc', 0)")

        # Reopen: enforcement must be skipped, app must keep working
        db2 = Database(db_path)
        assert db2._enforce_foreign_keys is False
        cursor = db2.connect().cursor()
        cursor.execute("PRAGMA foreign_keys")
        assert cursor.fetchone()[0] == 0
        # Normal operations still function
        client_id = db2.add_client({'file_number': 'LEG-1', 'first_name': 'A',
                                    'last_name': 'B', 'type_id': 1})
        assert client_id
        db2.close()

        # Clean up the orphan -> enforcement returns at next launch
        import sqlcipher3
        conn = sqlcipher3.connect(db_path)
        conn.execute("DELETE FROM attachments WHERE entry_id = 99999")
        conn.commit()
        conn.close()
        db3 = Database(db_path)
        assert db3._enforce_foreign_keys is True
        db3.close()

    def test_typed_empty_strings_migrated_on_open(self, tmp_path):
        db_path = str(tmp_path / 'legacy2.db')
        db = Database(db_path)
        client_id = db.add_client({'file_number': 'LEG-2', 'first_name': 'A',
                                   'last_name': 'B', 'type_id': 1})
        db.close()

        # Legacy '' values in typed columns (pre-H5 writes)
        self._raw_insert(
            db_path,
            "INSERT INTO entries (client_id, class, created_at, modified_at, "
            "fee, session_date, statement_id) VALUES (?, 'session', 1, 1, '', '', '')",
            (client_id,))

        db2 = Database(db_path)  # startup migration runs here
        cursor = db2.connect().cursor()
        cursor.execute(
            "SELECT fee, session_date, statement_id FROM entries "
            "WHERE client_id = ? AND class = 'session'", (client_id,))
        fee, session_date, statement_id = cursor.fetchone()
        assert fee is None
        assert session_date is None
        assert statement_id is None
        db2.close()


# ============================================================================
# BACKUP / RESTORE ROUND TRIP (review "Testing assessment" + H1)
# ============================================================================
# Exercises the REAL utils.backup functions end-to-end against an isolated
# temp data root (module path constants are monkeypatched, so the
# production data root is never touched).

class TestBackupRestoreRoundTrip:

    @pytest.fixture
    def backup_env(self, tmp_path, monkeypatch):
        """Point utils.backup's module-level paths at an isolated root."""
        import utils.backup as backup_mod
        root = tmp_path / 'dataroot'
        data_dir = root / 'data'
        attachments = root / 'attachments'
        data_dir.mkdir(parents=True)
        attachments.mkdir(parents=True)
        monkeypatch.setattr(backup_mod, 'DATA_ROOT', root)
        monkeypatch.setattr(backup_mod, 'DATA_DIR', data_dir)
        monkeypatch.setattr(backup_mod, 'ATTACHMENTS_DIR', attachments)
        monkeypatch.setattr(backup_mod, 'ASSETS_DIR', root / 'assets')
        monkeypatch.setattr(backup_mod, 'BACKUPS_DIR', root / 'backups')
        monkeypatch.setattr(backup_mod, 'MANIFEST_FILE', root / 'backups' / 'manifest.json')
        monkeypatch.setattr(backup_mod, 'RESTORE_STAGING_DIR', root / '.restore_staging')
        return backup_mod, root

    def _make_db(self, root, password='roundtrip-pw'):
        return Database(str(root / 'data' / 'edgecase.db'), password=password)

    def test_full_backup_restore_round_trip(self, backup_env):
        backup_mod, root = backup_env
        data_dir = root / 'data'

        # --- original state ---
        db = self._make_db(root)
        db.set_setting('practice_name', 'Original Practice')
        client_id = db.add_client({'file_number': 'RT-1', 'first_name': 'Round',
                                   'last_name': 'Trip', 'type_id': 1})
        att_dir = root / 'attachments' / str(client_id) / '1'
        att_dir.mkdir(parents=True)
        (att_dir / 'note.enc').write_bytes(b'original-attachment-bytes')

        result = backup_mod.create_backup(db=db)
        assert result and result.get('type') == 'full'

        # --- mutate everything after the backup ---
        db.set_setting('practice_name', 'Mutated Practice')
        db.add_client({'file_number': 'RT-2', 'first_name': 'Post',
                       'last_name': 'Backup', 'type_id': 1})
        (att_dir / 'note.enc').write_bytes(b'corrupted')

        # --- restore the full backup ---
        points = backup_mod.get_restore_points()
        full_point = next(p for p in points if p['type'] == 'full')
        backup_mod.prepare_restore(full_point['id'], db=db)
        db.close()

        # H1: stale sidecars from the pre-restore database must not
        # survive into the restored one
        (data_dir / 'edgecase.db-wal').write_bytes(b'stale wal')
        (data_dir / 'edgecase.db-shm').write_bytes(b'stale shm')

        info = backup_mod.complete_restore()
        assert info is not None
        # The stale sidecars must be gone. A WAL may legitimately exist
        # afterwards if one was part of the backup itself (H7 includes it),
        # but it must never be the stale pre-restore one.
        wal = data_dir / 'edgecase.db-wal'
        assert (not wal.exists()) or wal.read_bytes() != b'stale wal'
        assert not (data_dir / 'edgecase.db-shm').exists()

        # --- assert data equality with the original state ---
        db2 = self._make_db(root)
        assert db2.get_setting('practice_name') == 'Original Practice'
        clients = {c['file_number'] for c in db2.get_all_clients()}
        assert 'RT-1' in clients
        assert 'RT-2' not in clients  # post-backup client rolled back
        assert (att_dir / 'note.enc').read_bytes() == b'original-attachment-bytes'
        db2.close()

    def test_incremental_chain_round_trip(self, backup_env):
        backup_mod, root = backup_env

        # State A -> full backup
        db = self._make_db(root)
        db.set_setting('practice_name', 'State A')
        att_dir = root / 'attachments' / 'ledger' / '1'
        att_dir.mkdir(parents=True)
        (att_dir / 'receipt.enc').write_bytes(b'receipt-A')
        (att_dir / 'doomed.enc').write_bytes(b'to-be-deleted')
        assert backup_mod.create_backup(db=db)['type'] == 'full'

        # State B: change setting + attachment, delete a file -> incremental
        db.set_setting('practice_name', 'State B')
        (att_dir / 'receipt.enc').write_bytes(b'receipt-B')
        (att_dir / 'doomed.enc').unlink()
        incr = backup_mod.create_backup(db=db)
        assert incr and incr['type'] == 'incremental'

        # State C: further mutation, NOT backed up
        db.set_setting('practice_name', 'State C')

        # Restore the incremental point -> expect State B exactly
        points = backup_mod.get_restore_points()
        incr_point = next(p for p in points if p['type'] == 'incremental')
        backup_mod.prepare_restore(incr_point['id'], db=db)
        db.close()
        assert backup_mod.complete_restore() is not None

        db2 = self._make_db(root)
        assert db2.get_setting('practice_name') == 'State B'
        assert (att_dir / 'receipt.enc').read_bytes() == b'receipt-B'
        # File deleted before the incremental must not resurrect
        assert not (att_dir / 'doomed.enc').exists()
        db2.close()


# ============================================================================
# REQUEST-LAYER SECURITY (Host validation + per-client session auth)
#
# These are the first tests that exercise the Flask app itself rather than
# the database layer. They cover the 2026-06-09 fixes:
# - Host-header validation (DNS rebinding protection): requests not
#   addressed to a recognized local host are rejected before any handler.
# - Per-client session authentication: an unlocked database is app-global
#   and must not by itself grant access — each client needs the session
#   marker set by auth.login.
# ============================================================================

class TestRequestSecurity:
    """Host-header validation and session authentication enforcement."""

    @pytest.fixture
    def flask_app(self, db):
        """The real Flask app with the test database installed as 'unlocked'."""
        from web.app import app
        prev_db = app.config.get('db')
        app.config['db'] = db
        app.config['TESTING'] = True
        yield app
        app.config['db'] = prev_db

    def test_rebound_host_rejected(self, flask_app):
        """A request with a foreign Host header (DNS rebinding) gets 403."""
        client = flask_app.test_client()
        resp = client.get('/', headers={'Host': 'attacker.example.com'})
        assert resp.status_code == 403

    def test_rebound_host_rejected_even_for_login(self, flask_app):
        """Host validation runs for ALL endpoints, including the login page."""
        client = flask_app.test_client()
        resp = client.get('/login', headers={'Host': 'attacker.example.com'})
        assert resp.status_code == 403

    def test_localhost_hosts_allowed(self, flask_app):
        """localhost and 127.0.0.1 (any port) pass Host validation."""
        client = flask_app.test_client()
        for host in ('localhost:8080', '127.0.0.1:8080', 'localhost'):
            resp = client.get('/login', headers={'Host': host})
            assert resp.status_code == 200, f"Host {host!r} should be allowed"

    def test_lan_mode_host_rules(self, flask_app, monkeypatch):
        """LAN mode admits private-range IP literals but never DNS names."""
        from web.app import _host_is_allowed
        monkeypatch.setenv('EDGECASE_LAN', '1')
        assert _host_is_allowed('192.168.1.50:8080')
        assert _host_is_allowed('10.0.0.7:8080')
        assert _host_is_allowed('100.99.1.2:8080')  # Tailscale CGNAT range
        assert not _host_is_allowed('attacker.example.com:8080')
        assert not _host_is_allowed('8.8.8.8:8080')  # public IP literal
        monkeypatch.delenv('EDGECASE_LAN')
        # Outside LAN mode, private IPs are NOT accepted
        assert not _host_is_allowed('192.168.1.50:8080')

    def test_cookieless_request_rejected_while_unlocked(self, flask_app):
        """An unlocked database must not grant access to a client with no
        authenticated session — the pre-fix behavior let any cookieless
        request straight through."""
        client = flask_app.test_client()
        resp = client.get('/', headers={'Host': 'localhost:8080'})
        # Browser request -> redirected to login, never the home page
        assert resp.status_code in (301, 302)
        assert '/login' in resp.headers.get('Location', '')

    def test_cookieless_api_request_gets_401(self, flask_app):
        """API requests without an authenticated session get JSON 401."""
        client = flask_app.test_client()
        resp = client.get('/api/restore-message',
                          headers={'Host': 'localhost:8080'})
        assert resp.status_code == 401

    def test_authenticated_session_passes(self, flask_app):
        """A session carrying the auth.login marker is accepted."""
        client = flask_app.test_client()
        with client.session_transaction() as sess:
            sess['authenticated'] = True
            sess['last_activity'] = time.time()
        resp = client.get('/api/restore-message',
                          headers={'Host': 'localhost:8080'})
        assert resp.status_code == 200


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v'])


# ============================================================================
# FULL CONTENT DIFF (AI Scribe change-review overlay)
# ============================================================================

class TestFullContentDiff:
    def test_identical_text_has_no_markup(self):
        text = "Client attended the session and reported improvement."
        out = generate_full_content_diff(text, text)
        assert '<del>' not in out and '<strong>' not in out
        assert out == text

    def test_replacement_marks_old_and_new(self):
        out = generate_full_content_diff(
            "Client seemed anxious today.",
            "Client appeared anxious today.",
        )
        assert '<del>seemed</del>' in out
        assert '<strong>appeared</strong>' in out
        # Unchanged context is preserved, not elided
        assert out.startswith('Client')
        assert 'anxious today.' in out
        assert '[...]' not in out and '...' not in out

    def test_long_unchanged_runs_are_not_elided(self):
        old = ' '.join(f'word{i}' for i in range(200))
        new = old.replace('word100', 'replaced')
        out = generate_full_content_diff(old, new)
        assert 'word0' in out and 'word199' in out
        assert '[...]' not in out
        assert '<del>word100</del>' in out
        assert '<strong>replaced</strong>' in out

    def test_html_in_notes_is_escaped(self):
        out = generate_full_content_diff(
            "Plain note.",
            "Plain note. <script>alert(1)</script>",
        )
        assert '<script>' not in out
        assert '&lt;script&gt;' in out

    def test_empty_old_marks_everything_inserted(self):
        out = generate_full_content_diff("", "Entirely new text.")
        assert out == '<strong>Entirely new text.</strong>'

    def test_empty_new_marks_everything_deleted(self):
        out = generate_full_content_diff("Old text.", "")
        assert out == '<del>Old text.</del>'
