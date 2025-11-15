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

// ===== ENTRY SEARCH FUNCTIONALITY =====

const entrySearchInput = document.getElementById('entry-search');
const clearEntrySearchBtn = document.getElementById('clear-entry-search');

// Get all entry rows (not the profile, just the entries)
function getEntryRows() {
    // Get all entry rows - these are the <tr> elements with onclick handlers
    return document.querySelectorAll('tr[onclick*="window.location"]');
}

// Expand or collapse all year/month sections
function expandAllSections(expand) {
    // Get all year sections
    document.querySelectorAll('[id$="-content"]').forEach(content => {
        const iconId = content.id.replace('-content', '-icon');
        const icon = document.getElementById(iconId);
        
        if (expand) {
            content.style.display = 'block';
            if (icon) icon.textContent = '▼';
        } else {
            content.style.display = 'none';
            if (icon) icon.textContent = '▶';
        }
    });
}

// Search function
function performEntrySearch() {
    const searchTerm = entrySearchInput.value.toLowerCase().trim();
    
    // Save search term to sessionStorage
    if (searchTerm) {
        sessionStorage.setItem('entrySearch', searchTerm);
    } else {
        sessionStorage.removeItem('entrySearch');
    }
    
    // Show/hide clear button
    if (clearEntrySearchBtn) {
        clearEntrySearchBtn.style.display = searchTerm ? 'block' : 'none';
    }
    
    const entryRows = getEntryRows();
    
    if (!searchTerm) {
        // No search term - show all entries
        entryRows.forEach(row => {
            row.style.display = '';
        });
        
        // Collapse all sections first
        expandAllSections(false);
        
        // Then expand the most recent year and its most recent month
        const allYears = Array.from(document.querySelectorAll('[id^="year-"][id$="-content"]'));
        if (allYears.length > 0) {
            // Years are in reverse chronological order, so first one is most recent
            const mostRecentYear = allYears[0];
            const yearIcon = document.getElementById(mostRecentYear.id.replace('-content', '-icon'));
            
            mostRecentYear.style.display = 'block';
            if (yearIcon) yearIcon.textContent = '▼';
            
            // Find the most recent month in that year
            const monthsInYear = mostRecentYear.querySelectorAll('[id^="month-"][id$="-content"]');
            if (monthsInYear.length > 0) {
                const mostRecentMonth = monthsInYear[0];
                const monthIcon = document.getElementById(mostRecentMonth.id.replace('-content', '-icon'));
                
                mostRecentMonth.style.display = 'block';
                if (monthIcon) monthIcon.textContent = '▼';
            }
        }
        
        return;
    }
    
    // Expand all sections so results are visible
    expandAllSections(true);
    
    entryRows.forEach(row => {
        // Get description and content from data attributes
        const description = (row.dataset.description || '').toLowerCase();
        const content = (row.dataset.content || '').toLowerCase();
        
        // Search both description and content
        const searchableText = `${description} ${content}`;
        const matches = searchableText.includes(searchTerm);
        
        // Show or hide row
        row.style.display = matches ? '' : 'none';
    });
}

// Real-time search as user types
if (entrySearchInput) {
    entrySearchInput.addEventListener('input', performEntrySearch);
}

// Clear search button
if (clearEntrySearchBtn) {
    clearEntrySearchBtn.addEventListener('click', function() {
        entrySearchInput.value = '';
        sessionStorage.removeItem('entrySearch');
        performEntrySearch();
        entrySearchInput.focus();
    });
}

// Restore search from sessionStorage on page load
document.addEventListener('DOMContentLoaded', function() {
    const savedSearch = sessionStorage.getItem('entrySearch');
    if (savedSearch && entrySearchInput) {
        entrySearchInput.value = savedSearch;
        performEntrySearch();
    }
});

// ===== REAL-TIME ENTRY CLASS FILTER =====

// Get selected entry classes
function getSelectedClasses() {
    const checkboxes = document.querySelectorAll('#filter-form input[type="checkbox"]:checked');
    return Array.from(checkboxes).map(cb => cb.value);
}

// Save filter state to sessionStorage
function saveFilterState() {
    const selected = getSelectedClasses();
    sessionStorage.setItem('entryClassFilter', JSON.stringify(selected));
}

// Restore filter state from sessionStorage
function restoreFilterState() {
    const saved = sessionStorage.getItem('entryClassFilter');
    if (saved) {
        const selectedClasses = JSON.parse(saved);
        
        // Update checkboxes to match saved state
        document.querySelectorAll('#filter-form input[type="checkbox"]').forEach(checkbox => {
            checkbox.checked = selectedClasses.includes(checkbox.value);
        });
        
        // Update button text
        updateFilterButtonText();
    }
}

