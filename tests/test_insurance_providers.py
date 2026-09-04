"""Insurance providers: arbitrarily many numbers, assigned per client.

The provider number belongs to the practitioner; which one prints belongs to
the client, because the insurer does. A single always-on Settings field would
put a Blue Cross identifier on documents for clients who have nothing to do
with Blue Cross, and would have no answer at all once a second network is
joined.
"""
import pytest

from core.db.providers import DEFAULT_FORMAT, provider_line


def _client(db, file_number="INS-001"):
    return db.add_client({
        "file_number": file_number,
        "first_name": "Ins",
        "middle_name": "",
        "last_name": "Ured",
        "type_id": 1,
    })


# ----------------------------------------------------------------------
# Settings: many providers
# ----------------------------------------------------------------------

def test_many_providers_can_coexist(app_db):
    app_db.add_insurance_provider("Blue Cross", "123456")
    app_db.add_insurance_provider("Green Shield", "GS-99")
    app_db.add_insurance_provider("Canada Life", "CL/7")

    names = [p['name'] for p in app_db.get_insurance_providers()]
    assert names == ["Blue Cross", "Canada Life", "Green Shield"]  # alphabetical


def test_name_and_number_are_required(app_db):
    with pytest.raises(ValueError):
        app_db.add_insurance_provider("", "123456")
    with pytest.raises(ValueError):
        app_db.add_insurance_provider("Blue Cross", "   ")


def test_provider_can_be_edited(app_db):
    pid = app_db.add_insurance_provider("Blue Cross", "123456")
    assert app_db.update_insurance_provider(pid, "Blue Cross", "654321") is True
    assert app_db.get_insurance_provider(pid)['provider_number'] == "654321"


# ----------------------------------------------------------------------
# The printed line is the practitioner's, not the app's
# ----------------------------------------------------------------------

def test_default_format(app_db):
    pid = app_db.add_insurance_provider("Blue Cross", "123456")
    assert provider_line(app_db.get_insurance_provider(pid)) == \
        "Blue Cross — Provider No. 123456"


def test_custom_format_is_used_verbatim(app_db):
    pid = app_db.add_insurance_provider(
        "Blue Cross", "123456",
        number_format="Provider #{number} (Blue Cross Ontario)")
    assert provider_line(app_db.get_insurance_provider(pid)) == \
        "Provider #123456 (Blue Cross Ontario)"


def test_format_needing_neither_placeholder_is_allowed(app_db):
    """Some insurers want a fixed string; the app should not insist."""
    pid = app_db.add_insurance_provider("Blue Cross", "123456",
                                        number_format="Registered provider")
    assert provider_line(app_db.get_insurance_provider(pid)) == "Registered provider"


def test_malformed_format_falls_back_rather_than_breaking_a_statement(app_db):
    pid = app_db.add_insurance_provider("Blue Cross", "123456",
                                        number_format="No. {nmuber}")
    assert provider_line(app_db.get_insurance_provider(pid)) == \
        DEFAULT_FORMAT.format(name="Blue Cross", number="123456")


def test_no_provider_prints_nothing(app_db):
    assert provider_line(None) is None


# ----------------------------------------------------------------------
# Assignment lives on the client
# ----------------------------------------------------------------------

def test_client_defaults_to_no_provider(app_db):
    cid = _client(app_db)
    assert app_db.get_client_provider(cid) is None


def test_assigning_and_changing_an_insurer(app_db):
    cid = _client(app_db)
    bc = app_db.add_insurance_provider("Blue Cross", "123456")
    gs = app_db.add_insurance_provider("Green Shield", "GS-99")

    app_db.set_client_provider(cid, bc)
    assert app_db.get_client_provider(cid)['name'] == "Blue Cross"

    app_db.set_client_provider(cid, gs)
    assert app_db.get_client_provider(cid)['name'] == "Green Shield"


def test_a_client_can_drop_their_insurer(app_db):
    """Changing to none must be as easy as changing to another."""
    cid = _client(app_db)
    bc = app_db.add_insurance_provider("Blue Cross", "123456")
    app_db.set_client_provider(cid, bc)

    app_db.set_client_provider(cid, None)
    assert app_db.get_client_provider(cid) is None
    # The provider itself survives — other clients may still use it.
    assert app_db.get_insurance_provider(bc) is not None


def test_one_clients_insurer_does_not_leak_to_another(app_db):
    a = _client(app_db, "INS-A")
    b = _client(app_db, "INS-B")
    bc = app_db.add_insurance_provider("Blue Cross", "123456")
    app_db.set_client_provider(a, bc)

    assert app_db.get_client_provider(b) is None


# ----------------------------------------------------------------------
# Deletion is refused while in use
# ----------------------------------------------------------------------

def test_deleting_an_unused_provider_works(app_db):
    pid = app_db.add_insurance_provider("Blue Cross", "123456")
    ok, in_use = app_db.delete_insurance_provider(pid)
    assert ok is True and in_use is None
    assert app_db.get_insurance_provider(pid) is None


def test_deleting_a_provider_in_use_is_refused_with_a_count(app_db):
    """Silently unassigning would strip the number from her statements with
    no visible cause."""
    bc = app_db.add_insurance_provider("Blue Cross", "123456")
    for n in range(3):
        app_db.set_client_provider(_client(app_db, f"INS-{n}"), bc)

    ok, in_use = app_db.delete_insurance_provider(bc)
    assert ok is False
    assert in_use == 3
    assert app_db.get_insurance_provider(bc) is not None


def test_provider_is_deletable_once_its_clients_are_reassigned(app_db):
    bc = app_db.add_insurance_provider("Blue Cross", "123456")
    cid = _client(app_db)
    app_db.set_client_provider(cid, bc)
    assert app_db.delete_insurance_provider(bc)[0] is False

    app_db.set_client_provider(cid, None)
    assert app_db.delete_insurance_provider(bc)[0] is True


# ----------------------------------------------------------------------
# Disposal knows about the new relationship (today's recurring lesson)
# ----------------------------------------------------------------------

def test_disposing_of_a_client_does_not_take_the_provider_with_them(app_db):
    bc = app_db.add_insurance_provider("Blue Cross", "123456")
    keep = _client(app_db, "INS-KEEP")
    drop = _client(app_db, "INS-DROP")
    app_db.set_client_provider(keep, bc)
    app_db.set_client_provider(drop, bc)

    assert app_db.archive_and_delete_client(drop) is True

    assert app_db.get_insurance_provider(bc) is not None
    assert app_db.get_client_provider(keep)['name'] == "Blue Cross"
