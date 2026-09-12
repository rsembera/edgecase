"""Generated reports must not be left lying in the shared system temp dir.

`delivery.py` learned this for statements on 2026-06-07: PDFs holding PHI go
into a private (0700, randomized) mkdtemp directory that is removed once the
response is sent, never into `tempfile.gettempdir()` under a predictable name.

`ledger.py:generate_report_pdf` was missed. It wrote
`Payment_Record_<file_number>_<start>_to_<end>.pdf` — or
`Financial_Report_<start>_to_<end>.pdf` — straight into the shared temp dir
and never deleted it. On a machine where `gettempdir()` is `/tmp` (mode
`drwxrwxrwt`, as on Rick's), an unencrypted document naming a client and their
payment history stayed world-readable until the OS reaper eventually took it.

Wider exposure than the filename disclosure fixed on 2026-09-04: there the
contents stayed encrypted, here the whole document was in the clear.
"""
import glob
import os
import tempfile

import pytest


def _shared_temp_reports():
    d = tempfile.gettempdir()
    return set(glob.glob(os.path.join(d, 'Payment_Record_*.pdf'))
               + glob.glob(os.path.join(d, 'Financial_Report_*.pdf')))


@pytest.fixture
def temp_watch():
    """Snapshot the shared temp dir; assert the route added nothing to it.

    Cleans up anything the route did leave, so a red run doesn't seed the
    temp dir with PHI-shaped fixtures or let the next run pass on stale state.
    """
    before = _shared_temp_reports()

    def check():
        leaked = _shared_temp_reports() - before
        for p in leaked:
            try:
                os.remove(p)
            except OSError:
                pass
        assert not leaked, (
            "report PDF left in the shared system temp dir: "
            f"{sorted(os.path.basename(p) for p in leaked)}"
        )

    return check


def _make_client(app_db):
    return app_db.add_client({
        "file_number": "20250901-JH",
        "first_name": "Jane",
        "middle_name": "",
        "last_name": "Hale",
        "type_id": 1,
    })


def test_business_report_leaves_nothing_in_the_shared_temp_dir(
        client, app_db, temp_watch):
    resp = client.get('/ledger/report/pdf',
                      query_string={'start': '2026-01-01',
                                    'end': '2026-12-31'})
    assert resp.status_code == 200
    assert resp.mimetype == 'application/pdf'
    resp.close()          # release the streamed file so cleanup can run
    temp_watch()


def test_payment_record_leaves_nothing_in_the_shared_temp_dir(
        client, app_db, temp_watch):
    cid = _make_client(app_db)

    resp = client.get('/ledger/report/pdf',
                      query_string={'start': '2026-01-01',
                                    'end': '2026-12-31',
                                    'client': cid})
    assert resp.status_code == 200
    assert resp.mimetype == 'application/pdf'
    resp.close()
    temp_watch()


def test_download_name_still_carries_the_readable_title(client, app_db):
    """The private dir is an on-disk detail; the user-facing name is unchanged."""
    cid = _make_client(app_db)

    resp = client.get('/ledger/report/pdf',
                      query_string={'start': '2026-01-01',
                                    'end': '2026-12-31',
                                    'client': cid})
    disposition = resp.headers.get('Content-Disposition', '')
    assert 'Payment_Record_20250901-JH_2026-01-01_to_2026-12-31.pdf' in disposition
    resp.close()
