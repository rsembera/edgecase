#!/bin/bash
# Measure the real minimum macOS of a built .app and compare it with the
# LSMinimumSystemVersion it declares. Fails if the bundle needs more than
# it says (macOS would install it on systems where it crashes at launch).
#
# Usage: packaging/check_macos_floor.sh ["dist/EdgeCase Equalizer.app"]
set -euo pipefail

APP="${1:-dist/EdgeCase Equalizer.app}"
[ -d "$APP" ] || { echo "No such bundle: $APP" >&2; exit 2; }

declared=$(/usr/libexec/PlistBuddy -c "Print LSMinimumSystemVersion" \
    "$APP/Contents/Info.plist")

# Highest LC_BUILD_VERSION minos of any Mach-O in the bundle, and its file.
worst=$(find "$APP" -type f -print0 | while IFS= read -r -d '' f; do
    m=$(vtool -show-build "$f" 2>/dev/null | awk '/minos/{print $2; exit}')
    if [ -n "$m" ]; then printf '%s\t%s\n' "$m" "$f"; fi
done | sort -t$'\t' -k1,1V | tail -1)

actual=${worst%%$'\t'*}
file=${worst#*$'\t'}

echo "Declared: macOS $declared"
echo "Actual:   macOS $actual  (${file#"$APP"/})"

if [ "$(printf '%s\n%s\n' "$declared" "$actual" | sort -V | tail -1)" != "$declared" ]; then
    echo "FAIL: bundle needs macOS $actual but declares $declared." >&2
    exit 1
fi
echo "OK — README and website should say macOS $actual or later."
