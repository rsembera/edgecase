# EdgeCase Distribution Notes

**Created:** December 29, 2025  
**Status:** Planning for PyApp packaging

---

## Data Storage Issue (RESOLVED)

### Problem
Originally, all user data (database, attachments, backups, AI models) was stored relative to the app folder. This would cause:

1. **Data loss on updates** — replacing the app bundle wipes user data
2. **macOS App Translocation** — downloaded apps run from randomized read-only location
3. **Permission issues** — writing inside `/Applications/` is problematic

### Solution Implemented
`core/config.py` now detects installed vs development mode:

**Development mode** (default):
- Data stored relative to app folder (`~/apps/edgecase/data/`, etc.)
- Triggered when running from source

**Installed mode**:
- Data stored in platform-appropriate user directories
- Triggered by:
  - `PYAPP` environment variable (set by PyApp)
  - Running from `/Applications/` (macOS)
  - Running from `Program Files` (Windows)
  - `EDGECASE_INSTALLED` env var (manual override)

**Data locations in installed mode:**
| Platform | Location |
|----------|----------|
| macOS | `~/Library/Application Support/EdgeCase/` |
| Windows | `%APPDATA%\EdgeCase\` |
| Linux | `~/.local/share/EdgeCase/` |

---

## Database Reset Feature (TODO)

### Need
Users need a way to wipe test data before using the app for real clients. Since EdgeCase doesn't allow entry deletion (by design, for compliance), there's no way to clean up after testing.

### Proposed Implementation
Add "Reset Database" option in Settings:

1. Requires current password confirmation
2. Requires typing "RESET" to confirm
3. Wipes:
   - Database (`data/edgecase.db`)
   - All attachments (`attachments/`)
   - All backups (`backups/`)
   - Optionally: AI model (large file, user might want to keep)
   - Keeps: Settings? Or full reset?
4. Returns to first-run state (set new password)

### Location
Settings page, possibly in a "Danger Zone" section at the bottom.

---

## PyApp Packaging (TODO)

### What PyApp Does
- Bundles Python + dependencies + app code into single executable
- Sets `PYAPP` environment variable when running
- Handles cross-platform distribution

### Steps Needed
1. Create PyApp configuration
2. Test that installed mode detection works
3. Test data persistence across "updates" (reinstalls)
4. Create installers for macOS, Windows, Linux
5. Test on clean machines

### Open Questions
- How to handle AI model download in packaged app?
- Should we sign the macOS app? (cost vs convenience)
- Windows SmartScreen warnings without signing?

---

## First-Run Experience (TODO)

For distributed app, consider:

1. **Welcome screen** explaining what EdgeCase is
2. **Demo data option** — "Load sample data to explore" vs "Start fresh"
3. **Setup wizard** — practice name, your name, credentials
4. **Backup location prompt** — especially for cloud folder setup

---

## Testing Checklist Before Distribution

- [ ] Fresh install on clean macOS
- [ ] Fresh install on clean Windows
- [ ] Fresh install on clean Linux (Ubuntu)
- [ ] Data persists after app update/reinstall
- [ ] Database reset works correctly
- [ ] AI model download works in packaged app
- [ ] Backup/restore works with new paths
- [ ] All features work in installed mode

---

*Last updated: December 29, 2025*
