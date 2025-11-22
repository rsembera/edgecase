// Ledger Page JavaScript

// Year/month toggle functions
function toggleYear(yearId) {
    const yearContent = document.getElementById(`year-${yearId}`);
    const arrow = document.getElementById(`year-arrow-${yearId}`);
    
    if (yearContent.classList.contains('expanded')) {
        yearContent.classList.remove('expanded');
        arrow.textContent = '▼';
    } else {
        yearContent.classList.add('expanded');
        arrow.textContent = '▲';
    }
}

function toggleMonth(monthId) {
    const monthContent = document.getElementById(`month-${monthId}`);
    const arrow = document.getElementById(`month-arrow-${monthId}`);
    
    if (monthContent.classList.contains('expanded')) {
        monthContent.classList.remove('expanded');
        arrow.textContent = '▼';
    } else {
        monthContent.classList.add('expanded');
        arrow.textContent = '▲';
    }
}

// Search entries
function searchEntries() {
    const searchInput = document.getElementById('search-input');
    const searchTerm = searchInput.value.toLowerCase();
    const rows = document.querySelectorAll('.entry-row');
    
    rows.forEach(row => {
        const description = row.dataset.description.toLowerCase();
        const amount = row.dataset.amount;
        
        if (description.includes(searchTerm) || amount.includes(searchTerm)) {
            row.style.display = '';
        } else {
            row.style.display = 'none';
        }
    });
}

// Add Entry dropdown toggle
function toggleAddDropdown() {
    const dropdown = document.getElementById('add-dropdown');
    
    if (dropdown.style.display === 'none' || dropdown.style.display === '') {
        dropdown.style.display = 'block';
    } else {
        dropdown.style.display = 'none';
    }
}

// Close dropdown when clicking outside
document.addEventListener('click', function(event) {
    const dropdown = document.getElementById('add-dropdown');
    const addBtn = document.getElementById('add-entry-btn');
    
    if (dropdown && addBtn) {
        if (!addBtn.contains(event.target) && !dropdown.contains(event.target)) {
            dropdown.style.display = 'none';
        }
    }
});

// Expand most recent year/month on page load
document.addEventListener('DOMContentLoaded', function() {
    // Find the first year header and expand it
    const firstYearHeader = document.querySelector('.year-header');
    if (firstYearHeader) {
        const yearId = firstYearHeader.getAttribute('onclick').match(/'([^']+)'/)[1];
        toggleYear(yearId);
        
        // Expand the first month in that year
        const firstMonthHeader = document.querySelector(`#year-${yearId} .month-header`);
        if (firstMonthHeader) {
            const monthId = firstMonthHeader.getAttribute('onclick').match(/'([^']+)'/)[1];
            toggleMonth(monthId);
        }
    }
});
