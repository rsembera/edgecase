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
    
    // Add event listeners to all phone inputs
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
            { element: document.getElementById('emergency_contact_phone'), label: 'Emergency Contact Phone' }
        ];
        
        let errors = [];
        
        phoneInputs.forEach(input => {
            if (input.element.value && !validatePhone(input.element.value)) {
                errors.push('• ' + input.label + ' must be 10-12 digits');
                input.element.style.borderColor = '#e53e3e';
            } else {
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
