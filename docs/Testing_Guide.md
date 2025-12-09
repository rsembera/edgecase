# EdgeCase Equalizer - Comprehensive Testing Guide

**Purpose:** Systematic testing of all features before production launch  
**Created:** December 7, 2025  
**Estimated Time:** 2-3 hours

---

## FICTIONAL TEST DATA

### Client Types to Create

| Name | Color | Retention |
|------|-------|-----------|
| Low Fee | Dusty Rose | 10 years |
| Pro Bono | Soft Gray | 7 years |

*(Active and Inactive are built-in)*

### Fictional Clients

| Name | Type | Fee (in Profile) | Purpose |
|------|------|------------------|---------|
| **Alice Anderson** | Active | $150 (13% tax) | Standard individual client |
| **Bob Baker** | Active | $150 (13% tax) | Minor with guardian billing (60/40 split) |
| **Carol Chen** | Active | (set in link group) | Half of couples therapy |
| **David Chen** | Active | (set in link group) | Half of couples therapy |
| **Emma Evans** | Low Fee | $80 (0% tax) | Sliding scale client |
| **Frank Foster** | Pro Bono | $0 | Pro bono client |
| **Grace Green** | Active | (set in link group) | Family therapy (parent) |
| **Henry Green** | Active | (set in link group) | Family therapy (teen, minor with 2 guardians) |

---

## PHASE 1: SETUP & CLIENT TYPES

### 1.1 Verify Settings (5 min)

- [ ] Open Settings
- [ ] Confirm Practice Information is filled in
- [ ] Confirm Logo and Signature are uploaded
- [ ] Confirm Calendar settings work
- [ ] Confirm Backup frequency is set
- [ ] Check File Number Format

### 1.2 Create Client Types (5 min)

**Create "Low Fee" type:**
- [ ] Go to Main View → Edit Types
- [ ] Click "Add Type"
- [ ] Name: `Low Fee`
- [ ] Color: Dusty Rose
- [ ] Retention: 10 years
- [ ] Save

**Create "Pro Bono" type:**
- [ ] Click "Add Type"
- [ ] Name: `Pro Bono`
- [ ] Color: Soft Gray
- [ ] Retention: 7 years
- [ ] Save

**Verify:**
- [ ] Both types appear in the types list
- [ ] Colors display correctly
- [ ] Can edit a type (change color, save)

---

## PHASE 2: CREATE CLIENTS

### 2.1 Standard Client - Alice Anderson (5 min)

- [ ] Main View → Add Client
- [ ] First: `Alice`, Last: `Anderson`
- [ ] Type: Active
- [ ] Save → redirected to Profile

**Complete Profile:**
- [ ] Date of Birth: 1985-03-15
- [ ] Email: alice@example.com
- [ ] Cell: (613) 555-0101
- [ ] Preferred Contact: Text
- [ ] OK to Leave Message: Yes
- [ ] Address: 123 Main St, Ottawa, ON K1A 0A1
- [ ] Emergency Contact: John Anderson, Spouse, (613) 555-0102
- [ ] Referral Source: Google search

**Set Fee Override:**
- [ ] Base Price: $150.00
- [ ] Tax Rate: 13%
- [ ] Total: $169.50 (should auto-calculate)
- [ ] Default Duration: 50 minutes

- [ ] Additional Info: "Initial consultation completed. Presenting with work-related anxiety."
- [ ] Save

**Verify:**
- [ ] Profile shows in client file
- [ ] Fee override displays in profile card
- [ ] Client appears in Main View with correct type color

### 2.2 Minor with Guardian Billing - Bob Baker (10 min)

- [ ] Add Client: `Bob Baker`, Type: Active
- [ ] Complete Profile basics (DOB: 2012-06-20 - makes him 12)

**Set Fee Override:**
- [ ] Base: $150.00, Tax: 13%, Total: $169.50
- [ ] Duration: 50 minutes

**Guardian Billing Setup:**
- [ ] Check "Client is a minor"
- [ ] Guardian 1 Name: `Patricia Baker`
- [ ] Guardian 1 Email: patricia.baker@example.com
- [ ] Guardian 1 Phone: (613) 555-0201
- [ ] Guardian 1 Address: 456 Oak Ave, Ottawa, ON K1B 1B1
- [ ] Guardian 1 Pays: 60%
- [ ] Check "Add second guardian"
- [ ] Guardian 2 Name: `Michael Baker`
- [ ] Guardian 2 Email: michael.baker@example.com
- [ ] Guardian 2 Phone: (613) 555-0202
- [ ] Guardian 2 Address: 789 Pine St, Ottawa, ON K1C 2C2
- [ ] Guardian 2 Pays: 40%
- [ ] Save

