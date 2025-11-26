// Settings page JavaScript - EdgeCase Equalizer

// Load current settings on page load
function loadCurrentSettings() {
    const cardStyle = localStorage.getItem('cardStyle') || 'strait-laced';
    const backgroundStyle = localStorage.getItem('backgroundStyle') || 'suit-grey';
    
    document.getElementById('card-style').value = cardStyle;
    document.getElementById('background-style').value = backgroundStyle;
    
    // Load card positions
    loadCardPositions();
    
    // Update delete button visibility
    updateDeleteButton();
}

// Confirmation modal helpers
let confirmCallback = null;

function showConfirmModal(title, message, onConfirm) {
    console.log('showConfirmModal called with:', title, message);
    document.getElementById('confirm-title').textContent = title;
    document.getElementById('confirm-message').textContent = message;
    document.getElementById('confirm-modal').style.display = 'flex';
    
    confirmCallback = onConfirm;
    console.log('confirmCallback set:', typeof confirmCallback);
    
    // Set up the OK button click handler
    const okButton = document.getElementById('confirm-ok-button');
    console.log('OK button found:', okButton);
    okButton.onclick = function() {
        console.log('OK button clicked! Callback type:', typeof confirmCallback);
        
        // Save the callback BEFORE closing (which nulls it)
        const callback = confirmCallback;
        closeConfirmModal();
        
        if (callback) {
            console.log('Executing callback...');
            callback();
        } else {
            console.log('No callback to execute!');
        }
    };
}

function closeConfirmModal() {
    document.getElementById('confirm-modal').style.display = 'none';
    confirmCallback = null;
}

// Card layout management
const cardNames = {
    'active-clients': 'Active Clients',
    'sessions-week': 'Sessions This Week',
    'pending-invoices': 'Pending Invoices',
    'billable-month': 'Billable This Month',
    'current-time': 'Current Time',
    'navigation': 'Navigation'
};

// Load card positions from localStorage
function loadCardPositions() {
    const savedOrder = localStorage.getItem('cardOrder');
    let currentOrder;
    
    if (savedOrder) {
        currentOrder = JSON.parse(savedOrder);
    } else {
        // Default order
        currentOrder = ['active-clients', 'sessions-week', 'pending-invoices', 
                       'billable-month', 'current-time', 'navigation'];
    }
    
    // Set dropdown values
    for (let i = 0; i < 6; i++) {
        const select = document.getElementById(`position-${i + 1}`);
        if (select) {
            select.value = currentOrder[i];
        }
    }
    
    return currentOrder;
}

// Handle card swap when dropdown changes
function handleCardSwap(position) {
    const select = document.getElementById(`position-${position + 1}`);
    const newCardId = select.value;
    
    // Get the SAVED order from localStorage (the truth)
    const savedOrder = localStorage.getItem('cardOrder');
    let currentOrder;
    
    if (savedOrder) {
        currentOrder = JSON.parse(savedOrder);
    } else {
        // Default order
        currentOrder = ['active-clients', 'sessions-week', 'pending-invoices', 
                       'billable-month', 'current-time', 'navigation'];
    }
    
    // What card WAS in this position?
    const oldCardId = currentOrder[position];
    
    // Where is the newCardId currently?
    const existingPosition = currentOrder.indexOf(newCardId);
    
    if (existingPosition !== -1 && existingPosition !== position) {
        // Swap them in the array
        currentOrder[position] = newCardId;
        currentOrder[existingPosition] = oldCardId;
        
        // Update all dropdowns to reflect the swap
        for (let i = 0; i < 6; i++) {
            document.getElementById(`position-${i + 1}`).value = currentOrder[i];
        }
        
        // Save to localStorage
        localStorage.setItem('cardOrder', JSON.stringify(currentOrder));
        
        // Show success message briefly
        const successMsg = document.getElementById('success-message');
        successMsg.textContent = '✓ Card positions updated! Changes will appear on the main page.';
        successMsg.classList.add('show');
        setTimeout(() => {
            successMsg.classList.remove('show');
            successMsg.textContent = '✓ Settings saved successfully!';
        }, 2000);
    }
}

// Track which backgrounds are user-uploaded
let userBackgrounds = [];

