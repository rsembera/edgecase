// ---------------------------------------------------------------------------
// form-guard.js — shared dirty-form protection for entry forms.
//
// Opt-in: <form data-dirty-guard>. Provides, per guarded form:
//
// 1. Dirty-state Save button (EDIT mode; button marked [data-dirty-save],
//    inside the form or elsewhere with form="<form id>"): disabled and
//    labelled "No Changes" until the form differs from its load-time
//    state; the active label lives in data-dirty-label. Create forms have
//    no [data-dirty-save] button, so Save stays enabled — but the leave
//    protection below still applies (a half-typed new entry is the same
//    loss as an edit).
//
// 2. Unsaved-changes protection (ALL modes, mirroring session.js):
//    - beforeunload: tab close / reload / browser back asks first.
//      Disarmed on an un-prevented form submit and on the modal's
//      Leave Without Saving, so it never fires on a deliberate leave.
//    - In-page navigation (Cancel/Back, Prev/Next — any
//      .entry-form-actions / .profile-form-actions link): a custom modal
//      (components/unsaved_changes_modal.html) with the destination
//      remembered until the user decides. Only armed when the modal
//      elements exist in the page.
//
// Session pages keep their own bespoke version of all of this in
// session.js and do NOT use this script.
//
// Implementation notes carried over from session.js:
// - Snapshot-and-compare, not event counting: pickers.js writes input
//   values programmatically with NO input/change events, so we serialize
//   the form at load and re-compare on demand. Symmetric by construction
//   (edit + undo reads as clean).
// - pickers:ready re-baseline: async picker init writes values AFTER the
//   load snapshot; without a re-baseline the form is dirty from page load.
//   A real user edit before pickers finish wins and skips the re-baseline.
// - File inputs serialize as "[object File]" via URLSearchParams(FormData)
//   regardless of selection, so their filenames are appended to the
//   serialization explicitly.
// - CRITICAL PHASE NOTE (in-page guard): the base layout registers a
//   capture-phase click handler on document that intercepts same-origin
//   link clicks (server-liveness check), preventDefault()s them, and
//   navigates PROGRAMMATICALLY via window.location.href — so a
//   bubble-phase listener cannot stop those navigations. This guard
//   listens on WINDOW in the capture phase (which fires before document
//   capture) and stops propagation when it intervenes, so the liveness
//   handler never starts. Clean (non-dirty) clicks pass through
//   untouched.
// ---------------------------------------------------------------------------
document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('form[data-dirty-guard]').forEach(function(form) {
        const saveBtn =
            form.querySelector('[data-dirty-save]') ||
            (form.id
                ? document.querySelector('[data-dirty-save][form="' + form.id + '"]')
                : null);

        const activeLabel = saveBtn
            ? (saveBtn.getAttribute('data-dirty-label') || 'Save Changes')
            : null;

        const serialize = function() {
            const params = new URLSearchParams(new FormData(form)).toString();
            // Filenames of any file inputs (FormData renders File objects
            // as the useless constant "[object File]").
            const files = Array.from(form.querySelectorAll('input[type="file"]'))
                .map(function(input) { return input.value; })
                .join('|');
            return params + '\u0000' + files;
        };

        let baseline = serialize();
        const isDirty = function() { return serialize() !== baseline; };

        const refreshSaveButton = function() {
            if (!saveBtn) return;
            const dirty = isDirty();
            saveBtn.disabled = !dirty;
            saveBtn.textContent = dirty ? activeLabel : 'No Changes';
        };

        let userEdited = false;
        document.addEventListener('pickers:ready', function() {
            if (!userEdited) {
                baseline = serialize();
                refreshSaveButton();
            }
        });

        const markUserEdited = function() { userEdited = true; refreshSaveButton(); };
        form.addEventListener('input', markUserEdited);
        form.addEventListener('change', markUserEdited);
        // Picker writes dispatch no events; their click handlers run before
        // this document-level bubble listener, so a refresh here sees them.
        document.addEventListener('click', refreshSaveButton);

        refreshSaveButton();

        // --- Unsaved-changes protection (mirrors session.js) ---

        // Tab close / reload / browser back / address bar: the browser's
        // native warning — the only UI browsers permit at beforeunload.
        const onBeforeUnload = function(e) {
            if (isDirty()) {
                e.preventDefault();
                e.returnValue = '';  // some browsers require this for the dialog
            }
        };
        const disarmUnloadGuard = function() {
            window.removeEventListener('beforeunload', onBeforeUnload);
        };
        window.addEventListener('beforeunload', onBeforeUnload);
        form.addEventListener('submit', disarmUnloadGuard);

        // In-page navigation (Cancel/Back, Prev/Next): custom modal with
        // the destination remembered until the user decides. Armed only
        // when the page includes components/unsaved_changes_modal.html.
        const modal = document.getElementById('unsaved-changes-modal');
        const stayBtn = document.getElementById('unsaved-stay-btn');
        const leaveBtn = document.getElementById('unsaved-leave-btn');
        let pendingHref = null;

        if (modal && stayBtn && leaveBtn) {
            window.addEventListener('click', function(e) {
                const t = e.target;
                const link = t && t.closest
                    ? t.closest('.entry-form-actions a.btn, .profile-form-actions a.btn')
                    : null;
                if (!link || !isDirty()) return;
                e.preventDefault();
                e.stopPropagation();  // keeps the liveness handler from navigating
                pendingHref = link.href;
                modal.style.display = 'flex';
            }, true);

            stayBtn.addEventListener('click', function() {
                pendingHref = null;
                modal.style.display = 'none';
            });

            leaveBtn.addEventListener('click', function() {
                if (!pendingHref) return;
                disarmUnloadGuard();
                modal.style.display = 'none';
                window.location.assign(pendingHref);
            });
        }
    });
});
