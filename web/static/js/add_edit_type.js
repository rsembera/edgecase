/**
 * Add/Edit Client Type JavaScript - EdgeCase Equalizer
 * Handles client type creation/editing with color picker and retention settings.
 */

// Color picker
document.querySelectorAll('.color-option').forEach(option => {
    option.addEventListener('click', function() {
        const hex = this.dataset.hex;
        const name = this.dataset.name;
        const bubble = this.dataset.bubble;
        
        // Update hidden inputs
        document.getElementById('color').value = hex;
        document.getElementById('color_name').value = name;
        document.getElementById('bubble_color').value = bubble;
        
        // Update UI
        document.querySelectorAll('.color-option').forEach(opt => {
            opt.classList.remove('selected');
        });
        this.classList.add('selected');
    });
});

// Retention period conversion on page load
const form = document.getElementById('type-form');
const retentionDays = parseInt(form.dataset.retentionDays) || 0;

if (retentionDays > 0) {
    const retentionValue = document.getElementById('retention_value');
    const retentionUnit = document.getElementById('retention_unit');
    
    // Convert days to most appropriate unit
    if (retentionDays % 365 === 0) {
        retentionValue.value = retentionDays / 365;
        retentionUnit.value = 'years';
    } else if (retentionDays % 30 === 0) {
        retentionValue.value = retentionDays / 30;
        retentionUnit.value = 'months';
    } else {
        retentionValue.value = retentionDays;
        retentionUnit.value = 'days';
    }
}

// Convert retention period to days before form submission
form.addEventListener('submit', function(e) {
    const value = parseInt(document.getElementById('retention_value').value) || 0;
    const unit = document.getElementById('retention_unit').value;
    let days = value;
    
    if (unit === 'months') {
        days = value * 30;
    } else if (unit === 'years') {
        days = value * 365;
    }
    
    // Create hidden input with days value
    const hiddenInput = document.createElement('input');
    hiddenInput.type = 'hidden';
    hiddenInput.name = 'retention_period';
    hiddenInput.value = days;
    this.appendChild(hiddenInput);
});

// Delete confirmation modal
const deleteBtn = document.getElementById('delete-btn');
const deleteModal = document.getElementById('deleteModal');
const cancelDelete = document.getElementById('cancel-delete');
const confirmDelete = document.getElementById('confirm-delete');

// Error modal elements
const errorModal = document.getElementById('errorModal');
const errorMessage = document.getElementById('error-message');
const closeError = document.getElementById('close-error');

if (deleteBtn) {
    deleteBtn.addEventListener('click', function() {
        deleteModal.classList.add('active');
    });
}

if (cancelDelete) {
    cancelDelete.addEventListener('click', function() {
        deleteModal.classList.remove('active');
    });
}

if (closeError) {
    closeError.addEventListener('click', function() {
        errorModal.classList.remove('active');
    });
}

if (confirmDelete) {
    confirmDelete.addEventListener('click', function() {
        const typeId = form.dataset.typeId;
        if (!typeId) return;
        
        fetch(`/types/${typeId}/delete`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                window.location.href = '/types';
            } else {
                deleteModal.classList.remove('active');
                errorMessage.textContent = data.error || 'Failed to delete type';
                errorModal.classList.add('active');
            }
        })
        .catch(error => {
            deleteModal.classList.remove('active');
            errorMessage.textContent = 'Network error: Could not delete type';
            errorModal.classList.add('active');
            console.error('Delete error:', error);
        });
    });
}
