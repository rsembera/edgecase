/**
 * Communication Entry Form JavaScript - EdgeCase Equalizer
 * Handles communication creation/editing with auto-expanding textarea
 * and file upload functionality.
 */

// Auto-expanding textarea
const textarea = document.getElementById('content');
const maxHeight = 600; // About 30-35 lines

/**
 * Auto-resize textarea to fit content up to maxHeight
 */
function autoResize() {
    textarea.style.height = 'auto';
    const newHeight = Math.min(textarea.scrollHeight, maxHeight);
    textarea.style.height = newHeight + 'px';
    
    if (textarea.scrollHeight > maxHeight) {
        textarea.style.overflowY = 'scroll';
    } else {
        textarea.style.overflowY = 'hidden';
    }
}

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
 * Show "Add Another File" button after file is selected
 */
function handleFileSelected() {
    const addFileBtn = document.getElementById('add-file-btn');
    if (addFileBtn) {
        addFileBtn.style.display = 'block';
    }
}

/**
 * Show file validation modal
 */
function showFileValidationModal() {
    document.getElementById('file-validation-modal').style.display = 'flex';
}

/**
 * Close file validation modal
 */
function closeFileValidationModal() {
    document.getElementById('file-validation-modal').style.display = 'none';
}

// Multiple file upload management
const fileInputsContainer = document.getElementById('file-inputs');
const addFileBtn = document.getElementById('add-file-btn');
let fileInputCount = 1;

if (addFileBtn) {
    addFileBtn.addEventListener('click', function() {
        const allRows = fileInputsContainer.querySelectorAll('.file-input-row');
        const lastRow = allRows[allRows.length - 1];
        const lastFileInput = lastRow.querySelector('.file-input');
        
        if (!lastFileInput.files || lastFileInput.files.length === 0) {
            showFileValidationModal();
            return;
        }
        
        fileInputCount++;
        
        const newRow = document.createElement('div');
        newRow.className = 'file-input-row';
        newRow.style.marginBottom = '1rem';
        newRow.innerHTML = `
            <div style="display: flex; gap: 1rem; align-items: end;">
                <div style="flex: 2;">
                    <label style="display: block; margin-bottom: 0.25rem; font-size: 0.875rem; color: #374151;">
                        Choose file
                    </label>
                    <input type="file" 
                           name="files[]" 
                           class="file-input"
                           style="width: 100%; padding: 0.5rem; border: 1px solid #D1D5DB; border-radius: 0.375rem;">
                </div>
                <div style="flex: 2;">
                    <label style="display: block; margin-bottom: 0.25rem; font-size: 0.875rem; color: #374151;">
                        Description (optional)
                    </label>
                    <input type="text" 
                           name="file_descriptions[]" 
                           placeholder="Brief description"
                           style="width: 100%; padding: 0.5rem; border: 1px solid #D1D5DB; border-radius: 0.375rem;">
                </div>
                <button type="button" 
                        class="btn-small btn-danger remove-file-btn" 
                        style="white-space: nowrap;">Remove</button>
            </div>
        `;
        
        fileInputsContainer.appendChild(newRow);
        
        const removeBtn = newRow.querySelector('.remove-file-btn');
        removeBtn.addEventListener('click', function() {
            newRow.remove();
            fileInputCount--;
        });
    });
}

// Add remove functionality to initial row
const initialRemoveBtn = document.querySelector('.remove-file-btn');
if (initialRemoveBtn) {
    initialRemoveBtn.addEventListener('click', function() {
        const row = this.closest('.file-input-row');
        const fileInput = row.querySelector('.file-input');
        const descInput = row.querySelector('input[name="file_descriptions[]"]');
        
        const allRows = fileInputsContainer.querySelectorAll('.file-input-row');
        if (allRows.length === 1) {
            fileInput.value = '';
            descInput.value = '';
            const addBtn = document.getElementById('add-file-btn');
            if (addBtn) addBtn.style.display = 'none';
        } else {
            row.remove();
            fileInputCount--;
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

// Run on page load (for edit mode with existing content)
autoResize();

// Run on input
textarea.addEventListener('input', autoResize);

// ============================================================
// DATE/TIME PICKERS
// ============================================================

/**
 * Initialize date and time pickers for communication form
 */
async function initCommunicationPickers() {
    // Get time format setting
    const timeFormat = await getTimeFormatSetting();
    
    // Get initial values from hidden inputs
    const dateInput = document.getElementById('date');
    const timeInput = document.getElementById('comm_time');
    
    // Initialize date picker
    const datePicker = initDatePicker('comm-date-picker', {
        initialDate: dateInput.value ? parseDateString(dateInput.value) : new Date(),
        onSelect: (date) => {
            const year = date.getFullYear();
            const month = String(date.getMonth() + 1).padStart(2, '0');
            const day = String(date.getDate()).padStart(2, '0');
            dateInput.value = `${year}-${month}-${day}`;
        }
    });
    
    // CRITICAL: Set initial date value if not already set (new entries)
    // Without this, if user doesn't click a date, the hidden input stays empty
    if (!dateInput.value && datePicker) {
        const today = new Date();
        const year = today.getFullYear();
        const month = String(today.getMonth() + 1).padStart(2, '0');
        const day = String(today.getDate()).padStart(2, '0');
        dateInput.value = `${year}-${month}-${day}`;
    }
    
    // Initialize time picker
    const timePicker = initTimePicker('comm-time-picker', {
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
    document.addEventListener('DOMContentLoaded', initCommunicationPickers);
} else {
    initCommunicationPickers();
}
