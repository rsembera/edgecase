"""Retention system — PHIPA-driven archival and deletion lifecycle for Inactive
clients (retain-until computation, the deletion sweep, retention snapshots).

Extracted from core/database.py (Step 3). Relies on self.connect() from the
base Database class.
"""
import os
import time

from datetime import datetime


class RetentionMixin:

    # ============================================================
    # RETENTION SYSTEM FUNCTIONS
    # ============================================================

    @staticmethod
    def _calculate_retain_until(last_contact, retention_days, is_minor, dob_str):
        """
        Compute the epoch timestamp at which an Inactive client's file may be
        destroyed. Single source of truth for both the deletion sweep
        (get_clients_due_for_deletion) and the single-client preview, so the
        two can never drift apart.

        Anchored on last_contact (most recent entry's created_at). For minors,
        retention runs to the LATER of (last_contact + period) and
        (18th birthday + period). See Architecture_Decisions.md:
        RETENTION CLOCK ANCHORING.
        """

        retention_seconds = (retention_days or 0) * 24 * 60 * 60
        standard_retain_until = last_contact + retention_seconds

        if is_minor and dob_str:
            try:
                dob = datetime.strptime(dob_str, '%Y-%m-%d')
                try:
                    eighteenth_birthday = dob.replace(year=dob.year + 18)
                except ValueError:
                    # Feb 29 birthday: no Feb 29 in the target year. Clamp to
                    # Mar 1 (one day later than Feb 28) so a leap-day minor
                    # still gets the age-of-majority extension. Falling through
                    # to standard retention would be the unsafe, shorter direction.
                    eighteenth_birthday = dob.replace(year=dob.year + 18, month=3, day=1)
                after_majority = int(eighteenth_birthday.timestamp()) + retention_seconds
                return max(standard_retain_until, after_majority)
            except (ValueError, TypeError):
                return standard_retain_until

        return standard_retain_until

    def get_clients_due_for_deletion(self):
        """
        Get all Inactive clients whose retention period has expired.
        Returns list of dicts with client info and calculated retain_until.
        """
        
        conn = self.connect()
        cursor = conn.cursor()
        
        # Get all Inactive clients with retention_days set.
        # Match on is_system_locked (the flag that uniquely identifies the
        # seeded Inactive workflow type — see _create_default_types) rather
        # than the literal name, so a rename can never silently disable the
        # retention sweep (CODE_REVIEW.md M10).
        # Entry date aggregates and profile fields are pulled in via scalar
        # subqueries so the whole sweep is one round trip instead of three
        # extra queries per client (CODE_REVIEW.md L5).
        cursor.execute("""
            SELECT c.*, ct.name as type_name,
                   (SELECT MAX(created_at) FROM entries
                    WHERE client_id = c.id) AS entry_last_contact,
                   (SELECT MIN(created_at) FROM entries
                    WHERE client_id = c.id) AS entry_first_contact,
                   (SELECT is_minor FROM entries
                    WHERE client_id = c.id AND class = 'profile'
                    LIMIT 1) AS profile_is_minor,
                   (SELECT date_of_birth FROM entries
                    WHERE client_id = c.id AND class = 'profile'
                    LIMIT 1) AS profile_dob,
                   (SELECT 1 FROM entries
                    WHERE client_id = c.id AND class = 'profile'
                    LIMIT 1) AS has_profile
            FROM clients c
            JOIN client_types ct ON c.type_id = ct.id
            WHERE ct.is_system_locked = 1
            AND c.retention_days IS NOT NULL
            AND c.is_deleted = 0
        """)

        columns = [description[0] for description in cursor.description]
        inactive_clients = [dict(zip(columns, row)) for row in cursor.fetchall()]

        clients_due = []
        today = int(time.time())

        for client in inactive_clients:
            client_id = client['id']
            retention_days = client['retention_days']

            # 0 retention_days means "keep forever" - skip these
            if retention_days == 0:
                continue

            # Last contact date (most recent entry, or fall back to modified_at)
            last_contact = client['entry_last_contact'] if client['entry_last_contact'] else client['modified_at']

            # Profile fields for minor status (0/None when no profile exists,
            # matching the previous per-client query's fallback)
            is_minor = client['profile_is_minor'] if client['has_profile'] else 0
            dob_str = client['profile_dob'] if client['has_profile'] else None

            # Calculate retain_until (see _calculate_retain_until)
            retain_until = self._calculate_retain_until(
                last_contact, retention_days, is_minor, dob_str
            )

            # Check if retention period has expired
            if today >= retain_until:
                # First contact (earliest entry, or fall back to created_at)
                first_contact = client['entry_first_contact'] if client['entry_first_contact'] else client['created_at']
                
                # Build full name
                full_name = client['first_name']
                if client.get('middle_name'):
                    full_name += f" {client['middle_name']}"
                full_name += f" {client['last_name']}"
                
                clients_due.append({
                    'id': client_id,
                    'file_number': client['file_number'],
                    'full_name': full_name,
                    'first_contact': first_contact,
                    'last_contact': last_contact,
                    'retain_until': retain_until,
                    'is_minor': is_minor
                })
        
        return clients_due

    def archive_and_delete_client(self, client_id):
        """
        Archive client info and delete all their data.
        Returns True on success, False on failure.

        All database deletes happen in one transaction; attachment files
        are removed from disk only AFTER the commit succeeds, so a failed
        DELETE can never roll back the DB while the files are already gone
        (CODE_REVIEW.md H6). File-deletion failures after the commit are
        logged but do not fail the operation.
        """
        import shutil

        conn = self.connect()
        cursor = conn.cursor()

        try:
            # Get client data
            cursor.execute("SELECT * FROM clients WHERE id = ?", (client_id,))
            columns = [description[0] for description in cursor.description]
            row = cursor.fetchone()
            if not row:
                return False
            client = dict(zip(columns, row))
            
            # Get profile for minor check
            cursor.execute("""
                SELECT is_minor, date_of_birth
                FROM entries
                WHERE client_id = ? AND class = 'profile'
            """, (client_id,))
            profile = cursor.fetchone()
            is_minor = profile[0] if profile else 0
            dob_str = profile[1] if profile else None
            
            # Get first contact
            cursor.execute("""
                SELECT MIN(created_at) FROM entries WHERE client_id = ?
            """, (client_id,))
            result = cursor.fetchone()
            first_contact = result[0] if result and result[0] else client['created_at']
            
            # Get last contact
            cursor.execute("""
                SELECT MAX(created_at) FROM entries WHERE client_id = ?
            """, (client_id,))
            result = cursor.fetchone()
            # Fallback aligned with get_clients_due_for_deletion: use modified_at
            # (≈ when the file went cold) rather than created_at for entry-less clients
            last_contact = result[0] if result and result[0] else client['modified_at']
            
            # Calculate retain_until (see _calculate_retain_until)
            retention_days = client.get('retention_days') or 0
            retain_until = self._calculate_retain_until(
                last_contact, retention_days, is_minor, dob_str
            )
            
            # Build full name
            full_name = client['first_name']
            if client.get('middle_name'):
                full_name += f" {client['middle_name']}"
            full_name += f" {client['last_name']}"
            
            # Create archive record
            cursor.execute("""
                INSERT INTO archived_clients 
                (file_number, full_name, first_contact, last_contact, retain_until, deleted_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                client['file_number'],
                full_name,
                first_contact,
                last_contact,
                retain_until,
                int(time.time())
            ))
            
            # Get all entry IDs for this client (for attachment/link cleanup)
            cursor.execute("SELECT id FROM entries WHERE client_id = ?", (client_id,))
            entry_ids = [row[0] for row in cursor.fetchall()]

            if entry_ids:
                placeholders = ','.join('?' * len(entry_ids))

                # Delete attachments from database
                cursor.execute(f"DELETE FROM attachments WHERE entry_id IN ({placeholders})", entry_ids)

                # Delete entry links referencing this client's entries (either side)
                cursor.execute(
                    f"DELETE FROM entry_links WHERE entry_id_1 IN ({placeholders}) "
                    f"OR entry_id_2 IN ({placeholders})",
                    entry_ids + entry_ids
                )

            # Delete payment allocations before the rows they reference.
            # Allocations point at entries, statement portions AND the client,
            # so with PRAGMA foreign_keys=ON (core/database.py:57 turns it on
            # whenever the database passes its integrity check) deleting the
            # portions or entries first fails the whole disposal. The table
            # arrived with the payment-allocation work on 2026-08-09; this
            # function predates it and was never updated.
            cursor.execute("DELETE FROM payment_allocations WHERE client_id = ?",
                           (client_id,))
            if entry_ids:
                cursor.execute(
                    f"DELETE FROM payment_allocations WHERE entry_id IN ({placeholders})",
                    entry_ids
                )

            # Delete statement portions (orphans would permanently inflate
            # count_pending_invoices)
            cursor.execute("DELETE FROM statement_portions WHERE client_id = ?", (client_id,))

            # Delete client link rows (either side)
            cursor.execute(
                "DELETE FROM client_links WHERE client_id_1 = ? OR client_id_2 = ?",
                (client_id, client_id)
            )

            # Delete all entries
            cursor.execute("DELETE FROM entries WHERE client_id = ?", (client_id,))

            # Delete client record
            cursor.execute("DELETE FROM clients WHERE id = ?", (client_id,))

            conn.commit()

        except Exception as e:
            conn.rollback()
            print(f"Error archiving client {client_id}: {e}")
            return False

        # Delete attachment files from disk only AFTER the commit succeeded.
        # A failure here leaves the DB consistent; leftover files are logged
        # so they can be removed manually.
        try:
            from core.config import ATTACHMENTS_DIR
            client_attachments_dir = ATTACHMENTS_DIR / str(client_id)
            if os.path.exists(client_attachments_dir):
                shutil.rmtree(client_attachments_dir)
        except Exception as e:
            print(f"Warning: failed to delete attachment files for client {client_id}: {e}")

        return True

    def get_deleted_clients(self):
        """Get all archived client records."""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM archived_clients
            ORDER BY deleted_at DESC
        """)
        
        columns = [description[0] for description in cursor.description]
        archived = [dict(zip(columns, row)) for row in cursor.fetchall()]
        return archived

    def snapshot_retention_on_inactive(self, client_id, retention_days):
        """
        When changing to Inactive, store the retention_days from the original type.
        """
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE clients 
            SET retention_days = ?, modified_at = ?
            WHERE id = ?
        """, (retention_days, int(time.time()), client_id))
        
        conn.commit()
