/**
 * Settings Page JavaScript - EdgeCase Equalizer
 * Handles practice info, file uploads, theme settings, and various configuration options.
 */

// ============================================================
// HELPER: SHOW SECTION STATUS
// ============================================================

/**
 * Show a temporary success message in a section
 * @param {string} statusId - The ID of the status element
 * @param {string} message - Message to display (default: "✓ Saved!")
 */
function showSectionStatus(statusId, message = '✓ Saved!') {
    const status = document.getElementById(statusId);
    if (status) {
        status.textContent = message;
        status.classList.add('show');
        setTimeout(() => status.classList.remove('show'), 2500);
    }
}

// ============================================================
// CONFIRMATION MODAL
// ============================================================

let confirmCallback = null;

/**
 * Show a confirmation modal with custom title and message
 * @param {string} title - Modal title
 * @param {string} message - Modal message
 * @param {Function} onConfirm - Callback to execute on confirmation
 */
function showConfirmModal(title, message, onConfirm) {
    document.getElementById('confirm-title').textContent = title;
    document.getElementById('confirm-message').textContent = message;
    document.getElementById('confirm-modal').style.display = 'flex';
    
    confirmCallback = onConfirm;
    
    document.getElementById('confirm-ok-button').onclick = function() {
        const callback = confirmCallback;
        closeConfirmModal();
        if (callback) callback();
    };
}

/**
 * Close the confirmation modal
 */
function closeConfirmModal() {
    document.getElementById('confirm-modal').style.display = 'none';
    confirmCallback = null;
}

// ============================================================
// ABOUT MODAL
// ============================================================

/**
 * Show the about modal
 */
function showAboutModal() {
    document.getElementById('about-modal').style.display = 'flex';
}

/**
 * Close the about modal
 */
function closeAboutModal() {
    document.getElementById('about-modal').style.display = 'none';
}

// ============================================================
// CARD LAYOUT MANAGEMENT (auto-save, no confirmation)
// ============================================================

const CARD_NAMES = {
    'active-clients': 'Active Clients',
    'sessions-week': 'Sessions This Week',
    'pending-invoices': 'Pending Invoices',
    'billable-month': 'Billable This Month',
    'current-time': 'Current Time',
    'navigation': 'Navigation'
};

const DEFAULT_CARD_ORDER = [
    'active-clients', 'sessions-week', 'pending-invoices',
    'billable-month', 'current-time', 'navigation'
];

/**
 * Load card positions from localStorage and populate dropdowns
 * @returns {Array} Current card order
 */
function loadCardPositions() {
    const savedOrder = localStorage.getItem('cardOrder');
    const currentOrder = savedOrder ? JSON.parse(savedOrder) : [...DEFAULT_CARD_ORDER];
    
    for (let i = 0; i < 6; i++) {
        const select = document.getElementById(`position-${i + 1}`);
        if (select) select.value = currentOrder[i];
    }
    
    return currentOrder;
}

/**
 * Handle card position swap when dropdown changes (auto-save, no message)
 * @param {number} position - Zero-based position index
 */
function handleCardSwap(position) {
    const select = document.getElementById(`position-${position + 1}`);
    const newCardId = select.value;
    
    const savedOrder = localStorage.getItem('cardOrder');
    const currentOrder = savedOrder ? JSON.parse(savedOrder) : [...DEFAULT_CARD_ORDER];
    
    const oldCardId = currentOrder[position];
    const existingPosition = currentOrder.indexOf(newCardId);
    
    if (existingPosition !== -1 && existingPosition !== position) {
        // Swap cards
        currentOrder[position] = newCardId;
        currentOrder[existingPosition] = oldCardId;
        
        // Update all dropdowns
        for (let i = 0; i < 6; i++) {
            document.getElementById(`position-${i + 1}`).value = currentOrder[i];
        }
        
        localStorage.setItem('cardOrder', JSON.stringify(currentOrder));
    }
}

// ============================================================
// BACKGROUND MANAGEMENT (auto-save, no confirmation for theme changes)
// ============================================================

let userBackgrounds = [];

const SOLID_COLORS = [
    { value: 'suit-grey', name: 'Suit Grey' },
    { value: 'warm-stone', name: 'Warm Stone' },
    { value: 'sage-mist', name: 'Sage Mist' },
    { value: 'soft-cream', name: 'Soft Cream' }
];

/**
 * Load available background images and populate dropdown
 */
