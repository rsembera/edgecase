/* Outstanding Statements - JavaScript */

// Track current filter
let currentFilter = 'all';

document.addEventListener('DOMContentLoaded', function() {
    // Initialize Lucide icons
    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }
    
    // Set up search input clear button visibility
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
});

// ============================================
// DROPDOWN TOGGLE (matches main_view)
// ============================================

function toggleDropdown(id) {
    const dropdown = document.getElementById(id);
    if (dropdown) {
        dropdown.style.display = dropdown.style.display === 'none' ? 'block' : 'none';
    }
}

function setFilter(value, label) {
    currentFilter = value;
    document.getElementById('filter-label').textContent = label;
    document.getElementById('filter-dropdown').style.display = 'none';
    
    // Update active state on options
    document.querySelectorAll('.filter-option').forEach(opt => {
        opt.classList.toggle('active', opt.dataset.value === value);
    });
    
    filterTable();
}

// ============================================
// GENERATE SECTION TOGGLE
// ============================================

function toggleGenerateSection() {
    const content = document.getElementById('generate-content');
    const icon = document.getElementById('generate-toggle-icon');
    
    if (content.classList.contains('expanded')) {
        content.classList.remove('expanded');
        icon.classList.remove('expanded');
    } else {
        content.classList.add('expanded');
        icon.classList.add('expanded');
    }
}

// ============================================
// DATE HELPERS
// ============================================

function getDateFromDropdowns(prefix) {
    const year = document.getElementById(prefix + '-year').value;
    const month = document.getElementById(prefix + '-month').value.padStart(2, '0');
    const day = document.getElementById(prefix + '-day').value.padStart(2, '0');
    return `${year}-${month}-${day}`;
}

function setDateInDropdowns(prefix, date) {
    const d = new Date(date);
    document.getElementById(prefix + '-year').value = d.getFullYear();
    document.getElementById(prefix + '-month').value = d.getMonth() + 1;
    document.getElementById(prefix + '-day').value = d.getDate();
}

// ============================================
// FIND UNBILLED CLIENTS
// ============================================

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

function toggleSelectAll() {
    const selectAll = document.getElementById('select-all');
    const checkboxes = document.querySelectorAll('.client-checkbox');
    checkboxes.forEach(cb => cb.checked = selectAll.checked);
}

// ============================================
// GENERATE STATEMENTS
// ============================================

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
        headers: {
            'Content-Type': 'application/json'
        },
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

// ============================================
// FILTER AND SEARCH
// ============================================

function filterTable() {
    const searchTerm = document.getElementById('search-input').value.toLowerCase();
    const rows = document.querySelectorAll('.statement-row');
    
    rows.forEach(row => {
        const status = row.dataset.status;
        const client = row.dataset.client;
        const file = row.dataset.file;
        
        const statusMatch = currentFilter === 'all' || status === currentFilter;
        const searchMatch = !searchTerm || 
            client.includes(searchTerm) || 
            file.includes(searchTerm);
        
        row.style.display = (statusMatch && searchMatch) ? '' : 'none';
    });
    
    // Update clear button visibility
    updateClearButton();
}

function updateClearButton() {
    const searchInput = document.getElementById('search-input');
    const clearBtn = document.querySelector('.clear-search');
    if (searchInput && clearBtn) {
        clearBtn.style.display = searchInput.value ? 'block' : 'none';
    }
}

function clearSearch() {
    const searchInput = document.getElementById('search-input');
    if (searchInput) {
        searchInput.value = '';
        filterTable();
    }
}

// ============================================
// STATEMENT ACTIONS
// ============================================

function markSent(portionId) {
    fetch(`/statements/mark-sent/${portionId}`, {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        console.log('Email method:', data.email_method);
        if (data.success) {
            // Store portion_id in data for mailto fallback
            data.portion_id = portionId;
            
            // Trigger email client
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

function triggerMailtoEmail(data) {
    const subject = encodeURIComponent(data.subject);
    const body = encodeURIComponent(data.body + '\n\n[Please attach the downloaded PDF]');
    const mailto = `mailto:${data.recipient_email}?subject=${subject}&body=${body}`;
    
    // Download PDF so user can attach it
    const pdfLink = document.createElement('a');
    pdfLink.href = `/statements/pdf/${data.portion_id}`;
    pdfLink.download = '';
    pdfLink.click();
    
    // Small delay then open mailto
    setTimeout(() => {
        window.location.href = mailto;
        // Reload after mailto opens
        setTimeout(() => window.location.reload(), 1000);
    }, 300);
}

function triggerAppleScriptEmail(data) {
    fetch('/statements/send-applescript-email', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
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
            // Success - reload page
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

let currentPaymentPortionId = null;

function showPaymentForm(portionId, amountOwing) {
    currentPaymentPortionId = portionId;
    const input = document.getElementById('payment-amount');
    input.value = amountOwing.toFixed(2);
    input.dataset.max = amountOwing.toFixed(2);
    input.max = amountOwing.toFixed(2);
    document.getElementById('payment-modal').classList.add('visible');
}

function hidePaymentModal() {
    document.getElementById('payment-modal').classList.remove('visible');
    currentPaymentPortionId = null;
}

function confirmPayment() {
    const amountInput = document.getElementById('payment-amount');
    const amount = parseFloat(amountInput.value);
    
    // Validation
    if (isNaN(amount) || amount <= 0) {
        showSuccessModal('Please enter a valid positive amount', 'Invalid Amount');
        return;
    }
    
    // Get max amount from data attribute
    const maxAmount = parseFloat(amountInput.dataset.max);
    if (amount > maxAmount) {
        showSuccessModal(`Amount cannot exceed $${maxAmount.toFixed(2)}`, 'Invalid Amount');
        return;
    }
    
    fetch('/statements/mark-paid', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
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

// Close modal when clicking outside
document.getElementById('payment-modal').addEventListener('click', function(e) {
    if (e.target === this) {
        hidePaymentModal();
    }
});

// Format amount to 2 decimal places on blur
document.getElementById('payment-amount').addEventListener('blur', function() {
    const val = parseFloat(this.value);
    if (!isNaN(val)) {
        this.value = val.toFixed(2);
    }
});

function showSuccessModal(message, title) {
    document.getElementById('success-title').textContent = title || 'Success';
    document.getElementById('success-message').textContent = message;
    document.getElementById('success-modal').classList.add('visible');
}

function closeSuccessModal() {
    document.getElementById('success-modal').classList.remove('visible');
    window.location.reload();
}