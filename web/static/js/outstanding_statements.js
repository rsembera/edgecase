/**
 * Outstanding Statements JavaScript - EdgeCase Equalizer
 * Handles statement listing, filtering, generation, payments, and write-offs.
 */

// ============================================================
// STATE
// ============================================================

let currentFilter = 'all';
let currentPaymentPortionId = null;
let currentWriteOffPortionId = null;
let currentWriteOffAmount = 0;

// ============================================================
// INITIALIZATION
// ============================================================

document.addEventListener('DOMContentLoaded', function() {
    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }
    
    const searchInput = document.getElementById('search-input');
    if (searchInput) {
        updateClearButton();
        searchInput.addEventListener('input', updateClearButton);
    }
    
    // Close dropdown when clicking outside
    document.addEventListener('click', function(e) {
        if (!e.target.closest('.dropdown-btn') && !e.target.closest('#filter-dropdown')) {
            const dropdown = document.getElementById('filter-dropdown');
            if (dropdown) dropdown.style.display = 'none';
        }
    });
    
    // Payment modal - close on outside click
    const paymentModal = document.getElementById('payment-modal');
    if (paymentModal) {
        paymentModal.addEventListener('click', function(e) {
            if (e.target === this) hidePaymentModal();
        });
    }
    
    // Payment amount - format on blur
    const paymentAmount = document.getElementById('payment-amount');
    if (paymentAmount) {
        paymentAmount.addEventListener('blur', function() {
            const val = parseFloat(this.value);
            if (!isNaN(val)) this.value = val.toFixed(2);
        });
    }
    
    // Write-off modal - close on outside click
    const writeoffModal = document.getElementById('writeoff-modal');
    if (writeoffModal) {
        writeoffModal.addEventListener('click', function(e) {
            if (e.target === this) hideWriteOffModal();
        });
    }
});

// ============================================================
// DROPDOWN AND FILTER
// ============================================================

/**
 * Toggle visibility of a dropdown by ID
 * @param {string} id - DOM element ID
 */
function toggleDropdown(id) {
    const dropdown = document.getElementById(id);
    if (dropdown) {
        dropdown.style.display = dropdown.style.display === 'none' ? 'block' : 'none';
    }
}

/**
 * Set the current filter and update UI
 * @param {string} value - Filter value ('all', 'ready', 'sent', 'partial')
 * @param {string} label - Display label for the filter
 */
function setFilter(value, label) {
    currentFilter = value;
    document.getElementById('filter-label').textContent = label;
    document.getElementById('filter-dropdown').style.display = 'none';
    
    document.querySelectorAll('.filter-option').forEach(opt => {
        opt.classList.toggle('active', opt.dataset.value === value);
    });
    
    filterTable();
}

/**
 * Filter and search the statements table
 */
function filterTable() {
    const searchTerm = document.getElementById('search-input').value.toLowerCase();
    const rows = document.querySelectorAll('.statement-row');
    
    rows.forEach(row => {
        const status = row.dataset.status;
        const client = row.dataset.client;
        const file = row.dataset.file;
        
        const statusMatch = currentFilter === 'all' || status === currentFilter;
        const searchMatch = !searchTerm || client.includes(searchTerm) || file.includes(searchTerm);
        
        row.style.display = (statusMatch && searchMatch) ? '' : 'none';
    });
    
    updateClearButton();
}

/**
 * Update clear button visibility based on search input
 */
function updateClearButton() {
    const searchInput = document.getElementById('search-input');
    const clearBtn = document.querySelector('.clear-search');
    if (searchInput && clearBtn) {
        clearBtn.style.display = searchInput.value ? 'block' : 'none';
    }
}

/**
 * Clear the search input and re-filter
 */
function clearSearch() {
    const searchInput = document.getElementById('search-input');
    if (searchInput) {
        searchInput.value = '';
        filterTable();
    }
}

// ============================================================
// GENERATE SECTION
// ============================================================

/**
 * Toggle the generate statements section expand/collapse
 */
function toggleGenerateSection() {
    const content = document.getElementById('generate-content');
    const icon = document.getElementById('generate-toggle-icon');
    
    content.classList.toggle('expanded');
    icon.classList.toggle('expanded');
}

