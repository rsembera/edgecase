# EdgeCase Equalizer - Pre-Open-Source Code Review

**Review Date:** January 31, 2026
**Reviewer:** Claude (Automated Code Analysis)
**Project:** Practice management software for independent therapists
**Files Analyzed:** ~60 Python files, ~27 JavaScript files, templates, tests

---

## Executive Summary

EdgeCase Equalizer is a well-structured Flask application with meaningful test coverage for core business logic. The code is functional and clearly written by someone who understands the problem domain. However, there are several issues that critical open-source reviewers will likely flag—most notably some security concerns that should be addressed before public release.

### Overall Assessment: **B-** (Good foundation, needs polish)

| Category | Grade | Summary |
|----------|-------|---------|
| **Architecture** | B+ | Clean separation, good use of blueprints |
| **Security** | C+ | Some concerning patterns need fixing |
| **Code Quality** | B- | Functional but inconsistent, some duplication |
| **Test Coverage** | B | Core logic tested, critical modules untested |
| **Documentation** | C+ | README good, inline docs sparse |
| **Dead Code** | C | Multiple unused functions and duplicate imports |

---

## Critical Issues (Fix Before Monday)

### 1. SQL Injection Risk in Dynamic Column Names

**Location:** `core/database.py` (lines 598-615, 869-882, 1322-1326)

```python
# VULNERABLE PATTERN
for key, value in client_data.items():
    if key != 'id':
        set_clauses.append(f"{key} = ?")  # Column name NOT validated
        values.append(value)

cursor.execute(f"""
    UPDATE clients
    SET {', '.join(set_clauses)}
    WHERE id = ?
""", values)
```

**Problem:** While values are parameterized, column names are injected directly. An attacker controlling `client_data` keys could inject SQL.

**Fix:** Validate against a whitelist of allowed column names.

---

### 2. Weak Password Verification in Auth Blueprint

**Location:** `web/blueprints/auth.py` (lines 251-255)

```python
try:
    conn = db.connect()
    conn.execute("SELECT 1")  # Just tests if connection works!
except Exception as e:
    return render_template('change_password.html', error="Current password is incorrect")
```

**Problem:** This doesn't verify the password—it just checks if the database connection works. Password changes could potentially bypass verification.

---

### 3. Passwords Stored in Session Temporarily

**Location:** `web/blueprints/auth.py` (lines 259-261)

```python
session['password_change_current'] = current_password
session['password_change_new'] = new_password
```

**Problem:** Storing passwords (even temporarily) in Flask session is a security anti-pattern. Use a dedicated temporary store with short TTL.

---

### 4. XSS Vulnerabilities in JavaScript

**Locations:** Multiple JS files using innerHTML with unsanitized data

- `backups.js` (lines 314-322, 335-342): Template literals rendered via innerHTML
- `outstanding_statements.js` (lines 268-275): Client names in checkboxes
- `add_edit_link_group.js` (lines 140-148): Search results display

**Problem:** `escapeHtml()` exists in `main_view.js` but isn't used consistently.

---

## High Priority Issues

### 5. Bare Except Clauses Throughout PDF Generation

**Location:** `pdf/client_export.py`, `pdf/generator.py` (12+ instances)

```python
try:
    paragraphs.append(Paragraph(part, styles['ContentText']))
except:  # Bare except!
    plain = re.sub(r'<[^>]+>', '', part)
```

**Problem:** Bare excepts mask real errors and make debugging difficult. Replace with specific exception types.

---

### 6. Missing Input Validation on Form Data

**Location:** `web/blueprints/entries.py` (lines 109-112)

```python
'session_base': float(request.form.get('session_base')) if request.form.get('session_base') else None,
```

**Problem:** No try/except for type conversions. User enters "abc" → ValueError crashes the route.

---

### 7. Backup System Completely Untested

**Location:** `utils/backup.py` (1,072 lines)

**Problem:** Critical data recovery functionality with ZERO test coverage. Functions include:
- `create_backup()`, `restore_backup()`, `verify_backup()`
- `cleanup_old_backups()`, `complete_restore()`

This is a significant risk for a system handling sensitive therapy records.

---

### 8. N+1 Query Performance Issues

**Location:** `core/database.py` (lines 1034-1047), `web/blueprints/clients.py` (lines 154-156)

```python
for row in cursor.fetchall():  # First query
    cursor.execute("SELECT * FROM clients WHERE id = ?", (client_id,))  # Query per row!
```

**Problem:** For groups with 10 members, this executes 11 queries instead of 1 JOIN.

---

## Medium Priority Issues

