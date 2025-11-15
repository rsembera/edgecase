// Session Entry Form JavaScript - Extracted from session.html

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
    const feeInput = document.getElementById('fee');
    const durationInput = document.getElementById('duration');
    const sessionNumberDisplay = document.getElementById('session-number-display');
    const originalFee = feeInput.value;
    const originalDuration = durationInput.value;

    // Fetch consultation settings from database
    let consultationFee = '0.00';
    let consultationDuration = '20';
    let settingsLoaded = false;

    // Load settings immediately
    fetch('/api/practice_info')
        .then(response => response.json())
        .then(data => {
            if (data.success && data.info) {
                consultationFee = data.info.consultation_fee || '0.00';
                consultationDuration = data.info.consultation_duration || '20';
            }
            settingsLoaded = true;
            // Apply if checkbox already checked
            if (consultationCheckbox.checked) {
                feeInput.value = consultationFee;
                durationInput.value = consultationDuration;
            }
        })
        .catch(error => console.error('Failed to load consultation settings:', error));

    consultationCheckbox.addEventListener('change', function() {
        // Get values from data attributes
        const isEdit = document.body.dataset.isEdit === 'true';
        const nextSessionNumber = document.body.dataset.nextSessionNumber || '';
        
        if (this.checked) {
            // Consultation: use settings from database
            feeInput.value = consultationFee;
            durationInput.value = consultationDuration;
            
            if (!isEdit) {
                sessionNumberDisplay.textContent = 'Consultation';
            }
        } else {
            // Regular session: restore original values
            feeInput.value = originalFee;
            durationInput.value = originalDuration;
            
            if (!isEdit) {
                sessionNumberDisplay.textContent = 'Session ' + nextSessionNumber;
            }
        }
    });

    // Currency formatting for fee field
    document.getElementById('fee').addEventListener('blur', function(e) {
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
