"""Client file numbers.

Moved out of the Add Client route so AirLock's import numbers clients exactly
as Add Client does. Behaviour is pinned by tests/test_file_numbers.py, written
against the route before the move.

Formats (setting `file_number_format`):
    manual          the number the practitioner typed
    date-initials   YYYYMMDD-INITIALS, suffixed -2, -3... on collision
    prefix-counter  [prefix-]NNNN[-suffix]; the counter advances past any
                    number already in use, and is saved on success
"""
from datetime import datetime


class FileNumberError(ValueError):
    """Carries the message the Add Client form shows."""


def generate_file_number(db, first_name, middle_name, last_name, manual=None,
                         now=None) -> str:
    """Next file number for a new client under the configured format.

    `manual` is only used (and required) in manual format. For
    prefix-counter this advances the stored counter, exactly as creating a
    client from the form always has.
    """
    format_type = db.get_setting('file_number_format', 'manual')

    if format_type == 'date-initials':
        date_str = (now or datetime.now()).strftime('%Y%m%d')
        first_name = (first_name or '').strip()
        last_name = (last_name or '').strip()
        if not first_name or not last_name:
            raise FileNumberError(
                "First and last name are required to generate the file number.")
        middle = (middle_name or '').strip()
        initials = (first_name[0].upper() + (middle[0].upper() if middle else '')
                    + last_name[0].upper())
        base = f"{date_str}-{initials}"
        file_number = base
        suffix = 2
        while db.file_number_exists(file_number):
            file_number = f"{base}-{suffix}"
            suffix += 1
            if suffix > 100:
                raise FileNumberError(
                    "Too many clients with similar initials today. "
                    "Please use manual file number.")
        return file_number

    if format_type == 'prefix-counter':
        counter = int(db.get_setting('file_number_counter', '1'))
        file_number = prefix_counter_number(db, counter)
        while db.file_number_exists(file_number):
            counter += 1
            file_number = prefix_counter_number(db, counter)
        db.set_setting('file_number_counter', str(counter + 1))
        return file_number

    # manual (and any unknown format, as before)
    file_number = (manual or '').strip()
    if not file_number:
        raise FileNumberError("A file number is required.")
    if db.file_number_exists(file_number):
        raise FileNumberError(
            f"File number '{file_number}' already exists. "
            "Please choose a different one.")
    return file_number


def prefix_counter_number(db, counter) -> str:
    parts = []
    prefix = db.get_setting('file_number_prefix', '')
    suffix = db.get_setting('file_number_suffix', '')
    if prefix:
        parts.append(prefix)
    parts.append(str(counter).zfill(4))
    if suffix:
        parts.append(suffix)
    return '-'.join(parts)


def preview_file_number(db, first_name='', middle_name='', last_name='',
                        now=None) -> str:
    """What the next number would look like, without advancing anything.
    Empty in manual format."""
    format_type = db.get_setting('file_number_format', 'manual')
    if format_type == 'date-initials':
        date_str = (now or datetime.now()).strftime('%Y%m%d')
        if first_name.strip() and last_name.strip():
            initials = (first_name.strip()[0] + middle_name.strip()[:1]
                        + last_name.strip()[0]).upper()
        else:
            initials = 'ABC'
        return f"{date_str}-{initials}"
    if format_type == 'prefix-counter':
        return prefix_counter_number(db, int(db.get_setting('file_number_counter', '1')))
    return ''
