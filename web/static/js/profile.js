/**
 * Profile Entry Form JavaScript - EdgeCase Equalizer
 * Handles client profile creation/editing including guardian billing, fee overrides,
 * phone formatting, and form validation.
 */

// ============================================================
// STATE
// ============================================================

let lastEditedFee = null;
let validationPassed = false;

// ============================================================
// VALIDATION MODAL
// ============================================================

/**
 * Show the validation error modal
 * @param {string} message - HTML message to display
 */
function showValidationModal(message) {
    document.getElementById('validation-errors').innerHTML = message;
    document.getElementById('validation-modal').style.display = 'flex';
}

/**
 * Close the validation modal
 */
function closeValidationModal() {
    document.getElementById('validation-modal').style.display = 'none';
}

// ============================================================
// PHONE NUMBER FORMATTING
// ============================================================

/**
 * Format phone number for display (North American format)
 * @param {string} value - Raw phone input
 * @returns {string} Formatted phone or raw digits
 */
function formatPhoneNumber(value) {
    let cleaned = value.replace(/\D/g, '').substring(0, 12);
    
    if (cleaned.length === 10) {
        return '(' + cleaned.substring(0, 3) + ') ' + cleaned.substring(3, 6) + '-' + cleaned.substring(6, 10);
    }
    
    return cleaned;
}

/**
 * Validate phone number has 10-12 digits
 * @param {string} phoneValue - Phone value to validate
 * @returns {boolean} True if valid or empty
 */
function validatePhone(phoneValue) {
    if (!phoneValue) return true;
    const digitsOnly = phoneValue.replace(/\D/g, '');
    return digitsOnly.length >= 10 && digitsOnly.length <= 12;
}

/**
 * Initialize phone input formatting for all phone fields
 */
function initPhoneInputs() {
    document.querySelectorAll('.phone-input').forEach(input => {
        if (input.value) {
            input.value = formatPhoneNumber(input.value);
        }
        
        input.addEventListener('input', function() {
            const cursorPos = this.selectionStart;
            const oldLength = this.value.length;
            
            this.value = formatPhoneNumber(this.value);
            
            const newLength = this.value.length;
            const newCursor = cursorPos + (newLength - oldLength);
            this.setSelectionRange(newCursor, newCursor);
        });
    });
}

// ============================================================
// FEE OVERRIDE
// ============================================================

/**
 * Initialize fee override toggle and calculation
 */
function initFeeOverride() {
    const feeOverrideEnabled = document.getElementById('fee_override_enabled');
    const feeOverrideFields = document.getElementById('fee-override-fields');
    
    if (!feeOverrideEnabled) return;
    
    feeOverrideEnabled.addEventListener('change', function() {
        if (this.checked) {
            feeOverrideFields.style.display = 'block';
            
            // Auto-populate with type defaults if empty
            const form = document.getElementById('profile-form');
            const baseInput = document.getElementById('fee_override_base');
            const taxInput = document.getElementById('fee_override_tax_rate');
            const totalInput = document.getElementById('fee_override_total');
            
            if (!baseInput.value) baseInput.value = form.dataset.typeBase;
            if (!taxInput.value) taxInput.value = form.dataset.typeTax;
            if (!totalInput.value) totalInput.value = form.dataset.typeTotal;
        } else {
            feeOverrideFields.style.display = 'none';
            document.getElementById('fee_override_base').value = '';
            document.getElementById('fee_override_tax_rate').value = '';
            document.getElementById('fee_override_total').value = '';
        }
    });
    
    initFeeCalculation();
}

/**
 * Initialize three-way fee calculation listeners
 */
function initFeeCalculation() {
    const feeOverrideBase = document.getElementById('fee_override_base');
    const feeOverrideTax = document.getElementById('fee_override_tax_rate');
    const feeOverrideTotal = document.getElementById('fee_override_total');
    
    if (!feeOverrideBase) return;
    
    function calculateOverrideFee() {
        const base = parseFloat(feeOverrideBase.value) || 0;
        const rate = parseFloat(feeOverrideTax.value) || 0;
        const total = parseFloat(feeOverrideTotal.value) || 0;
        
        if (lastEditedFee === 'base' || lastEditedFee === 'tax') {
            feeOverrideTotal.value = (base * (1 + rate / 100)).toFixed(2);
        } else if (lastEditedFee === 'total') {
            feeOverrideBase.value = (total / (1 + rate / 100)).toFixed(2);
        }
    }
    
    function formatOnBlur(el) {
        if (el.value) el.value = parseFloat(el.value).toFixed(2);
    }
    
    feeOverrideBase.addEventListener('input', () => { lastEditedFee = 'base'; calculateOverrideFee(); });
    feeOverrideBase.addEventListener('blur', () => formatOnBlur(feeOverrideBase));
    
    feeOverrideTax.addEventListener('input', () => { lastEditedFee = 'tax'; calculateOverrideFee(); });
    feeOverrideTax.addEventListener('blur', () => formatOnBlur(feeOverrideTax));
    
    feeOverrideTotal.addEventListener('input', () => { lastEditedFee = 'total'; calculateOverrideFee(); });
    feeOverrideTotal.addEventListener('blur', () => formatOnBlur(feeOverrideTotal));
}

