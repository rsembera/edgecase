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

// Three-way fee calculation (same logic as item.js)
const basePrice = document.getElementById('session_base_price');
const taxRate = document.getElementById('session_tax_rate');
const totalPrice = document.getElementById('session_total');

let lastEdited = null;

function calculateFee() {
    const base = parseFloat(basePrice.value) || 0;
    const rate = parseFloat(taxRate.value) || 0;
    const total = parseFloat(totalPrice.value) || 0;
    
    // If user just edited base or tax rate, calculate total
    if (lastEdited === 'base' || lastEdited === 'rate') {
        const calculatedTotal = base * (1 + rate / 100);
        totalPrice.value = calculatedTotal.toFixed(2);
    }
    // If user just edited total, calculate base (keeping tax rate)
    else if (lastEdited === 'total') {
        const calculatedBase = total / (1 + rate / 100);
        basePrice.value = calculatedBase.toFixed(2);
    }
}

basePrice.addEventListener('input', function() {
    lastEdited = 'base';
    calculateFee();
});

taxRate.addEventListener('input', function() {
    lastEdited = 'rate';
    calculateFee();
});

totalPrice.addEventListener('input', function() {
    lastEdited = 'total';
    calculateFee();
});

// Currency formatting
function formatCurrency(input) {
    let value = parseFloat(input.value);
    if (!isNaN(value)) {
        input.value = value.toFixed(2);
    }
}

function formatTaxRate(input) {
    let value = parseFloat(input.value);
    if (!isNaN(value)) {
        input.value = value.toFixed(2);
    }
}

basePrice.addEventListener('blur', function() {
    formatCurrency(this);
});

totalPrice.addEventListener('blur', function() {
    formatCurrency(this);
});

taxRate.addEventListener('blur', function() {
    formatTaxRate(this);
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

if (confirmDelete) {
    confirmDelete.addEventListener('click', function() {
        // Create a form to submit DELETE request
        const deleteForm = document.createElement('form');
        deleteForm.method = 'POST';
        
        const typeId = form.dataset.typeId;
        if (typeId) {
            deleteForm.action = `/edit_type/${typeId}`;
        }
        
        const input = document.createElement('input');
        input.type = 'hidden';
        input.name = '_method';
        input.value = 'DELETE';
        deleteForm.appendChild(input);
        
        document.body.appendChild(deleteForm);
        deleteForm.submit();
    });
}

// On page load, if editing existing type, set lastEdited to make calculations work
if (form.dataset.typeId) {
    lastEdited = 'base';
}