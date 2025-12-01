/**
 * Session Entry Form JavaScript - EdgeCase Equalizer
 * Handles session creation/editing including format-based fee calculation,
 * consultation/pro-bono toggles, and link group integration.
 */

// ============================================================
// DATA INITIALIZATION
// ============================================================

const sessionData = document.getElementById('session-data');
const isEdit = sessionData?.dataset.isEdit === 'true';
const nextSessionNumber = sessionData?.dataset.nextSessionNumber || '';

// Parse fee sources from JSON script tag
const feeSourcesScript = document.getElementById('fee-sources-data');
const feeSources = feeSourcesScript ? JSON.parse(feeSourcesScript.textContent) : {};
window.feeSources = feeSources;

// Form elements
const formatDropdown = document.getElementById('format');
const baseFeeInput = document.getElementById('base_fee');
const taxRateInput = document.getElementById('tax_rate');
const totalFeeInput = document.getElementById('fee');
const feeSourceSpan = document.getElementById('fee-source');
const durationInput = document.getElementById('duration');
const consultationCheckbox = document.getElementById('is_consultation');
const proBonoCheckbox = document.getElementById('is_pro_bono');
const sessionNumberDisplay = document.getElementById('session-number-display');

// Store original values for restoration
const originalBaseFee = baseFeeInput?.value || '0.00';
const originalTaxRate = taxRateInput?.value || '0.00';
const originalTotalFee = totalFeeInput?.value || '0.00';
const originalDuration = durationInput?.value || '50';

// Consultation settings (loaded from server)
let consultationBase = '0.00';
let consultationTax = '0.00';
let consultationTotal = '0.00';
let consultationDuration = '20';

// ============================================================
// FEE CALCULATION
// ============================================================

/**
 * Update fees based on selected session format
 * @param {string} format - 'individual', 'couples', 'family', or 'group'
 */
function updateFeesForFormat(format) {
    // Don't auto-update fees when editing existing sessions
    if (isEdit) return;
    
    // Don't update if consultation or pro bono is checked
    if (consultationCheckbox?.checked || proBonoCheckbox?.checked) return;
    
    let fees = null;
    let source = '';
    
    if (format === 'individual') {
        fees = feeSources.profileFees;
        source = 'Profile';
        
        if (feeSources.profileFees?.duration) {
            durationInput.value = feeSources.profileFees.duration;
        }
    } else if (['couples', 'family', 'group'].includes(format)) {
        if (feeSources.linkGroups?.[format]) {
            fees = feeSources.linkGroups[format];
            source = `Link Group (${format.charAt(0).toUpperCase() + format.slice(1)})`;
            
            if (feeSources.linkGroups[format].duration) {
                durationInput.value = feeSources.linkGroups[format].duration;
            }
        } else {
            // No link group found - show modal
            const formatName = format.charAt(0).toUpperCase() + format.slice(1);
            const message = `This client is not in a ${formatName} link group. To bill ${format} sessions, you need to create a link group with the "${formatName}" format first.`;
            
            document.getElementById('missing-link-message').textContent = message;
            document.getElementById('missing-link-modal').style.display = 'flex';
            
            formatDropdown.value = 'individual';
            updateFeesForFormat('individual');
            return;
        }
    }
    
    if (fees) {
        baseFeeInput.value = parseFloat(fees.base || 0).toFixed(2);
        taxRateInput.value = parseFloat(fees.tax || 0).toFixed(2);
        totalFeeInput.value = parseFloat(fees.total || 0).toFixed(2);
        feeSourceSpan.textContent = `Source: ${source}`;
    }
}

/**
 * Three-way fee calculation when user manually edits fees
 * @param {string} changedField - 'base', 'tax', or 'total'
 */
function calculateSessionFee(changedField) {
    const base = parseFloat(baseFeeInput.value) || 0;
    const taxRate = parseFloat(taxRateInput.value) || 0;
    const total = parseFloat(totalFeeInput.value) || 0;
    
    if (changedField === 'base' || changedField === 'tax') {
        totalFeeInput.value = (base * (1 + taxRate / 100)).toFixed(2);
    } else if (changedField === 'total') {
        baseFeeInput.value = (taxRate > 0 ? total / (1 + taxRate / 100) : total).toFixed(2);
    }
}

/**
 * Format fee field to 2 decimal places on blur
 * @param {Event} e - Blur event
 */
function formatFeeOnBlur(e) {
    const value = parseFloat(e.target.value);
    if (!isNaN(value)) {
        e.target.value = value.toFixed(2);
    }
}

// ============================================================
// CONSULTATION SETTINGS
// ============================================================

/**
 * Load consultation settings from server
 */
