"""recover_if_interrupted() must leave a rotate_master marker alone.

EdgeCase's startup recovery exists to UNDO interrupted migrations by restoring
a backup. A master-key rotation (core.master_rotation) rolls forward instead:
its backup may be up to a day old, and restoring it could discard a day of
clinical notes to fix a key problem. This is the single highest-risk
integration point in the rotation change, so it gets its own file.
"""
import json

import pytest

from core import master_rotation as rot
from core import migrate_crypto as mc
from tests.test_master_rotation import (  # noqa: F401  (fixture)
    PW, _all_files, _crash_at, _keyinfo, _no_residue, assert_fully_openable,
    install,
)


def test_recover_if_interrupted_does_not_roll_back_a_rotation(install):  # noqa: F811
    """THE highest-value test in the set. EdgeCase's startup recovery exists
    to undo interrupted migrations. A rotation rolls forward; the routine
    must recognise the marker and leave everything — marker, state, files,
    database, key file — exactly as it found it."""
    root = install["root"]
    with pytest.MonkeyPatch.context() as crash:
        _crash_at(crash, "_commit_rotation")
        with pytest.raises(RuntimeError):
            rot.rotate_master(PW, root=root)

    marker = root / "data" / ".v2_migrating"
    state = root / "data" / ".master_rotation_state"
    assert json.loads(marker.read_text())["kind"] == "rotate_master"
    snapshot = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    rolled_back = {"n": 0}

    with pytest.MonkeyPatch.context() as spy:
        spy.setattr(mc, "_rollback", lambda *a, **k: rolled_back.__setitem__("n", 1))
        outcome = mc.recover_if_interrupted(root=root)

    assert outcome == "rotation_pending"
    assert rolled_back["n"] == 0, "recover_if_interrupted rolled back a rotation"
    assert marker.exists() and state.exists()
    for p, data in snapshot.items():
        assert p.read_bytes() == data, f"{p} was modified by startup recovery"

    # And the rotation still completes afterwards.
    result = rot.rotate_master(PW, root=root)
    assert_fully_openable(root, PW, result["recovery_key"])
    _no_residue(root)


def test_recover_if_interrupted_still_handles_the_other_kinds(install):  # noqa: F811
    """Adding the guard must not swallow the markers it is not for."""
    root = install["root"]
    (root / "data" / ".v2_migrating").write_text(json.dumps(
        {"kind": "migrate_v3", "backup_filename": "x.zip",
         "backup_dir": str(root / "backups")}))
    assert mc.recover_if_interrupted(root=root) == "finalized"
    assert not (root / "data" / ".v2_migrating").exists()