async function loadBackgroundOptions() {
    try {
        const response = await fetch('/api/backgrounds');
        const data = await response.json();
        
        const systemBackgrounds = data.system || [];
        userBackgrounds = data.user || [];
        
        const select = document.getElementById('background-style');
        select.innerHTML = '';
        
        // Add solid colors
        const solidGroup = document.createElement('optgroup');
        solidGroup.label = 'Solid Colors';
        SOLID_COLORS.forEach(color => {
            const option = document.createElement('option');
            option.value = color.value;
            option.textContent = color.name;
            solidGroup.appendChild(option);
        });
        select.appendChild(solidGroup);
        
        // Add system backgrounds
        if (systemBackgrounds.length > 0) {
            const systemGroup = document.createElement('optgroup');
            systemGroup.label = 'System Backgrounds';
            systemBackgrounds.forEach(bg => {
                const displayName = bg.replace(/\.[^/.]+$/, '').replace(/-/g, ' ')
                    .replace(/\b\w/g, l => l.toUpperCase());
                const option = document.createElement('option');
                option.value = 'system:' + bg;
                option.textContent = displayName;
                systemGroup.appendChild(option);
            });
            select.appendChild(systemGroup);
        }
        
        // Add user backgrounds
        if (userBackgrounds.length > 0) {
            const userGroup = document.createElement('optgroup');
            userGroup.label = 'My Backgrounds';
            userBackgrounds.forEach(bg => {
                const displayName = bg.replace(/\.[^/.]+$/, '').replace(/-/g, ' ')
                    .replace(/\b\w/g, l => l.toUpperCase());
                const option = document.createElement('option');
                option.value = 'user:' + bg;
                option.textContent = displayName;
                userGroup.appendChild(option);
            });
            select.appendChild(userGroup);
        }
        
        loadCurrentSettings();
    } catch (error) {
        console.error('Failed to load background options:', error);
        loadCurrentSettings();
    }
}

/**
 * Load current theme settings from localStorage
 */
function loadCurrentSettings() {
    const cardStyle = localStorage.getItem('cardStyle') || 'strait-laced';
    const backgroundStyle = localStorage.getItem('backgroundStyle') || 'suit-grey';
    
    document.getElementById('card-style').value = cardStyle;
    document.getElementById('background-style').value = backgroundStyle;
    
    loadCardPositions();
    updateDeleteButton();
}

/**
 * Show/hide delete button based on whether a user background is selected
 */
function updateDeleteButton() {
    const select = document.getElementById('background-style');
    const deleteBtn = document.getElementById('delete-bg-button');
    
    if (select.value.startsWith('user:')) {
        deleteBtn.classList.add('visible');
    } else {
        deleteBtn.classList.remove('visible');
    }
}

/**
 * Save and apply card style immediately (no message)
 */
function saveAndApplyCardStyle() {
    const cardStyle = document.getElementById('card-style').value;
    localStorage.setItem('cardStyle', cardStyle);
    applyTheme();
}

/**
 * Save and apply background immediately (no message)
 */
function saveAndApplyBackground() {
    const backgroundStyle = document.getElementById('background-style').value;
    localStorage.setItem('backgroundStyle', backgroundStyle);
    applyTheme();
    updateDeleteButton();
}

/**
 * Upload a new background image
 */
async function uploadBackground() {
    const fileInput = document.getElementById('background-upload');
    const file = fileInput.files[0];
    
    if (!file) {
        alert('Please select a file first');
        return;
    }
    
    if (!file.type.startsWith('image/')) {
        alert('Please upload an image file');
        return;
    }
    
    const formData = new FormData();
    formData.append('background', file);
    
    try {
        const response = await fetch('/upload_background', {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        
        if (result.success) {
            const statusDiv = document.getElementById('upload-status');
            statusDiv.textContent = '✓ Background uploaded successfully!';
            statusDiv.style.display = 'block';
            
            fileInput.value = '';
            document.getElementById('upload-filename').textContent = '';
            document.getElementById('upload-button').classList.add('hidden');
            
            await loadBackgroundOptions();
            document.getElementById('background-style').value = 'user:' + result.filename;
            saveAndApplyBackground();
            
            setTimeout(() => statusDiv.style.display = 'none', 3000);
        } else {
            alert('Upload failed: ' + result.error);
        }
    } catch (error) {
        alert('Upload failed: ' + error.message);
    }
}

/**
 * Delete a user-uploaded background
 */
async function deleteBackground() {
    const select = document.getElementById('background-style');
    const selectedValue = select.value;
    
    if (!selectedValue.startsWith('user:')) {
        alert('Can only delete user-uploaded backgrounds');
        return;
    }
    
    const filename = selectedValue.replace('user:', '');
    
    showConfirmModal('Delete Background', `Delete background "${filename}"?`, async function() {
        try {
            const response = await fetch('/delete_background', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filename: filename })
            });
            
            const result = await response.json();
            
            if (result.success) {
                const statusDiv = document.getElementById('upload-status');
                statusDiv.textContent = '✓ Background deleted successfully!';
                statusDiv.style.display = 'block';
                
                const backgroundStyle = localStorage.getItem('backgroundStyle');
                if (backgroundStyle === selectedValue) {
                    localStorage.setItem('backgroundStyle', 'suit-grey');
                    applyTheme();
                }
                
                await loadBackgroundOptions();
                setTimeout(() => statusDiv.style.display = 'none', 3000);
            } else {
                alert('Delete failed: ' + result.error);
            }
        } catch (error) {
            console.error('Delete error:', error);
            alert('Delete failed: ' + error.message);
        }
    });
}

