// Income Entry Form JavaScript

// Auto-expanding textarea for content/notes field
const textarea = document.getElementById('content');
const maxHeight = 400;

if (textarea) {
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
    
    autoResize();
    textarea.addEventListener('input', autoResize);
}

// Format to 2 decimal places on blur for amount fields
const totalAmountInput = document.getElementById('total_amount');
const taxAmountInput = document.getElementById('tax_amount');

if (totalAmountInput) {
    totalAmountInput.addEventListener('blur', function() {
        if (this.value) {
            this.value = parseFloat(this.value).toFixed(2);
        }
    });
}

if (taxAmountInput) {
    taxAmountInput.addEventListener('blur', function() {
        if (this.value) {
            this.value = parseFloat(this.value).toFixed(2);
        }
    });
}

// Toggle upload section
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

// Show "Add Another File" button only after file is selected in current session
function handleFileSelected() {
    const addFileBtn = document.getElementById('add-file-btn');
    addFileBtn.style.display = 'block';
}

// File validation modal functions
function showFileValidationModal() {
    document.getElementById('file-validation-modal').style.display = 'flex';
}

function closeFileValidationModal() {
    document.getElementById('file-validation-modal').style.display = 'none';
}

// Multiple file upload management
const fileInputsContainer = document.getElementById('file-inputs');
const addFileBtn = document.getElementById('add-file-btn');
let fileInputCount = 1;

// Add another file input row (only if current row has a file selected)
if (addFileBtn) {
    addFileBtn.addEventListener('click', function() {
        // Check if the last file input has a file selected
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
        
        // Add event listener to new remove button
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
        
        // Clear the inputs instead of removing if it's the only row
        const allRows = fileInputsContainer.querySelectorAll('.file-input-row');
        if (allRows.length === 1) {
            fileInput.value = '';
            descInput.value = '';
            // Hide "Add Another File" button when cleared
            document.getElementById('add-file-btn').style.display = 'none';
        } else {
            row.remove();
            fileInputCount--;
        }
    });
}

// Delete attachment (for edit mode)
let deleteAttachmentId = null;

function deleteAttachment(attachmentId) {
    deleteAttachmentId = attachmentId;
    document.getElementById('delete-modal').style.display = 'flex';
}

function closeDeleteModal() {
    document.getElementById('delete-modal').style.display = 'none';
    deleteAttachmentId = null;
}

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

// Delete entire income entry (edit mode only)
function confirmDeleteEntry() {
    document.getElementById('delete-entry-modal').style.display = 'flex';
}

function closeDeleteEntryModal() {
    document.getElementById('delete-entry-modal').style.display = 'none';
}

function deleteEntry() {
    // Get entry ID from URL (e.g., /ledger/income/123)
    const pathParts = window.location.pathname.split('/');
    const entryId = pathParts[3]; // /ledger/income/[ID]
    
    fetch(`/ledger/income/${entryId}/delete`, {
        method: 'POST'
    })
    .then(response => {
        if (response.ok) {
            window.location.href = '/ledger';
        } else {
            return response.text().then(text => {
                console.error('Server response:', text);
                alert('Error deleting income entry');
                closeDeleteEntryModal();
            });
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('Error deleting income entry');
        closeDeleteEntryModal();
    });
}
