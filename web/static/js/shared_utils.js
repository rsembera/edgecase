/**
 * EdgeCase Shared Frontend Utilities
 *
 * Loaded globally via base.html BEFORE page-specific scripts.
 * Consolidates helpers that were previously copy-pasted across files
 * (see CODE_REVIEW.md L10). Plain script (no modules) — functions are
 * global, matching the rest of the frontend.
 */

// ============================================================
// HTML ESCAPING
// ============================================================

/**
 * Escape a string for safe interpolation into innerHTML.
 * @param {string} text - Untrusted text
 * @returns {string} HTML-escaped text ('' for null/undefined/empty)
 */
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ============================================================
// DOUBLE-SUBMIT PROTECTION
// ============================================================

/**
 * Resolve the button that triggered the currently-dispatching event.
 * Works inside functions invoked from inline onclick="..." handlers
 * without changing the template markup.
 * @returns {HTMLButtonElement|null}
 */
function resolveEventButton() {
    const evt = window.event;
    if (evt && evt.target && typeof evt.target.closest === 'function') {
        return evt.target.closest('button');
    }
    return null;
}

/**
 * Disable a button while an async operation is pending, then restore it.
 * Mirrors the disable + spinner + restore pattern used by backups.js /
 * settings.js (see CODE_REVIEW.md L6 — double-submit protection).
 *
 * @param {HTMLButtonElement|null} btn - Trigger button (null-safe: just runs fn)
 * @param {Function} asyncFn - Function returning a Promise (the fetch chain)
 * @param {string} [pendingText] - Optional label shown with a spinner while
 *     pending; omit for icon-only buttons (they are just disabled).
 * @returns {Promise} Resolves with asyncFn's result
 */
async function withButtonDisabled(btn, asyncFn, pendingText) {
    if (!btn) return asyncFn();
    if (btn.disabled) return; // Already pending — swallow duplicate click
    const originalHtml = btn.innerHTML;
    btn.disabled = true;
    if (pendingText) {
        btn.innerHTML = '<i data-lucide="loader" class="icon-sm icon-inline btn-spinner"></i> '
            + escapeHtml(pendingText);
        if (typeof lucide !== 'undefined') lucide.createIcons();
    }
    try {
        return await asyncFn();
    } finally {
        btn.disabled = false;
        btn.innerHTML = originalHtml;
        if (pendingText && typeof lucide !== 'undefined') lucide.createIcons();
    }
}

// ============================================================
// TEXTAREA AUTO-RESIZE
// ============================================================

/**
 * Auto-resize a textarea to fit its content up to maxHeight,
 * showing a scrollbar beyond that.
 * @param {HTMLTextAreaElement} textarea - The textarea to resize
 * @param {number} [maxHeight=600] - Maximum height in pixels
 */
function autoResizeTextarea(textarea, maxHeight = 600) {
    if (!textarea) return;
    // Reset height to auto to get the correct scrollHeight
    textarea.style.height = 'auto';
    const newHeight = Math.min(textarea.scrollHeight, maxHeight);
    textarea.style.height = newHeight + 'px';
    textarea.style.overflowY = textarea.scrollHeight > maxHeight ? 'scroll' : 'hidden';
}

// ============================================================
// THREE-WAY FEE CALCULATION
// ============================================================

/**
 * Three-way fee calculation: editing base or tax recomputes the total;
 * editing the total back-computes the base.
 * @param {HTMLInputElement} baseInput - Base fee input
 * @param {HTMLInputElement} taxInput - Tax rate (%) input
 * @param {HTMLInputElement} totalInput - Total fee input
 * @param {string} changedField - Which field was changed: 'base', 'tax', or 'total'
 * @returns {number|null} The resulting total, or null if changedField was unrecognized
 */
function calculateThreeWayFee(baseInput, taxInput, totalInput, changedField) {
    const base = parseFloat(baseInput.value) || 0;
    const taxRate = parseFloat(taxInput.value) || 0;
    const total = parseFloat(totalInput.value) || 0;

    if (changedField === 'base' || changedField === 'tax') {
        const calculatedTotal = base * (1 + taxRate / 100);
        totalInput.value = calculatedTotal.toFixed(2);
        return calculatedTotal;
    } else if (changedField === 'total') {
        const calculatedBase = taxRate > 0 ? total / (1 + taxRate / 100) : total;
        baseInput.value = calculatedBase.toFixed(2);
        return total;
    }
    return null;
}