**Verify:**
- [ ] "Minor" badge appears on client
- [ ] Guardian info displays in profile
- [ ] Percentages add to 100%

### 2.3 Couples Therapy - Carol & David Chen (10 min)

**Create both clients:**
- [ ] Add Client: `Carol Chen`, Type: Active, complete basic profile (no fee override needed)
- [ ] Add Client: `David Chen`, Type: Active, complete basic profile (no fee override needed)

**Create Link Group:**
- [ ] Go to Main View → Manage Links
- [ ] Click "Add Link Group"
- [ ] Select Carol Chen and David Chen
- [ ] Format: Couples
- [ ] Duration: 75 minutes
- [ ] Set fees for each member:
  - Carol: Base $75, Tax 13%, Total $84.75
  - David: Base $75, Tax 13%, Total $84.75
- [ ] Save

**Verify:**
- [ ] Link group appears in Manage Links
- [ ] Both clients show link indicator in Main View
- [ ] Both clients show "Linked Files" section in their client file

### 2.4 Low Fee Client - Emma Evans (3 min)

- [ ] Add Client: `Emma Evans`, Type: Low Fee
- [ ] Complete basic profile

**Set Fee Override:**
- [ ] Base: $80.00, Tax: 0%, Total: $80.00
- [ ] Duration: 50 minutes
- [ ] Save

### 2.5 Pro Bono Client - Frank Foster (3 min)

- [ ] Add Client: `Frank Foster`, Type: Pro Bono
- [ ] Complete basic profile

**Set Fee Override:**
- [ ] Base: $0, Tax: 0%, Total: $0
- [ ] Duration: 50 minutes
- [ ] Save

### 2.6 Family Therapy Setup (10 min)

**Create clients:**
- [ ] Add Client: `Grace Green`, Type: Active, complete basic profile
- [ ] Add Client: `Henry Green`, Type: Active

**Henry is a minor with two guardians:**
- [ ] Edit Henry's Profile
- [ ] DOB: 2009-08-10 (15 years old)
- [ ] Check "Client is a minor"
- [ ] Guardian 1: Grace Green (mother), 70%
  - Same address as Grace's profile
- [ ] Guardian 2: Robert Green (father), 30%
  - Different address: 321 Elm St, Ottawa, ON K1D 3D3
- [ ] Save

**Create Family Link Group:**
- [ ] Manage Links → Add Link Group
- [ ] Select Grace and Henry
- [ ] Format: Family
- [ ] Duration: 75 minutes
- [ ] Set fees:
  - Grace: Base $85, Tax 13%, Total $96.05
  - Henry: Base $85, Tax 13%, Total $96.05
- [ ] Save

---

## PHASE 3: ENTRY TYPES

### 3.1 Session Entries (15 min)

**Alice - Standard Session:**
- [ ] Open Alice's file → Add → Session
- [ ] Date: Today, Time: 10:00 AM
- [ ] Modality: In-Person
- [ ] Format: Individual
- [ ] Duration/Fee should come from profile
- [ ] Mood: Normal, Affect: Normal, Risk: None
- [ ] Notes: "Client discussed ongoing work stress. Explored coping strategies."
- [ ] Save
- [ ] Verify: Session #1 appears, entry is locked

**Alice - Second Session:**
- [ ] Add another session (different date)
- [ ] Verify: Session #2 (numbering works)

**Alice - Consultation:**
- [ ] Add Session, check "Consultation" checkbox
- [ ] Verify: Fee changes to consultation fee from Settings
- [ ] Save and verify it doesn't affect session numbering

**Bob - Session with Minor:**
- [ ] Add Session for Bob
- [ ] Verify: Fee comes from Bob's profile fee override
- [ ] Save

**Carol & David - Couples Session:**
- [ ] Open Carol's file → Add → Session
- [ ] Format dropdown: select "Couples"
- [ ] Verify: Fee/duration from link group
- [ ] "Link" toggle should be ON by default
- [ ] Save
- [ ] Verify: Entry appears in BOTH Carol and David's files

**Emma - Low Fee Session:**
- [ ] Add Session for Emma
- [ ] Verify: Fee is $80 (from her profile)

**Frank - Pro Bono Session:**
- [ ] Add Session for Frank
- [ ] Verify: Fee is $0 (from his profile)

**Test AI Scribe (if model downloaded):**
- [ ] Create new session or edit existing
- [ ] Click the purple feather button
- [ ] Type bullet points in the modal
- [ ] Test "Write Up" - converts to prose
- [ ] Test "Proofread" on the result
- [ ] Accept and verify text is inserted

