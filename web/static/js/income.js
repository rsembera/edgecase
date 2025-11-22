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

// Multiple file upload management (same as Upload entry)
const fileInputsContainer = document.getElementById('file-inputs');
const addFileBtn = document.getElementById('add-file-btn');
let fileInputCount = 1;

// Add another file input row
addFileBtn.addEventListener('click', function() {
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
    
    // Update remove button visibility
    updateRemoveButtons();
    
    // Add event listener to new remove button
    const removeBtn = newRow.querySelector('.remove-file-btn');
    removeBtn.addEventListener('click', function() {
        newRow.remove();
        fileInputCount--;
        updateRemoveButtons();
    });
});

// Show/hide remove buttons (only show if more than one file input)
function updateRemoveButtons() {
    const allRows = fileInputsContainer.querySelectorAll('.file-input-row');
    allRows.forEach(row => {
        const removeBtn = row.querySelector('.remove-file-btn');
        if (allRows.length > 1) {
            removeBtn.style.display = 'block';
        } else {
            removeBtn.style.display = 'none';
        }
    });
}

// Add remove functionality to initial row
const initialRemoveBtn = document.querySelector('.remove-file-btn');
if (initialRemoveBtn) {
    initialRemoveBtn.addEventListener('click', function() {
        const row = this.closest('.file-input-row');
        row.remove();
        fileInputCount--;
        updateRemoveButtons();
    });
}

// Initial state
updateRemoveButtons();

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