// ============================================================
// DATE HELPERS
// ============================================================

/**
 * Get date string from dropdown selects
 * @param {string} prefix - Prefix for element IDs (e.g., 'start' or 'end')
 * @returns {string} Date in YYYY-MM-DD format
 */
function getDateFromDropdowns(prefix) {
    const year = document.getElementById(prefix + '-year').value;
    const month = document.getElementById(prefix + '-month').value.padStart(2, '0');
    const day = document.getElementById(prefix + '-day').value.padStart(2, '0');
    return `${year}-${month}-${day}`;
}

/**
 * Set dropdown selects from a date string
 * @param {string} prefix - Prefix for element IDs
 * @param {string} date - Date string parseable by Date constructor
 */
function setDateInDropdowns(prefix, date) {
    const d = new Date(date);
    document.getElementById(prefix + '-year').value = d.getFullYear();
    document.getElementById(prefix + '-month').value = d.getMonth() + 1;
    document.getElementById(prefix + '-day').value = d.getDate();
}

// ============================================================
// FIND UNBILLED CLIENTS
// ============================================================

/**
 * Find clients with unbilled sessions in the selected date range
 */
function findUnbilled() {
    const startDate = getDateFromDropdowns('start');
    const endDate = getDateFromDropdowns('end');
    
    fetch(`/statements/find-unbilled?start=${startDate}&end=${endDate}`)
        .then(response => response.json())
        .then(data => {
            const container = document.getElementById('unbilled-results');
            
            if (data.clients && data.clients.length > 0) {
                let html = `
                    <div class="unbilled-results">
                        <h4>Clients with Unbilled Sessions (${data.clients.length})</h4>
                        <div class="select-all-row">
                            <input type="checkbox" id="select-all" onchange="toggleSelectAll()">
                            <label for="select-all">Select All</label>
                        </div>
                        <div id="unbilled-list">
                `;
                
                data.clients.forEach(client => {
                    html += `
                        <div class="unbilled-client">
                            <input type="checkbox" class="client-checkbox" value="${client.id}" data-amount="${client.unbilled_total}">
                            <span class="client-name">${client.name}</span>
                            <span class="file-number">${client.file_number}</span>
                            <span class="unbilled-amount">$${client.unbilled_total.toFixed(2)}</span>
                        </div>
                    `;
                });
                
                html += `
                        </div>
                        <div class="generate-actions">
                            <button class="btn" onclick="generateStatements()">Generate Statements</button>
                        </div>
                    </div>
                `;
                
                container.innerHTML = html;
            } else {
                container.innerHTML = `
                    <div class="unbilled-results">
                        <p style="color: #718096; padding: 1rem 0;">No unbilled sessions found for the selected date range.</p>
                    </div>
                `;
            }
        })
        .catch(error => {
            console.error('Error finding unbilled:', error);
            alert('Error searching for unbilled sessions');
        });
}

/**
 * Toggle all client checkboxes based on "Select All" state
 */
function toggleSelectAll() {
    const selectAll = document.getElementById('select-all');
    const checkboxes = document.querySelectorAll('.client-checkbox');
    checkboxes.forEach(cb => cb.checked = selectAll.checked);
}

// ============================================================
// GENERATE STATEMENTS
// ============================================================

/**
 * Generate statements for selected clients
 */
function generateStatements() {
    const checkboxes = document.querySelectorAll('.client-checkbox:checked');
    const clientIds = Array.from(checkboxes).map(cb => parseInt(cb.value));
    
    if (clientIds.length === 0) {
        showSuccessModal('Please select at least one client', 'No Selection');
        return;
    }
    
    const startDate = getDateFromDropdowns('start');
    const endDate = getDateFromDropdowns('end');
    
    fetch('/statements/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            client_ids: clientIds,
            start_date: startDate,
            end_date: endDate
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            const word = data.count === 1 ? 'statement' : 'statements';
            showSuccessModal(`Generated ${data.count} ${word}`, 'Success');
        } else {
            alert('Error: ' + (data.error || 'Unknown error'));
        }
    })
    .catch(error => {
        console.error('Error generating statements:', error);
        alert('Error generating statements');
    });
}