### 3.2 Communication Entries (5 min)

**Alice - Email to client:**
- [ ] Add → Communication
- [ ] Recipient: To Client
- [ ] Type: Email
- [ ] Description: "Session confirmation"
- [ ] Content: "Hi Alice, confirming our appointment for Thursday at 2pm."
- [ ] Save

**Alice - Phone from client:**
- [ ] Add → Communication
- [ ] Recipient: From Client
- [ ] Type: Phone
- [ ] Description: "Reschedule request"
- [ ] Content: "Client called to reschedule Thursday's session to Friday."
- [ ] Save

**Alice - Internal Note:**
- [ ] Add → Communication
- [ ] Recipient: Internal Note
- [ ] Type: Administrative
- [ ] Description: "Insurance info"
- [ ] Content: "Client's insurance covers 80% of sessions."
- [ ] Save

**Verify:** All three show in timeline with correct icons

### 3.3 Absence Entries (5 min)

**Alice - Cancelled with fee:**
- [ ] Add → Absence
- [ ] Date/Time: Pick a date
- [ ] Fee: Use profile fee ($169.50)
- [ ] Description: "Late cancellation"
- [ ] Content: "Client cancelled less than 24 hours before session."
- [ ] Save

**Emma - Cancelled without fee:**
- [ ] Add → Absence for Emma
- [ ] Fee: $0.00
- [ ] Description: "Excused absence"
- [ ] Content: "Family emergency, waived cancellation fee."
- [ ] Save

### 3.4 Item Entries (5 min)

**Alice - Book purchase:**
- [ ] Add → Item
- [ ] Description: "Anxiety workbook"
- [ ] Base Price: $25.00
- [ ] Tax Rate: 13%
- [ ] Verify Total calculates: $28.25
- [ ] Save

**Alice - Letter/Report:**
- [ ] Add → Item
- [ ] Description: "Letter to employer"
- [ ] Base Price: $50.00
- [ ] Tax Rate: 0%
- [ ] Save

### 3.5 Upload Entries (5 min)

**Alice - Upload intake form:**
- [ ] Add → Upload
- [ ] Description: "Signed intake form"
- [ ] Upload a test PDF
- [ ] Save
- [ ] Verify: Can view/download the attachment

**Alice - Add attachment to existing Communication:**
- [ ] Edit the "Insurance info" communication
- [ ] Upload a file
- [ ] Save
- [ ] Verify: Attachment appears in entry

---

## PHASE 4: STATEMENTS & BILLING

### 4.1 Generate Statements (15 min)

**Generate for Alice:**
- [ ] Go to Billing → Outstanding Statements
- [ ] Click "Generate Statements"
- [ ] Select date range covering Alice's billable entries
- [ ] Generate
- [ ] Verify: Statement created for Alice showing:
  - 2 Sessions
  - 1 Absence (with fee)
  - 2 Items
  - Correct total

**Generate for Bob (guardian billing):**
- [ ] Generate statement for Bob
- [ ] Verify: TWO portions created (one per guardian)
- [ ] Patricia's portion: 60% of total
- [ ] Michael's portion: 40% of total

**Generate for Couples:**
- [ ] Generate statement covering the couples session
- [ ] Verify: Separate statements for Carol and David (each their portion)

**Verify Pro Bono:**
- [ ] Frank should have NO statement generated (all $0 entries)

### 4.2 Send Statements (10 min)

**Test PDF viewing:**
- [ ] Click "View PDF" on Alice's statement
- [ ] Verify: PDF opens with correct logo, signature, amounts

**Test Mark Sent:**
- [ ] Click "Mark Sent" on Alice's statement
- [ ] Verify: Status changes to "Sent"
- [ ] Verify: Communication entry created in Alice's file with PDF attached

**Test Email (mailto):**
- [ ] On Bob's Guardian 1 portion, click email button
- [ ] Verify: Email client opens with correct recipient, subject, body

**Test Email (AppleScript if configured):**
- [ ] Try sending via AppleScript
- [ ] Verify: Mail.app opens with PDF attached

### 4.3 Record Payments (10 min)

**Full payment:**
- [ ] On Alice's statement, click "Record Payment"
- [ ] Enter full amount
- [ ] Confirm
- [ ] Verify: Status changes to "Paid"
- [ ] Verify: Income entry auto-created in Ledger

**Partial payment:**
- [ ] On Bob's Guardian 1 portion, record partial payment
- [ ] Verify: Status shows "Partial"
- [ ] Verify: Shows amount remaining

