// Ledger Page JavaScript

// Year/month toggle functions
function toggleYear(yearId) {
    const yearContent = document.getElementById(`${yearId}-content`);
    const arrow = document.getElementById(`${yearId}-icon`);
    
    if (yearContent.classList.contains('expanded')) {
        yearContent.classList.remove('expanded');
        arrow.textContent = '▶';
    } else {
        yearContent.classList.add('expanded');
        arrow.textContent = '▼';
    }
}

function toggleMonth(monthId) {
    const monthContent = document.getElementById(`${monthId}-content`);
    const arrow = document.getElementById(`${monthId}-icon`);
    
    if (monthContent.classList.contains('expanded')) {
        monthContent.classList.remove('expanded');
        arrow.textContent = '▶';
    } else {
        monthContent.classList.add('expanded');
        arrow.textContent = '▼';
    }
}

// Search entries
function searchEntries() {
    const searchInput = document.getElementById('search-input');
    const clearBtn = document.querySelector('.clear-search');
    const searchTerm = searchInput.value.toLowerCase().trim();
    const rows = document.querySelectorAll('.entry-row');
    
    // Show/hide clear button
    if (clearBtn) {
        clearBtn.style.display = searchTerm ? 'block' : 'none';
    }
    
    if (!searchTerm) {
        // No search term - show all rows and collapse to default state
        rows.forEach(row => {
            row.style.display = '';
        });
        collapseAllAndExpandRecent();
        return;
    }
    
    // Track which months and years have matches
    const monthsWithMatches = new Set();
    const yearsWithMatches = new Set();
    
    rows.forEach(row => {
        const description = row.dataset.description.toLowerCase();
        const amount = row.dataset.amount;
        
        if (description.includes(searchTerm) || amount.includes(searchTerm)) {
            row.style.display = '';
            
            // Find parent month and year
            const monthContent = row.closest('.month-content');
            const yearContent = row.closest('.year-content');
            
            if (monthContent) {
                monthsWithMatches.add(monthContent.id);
            }
            if (yearContent) {
                yearsWithMatches.add(yearContent.id);
            }
        } else {
            row.style.display = 'none';
        }
    });
    
    // Collapse all sections first
    document.querySelectorAll('.year-content').forEach(el => {
        el.classList.remove('expanded');
        const yearId = el.id.replace('-content', '');
        const arrow = document.getElementById(`${yearId}-icon`);
        if (arrow) arrow.textContent = '▶';
    });
    
    document.querySelectorAll('.month-content').forEach(el => {
        el.classList.remove('expanded');
        const monthId = el.id.replace('-content', '');
        const arrow = document.getElementById(`${monthId}-icon`);
        if (arrow) arrow.textContent = '▶';
    });
    
    // Expand sections with matches
    yearsWithMatches.forEach(yearContentId => {
        const yearContent = document.getElementById(yearContentId);
        const yearId = yearContentId.replace('-content', '');
        const arrow = document.getElementById(`${yearId}-icon`);
        
        if (yearContent) {
            yearContent.classList.add('expanded');
            if (arrow) arrow.textContent = '▼';
        }
    });
    
    monthsWithMatches.forEach(monthContentId => {
        const monthContent = document.getElementById(monthContentId);
        const monthId = monthContentId.replace('-content', '');
        const arrow = document.getElementById(`${monthId}-icon`);
        
        if (monthContent) {
            monthContent.classList.add('expanded');
            if (arrow) arrow.textContent = '▼';
        }
    });
}

// Collapse all and expand most recent (helper function)
function collapseAllAndExpandRecent() {
    // Collapse all
    document.querySelectorAll('.year-content').forEach(el => {
        el.classList.remove('expanded');
        const yearId = el.id.replace('-content', '');
        const arrow = document.getElementById(`${yearId}-icon`);
        if (arrow) arrow.textContent = '▶';
    });
    
    document.querySelectorAll('.month-content').forEach(el => {
        el.classList.remove('expanded');
        const monthId = el.id.replace('-content', '');
        const arrow = document.getElementById(`${monthId}-icon`);
        if (arrow) arrow.textContent = '▶';
    });
    
    // Expand most recent
    const firstYearHeader = document.querySelector('.year-header');
    if (firstYearHeader) {
        const match = firstYearHeader.getAttribute('onclick').match(/'([^']+)'/);
        if (match) {
            const yearId = match[1];
            const yearContent = document.getElementById(`${yearId}-content`);
            const yearArrow = document.getElementById(`${yearId}-icon`);
            
            if (yearContent) {
                yearContent.classList.add('expanded');
                if (yearArrow) yearArrow.textContent = '▼';
            }
            
            const firstMonthHeader = document.querySelector(`#${yearId}-content .month-header`);
            if (firstMonthHeader) {
                const monthMatch = firstMonthHeader.getAttribute('onclick').match(/'([^']+)'/);
                if (monthMatch) {
                    const monthId = monthMatch[1];
                    const monthContent = document.getElementById(`${monthId}-content`);
                    const monthArrow = document.getElementById(`${monthId}-icon`);
                    
                    if (monthContent) {
                        monthContent.classList.add('expanded');
                        if (monthArrow) monthArrow.textContent = '▼';
                    }
                }
            }
        }
    }
}

// Clear search
function clearSearch() {
    const searchInput = document.getElementById('search-input');
    searchInput.value = '';
    searchEntries();
    searchInput.focus();
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
    // Find the first year header (most recent year)
    const firstYearHeader = document.querySelector('.year-header');
    if (firstYearHeader) {
        const yearId = firstYearHeader.getAttribute('onclick').match(/'([^']+)'/)[1];
        
        // Get year content and arrow
        const yearContent = document.getElementById(`${yearId}-content`);
        const yearArrow = document.getElementById(`${yearId}-icon`);
        
        // Expand year
        if (yearContent) {
            yearContent.classList.add('expanded');
            yearArrow.textContent = '▼';
        }
        
        // Find the first month in that year (most recent month)
        const firstMonthHeader = document.querySelector(`#${yearId}-content .month-header`);
        if (firstMonthHeader) {
            const monthId = firstMonthHeader.getAttribute('onclick').match(/'([^']+)'/)[1];
            
            // Get month content and arrow
            const monthContent = document.getElementById(`${monthId}-content`);
            const monthArrow = document.getElementById(`${monthId}-icon`);
            
            // Expand month
            if (monthContent) {
                monthContent.classList.add('expanded');
                monthArrow.textContent = '▼';
            }
        }
    }
});