// ============================================================
// TIME FORMAT (auto-save with confirmation)
// ============================================================

/**
 * Load time format setting from server
 */
function loadTimeFormat() {
    fetch('/api/time_format')
        .then(response => response.json())
        .then(data => {
            const timeFormat = document.getElementById('time-format');
            if (timeFormat) {
                timeFormat.value = data.time_format || '12h';
            }
        });
}

/**
 * Save time format setting to server (auto-save with confirmation)
 */
async function saveTimeFormat() {
    try {
        const response = await fetch('/api/time_format', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                time_format: document.getElementById('time-format').value
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            showSectionStatus('time-format-status');
        }
    } catch (error) {
        console.error('Failed to save time format:', error);
    }
}

// ============================================================
// PRACTICE INFORMATION (manual save with confirmation)
// ============================================================

/**
 * Load practice information from database
 */
async function loadPracticeInfo() {
    try {
        const response = await fetch('/api/practice_info');
        const data = await response.json();
        
        if (data.success && data.info) {
            document.getElementById('practice-name').value = data.info.practice_name || '';
            document.getElementById('therapist-name').value = data.info.therapist_name || '';
            document.getElementById('credentials').value = data.info.credentials || '';
            document.getElementById('practice-email').value = data.info.email || '';
            document.getElementById('practice-phone').value = data.info.phone || '';
            document.getElementById('practice-address').value = data.info.address || '';
            document.getElementById('website').value = data.info.website || '';
            document.getElementById('consultation-base').value = parseFloat(data.info.consultation_base_price || 0).toFixed(2);
            document.getElementById('consultation-tax').value = parseFloat(data.info.consultation_tax_rate || 0).toFixed(2);
            document.getElementById('consultation-total').value = parseFloat(data.info.consultation_fee || 0).toFixed(2);
            document.getElementById('consultation-duration').value = data.info.consultation_duration || '20';
            
            updateLogoSignatureUI(data.info);
        }
    } catch (error) {
        console.error('Failed to load practice info:', error);
    }
}

/**
 * Update logo and signature UI based on current state
 * @param {Object} info - Practice info object
 */
function updateLogoSignatureUI(info) {
    const logoChooseBtn = document.getElementById('logo-choose-button');
    const sigChooseBtn = document.getElementById('signature-choose-button');
    const logoPreviewContainer = document.getElementById('logo-preview-container');
    const logoPreview = document.getElementById('logo-preview');
    const sigPreviewContainer = document.getElementById('signature-preview-container');
    const sigPreview = document.getElementById('signature-preview');
    
    if (info.logo_filename) {
        document.getElementById('logo-current').innerHTML = 
            '<i data-lucide="check-circle" style="width: 16px; height: 16px; vertical-align: -3px; color: #0E5346;"></i> Logo uploaded';
        lucide.createIcons();
        document.getElementById('logo-delete-button').classList.add('visible');
        if (logoChooseBtn) logoChooseBtn.classList.add('hidden');
        // Show preview
        if (logoPreviewContainer && logoPreview) {
            logoPreview.src = '/view_logo?' + new Date().getTime(); // Cache bust
            logoPreviewContainer.style.display = 'block';
        }
    } else {
        document.getElementById('logo-current').textContent = '';
        document.getElementById('logo-delete-button').classList.remove('visible');
        if (logoChooseBtn) logoChooseBtn.classList.remove('hidden');
        // Hide preview
        if (logoPreviewContainer) logoPreviewContainer.style.display = 'none';
    }
    
    if (info.signature_filename) {
        document.getElementById('signature-current').innerHTML = 
            '<i data-lucide="check-circle" style="width: 16px; height: 16px; vertical-align: -3px; color: #0E5346;"></i> Signature uploaded';
        lucide.createIcons();
        document.getElementById('signature-delete-button').classList.add('visible');
        if (sigChooseBtn) sigChooseBtn.classList.add('hidden');
        // Show preview
        if (sigPreviewContainer && sigPreview) {
            sigPreview.src = '/view_signature?' + new Date().getTime(); // Cache bust
            sigPreviewContainer.style.display = 'block';
        }
    } else {
        document.getElementById('signature-current').textContent = '';
        document.getElementById('signature-delete-button').classList.remove('visible');
        if (sigChooseBtn) sigChooseBtn.classList.remove('hidden');
        // Hide preview
        if (sigPreviewContainer) sigPreviewContainer.style.display = 'none';
    }
}

/**
 * Save practice information to database (manual save with confirmation)
 */