// Load available background images
async function loadBackgroundOptions() {
    try {
        const response = await fetch('/api/backgrounds');
        const data = await response.json();
        
        // Separate system and user backgrounds
        const systemBackgrounds = data.system || [];
        userBackgrounds = data.user || [];
        
        const select = document.getElementById('background-style');
        
        // Clear all existing options
        select.innerHTML = '';
        
        // Add solid color options
        const solidColors = [
            { value: 'suit-grey', name: 'Suit Grey' },
            { value: 'warm-stone', name: 'Warm Stone' },
            { value: 'sage-mist', name: 'Sage Mist' },
            { value: 'soft-cream', name: 'Soft Cream' }
        ];
        
        const solidGroup = document.createElement('optgroup');
        solidGroup.label = 'Solid Colors';
        solidColors.forEach(color => {
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
                const displayName = bg.replace(/\.[^/.]+$/, '').replace(/-/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
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
                const displayName = bg.replace(/\.[^/.]+$/, '').replace(/-/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
                const option = document.createElement('option');
                option.value = 'user:' + bg;
                option.textContent = displayName;
                userGroup.appendChild(option);
            });
            select.appendChild(userGroup);
        }
        
        // Load current settings after options are populated
        loadCurrentSettings();
    } catch (error) {
        console.error('Failed to load background options:', error);
        loadCurrentSettings();
    }
}

// Show/hide delete button based on selection
function updateDeleteButton() {
    const select = document.getElementById('background-style');
    const deleteBtn = document.getElementById('delete-bg-button');
    
    // Show delete button only for user backgrounds
    if (select.value.startsWith('user:')) {
        deleteBtn.classList.add('visible');
    } else {
        deleteBtn.classList.remove('visible');
    }
}

// Delete user background
async function deleteBackground() {
    console.log('deleteBackground called');
    const select = document.getElementById('background-style');
    const selectedValue = select.value;
    
    console.log('Selected value:', selectedValue);
    
    if (!selectedValue.startsWith('user:')) {
        alert('Can only delete user-uploaded backgrounds');
        return;
    }
    
    const filename = selectedValue.replace('user:', '');
    console.log('Filename to delete:', filename);
    
    showConfirmModal('Delete Background', `Delete background "${filename}"?`, async function() {
        console.log('Delete confirmed, making API call');
        try {
            const response = await fetch('/delete_background', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ filename: filename })
            });
            
            console.log('Response received:', response);
            const result = await response.json();
            console.log('Result:', result);
            
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
                
                setTimeout(() => {
                    statusDiv.style.display = 'none';
                }, 3000);
            } else {
                alert('Delete failed: ' + result.error);
            }
        } catch (error) {
            console.error('Delete error:', error);
            alert('Delete failed: ' + error.message);
        }
    });
}

// Show filename when file is selected
document.getElementById('background-upload').addEventListener('change', function(e) {
    const filename = e.target.files[0]?.name;
    if (filename) {
        document.getElementById('upload-filename').textContent = filename;
        document.getElementById('upload-button').style.display = 'inline-block';
    }
});

// Upload background image
async function uploadBackground() {
    const fileInput = document.getElementById('background-upload');
    const file = fileInput.files[0];
    
    if (!file) {
        alert('Please select a file first');
        return;
    }
    
    // Validate file type
    if (!file.type.startsWith('image/')) {
        alert('Please upload an image file');
        return;
    }
    
    // Create form data
    const formData = new FormData();
    formData.append('background', file);
    
    try {
        const response = await fetch('/upload_background', {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        
        if (result.success) {
            // Show success message
            const statusDiv = document.getElementById('upload-status');
            statusDiv.textContent = '✓ Background uploaded successfully!';
            statusDiv.style.display = 'block';
            
            // Clear the file input
            fileInput.value = '';
            document.getElementById('upload-filename').textContent = '';
            document.getElementById('upload-button').style.display = 'none';
            
            // Reload background options to include the new one
            await loadBackgroundOptions();
            
            // Auto-select the newly uploaded background
            document.getElementById('background-style').value = 'user:' + result.filename;
            
            // Apply the background immediately
            saveAndApplyBackground();
            
            // Hide success message after 3 seconds
            setTimeout(() => {
                statusDiv.style.display = 'none';
            }, 3000);
        } else {
            alert('Upload failed: ' + result.error);
        }
    } catch (error) {
        alert('Upload failed: ' + error.message);
    }
}

// Save settings
async function saveSettings() {
    // Validate phone number FIRST
    const practicePhone = document.getElementById('practice-phone').value;

    if (practicePhone && !validatePhone(practicePhone)) {
        alert('Practice phone must be 10-15 digits');
        document.getElementById('practice-phone').style.borderColor = '#e53e3e';
        return; // Stop here, don't save
    }
    
    // Reset border color
    document.getElementById('practice-phone').style.borderColor = '';
    
    // Save practice info to database
    await savePracticeInfo();
    
    // Save file number settings
    await saveFileNumberSettings();
    
    // Save calendar settings
    await fetch('/api/calendar_settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            calendar_method: document.getElementById('calendar_method').value,
            calendar_name: document.getElementById('calendar_name').value
        })
    });
    
    // Show success message and redirect
    const successMsg = document.getElementById('success-message');
    successMsg.classList.add('show');
    setTimeout(() => {
        successMsg.classList.remove('show');
        // Redirect to main view after saving
        window.location.href = '/';
    }, 1000);
}

