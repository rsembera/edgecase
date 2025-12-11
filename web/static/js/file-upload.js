/**
 * Shared File Upload Functions - EdgeCase Equalizer
 * Used by Communication, Upload, and Item entry forms.
 */

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

// ============================================================
// ATTACHMENT DELETION (for edit mode)
// ============================================================

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