async function savePracticeInfo() {
    // Validate phone
    const practicePhone = document.getElementById('practice-phone').value;
    if (practicePhone && !validatePhone(practicePhone)) {
        alert('Practice phone must be 10-15 digits');
        document.getElementById('practice-phone').style.borderColor = '#e53e3e';
        return;
    }
    document.getElementById('practice-phone').style.borderColor = '';
    
    const practiceData = {
        practice_name: document.getElementById('practice-name').value,
        therapist_name: document.getElementById('therapist-name').value,
        credentials: document.getElementById('credentials').value,
        email: document.getElementById('practice-email').value,
        phone: document.getElementById('practice-phone').value,
        address: document.getElementById('practice-address').value,
        website: document.getElementById('website').value,
        consultation_base_price: document.getElementById('consultation-base').value,
        consultation_tax_rate: document.getElementById('consultation-tax').value,
        consultation_fee: document.getElementById('consultation-total').value,
        consultation_duration: document.getElementById('consultation-duration').value
    };
    
    try {
        const response = await fetch('/api/practice_info', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(practiceData)
        });
        
        const result = await response.json();
        
        if (result.success) {
            showSectionStatus('practice-info-status');
        } else {
            alert('Failed to save practice information');
        }
    } catch (error) {
        alert('Failed to save practice information: ' + error.message);
    }
}

// ============================================================
// PHONE NUMBER FORMATTING
// ============================================================

/**
 * Format phone number as user types (supports NA and international)
 * @param {Event} e - Input event
 */
function formatPhoneNumber(e) {
    let rawValue = e.target.value;
    
    // International format with + - don't format, just limit length
    if (rawValue.startsWith('+')) {
        let cleaned = '+' + rawValue.slice(1).replace(/\D/g, '');
        e.target.value = cleaned.substring(0, 21);
        return;
    }
    
    // Remove all non-digit characters
    let cleaned = rawValue.replace(/\D/g, '');
    
    // Limit to 12 digits (international support)
    cleaned = cleaned.substring(0, 12);
    
    // Only format if exactly 10 digits (North American format)
    if (cleaned.length === 10) {
        e.target.value = '(' + cleaned.substring(0, 3) + ') ' + cleaned.substring(3, 6) + '-' + cleaned.substring(6, 10);
    } else {
        // For 11-12 digits or incomplete, just return digits as-is
        e.target.value = cleaned;
    }
}

/**
 * Validate phone number has correct digit count
 * @param {string} phoneValue - Phone number to validate
 * @returns {boolean} True if valid
 */
function validatePhone(phoneValue) {
    if (!phoneValue) return true;
    
    if (phoneValue.startsWith('+')) {
        const digitsOnly = phoneValue.slice(1).replace(/\D/g, '');
        return digitsOnly.length >= 10 && digitsOnly.length <= 20;
    }
    
    const digitsOnly = phoneValue.replace(/\D/g, '');
    return digitsOnly.length >= 10 && digitsOnly.length <= 15;
}

// ============================================================
// CONSULTATION FEE CALCULATION
// ============================================================

/**
 * Three-way calculation for consultation fee
 * @param {string} changedField - Which field was changed ('base', 'tax', or 'total')
 */
function calculateConsultationFee(changedField) {
    const baseInput = document.getElementById('consultation-base');
    const taxInput = document.getElementById('consultation-tax');
    const totalInput = document.getElementById('consultation-total');
    
    const base = parseFloat(baseInput.value) || 0;
    const taxRate = parseFloat(taxInput.value) || 0;
    const total = parseFloat(totalInput.value) || 0;
    
    if (changedField === 'base' || changedField === 'tax') {
        const calculatedTotal = base * (1 + taxRate / 100);
        totalInput.value = calculatedTotal.toFixed(2);
    } else if (changedField === 'total') {
        if (taxRate > 0) {
            const calculatedBase = total / (1 + taxRate / 100);
            baseInput.value = calculatedBase.toFixed(2);
        } else {
            baseInput.value = total.toFixed(2);
        }
    }
}

/**
 * Format fee field to 2 decimal places on blur
 * @param {Event} e - Blur event
 */
function formatFeeField(e) {
    let value = parseFloat(e.target.value);
    if (!isNaN(value)) {
        e.target.value = value.toFixed(2);
    }
}

/**
 * Format tax rate field to 1 decimal place on blur
 * @param {Event} e - Blur event
 */
function formatTaxField(e) {
    let value = parseFloat(e.target.value);
    if (!isNaN(value)) {
        e.target.value = value.toFixed(1);
    }
}

// ============================================================
// LOGO AND SIGNATURE UPLOADS
// ============================================================

/**
 * Upload practice logo
 */
