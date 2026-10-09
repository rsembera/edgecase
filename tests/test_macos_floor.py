"""The bundle's declared minimum macOS must not undersell what it needs.

py2app copies in the build machine's Homebrew Python and its extension
modules, all compiled for that machine's macOS. LSMinimumSystemVersion is
only a label: if it is lower than the real requirement, macOS installs the
app on older systems and it dies at launch. 2.0.4 declared 10.15 (and the
website said 12+) while every lib-dynload module required 26.0.

The bundled Python's own deployment target is the floor for everything it
compiled, so the declared value must be at least that. Bundled native
libraries can be higher still; packaging/check_macos_floor.sh measures the
built .app for those.
"""
import sys
import sysconfig

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "darwin",
                                reason="macOS bundle only")


def _ver(s):
    return tuple(int(p) for p in str(s).split("."))


def test_declared_floor_covers_build_python():
    import setup_app
    declared = setup_app.OPTIONS["plist"]["LSMinimumSystemVersion"]
    target = sysconfig.get_config_var("MACOSX_DEPLOYMENT_TARGET")
    assert target, "build Python reports no deployment target"
    assert _ver(declared) >= _ver(target), (
        f"Info.plist declares macOS {declared}, but the bundled Python "
        f"is built for {target}")
