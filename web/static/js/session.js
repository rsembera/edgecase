/**
 * Session Entry Form JavaScript - EdgeCase Equalizer
 * Handles session creation/editing including format-based fee calculation,
 * consultation/pro-bono toggles, and link group integration.
 */

// Read data from hidden elements
const sessionData = document.getElementById('session-data');
const isEdit = sessionData.dataset.isEdit === 'true';
const nextSessionNumber = sessionData.dataset.nextSessionNumber || '';

// Parse fee sources from JSON script tag
const feeSourcesScript = document.getElementById('fee-sources-data');
const feeSources = JSON.parse(feeSourcesScript.textContent);

// Make feeSources available globally
window.feeSources = feeSources;

// Format dropdown fee logic
const formatDropdown = document.getElementById('format');
const baseFeeInput = document.getElementById('base_fee');
const taxRateInput = document.getElementById('tax_rate');
const totalFeeInput = document.getElementById('fee');
const feeSourceSpan = document.getElementById('fee-source');

// Update fees when format changes
if (formatDropdown) {
    formatDropdown.addEventListener('change', function() {
        updateFeesForFormat(this.value);
    });
    
    // Initialize fees on page load (NEW SESSIONS ONLY)
    if (formatDropdown.value && !isEdit) {
        updateFeesForFormat(formatDropdown.value);
    }
}

/**
 * Update fee fields based on selected session format
 * @param {string} format - Session format: 'individual', 'couples', 'family', or 'group'
 */
function updateFeesForFormat(format) {
    // DON'T auto-update fees when editing existing sessions
    // User should see the fees that were saved, not auto-calculated values
    if (isEdit) {
        return;
    }
    
    // Don't update fees if consultation or pro bono is checked
    const consultationCheckbox = document.getElementById('is_consultation');
    const proBonoCheckbox = document.getElementById('is_pro_bono');
    
    if (consultationCheckbox && consultationCheckbox.checked) {
        return; // Exit early, keep consultation fees
    }
    
    if (proBonoCheckbox && proBonoCheckbox.checked) {
        return; // Exit early, keep pro bono fees (zero)
    }
    
    const feeSources = window.feeSources || {};
    let fees = null;
    let source = '';
    
    if (format === 'individual') {
        fees = feeSources.profileFees;
        source = 'Profile';
        
        // Also set duration from profile
        if (feeSources.profileFees.duration) {
            durationInput.value = feeSources.profileFees.duration;
        }

    } else if (format === 'couples' || format === 'family' || format === 'group') {
        // Couples/Family/Group: Check Link Group
        if (feeSources.linkGroups && feeSources.linkGroups[format]) {
            fees = feeSources.linkGroups[format];
            source = `Link Group (${format.charAt(0).toUpperCase() + format.slice(1)})`;
            
            // Also set duration from link group
            if (feeSources.linkGroups[format].duration) {
                durationInput.value = feeSources.linkGroups[format].duration;
            }
        } else {
            // No link group found - show modal
            const formatName = format.charAt(0).toUpperCase() + format.slice(1);
            const message = `This client is not in a ${formatName} link group. To bill ${format} sessions, you need to create a link group with the "${formatName}" format first.`;
            
            document.getElementById('missing-link-message').textContent = message;
            document.getElementById('missing-link-modal').style.display = 'flex';
            
            // Reset to individual (use Choices.js API)
            window.setChoicesValue('format', 'individual');
            updateFeesForFormat('individual');
            return;
        }
    }
    
    // Update fee fields
    if (fees) {
        baseFeeInput.value = parseFloat(fees.base || 0).toFixed(2);
        taxRateInput.value = parseFloat(fees.tax || 0).toFixed(2);
        totalFeeInput.value = parseFloat(fees.total || 0).toFixed(2);
        feeSourceSpan.textContent = `Source: ${source}`;
    }
}

/**
 * Three-way fee calculation when user manually edits fees
 * @param {string} changedField - Which field was changed: 'base', 'tax', or 'total'
 */
function calculateSessionFee(changedField) {
    calculateThreeWayFee(baseFeeInput, taxRateInput, totalFeeInput, changedField);
}

// Add listeners for manual fee editing
baseFeeInput.addEventListener('input', () => calculateSessionFee('base'));
taxRateInput.addEventListener('input', () => calculateSessionFee('tax'));
totalFeeInput.addEventListener('input', () => calculateSessionFee('total'));