async function uploadLogo() {
    const fileInput = document.getElementById('logo-upload');
    const file = fileInput.files[0];
    
    if (!file) return;
    
    if (!file.type.startsWith('image/')) {
        alert('Please upload an image file');
        fileInput.value = '';
        return;
    }
    
    const formData = new FormData();
    formData.append('logo', file);
    
    try {
        const response = await fetch('/upload_logo', { method: 'POST', body: formData });
        const result = await response.json();
        
        if (result.success) {
            document.getElementById('logo-current').innerHTML = 
                '<i data-lucide="check-circle" style="width: 16px; height: 16px; vertical-align: -3px; color: #0E5346;"></i> Logo uploaded';
            lucide.createIcons();
            document.getElementById('logo-delete-button').classList.add('visible');
            document.getElementById('logo-choose-button').classList.add('hidden');
            fileInput.value = '';
            // Show preview
            const previewContainer = document.getElementById('logo-preview-container');
            const preview = document.getElementById('logo-preview');
            if (previewContainer && preview) {
                preview.src = '/view_logo?' + new Date().getTime();
                previewContainer.style.display = 'block';
            }
        } else {
            alert('Upload failed: ' + result.error);
        }
    } catch (error) {
        alert('Upload failed: ' + error.message);
    }
}

/**
 * Upload digital signature
 */
async function uploadSignature() {
    const fileInput = document.getElementById('signature-upload');
    const file = fileInput.files[0];
    
    if (!file) return;
    
    if (!file.type.startsWith('image/')) {
        alert('Please upload an image file');
        fileInput.value = '';
        return;
    }
    
    const formData = new FormData();
    formData.append('signature', file);
    
    try {
        const response = await fetch('/upload_signature', { method: 'POST', body: formData });
        const result = await response.json();
        
        if (result.success) {
            document.getElementById('signature-current').innerHTML = 
                '<i data-lucide="check-circle" style="width: 16px; height: 16px; vertical-align: -3px; color: #0E5346;"></i> Signature uploaded';
            lucide.createIcons();
            document.getElementById('signature-delete-button').classList.add('visible');
            document.getElementById('signature-choose-button').classList.add('hidden');
            fileInput.value = '';
            // Show preview
            const previewContainer = document.getElementById('signature-preview-container');
            const preview = document.getElementById('signature-preview');
            if (previewContainer && preview) {
                preview.src = '/view_signature?' + new Date().getTime();
                previewContainer.style.display = 'block';
            }
        } else {
            alert('Upload failed: ' + result.error);
        }
    } catch (error) {
        alert('Upload failed: ' + error.message);
    }
}

/**
 * Delete practice logo
 */
async function deleteLogo() {
    showConfirmModal('Delete Logo', 'Delete practice logo?', async function() {
        try {
            const response = await fetch('/delete_logo', { method: 'POST' });
            const result = await response.json();
            
            if (result.success) {
                document.getElementById('logo-current').textContent = '';
                document.getElementById('logo-delete-button').classList.remove('visible');
                document.getElementById('logo-choose-button').classList.remove('hidden');
                // Hide preview
                const previewContainer = document.getElementById('logo-preview-container');
                if (previewContainer) previewContainer.style.display = 'none';
                showSectionStatus('statement-status', '✓ Logo deleted!');
            } else {
                alert('Delete failed: ' + result.error);
            }
        } catch (error) {
            console.error('Delete error:', error);
            alert('Delete failed: ' + error.message);
        }
    });
}

/**
 * Delete digital signature
 */
async function deleteSignature() {
    showConfirmModal('Delete Signature', 'Delete digital signature?', async function() {
        try {
            const response = await fetch('/delete_signature', { method: 'POST' });
            const result = await response.json();
            
            if (result.success) {
                document.getElementById('signature-current').textContent = '';
                document.getElementById('signature-delete-button').classList.remove('visible');
                document.getElementById('signature-choose-button').classList.remove('hidden');
                // Hide preview
                const previewContainer = document.getElementById('signature-preview-container');
                if (previewContainer) previewContainer.style.display = 'none';
                showSectionStatus('statement-status', '✓ Signature deleted!');
            } else {
                alert('Delete failed: ' + result.error);
            }
        } catch (error) {
            console.error('Delete error:', error);
            alert('Delete failed: ' + error.message);
        }
    });
}

// ============================================================
// FILE NUMBER SETTINGS (auto-save with confirmation)
// ============================================================

/**
 * Handle file number format dropdown change
 * - Auto-saves for manual and date-initials (clear, immediate actions)
 * - Just shows options panel for prefix-counter (user fills in, then clicks Save)
 */
function handleFileNumberFormatChange() {
    const format = document.getElementById('file-number-format').value;
    
    // Toggle the options visibility
    toggleFileNumberFields();
    
    // Auto-save for simple formats (no text input needed)
    if (format !== 'prefix-counter') {
        const settings = {
            format: format,
            prefix: '',
            suffix: '',
            counter: 1
        };
        
        fetch('/settings/file-number', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showSectionStatus('file-number-format-status');
            }
        })
        .catch(error => console.error('Error saving file number settings:', error));
    }
    // For prefix-counter, user will click Save button after filling in fields
}