// ============================================================
// STATEMENT ACTIONS
// ============================================================

/**
 * Mark statement as sent and trigger email
 * @param {number} portionId - Statement portion ID
 */
function markSent(portionId) {
    fetch(`/statements/mark-sent/${portionId}`, { method: 'POST' })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                data.portion_id = portionId;
                
                if (data.email_method === 'applescript') {
                    triggerAppleScriptEmail(data);
                } else {
                    triggerMailtoEmail(data);
                }
            } else {
                alert('Error: ' + (data.error || 'Unknown error'));
            }
        })
        .catch(error => {
            console.error('Error marking sent:', error);
            alert('Error marking statement as sent');
        });
}

/**
 * Generate PDF only (no email) - opens in new window
 * @param {number} portionId - Statement portion ID
 */
function generateOnly(portionId) {
    // Open window immediately to avoid popup blocker
    const pdfWindow = window.open('about:blank', '_blank');
    
    fetch(`/statements/mark-sent/${portionId}?skip_email=1`, { method: 'POST' })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                pdfWindow.location.href = `/statements/view-pdf/${portionId}`;
                setTimeout(() => window.location.reload(), 500);
            } else {
                pdfWindow.close();
                alert('Error: ' + (data.error || 'Unknown error'));
            }
        })
        .catch(error => {
            pdfWindow.close();
            console.error('Error generating statement:', error);
            alert('Error generating statement');
        });
}

/**
 * Trigger mailto link with PDF download
 * @param {Object} data - Email data from server
 */
function triggerMailtoEmail(data) {
    const subject = encodeURIComponent(data.subject);
    const body = encodeURIComponent(data.body + '\n\n[Please attach the downloaded PDF]');
    const mailto = `mailto:${data.recipient_email}?subject=${subject}&body=${body}`;
    
    // Download PDF for manual attachment
    const pdfLink = document.createElement('a');
    pdfLink.href = `/statements/pdf/${data.portion_id}`;
    pdfLink.download = '';
    pdfLink.click();
    
    setTimeout(() => {
        window.location.href = mailto;
        setTimeout(() => window.location.reload(), 1000);
    }, 300);
}

/**
 * Send email via AppleScript with PDF attachment
 * @param {Object} data - Email data from server
 */
function triggerAppleScriptEmail(data) {
    fetch('/statements/send-applescript-email', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            recipient_email: data.recipient_email,
            subject: data.subject,
            body: data.body,
            pdf_path: data.pdf_path,
            email_from: data.email_from
        })
    })
    .then(response => response.json())
    .then(result => {
        if (result.success) {
            window.location.reload();
        } else {
            alert('AppleScript email failed: ' + result.error + '\n\nFalling back to mailto...');
            triggerMailtoEmail(data);
        }
    })
    .catch(error => {
        console.error('AppleScript error:', error);
        alert('AppleScript email failed. Falling back to mailto...');
        triggerMailtoEmail(data);
    });
}

// ============================================================
// PAYMENT MODAL
// ============================================================

/**
 * Show the payment modal for a statement portion
 * @param {number} portionId - Statement portion ID
 * @param {number} amountOwing - Amount still owed
 */
function showPaymentForm(portionId, amountOwing) {
    currentPaymentPortionId = portionId;
    const input = document.getElementById('payment-amount');
    input.value = amountOwing.toFixed(2);
    input.dataset.max = amountOwing.toFixed(2);
    input.max = amountOwing.toFixed(2);
    document.getElementById('payment-modal').classList.add('visible');
}

/**
 * Hide the payment modal
 */
function hidePaymentModal() {
    document.getElementById('payment-modal').classList.remove('visible');
    currentPaymentPortionId = null;
}

/**
 * Submit the payment
 */
