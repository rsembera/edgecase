// ---------------------------------------------------------------------------
// form-guard.js — shared dirty-state Save button for entry EDIT forms.
//
// Opt-in: <form data-dirty-guard>. The save button is [data-dirty-save],
// found inside the form or (comm/upload, whose action buttons sit outside
// the form) anywhere in the document with form="<form id>". The button's
// active label lives in data-dirty-label ("Save Edits", "Save Absence", …);
// while the form matches its load-time state it is disabled and reads
// "No Changes" — the same behaviour the session form has had in locked
// mode since 2026-06.
//
// This is deliberately the save-button SUBSET of session.js's dirty block:
// no beforeunload guard and no leave-confirmation modal (session keeps its
// own bespoke version of those; see session.js for their misfire history).
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
//   serialization explicitly — otherwise attaching a file to a locked
//   communication/item/upload would never enable Save.
// ---------------------------------------------------------------------------
document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('form[data-dirty-guard]').forEach(function(form) {
        const saveBtn =
            form.querySelector('[data-dirty-save]') ||
            (form.id
                ? document.querySelector('[data-dirty-save][form="' + form.id + '"]')
                : null);
        if (!saveBtn) return;

        const activeLabel = saveBtn.getAttribute('data-dirty-label') || 'Save Changes';

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
    });
});
