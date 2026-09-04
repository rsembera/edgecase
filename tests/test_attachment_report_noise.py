"""Unresolved rows are reported once, and again when the situation changes.

Seventeen identical lines at every launch — as the testing install produced on
2026-09-04 — teaches the reader to skip startup output, which is how the next
real one gets missed. But going silent would be worse: these lines are how
JH's three missing statements were found after eleven weeks.

So: full detail the first time and whenever the set changes; a single counted
line while it stays the same.

Same shape as tests/test_attachment_rename_pass.py — temp tree, bare sqlite,
the real install untouched.
"""
import sqlite3

import pytest

from core import attachment_names as an


@pytest.fixture
def tree(tmp_path):
    root = tmp_path
    (root / "attachments").mkdir()
    con = sqlite3.connect(":memory:")
    con.execute("""
        CREATE TABLE attachments (
            id INTEGER PRIMARY KEY, entry_id INTEGER, filename TEXT,
            description TEXT, filepath TEXT NOT NULL, filesize INTEGER,
            uploaded_at INTEGER)
    """)
    return root, con


def _add_missing(con, n, prefix="ghost"):
    """Rows pointing at files that were never planted on disk."""
    for i in range(n):
        con.execute(
            "INSERT INTO attachments (entry_id, filename, description, "
            "filepath, filesize, uploaded_at) VALUES (1, ?, '', ?, 0, 0)",
            (f"{prefix}{i}.pdf", f"attachments/1/{i}/{prefix}{i}.pdf"))
    con.commit()


def _run(tree):
    root, con = tree
    lines = []
    an.rename_readable_attachments(
        con, attachments_dir=root / "attachments", data_root=root,
        log=lines.append)
    return lines


def _missing(lines):
    # 'left as is' marks a per-row detail line; the summary also contains the
    # words 'missing file', so matching on those alone catches both.
    return [ln for ln in lines if 'left as is' in ln]


def _summary(lines):
    return [ln for ln in lines if 'unchanged since last check' in ln]


def test_first_run_lists_every_unresolved_row(tree):
    _add_missing(tree[1], 3)
    lines = _run(tree)
    assert len(_missing(lines)) == 3
    assert not _summary(lines)


def test_second_run_reports_a_single_counted_line(tree):
    _add_missing(tree[1], 3)
    _run(tree)

    lines = _run(tree)
    assert not _missing(lines)
    assert len(_summary(lines)) == 1


def test_the_summary_still_says_how_many(tree):
    """Quieter, not silent: the count must survive."""
    _add_missing(tree[1], 17)
    _run(tree)
    assert '17' in _summary(_run(tree))[0]


def test_a_new_missing_row_is_news_again(tree):
    """The failure this protects against: a real problem appearing after the
    reader has learned to skip the output."""
    _add_missing(tree[1], 3)
    _run(tree)
    assert not _missing(_run(tree))          # quiet

    _add_missing(tree[1], 1, prefix="new")

    lines = _run(tree)
    assert len(_missing(lines)) == 4
    assert not _summary(lines)


def test_resolving_everything_goes_quiet_and_a_recurrence_is_news(tree):
    root, con = tree
    _add_missing(con, 2)
    _run(tree)

    con.execute("DELETE FROM attachments")
    con.commit()
    lines = _run(tree)
    assert not _missing(lines) and not _summary(lines)

    # The same shape returning later must be reported, not swallowed.
    _add_missing(con, 2)
    assert len(_missing(_run(tree))) == 2


def test_the_state_file_holds_no_paths(tree):
    """Those paths carry client file numbers on any pre-2026-09-04 install;
    only a digest is stored."""
    root, con = tree
    _add_missing(con, 1, prefix="Statement_20250901-JH_")
    _run(tree)

    body = an._state_file(root / "attachments").read_text().strip()
    assert 'JH' not in body
    assert 'Statement' not in body
    assert len(body) == 64          # sha256 hex


def test_the_state_file_is_not_itself_reported_as_an_orphan(tree):
    """A dotfile in the attachments tree must not become an orphan finding."""
    _add_missing(tree[1], 1)
    _run(tree)
    lines = _run(tree)
    assert not [ln for ln in lines if 'unresolved_report' in ln]