// Load practice information from database
async function loadPracticeInfo() {
    try {
        const response = await fetch('/api/practice_info');
        const data = await response.json();
        
        if (data.success && data.info) {
            console.log('Practice info loaded:', data.info);
            // Populate form fields
            document.getElementById('practice-name').value = data.info.practice_name || '';
            document.getElementById('therapist-name').value = data.info.therapist_name || '';
            document.getElementById('credentials').value = data.info.credentials || '';
            document.getElementById('practice-email').value = data.info.email || '';
            document.getElementById('practice-phone').value = data.info.phone || '';
            document.getElementById('practice-address').value = data.info.address || '';  // CHANGED: single address field
            document.getElementById('website').value = data.info.website || '';
            document.getElementById('consultation-base').value = parseFloat(data.info.consultation_base_price || 0).toFixed(2);
            document.getElementById('consultation-tax').value = parseFloat(data.info.consultation_tax_rate || 0).toFixed(2);
            document.getElementById('consultation-total').value = parseFloat(data.info.consultation_fee || 0).toFixed(2);
            document.getElementById('currency').value = data.info.currency || 'CAD';
            document.getElementById('consultation-duration').value = data.info.consultation_duration || '20';
            
            // Show current logo/signature status
            if (data.info.logo_filename) {
                document.getElementById('logo-current').textContent = '✓ ' + data.info.logo_filename;
                document.getElementById('logo-delete-button').style.display = 'inline-block';
            } else {
                document.getElementById('logo-current').textContent = '';
                document.getElementById('logo-delete-button').style.display = 'none';
            }
            
            if (data.info.signature_filename) {
                document.getElementById('signature-current').textContent = '✓ ' + data.info.signature_filename;
                document.getElementById('signature-delete-button').style.display = 'inline-block';
            } else {
                document.getElementById('signature-current').textContent = '';
                document.getElementById('signature-delete-button').style.display = 'none';
            }
        }
    } catch (error) {
        console.error('Failed to load practice info:', error);
    }
}

// Save practice information to database
async function savePracticeInfo() {
    const practiceData = {
        practice_name: document.getElementById('practice-name').value,
        therapist_name: document.getElementById('therapist-name').value,
        credentials: document.getElementById('credentials').value,
        email: document.getElementById('practice-email').value,
        phone: document.getElementById('practice-phone').value,
        address: document.getElementById('practice-address').value,  // CHANGED: single address field
        website: document.getElementById('website').value,
        currency: document.getElementById('currency').value,
        consultation_base_price: document.getElementById('consultation-base').value,
        consultation_tax_rate: document.getElementById('consultation-tax').value,
        consultation_fee: document.getElementById('consultation-total').value,
        consultation_duration: document.getElementById('consultation-duration').value
    };
    
    try {
        const response = await fetch('/api/practice_info', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(practiceData)
        });
        
        const result = await response.json();
        
        if (result.success) {
            // Show success message
            const statusDiv = document.getElementById('practice-info-status');
            statusDiv.textContent = '✓ Practice information saved successfully!';
            statusDiv.style.display = 'block';
            
            // Hide after 3 seconds
            setTimeout(() => {
                statusDiv.style.display = 'none';
            }, 3000);
        } else {
            alert('Failed to save practice information');
        }
    } catch (error) {
        alert('Failed to save practice information: ' + error.message);
    }
}