**Write-off:**
- [ ] On Bob's Guardian 2 portion (if unpaid), click "Write Off"
- [ ] Confirm
- [ ] Verify: Status changes to "Written Off"

---

## PHASE 5: LEDGER & FINANCIAL REPORTS

### 5.1 Income Entries (5 min)

**Verify auto-generated income:**
- [ ] Go to Ledger
- [ ] Verify: Income from Alice's payment appears
- [ ] Source shows Alice's file number

**Manual income entry:**
- [ ] Add → Income
- [ ] Date: Today
- [ ] Source: "Insurance reimbursement"
- [ ] Base: $100, Tax: 0%, Total: $100
- [ ] Description: "Blue Cross claim #12345"
- [ ] Save

### 5.2 Expense Entries (10 min)

**Create expense with new category:**
- [ ] Add → Expense
- [ ] Date: Today
- [ ] Category: Type "Office Supplies" (new category)
- [ ] Payee: Type "Staples" (new payee)
- [ ] Base: $45.00, Tax: 13%, Total: $50.85
- [ ] Description: "Printer paper and pens"
- [ ] Upload a receipt (any PDF)
- [ ] Save

**Create expense with existing category:**
- [ ] Add → Expense
- [ ] Category: Select "Office Supplies" from dropdown
- [ ] Payee: Type "Amazon"
- [ ] Fill in amounts
- [ ] Save

**Create different category:**
- [ ] Add → Expense
- [ ] Category: "Professional Development"
- [ ] Payee: "CRPO"
- [ ] Description: "Annual registration fee"
- [ ] Save

**Test autocomplete:**
- [ ] Add new expense
- [ ] Start typing "Stap..." in Payee field
- [ ] Verify: "Staples" appears in suggestions

**Test removing suggestion:**
- [ ] Click X next to a suggested payee
- [ ] Verify: Removed from suggestions
- [ ] Add expense with that payee again
- [ ] Verify: Payee is back in suggestions

### 5.3 Financial Report (5 min)

- [ ] Go to Ledger → Generate Report
- [ ] Select date range covering all your test entries
- [ ] Click Calculate
- [ ] Verify: Shows income by source, expenses by category, totals
- [ ] Click Generate PDF
- [ ] Verify: PDF generated with correct data

---

## PHASE 6: CALENDAR & SCHEDULING

### 6.1 Schedule Appointment (5 min)

**Test .ics download:**
- [ ] Go to Alice's file
- [ ] Click Schedule button
- [ ] Fill in: Date, Time, Duration
- [ ] Add a video link (optional)
- [ ] Select repeat pattern (optional)
- [ ] Click Create Event
- [ ] Verify: .ics file downloads
- [ ] Open .ics file, verify it has correct details

**Test AppleScript (if configured):**
- [ ] Schedule another appointment
- [ ] Verify: Event added directly to Calendar app
- [ ] Check Calendar app to confirm

### 6.2 Natural Language Parsing (2 min)

- [ ] In the Schedule form, try typing in the date field:
  - "Friday 2pm" → should parse
  - "next Monday" → should parse
  - "tomorrow" → should parse

---

## PHASE 7: EXPORTS & REPORTS

### 7.1 Session Summary Report (5 min)

- [ ] Go to Alice's file
- [ ] Add → Session Summary Report
- [ ] Select date range
- [ ] Check "Include fees"
- [ ] Generate
- [ ] Verify: PDF shows all sessions with fees

- [ ] Generate again WITHOUT fees checked
- [ ] Verify: PDF shows sessions but no fee column

### 7.2 Export Entries (5 min)

**Export to PDF:**
- [ ] Go to Alice's file → Export
- [ ] Select several entries
- [ ] Export as PDF
- [ ] Verify: PDF contains selected entries

**Export to Markdown:**
- [ ] Export same entries as Markdown
- [ ] Verify: .md file downloads
- [ ] Open and verify content

---

## PHASE 8: BACKUP & RESTORE

### 8.1 Create Backups (5 min)