// Date dropdowns → hidden field (same as profile.html)
const dateYear = document.getElementById('date_year');
const dateMonth = document.getElementById('date_month');
const dateDay = document.getElementById('date_day');
const dateHidden = document.getElementById('session_date');

/**
 * Update hidden session_date field from dropdown selections
 */
function updateSessionDate() {
    if (dateYear.value && dateMonth.value && dateDay.value) {
        dateHidden.value = `${dateYear.value}-${dateMonth.value}-${dateDay.value}`;
    } else {
        dateHidden.value = '';
    }
}

// Consultation checkbox logic with settings from database
const consultationCheckbox = document.getElementById('is_consultation');
// baseFeeInput, taxRateInput, totalFeeInput already declared above
const durationInput = document.getElementById('duration');
const sessionNumberDisplay = document.getElementById('session-number-display');

// Store original values (for unchecking)
const originalBaseFee = baseFeeInput.value;
const originalTaxRate = taxRateInput.value;
const originalTotalFee = totalFeeInput.value;
const originalDuration = durationInput.value;

// Fetch consultation settings from database
let consultationBase = '0.00';
let consultationTax = '0.00';
let consultationTotal = '0.00';
let consultationDuration = '20';
let settingsLoaded = false;

// Load settings immediately
fetch('/api/practice_info')
    .then(response => response.json())
    .then(data => {
        if (data.success && data.info) {
            consultationBase = data.info.consultation_base_price || '0.00';
            consultationTax = data.info.consultation_tax_rate || '0.00';
            consultationTotal = data.info.consultation_fee || '0.00';
            consultationDuration = data.info.consultation_duration || '20';
        }
        settingsLoaded = true;
        // Apply if checkbox already checked
        if (consultationCheckbox.checked) {
            baseFeeInput.value = consultationBase;
            taxRateInput.value = consultationTax;
            totalFeeInput.value = consultationTotal;
            durationInput.value = consultationDuration;
        }
    })
    .catch(error => console.error('Failed to load consultation settings:', error));

consultationCheckbox.addEventListener('change', function() {
    // Get values from data attributes
    const isEdit = document.body.dataset.isEdit === 'true';
    const nextSessionNumber = document.body.dataset.nextSessionNumber || '';
    const serviceInput = document.getElementById('service');
    
    if (this.checked) {
        // Consultation: use settings from database (all three fee fields)
        baseFeeInput.value = consultationBase;
        taxRateInput.value = consultationTax;
        totalFeeInput.value = consultationTotal;
        durationInput.value = consultationDuration;
        
        // Auto-populate service field with "Consultation"
        if (serviceInput) {
            serviceInput.value = 'Consultation';
        }
        
        if (!isEdit) {
            sessionNumberDisplay.textContent = 'Consultation';
        }
    } else {
        // Regular session: check if format is selected
        const currentFormat = formatDropdown.value;
        
        if (currentFormat && currentFormat !== '') {
            // Format selected: apply fees and duration for that format
            updateFeesForFormat(currentFormat);
        } else {
            // No format selected: set to 0
            baseFeeInput.value = '0.00';
            taxRateInput.value = '0.00';
            totalFeeInput.value = '0.00';
            // Restore original duration only when no format selected
            durationInput.value = originalDuration;
        }
        
        // Only clear service field if it still says "Consultation"
        if (serviceInput && serviceInput.value === 'Consultation') {
            serviceInput.value = '';
        }
        
        if (!isEdit) {
            sessionNumberDisplay.textContent = 'Session ' + nextSessionNumber;
        }
    }
});

// Pro bono checkbox logic
const proBonoCheckbox = document.getElementById('is_pro_bono');

if (proBonoCheckbox) {
    proBonoCheckbox.addEventListener('change', function() {
        if (this.checked) {
            // Pro bono: set fees to 0, keep session numbering
            baseFeeInput.value = '0.00';
            taxRateInput.value = '0.00';
            totalFeeInput.value = '0.00';
            
            // Uncheck consultation if it was checked
            if (consultationCheckbox.checked) {
                consultationCheckbox.checked = false;
            }
        } else {
            // Unchecked: restore fees based on format
            const currentFormat = formatDropdown.value;
            
            if (currentFormat && currentFormat !== '') {
                updateFeesForFormat(currentFormat);
            } else {
                baseFeeInput.value = '0.00';
                taxRateInput.value = '0.00';
                totalFeeInput.value = '0.00';
            }
        }
    });
}

// Prevent both consultation and pro bono being checked at once
if (consultationCheckbox && proBonoCheckbox) {
    consultationCheckbox.addEventListener('change', function() {
        if (this.checked && proBonoCheckbox.checked) {
            proBonoCheckbox.checked = false;
        }
    });
}

