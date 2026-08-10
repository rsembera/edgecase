/**
 * Outstanding Statements JavaScript - EdgeCase Equalizer
 * Handles statement listing, filtering, generation, payments, and write-offs.
 */

// ============================================================
// UTILITIES
// ============================================================
// escapeHtml() now lives in shared_utils.js

// ============================================================
// STATE
// ============================================================

let currentFilter = 'all';
let currentPaymentPortionId = null;
let currentProposal = null;
let proposalDebounce = null;
let paymentDatePicker = null;
let currentWriteOffPortionId = null;
let currentWriteOffAmount = 0;
let currentEmailPortionId = null;
let startDatePicker = null;
let endDatePicker = null;

// ============================================================
// INITIALIZATION
// ============================================================

document.addEventListener('DOMContentLoaded', function() {
    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }
    
    // Initialize date pickers
    initStatementPickers();
    
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
    
    // Payment amount - format on blur, re-propose the split on input
    const paymentAmount = document.getElementById('payment-amount');
    if (paymentAmount) {
        paymentAmount.addEventListener('blur', function() {
            const val = parseFloat(this.value);
            if (!isNaN(val)) this.value = val.toFixed(2);
        });
        paymentAmount.addEventListener('input', onPaymentAmountChanged);
    }

    // Payment date picker (same custom picker as the generate section)
    const paymentDateContainer = document.getElementById('payment-date-picker');
    if (paymentDateContainer) {
        paymentDatePicker = new DatePicker(paymentDateContainer, {
            initialDate: new Date(),
            onSelect: (date) => setPaymentDate(date)
        });
        setPaymentDate(new Date());
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
// DATE PICKER FUNCTIONS
// ============================================================

/**
 * Initialize date pickers for statement generation
 */
function initStatementPickers() {
    const dataEl = document.getElementById('statements-data');
    if (!dataEl) return;
    
    const data = JSON.parse(dataEl.textContent);
    
    const startDateInput = document.getElementById('start_date');
    const endDateInput = document.getElementById('end_date');
    
    // Parse initial dates
    const startDate = new Date(
        data.defaultStartYear,
        data.defaultStartMonth - 1,
        data.defaultStartDay
    );
    const endDate = new Date(
        data.defaultEndYear,
        data.defaultEndMonth - 1,
        data.defaultEndDay
    );
    
    // Initialize start date picker
    const startContainer = document.getElementById('start-date-picker');
    if (startContainer) {
        startDatePicker = new DatePicker(startContainer, {
            initialDate: startDate,
            onSelect: (date) => {
                const y = date.getFullYear();
                const m = (date.getMonth() + 1).toString().padStart(2, '0');
                const d = date.getDate().toString().padStart(2, '0');
                startDateInput.value = `${y}-${m}-${d}`;
            }
        });
    }
    
    // Initialize end date picker
    const endContainer = document.getElementById('end-date-picker');
    if (endContainer) {
        endDatePicker = new DatePicker(endContainer, {
            initialDate: endDate,
            onSelect: (date) => {
                const y = date.getFullYear();
                const m = (date.getMonth() + 1).toString().padStart(2, '0');
                const d = date.getDate().toString().padStart(2, '0');
                endDateInput.value = `${y}-${m}-${d}`;
            }
        });
    }
}

/**
 * Get date string from hidden input
 * @param {string} prefix - Prefix for element ID ('start' or 'end')
 * @returns {string} Date in YYYY-MM-DD format
 */
function getDateFromDropdowns(prefix) {
    // Now reads from hidden inputs instead of dropdowns
    return document.getElementById(prefix + '_date').value;
}

/**
 * Set date using the picker
 * @param {string} prefix - Prefix ('start' or 'end')
 * @param {string} date - Date string parseable by Date constructor
 */
function setDateInDropdowns(prefix, date) {
    const d = new Date(date);
    if (prefix === 'start' && startDatePicker) {
        startDatePicker.setDate(d);
    } else if (prefix === 'end' && endDatePicker) {
        endDatePicker.setDate(d);
    }
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
                            <span class="client-name">${escapeHtml(client.name)}</span>
                            <span class="file-number">${escapeHtml(client.file_number)}</span>
                            <span class="unbilled-amount">$${client.unbilled_total.toFixed(2)}</span>
                        </div>
                    `;
                });
                
                html += `
                        </div>
                        <div class="generate-actions">
                            <button class="btn" onclick="generateStatements(this)">Generate Statements</button>
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
 * @param {HTMLButtonElement} [btnEl] - Trigger button (passed via onclick="...(this)")
 */
function generateStatements(btnEl) {
    const btn = btnEl || resolveEventButton();
    const checkboxes = document.querySelectorAll('.client-checkbox:checked');
    const clientIds = Array.from(checkboxes).map(cb => parseInt(cb.value));

    if (clientIds.length === 0) {
        showSuccessModal('Please select at least one client', 'No Selection');
        return;
    }

    const startDate = getDateFromDropdowns('start');
    const endDate = getDateFromDropdowns('end');

    withButtonDisabled(btn, () => fetch('/statements/generate', {
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
            // Build smart message based on statements vs portions
            let message;
            const stmtCount = data.count;
            const portionCount = data.portion_count || stmtCount;
            
            if (portionCount > stmtCount) {
                // Guardian billing created extra portions
                const stmtWord = stmtCount === 1 ? 'statement' : 'statements';
                const portionWord = portionCount === 1 ? 'portion' : 'portions';
                message = `Generated ${stmtCount} ${stmtWord} (${portionCount} ${portionWord})`;
            } else {
                const word = stmtCount === 1 ? 'statement' : 'statements';
                message = `Generated ${stmtCount} ${word}`;
            }

            // Clients whose credits outweighed their charges get no
            // statement — say so, or the missing statement looks like a
            // bug. Their entries stay unbilled and carry forward.
            const skipped = data.skipped || [];
            if (skipped.length > 0) {
                // Negative totals format as -$40.00, not $-40.00
                const names = skipped.map(s =>
                    `${s.name} (-$${Math.abs(s.total).toFixed(2)})`).join(', ');
                message += `. No statement for ${names} — credits exceed charges `
                         + `for this period, so those entries stay unbilled and `
                         + `will appear on the next statement that covers them.`;
            }

            showSuccessModal(message, 'Success');
        } else {
            alert('Error: ' + (data.error || 'Unknown error'));
        }
    })
    .catch(error => {
        console.error('Error generating statements:', error);
        alert('Error generating statements');
    }), 'Generating...');
}

// ============================================================
// STATEMENT ACTIONS
// ============================================================

/**
 * Open the pre-send email review modal for a statement portion.
 *
 * Fetches the composed email (recipient/subject/body) from the read-only
 * preview route — NOTHING is marked sent and no Communication entry exists
 * yet, so Cancel truly aborts. The user can edit the subject/body; whatever
 * they approve is posted to mark-sent, which records it verbatim as the
 * Communication entry (the client file matches the email actually sent).
 * @param {number} portionId - Statement portion ID
 */
function markSent(portionId) {
    const btn = resolveEventButton();
    withButtonDisabled(btn, () => fetch(`/statements/email-preview/${portionId}`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                currentEmailPortionId = portionId;
                document.getElementById('email-recipient').textContent =
                    data.recipient_email || '(no email on file — Mail will open without a recipient)';
                document.getElementById('email-subject').value = data.subject;
                document.getElementById('email-body').value = data.body;
                document.getElementById('email-modal').classList.add('visible');
            } else {
                alert('Error: ' + (data.error || 'Unknown error'));
            }
        })
        .catch(error => {
            console.error('Error loading email preview:', error);
            alert('Error loading email preview');
        }));
}

