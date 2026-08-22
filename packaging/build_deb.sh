#!/bin/bash
# Build the EdgeCase Equalizer .deb. Run from the repo root on a Debian/Ubuntu box.
# Usage: packaging/build_deb.sh 2.0.0
set -euo pipefail

VERSION="${1:?usage: build_deb.sh VERSION}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PKG="edgecase_${VERSION}_amd64"
STAGE="$REPO/packaging/deb/$PKG"
APP="$STAGE/opt/edgecase"
PYVER="$(python3 -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')"

echo "== Staging $PKG (python $PYVER)"
rm -rf "$STAGE"
mkdir -p "$STAGE/DEBIAN" "$APP" "$STAGE/usr/bin" "$STAGE/usr/share/applications"
for s in 48x48 96x96 128x128 180x180 256x256; do
    mkdir -p "$STAGE/usr/share/icons/hicolor/$s/apps"
    cp "$REPO/packaging/icons/edgecase-$s.png" "$STAGE/usr/share/icons/hicolor/$s/apps/edgecase.png"
done

echo "== Copying application"
cd "$REPO"
cp -r ai core pdf web utils desktop.py main.py requirements.txt "$APP/"
find "$APP" -name __pycache__ -type d -prune -exec rm -rf {} +

echo "== Building venv"
python3 -m venv "$APP/venv"
"$APP/venv/bin/pip" install -q --upgrade pip
"$APP/venv/bin/pip" install -q -r "$APP/requirements.txt"

echo "== Copying PyGObject from system"
cp -r /usr/lib/python3/dist-packages/gi "$APP/venv/lib/python$PYVER/site-packages/"

echo "== Smoke import"
( cd "$APP" && venv/bin/python -c "import gi, sqlcipher3, argon2, cryptography, webview; import web.cli; print('imports ok')" )

cat > "$STAGE/DEBIAN/control" << EOF
Package: edgecase
Version: $VERSION
Section: office
Priority: optional
Architecture: amd64
Depends: python3 (>= 3.11), python3-gi, gir1.2-gtk-3.0, gir1.2-webkit2-4.1
Maintainer: Richard Sembera <richard@lightinextension.ca>
Description: EdgeCase Equalizer - Practice management for independent therapists
 A local-first, PHIPA-compliant practice management application
 for solo therapy practitioners. Features client management,
 session notes, billing, and encrypted data storage.
EOF

cat > "$STAGE/usr/bin/edgecase" << 'EOF'
#!/bin/bash
cd /opt/edgecase
source venv/bin/activate
exec python desktop.py "$@"
EOF
chmod +x "$STAGE/usr/bin/edgecase"

cat > "$STAGE/usr/share/applications/edgecase.desktop" << 'EOF'
[Desktop Entry]
Name=EdgeCase Equalizer
Comment=Practice management for independent therapists
Exec=/usr/bin/edgecase
Icon=edgecase
Terminal=false
Type=Application
Categories=Office;
Keywords=therapy;practice;management;billing;
EOF

echo "== dpkg-deb"
cd "$REPO/packaging/deb"
dpkg-deb --build --root-owner-group "$PKG" > /dev/null
ls -la "$PKG.deb"
sha256sum "$PKG.deb"
