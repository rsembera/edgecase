"""Settings operations — key/value application settings.

Extracted from core/database.py (Step 3). Relies on self.connect() provided by
the base Database class it is mixed into.
"""
import time


class SettingsMixin:
    """get/set rows in the `settings` table."""

    def set_setting(self, key: str, value: str):
        """Set a setting value."""
        conn = self.connect()
        cursor = conn.cursor()

        now = int(time.time())
        cursor.execute("""
            INSERT INTO settings (key, value, modified_at) 
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=?, modified_at=?
        """, (key, value, now, value, now))

        conn.commit()

    def get_setting(self, key: str, default: str = '') -> str:
        """Get a setting value."""
        conn = self.connect()
        cursor = conn.cursor()

        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()

        return row[0] if row else default