/**
 * Toggle visibility of prefix-counter options based on format selection
 */
function toggleFileNumberFields() {
    const format = document.getElementById('file-number-format').value;
    const options = document.getElementById('prefix-counter-options');
    
    if (format === 'prefix-counter') {
        options.style.display = 'block';
        updateFileNumberPreview();
    } else {
        options.style.display = 'none';
    }
}

/**
 * Update file number preview based on current settings
 */
function updateFileNumberPreview() {
    const prefix = document.getElementById('file-number-prefix').value || '';
    const suffix = document.getElementById('file-number-suffix').value || '';
    const start = document.getElementById('file-number-start').value || '1';
    
    const paddedNumber = start.toString().padStart(4, '0');
    
    let preview = '';
    if (prefix) preview += prefix + '-';
    preview += paddedNumber;
    if (suffix) preview += '-' + suffix;
    
    const previewEl = document.getElementById('file-number-preview');
    previewEl.textContent = preview;
    
    // Warn if too long
    if (preview.length > 12) {
        previewEl.style.borderColor = '#B91C1C';
        previewEl.style.color = '#B91C1C';
    } else {
        previewEl.style.borderColor = '#DEE2E6';
        previewEl.style.color = '#111827';
    }
}

/**
 * Load file number settings from server
 */
function loadFileNumberSettings() {
    fetch('/settings/file-number')
        .then(response => response.json())
        .then(data => {
            if (data.format) {
                document.getElementById('file-number-format').value = data.format;
                toggleFileNumberFields();
                
                if (data.format === 'prefix-counter') {
                    document.getElementById('file-number-prefix').value = data.prefix || '';
                    document.getElementById('file-number-suffix').value = data.suffix || '';
                    document.getElementById('file-number-start').value = data.counter || 1;
                    updateFileNumberPreview();
                }
            }
        })
        .catch(error => console.error('Error loading file number settings:', error));
}

/**
 * Save file number settings to server (called by Save button in prefix-counter panel)
 */
function saveFileNumberSettings() {
    const format = document.getElementById('file-number-format').value;
    
    const settings = {
        format: format,
        prefix: format === 'prefix-counter' ? document.getElementById('file-number-prefix').value : '',
        suffix: format === 'prefix-counter' ? document.getElementById('file-number-suffix').value : '',
        counter: format === 'prefix-counter' ? parseInt(document.getElementById('file-number-start').value) : 1
    };
    
    fetch('/settings/file-number', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showSectionStatus('file-number-status');
        }
    })
    .catch(error => console.error('Error saving file number settings:', error));
}

// ============================================================
// CALENDAR SETTINGS (auto-save with confirmation)
// ============================================================

/**
 * Toggle calendar name field visibility based on method
 */
function toggleCalendarNameField() {
    const method = document.getElementById('calendar_method').value;
    const nameGroup = document.getElementById('calendar-name-group');
    nameGroup.style.display = method === 'applescript' ? 'block' : 'none';
}

/**
 * Load calendar settings from server
 */
function loadCalendarSettings() {
    const calendarMethod = document.getElementById('calendar_method');
    const calendarNameGroup = document.getElementById('calendar-name-group');
    const calendarName = document.getElementById('calendar_name');
    
    if (!calendarMethod) return;
    
    fetch('/api/calendar_settings')
        .then(response => response.json())
        .then(data => {
            if (data.calendar_method) {
                calendarMethod.value = data.calendar_method;
                calendarNameGroup.style.display = data.calendar_method === 'applescript' ? 'block' : 'none';
            }
            if (data.calendar_name) {
                calendarName.value = data.calendar_name;
            }
        });
}

/**
 * Save calendar settings to server (auto-save with confirmation)
 */
async function saveCalendarSettings() {
    toggleCalendarNameField();
    
    try {
        const response = await fetch('/api/calendar_settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                calendar_method: document.getElementById('calendar_method').value,
                calendar_name: document.getElementById('calendar_name').value
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            showSectionStatus('calendar-status');
        }
    } catch (error) {
        console.error('Failed to save calendar settings:', error);
    }
}

// ============================================================
// SECURITY SETTINGS (auto-save with confirmation)
// ============================================================

/**
 * Load security settings from server
 */
function loadSecuritySettings() {
    fetch('/api/security_settings')
        .then(response => response.json())
        .then(data => {
            const timeout = document.getElementById('session_timeout');
            if (timeout) {
                timeout.value = data.session_timeout || '30';
            }
        });
}

/**
 * Save security settings to server (auto-save with confirmation)
 */
async function saveSecuritySettings() {
    try {
        const response = await fetch('/api/security_settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_timeout: document.getElementById('session_timeout').value
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            showSectionStatus('security-status');
        }
    } catch (error) {
        console.error('Failed to save security settings:', error);
    }
}

// ============================================================
// STATEMENT SETTINGS (manual save with confirmation)
// ============================================================

