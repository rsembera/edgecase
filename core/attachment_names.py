"""
One-time rename pass: anonymize attachment filenames left on disk by the
old statement-delivery writer.

Until 2026-09 web/blueprints/statements/delivery.py stored generated
statement PDFs as Statement_<file_number>_<date>.pdf. The contents were
always encrypted; the NAME disclosed initials, intake date and billing
month to anyone who could list the directory or a backup zip. Uploads were
never affected — web/utils.py has stored <uuid>.enc from the start.

This module brings existing rows into line with the rule the fixed writer
now follows. It runs at login, after the database has been opened and
before the app is handed to the user (see web.blueprints.auth), and it is
idempotent: rows already named <uuid>.enc are skipped, so on a clean install
the whole pass is one SELECT.

Safety rules, in order of importance:
  * Rename on disk and UPDATE attachments.filepath in the same transaction.
    The order is UPDATE (uncommitted) -> os.rename -> COMMIT, and a failed
    commit renames the file back. There is no way to make a filesystem
    rename and a SQLite commit one atomic step; this ordering keeps the
    window to the commit itself and leaves the row untouched if the rename
    is refused.
  * Never touch a file that has no matching attachments row. A readable
    name under attachments/ with no row is reported, not renamed — guessing
    which row it belongs to is exactly the kind of cleverness that loses
    clinical records.
  * Never touch a row whose file is missing. Reported, left as is.
  * Never touch a file OUTSIDE this install's attachments folder, however
    the row points at it. A database restored from another install on the
    same machine carries that install's absolute paths.
  * Dotfiles (.DS_Store) are ignored everywhere.

Only the basename changes for a row whose file is where the row says. A
row that stored an absolute path keeps an absolute path; a relative one
stays relative, so resolution behaviour is unchanged for every reader.

The one exception is a row whose absolute path points at a PREVIOUS install
location (the old statement writer stored absolute paths, so a restore onto
another machine or a renamed folder broke every generated statement). If the
same attachments/<client>/<entry>/<name> tail exists under the current tree,
the row is re-pointed at it, relative to DATA_ROOT from then on. Exact tail
match only; nothing is adopted on a guess.
"""
import hashlib
import os
import re
import uuid
from pathlib import Path

import core.config as config

# The exact shape web/utils.py and delivery.py now write.
UUID_ENC_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.enc$")


def is_anonymized_name(name: str) -> bool:
    return bool(UUID_ENC_RE.match(name))


def _resolve(filepath: str, data_root: Path) -> Path:
    if os.path.isabs(filepath):
        return Path(filepath)
    return Path(data_root) / filepath


def _under(path: Path, tree: Path) -> bool:
    try:
        path.resolve().relative_to(tree.resolve())
        return True
    except (ValueError, OSError):
        return False


def _relocation_candidate(stored: str, attachments_dir: Path):
    """For a stored path that does not exist: the same file under the
    current attachments tree, if the tail after the last 'attachments/'
    segment resolves there. Exact tail match only — client id, entry id
    and name all have to agree — so this cannot adopt a different row's
    file. None when there is no such file."""
    parts = Path(stored).parts
    hits = [i for i, part in enumerate(parts) if part == "attachments"]
    if not hits:
        return None
    tail = parts[hits[-1] + 1:]
    if not tail:
        return None
    candidate = attachments_dir.joinpath(*tail)
    return candidate if candidate.is_file() else None


def _renamed_value(stored: str, new_name: str) -> str:
    """The new filepath column value: same directory part, new basename,
    same absolute/relative style, same separator convention."""
    head, _tail = os.path.split(stored)
    return os.path.join(head, new_name) if head else new_name


