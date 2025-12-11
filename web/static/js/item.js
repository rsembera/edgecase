/**
 * Item Entry Form JavaScript - EdgeCase Equalizer
 * Handles billable item creation/editing with three-way fee calculation
 * and date/time pickers.
 */

/**
 * Three-way fee calculation for item fees
 * @param {string} changedField - Which field was changed: 'base', 'tax', or 'total'
 */
function calculateItemFee(changedField) {
    const baseInput = document.getElementById('base_price');
    const taxInput = document.getElementById('tax_rate');
    const totalInput = document.getElementById('fee');
    
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
 * Format input value to 2 decimal places
 * @param {HTMLInputElement} input - Input element to format
 */
function formatToTwoDecimals(input) {
    const value = parseFloat(input.value);
    if (!isNaN(value)) {
        input.value = value.toFixed(2);
    }
}

// Auto-expanding textarea
const contentTextarea = document.getElementById('content');
const maxHeight = 600;

/**
 * Auto-resize textarea to fit content up to maxHeight
 */
function autoResize() {
    if (!contentTextarea) return;
    contentTextarea.style.height = 'auto';
    const newHeight = Math.min(contentTextarea.scrollHeight, maxHeight);
    contentTextarea.style.height = newHeight + 'px';
    
    if (contentTextarea.scrollHeight > maxHeight) {
        contentTextarea.style.overflowY = 'scroll';
    } else {
        contentTextarea.style.overflowY = 'hidden';
    }
}

// Run on page load (for edit mode with existing content)
autoResize();

// Run on input
if (contentTextarea) {
    contentTextarea.addEventListener('input', autoResize);
}

// ============================================================
// DATE/TIME PICKERS
// ============================================================

/**
 * Initialize date and time pickers for item form
 */
async function initItemPickers() {
    // Get time format setting
    const timeFormat = await getTimeFormatSetting();
    
    // Get initial values from hidden inputs
    const dateInput = document.getElementById('item_date');
    const timeInput = document.getElementById('item_time');
    
    // Initialize date picker
    const datePicker = initDatePicker('item-date-picker', {
        initialDate: dateInput.value ? parseDateString(dateInput.value) : new Date(),
        onSelect: (date) => {
            const year = date.getFullYear();
            const month = String(date.getMonth() + 1).padStart(2, '0');
            const day = String(date.getDate()).padStart(2, '0');
            dateInput.value = `${year}-${month}-${day}`;
        }
    });
    
    // Initialize time picker
    const timePicker = initTimePicker('item-time-picker', {
        format: timeFormat,
        initialTime: timeInput.value || null,
        onSelect: (timeStr) => {
            timeInput.value = timeStr;
        }
    });
    
    // If no initial time and not in edit mode, populate with current time
    if (!timeInput.value) {
        timeInput.value = timePicker.formatTime();
    }
}

// Initialize pickers when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initItemPickers);
} else {
    initItemPickers();
}


// ============================================================
// GUARDIAN SPLIT HANDLING
// ============================================================

// These will be set once DOM is ready
let hasTwoGuardians = false;
let isBilled = false;
let isEditMode = false;
let guardian1Percent = 50;
let guardian2Percent = 50;

/**
 * Initialize guardian data from DOM attributes
 */
function initGuardianData() {
    const itemData = document.getElementById('item-data');
    if (itemData) {
        hasTwoGuardians = itemData.dataset.hasTwoGuardians === 'true';
        isBilled = itemData.dataset.isBilled === 'true';
        isEditMode = itemData.dataset.isEdit === 'true';
        guardian1Percent = parseFloat(itemData.dataset.guardian1Percent) || 50;
        guardian2Percent = parseFloat(itemData.dataset.guardian2Percent) || 50;
    }
}

/**
 * Sync guardian amounts - when one changes, adjust the other to match total
 * @param {string} source - Which field was edited: 'g1' or 'g2'
 */
function syncGuardianAmounts(source) {
    if (!hasTwoGuardians || isBilled) return;
    
    const g1Input = document.getElementById('guardian1_amount');
    const g2Input = document.getElementById('guardian2_amount');
    const totalInput = document.getElementById('fee');
    
    if (!g1Input || !g2Input || !totalInput) return;
    
    const total = parseFloat(totalInput.value) || 0;
    const g1 = parseFloat(g1Input.value) || 0;
    const g2 = parseFloat(g2Input.value) || 0;
    
    if (source === 'g1') {
        // G1 was edited, adjust G2 to make up remainder
        const newG2 = total - g1;
        g2Input.value = newG2.toFixed(2);
    } else if (source === 'g2') {
        // G2 was edited, adjust G1 to make up remainder
        const newG1 = total - g2;
        g1Input.value = newG1.toFixed(2);
    }
}

/**
 * Auto-populate guardian split based on profile percentages when fee changes
 */
function autoPopulateGuardianSplit() {
    if (!hasTwoGuardians || isBilled) return;
    
    const g1Input = document.getElementById('guardian1_amount');
    const g2Input = document.getElementById('guardian2_amount');
    const totalInput = document.getElementById('fee');
    
    if (!g1Input || !g2Input || !totalInput) return;
    
    const total = parseFloat(totalInput.value) || 0;
    
    // Use profile percentages for split
    // Round g1 to 2 decimals, g2 gets remainder to ensure exact total
    const g1 = Math.round(total * guardian1Percent) / 100;
    const g2 = Math.round((total - g1) * 100) / 100;
    
    g1Input.value = g1.toFixed(2);
    g2Input.value = g2.toFixed(2);
}