/**
 * Toggle attestation text field visibility
 */
function toggleAttestationText() {
    const checkbox = document.getElementById('include_attestation');
    const textGroup = document.getElementById('attestation-text-group');
    textGroup.style.display = checkbox.checked ? 'block' : 'none';
}

/**
 * Toggle email from field visibility based on email method
 */
function toggleEmailFromField() {
    const method = document.getElementById('email_method').value;
    const emailFromGroup = document.getElementById('email-from-group');
    if (emailFromGroup) {
        emailFromGroup.style.display = method === 'applescript' ? 'block' : 'none';
    }
}

/**
 * Load statement settings from server
 */
function loadStatementSettings() {
    const currencyField = document.getElementById('currency');
    if (!currencyField) return;
    
    fetch('/api/statement_settings')
        .then(response => response.json())
        .then(data => {
            if (data.currency) document.getElementById('currency').value = data.currency;
            if (data.registration_info) document.getElementById('registration_info').value = data.registration_info;
            if (data.payment_instructions) document.getElementById('payment_instructions').value = data.payment_instructions;
            if (data.email_from_address) document.getElementById('email_from').value = data.email_from_address;
            if (data.statement_email_body) document.getElementById('statement_email_body').value = data.statement_email_body;
            if (data.email_method) document.getElementById('email_method').value = data.email_method;
            toggleEmailFromField();
            
            const attestationCheckbox = document.getElementById('include_attestation');
            attestationCheckbox.checked = data.include_attestation === true || data.include_attestation === 'true';
            toggleAttestationText();
            
            if (data.attestation_text) document.getElementById('attestation_text').value = data.attestation_text;
        });
}

/**
 * Save statement settings to server (manual save with confirmation)
 */
async function saveStatementSettings() {
    try {
        const response = await fetch('/api/statement_settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                currency: document.getElementById('currency').value,
                registration_info: document.getElementById('registration_info').value,
                payment_instructions: document.getElementById('payment_instructions').value,
                include_attestation: document.getElementById('include_attestation').checked,
                attestation_text: document.getElementById('attestation_text').value,
                email_method: document.getElementById('email_method').value,
                email_from_address: document.getElementById('email_from').value,
                statement_email_body: document.getElementById('statement_email_body').value
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            showSectionStatus('statement-status');
        } else {
            alert('Failed to save statement settings');
        }
    } catch (error) {
        alert('Failed to save statement settings: ' + error.message);
    }
}

// ============================================================
// AI SCRIBE SETTINGS
// ============================================================

/**
 * Load AI Scribe status and update UI
 */
async function loadAIStatus() {
    try {
        // Check system capability
        const capResp = await fetch('/api/ai/capability');
        const capData = await capResp.json();
        
        const capStatus = document.getElementById('ai-capability-status');
        if (capStatus) {
            if (capData.capable) {
                capStatus.innerHTML = `<p style="color: #0E5346; font-size: 0.875rem;"><i data-lucide="cpu" style="width: 14px; height: 14px; vertical-align: -2px; margin-right: 0.25rem;"></i>${capData.message}</p>`;
            } else {
                capStatus.innerHTML = `<p style="color: #991B1B; font-size: 0.875rem;"><i data-lucide="alert-circle" style="width: 14px; height: 14px; vertical-align: -2px; margin-right: 0.25rem;"></i>${capData.message}</p>`;
            }
        }
        
        // Check model status
        const statusResp = await fetch('/api/ai/status');
        const statusData = await statusResp.json();
        
        const notDownloaded = document.getElementById('ai-not-downloaded');
        const downloaded = document.getElementById('ai-downloaded');
        
        if (statusData.downloaded) {
            notDownloaded.style.display = 'none';
            downloaded.style.display = 'block';
            
            const modelInfo = document.getElementById('ai-model-info');
            if (modelInfo && statusData.size_gb) {
                modelInfo.textContent = `${statusData.name} is installed (${statusData.size_gb}GB)`;
            }
            
            const modelStatus = document.getElementById('ai-model-status');
            if (modelStatus) {
                if (statusData.loaded) {
                    modelStatus.innerHTML = '<p style="color: #0369A1; font-size: 0.875rem;"><i data-lucide="zap" style="width: 14px; height: 14px; vertical-align: -2px; margin-right: 0.25rem;"></i>Model is loaded in memory (ready to use)</p>';
                } else {
                    modelStatus.innerHTML = '<p style="color: #6B7280; font-size: 0.875rem;"><i data-lucide="moon" style="width: 14px; height: 14px; vertical-align: -2px; margin-right: 0.25rem;"></i>Model is not loaded (will load automatically when needed)</p>';
                }
            }
        } else {
            notDownloaded.style.display = 'block';
            downloaded.style.display = 'none';
        }
        
        // Refresh Lucide icons
        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }
    } catch (error) {
        console.error('Error loading AI status:', error);
    }
}