// ============================================================
// GUARDIAN SECTION
// ============================================================

/**
 * Initialize guardian section toggles
 */
function initGuardianSection() {
    const isMinor = document.getElementById('is_minor');
    const guardianFields = document.getElementById('guardian-fields');
    const hasGuardian2 = document.getElementById('has_guardian2');
    const guardian2Fields = document.getElementById('guardian2-fields');
    
    if (isMinor) {
        isMinor.addEventListener('change', function() {
            guardianFields.style.display = this.checked ? 'block' : 'none';
            toggleFieldsDisabled(guardianFields, !this.checked);
        });
    }
    
    if (hasGuardian2) {
        hasGuardian2.addEventListener('change', function() {
            guardian2Fields.style.display = this.checked ? 'block' : 'none';
            toggleFieldsDisabled(guardian2Fields, !this.checked);
        });
    }
    
    // Initialize disabled state
    if (isMinor && !isMinor.checked) {
        toggleFieldsDisabled(guardianFields, true);
    }
    if (hasGuardian2 && !hasGuardian2.checked) {
        toggleFieldsDisabled(guardian2Fields, true);
    }
    
    initGuardianPercentageValidation();
}

/**
 * Toggle disabled state on all inputs within a container
 * @param {HTMLElement} container - Container element
 * @param {boolean} disabled - Whether to disable
 */
function toggleFieldsDisabled(container, disabled) {
    if (!container) return;
    container.querySelectorAll('input, textarea').forEach(input => {
        if (disabled) {
            input.setAttribute('disabled', 'disabled');
        } else {
            input.removeAttribute('disabled');
        }
    });
}

/**
 * Initialize guardian percentage validation
 */
function initGuardianPercentageValidation() {
    const guardian1Amount = document.getElementById('guardian1_amount');
    const guardian2Amount = document.getElementById('guardian2_amount');
    
    if (guardian1Amount) {
        guardian1Amount.addEventListener('input', validateGuardianAmounts);
        guardian1Amount.addEventListener('blur', function() {
            if (this.value) this.value = parseFloat(this.value).toFixed(1);
        });
    }
    
    if (guardian2Amount) {
        guardian2Amount.addEventListener('input', validateGuardianAmounts);
        guardian2Amount.addEventListener('blur', function() {
            if (this.value) this.value = parseFloat(this.value).toFixed(1);
        });
    }
}

/**
 * Validate that guardian percentages add up to 100%
 * @returns {boolean} True if valid
 */
function validateGuardianAmounts() {
    const isMinor = document.getElementById('is_minor');
    const hasGuardian2 = document.getElementById('has_guardian2');
    const validation = document.getElementById('guardian-validation');
    const validationMessage = document.getElementById('guardian-validation-message');
    
    if (!isMinor || !isMinor.checked) {
        if (validation) validation.style.display = 'none';
        return true;
    }
    
    const guardian1Percent = parseFloat(document.getElementById('guardian1_amount').value) || 0;
    const guardian2Percent = (hasGuardian2 && hasGuardian2.checked) ? 
        (parseFloat(document.getElementById('guardian2_amount').value) || 0) : 0;
    
    const total = guardian1Percent + guardian2Percent;
    const difference = Math.abs(total - 100);
    
    if (difference > 0.1) {
        validation.style.display = 'block';
        validationMessage.innerHTML = `<br>Guardian percentages (${total.toFixed(1)}%) must equal 100%`;
        return false;
    } else {
        validation.style.display = 'none';
        return true;
    }
}

// ============================================================
// DATE OF BIRTH
// ============================================================

/**
 * Initialize date of birth dropdown to hidden field sync
 */