### 9. Dead Code

| File | Function | Lines |
|------|----------|-------|
| `web/utils.py` | `safe_float()` | 18-25 |
| `web/utils.py` | `safe_int()` | 28-35 |
| `web/utils.py` | `delete_attachment_files()` | 279-304 |
| `ai/ai_scribe.js` | `getClientId()` | 253-260 |

### 10. Duplicate Code

- **Currency symbol function:** Defined identically in 3 files (`generator.py`, `client_export.py`, `ledger_report.py`)
- **COLOR_PALETTE:** Defined in both `color_palette.js` and `main_view.js`
- **Fee retrieval pattern:** Repeated 4+ times in `entries.py`
- **Autocomplete function:** Nearly identical in `expense.js` and `income.js`

### 11. Duplicate/Unnecessary Imports

**Location:** `core/database.py`

```python
import time  # Line 9 (module level)
import time  # Line 737 (inside function)
import time  # Line 761 (inside function)
# ...repeated 5+ more times
```

### 12. Global Mutable State

```python
# Multiple blueprints use this pattern:
db = None

def init_blueprint(database):
    global db
    db = database
```

**Problem:** Makes testing difficult and is not thread-safe.

### 13. Inconsistent Error Handling

- Some routes return JSON errors, others return HTML
- Mix of `print()` statements and no logging
- Silent failures in exception handlers

---

## What Reviewers Will Like ✓

1. **Meaningful test coverage:** 43 tests covering billing calculations, session numbering, payment status, guardian splits, date parsing edge cases

2. **Clean blueprint organization:** Logical separation by feature (auth, clients, entries, ledger, statements)

3. **Security-conscious features:** SQLCipher encryption, file path traversal protection in some places, CSRF setup

4. **Domain expertise evident:** Code shows understanding of therapy practice needs (guardian billing, couples therapy, compliance requirements)

5. **Reasonable dependencies:** Modern, well-maintained packages (Flask 3.1, SQLCipher, ReportLab)

6. **Cross-platform consideration:** Installation docs for macOS, Linux, Windows

---

## What Reviewers Will Question ❓

1. **Why is the 1,000+ line backup system untested?**
2. **Why are there 3 copies of the currency symbol function?**
3. **Why use bare excepts when you clearly know better elsewhere?**
4. **Why store passwords in session during password change?**
5. **Why no type hints on most functions?**
6. **Why does pyproject.toml say "Beta" but README says "Production ready"?**

---

## Quick Wins (Low Effort, High Impact)

1. **Add whitelist validation** for dynamic column names in UPDATE queries
2. **Remove the 3 dead utility functions** or add tests
3. **Extract currency symbol function** to shared utility
4. **Add `.catch()` to fire-and-forget fetches** in JavaScript
5. **Replace bare excepts** with specific exception types + logging
6. **Add try/except** around form float/int conversions

---

## Test Coverage Gaps

| Module | Lines | Tests | Status |
|--------|-------|-------|--------|
| `utils/backup.py` | 1,072 | 0 | ❌ Critical |
| `web/cli.py` | 235 | 0 | ❌ Important |
| `web/app.py` (startup) | 377 | 0 | ⚠️ Medium |
| `core/encryption.py` (files) | ~100 | 2 (DB only) | ⚠️ Medium |
| `core/database.py` | 2,000+ | 43 | ✓ Core tested |
| `web/blueprints/*` | ~3,000 | 0 | ⚠️ Integration |

---

## Recommended Priority Order

### Before Open Source (This Weekend)

1. Fix SQL injection in dynamic column names
2. Fix password verification logic in auth
3. Remove passwords from session storage
4. Add basic input validation on float/int conversions
5. Remove dead code functions

### First Week After Launch

1. Add backup system tests (critical data recovery)
2. Extract duplicate code to shared utilities
3. Replace bare excepts with specific types
4. Consistent XSS protection in JavaScript

### First Month

1. Add type hints throughout
2. CLI and integration tests
3. Refactor global db pattern to Flask app context
4. Performance optimization for N+1 queries

---

## Conclusion

EdgeCase Equalizer is solid working software with a clear purpose and domain understanding. The security issues are fixable, and the code quality issues are mostly about consistency rather than fundamental problems.

**For a solo developer project, this is above average.** Most open-source reviewers will appreciate the meaningful tests and clean architecture, even while pointing out the issues listed above.

The biggest risks are:
1. The untested backup system (if someone's data gets corrupted during restore, that's very bad)
2. The security patterns in password handling
3. The SQL injection surface in dynamic queries

Fix those three, and you'll be in good shape for Monday.
