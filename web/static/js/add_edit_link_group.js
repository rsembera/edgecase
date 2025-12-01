/**
 * Add/Edit Link Group JavaScript - EdgeCase Equalizer
 * Handles link group creation/editing with client search,
 * member selection, and per-member fee configuration.
 */

// Get all clients data from hidden div
const allClientsData = JSON.parse(document.getElementById('all-clients-data').textContent);

// Get existing group data (if editing)
const groupDataElement = document.getElementById('group-data');
const existingGroupData = groupDataElement ? JSON.parse(groupDataElement.textContent) : null;

let selectedClients = [];

// Initialize with existing selected clients (if editing)
document.addEventListener('DOMContentLoaded', function() {
    const existingClients = document.querySelectorAll('.selected-client');
    existingClients.forEach(el => {
        const clientId = parseInt(el.dataset.clientId);
        if (!selectedClients.includes(clientId)) {
            selectedClients.push(clientId);
        }
    });
    
    // Update member fees display if clients already selected
    if (selectedClients.length > 0) {
        updateMemberFees();
    }
});

// Client search functionality
const searchInput = document.getElementById('client-search');
const searchResults = document.getElementById('search-results');

searchInput.addEventListener('input', function(e) {
    const query = e.target.value.toLowerCase().trim();
    
    if (query.length === 0) {
        searchResults.classList.remove('active');
        searchResults.innerHTML = '';
        return;
    }
    
    // Filter clients
    const matches = allClientsData.filter(client => {
        // Skip already selected clients
        if (selectedClients.includes(client.id)) return false;
        
        // Search in name and file number
        const fullName = `${client.first_name} ${client.middle_name || ''} ${client.last_name}`.toLowerCase();
        const fileNumber = client.file_number.toLowerCase();
        
        return fullName.includes(query) || fileNumber.includes(query);
    });
    
    // Display results
    if (matches.length > 0) {
        searchResults.innerHTML = matches.map(client => `
            <div class="search-result" onclick="selectClient(${client.id})">
                <span class="client-badge" style="background-color: ${client.type.color}">
                    ${client.type.name}
                </span>
                <span class="client-name">${client.first_name} ${client.middle_name || ''} ${client.last_name}</span>
                <span class="client-file">${client.file_number}</span>
            </div>
        `).join('');
        searchResults.classList.add('active');
    } else {
        searchResults.innerHTML = '<div style="padding: 1rem; text-align: center; color: #9CA3AF;">No clients found</div>';
        searchResults.classList.add('active');
    }
});

// Close search results when clicking outside
document.addEventListener('click', function(e) {
    if (!searchInput.contains(e.target) && !searchResults.contains(e.target)) {
        searchResults.classList.remove('active');
    }
});

/**
 * Select a client and add them to the group
 * @param {number} clientId - ID of client to add
 */
function selectClient(clientId) {
    if (selectedClients.includes(clientId)) return;
    
    const client = allClientsData.find(c => c.id === clientId);
    if (!client) return;
    
    selectedClients.push(clientId);
    
    // Add to selected clients display
    const selectedContainer = document.getElementById('selected-clients');
    const clientDiv = document.createElement('div');
    clientDiv.className = 'selected-client';
    clientDiv.dataset.clientId = clientId;
    clientDiv.innerHTML = `
        <span class="client-badge" style="background-color: ${client.type.color}">
            ${client.type.name}
        </span>
        <span class="client-name">${client.first_name} ${client.middle_name || ''} ${client.last_name}</span>
        <span class="client-file">${client.file_number}</span>
        <button type="button" class="remove-client" onclick="removeClient(${clientId})">×</button>
    `;
    selectedContainer.appendChild(clientDiv);
    
    // Update member fees
    updateMemberFees();
    
    // Clear search
    searchInput.value = '';
    searchResults.classList.remove('active');
    searchResults.innerHTML = '';
}

/**
 * Remove a client from the group
 * @param {number} clientId - ID of client to remove
 */
function removeClient(clientId) {
    selectedClients = selectedClients.filter(id => id !== clientId);
    
    // Remove from display
    const clientDiv = document.querySelector(`.selected-client[data-client-id="${clientId}"]`);
    if (clientDiv) {
        clientDiv.remove();
    }
    
    // Update member fees
    updateMemberFees();
}

/**
 * Update the member fees section based on selected clients
 */
