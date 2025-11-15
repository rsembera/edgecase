// Client File View JavaScript - Extracted from client_file.html

function toggleYear(yearId) {
    const content = document.getElementById(yearId + '-content');
    const icon = document.getElementById(yearId + '-icon');
    
    if (content.style.display === 'none') {
        content.style.display = 'block';
        icon.textContent = '▼';
    } else {
        content.style.display = 'none';
        icon.textContent = '▶';
    }
}

function toggleMonth(monthId) {
    const content = document.getElementById(monthId + '-content');
    const icon = document.getElementById(monthId + '-icon');
    
    if (content.style.display === 'none') {
        content.style.display = 'block';
        icon.textContent = '▼';
    } else {
        content.style.display = 'none';
        icon.textContent = '▶';
    }
}

// Dropdown toggle for filters and type selector
function toggleDropdown(dropdownId) {
    const dropdown = document.getElementById(dropdownId);
    const allDropdowns = document.querySelectorAll('[id$="-dropdown"]');
    
    // Close all other dropdowns
    allDropdowns.forEach(d => {
        if (d.id !== dropdownId) {
            d.style.display = 'none';
        }
    });
    
    // Toggle this dropdown (check for both 'none' and empty string)
    if (dropdown.style.display === 'none' || dropdown.style.display === '') {
        dropdown.style.display = 'block';
    } else {
        dropdown.style.display = 'none';
    }
}

// Close dropdowns when clicking outside
document.addEventListener('click', function(e) {
    if (!e.target.closest('.type-badge') && !e.target.closest('.dropdown-btn') && !e.target.closest('[id$="-dropdown"]')) {
        document.querySelectorAll('[id$="-dropdown"]').forEach(d => d.style.display = 'none');
    }
});

// Update class filter button text as checkboxes change
document.querySelectorAll('#filter-form input[type="checkbox"]').forEach(checkbox => {
    checkbox.addEventListener('change', function() {
        const checkedCount = document.querySelectorAll('#filter-form input[type="checkbox"]:checked').length;
        const filterButton = document.getElementById('class-filter-button');
        if (filterButton) {
            filterButton.textContent = `Filter: ${checkedCount} type${checkedCount !== 1 ? 's' : ''} ▾`;
        }
    });
});