// Hook into fee calculation to auto-populate guardian split
const originalCalculateItemFee = calculateItemFee;
calculateItemFee = function(changedField) {
    originalCalculateItemFee(changedField);
    // Only auto-populate on new items, not edits
    if (!isEditMode) {
        autoPopulateGuardianSplit();
    }
};

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    // Initialize guardian data from DOM first
    initGuardianData();
    
    // Auto-populate guardian split based on profile percentages for new items
    if (hasTwoGuardians && !isEditMode && !isBilled) {
        autoPopulateGuardianSplit();
    }
    
    // Add form submission validation - fee must be non-zero (all items)
    if (!isEditMode && !isBilled) {
        const form = document.querySelector('form');
        if (form) {
            form.addEventListener('submit', function(e) {
                const totalInput = document.getElementById('fee');
                const total = parseFloat(totalInput.value) || 0;
                
                if (total === 0) {
                    e.preventDefault();
                    showValidationModal('Please enter a non-zero price.');
                    return;
                }
            });
        }
    }
});

/**
 * Show validation error modal
 * @param {string} message - Error message to display
 */
function showValidationModal(message) {
    document.getElementById('validation-message').textContent = message;
    document.getElementById('validation-modal').style.display = 'flex';
}

/**
 * Close validation modal
 */
function closeValidationModal() {
    document.getElementById('validation-modal').style.display = 'none';
}

// ============================================================
// FILE UPLOAD HANDLING
// ============================================================

/**
 * Toggle the file upload section visibility
 */
function toggleUploadSection() {
    const uploadSection = document.getElementById('upload-section');
    const toggleIcon = document.getElementById('upload-toggle-icon');
    
    if (uploadSection.style.display === 'none') {
        uploadSection.style.display = 'block';
        toggleIcon.textContent = '▼';
    } else {
        uploadSection.style.display = 'none';
        toggleIcon.textContent = '▶';
    }
}

/**
 * Auto-add new file row when a file is selected
 */
function handleFileSelected(inputElement) {
    if (!inputElement.files || inputElement.files.length === 0) return;
    
    const container = document.getElementById('file-inputs');
    const allRows = container.querySelectorAll('.file-input-row');
    const lastRow = allRows[allRows.length - 1];
    const lastInput = lastRow.querySelector('.file-input');
    
    // Only add new row if this is the last row and it now has a file
    if (inputElement === lastInput) {
        addNewFileRow();
    }
    
    updateRemoveButtons();
}

/**
 * Add a new empty file input row
 */
function addNewFileRow() {
    const container = document.getElementById('file-inputs');
    
    const newRow = document.createElement('div');
    newRow.className = 'file-input-row';
    newRow.innerHTML = `
        <div class="file-row-grid">
            <div class="file-col">
                <label>Choose file</label>
                <input type="file" name="files[]" class="file-input" onchange="handleFileSelected(this)">
            </div>
            <div class="file-col">
                <label>Description (optional)</label>
                <input type="text" name="file_descriptions[]" placeholder="Brief description">
            </div>
            <button type="button" class="btn-small btn-danger remove-file-btn" onclick="removeFileRow(this)">Remove</button>
        </div>
    `;
    
    container.appendChild(newRow);
    updateRemoveButtons();
}

/**
 * Remove a file row
 */
function removeFileRow(button) {
    const row = button.closest('.file-input-row');
    const container = document.getElementById('file-inputs');
    const allRows = container.querySelectorAll('.file-input-row');
    
    if (allRows.length === 1) {
        // Clear the only row instead of removing
        const fileInput = row.querySelector('.file-input');
        const descInput = row.querySelector('input[name="file_descriptions[]"]');
        fileInput.value = '';
        if (descInput) descInput.value = '';
    } else {
        row.remove();
    }
    
    updateRemoveButtons();
}

/**
 * Update remove button visibility - hide when only one empty row
 */
function updateRemoveButtons() {
    const container = document.getElementById('file-inputs');
    if (!container) return;
    
    const rows = container.querySelectorAll('.file-input-row');
    
    rows.forEach((row, index) => {
        const removeBtn = row.querySelector('.remove-file-btn');
        if (removeBtn) {
            // Show remove button if more than one row
            removeBtn.style.display = rows.length > 1 ? '' : 'none';
        }
    });
}

// Delete attachment (for edit mode)
let deleteAttachmentId = null;

/**
 * Show delete attachment confirmation modal
 * @param {number} attachmentId - ID of attachment to delete
 */
function deleteAttachment(attachmentId) {
    deleteAttachmentId = attachmentId;
    document.getElementById('delete-modal').style.display = 'flex';
}

/**
 * Close the delete attachment modal
 */
function closeDeleteModal() {
    document.getElementById('delete-modal').style.display = 'none';
    deleteAttachmentId = null;
}

/**
 * Confirm and execute attachment deletion
 */
function confirmDelete() {
    if (!deleteAttachmentId) return;
    
    fetch(`/attachment/${deleteAttachmentId}/delete`, {
        method: 'POST'
    })
    .then(response => {
        if (response.ok) {
            window.location.reload();
        } else {
            alert('Error deleting attachment');
            closeDeleteModal();
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('Error deleting attachment');
        closeDeleteModal();
    });
}
