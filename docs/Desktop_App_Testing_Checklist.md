# Desktop App Testing Checklist

Testing guide for EdgeCase Equalizer desktop packages (.app for macOS, .deb for Linux).

## Pre-Test Setup

### macOS (.app)
- [ ] Use testing data: `EDGECASE_DATA=/Users/rick/Applications/edgecase-testing`
- [ ] Run: `"/Users/rick/Applications/edgecase/dist/EdgeCase Equalizer.app/Contents/MacOS/EdgeCase Equalizer"`
- [ ] Testing DB password:

### Linux (.deb)
- [ ] Install: `sudo dpkg -i edgecase_1.0.0_amd64.deb`
- [ ] Run from menu OR: `EDGECASE_DATA=/home/rick/Applications/edgecase-testing edgecase`
- [ ] Testing DB password: `Alkahest131!`

---

## Core Functionality

### Database & Authentication
- [ ] First run: Master password creation works
- [ ] Login with existing database works
- [ ] Logout works
- [ ] Session timeout works (if configured)

### Client Management
- [ ] Create new client
- [ ] Edit client
- [ ] View client file
- [ ] Delete client (soft delete)

### Session Notes
- [ ] Create session note
- [ ] Edit session note
- [ ] View session in client file

### Billing & Statements
- [ ] Create income entry
- [ ] Create expense entry
- [ ] Generate statement
- [ ] View ledger

---

## Desktop-Specific Features

### PDF/File Handling
- [ ] View PDF (should open in system PDF viewer, not browser popup)
- [ ] Download attachment (should save to ~/Downloads with toast notification)
- [ ] View other attachments (images, etc.)

### Window Behavior
- [ ] Window opens at correct size (1280x800)
- [ ] Window can be resized (min 800x600)
- [ ] Window title shows "EdgeCase Equalizer"

### localStorage Persistence
- [ ] Change view mode (Detailed/Compact)
- [ ] Change theme/card style
- [ ] Close app completely
- [ ] Reopen app
- [ ] Settings should persist after reopen

### Backup on Close
- [ ] Close the app window
- [ ] Check terminal output for "Running shutdown backup..." message
- [ ] Verify backup completed successfully

---

## AI Scribe (Optional Feature)

### Model Download
- [ ] Navigate to AI Scribe settings
- [ ] Initiate model download
- [ ] Download progress displays correctly
- [ ] Model downloads successfully to models/ directory

### Transcription
- [ ] Record or upload audio
- [ ] Transcription runs successfully
- [ ] Results display correctly

**Note:** AI Scribe requires ~4.6GB model download. Skip if not testing this feature.

---

## Platform-Specific Checks

### macOS Only
- [ ] App icon appears in Dock while running
- [ ] App appears in Force Quit menu
- [ ] Cmd+Q closes app properly
- [ ] After notarization: App runs without Gatekeeper warnings on other Macs

### Linux Only
- [ ] App icon appears in application menu
- [ ] Desktop entry launches app correctly
- [ ] xdg-open works for file viewing
- [ ] GTK/WebKit rendering looks correct

---

## Edge Cases

### Error Handling
- [ ] Wrong password shows error message
- [ ] Network errors handled gracefully (if applicable)
- [ ] Missing files/directories handled

### Data Integrity
- [ ] Changes persist after app restart
- [ ] No data corruption after forced close
- [ ] Backup files are valid

---

## Post-Test Cleanup

- [ ] Remove test data if needed
- [ ] Uninstall .deb if testing: `sudo dpkg -r edgecase`

---

## Known Limitations

### macOS
- No password manager autofill (WKWebView limitation)
- First notarization takes 24-72 hours

### Linux
- Requires GTK3 and WebKit2GTK dependencies
- No system tray icon (not implemented)

---

## Version Tested

- **Date:** _______________
- **macOS version:** _______________
- **Linux distro/version:** _______________
- **EdgeCase version:** 2.0.0
- **Tester:** _______________