// Phone number formatting with extension support (up to 5 digits) and international bypass
const practicePhoneInput = document.getElementById('practice-phone');

practicePhoneInput.addEventListener('input', function(e) {
    let rawValue = e.target.value;
    
    // If starts with +, it's international - don't format, just limit length
    if (rawValue.startsWith('+')) {
        // Allow + and up to 20 digits
        let cleaned = '+' + rawValue.slice(1).replace(/\D/g, '');
        e.target.value = cleaned.substring(0, 21); // + plus 20 digits
        return;
    }
    
    let value = rawValue.replace(/\D/g, ''); // Remove non-digits
    
    if (value.length <= 10) {
        // Format as (123) 456-7890
        if (value.length > 6) {
            value = `(${value.slice(0, 3)}) ${value.slice(3, 6)}-${value.slice(6)}`;
        } else if (value.length > 3) {
            value = `(${value.slice(0, 3)}) ${value.slice(3)}`;
        } else if (value.length > 0) {
            value = `(${value}`;
        }
    } else if (value.length <= 15) {
        // Allow up to 15 digits (10 + 5 digit extension)
        value = `(${value.slice(0, 3)}) ${value.slice(3, 6)}-${value.slice(6, 10)} ext ${value.slice(10)}`;
    } else {
        // Truncate at 15 digits
        value = value.slice(0, 15);
        value = `(${value.slice(0, 3)}) ${value.slice(3, 6)}-${value.slice(6, 10)} ext ${value.slice(10)}`;
    }
    
    e.target.value = value;
});

// Validate phone number has 10-15 digits (or international format)
function validatePhone(phoneValue) {
    if (!phoneValue) return true; // Empty is okay
    
    // International format: starts with + and has 10-20 digits after it
    if (phoneValue.startsWith('+')) {
        const digitsOnly = phoneValue.slice(1).replace(/\D/g, '');
        return digitsOnly.length >= 10 && digitsOnly.length <= 20;
    }
    
    // North American format: 10-15 digits
    const digitsOnly = phoneValue.replace(/\D/g, '');
    return digitsOnly.length >= 10 && digitsOnly.length <= 15;
}

// Validate phone number has 10-15 digits
function validatePhone(phoneValue) {
    if (!phoneValue) return true; // Empty is okay
    const digitsOnly = phoneValue.replace(/\D/g, '');
    return digitsOnly.length >= 10 && digitsOnly.length <= 15;
}

// Three-way calculation for consultation fee
function calculateConsultationFee(changedField) {
    const baseInput = document.getElementById('consultation-base');
    const taxInput = document.getElementById('consultation-tax');
    const totalInput = document.getElementById('consultation-total');
    
    const base = parseFloat(baseInput.value) || 0;
    const taxRate = parseFloat(taxInput.value) || 0;
    const total = parseFloat(totalInput.value) || 0;
    
    if (changedField === 'base' || changedField === 'tax') {
        // Calculate total from base + tax
        const calculatedTotal = base * (1 + taxRate / 100);
        totalInput.value = calculatedTotal.toFixed(2);
    } else if (changedField === 'total') {
        // Calculate base from total - tax
        if (taxRate > 0) {
            const calculatedBase = total / (1 + taxRate / 100);
            baseInput.value = calculatedBase.toFixed(2);
        } else {
            // If no tax, total = base
            baseInput.value = total.toFixed(2);
        }
    }
}

// Auto-format consultation fee fields on blur
document.getElementById('consultation-base').addEventListener('blur', function(e) {
    let value = parseFloat(e.target.value);
    if (!isNaN(value)) {
        e.target.value = value.toFixed(2);
    }
});

document.getElementById('consultation-tax').addEventListener('blur', function(e) {
    let value = parseFloat(e.target.value);
    if (!isNaN(value)) {
        e.target.value = value.toFixed(1);
    }
});

document.getElementById('consultation-total').addEventListener('blur', function(e) {
    let value = parseFloat(e.target.value);
    if (!isNaN(value)) {
        e.target.value = value.toFixed(2);
    }
});