// Update filter button text
function updateFilterButtonText() {
    const checkedCount = document.querySelectorAll('#filter-form input[type="checkbox"]:checked').length;
    const filterButton = document.getElementById('class-filter-button');
    if (filterButton) {
        filterButton.textContent = `Filter: ${checkedCount} type${checkedCount !== 1 ? 's' : ''} ▾`;
    }
}

// Apply filter (show/hide entries based on selected classes)
function applyEntryFilter() {
    const selectedClasses = getSelectedClasses();
    const entryRows = getEntryRows();
    const totalCheckboxes = document.querySelectorAll('#filter-form input[type="checkbox"]').length;
    
    // Save filter state
    saveFilterState();
    updateFilterButtonText();
    
    // If ALL classes selected (or none), show all and don't auto-expand
    if (selectedClasses.length === 0 || selectedClasses.length === totalCheckboxes) {
        entryRows.forEach(row => {
            // Don't override search filtering
            if (entrySearchInput && entrySearchInput.value.trim()) {
                // Search is active, let search handle visibility
                return;
            }
            row.style.display = '';
        });
        
        // Don't auto-expand when showing everything - just expand most recent
        if (!entrySearchInput || !entrySearchInput.value.trim()) {
            expandAllSections(false);
            
            // Expand most recent year and month
            const allYears = Array.from(document.querySelectorAll('[id^="year-"][id$="-content"]'));
            if (allYears.length > 0) {
                const mostRecentYear = allYears[0];
                const yearIcon = document.getElementById(mostRecentYear.id.replace('-content', '-icon'));
                
                mostRecentYear.style.display = 'block';
                if (yearIcon) yearIcon.textContent = '▼';
                
                const monthsInYear = mostRecentYear.querySelectorAll('[id^="month-"][id$="-content"]');
                if (monthsInYear.length > 0) {
                    const mostRecentMonth = monthsInYear[0];
                    const monthIcon = document.getElementById(mostRecentMonth.id.replace('-content', '-icon'));
                    
                    mostRecentMonth.style.display = 'block';
                    if (monthIcon) monthIcon.textContent = '▼';
                }
            }
        }
        
        return;
    }
    
    // Expand all sections so filtered results are visible
    expandAllSections(true);
    
    entryRows.forEach(row => {
        // Get the entry class from the row
        // Look for the class badge text
        const classBadge = row.querySelector('.session-badge');
        if (!classBadge) {
            row.style.display = 'none';
            return;
        }
        
        const badgeText = classBadge.textContent.trim().toLowerCase();
        
        // Check if this class is selected
        let matches = false;
        if (selectedClasses.includes('session') && (badgeText === 'session' || badgeText === 'consultation')) {
            matches = true;
        } else if (selectedClasses.includes('consultation') && badgeText === 'consultation') {
            matches = true;
        } else if (selectedClasses.includes('communication') && badgeText === 'communication') {
            matches = true;
        } else if (selectedClasses.includes('absence') && badgeText === 'absence') {
            matches = true;
        } else if (selectedClasses.includes('item') && badgeText === 'item') {
            matches = true;
        }
        
        // If search is also active, combine both filters
        if (entrySearchInput && entrySearchInput.value.trim()) {
            const searchTerm = entrySearchInput.value.toLowerCase().trim();
            const description = (row.dataset.description || '').toLowerCase();
            const content = (row.dataset.content || '').toLowerCase();
            const searchableText = `${description} ${content}`;
            const searchMatches = searchableText.includes(searchTerm);
            
            // Must match both filter AND search
            row.style.display = (matches && searchMatches) ? '' : 'none';
        } else {
            // Only filter, no search
            row.style.display = matches ? '' : 'none';
        }
    });
}

// Add real-time filtering to checkboxes
document.querySelectorAll('#filter-form input[type="checkbox"]').forEach(checkbox => {
    checkbox.addEventListener('change', function() {
        applyEntryFilter();
    });
});

// Restore filter on page load
document.addEventListener('DOMContentLoaded', function() {
    restoreFilterState();
    applyEntryFilter();
});

// Update search to work with filter
const originalPerformSearch = performEntrySearch;
performEntrySearch = function() {
    // Call original search logic
    originalPerformSearch();
    
    // Then apply filter on top of it
    applyEntryFilter();
};