// Settings page JavaScript - EdgeCase Equalizer

// Phone number auto-formatting (supports 10-12 digits) - same as profile.js
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

// Section toggle functionality
document.addEventListener('DOMContentLoaded', function() {
    // Set up section toggles
    const sectionToggleBtns = document.querySelectorAll('.section-toggle-btn');
    
    sectionToggleBtns.forEach(btn => {
        btn.addEventListener('click', function() {
            const sectionName = this.dataset.section;
            const sectionContent = document.getElementById(`${sectionName}-section`);
            const icon = this.querySelector('.toggle-icon');
            
            if (sectionContent.style.display === 'none') {
                sectionContent.style.display = 'block';
                icon.textContent = '▼';
            } else {
                sectionContent.style.display = 'none';
                icon.textContent = '▶';
            }
        });
    });
    
    // Initialize other components
    loadBackgroundOptions();
    loadPracticeInfo();
    loadFileNumberSettings();
    
    // Add phone number formatting
    const phoneInput = document.getElementById('practice-phone');
    if (phoneInput) {
        // Format on page load if value exists
        if (phoneInput.value) {
            phoneInput.value = formatPhoneNumber(phoneInput.value);
        }
        
        // Format as user types (with cursor position handling)
        phoneInput.addEventListener('input', function(e) {
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
    }
    
    // Add event listeners for file number preview
    const prefixInput = document.getElementById('file-number-prefix');
    const suffixInput = document.getElementById('file-number-suffix');
    const startInput = document.getElementById('file-number-start');
    
    if (prefixInput) prefixInput.addEventListener('input', updateFileNumberPreview);
    if (suffixInput) suffixInput.addEventListener('input', updateFileNumberPreview);
    if (startInput) startInput.addEventListener('input', updateFileNumberPreview);
});

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
        
        // Clear existing options except "Suit Grey"
        while (select.options.length > 1) {
            select.remove(1);
        }
        
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
        deleteBtn.style.display = 'inline-block';
    } else {
        deleteBtn.style.display = 'none';
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
    
    showConfirmModal('Delete Background', `Delete "${filename}"?`, async function() {
        console.log('Delete confirmed, making API call');
        try {
            const response = await fetch('/delete_background', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
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
                
                // Switch to default background
                localStorage.setItem('backgroundStyle', 'suit-grey');
                document.getElementById('background-style').value = 'suit-grey';
                applyTheme();
                
                // Reload background options
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

// Background upload functionality
document.getElementById('background-upload').addEventListener('change', function(e) {
    const file = e.target.files[0];
    if (file) {
        document.getElementById('upload-filename').textContent = file.name;
        document.getElementById('upload-button').style.display = 'inline-block';
    }
});

async function uploadBackground() {
    const fileInput = document.getElementById('background-upload');
    const file = fileInput.files[0];
    
    if (!file) {
        alert('Please select a file first');
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
            // Show success message
            const statusDiv = document.getElementById('upload-status');
            statusDiv.textContent = '✓ Background uploaded successfully!';
            statusDiv.style.display = 'block';
            
            // Clear the file input
            fileInput.value = '';
            document.getElementById('upload-filename').textContent = '';
            document.getElementById('upload-button').style.display = 'none';
            
            // Reload background options and switch to the new background
            await loadBackgroundOptions();
            const newValue = 'user:' + result.filename;
            localStorage.setItem('backgroundStyle', newValue);
            document.getElementById('background-style').value = newValue;
            applyTheme();
            updateDeleteButton();
            
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

// Practice information management
async function loadPracticeInfo() {
    try {
        const response = await fetch('/api/practice_info');
        const result = await response.json();
        
        if (result.success && result.info) {
            const data = result.info;  // Info is nested in result
            
            document.getElementById('practice-name').value = data.practice_name || '';
            document.getElementById('therapist-name').value = data.therapist_name || '';
            document.getElementById('credentials').value = data.credentials || '';
            document.getElementById('practice-phone').value = data.phone || '';
            document.getElementById('practice-email').value = data.email || '';
            document.getElementById('practice-address').value = data.address || '';
            document.getElementById('practice-website').value = data.website || '';
            document.getElementById('default-session-duration').value = data.consultation_duration || '20';
            
            // Format phone after loading
            const phoneInput = document.getElementById('practice-phone');
            if (phoneInput.value) {
                phoneInput.value = formatPhoneNumber(phoneInput.value);
            }
            
            // Show current logo/signature if they exist
            if (data.logo_filename) {
                document.getElementById('logo-current').textContent = '✓ ' + data.logo_filename;
                document.getElementById('logo-delete-button').style.display = 'inline-block';
            }
            if (data.signature_filename) {
                document.getElementById('signature-current').textContent = '✓ ' + data.signature_filename;
                document.getElementById('signature-delete-button').style.display = 'inline-block';
            }
        }
    } catch (error) {
        console.error('Failed to load practice info:', error);
    }
}

async function saveSettings() {
    const practiceInfo = {
        practice_name: document.getElementById('practice-name').value,
        therapist_name: document.getElementById('therapist-name').value,
        credentials: document.getElementById('credentials').value,
        phone: document.getElementById('practice-phone').value,
        email: document.getElementById('practice-email').value,
        address: document.getElementById('practice-address').value,
        website: document.getElementById('practice-website').value,
        consultation_duration: parseInt(document.getElementById('default-session-duration').value)
    };
    
    try {
        const response = await fetch('/api/practice_info', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(practiceInfo)
        });
        
        if (response.ok) {
            // Also save file number settings
            await saveFileNumberSettings();
            
            // Show success message briefly, then redirect
            const successMsg = document.getElementById('success-message');
            successMsg.classList.add('show');
            setTimeout(() => {
                window.location.href = '/';  // Redirect to main view
            }, 1000);
        } else {
            alert('Failed to save settings');
        }
    } catch (error) {
        console.error('Error saving settings:', error);
        alert('Error saving settings: ' + error.message);
    }
}

// Logo upload functionality
document.getElementById('logo-upload').addEventListener('change', function(e) {
    const file = e.target.files[0];
    if (file) {
        document.getElementById('logo-filename').textContent = file.name;
        document.getElementById('logo-upload-button').style.display = 'inline-block';
    }
});

async function uploadLogo() {
    const fileInput = document.getElementById('logo-upload');
    const file = fileInput.files[0];
    
    if (!file) {
        alert('Please select a file first');
        return;
    }
    
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

// Signature upload functionality
document.getElementById('signature-upload').addEventListener('change', function(e) {
    const file = e.target.files[0];
    if (file) {
        document.getElementById('signature-filename').textContent = file.name;
        document.getElementById('signature-upload-button').style.display = 'inline-block';
    }
});

async function uploadSignature() {
    const fileInput = document.getElementById('signature-upload');
    const file = fileInput.files[0];
    
    if (!file) {
        alert('Please select a file first');
        return;
    }
    
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
    
    return fetch('/settings/file-number', {
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
        return data;
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

function showAboutModal() {
    document.getElementById('about-modal').style.display = 'flex';
}

function closeAboutModal() {
    document.getElementById('about-modal').style.display = 'none';
}