/**
 * Format fee value to 2 decimal places on blur
 * @param {Event} e - Blur event
 */
function formatFeeOnBlur(e) {
    let value = parseFloat(e.target.value);
    if (!isNaN(value)) {
        e.target.value = value.toFixed(2);
    }
}

// Currency formatting for all fee fields on blur
baseFeeInput.addEventListener('blur', formatFeeOnBlur);
taxRateInput.addEventListener('blur', formatFeeOnBlur);
totalFeeInput.addEventListener('blur', formatFeeOnBlur);

// Auto-expanding textarea
const textarea = document.getElementById('content');
const maxHeight = 600; // About 30-35 lines

/**
 * Auto-resize textarea to fit content up to maxHeight
 * (delegates to shared_utils.js)
 */
function autoResize() {
    autoResizeTextarea(textarea, maxHeight);
}

// Run on page load (for edit mode with existing content)
// Use requestAnimationFrame to ensure DOM is fully rendered (Safari fix)
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        requestAnimationFrame(autoResize);
    });
} else {
    requestAnimationFrame(autoResize);
}

// Run on input
textarea.addEventListener('input', autoResize);

/**
 * Close the missing link group modal
 */
function closeMissingLinkModal() {
    document.getElementById('missing-link-modal').style.display = 'none';
}


// ============================================================
// DATE AND TIME PICKERS INITIALIZATION
// ============================================================

/**
 * Initialize date and time pickers for session form
 */
async function initSessionPickers() {
    // Get initial values from hidden inputs
    const dateInput = document.getElementById('date');
    const timeInput = document.getElementById('session_time');
    
    // Parse initial date
    let initialDate = new Date();
    if (dateInput && dateInput.value) {
        const parts = dateInput.value.split('-');
        if (parts.length === 3) {
            initialDate = new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]));
        }
    }
    
    // Get time format setting
    const timeFormat = await getTimeFormatSetting();
    
    // Initialize date picker
    const dateContainer = document.getElementById('session-date-picker');
    if (dateContainer) {
        const datePicker = new DatePicker(dateContainer, {
            initialDate: initialDate,
            onSelect: (date) => {
                const y = date.getFullYear();
                const m = (date.getMonth() + 1).toString().padStart(2, '0');
                const d = date.getDate().toString().padStart(2, '0');
                dateInput.value = `${y}-${m}-${d}`;
            }
        });
    }
    
    // Initialize time picker
    const timeContainer = document.getElementById('session-time-picker');
    if (timeContainer) {
        const timePicker = new TimePicker(timeContainer, {
            format: timeFormat,
            initialTime: timeInput.value || null,
            onSelect: (time) => {
                timeInput.value = time;
            }
        });
        
        // Set initial value if not in edit mode
        if (!timeInput.value) {
            timeInput.value = timePicker.getTime();
        }
    }

    // Picker init is async (awaits the time-format setting) and writes
    // form values (default time above) AFTER the dirty-tracking baseline
    // is captured at DOMContentLoaded. Announce completion so the guard
    // can re-baseline; otherwise the form reads as dirty from page load.
    document.dispatchEvent(new Event('pickers:ready'));
}

// Initialize pickers when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initSessionPickers);
} else {
    initSessionPickers();
}


// ============================================================
// AI SCRIBE BUTTON VALIDATION
// ============================================================

/**
 * Show a validation message for AI Scribe requirements
 */