/**
 * Hide the email review modal without sending (no server side effects).
 */
function hideEmailModal() {
    document.getElementById('email-modal').classList.remove('visible');
    currentEmailPortionId = null;
}

/**
 * Confirm the reviewed email: mark the portion sent (creating the
 * Communication entry with the edited text) and trigger the email.
 */
function confirmSendEmail() {
    const btn = resolveEventButton();
    const portionId = currentEmailPortionId;
    if (!portionId) return;

    const subject = document.getElementById('email-subject').value.trim();
    const body = document.getElementById('email-body').value;

    withButtonDisabled(btn, () => fetch(`/statements/mark-sent/${portionId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ subject: subject, body: body })
    })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                hideEmailModal();
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
        }), 'Sending...');
}

/**
 * Generate PDF only (no email) - opens in new window or Preview
 * @param {number} portionId - Statement portion ID
 */
function generateOnly(portionId) {
    const btn = resolveEventButton();

    // Check if running in desktop mode
    const isDesktop = window.pywebview && window.pywebview.api && window.pywebview.api.open_pdf;

    // In browser mode, open window immediately to avoid popup blocker
    const pdfWindow = isDesktop ? null : window.open('about:blank', '_blank');

    withButtonDisabled(btn, () => fetch(`/statements/mark-sent/${portionId}?skip_email=1`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                const pdfUrl = `/statements/view-pdf/${portionId}`;
                if (isDesktop) {
                    window.pywebview.api.open_pdf(pdfUrl);
                } else {
                    pdfWindow.location.href = pdfUrl;
                }
                setTimeout(() => window.location.reload(), 500);
            } else {
                if (pdfWindow) pdfWindow.close();
                alert('Error: ' + (data.error || 'Unknown error'));
            }
        })
        .catch(error => {
            if (pdfWindow) pdfWindow.close();
            console.error('Error generating statement:', error);
            alert('Error generating statement');
        }));
}

/**
 * Trigger mailto link with PDF download
 * @param {Object} data - Email data from server
 */
function triggerMailtoEmail(data) {
    const subject = encodeURIComponent(data.subject);
    const body = encodeURIComponent(data.body + '\n\n[Please attach the downloaded PDF]');
    const mailto = `mailto:${data.recipient_email}?subject=${subject}&body=${body}`;
    
    // Check if running in desktop mode
    const isDesktop = window.pywebview && window.pywebview.api && window.pywebview.api.open_external_url;
    
    if (isDesktop) {
        // Desktop mode: use Python API to download PDF and open mailto
        window.pywebview.api.download_file(`/statements/pdf/${data.portion_id}`);
        setTimeout(() => {
            window.pywebview.api.open_external_url(mailto);
            setTimeout(() => window.location.reload(), 1000);
        }, 300);
    } else {
        // Browser mode: use standard link clicks
        const pdfLink = document.createElement('a');
        pdfLink.href = `/statements/pdf/${data.portion_id}`;
        pdfLink.download = '';
        pdfLink.click();
        
        setTimeout(() => {
            window.location.href = mailto;
            setTimeout(() => window.location.reload(), 1000);
        }, 300);
    }
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
            // Delay reload so Mail.app keeps focus after activate
            setTimeout(() => window.location.reload(), 2000);
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
//
// Payment is recorded against a PAYER, not a statement: one deposit can
// settle several statements, which is the whole point of this modal. The
// oldest-first split is proposed by the server (core/billing.propose_
// allocation) rather than recomputed here, so there is only one copy of
// that arithmetic. This file only sums and displays.

/**
 * Open the payment modal for the payer behind a statement portion.
 * @param {number} portionId - Any statement portion belonging to the payer
 */
function showPaymentForm(portionId) {
    currentPaymentPortionId = portionId;

    document.getElementById('payment-error').style.display = 'none';
    document.getElementById('payment-notes').value = '';
    document.getElementById('allocation-rows').innerHTML = '';
    document.getElementById('allocation-summary').textContent = '';

    // Default the date to today, every time the modal opens
    const today = new Date();
    setPaymentDate(today);
    if (paymentDatePicker) {
        paymentDatePicker.setDate(today, false);
    }

    fetch(`/statements/payment-proposal?portion_id=${portionId}`)
        .then(response => response.json())
        .then(data => {
            if (!data.success) {
                alert('Error: ' + (data.error || 'Unknown error'));
                return;
            }
            currentProposal = data;
            document.getElementById('payment-amount').value = data.total_owing.toFixed(2);
            renderPayerLine(data);
            renderAllocationRows(data);
            updateAllocationSummary();
            document.getElementById('payment-modal').classList.add('visible');
        })
        .catch(error => {
            console.error('Error loading payment proposal:', error);
            alert('Error loading outstanding statements for this client');
        });
}

/**
 * Write the payer line: who this payment is from, and any credit held.
 * @param {Object} data - Proposal payload
 */
function renderPayerLine(data) {
    let text = data.client_name + ' (' + data.file_number + ')';
    if (data.payer_label) {
        text += ' — ' + data.payer_label;
    }
    if (data.credit > 0) {
        text += ` · $${data.credit.toFixed(2)} on account`;
    }
    document.getElementById('payment-payer').textContent = text;
}

/**
 * Render one row per open statement, with the proposed amount pre-filled.
 * @param {Object} data - Proposal payload
 */
function renderAllocationRows(data) {
    const tbody = document.getElementById('allocation-rows');

    if (!data.portions || data.portions.length === 0) {
        tbody.innerHTML = `
            <tr><td colspan="3" class="allocation-empty">
                Nothing outstanding — the full amount will be held as credit.
            </td></tr>`;
        return;
    }

    tbody.innerHTML = data.portions.map(portion => `
        <tr>
            <td>
                ${escapeHtml(portion.description)}
                <span class="allocation-date">${escapeHtml(portion.date)}</span>
            </td>
            <td class="numeric">$${portion.amount_owing.toFixed(2)}</td>
            <td class="numeric">
                <input type="number" class="allocation-input"
                       step="0.01" min="0" max="${portion.amount_owing}"
                       data-portion-id="${portion.portion_id}"
                       data-owing="${portion.amount_owing}"
                       value="${portion.proposed.toFixed(2)}"
                       oninput="onAllocationEdited()">
            </td>
        </tr>
    `).join('');
}

/**
 * Re-ask the server for a split when the amount changes.
 *
 * Changing the amount re-proposes from scratch, discarding manual edits —
 * the amount is the fact ("this is what arrived"), and the split is a
 * consequence of it.
 */
function onPaymentAmountChanged() {
    if (!currentPaymentPortionId) return;

    clearTimeout(proposalDebounce);
    proposalDebounce = setTimeout(() => {
        const amount = parseFloat(document.getElementById('payment-amount').value);
        if (isNaN(amount) || amount < 0) {
            updateAllocationSummary();
            return;
        }

        fetch(`/statements/payment-proposal?portion_id=${currentPaymentPortionId}`
              + `&amount=${amount}`)
            .then(response => response.json())
            .then(data => {
                if (!data.success) return;
                currentProposal = data;
                renderAllocationRows(data);
                updateAllocationSummary();
            })
            .catch(error => console.error('Error re-proposing split:', error));
    }, 300);
}

/**
 * A manual edit only changes the summary — the split is now the user's.
 */
function onAllocationEdited() {
    updateAllocationSummary();
}

/**
 * Total of the allocation inputs.
 * @returns {number} Sum in dollars
 */
function allocationTotal() {
    let total = 0;
    document.querySelectorAll('.allocation-input').forEach(input => {
        const value = parseFloat(input.value);
        if (!isNaN(value)) total += value;
    });
    return Math.round(total * 100) / 100;
}

/**
 * Describe what will happen: applied, held as credit, or over-applied.
 */
function updateAllocationSummary() {
    const summary = document.getElementById('allocation-summary');
    const amount = parseFloat(document.getElementById('payment-amount').value);
    const applied = allocationTotal();

    if (isNaN(amount)) {
        summary.textContent = '';
        summary.classList.remove('over');
        return;
    }

    const remainder = Math.round((amount - applied) * 100) / 100;

    if (remainder < 0) {
        summary.textContent = `Applied $${applied.toFixed(2)}, which is more than `
                            + `the $${amount.toFixed(2)} received.`;
        summary.classList.add('over');
    } else if (remainder > 0) {
        summary.textContent = `Applied $${applied.toFixed(2)} · $${remainder.toFixed(2)} `
                            + `held as credit on the client's account.`;
        summary.classList.remove('over');
    } else {
        summary.textContent = `Applied $${applied.toFixed(2)} of $${amount.toFixed(2)}.`;
        summary.classList.remove('over');
    }
}

/**
 * Store the chosen payment date as YYYY-MM-DD.
 * @param {Date} date
 */
function setPaymentDate(date) {
    const y = date.getFullYear();
    const m = (date.getMonth() + 1).toString().padStart(2, '0');
    const d = date.getDate().toString().padStart(2, '0');
    document.getElementById('payment-date').value = `${y}-${m}-${d}`;
}

/**
 * Hide the payment modal
 */
function hidePaymentModal() {
    document.getElementById('payment-modal').classList.remove('visible');
    currentPaymentPortionId = null;
    currentProposal = null;
}

/**
 * Submit the payment with its allocation split.
 */
function confirmPayment() {
    const btn = resolveEventButton();
    const errorBox = document.getElementById('payment-error');
    errorBox.style.display = 'none';

    const showError = (message) => {
        errorBox.textContent = message;
        errorBox.style.display = 'block';
    };

    const amount = parseFloat(document.getElementById('payment-amount').value);
    if (isNaN(amount) || amount <= 0) {
        showError('Enter the amount received.');
        return;
    }

    const allocations = [];
    let invalid = null;
    document.querySelectorAll('.allocation-input').forEach(input => {
        const value = parseFloat(input.value);
        if (isNaN(value) || value === 0) return;
        if (value < 0) {
            invalid = 'Amounts applied to a statement cannot be negative.';
            return;
        }
        if (value > parseFloat(input.dataset.owing) + 0.001) {
            invalid = 'An amount applied is more than that statement has outstanding.';
            return;
        }
        allocations.push({
            portion_id: parseInt(input.dataset.portionId),
            amount: value
        });
    });

    if (invalid) {
        showError(invalid);
        return;
    }

    if (allocationTotal() > amount + 0.001) {
        showError('The amounts applied add up to more than the payment received.');
        return;
    }

    withButtonDisabled(btn, () => fetch('/statements/record-payment', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            portion_id: currentPaymentPortionId,
            payment_amount: amount,
            payment_date: document.getElementById('payment-date').value,
            notes: document.getElementById('payment-notes').value.trim(),
            allocations: allocations
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            hidePaymentModal();
            let message = 'Payment recorded';
            if (data.credit > 0) {
                message += `. $${data.credit.toFixed(2)} is held as credit on the `
                         + `client's account.`;
            }
            showSuccessModal(message, 'Success');
        } else {
            showError(data.error || 'Unknown error');
        }
    })
    .catch(error => {
        console.error('Error recording payment:', error);
        showError('Error recording payment');
    }), 'Saving...');
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
    document.getElementById('writeoff-error').style.display = 'none';
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
    const btn = resolveEventButton();
    const reason = document.getElementById('writeoff-reason').value;
    const note = document.getElementById('writeoff-note').value.trim();
    const errorBox = document.getElementById('writeoff-error');

    // Clear previous error
    errorBox.style.display = 'none';

    if (!reason) {
        errorBox.textContent = 'Please select a reason';
        errorBox.style.display = 'block';
        return;
    }

    if (reason === 'other' && !note) {
        errorBox.textContent = 'Please provide an explanation';
        errorBox.style.display = 'block';
        return;
    }

    withButtonDisabled(btn, () => fetch('/statements/write-off', {
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
    }), 'Saving...');
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
