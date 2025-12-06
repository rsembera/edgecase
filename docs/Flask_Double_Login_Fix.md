# Flask Double-Login Issue on Safari/Firefox

**Problem Discovered:** December 5, 2025  
**Project:** EdgeCase Equalizer  
**Commit:** 1566279

---

## The Problem

After entering correct credentials and clicking Login:
1. POST to /login succeeds
2. Redirect to main view (/)
3. Immediately redirected back to /login?timeout=1

User has to log in twice. Works fine in Chrome, fails in Safari and Firefox.

---

## Root Cause

**Race condition with session cookies.**

The `before_request` handler was checking `session.get('last_activity')` to enforce session timeout. But `last_activity` wasn't being set during login - only in `before_request` itself.

Timeline of what went wrong:

1. User POSTs credentials to /login
2. Login route sets `session['logged_in'] = True` and redirects
3. Browser receives redirect, but cookie not fully persisted yet
4. Browser requests main view (/)
5. `before_request` runs, checks for `last_activity`
6. Stale/empty session data causes timeout check to fail
7. Redirect back to /login?timeout=1

Safari and Firefox are stricter about cookie timing than Chrome.

---

## The Fix

Four changes to ensure reliable session handling:

### 1. Clear stale session data before setting new values

**File:** `web/blueprints/auth.py` in `login()` route

```python
# Before setting new session values, clear any stale data
session.clear()

# Now set fresh session
session['logged_in'] = True
session['last_activity'] = time.time()  # Set immediately!
```

### 2. Set last_activity during login, not just in before_request

```python
# In login() route, after session.clear():
session['last_activity'] = time.time()
```

This ensures the session has `last_activity` before the first `before_request` runs.

### 3. Use a unique session cookie name

**File:** `web/app.py`

```python
app.config['SESSION_COOKIE_NAME'] = 'edgecase_session'
```

Avoids conflicts with other Flask apps running on localhost during development.

### 4. Use make_response for explicit cookie handling

**File:** `web/blueprints/auth.py`

```python
from flask import make_response

# Instead of: return redirect(url_for('clients.index'))
response = make_response(redirect(url_for('clients.index')))
return response
```

This ensures the response headers (including Set-Cookie) are properly constructed before sending.

---

## Complete Login Route Pattern

```python
from flask import session, redirect, url_for, make_response
import time

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password')
        
        # ... validate password ...
        
        if valid:
            # Clear any stale session data first
            session.clear()
            
            # Set fresh session with last_activity immediately
            session['logged_in'] = True
            session['last_activity'] = time.time()
            
            # Use make_response for explicit cookie handling
            response = make_response(redirect(url_for('main.index')))
            return response
        else:
            return render_template('login.html', error='Invalid password')
    
    return render_template('login.html')
```

---

## Before Request Handler

```python
@app.before_request
def check_session_timeout():
    # Skip for static files and login page
    if request.endpoint in ('static', 'auth.login', 'auth.logout'):
        return
    
    if not session.get('logged_in'):
        return redirect(url_for('auth.login'))
    
    # Check timeout
    last_activity = session.get('last_activity')
    if last_activity:
        timeout_minutes = get_timeout_setting()  # e.g., 30
        if timeout_minutes > 0:
            elapsed = time.time() - last_activity
            if elapsed > timeout_minutes * 60:
                session.clear()
                return redirect(url_for('auth.login', timeout=1))
    
    # Update last activity
    session['last_activity'] = time.time()
```

---

## Key Takeaways

1. **Always set `last_activity` during login** - Don't rely on `before_request` to set it on first run

2. **Use `session.clear()` before setting new session values** - Prevents stale data from previous sessions

3. **Use unique cookie names in development** - `SESSION_COOKIE_NAME = 'yourapp_session'`

4. **Safari/Firefox are stricter** - If it works in Chrome but not Safari, suspect cookie timing issues

5. **Test login flow in multiple browsers** - Cookie handling varies

---

## Symptoms Checklist

If you see these symptoms, this fix likely applies:

- [ ] Login works in Chrome but not Safari/Firefox
- [ ] User must log in twice
- [ ] Redirect includes `?timeout=1` parameter
- [ ] Problem is intermittent or timing-dependent
- [ ] Using Flask sessions with `before_request` timeout checking

---

*Reference document for future Flask projects*