/**
 * Download the AI model with progress tracking
 */
async function downloadAIModel() {
    const btn = document.getElementById('ai-download-btn');
    const progress = document.getElementById('ai-download-progress');
    const statusText = document.getElementById('ai-download-status');
    const progressBar = document.getElementById('ai-download-bar');
    const sizeText = document.getElementById('ai-download-size');
    
    btn.disabled = true;
    progress.style.display = 'block';
    statusText.textContent = 'Starting download...';
    progressBar.style.width = '0%';
    sizeText.textContent = '';
    
    try {
        const response = await fetch('/api/ai/download', { method: 'POST' });
        
        if (!response.ok) {
            throw new Error('Download request failed');
        }
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let totalSize = null;
        
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            buffer += decoder.decode(value, { stream: true });
            
            // Process complete SSE messages
            const lines = buffer.split('\n\n');
            buffer = lines.pop() || '';  // Keep incomplete message in buffer
            
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.substring(6));
                        
                        if (data.status === 'checking') {
                            statusText.textContent = data.message;
                        } else if (data.status === 'downloading') {
                            statusText.textContent = 'Downloading Hermes 3...';
                            if (data.total) {
                                totalSize = data.total;
                            }
                        } else if (data.status === 'progress') {
                            const downloaded = data.downloaded || 0;
                            const total = data.total || totalSize;
                            
                            if (total) {
                                const percent = Math.min(100, (downloaded / total) * 100);
                                progressBar.style.width = percent.toFixed(1) + '%';
                                const downloadedMB = (downloaded / (1024 * 1024)).toFixed(0);
                                const totalMB = (total / (1024 * 1024)).toFixed(0);
                                sizeText.textContent = `${downloadedMB} MB / ${totalMB} MB (${percent.toFixed(0)}%)`;
                            } else {
                                // Unknown total - just show downloaded size
                                const downloadedMB = (downloaded / (1024 * 1024)).toFixed(0);
                                sizeText.textContent = `${downloadedMB} MB downloaded...`;
                            }
                        } else if (data.status === 'complete') {
                            progressBar.style.width = '100%';
                            statusText.textContent = 'Download complete!';
                            sizeText.textContent = '';
                            // Reload status to update UI
                            setTimeout(() => loadAIStatus(), 500);
                        } else if (data.status === 'error') {
                            throw new Error(data.message || 'Download failed');
                        }
                    } catch (parseError) {
                        console.error('Failed to parse SSE data:', parseError);
                    }
                }
            }
        }
    } catch (error) {
        statusText.textContent = 'Download failed: ' + error.message;
        sizeText.textContent = 'You can try again or check your internet connection.';
        btn.disabled = false;
    }
}

/**
 * Unload AI model from memory
 */
async function unloadAIModel() {
    try {
        const response = await fetch('/api/ai/unload', { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            loadAIStatus();
        }
    } catch (error) {
        alert('Failed to unload model: ' + error.message);
    }
}

/**
 * Delete the AI model
 */
async function deleteAIModel() {
    if (!confirm('Are you sure you want to delete the AI model? You will need to download it again to use AI Scribe.')) {
        return;
    }
    
    try {
        const response = await fetch('/api/ai/delete', { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            loadAIStatus();
        } else {
            throw new Error(data.error || 'Delete failed');
        }
    } catch (error) {
        alert('Failed to delete model: ' + error.message);
    }
}

// ============================================================
// EVENT LISTENERS
// ============================================================

document.addEventListener('DOMContentLoaded', function() {
    // Load all settings
    loadBackgroundOptions();
    loadPracticeInfo();
    loadFileNumberSettings();
    loadSecuritySettings();
    loadCalendarSettings();
    loadStatementSettings();
    loadTimeFormat();
    loadAIStatus();
    
    // Phone formatting
    const phoneInput = document.getElementById('practice-phone');
    if (phoneInput) {
        phoneInput.addEventListener('input', formatPhoneNumber);
    }
    
    // Fee field formatting
    document.getElementById('consultation-base')?.addEventListener('blur', formatFeeField);
    document.getElementById('consultation-total')?.addEventListener('blur', formatFeeField);
    document.getElementById('consultation-tax')?.addEventListener('blur', formatTaxField);
    
    // File number preview updates
    document.getElementById('file-number-prefix')?.addEventListener('input', updateFileNumberPreview);
    document.getElementById('file-number-suffix')?.addEventListener('input', updateFileNumberPreview);
    document.getElementById('file-number-start')?.addEventListener('input', updateFileNumberPreview);
    
    // Background upload filename display
    document.getElementById('background-upload')?.addEventListener('change', function(e) {
        const filename = e.target.files[0]?.name;
        if (filename) {
            document.getElementById('upload-filename').textContent = filename;
            document.getElementById('upload-button').classList.remove('hidden');
        }
    });
});
