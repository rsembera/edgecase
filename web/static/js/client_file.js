/**
 * Client File View JavaScript - EdgeCase Equalizer
 * Handles entry timeline display with year/month collapse, filtering, and search.
 */

/**
 * Toggle a year section expand/collapse
 * @param {string} yearId - ID prefix for the year section
 */
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

/**
 * Toggle a month section expand/collapse
 * @param {string} monthId - ID prefix for the month section
 */
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

/**
 * Toggle dropdown menu visibility, closing all others first
 * Includes edge detection for dropdowns near bottom of viewport
 * @param {string} dropdownId - ID of dropdown element to toggle
 */
function toggleDropdown(dropdownId) {
    const dropdown = document.getElementById(dropdownId);
    const allDropdowns = document.querySelectorAll('[id$="-dropdown"]');
    
    // Close all other dropdowns
    allDropdowns.forEach(d => {
        if (d.id !== dropdownId) {
            d.style.display = 'none';
            d.classList.remove('dropdown-menu-up');
        }
    });
    
    // Toggle this dropdown (check for both 'none' and empty string)
    if (dropdown.style.display === 'none' || dropdown.style.display === '') {
        dropdown.style.display = 'block';
        
        // Edge detection for add-entry-dropdown
        if (dropdownId === 'add-entry-dropdown') {
            // Reset position first
            dropdown.classList.remove('dropdown-menu-up');
            
            // Check if dropdown extends beyond viewport
            const rect = dropdown.getBoundingClientRect();
            const viewportHeight = window.innerHeight;
            const spaceBelow = viewportHeight - rect.top;
            const dropdownHeight = rect.height;
            
            // If not enough space below, flip upward
            if (spaceBelow < dropdownHeight + 20) {
                dropdown.classList.add('dropdown-menu-up');
            }
        }
    } else {
        dropdown.style.display = 'none';
        dropdown.classList.remove('dropdown-menu-up');
    }
}

// Close dropdowns when clicking outside
document.addEventListener('click', function(e) {
    if (!e.target.closest('.type-badge') && !e.target.closest('.dropdown-btn') && !e.target.closest('[id$="-dropdown"]')) {
        document.querySelectorAll('[id$="-dropdown"]').forEach(d => {
            d.style.display = 'none';
            d.classList.remove('dropdown-menu-up');
        });
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

/**
 * Get all entry rows (entries in the timeline, not the profile)
 * @returns {NodeList} Entry row elements with onclick handlers
 */
function getEntryRows() {
    return document.querySelectorAll('tr[onclick*="window.location"]');
}

/**
 * Expand or collapse all year/month sections
 * @param {boolean} expand - True to expand all, false to collapse all
 */
function expandAllSections(expand) {
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

/**
 * Perform search on entries, showing/hiding based on search term
 */
function performEntrySearch() {
    const searchTerm = entrySearchInput.value.toLowerCase().trim();
    
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

// Clear search input on page load
document.addEventListener('DOMContentLoaded', function() {
    if (entrySearchInput) {
        entrySearchInput.value = '';
        sessionStorage.removeItem('entrySearch');
    }
});

// ===== REAL-TIME ENTRY CLASS FILTER =====

/**
 * Get currently selected entry class filter values
 * @returns {Array} Array of selected class values
 */
function getSelectedClasses() {
    const checkboxes = document.querySelectorAll('#filter-form input[type="checkbox"]:checked');
    return Array.from(checkboxes).map(cb => cb.value);
}

/**
 * Save current filter state to sessionStorage
 */
function saveFilterState() {
    const selected = getSelectedClasses();
    sessionStorage.setItem('entryClassFilter', JSON.stringify(selected));
}

/**
 * Restore filter state from sessionStorage
 */
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

/**
 * Update filter button text to show count of selected types
 */
function updateFilterButtonText() {
    const checkedCount = document.querySelectorAll('#filter-form input[type="checkbox"]:checked').length;
    const filterButton = document.getElementById('class-filter-button');
    if (filterButton) {
        filterButton.textContent = `Filter: ${checkedCount} type${checkedCount !== 1 ? 's' : ''} ▾`;
    }
}

/**
 * Apply entry class filter - show/hide entries based on selected classes
 */
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