function initDateOfBirth() {
    const dobYear = document.getElementById('dob_year');
    const dobMonth = document.getElementById('dob_month');
    const dobDay = document.getElementById('dob_day');
    const dobHidden = document.getElementById('date_of_birth');
    
    if (!dobYear) return;
    
    function updateDOB() {
        if (dobYear.value && dobMonth.value && dobDay.value) {
            dobHidden.value = `${dobYear.value}-${dobMonth.value}-${dobDay.value}`;
        } else {
            dobHidden.value = '';
        }
    }
    
    dobYear.addEventListener('change', updateDOB);
    dobMonth.addEventListener('change', updateDOB);
    dobDay.addEventListener('change', updateDOB);
}

// ============================================================
// AUTO-EXPANDING TEXTAREA
// ============================================================

/**
 * Initialize auto-expanding textarea for Additional Information
 */
function initAutoExpandTextarea() {
    const textarea = document.getElementById('additional_info');
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
// TYPE DROPDOWN
// ============================================================

/**
 * Toggle dropdown visibility
 * @param {string} dropdownId - ID of dropdown element
 */
function toggleDropdown(dropdownId) {
    const dropdown = document.getElementById(dropdownId);
    if (dropdown.style.display === 'none' || dropdown.style.display === '') {
        dropdown.style.display = 'block';
    } else {
        dropdown.style.display = 'none';
    }
}

/**
 * Initialize type badge dropdown
 */
function initTypeDropdown() {
    const typeBadge = document.getElementById('profile-type-badge');
    if (typeBadge) {
        typeBadge.addEventListener('click', function(e) {
            e.stopPropagation();
            toggleDropdown('type-dropdown');
        });
    }
    
    document.addEventListener('click', function(e) {
        if (!e.target.closest('.type-badge') && !e.target.closest('[id$="-dropdown"]')) {
            const dropdown = document.getElementById('type-dropdown');
            if (dropdown) dropdown.style.display = 'none';
        }
    });
}

// ============================================================
// FORM VALIDATION
// ============================================================

/**
 * Initialize form submission validation
 */
function initFormValidation() {
    const form = document.getElementById('profile-form');
    if (!form) return;
    
    form.addEventListener('submit', function(e) {
        if (validationPassed) {
            validationPassed = false;
            return true;
        }
        
        e.preventDefault();
        e.stopPropagation();
        
        const phoneInputs = [
            { element: document.getElementById('phone'), label: 'Cell' },
            { element: document.getElementById('home_phone'), label: 'Home Phone' },
            { element: document.getElementById('work_phone'), label: 'Work Phone' },
            { element: document.getElementById('emergency_contact_phone'), label: 'Emergency Contact Phone' },
            { element: document.getElementById('guardian1_phone'), label: 'Guardian 1 Phone' },
            { element: document.getElementById('guardian2_phone'), label: 'Guardian 2 Phone' }
        ];
        
        let errors = [];
        
        phoneInputs.forEach(input => {
            if (input.element && input.element.value && !validatePhone(input.element.value)) {
                errors.push('• ' + input.label + ' must be 10-12 digits');
                input.element.style.borderColor = '#e53e3e';
            } else if (input.element) {
                input.element.style.borderColor = '#e2e8f0';
            }
        });
        
        // Validate text number vs preferred contact
        const textNumber = document.getElementById('text_number');
        const preferredContact = document.getElementById('preferred_contact');
        
        if (preferredContact.value === 'text' && (!textNumber.value || textNumber.value === 'none')) {
            errors.push('• Cannot select "Text Message" as preferred contact if Text Number is "None (no texting)"');
            preferredContact.style.borderColor = '#e53e3e';
            if (textNumber) textNumber.style.borderColor = '#e53e3e';
        } else {
            preferredContact.style.borderColor = '#e2e8f0';
            if (textNumber) textNumber.style.borderColor = '#e2e8f0';
        }
        
        if (!validateGuardianAmounts()) {
            errors.push('• Guardian percentages must equal 100%');
        }
        
        if (errors.length > 0) {
            showValidationModal(errors.join('<br>'));
            return false;
        } else {
            validationPassed = true;
            this.submit();
        }
    });
}

// ============================================================
// INITIALIZATION
// ============================================================

document.addEventListener('DOMContentLoaded', function() {
    initPhoneInputs();
    initFeeOverride();
    initGuardianSection();
    initDateOfBirth();
    initAutoExpandTextarea();
    initTypeDropdown();
    initFormValidation();
});