function confirmPayment() {
    const amountInput = document.getElementById('payment-amount');
    const amount = parseFloat(amountInput.value);
    
    if (isNaN(amount) || amount <= 0) {
        showSuccessModal('Please enter a valid positive amount', 'Invalid Amount');
        return;
    }
    
    const maxAmount = parseFloat(amountInput.dataset.max);
    if (amount > maxAmount) {
        showSuccessModal(`Amount cannot exceed $${maxAmount.toFixed(2)}`, 'Invalid Amount');
        return;
    }
    
    fetch('/statements/mark-paid', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            portion_id: currentPaymentPortionId,
            payment_amount: amount,
            payment_type: amount >= maxAmount ? 'full' : 'partial'
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            hidePaymentModal();
            showSuccessModal('Payment recorded', 'Success');
        } else {
            alert('Error: ' + (data.error || 'Unknown error'));
        }
    })
    .catch(error => {
        console.error('Error recording payment:', error);
        alert('Error recording payment');
    });
}

// ============================================================
// WRITE-OFF MODAL
// ============================================================

/**
 * Show the write-off modal for a statement portion
 * @param {number} portionId - Statement portion ID
 * @param {number} amountOwing - Amount to write off
 */
function showWriteOffModal(portionId, amountOwing) {
    currentWriteOffPortionId = portionId;
    currentWriteOffAmount = amountOwing;
    
    document.getElementById('writeoff-reason').value = '';
    document.getElementById('writeoff-note').value = '';
    document.getElementById('writeoff-note-group').style.display = 'none';
    document.getElementById('writeoff-hint').textContent = '';
    document.getElementById('writeoff-amount-text').textContent = '$' + amountOwing.toFixed(2);
    
    document.getElementById('writeoff-modal').classList.add('visible');
}

/**
 * Hide the write-off modal
 */
function hideWriteOffModal() {
    document.getElementById('writeoff-modal').classList.remove('visible');
    currentWriteOffPortionId = null;
    currentWriteOffAmount = 0;
}

/**
 * Toggle write-off note field visibility and update hint based on reason
 */
function toggleWriteOffNote() {
    const reason = document.getElementById('writeoff-reason').value;
    const noteGroup = document.getElementById('writeoff-note-group');
    const hint = document.getElementById('writeoff-hint');
    
    noteGroup.style.display = reason === 'other' ? 'block' : 'none';
    
    switch (reason) {
        case 'uncollectible':
            hint.textContent = 'This will create a "Bad Debt" expense entry in the Ledger.';
            hint.style.color = '#B45309';
            break;
        case 'waived':
        case 'billing_error':
            hint.textContent = 'The debt will be resolved. No ledger entry will be created.';
            hint.style.color = '#718096';
            break;
        case 'other':
            hint.textContent = 'Please provide an explanation. No ledger entry will be created.';
            hint.style.color = '#718096';
            break;
        default:
            hint.textContent = '';
    }
}

/**
 * Submit the write-off
 */
function confirmWriteOff() {
    const reason = document.getElementById('writeoff-reason').value;
    const note = document.getElementById('writeoff-note').value.trim();
    
    if (!reason) {
        showSuccessModal('Please select a reason', 'Missing Reason');
        return;
    }
    
    if (reason === 'other' && !note) {
        showSuccessModal('Please provide an explanation', 'Missing Explanation');
        return;
    }
    
    fetch('/statements/write-off', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            portion_id: currentWriteOffPortionId,
            reason: reason,
            note: note,
            amount: currentWriteOffAmount
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            hideWriteOffModal();
            showSuccessModal('Statement written off', 'Success');
        } else {
            alert('Error: ' + (data.error || 'Unknown error'));
        }
    })
    .catch(error => {
        console.error('Error writing off statement:', error);
        alert('Error writing off statement');
    });
}

// ============================================================
// SUCCESS MODAL
// ============================================================

/**
 * Show a success/info modal
 * @param {string} message - Message to display
 * @param {string} title - Modal title (default: 'Success')
 */
function showSuccessModal(message, title) {
    document.getElementById('success-title').textContent = title || 'Success';
    document.getElementById('success-message').textContent = message;
    document.getElementById('success-modal').classList.add('visible');
}

/**
 * Close the success modal and reload page
 */
function closeSuccessModal() {
    document.getElementById('success-modal').classList.remove('visible');
    window.location.reload();
}