// ============================================================
// COLOR PALETTE (client type badges and cards)
// ============================================================

const COLOR_PALETTE = {
    green:  { name: 'Green',  bg: '#D1F0E8', badge: '#00AA88', text: '#1F2937' },
    blue:   { name: 'Blue',   bg: '#DBEAFE', badge: '#3B82F6', text: '#1F2937' },
    purple: { name: 'Purple', bg: '#E9D5FF', badge: '#A855F7', text: '#1F2937' },
    pink:   { name: 'Pink',   bg: '#FCE7F3', badge: '#EC4899', text: '#1F2937' },
    yellow: { name: 'Yellow', bg: '#FEF3C7', badge: '#F59E0B', text: '#1F2937' },
    orange: { name: 'Orange', bg: '#FFEDD5', badge: '#F97316', text: '#1F2937' },
    teal:   { name: 'Teal',   bg: '#CCFBF1', badge: '#14B8A6', text: '#1F2937' },
    gray:   { name: 'Gray',   bg: '#F3F4F6', badge: '#6B7280', text: '#1F2937' }
};

/**
 * Get color scheme for a given color key
 * @param {string} colorKey - Key from COLOR_PALETTE
 * @returns {Object} Color scheme with bg, badge, and text colors
 */
function getColors(colorKey) {
    return COLOR_PALETTE[colorKey] || COLOR_PALETTE.green;
}


// ============================================================================
// In-app dialogs
//
// EdgeCase does not use the browser's showMessage()/confirm(): they look foreign,
// block the page, and behave differently in the desktop shell. These two
// build a modal in the app's own style on demand, so any page that loads
// this file can use them without carrying markup. Text goes in through
// textContent, never innerHTML. tests/test_no_browser_dialogs.py keeps the
// browser versions from coming back.
// ============================================================================

function _appDialog(message, title, buttons) {
    return new Promise(function (resolve) {
        const overlay = document.createElement('div');
        overlay.className = 'modal active app-dialog';
        overlay.setAttribute('role', 'dialog');
        overlay.setAttribute('aria-modal', 'true');

        const box = document.createElement('div');
        box.className = 'modal-content unsaved-changes-modal-content';

        if (title) {
            const heading = document.createElement('h3');
            heading.textContent = title;
            box.appendChild(heading);
        }

        const text = document.createElement('p');
        text.style.whiteSpace = 'pre-line';
        text.textContent = message;
        box.appendChild(text);

        const actions = document.createElement('div');
        actions.className = 'unsaved-changes-modal-actions';

        function close(value) {
            document.removeEventListener('keydown', onKey, true);
            overlay.remove();
            resolve(value);
        }
        function onKey(event) {
            if (event.key === 'Escape') {
                event.preventDefault();
                close(buttons[0].value);
            }
        }

        buttons.forEach(function (spec) {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = spec.primary ? 'btn' : 'btn btn-secondary';
            button.textContent = spec.label;
            button.addEventListener('click', function () { close(spec.value); });
            actions.appendChild(button);
            if (spec.primary) setTimeout(function () { button.focus(); }, 0);
        });

        box.appendChild(actions);
        overlay.appendChild(box);
        document.addEventListener('keydown', onKey, true);
        document.body.appendChild(overlay);
    });
}

/**
 * Show a message with an OK button. Returns a Promise that resolves when
 * it is dismissed — chain on it for anything that must wait (a redirect).
 */
function showMessage(message, title) {
    return _appDialog(String(message), title || '',
                      [{ label: 'OK', value: undefined, primary: true }]);
}

/**
 * Ask a yes/no question. Resolves true if confirmed, false otherwise
 * (Cancel, or Escape).
 */
function confirmDialog(message, options) {
    options = options || {};
    return _appDialog(String(message), options.title || '', [
        { label: options.cancelLabel || 'Cancel', value: false },
        { label: options.confirmLabel || 'OK', value: true, primary: true },
    ]);
}

/**
 * For <form onsubmit="return confirmSubmit(this, '...')">: holds the
 * submission until the question is answered.
 */
function confirmSubmit(form, message, options) {
    confirmDialog(message, options).then(function (ok) {
        if (ok) form.submit();   // submit() does not re-fire onsubmit
    });
    return false;
}
