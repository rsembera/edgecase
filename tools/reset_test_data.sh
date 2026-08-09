#!/bin/bash
#
# Reset the EdgeCase TESTING data directory from a pre-v3 snapshot, so the
# encryption upgrade can be run from scratch as many times as needed.
#
# Nothing is ever deleted. The current testing directory is MOVED aside with a
# timestamp; if a reset turns out to be a mistake, the previous state is still
# on disk and can simply be moved back.
#
# Usage:  bash tools/reset_test_data.sh
#
set -euo pipefail

TARGET="/Users/rick/Applications/edgecase-testing"
SNAPSHOT="/Users/rick/Applications/edgecase-testing-PREV3-20260809-1724"
PRODUCTION="/Users/rick/Applications/edgecase"

fail() { echo "REFUSING: $1" >&2; exit 1; }

# --- Guards. Each of these exists because the alternative is losing data. ---

[ "$TARGET" != "$PRODUCTION" ] || fail "target is the production directory"
case "$TARGET" in
    *edgecase-testing) : ;;
    *) fail "target '$TARGET' is not an edgecase-testing path" ;;
esac

[ -f "$SNAPSHOT/data/edgecase.db" ] || fail "snapshot has no data/edgecase.db: $SNAPSHOT"

# The snapshot must predate the upgrade, or resetting to it proves nothing.
MAGIC=$(head -c 4 "$SNAPSHOT/data/.keyinfo" 2>/dev/null || echo "none")
[ "$MAGIC" = "ECC2" ] || fail "snapshot key-info is '$MAGIC', expected ECC2 (a pre-upgrade snapshot)"

if [ -e "$TARGET" ]; then
    [ -f "$TARGET/data/edgecase.db" ] || fail "'$TARGET' exists but is not an EdgeCase data directory"
fi

# A running server holds the database open; resetting underneath it would
# leave the process writing to a directory that has been moved away.
if lsof -nP -iTCP:8080 -sTCP:LISTEN >/dev/null 2>&1; then
    fail "something is listening on :8080 - stop the EdgeCase server first"
fi

# --- Do it. Move aside, never delete. ---

if [ -e "$TARGET" ]; then
    ASIDE="${TARGET}.old-$(date +%Y%m%d-%H%M%S)"
    mv "$TARGET" "$ASIDE"
    echo "  moved aside : $ASIDE"
fi

cp -a "$SNAPSHOT" "$TARGET"

NEW_MAGIC=$(head -c 4 "$TARGET/data/.keyinfo")
[ "$NEW_MAGIC" = "ECC2" ] || fail "restored key-info is '$NEW_MAGIC', expected ECC2"

echo "  restored    : $TARGET (key-info: $NEW_MAGIC, pre-upgrade)"
echo "  attachments : $(find "$TARGET/attachments" -type f ! -name '.*' | wc -l | tr -d ' ')"
echo
echo "Ready. Start the testing instance with:"
echo "  cd $PRODUCTION && EDGECASE_DATA=$TARGET venv/bin/python main.py"
echo
echo "Old copies (safe to remove yourself once you're happy):"
ls -d "${TARGET}".old-* 2>/dev/null | sed 's/^/  /' || echo "  none"