// Show filename when logo is selected
document.getElementById('logo-upload').addEventListener('change', function(e) {
    const filename = e.target.files[0]?.name;
    if (filename) {
        document.getElementById('logo-filename').textContent = filename;
        document.getElementById('logo-upload-button').style.display = 'inline-block';
    }
});

// Show filename when signature is selected
document.getElementById('signature-upload').addEventListener('change', function(e) {
    const filename = e.target.files[0]?.name;
    if (filename) {
        document.getElementById('signature-filename').textContent = filename;
        document.getElementById('signature-upload-button').style.display = 'inline-block';
    }
});

// Upload logo
async function uploadLogo() {
    const fileInput = document.getElementById('logo-upload');
    const file = fileInput.files[0];
    
    if (!file) {
        alert('Please select a file first');
        return;
    }
    
    // Validate file type
    if (!file.type.startsWith('image/')) {
        alert('Please upload an image file');
        return;
    }
    
    // Create form data
    const formData = new FormData();
    formData.append('logo', file);
    
    try {
        const response = await fetch('/upload_logo', {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        
        if (result.success) {
            // Show success message
            const statusDiv = document.getElementById('practice-info-status');
            statusDiv.textContent = '✓ Logo uploaded successfully!';
            statusDiv.style.display = 'block';

            // Update display
            document.getElementById('logo-current').textContent = '✓ ' + result.filename;
            document.getElementById('logo-delete-button').style.display = 'inline-block';
            
            // Clear the file input
            fileInput.value = '';
            document.getElementById('logo-filename').textContent = '';
            document.getElementById('logo-upload-button').style.display = 'none';
            
            // Hide success message after 3 seconds
            setTimeout(() => {
                statusDiv.style.display = 'none';
            }, 3000);
        } else {
            alert('Upload failed: ' + result.error);
        }
    } catch (error) {
        alert('Upload failed: ' + error.message);
    }
}

// Upload signature
async function uploadSignature() {
    const fileInput = document.getElementById('signature-upload');
    const file = fileInput.files[0];
    
    if (!file) {
        alert('Please select a file first');
        return;
    }
    
    // Validate file type
    if (!file.type.startsWith('image/')) {
        alert('Please upload an image file');
        return;
    }
    
    // Create form data
    const formData = new FormData();
    formData.append('signature', file);
    
    try {
        const response = await fetch('/upload_signature', {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        
        if (result.success) {
            // Show success message
            const statusDiv = document.getElementById('practice-info-status');
            statusDiv.textContent = '✓ Signature uploaded successfully!';
            statusDiv.style.display = 'block';

            // Update display
            document.getElementById('signature-current').textContent = '✓ ' + result.filename;
            document.getElementById('signature-delete-button').style.display = 'inline-block';
            
            // Clear the file input
            fileInput.value = '';
            document.getElementById('signature-filename').textContent = '';
            document.getElementById('signature-upload-button').style.display = 'none';
            
            // Hide success message after 3 seconds
            setTimeout(() => {
                statusDiv.style.display = 'none';
            }, 3000);
        } else {
            alert('Upload failed: ' + result.error);
        }
    } catch (error) {
        alert('Upload failed: ' + error.message);
    }
}

// Delete logo
async function deleteLogo() {
    console.log('deleteLogo called');
    showConfirmModal('Delete Logo', 'Delete practice logo?', async function() {
        console.log('Delete confirmed, making API call');
        try {
            const response = await fetch('/delete_logo', {
                method: 'POST'
            });
            
            console.log('Response received:', response);
            const result = await response.json();
            console.log('Result:', result);
            
            if (result.success) {
                const statusDiv = document.getElementById('practice-info-status');
                statusDiv.textContent = '✓ Logo deleted successfully!';
                statusDiv.style.display = 'block';
                
                document.getElementById('logo-current').textContent = '';
                document.getElementById('logo-delete-button').style.display = 'none';
                
                setTimeout(() => {
                    statusDiv.style.display = 'none';
                }, 3000);
            } else {
                alert('Delete failed: ' + result.error);
            }
        } catch (error) {
            console.error('Delete error:', error);
            alert('Delete failed: ' + error.message);
        }
    });
}

// Delete signature
async function deleteSignature() {
    console.log('deleteSignature called');
    showConfirmModal('Delete Signature', 'Delete digital signature?', async function() {
        console.log('Delete confirmed, making API call');
        try {
            const response = await fetch('/delete_signature', {
                method: 'POST'
            });
            
            console.log('Response received:', response);
            const result = await response.json();
            console.log('Result:', result);
            
            if (result.success) {
                const statusDiv = document.getElementById('practice-info-status');
                statusDiv.textContent = '✓ Signature deleted successfully!';
                statusDiv.style.display = 'block';
                
                document.getElementById('signature-current').textContent = '';
                document.getElementById('signature-delete-button').style.display = 'none';
                
                setTimeout(() => {
                    statusDiv.style.display = 'none';
                }, 3000);
            } else {
                alert('Delete failed: ' + result.error);
            }
        } catch (error) {
            console.error('Delete error:', error);
            alert('Delete failed: ' + error.message);
        }
    });
}

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

function updateFileNumberPreview() {
    const prefix = document.getElementById('file-number-prefix').value || '';
    const suffix = document.getElementById('file-number-suffix').value || '';
    const start = document.getElementById('file-number-start').value || '1';
    
    // Pad number to 4 digits
    const paddedNumber = start.toString().padStart(4, '0');
    
    // Build preview
    let preview = '';
    if (prefix) preview += prefix + '-';
    preview += paddedNumber;
    if (suffix) preview += '-' + suffix;
    
    document.getElementById('file-number-preview').textContent = preview;
    
    // Check length
    if (preview.length > 12) {
        document.getElementById('file-number-preview').style.borderColor = '#B91C1C';
        document.getElementById('file-number-preview').style.color = '#B91C1C';
    } else {
        document.getElementById('file-number-preview').style.borderColor = '#DEE2E6';
        document.getElementById('file-number-preview').style.color = '#111827';
    }
}

// Add event listeners for preview updates
document.addEventListener('DOMContentLoaded', function() {
    document.getElementById('file-number-prefix').addEventListener('input', updateFileNumberPreview);
    document.getElementById('file-number-suffix').addEventListener('input', updateFileNumberPreview);
    document.getElementById('file-number-start').addEventListener('input', updateFileNumberPreview);
});

// Load file number settings
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

// Save file number settings
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
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(settings)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            const status = document.getElementById('file-number-status');
            status.textContent = '✓ File number format saved';
            status.style.display = 'block';
            setTimeout(() => status.style.display = 'none', 3000);
        }
    })
    .catch(error => console.error('Error saving file number settings:', error));
}

