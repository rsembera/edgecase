# EdgeCase Equalizer - macOS Packaging Guide

This document describes how to build, sign, notarize, and package the macOS .app and .dmg for EdgeCase Equalizer.

## Prerequisites

- macOS with Xcode command line tools
- Python 3.13+ with py2app
- Apple Developer ID certificate (for signing)
- Apple Developer account (for notarization)
- App-specific password for notarization

## Directory Structure

```
packaging/
├── dmg_background.png        # DMG installer background (tracked in git)
└── icons/                    # Shared with Linux

assets/
└── icon.icns                 # macOS app icon

dist/
├── EdgeCase Equalizer.app/   # Built application
└── EdgeCase-1.0.0.dmg        # Final distributable
```

## Signing Credentials

- **Certificate:** `Developer ID Application: RICHARD L SEMBERA (2GKBD5N2AH)`
- **Team ID:** `2GKBD5N2AH`
- **Keychain Profile:** `EdgeCase Notarization`
- **Apple ID:** `rsembera@ncf.ca`

## Build Steps

### 0. Crypto v2 migration — pre-build checklist (added 2026-06-14)

The attachment-encryption migration (Fernet → Argon2id / AES-256-GCM) runs
automatically on each user's first launch after updating; their data in
`~/Library/Application Support/EdgeCase/` is migrated in place, and the
migration runner takes its own verified backup first. Before building, confirm
in `setup_app.py`:

- **`includes` lists every new core module.** py2app does not auto-detect them.
  `core.encryption` is listed; you must also add `core.encryption_v2` and the
  migration-runner module (e.g. `core.migrate_crypto`) or packaged users hit an
  ImportError at launch. (Linux does not need this — its build copies all of
  `core/`.)
- **Add `argon2-cffi` to py2app `packages`.** EdgeCase derives the Argon2id
  master key with `argon2-cffi` (cryptography's own Argon2id measured ~5× slower
  on the M4 — ~3.9s vs ~0.74s). Add `'argon2'` and `'_argon2_cffi_bindings'` to
  the `packages` list in `setup_app.py`, or packaged users hit an ImportError.
  (`cryptography` is still bundled — it handles HKDF and AES-GCM.)
- **Do not remove v1 (Fernet) read-compat** for at least a release cycle or two
  after this ships — see `Architecture_Decisions.md`. A user slow to update, or
  one whose migration failed and stayed on v1, must still be able to read files.

### 1. Prepare for build

Temporarily rename `pyproject.toml` to prevent py2app conflicts:

```bash
cd ~/Applications/edgecase
mv pyproject.toml pyproject.toml.bak
```

### 2. Build the .app bundle with py2app

```bash
source venv/bin/activate
python setup_app.py py2app
```

### 3. Restore pyproject.toml

```bash
mv pyproject.toml.bak pyproject.toml
```

### 4. Sign all binary files individually

**CRITICAL:** You must sign all `.so` and `.dylib` files individually BEFORE signing the app bundle, or notarization will fail.

```bash
cd ~/Applications/edgecase

# Find and sign all .so and .dylib files
find "dist/EdgeCase Equalizer.app" -type f \( -name "*.so" -o -name "*.dylib" \) | while read -r file; do
    codesign --force --options runtime --timestamp \
        --sign "Developer ID Application: RICHARD L SEMBERA (2GKBD5N2AH)" \
        "$file"
done
```

### 5. Sign the app bundle

```bash
codesign --force --options runtime --timestamp \
    --sign "Developer ID Application: RICHARD L SEMBERA (2GKBD5N2AH)" \
    --deep "dist/EdgeCase Equalizer.app"
```

### 6. Verify signature

```bash
codesign --verify --deep --strict "dist/EdgeCase Equalizer.app"
spctl --assess --type exec "dist/EdgeCase Equalizer.app"
```

## Notarization

### 1. Create a ZIP for notarization

```bash
cd dist
ditto -c -k --keepParent "EdgeCase Equalizer.app" "EdgeCase_Equalizer.zip"
```

### 2. Submit for notarization

```bash
xcrun notarytool submit "EdgeCase_Equalizer.zip" \
    --keychain-profile "EdgeCase Notarization" \
    --wait
```

This will return a submission ID and wait for completion (usually 5-15 minutes).

### 3. Check notarization status (if needed)

```bash
xcrun notarytool log <submission-id> --keychain-profile "EdgeCase Notarization"
```

### 4. Staple the notarization ticket

```bash
xcrun stapler staple "EdgeCase Equalizer.app"
```

### 5. Clean up

```bash
rm EdgeCase_Equalizer.zip
```

## DMG Creation

### 1. Create a temporary DMG folder

```bash
cd ~/Applications/edgecase/dist
mkdir dmg_temp
cp -R "EdgeCase Equalizer.app" dmg_temp/
ln -s /Applications dmg_temp/Applications
cp ../packaging/dmg_background.png dmg_temp/.background.png
```

### 2. Create the DMG

```bash
hdiutil create -volname "EdgeCase Equalizer" \
    -srcfolder dmg_temp \
    -ov -format UDZO \
    "EdgeCase-1.0.0.dmg"
```

### 3. Clean up

```bash
rm -rf dmg_temp
```

## Setting up Keychain Profile (One-time)

To store notarization credentials in the keychain:

```bash
xcrun notarytool store-credentials "EdgeCase Notarization" \
    --apple-id "rsembera@ncf.ca" \
    --team-id "2GKBD5N2AH"
```

You'll be prompted for your app-specific password.

## Troubleshooting

### Notarization fails with "invalid signature"

Make sure you signed ALL binary files individually before signing the app bundle. Check how many files need signing:

```bash
find "dist/EdgeCase Equalizer.app" -type f \( -name "*.so" -o -name "*.dylib" \) | wc -l
```

### "Developer cannot be verified" warning

The app hasn't been notarized, or the ticket hasn't been stapled. Re-run notarization steps.

### py2app build fails

- Ensure `pyproject.toml` is renamed before building
- Check that all dependencies are in `requirements.txt`
- Verify Python version matches (3.13+)

## Notes

- The DMG background image (`packaging/dmg_background.png`) shows "Drag to Applications" with an arrow
- The app icon (`assets/icon.icns`) is the three-bar EdgeCase logo
- Application data is stored in `~/Library/Application Support/EdgeCase/`
- Notarization requires an internet connection and may take 5-15 minutes
