# EdgeCase Equalizer - Linux .deb Packaging Guide

This document describes how to build the Linux .deb package for EdgeCase Equalizer.

## Prerequisites

- Debian/Ubuntu-based Linux system
- Python 3.13 with venv support
- `dpkg-deb` (comes with Debian/Ubuntu)
- System packages: `python3-gi` (PyGObject/GTK bindings)

## Directory Structure

```
packaging/
├── icons/                    # App icons (tracked in git)
│   ├── edgecase-48x48.png
│   ├── edgecase-96x96.png
│   ├── edgecase-128x128.png
│   ├── edgecase-180x180.png
│   └── edgecase-256x256.png
└── deb/                      # Build directory (gitignored)
    ├── edgecase_1.0.0_amd64/ # Package staging
    └── edgecase_1.0.0_amd64.deb
```

## Build Steps

### 1. Create package directory structure

```bash
cd ~/Applications/edgecase/packaging/deb
rm -rf edgecase_1.0.0_amd64
mkdir -p edgecase_1.0.0_amd64/DEBIAN
mkdir -p edgecase_1.0.0_amd64/opt/edgecase
mkdir -p edgecase_1.0.0_amd64/usr/bin
mkdir -p edgecase_1.0.0_amd64/usr/share/applications
mkdir -p edgecase_1.0.0_amd64/usr/share/icons/hicolor/{48x48,96x96,128x128,180x180,256x256}/apps
```

### 2. Copy application files

```bash
cd ~/Applications/edgecase
cp -r ai core pdf web utils assets desktop.py main.py requirements.txt \
    packaging/deb/edgecase_1.0.0_amd64/opt/edgecase/
```

### 3. Create Python virtual environment and install dependencies

```bash
cd packaging/deb/edgecase_1.0.0_amd64/opt/edgecase
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Copy PyGObject (GTK bindings) from system

PyWebView requires GTK bindings which can't be installed via pip. Copy from system:

```bash
cp -r /usr/lib/python3/dist-packages/gi \
    packaging/deb/edgecase_1.0.0_amd64/opt/edgecase/venv/lib/python3.13/site-packages/
```

### 5. Create DEBIAN/control file

```bash
cat > packaging/deb/edgecase_1.0.0_amd64/DEBIAN/control << 'EOF'
Package: edgecase
Version: 1.0.0
Section: office
Priority: optional
Architecture: amd64
Maintainer: Richard Sembera <richard@lightinextension.ca>
Description: EdgeCase Equalizer - Practice management for independent therapists
 A local-first, PHIPA-compliant practice management application
 for solo therapy practitioners. Features client management,
 session notes, billing, and encrypted data storage.
EOF
```

### 6. Create launcher script

```bash
cat > packaging/deb/edgecase_1.0.0_amd64/usr/bin/edgecase << 'EOF'
#!/bin/bash
cd /opt/edgecase
source venv/bin/activate
exec python desktop.py "$@"
EOF
chmod +x packaging/deb/edgecase_1.0.0_amd64/usr/bin/edgecase
```

### 7. Create desktop entry

```bash
cat > packaging/deb/edgecase_1.0.0_amd64/usr/share/applications/edgecase.desktop << 'EOF'
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
```

### 8. Copy icons

```bash
cp packaging/icons/edgecase-48x48.png \
    packaging/deb/edgecase_1.0.0_amd64/usr/share/icons/hicolor/48x48/apps/edgecase.png
cp packaging/icons/edgecase-96x96.png \
    packaging/deb/edgecase_1.0.0_amd64/usr/share/icons/hicolor/96x96/apps/edgecase.png
cp packaging/icons/edgecase-128x128.png \
    packaging/deb/edgecase_1.0.0_amd64/usr/share/icons/hicolor/128x128/apps/edgecase.png
cp packaging/icons/edgecase-180x180.png \
    packaging/deb/edgecase_1.0.0_amd64/usr/share/icons/hicolor/180x180/apps/edgecase.png
cp packaging/icons/edgecase-256x256.png \
    packaging/deb/edgecase_1.0.0_amd64/usr/share/icons/hicolor/256x256/apps/edgecase.png
```

### 9. Build the .deb package

```bash
cd ~/Applications/edgecase/packaging/deb
dpkg-deb --build edgecase_1.0.0_amd64
```

## Installation

```bash
sudo dpkg -i edgecase_1.0.0_amd64.deb
sudo gtk-update-icon-cache /usr/share/icons/hicolor/
```

## Uninstallation

```bash
sudo dpkg -r edgecase
```

## Notes

- The `packaging/deb/` directory is gitignored except for `packaging/icons/`
- Icons are tracked in git so they don't need to be regenerated each build
- The venv includes PyGObject copied from the system (not pip-installable)
- Application data is stored in `~/.local/share/edgecase/`