// Save and apply card style immediately
function saveAndApplyCardStyle() {
    const cardStyle = document.getElementById('card-style').value;
    localStorage.setItem('cardStyle', cardStyle);
    applyTheme();
}

// Save and apply background immediately
function saveAndApplyBackground() {
    const backgroundStyle = document.getElementById('background-style').value;
    localStorage.setItem('backgroundStyle', backgroundStyle);
    applyTheme();
    updateDeleteButton();
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    loadBackgroundOptions();
    loadPracticeInfo();
    loadFileNumberSettings();  // ADD THIS LINE
});

function showAboutModal() {
    document.getElementById('about-modal').style.display = 'flex';
}

function closeAboutModal() {
    document.getElementById('about-modal').style.display = 'none';
}

// Calendar Settings
(function() {
    const calendarMethod = document.getElementById('calendar_method');
    const calendarNameGroup = document.getElementById('calendar-name-group');
    const calendarName = document.getElementById('calendar_name');
    
    if (!calendarMethod) return; // Not on settings page
    
    // Show/hide calendar name based on method
    calendarMethod.addEventListener('change', function() {
        calendarNameGroup.style.display = this.value === 'applescript' ? 'block' : 'none';
    });
    
    // Load calendar settings
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
})();

function saveCalendarSettings() {
    const calendarMethod = document.getElementById('calendar_method');
    const calendarName = document.getElementById('calendar_name');
    
    fetch('/api/calendar_settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            calendar_method: calendarMethod.value,
            calendar_name: calendarName.value
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alert('Calendar settings saved!');
        }
    });
}

// Toggle calendar name field visibility
function toggleCalendarNameField() {
    const method = document.getElementById('calendar_method').value;
    const nameGroup = document.getElementById('calendar-name-group');
    nameGroup.style.display = method === 'applescript' ? 'block' : 'none';
}