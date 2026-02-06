# EdgeCase Equalizer — Distribution Plan

**Created:** January 5, 2026  
**Revised:** February 5, 2026  
**Status:** In production since January 3, 2026. Source available on GitHub. Packaging next.

---

## Overview

**Platforms:** Mac (primary), Linux (secondary), Source (always available)  
**Price:** Free / Open Source (AGPL-3.0)  
**Architecture:** Flask app running locally, accessed via browser or native window

EdgeCase runs as a local web server on the user's machine. Data never leaves the computer. The packaging strategy wraps this into something that feels like a native desktop app.

---

## Packaging Stack

Two tools, complementary roles:

| Tool | Role | What It Does |
|------|------|-------------|
| **PyApp** | Installer/bundler | Bundles Python 3.13 + all dependencies into a single executable. Handles first-run setup. |
| **Pywebview** | Window manager | Opens Flask in a native OS window (WebKit on Mac, WebView2 on Windows) instead of a browser tab. No address bar, no tabs — looks like a desktop app. |

**Why both?** PyApp solves "how do I install this without knowing Python." Pywebview solves "why is my therapy software running in Safari." Together they create a proper .app that a non-technical therapist can drag to Applications and double-click.

**Pywebview integration:** ~5 lines in main.py. Detects packaged mode, launches native window instead of opening browser. Falls back to browser if pywebview unavailable (source installs).

```python
# Simplified concept
if os.environ.get('EDGECASE_DESKTOP'):
    import webview
    webview.create_window('EdgeCase Equalizer', 'http://localhost:8080')
    webview.start()
else:
    webbrowser.open('http://localhost:8080')
```

Flask code stays identical either way. Pywebview is purely a window around the same app.

---

## Platform Details

### Mac (.dmg) — Primary

**Build chain:** PyApp + Pywebview → .app bundle → signed → .dmg

- [ ] Install and configure PyApp
- [ ] Add pywebview to requirements (uses WebKit on Mac, no extra engine)
- [ ] Bundle Python 3.13 + all dependencies
- [ ] Handle SQLCipher native extension
- [ ] Build .app bundle
- [ ] Test on clean Mac (no Python installed)
- [ ] Create .dmg for drag-to-Applications install

**Code signing:**
- [ ] Enroll in Apple Developer Program
- [ ] Obtain Developer ID certificate
- [ ] Sign the .app bundle
- [ ] Submit for notarization
- [ ] Test that signed app opens without Gatekeeper warnings

Without signing, users see "unidentified developer" and must manually override in System Settings. For a professional tool targeting non-technical therapists, that's a non-starter.

### Linux (.deb) — Secondary

**Build chain:** fpm wrapping Python app + dependencies

- [ ] Test source install on Mercury (Debian)
- [ ] Install fpm (`gem install fpm`)
- [ ] Build .deb package
- [ ] Test .deb install on clean Debian/Ubuntu
- [ ] Add to GitHub releases

Pywebview on Linux uses GTK/WebKit — works but less polished than Mac. Linux users comfortable running from source are the likely audience anyway, so .deb is a convenience, not a requirement.

### Source (GitHub) — Always Available

- Clone repo, create venv, pip install, run
- README has full instructions
- No pywebview needed — opens in browser
- For developers, tinkerers, and anyone who wants to read the code before trusting it

### Windows — Not Supported

Source code works on Windows (Python is cross-platform). No packaged installer. Windows users who want EdgeCase can run from source or use Jane.

---

## Data Storage

User data lives outside the app bundle so updates don't wipe anything:

| Platform | Data Location |
|----------|--------------|
| Mac (installed) | `~/Library/Application Support/EdgeCase/` |
| Linux (installed) | `~/.local/share/EdgeCase/` |
| Source/dev | Relative to app folder |

Detection is automatic via `core/config.py`: checks for `PYAPP` env var, `/Applications/` path, or `EDGECASE_INSTALLED` override.

---

## Update Strategy

**Philosophy:** Source stays current. Packages release quarterly unless critical bugs.

### Source (GitHub)
- Updated continuously
- Users update via `git pull`
- Living version of EdgeCase

### Mac (.dmg) and Linux (.deb)
- Quarterly releases (or critical bug fixes)
- Manual download from GitHub Releases — no auto-updater
- User data persists across updates (stored outside app bundle)

### Version Numbering

```
1.0.0 — Initial release
1.0.x — Bug fixes
1.x.0 — Minor features
2.0.0 — Breaking changes (if ever)
```

### Release Checklist

- [ ] Update version in app
- [ ] Write release notes
- [ ] Build and sign Mac .app, create .dmg
- [ ] Build Linux .deb
- [ ] Upload to GitHub Releases
- [ ] Update website download links

### Future Consideration
- "Check for updates" link in Settings → opens GitHub Releases page
- Not a priority for v1.x

---

## Distribution Channels

| Channel | What | When |
|---------|------|------|
| GitHub Releases | .dmg, .deb, source | Primary, always |
| edgecaseequalizer.ca | Download links, screenshots, explanation | After packaging done |
| README | Installation instructions, screenshots | Done |

---

## Technical Notes

### Why Pywebview Over Electron

Electron bundles an entire Chromium browser (~200MB). Pywebview uses the OS's existing web renderer (WebKit on Mac, WebView2 on Windows). Result: smaller package, smaller attack surface, same native-window effect.

EdgeCase already has desktop mode with heartbeat monitoring (auto-shutdown when browser closes). Pywebview replaces the "open in browser" step with a native window, keeping all existing shutdown/heartbeat logic.

### SQLCipher Packaging

The trickiest part of packaging. SQLCipher is a native C extension that needs to be compiled for the target platform. Options:
- Bundle pre-compiled .dylib/.so with PyApp
- Use sqlcipher3 Python package (handles compilation)
- Test thoroughly on clean installs

### AI Model

The Hermes 3 8B model (~4.6GB) is NOT bundled with the installer. Downloaded on first use via Settings page. Model management already handles this — progress tracking, platform detection, storage in user data directory.

---

*"Every practice is an edge case"*
