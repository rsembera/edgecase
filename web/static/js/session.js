// Session Entry Form JavaScript - Extracted from session.html

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
            
            // Reset to individual
            formatDropdown.value = 'individual';
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

// Three-way fee calculation (when user manually edits fees)
function calculateSessionFee(changedField) {
    const base = parseFloat(baseFeeInput.value) || 0;
    const taxRate = parseFloat(taxRateInput.value) || 0;
    const total = parseFloat(totalFeeInput.value) || 0;
    
    if (changedField === 'base' || changedField === 'tax') {
        // Calculate total from base + tax
        const calculatedTotal = base * (1 + taxRate / 100);
        totalFeeInput.value = calculatedTotal.toFixed(2);
    } else if (changedField === 'total') {
        // Calculate base from total - tax
        if (taxRate > 0) {
            const calculatedBase = total / (1 + taxRate / 100);
            baseFeeInput.value = calculatedBase.toFixed(2);
        } else {
            // If no tax, total = base
            baseFeeInput.value = total.toFixed(2);
        }
    }
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
        
        if (this.checked) {
            // Consultation: use settings from database (all three fee fields)
            baseFeeInput.value = consultationBase;
            taxRateInput.value = consultationTax;
            totalFeeInput.value = consultationTotal;
            durationInput.value = consultationDuration;
            
            if (!isEdit) {
                sessionNumberDisplay.textContent = 'Consultation';
            }
        } else {
            // Regular session: check if format is selected
            const currentFormat = formatDropdown.value;
            
            if (currentFormat && currentFormat !== '') {
                // Format selected: apply fees for that format
                updateFeesForFormat(currentFormat);
            } else {
                // No format selected: set to 0
                baseFeeInput.value = '0.00';
                taxRateInput.value = '0.00';
                totalFeeInput.value = '0.00';
            }
            
            // Restore original duration regardless
            durationInput.value = originalDuration;
            
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

    // Currency formatting for all fee fields on blur
    baseFeeInput.addEventListener('blur', function(e) {
        let value = parseFloat(e.target.value);
        if (!isNaN(value)) {
            e.target.value = value.toFixed(2);
        }
    });

    taxRateInput.addEventListener('blur', function(e) {
        let value = parseFloat(e.target.value);
        if (!isNaN(value)) {
            e.target.value = value.toFixed(2);
        }
    });

    totalFeeInput.addEventListener('blur', function(e) {
        let value = parseFloat(e.target.value);
        if (!isNaN(value)) {
            e.target.value = value.toFixed(2);
        }
    });

    // Auto-expanding textarea
    const textarea = document.getElementById('content');
    const maxHeight = 600; // About 30-35 lines

    function autoResize() {
        // Reset height to auto to get the correct scrollHeight
        textarea.style.height = 'auto';
        
        // Set new height, but don't exceed maxHeight
        const newHeight = Math.min(textarea.scrollHeight, maxHeight);
        textarea.style.height = newHeight + 'px';
        
        // Add scrollbar if content exceeds maxHeight
        if (textarea.scrollHeight > maxHeight) {
            textarea.style.overflowY = 'scroll';
        } else {
            textarea.style.overflowY = 'hidden';
        }
    }

    // Run on page load (for edit mode with existing content)
    autoResize();

    // Run on input
    textarea.addEventListener('input', autoResize);

    // Close missing link modal
    function closeMissingLinkModal() {
        document.getElementById('missing-link-modal').style.display = 'none';
    }