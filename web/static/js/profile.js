// Profile Entry Form JavaScript - Extracted from profile.html

// Validation modal functions
function showValidationModal(message) {
    document.getElementById('validation-errors').innerHTML = message;
    document.getElementById('validation-modal').style.display = 'flex';
}

function closeValidationModal() {
    document.getElementById('validation-modal').style.display = 'none';
}

// Phone number auto-formatting (supports 10-12 digits)
function formatPhoneNumber(value) {
    // Remove all non-digit characters
    let cleaned = value.replace(/\D/g, '');
    
    // Limit to 12 digits (international support)
    cleaned = cleaned.substring(0, 12);
    
    // Only format if exactly 10 digits (North American format)
    if (cleaned.length === 10) {
        return '(' + cleaned.substring(0, 3) + ') ' + cleaned.substring(3, 6) + '-' + cleaned.substring(6, 10);
    }
    
    // For 11-12 digits or incomplete, just return digits as-is
    return cleaned;
}

// Validate phone number has 10-12 digits
function validatePhone(phoneValue) {
    if (!phoneValue) return true; // Empty is okay
    const digitsOnly = phoneValue.replace(/\D/g, '');
    return digitsOnly.length >= 10 && digitsOnly.length <= 12;
}

// Add event listeners to all phone inputs (including guardian phones)
document.querySelectorAll('.phone-input').forEach(input => {
    if (input.value) {
        input.value = formatPhoneNumber(input.value);
    }
    
    input.addEventListener('input', function(e) {
        const cursorPos = this.selectionStart;
        const oldValue = this.value;
        const oldLength = oldValue.length;
        
        this.value = formatPhoneNumber(this.value);
        
        const newLength = this.value.length;
        if (newLength > oldLength) {
            this.setSelectionRange(cursorPos + (newLength - oldLength), cursorPos + (newLength - oldLength));
        } else {
            this.setSelectionRange(cursorPos, cursorPos);
        }
    });
});

// Fee Override toggle
const feeOverrideEnabled = document.getElementById('fee_override_enabled');
const feeOverrideFields = document.getElementById('fee-override-fields');

if (feeOverrideEnabled) {
    feeOverrideEnabled.addEventListener('change', function() {
        if (this.checked) {
            feeOverrideFields.style.display = 'block';
            // Auto-populate with type defaults if fields are empty
            const form = document.getElementById('profile-form');
            const baseInput = document.getElementById('fee_override_base');
            const taxInput = document.getElementById('fee_override_tax_rate');
            const totalInput = document.getElementById('fee_override_total');
            
            if (!baseInput.value) {
                baseInput.value = form.dataset.typeBase;
            }
            if (!taxInput.value) {
                taxInput.value = form.dataset.typeTax;
            }
            if (!totalInput.value) {
                totalInput.value = form.dataset.typeTotal;
            }
            
            // Recalculate total fee display for guardians
            updateGuardianTotalFee();
        } else {
            feeOverrideFields.style.display = 'none';
            // Clear override fields when disabled
            document.getElementById('fee_override_base').value = '';
            document.getElementById('fee_override_tax_rate').value = '';
            document.getElementById('fee_override_total').value = '';
            
            updateGuardianTotalFee();
        }
    });
}

// Three-way fee calculation (same logic as Client Type and Item)
const feeOverrideBase = document.getElementById('fee_override_base');
const feeOverrideTax = document.getElementById('fee_override_tax_rate');
const feeOverrideTotal = document.getElementById('fee_override_total');

let lastEditedFee = null;

function calculateOverrideFee() {
    const base = parseFloat(feeOverrideBase.value) || 0;
    const rate = parseFloat(feeOverrideTax.value) || 0;
    const total = parseFloat(feeOverrideTotal.value) || 0;
    
    if (lastEditedFee === 'base' || lastEditedFee === 'tax') {
        const calculatedTotal = base * (1 + rate / 100);
        feeOverrideTotal.value = calculatedTotal.toFixed(2);
    } else if (lastEditedFee === 'total') {
        const calculatedBase = total / (1 + rate / 100);
        feeOverrideBase.value = calculatedBase.toFixed(2);
    }
    
    // Update guardian total fee display
    updateGuardianTotalFee();
}

if (feeOverrideBase) {
    feeOverrideBase.addEventListener('input', function() {
        lastEditedFee = 'base';
        calculateOverrideFee();
    });
    
    feeOverrideBase.addEventListener('blur', function() {
        if (this.value) {
            this.value = parseFloat(this.value).toFixed(2);
        }
    });
}

if (feeOverrideTax) {
    feeOverrideTax.addEventListener('input', function() {
        lastEditedFee = 'tax';
        calculateOverrideFee();
    });
    
    feeOverrideTax.addEventListener('blur', function() {
        if (this.value) {
            this.value = parseFloat(this.value).toFixed(2);
        }
    });
}

if (feeOverrideTotal) {
    feeOverrideTotal.addEventListener('input', function() {
        lastEditedFee = 'total';
        calculateOverrideFee();
    });
    
    feeOverrideTotal.addEventListener('blur', function() {
        if (this.value) {
            this.value = parseFloat(this.value).toFixed(2);
        }
    });
}

// Guardian section toggle
const isMinor = document.getElementById('is_minor');
const guardianFields = document.getElementById('guardian-fields');

if (isMinor) {
    isMinor.addEventListener('change', function() {
        guardianFields.style.display = this.checked ? 'block' : 'none';
    });
}

// Guardian 2 toggle
const hasGuardian2 = document.getElementById('has_guardian2');
const guardian2Fields = document.getElementById('guardian2-fields');

