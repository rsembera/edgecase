// Outstanding Statements page JavaScript

document.addEventListener('DOMContentLoaded', function() {
    // Mark Paid buttons
    document.querySelectorAll('.mark-paid-btn').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.stopPropagation();
            const portionId = this.dataset.portionId;
            showPaymentForm(portionId);
        });
    });
    
    // Cancel payment buttons
    document.querySelectorAll('.cancel-payment-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            const formRow = this.closest('.payment-form-row');
            hidePaymentForm(formRow);
        });
    });
    
    // Confirm payment buttons
    document.querySelectorAll('.confirm-payment-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            const portionId = this.dataset.portionId;
            const amountOwing = parseFloat(this.dataset.amountOwing);
            confirmPayment(portionId, amountOwing);
        });
    });
    
    // Radio button toggle for partial payment input
    document.querySelectorAll('input[type="radio"][name^="payment-type-"]').forEach(radio => {
        radio.addEventListener('change', function() {
            const formRow = this.closest('.payment-form-row');
            const partialInput = formRow.querySelector('.partial-amount');
            
            if (this.value === 'partial') {
                partialInput.disabled = false;
                partialInput.focus();
            } else {
                partialInput.disabled = true;
                partialInput.value = '';
            }
        });
    });
    
    // Initialize Lucide icons
    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }
});

function filterTable() {
    const searchInput = document.getElementById('search-input');
    const statusFilter = document.getElementById('status-filter');
    const searchTerm = searchInput ? searchInput.value.toLowerCase() : '';
    const statusValue = statusFilter ? statusFilter.value : 'all';
    
    // Show/hide clear button
    const clearBtn = document.querySelector('.clear-search');
    if (clearBtn) {
        clearBtn.style.display = searchTerm ? 'flex' : 'none';
    }
    
    document.querySelectorAll('.statements-table tbody tr.entry-row').forEach(row => {
        const clientName = row.dataset.clientName || '';
        const fileNumber = row.dataset.fileNumber || '';
        const status = row.dataset.status || '';
        
        const matchesSearch = clientName.includes(searchTerm) || 
                             fileNumber.includes(searchTerm);
        const matchesStatus = statusValue === 'all' || status === statusValue;
        
        if (matchesSearch && matchesStatus) {
            row.style.display = '';
        } else {
            row.style.display = 'none';
            // Also hide associated payment form row
            const portionId = row.dataset.portionId;
            const formRow = document.querySelector(`.payment-form-row[data-for-portion="${portionId}"]`);
            if (formRow) {
                formRow.style.display = 'none';
            }
        }
    });
}

function clearSearch() {
    const searchInput = document.getElementById('search-input');
    if (searchInput) {
        searchInput.value = '';
        filterTable();
    }
}

function showPaymentForm(portionId) {
    // Hide all other payment forms
    document.querySelectorAll('.payment-form-row').forEach(row => {
        row.style.display = 'none';
    });
    
    // Show this payment form
    const formRow = document.querySelector(`.payment-form-row[data-for-portion="${portionId}"]`);
    if (formRow) {
        formRow.style.display = '';
        
        // Reset form
        const fullRadio = formRow.querySelector('input[value="full"]');
        if (fullRadio) fullRadio.checked = true;
        
        const partialInput = formRow.querySelector('.partial-amount');
        if (partialInput) {
            partialInput.disabled = true;
            partialInput.value = '';
        }
        
        const notesInput = formRow.querySelector('.notes-input');
        if (notesInput) notesInput.value = '';
    }
}

function hidePaymentForm(formRow) {
    formRow.style.display = 'none';
}

function confirmPayment(portionId, amountOwing) {
    const formRow = document.querySelector(`.payment-form-row[data-for-portion="${portionId}"]`);
    const paymentType = formRow.querySelector('input[name^="payment-type-"]:checked').value;
    const partialAmount = formRow.querySelector('.partial-amount').value;
    const notes = formRow.querySelector('.notes-input').value;
    
    let paymentAmount;
    if (paymentType === 'full') {
        paymentAmount = amountOwing;
    } else {
        paymentAmount = parseFloat(partialAmount);
        if (isNaN(paymentAmount) || paymentAmount <= 0) {
            alert('Please enter a valid payment amount');
            return;
        }
        if (paymentAmount > amountOwing) {
            alert('Payment amount cannot exceed amount owing');
            return;
        }
    }
    
    // Disable button while processing
    const confirmBtn = formRow.querySelector('.confirm-payment-btn');
    confirmBtn.disabled = true;
    confirmBtn.textContent = 'Processing...';
    
    fetch('/statements/mark-paid', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            portion_id: portionId,
            payment_amount: paymentAmount,
            payment_type: paymentType,
            notes: notes
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Reload page to show updated data
            window.location.reload();
        } else {
            alert(data.error || 'Failed to process payment');
            confirmBtn.disabled = false;
            confirmBtn.textContent = 'Confirm Payment';
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('Network error. Please try again.');
        confirmBtn.disabled = false;
        confirmBtn.textContent = 'Confirm Payment';
    });
}