- [ ] Go to Backups page
- [ ] Click "Backup Now"
- [ ] Verify: Full backup created (first backup is always full)
- [ ] Make a small change (edit a client's profile)
- [ ] Click "Backup Now" again
- [ ] Verify: Incremental backup created

### 8.2 Verify Backup Contents (2 min)

- [ ] Check backup list shows both backups
- [ ] Verify: Full backup shows larger size
- [ ] Verify: Incremental shows smaller size
- [ ] Verify: Timestamps are correct

### 8.3 Test Restore (5 min)

⚠️ **Warning:** This will replace your current database

- [ ] Note current state of data
- [ ] Select the full backup
- [ ] Click Restore
- [ ] Confirm the warning
- [ ] App will restart
- [ ] Login again
- [ ] Verify: Data restored to that point

### 8.4 Delete Old Backups (2 min)

- [ ] Create a new full backup (so you have two chains)
- [ ] Try to delete the older full backup
- [ ] Verify: Cascade warning appears (will delete its incrementals)
- [ ] Confirm deletion
- [ ] Verify: Old chain removed

---

## PHASE 9: EDGE CASES & ERROR HANDLING

### 9.1 Validation Tests (5 min)

- [ ] Try creating client with empty name → Should fail
- [ ] Try guardian percentages that don't equal 100% → Should fail
- [ ] Try uploading non-image as logo → Should fail

### 9.2 Edit Locked Entries (3 min)

- [ ] Open a locked session entry (click to view, then Edit)
- [ ] Make an edit to the notes
- [ ] Save
- [ ] Verify: Edit history shows the change with diff

### 9.3 Delete Protection (3 min)

- [ ] Try to delete a client type that has clients assigned
- [ ] Verify: Error message, deletion prevented
- [ ] Try to delete Active or Inactive type
- [ ] Verify: Not possible (system locked)

### 9.4 Link Group Edge Cases (5 min)

- [ ] Try creating link group with only 1 member → Should fail
- [ ] Edit a link group, try to remove all but 1 member → Should fail
- [ ] Change a linked client's type to Inactive
- [ ] Verify: Client removed from link group automatically

---

## PHASE 10: CLEANUP & FINAL CHECKS

### 10.1 Main View Verification (3 min)

- [ ] All clients display with correct type colors
- [ ] Payment status indicators show correctly (green/yellow/red dots)
- [ ] Filter by type works
- [ ] Sort options work
- [ ] Search finds clients by name
- [ ] Detailed/Compact toggle works without page reload

### 10.2 Info Cards (2 min)

- [ ] Main View info cards show reasonable counts:
  - Active Clients
  - Sessions This Week
  - Pending Invoices
  - Billable This Month

### 10.3 Session Timeout (2 min)

- [ ] Check Settings → Security → timeout setting
- [ ] Optionally: Set to 15 min and wait
- [ ] Verify: Redirected to login with timeout message

### 10.4 Password Change (2 min)

- [ ] Settings → Security → Change Password
- [ ] Enter current password
- [ ] Enter new password (then change back if desired)
- [ ] Verify: Works correctly

---

## TESTING CHECKLIST SUMMARY

### Client Types
- [ ] Create custom types
- [ ] Edit types
- [ ] Type deletion rules enforced

### Clients
- [ ] Create clients (all types)
- [ ] Profile with all fields
- [ ] Fee override in profile
- [ ] Minor with guardian billing
- [ ] Default duration

### Link Groups
- [ ] Couples therapy link
- [ ] Family therapy link
- [ ] Fee allocation per member
- [ ] Linked entries sync to both files

### Entries
- [ ] Session (all variations)
- [ ] Communication (all recipient types)
- [ ] Absence (with/without fee)
- [ ] Item (with tax calculation)
- [ ] Upload (attachments)
- [ ] Edit history works on locked entries

### AI Scribe
- [ ] Write Up
- [ ] Proofread
- [ ] Expand
- [ ] Contract

### Statements
- [ ] Generate statements
- [ ] Guardian split billing (60/40)
- [ ] View PDF
- [ ] Mark Sent (creates Communication)
- [ ] Email (both methods)
- [ ] Record Payment (creates Income)
- [ ] Partial payment
- [ ] Write-off

### Ledger
- [ ] Auto income from payments
- [ ] Manual income
- [ ] Expenses with categories
- [ ] Expenses with receipts
- [ ] Autocomplete for payees/categories
- [ ] Financial report PDF

### Calendar
- [ ] .ics download
- [ ] AppleScript (Mac)
- [ ] Natural language parsing

### Exports
- [ ] Session summary PDF (with/without fees)
- [ ] Entry export PDF
- [ ] Entry export Markdown

### Backups
- [ ] Full backup
- [ ] Incremental backup
- [ ] Restore
- [ ] Delete old chains

### Settings
- [ ] All sections save correctly
- [ ] Calendar settings flow (single notification)
- [ ] Session timeout works
- [ ] Password change works

---

## ISSUES FOUND

| # | Description | Severity | Status |
|---|-------------|----------|--------|
| 1 | | | |
| 2 | | | |
| 3 | | | |

---

*Testing Guide for EdgeCase Equalizer v1.0*  
*Created: December 7, 2025*