if (hasGuardian2) {
    hasGuardian2.addEventListener('change', function() {
        guardian2Fields.style.display = this.checked ? 'block' : 'none';
    });
}

// Update guardian total fee display
function updateGuardianTotalFee() {
    const display = document.getElementById('total-session-fee-display');
    if (!display) return;
    
    let total;
    if (feeOverrideEnabled && feeOverrideEnabled.checked && feeOverrideTotal.value) {
        total = parseFloat(feeOverrideTotal.value);
    } else {
        const form = document.getElementById('profile-form');
        total = parseFloat(form.dataset.typeTotal);
    }
    
    display.textContent = '$' + total.toFixed(2);
    
    // Revalidate guardian amounts
    validateGuardianAmounts();
}

// Guardian amount validation
function validateGuardianAmounts() {
    const validation = document.getElementById('guardian-validation');
    const validationMessage = document.getElementById('guardian-validation-message');
    
    if (!isMinor || !isMinor.checked) {
        if (validation) validation.style.display = 'none';
        return true;
    }
    
    const guardian1Amount = parseFloat(document.getElementById('guardian1_amount').value) || 0;
    const guardian2Amount = hasGuardian2 && hasGuardian2.checked ? 
                           (parseFloat(document.getElementById('guardian2_amount').value) || 0) : 0;
    
    const total = guardian1Amount + guardian2Amount;
    
    // Get expected total
    let expectedTotal;
    if (feeOverrideEnabled && feeOverrideEnabled.checked && feeOverrideTotal.value) {
        expectedTotal = parseFloat(feeOverrideTotal.value);
    } else {
        const form = document.getElementById('profile-form');
        expectedTotal = parseFloat(form.dataset.typeTotal);
    }
    
    const difference = Math.abs(total - expectedTotal);
    
    if (difference > 0.01) { // Allow 1 cent rounding difference
        validation.style.display = 'flex';
        validationMessage.textContent = `Guardian amounts ($${total.toFixed(2)}) must equal total session fee ($${expectedTotal.toFixed(2)})`;
        return false;
    } else {
        validation.style.display = 'none';
        return true;
    }
}

// Add validation to guardian amount inputs
const guardian1Amount = document.getElementById('guardian1_amount');
const guardian2Amount = document.getElementById('guardian2_amount');

if (guardian1Amount) {
    guardian1Amount.addEventListener('input', validateGuardianAmounts);
    guardian1Amount.addEventListener('blur', function() {
        if (this.value) {
            this.value = parseFloat(this.value).toFixed(2);
        }
    });
}

if (guardian2Amount) {
    guardian2Amount.addEventListener('input', validateGuardianAmounts);
    guardian2Amount.addEventListener('blur', function() {
        if (this.value) {
            this.value = parseFloat(this.value).toFixed(2);
        }
    });
}

// Form validation on submit
let validationPassed = false;

document.getElementById('profile-form').addEventListener('submit', function(e) {
    // If validation already passed, allow submission
    if (validationPassed) {
        validationPassed = false; // Reset for next time
        return true;
    }
    
    // Prevent default to validate first
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
    
    // Validate text number vs preferred contact method
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
    
    // Validate guardian amounts if minor
    if (!validateGuardianAmounts()) {
        errors.push('• Guardian payment amounts must equal total session fee');
    }
    
    if (errors.length > 0) {
        showValidationModal(errors.join('<br>'));
        return false;
    } else {
        // Validation passed, submit the form
        validationPassed = true;
        this.submit();
    }
});

// Date of birth dropdowns → hidden field
const dobYear = document.getElementById('dob_year');
const dobMonth = document.getElementById('dob_month');
const dobDay = document.getElementById('dob_day');
const dobHidden = document.getElementById('date_of_birth');

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

// Auto-expanding textarea for Additional Information
const additionalInfoTextarea = document.getElementById('additional_info');
const maxHeight = 600; // About 30-35 lines

function autoResize() {
    // Reset height to auto to get the correct scrollHeight
    additionalInfoTextarea.style.height = 'auto';
    
    // Set new height, but don't exceed maxHeight
    const newHeight = Math.min(additionalInfoTextarea.scrollHeight, maxHeight);
    additionalInfoTextarea.style.height = newHeight + 'px';
    
    // Add scrollbar if content exceeds maxHeight
    if (additionalInfoTextarea.scrollHeight > maxHeight) {
        additionalInfoTextarea.style.overflowY = 'scroll';
    } else {
        additionalInfoTextarea.style.overflowY = 'hidden';
    }
}

// Run on page load (for edit mode with existing content)
autoResize();

// Run on input
additionalInfoTextarea.addEventListener('input', autoResize);

// Dropdown toggle for type selector
function toggleDropdown(dropdownId) {
    const dropdown = document.getElementById(dropdownId);
    
    // Toggle this dropdown (check for both 'none' and empty string)
    if (dropdown.style.display === 'none' || dropdown.style.display === '') {
        dropdown.style.display = 'block';
    } else {
        dropdown.style.display = 'none';
    }
}

// Add click handler to type badge
const typeBadge = document.getElementById('profile-type-badge');
if (typeBadge) {
    typeBadge.addEventListener('click', function(e) {
        e.stopPropagation();
        toggleDropdown('type-dropdown');
    });
}

// Close dropdown when clicking outside
document.addEventListener('click', function(e) {
    if (!e.target.closest('.type-badge') && !e.target.closest('[id$="-dropdown"]')) {
        const dropdown = document.getElementById('type-dropdown');
        if (dropdown) dropdown.style.display = 'none';
    }
});