function loadConsultationSettings() {
    fetch('/api/practice_info')
        .then(response => response.json())
        .then(data => {
            if (data.success && data.info) {
                consultationBase = data.info.consultation_base_price || '0.00';
                consultationTax = data.info.consultation_tax_rate || '0.00';
                consultationTotal = data.info.consultation_fee || '0.00';
                consultationDuration = data.info.consultation_duration || '20';
            }
            
            // Apply if checkbox already checked on page load
            if (consultationCheckbox?.checked) {
                applyConsultationFees();
            }
        })
        .catch(error => console.error('Failed to load consultation settings:', error));
}

/**
 * Apply consultation fees to form
 */
function applyConsultationFees() {
    baseFeeInput.value = consultationBase;
    taxRateInput.value = consultationTax;
    totalFeeInput.value = consultationTotal;
    durationInput.value = consultationDuration;
}

// ============================================================
// CHECKBOX HANDLERS
// ============================================================

/**
 * Handle consultation checkbox change
 */
function handleConsultationChange() {
    if (consultationCheckbox.checked) {
        applyConsultationFees();
        
        if (!isEdit && sessionNumberDisplay) {
            sessionNumberDisplay.textContent = 'Consultation';
        }
    } else {
        const currentFormat = formatDropdown?.value;
        
        if (currentFormat) {
            updateFeesForFormat(currentFormat);
        } else {
            baseFeeInput.value = '0.00';
            taxRateInput.value = '0.00';
            totalFeeInput.value = '0.00';
        }
        
        durationInput.value = originalDuration;
        
        if (!isEdit && sessionNumberDisplay) {
            sessionNumberDisplay.textContent = 'Session ' + nextSessionNumber;
        }
    }
    
    // Uncheck pro bono if consultation is checked
    if (consultationCheckbox.checked && proBonoCheckbox?.checked) {
        proBonoCheckbox.checked = false;
    }
}

/**
 * Handle pro bono checkbox change
 */
function handleProBonoChange() {
    if (proBonoCheckbox.checked) {
        baseFeeInput.value = '0.00';
        taxRateInput.value = '0.00';
        totalFeeInput.value = '0.00';
        
        // Uncheck consultation
        if (consultationCheckbox?.checked) {
            consultationCheckbox.checked = false;
        }
    } else {
        const currentFormat = formatDropdown?.value;
        
        if (currentFormat) {
            updateFeesForFormat(currentFormat);
        } else {
            baseFeeInput.value = '0.00';
            taxRateInput.value = '0.00';
            totalFeeInput.value = '0.00';
        }
    }
}

// ============================================================
// AUTO-EXPANDING TEXTAREA
// ============================================================

/**
 * Initialize auto-expanding textarea
 */
function initAutoExpandTextarea() {
    const textarea = document.getElementById('content');
    if (!textarea) return;
    
    const maxHeight = 600;
    
    function autoResize() {
        textarea.style.height = 'auto';
        const newHeight = Math.min(textarea.scrollHeight, maxHeight);
        textarea.style.height = newHeight + 'px';
        textarea.style.overflowY = textarea.scrollHeight > maxHeight ? 'scroll' : 'hidden';
    }
    
    autoResize();
    textarea.addEventListener('input', autoResize);
}

// ============================================================
// MODALS
// ============================================================

/**
 * Close the missing link group modal
 */
function closeMissingLinkModal() {
    document.getElementById('missing-link-modal').style.display = 'none';
}

// ============================================================
// INITIALIZATION
// ============================================================

document.addEventListener('DOMContentLoaded', function() {
    // Load consultation settings
    loadConsultationSettings();
    
    // Format dropdown - update fees on change (new sessions only)
    if (formatDropdown) {
        formatDropdown.addEventListener('change', function() {
            updateFeesForFormat(this.value);
        });
        
        if (formatDropdown.value && !isEdit) {
            updateFeesForFormat(formatDropdown.value);
        }
    }
    
    // Fee field event listeners
    if (baseFeeInput) {
        baseFeeInput.addEventListener('input', () => calculateSessionFee('base'));
        baseFeeInput.addEventListener('blur', formatFeeOnBlur);
    }
    if (taxRateInput) {
        taxRateInput.addEventListener('input', () => calculateSessionFee('tax'));
        taxRateInput.addEventListener('blur', formatFeeOnBlur);
    }
    if (totalFeeInput) {
        totalFeeInput.addEventListener('input', () => calculateSessionFee('total'));
        totalFeeInput.addEventListener('blur', formatFeeOnBlur);
    }
    
    // Checkbox handlers
    if (consultationCheckbox) {
        consultationCheckbox.addEventListener('change', handleConsultationChange);
    }
    if (proBonoCheckbox) {
        proBonoCheckbox.addEventListener('change', handleProBonoChange);
    }
    
    // Auto-expanding textarea
    initAutoExpandTextarea();
});
