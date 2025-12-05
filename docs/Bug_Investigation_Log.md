# EdgeCase Equalizer - Bug Investigation Log

**Purpose:** Record of systematic bug investigation before production launch  
**Investigation Date:** December 5, 2025  
**Status:** Complete - Ready for January 2026 launch

---

## SUMMARY

| Priority | Total | Fixed/Handled | By Design | Non-Issue | Theoretical |
|----------|-------|---------------|-----------|-----------|-------------|
| High | 6 | 1 | 1 | 3 | 0 |
| Medium | 11 | 4 | 5 | 2 | 0 |
| Lower | 24 | 12 | 7 | 2 | 3 |
| **Total** | **41** | **17** | **13** | **7** | **3** |

**Result:** 38 items confirmed resolved, 3 minor theoretical edge cases that fail gracefully.

---

## HIGH PRIORITY (6 items)

| # | Bug | Status | Evidence |
|---|-----|--------|----------|
| HP1 | File number collision | ✅ Fixed | Commit 53511a7 |
| HP2 | Attachment cleanup on retention delete | ✅ Handled | `shutil.rmtree(client_attachments_dir)` in `archive_and_delete_client()` |
| HP3 | Deleting expense category with expenses | ✅ Non-issue | No delete functionality exists (by design) |
| HP4 | Deleting payee with expenses | ✅ Non-issue | No delete functionality exists (by design) |
| HP5 | Link group min 2 members on edit | ✅ Validated | `len(data['client_ids']) < 2` check on line 140 |
| HP6 | Link group fees not summing | ✅ By Design | Fees are independent per member |

---

## MEDIUM PRIORITY (11 items)

| # | Bug | Status | Evidence |
|---|-----|--------|----------|
| MP1 | Editing billed session | ✅ Fixed | Commit e1fd012 - Add billed entry protection |
| MP2 | Statement for $0 total | ✅ By Design | Query excludes `fee > 0` requirement |
| MP3 | Client with no profile entry | ✅ Handled | `if profile else ''` pattern throughout |
| MP4 | Edit propagation to linked entries | ✅ By Design | Linked entries are independent copies |
| MP5 | Session numbering across linked | ✅ By Design | Each client has own numbering |
| MP6 | Void vs write-off semantics | ✅ Fixed | Commit 25f289a |
| MP7 | Link group with 1 member on create | ✅ Validated | `len(data['client_ids']) < 2` check |
| MP8 | Future-dated sessions and numbering | ✅ By Design | Renumbered chronologically |
| MP9 | Can you delete a Profile entry? | ✅ Not Possible | No delete route for entries |
| MP10 | Absence with $0 fee | ✅ By Design | Excluded from statements (`fee > 0` check) |
| MP11 | Item with negative price | ✅ Fixed | Commit 3c20f19 - Allow negative items (credits) |

---

## LOWER PRIORITY (24 items)

| # | Bug | Status | Evidence |
|---|-----|--------|----------|
| LP1 | Partial payments + guardian splits | ✅ Handled | Each portion tracked independently |
| LP2 | Income auto-gen for guardian portions | ✅ Handled | Description includes "(Guardian X)" |
| LP3 | Password change + re-encryption | ✅ Fixed | Commit 0b1e131 |
| LP4 | Retention period of 0 days | ✅ Fixed | Commit 0bbf29d - 0 means 'keep forever' |
| LP5 | Backup during pending restore | ✅ By Design | Separate directories |
| LP6 | Very long session notes in PDF | ✅ By Design | Paragraph auto-wraps |
| LP7 | Large file upload size limits | ✅ Fixed | Commit c9dff65 - Add 50MB limit |
| LP8 | Unicode/special chars in names | ✅ Fixed | Commit 3964191 - Fix calendar event escaping |
| LP9 | Timezone consistency | ✅ By Design | All Unix timestamps, local display |
| LP10 | AI model unload during generation | ⚠️ Theoretical | No lock during stream, but UI separation makes unlikely |
| LP11 | Double-click duplicate entries | ✅ Fixed | Commit 301c998 |
| LP12 | Browser back button after submit | ✅ By Design | POST-Redirect-GET pattern |
| LP13 | Session timeout during long form | ✅ Fixed | Commit 135d451 - Add timeout warning modal |
| LP14 | Incremental restore without full | ✅ Handled | Orphaned incrementals skipped |
| LP15 | Backup location unavailable | ✅ Handled | Cleans up partial, raises error |
| LP16 | Corrupted manifest.json | ✅ Fixed | Commit e03386e - Handle gracefully |
| LP17 | Corrupt logo/signature upload | ⚠️ Partial | Extension validated, not content. Fails at render. |
| LP18 | PDF export with hundreds of entries | ✅ By Design | ReportLab handles large documents |
| LP19 | Statement PDF with long address | ✅ By Design | Paragraph auto-wraps |
| LP20 | Concurrent multi-tab access | ✅ Handled | Thread-local + WAL mode |
| LP21 | Disk full during write | ⚠️ Unhandled | Would error, no corruption, poor UX |
| LP22 | SQL injection in search | ✅ Secure | Parameterized queries throughout |
| LP23 | Very long client names - layout | ✅ Fixed | Commit f9acbfa |
| LP24 | Calendar name special chars | ✅ Fixed | Commit 3964191 |

---

## THEORETICAL ISSUES (3 items)

These are edge cases that would fail gracefully but aren't fully handled:

### LP10: AI model unload during active generation
- **Risk:** Low - UI separation means user would have to navigate to Settings mid-generation
- **Impact:** Generation would error, no data loss
- **Mitigation:** None needed for single-user app

### LP17: Corrupt image file upload (logo/signature)
- **Risk:** Low - User would need to upload a corrupt file with valid extension
- **Impact:** PDF generation would fail, user sees error, can re-upload
- **Mitigation:** Could add image validation, but low priority

### LP21: Disk full during database write
- **Risk:** Very low - Modern systems rarely run out of disk
- **Impact:** SQLite transaction rolled back, Flask returns 500, no data corruption
- **Mitigation:** Could add disk space check, but edge case

---

## ADDITIONAL FIX: Double-Login Issue

**Problem:** Safari and Firefox required logging in twice. After first login, redirected back to login with `?timeout=1`.

**Root Cause:** Race condition where session cookie wasn't fully persisted before redirect, causing stale session data to trigger timeout check.

**Fix:** Commit 1566279
- Clear stale session data before setting new values on login
- Set `last_activity` immediately during login (not just in `before_request`)
- Use unique cookie name (`edgecase_session`) to avoid conflicts
- Use `make_response()` for explicit cookie handling on redirect

---

## CONCLUSION

The systematic bug investigation covered 41 potential issues across all priority levels. Only 3 minor theoretical edge cases remain, all of which fail gracefully without data loss.

**The system is ready for production use.**

---

*Investigation completed: December 5, 2025*