def rename_readable_attachments(conn, attachments_dir=None, data_root=None,
                                log=print) -> dict:
    """Rename every attachments row whose on-disk name is not <uuid>.enc.

    `conn` is an open sqlite connection to the practice database (any key
    state — file contents are never read, so encryption is irrelevant).
    `attachments_dir` / `data_root` default to the live config paths and
    exist for tests against a temporary tree.

    Returns a summary dict: renamed, already_anonymized, relocated (rows
    whose absolute path pointed at a previous install location and were
    re-pointed at the same file under the current tree), missing (rows
    whose file is not on disk), outside_tree (rows whose absolute path
    points at an existing file OUTSIDE this install's attachments folder —
    never touched), orphans (readable-named files with no row), failed
    (rename or commit errors, with the reason).
    """
    attachments_dir = Path(attachments_dir or config.ATTACHMENTS_DIR)
    data_root = Path(data_root or config.DATA_ROOT)

    summary = {"renamed": 0, "already_anonymized": 0, "relocated": 0,
               "missing": [], "outside_tree": [], "orphans": [], "failed": []}

    rows = conn.execute("SELECT id, filepath FROM attachments").fetchall()
    known_paths = set()

    for row_id, stored in rows:
        if not stored:
            continue
        current = _resolve(stored, data_root)
        relocated = False
        if not _under(current, attachments_dir):
            # NEVER rename a file outside this install's attachments tree,
            # even if the row's absolute path points at one that exists
            # (a restore of another install's database onto this machine
            # would otherwise reach into that other install and rename
            # its files while updating only this database). Rows like
            # that are either relocatable — see below — or left alone.
            candidate = _relocation_candidate(stored, attachments_dir)
            if candidate is None:
                (summary["outside_tree"] if current.is_file()
                 else summary["missing"]).append(stored)
                continue
            current = candidate
            try:
                stored = str(candidate.relative_to(data_root))
            except ValueError:
                stored = str(candidate)
            relocated = True
        elif not current.is_file():
            # The old statement writer stored ABSOLUTE paths, which break
            # the moment the install moves (a restore onto another
            # machine, a renamed folder). If the same attachments/<client>/
            # <entry>/<name> tail exists under the current tree, that is
            # this row's file: adopt it and store the path relative to
            # DATA_ROOT from now on, as web/utils.py always has.
            candidate = _relocation_candidate(stored, attachments_dir)
            if candidate is None:
                summary["missing"].append(stored)
                continue
            current = candidate
            try:
                stored = str(candidate.relative_to(data_root))
            except ValueError:
                stored = str(candidate)
            relocated = True
        name = current.name
        if is_anonymized_name(name):
            known_paths.add(current.resolve())
            if relocated:
                try:
                    conn.execute("UPDATE attachments SET filepath = ? WHERE id = ?",
                                 (stored, row_id))
                    conn.commit()
                    summary["relocated"] += 1
                except Exception as e:
                    conn.rollback()
                    summary["failed"].append((stored, str(e)))
                    log(f"[Attachments] could not relocate {name}: {e}")
            else:
                summary["already_anonymized"] += 1
            continue

        new_name = f"{uuid.uuid4()}.enc"
        target = current.with_name(new_name)
        new_value = _renamed_value(stored, new_name)

        try:
            # UPDATE first, uncommitted (the connection's default implicit
            # transaction): if the rename is refused the transaction is
            # rolled back and the row never changes.
            conn.execute("UPDATE attachments SET filepath = ? WHERE id = ?",
                         (new_value, row_id))
            os.rename(current, target)
            try:
                conn.commit()
            except Exception:
                # The commit is the one step that can fail AFTER the disk
                # has moved; put the file back so row and file still agree.
                os.rename(target, current)
                raise
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            summary["failed"].append((stored, str(e)))
            log(f"[Attachments] could not rename {name}: {e}")
            continue

        known_paths.add(target.resolve())
        summary["renamed"] += 1
        if relocated:
            summary["relocated"] += 1

    # Readable-named files on disk that no row points at. Reported only.
    if attachments_dir.exists():
        for path in attachments_dir.rglob("*"):
            if not path.is_file() or path.name.startswith("."):
                continue
            if is_anonymized_name(path.name):
                continue
            if path.resolve() in known_paths:
                continue
            summary["orphans"].append(str(path))

    if summary["renamed"]:
        log(f"[Attachments] anonymized {summary['renamed']} filename(s)")
    if summary["relocated"]:
        log(f"[Attachments] re-pointed {summary['relocated']} row(s) from a "
            f"previous install location to the current one")

    _report_unresolved(summary, attachments_dir, log)
    return summary


def _unresolved_fingerprint(summary):
    """A hash of what could not be resolved, so an unchanged situation can be
    reported once rather than at every launch.

    Only the digest is stored — never the paths themselves, which carry client
    file numbers on any install that predates the 2026-09-04 rename.
    """
    items = (sorted(summary["missing"])
             + sorted(summary["outside_tree"])
             + sorted(summary["orphans"]))
    if not items:
        return None
    return hashlib.sha256("\n".join(items).encode()).hexdigest()


def _report_unresolved(summary, attachments_dir, log):
    """Report rows and files that could not be resolved.

    In full the first time, and again whenever the set changes; otherwise a
    single counted line. Repeating seventeen identical lines at every launch
    teaches the reader to skip startup output, which is how the next real one
    gets missed.
    """
    counts = {k: len(summary[k])
              for k in ("missing", "outside_tree", "orphans")}
    total = sum(counts.values())
    if not total:
        # Resolved since last time: drop the record so a recurrence is news.
        _state_file(attachments_dir).unlink(missing_ok=True)
        return

    fingerprint = _unresolved_fingerprint(summary)
    state = _state_file(attachments_dir)
    try:
        seen = state.read_text().strip()
    except OSError:
        seen = ""

    if seen == fingerprint:
        parts = [f"{n} {label}" for label, n in (
            ("row(s) point at a missing file", counts["missing"]),
            ("row(s) point outside this install", counts["outside_tree"]),
            ("file(s) have no attachment row", counts["orphans"]),
        ) if n]
        log(f"[Attachments] unchanged since last check: {', '.join(parts)}. "
            f"Run tools/audit_orphans.py for detail.")
        return

    for stored in summary["missing"]:
        log(f"[Attachments] row points at a missing file, left as is: {stored}")
    for stored in summary["outside_tree"]:
        log(f"[Attachments] row points outside this install's attachments "
            f"folder, left as is: {stored}")
    for orphan in summary["orphans"]:
        log(f"[Attachments] readable filename with no attachment row, "
            f"left as is: {orphan}")

    try:
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_text(fingerprint)
    except OSError:
        pass  # Reporting state is not worth failing a login over.


def _state_file(attachments_dir):
    return Path(attachments_dir) / ".unresolved_report"
