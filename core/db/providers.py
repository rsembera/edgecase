"""Insurance providers: networks the practitioner has joined.

The provider number belongs to the practitioner, but *which* number prints on
a document is a property of the client, because the insurer is. So the numbers
live here and `clients.provider_id` carries the assignment — set once on the
client profile, after which every statement and payment record for that client
carries the right line without a per-document decision to remember.

`number_format` is the printed line as the insurer wants it, with `{name}` and
`{number}` substituted. Insurers differ; the app should not impose a style.
"""
import time


DEFAULT_FORMAT = '{name} — Provider No. {number}'


class ProviderMixin:

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def get_insurance_providers(self):
        """All providers, alphabetical."""
        conn = self.connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, name, provider_number, number_format,
                   created_at, modified_at
            FROM insurance_providers
            ORDER BY name COLLATE NOCASE
        """)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def get_insurance_provider(self, provider_id):
        if not provider_id:
            return None
        conn = self.connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, name, provider_number, number_format,
                   created_at, modified_at
            FROM insurance_providers WHERE id = ?
        """, (provider_id,))
        row = cur.fetchone()
        if not row:
            return None
        return dict(zip([d[0] for d in cur.description], row))

    def get_client_provider(self, client_id):
        """The provider assigned to a client, or None. Used by the statement
        and payment-record generators."""
        conn = self.connect()
        cur = conn.cursor()
        cur.execute("SELECT provider_id FROM clients WHERE id = ?", (client_id,))
        row = cur.fetchone()
        if not row or not row[0]:
            return None
        return self.get_insurance_provider(row[0])

    def count_clients_using_provider(self, provider_id):
        conn = self.connect()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM clients WHERE provider_id = ?",
                    (provider_id,))
        return cur.fetchone()[0]

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def add_insurance_provider(self, name, provider_number,
                               number_format=None):
        name = (name or '').strip()
        provider_number = (provider_number or '').strip()
        if not name or not provider_number:
            raise ValueError("Insurer name and provider number are required.")
        fmt = (number_format or '').strip() or DEFAULT_FORMAT

        now = int(time.time())
        conn = self.connect()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO insurance_providers
                (name, provider_number, number_format, created_at, modified_at)
            VALUES (?, ?, ?, ?, ?)
        """, (name, provider_number, fmt, now, now))
        conn.commit()
        return cur.lastrowid

    def update_insurance_provider(self, provider_id, name, provider_number,
                                  number_format=None):
        name = (name or '').strip()
        provider_number = (provider_number or '').strip()
        if not name or not provider_number:
            raise ValueError("Insurer name and provider number are required.")
        fmt = (number_format or '').strip() or DEFAULT_FORMAT

        conn = self.connect()
        cur = conn.cursor()
        cur.execute("""
            UPDATE insurance_providers
            SET name = ?, provider_number = ?, number_format = ?, modified_at = ?
            WHERE id = ?
        """, (name, provider_number, fmt, int(time.time()), provider_id))
        conn.commit()
        return cur.rowcount > 0

    def delete_insurance_provider(self, provider_id):
        """Refuse while clients are assigned.

        Returns (True, None) or (False, count). Silently unassigning would
        strip the number from those clients' statements with no visible cause;
        foreign keys are enforced (core/database.py:57), so a cascade is not
        available by accident either.
        """
        in_use = self.count_clients_using_provider(provider_id)
        if in_use:
            return False, in_use

        conn = self.connect()
        cur = conn.cursor()
        cur.execute("DELETE FROM insurance_providers WHERE id = ?",
                    (provider_id,))
        conn.commit()
        return True, None

    def set_client_provider(self, client_id, provider_id):
        """Assign, change, or clear (provider_id None/'' -> no insurer)."""
        pid = int(provider_id) if provider_id else None
        conn = self.connect()
        cur = conn.cursor()
        cur.execute("UPDATE clients SET provider_id = ?, modified_at = ? "
                    "WHERE id = ?", (pid, int(time.time()), client_id))
        conn.commit()
        return cur.rowcount > 0


def provider_line(provider):
    """The line to print, or None when the client has no insurer.

    A malformed custom format must not break a statement, so an unknown
    placeholder falls back to the default rather than raising.
    """
    if not provider:
        return None
    fmt = provider.get('number_format') or DEFAULT_FORMAT
    values = {'name': provider.get('name', ''),
              'number': provider.get('provider_number', '')}
    try:
        return fmt.format(**values).strip()
    except (KeyError, IndexError, ValueError):
        return DEFAULT_FORMAT.format(**values).strip()