function updateMemberFees() {
    const feesSection = document.getElementById('member-fees-section');
    const feesContainer = document.getElementById('member-fees-container');
    
    if (selectedClients.length === 0) {
        feesSection.style.display = 'none';
        feesContainer.innerHTML = '';
        return;
    }
    
    feesSection.style.display = 'block';
    
    // Build fee input rows for each selected client
    feesContainer.innerHTML = selectedClients.map(clientId => {
        const client = allClientsData.find(c => c.id === clientId);
        if (!client) return '';
        
        // Get fees: use saved fees if editing, otherwise use client type defaults
        let defaultBase, defaultTax, defaultTotal;

        if (existingGroupData && existingGroupData.members) {
            const savedMember = existingGroupData.members.find(m => m.id === clientId);
            if (savedMember && savedMember.member_total_fee !== null) {
                defaultBase = savedMember.member_base_fee || 0;
                defaultTax = savedMember.member_tax_rate || 0;
                defaultTotal = savedMember.member_total_fee || 0;
            } else {
                defaultBase = client.type.session_base_price || 0;
                defaultTax = client.type.session_tax_rate || 0;
                defaultTotal = client.type.session_fee || 0;
            }
        } else {
            defaultBase = client.profile_base_fee || 0;
            defaultTax = client.profile_tax_rate || 0;
            defaultTotal = client.profile_total_fee || 0;
        }
        
        return `
            <div class="member-fee-row" data-client-id="${clientId}">
                <div class="member-info">
                    <span class="client-badge" style="background-color: ${client.type.color}">
                        ${client.type.name}
                    </span>
                    <strong>${client.first_name} ${client.middle_name || ''} ${client.last_name}</strong>
                    <span style="color: #718096;">${client.file_number}</span>
                </div>
                <div class="fee-inputs">
                    <div class="fee-input-group">
                        <label>Base Fee</label>
                        <input type="number" 
                               name="base_fee_${clientId}" 
                               class="base-fee"
                               step="0.01" 
                               min="0"
                               value="${defaultBase.toFixed(2)}"
                               data-client-id="${clientId}"
                               onchange="calculateFee(${clientId}, 'base')">
                    </div>
                    <div class="fee-input-group">
                        <label>Tax Rate (%)</label>
                        <input type="number" 
                               name="tax_rate_${clientId}" 
                               class="tax-rate"
                               step="0.01" 
                               min="0"
                               value="${defaultTax.toFixed(2)}"
                               data-client-id="${clientId}"
                               onchange="calculateFee(${clientId}, 'tax')">
                    </div>
                    <div class="fee-input-group">
                        <label>Total Fee</label>
                        <input type="number" 
                               name="total_fee_${clientId}" 
                               class="total-fee"
                               step="0.01" 
                               min="0"
                               value="${defaultTotal.toFixed(2)}"
                               data-client-id="${clientId}"
                               onchange="calculateFee(${clientId}, 'total')">
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

/**
 * Three-way fee calculation for member fees
 * @param {number} clientId - ID of client
 * @param {string} changedField - Which field was changed: 'base', 'tax', or 'total'
 */
function calculateFee(clientId, changedField) {
    const row = document.querySelector(`.member-fee-row[data-client-id="${clientId}"]`);
    if (!row) return;
    
    const baseInput = row.querySelector('.base-fee');
    const taxInput = row.querySelector('.tax-rate');
    const totalInput = row.querySelector('.total-fee');
    
    const base = parseFloat(baseInput.value) || 0;
    const taxRate = parseFloat(taxInput.value) || 0;
    const total = parseFloat(totalInput.value) || 0;
    
    if (changedField === 'base' || changedField === 'tax') {
        const calculatedTotal = base * (1 + taxRate / 100);
        totalInput.value = calculatedTotal.toFixed(2);
    } else if (changedField === 'total') {
        if (taxRate > 0) {
            const calculatedBase = total / (1 + taxRate / 100);
            baseInput.value = calculatedBase.toFixed(2);
        } else {
            baseInput.value = total.toFixed(2);
        }
    }
}

// Form submission
document.getElementById('link-group-form').addEventListener('submit', function(e) {
    e.preventDefault();
    
    // Validation
    if (selectedClients.length < 2) {
        alert('Please select at least 2 clients for the link group');
        return;
    }
    
    const format = document.getElementById('format').value;
    if (!format) {
        alert('Please select a session format');
        return;
    }
    
    // Collect member fees
    const memberFees = {};
    selectedClients.forEach(clientId => {
        const baseInput = document.querySelector(`input[name="base_fee_${clientId}"]`);
        const taxInput = document.querySelector(`input[name="tax_rate_${clientId}"]`);
        const totalInput = document.querySelector(`input[name="total_fee_${clientId}"]`);
        
        memberFees[clientId] = {
            base_fee: parseFloat(baseInput.value) || 0,
            tax_rate: parseFloat(taxInput.value) || 0,
            total_fee: parseFloat(totalInput.value) || 0
        };
    });
    
    const sessionDuration = parseInt(document.getElementById('session_duration').value) || 50;

    const formData = {
        client_ids: selectedClients,
        format: format,
        session_duration: sessionDuration,
        member_fees: memberFees
    };
    
    fetch(window.location.href, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(formData)
    })
    .then(response => {
        if (response.ok) {
            window.location.href = '/links';
        } else {
            return response.text().then(text => {
                throw new Error(text || 'Error saving link group');
            });
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showErrorModal(error.message);
    });
});

/**
 * Show error modal with message
 * @param {string} message - Error message to display
 */
function showErrorModal(message) {
    document.getElementById('error-message').textContent = message;
    document.getElementById('error-modal').style.display = 'flex';
}

/**
 * Close the error modal
 */
function closeErrorModal() {
    document.getElementById('error-modal').style.display = 'none';
}