function showAiScribeValidationMessage() {
    // Check if we already have a modal for this
    let modal = document.getElementById('ai-scribe-validation-modal');
    if (!modal) {
        // Create the modal
        modal = document.createElement('div');
        modal.id = 'ai-scribe-validation-modal';
        modal.className = 'modal-overlay';
        modal.innerHTML = `
            <div class="modal-content">
                <h3>Fill in Session Details First</h3>
                <p>Please fill in the required session details (date, time, modality, format, duration) before using AI Scribe.</p>
                <div class="modal-actions">
                    <button type="button" class="btn btn-primary" onclick="document.getElementById('ai-scribe-validation-modal').style.display='none'">OK</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
    }
    modal.style.display = 'flex';
}

/**
 * Check if required fields for AI Scribe are filled
 */
function validateForAiScribe() {
    const dateInput = document.getElementById('date');
    const timeInput = document.getElementById('session_time');
    const modalitySelect = document.getElementById('modality');
    const formatSelect = document.getElementById('format');
    const durationInput = document.getElementById('duration');
    
    // Check each required field
    if (!dateInput || !dateInput.value) return false;
    if (!timeInput || !timeInput.value) return false;
    if (!modalitySelect || !modalitySelect.value) return false;
    if (!formatSelect || !formatSelect.value) return false;
    if (!durationInput || !durationInput.value) return false;
    
    return true;
}

// Add click handler to AI Scribe button
document.addEventListener('DOMContentLoaded', function() {
    const aiScribeBtn = document.querySelector('button[name="ai_scribe"]');
    if (aiScribeBtn) {
        aiScribeBtn.addEventListener('click', function(e) {
            if (!validateForAiScribe()) {
                e.preventDefault();
                showAiScribeValidationMessage();
            }
        });
    }
});


// ---------------------------------------------------------------------------
// Form dirty-tracking — two consumers:
//
// 1. Locked-entry review: "Save Changes" stays disabled (labelled "No
//    Changes") until the form actually differs from what was loaded.
// 2. All modes: unsaved-changes protection. Navigating away from a dirty
//    form — Cancel/Back, Prev/Next, tab close, reload — asks first.
//    Session notes are the most expensive thing in the app to lose.
//
// Implementation note: the date/time pickers (pickers.js) write input values
// programmatically and dispatch NO input/change events, so event listeners
// alone would miss picker edits. Instead we snapshot the serialized form
// state at load and re-compare on demand. Symmetric by construction:
// editing a field and then restoring its original value reads as clean.
// The backend has its own no-op guard for no-change saves of locked
// entries (entries.edit_session), so the button state is UX, not integrity.
// ---------------------------------------------------------------------------
document.addEventListener('DOMContentLoaded', function() {
    // Select the entry form BY ID: edit-mode pages contain a second POST
    // form (the redact button component, which renders before this one),
    // so form[method="post"] or forms[0] would bind the wrong form and
    // silently disable dirty detection on exactly the pages that need it.
    const form = document.getElementById('session-entry-form');
    if (!form) return;

    const saveBtn = document.getElementById('save-changes-btn');  // locked mode only
    const serialize = () => new URLSearchParams(new FormData(form)).toString();
    let baseline = serialize();
    const isDirty = () => serialize() !== baseline;

    // Re-baseline when async picker init finishes: it writes form values
    // (e.g. a default time) AFTER the snapshot above, which otherwise
    // leaves the form permanently "dirty" from page load — prompting on
    // every reload/close with no user edit. If the user has already
    // edited, their dirty state wins and we skip the re-baseline.
    let userEdited = false;
    document.addEventListener('pickers:ready', () => {
        if (!userEdited) {
            baseline = serialize();
            refreshSaveButton();
        }
    });

    const refreshSaveButton = () => {
        if (!saveBtn) return;
        const dirty = isDirty();
        saveBtn.disabled = !dirty;
        saveBtn.textContent = dirty ? 'Save Changes' : 'No Changes';
    };

    const markUserEdited = () => { userEdited = true; refreshSaveButton(); };
    form.addEventListener('input', markUserEdited);
    form.addEventListener('change', markUserEdited);
    // Catches picker writes: their click handlers set values before this
    // document-level listener runs in the bubble phase.
    document.addEventListener('click', refreshSaveButton);

    // In-page navigation (Cancel/Back, Prev, Next): custom modal with the
    // destination remembered until the user decides.
    //
    // NOTE: deliberately NO window beforeunload guard. A native
    // leave-page warning on tab close/reload kept misfiring across
    // browsers (see Session log 2026-06-10) and is not worth the UX
    // risk; the modal covers the in-app navigation paths where notes
    // actually get lost.
    const modal = document.getElementById('unsaved-changes-modal');
    const stayBtn = document.getElementById('unsaved-stay-btn');
    const leaveBtn = document.getElementById('unsaved-leave-btn');
    let pendingHref = null;

    if (modal && stayBtn && leaveBtn) {
        document.querySelectorAll('.entry-form-actions a.btn').forEach((link) => {
            link.addEventListener('click', (e) => {
                if (!isDirty()) return;
                e.preventDefault();
                pendingHref = link.href;
                modal.style.display = 'flex';
            });
        });

        stayBtn.addEventListener('click', () => {
            pendingHref = null;
            modal.style.display = 'none';
        });

        leaveBtn.addEventListener('click', () => {
            if (!pendingHref) return;
            modal.style.display = 'none';
            window.location.assign(pendingHref);
        });
    }

});
