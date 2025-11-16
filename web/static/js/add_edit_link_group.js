// Get all clients data from hidden div
const allClientsData = JSON.parse(document.getElementById('all-clients-data').textContent);
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
        const fullName = `${client.first_name} ${client.last_name}`.toLowerCase();
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
                <span class="client-name">${client.first_name} ${client.last_name}</span>
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

// Select a client
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
        <span class="client-name">${client.first_name} ${client.last_name}</span>
        <span class="client-file">${client.file_number}</span>
        <button type="button" class="remove-client" onclick="removeClient(${clientId})">×</button>
    `;
    selectedContainer.appendChild(clientDiv);
    
    // Clear search
    searchInput.value = '';
    searchResults.classList.remove('active');
    searchResults.innerHTML = '';
}

// Remove a client
function removeClient(clientId) {
    selectedClients = selectedClients.filter(id => id !== clientId);
    
    // Remove from display
    const clientDiv = document.querySelector(`.selected-client[data-client-id="${clientId}"]`);
    if (clientDiv) {
        clientDiv.remove();
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
    
    const billingArrangement = document.querySelector('input[name="billing_arrangement"]:checked').value;
    
    // Submit form data
    const formData = {
        client_ids: selectedClients,
        billing_arrangement: billingArrangement
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
        alert('Error saving link group: ' + error.message);
    });
});