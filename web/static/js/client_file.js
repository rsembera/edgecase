/**
 * Client File View JavaScript - EdgeCase Equalizer
 * Handles entry timeline display with year/month collapse, filtering, and search.
 */

// ============================================================
// YEAR/MONTH EXPANSION
// ============================================================

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
 * Expand or collapse all year/month sections
 * @param {boolean} expand - True to expand, false to collapse
 */
function expandAllSections(expand) {
    document.querySelectorAll('[id$="-content"]').forEach(content => {
        const iconId = content.id.replace('-content', '-icon');
        const icon = document.getElementById(iconId);
        
        content.style.display = expand ? 'block' : 'none';
        if (icon) icon.textContent = expand ? '▼' : '▶';
    });
}

/**
 * Expand only the most recent year and its most recent month
 */
function expandMostRecent() {
    expandAllSections(false);
    
    const allYears = Array.from(document.querySelectorAll('[id^="year-"][id$="-content"]'));
    if (allYears.length === 0) return;
    
    // Years are in reverse chronological order
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

// ============================================================
// DROPDOWN MENUS
// ============================================================

/**
 * Toggle a dropdown menu visibility
 * @param {string} dropdownId - ID of the dropdown element
 */
function toggleDropdown(dropdownId) {
    const dropdown = document.getElementById(dropdownId);
    
    // Close all other dropdowns
    document.querySelectorAll('[id$="-dropdown"]').forEach(d => {
        if (d.id !== dropdownId) d.style.display = 'none';
    });
    
    dropdown.style.display = (dropdown.style.display === 'none' || dropdown.style.display === '') 
        ? 'block' : 'none';
}

/**
 * Initialize dropdown close-on-outside-click
 */
function initDropdownClose() {
    document.addEventListener('click', function(e) {
        if (!e.target.closest('.type-badge') && 
            !e.target.closest('.dropdown-btn') && 
            !e.target.closest('[id$="-dropdown"]')) {
            document.querySelectorAll('[id$="-dropdown"]').forEach(d => d.style.display = 'none');
        }
    });
}

// ============================================================
// ENTRY SEARCH
// ============================================================

/**
 * Get all entry rows (entries in the timeline, not profile)
 * @returns {NodeList} Entry row elements
 */
function getEntryRows() {
    return document.querySelectorAll('tr[onclick*="window.location"]');
}

/**
 * Perform search on entries
 */
function performEntrySearch() {
    const searchInput = document.getElementById('entry-search');
    const clearBtn = document.getElementById('clear-entry-search');
    
    if (!searchInput) return;
    
    const searchTerm = searchInput.value.toLowerCase().trim();
    
    if (clearBtn) {
        clearBtn.style.display = searchTerm ? 'block' : 'none';
    }
    
    const entryRows = getEntryRows();
    
    if (!searchTerm) {
        entryRows.forEach(row => row.style.display = '');
        expandMostRecent();
        return;
    }
    
    expandAllSections(true);
    
    entryRows.forEach(row => {
        const description = (row.dataset.description || '').toLowerCase();
        const content = (row.dataset.content || '').toLowerCase();
        const searchableText = `${description} ${content}`;
        
        row.style.display = searchableText.includes(searchTerm) ? '' : 'none';
    });
}

/**
 * Initialize search input handlers
 */
function initSearch() {
    const searchInput = document.getElementById('entry-search');
    const clearBtn = document.getElementById('clear-entry-search');
    
    if (searchInput) {
        searchInput.value = '';
        sessionStorage.removeItem('entrySearch');
        searchInput.addEventListener('input', performEntrySearch);
    }
    
    if (clearBtn) {
        clearBtn.addEventListener('click', function() {
            searchInput.value = '';
            sessionStorage.removeItem('entrySearch');
            performEntrySearch();
            searchInput.focus();
        });
    }
}

// ============================================================
// ENTRY CLASS FILTER
// ============================================================

/**
 * Get currently selected entry classes
 * @returns {Array} Selected class values
 */
function getSelectedClasses() {
    const checkboxes = document.querySelectorAll('#filter-form input[type="checkbox"]:checked');
    return Array.from(checkboxes).map(cb => cb.value);
}

/**
 * Save filter state to sessionStorage
 */
function saveFilterState() {
    sessionStorage.setItem('entryClassFilter', JSON.stringify(getSelectedClasses()));
}

/**
 * Restore filter state from sessionStorage
 */
function restoreFilterState() {
    const saved = sessionStorage.getItem('entryClassFilter');
    if (!saved) return;
    
    const selectedClasses = JSON.parse(saved);
    
    document.querySelectorAll('#filter-form input[type="checkbox"]').forEach(checkbox => {
        checkbox.checked = selectedClasses.includes(checkbox.value);
    });
    
    updateFilterButtonText();
}

/**
 * Update filter button text to show count
 */
function updateFilterButtonText() {
    const checkedCount = document.querySelectorAll('#filter-form input[type="checkbox"]:checked').length;
    const filterButton = document.getElementById('class-filter-button');
    if (filterButton) {
        filterButton.textContent = `Filter: ${checkedCount} type${checkedCount !== 1 ? 's' : ''} ▾`;
    }
}

/**
 * Apply entry class filter (show/hide entries based on selected classes)
 */
function applyEntryFilter() {
    const selectedClasses = getSelectedClasses();
    const entryRows = getEntryRows();
    const totalCheckboxes = document.querySelectorAll('#filter-form input[type="checkbox"]').length;
    const searchInput = document.getElementById('entry-search');
    
    saveFilterState();
    updateFilterButtonText();
    
    // All or none selected = show all
    if (selectedClasses.length === 0 || selectedClasses.length === totalCheckboxes) {
        entryRows.forEach(row => {
            if (searchInput && searchInput.value.trim()) return; // Let search handle it
            row.style.display = '';
        });
        
        if (!searchInput || !searchInput.value.trim()) {
            expandMostRecent();
        }
        return;
    }
    
    expandAllSections(true);
    
    entryRows.forEach(row => {
        const classBadge = row.querySelector('.session-badge');
        if (!classBadge) {
            row.style.display = 'none';
            return;
        }
        
        const badgeText = classBadge.textContent.trim().toLowerCase();
        
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
        
        // Combine with search if active
        if (searchInput && searchInput.value.trim()) {
            const searchTerm = searchInput.value.toLowerCase().trim();
            const description = (row.dataset.description || '').toLowerCase();
            const content = (row.dataset.content || '').toLowerCase();
            const searchMatches = `${description} ${content}`.includes(searchTerm);
            
            row.style.display = (matches && searchMatches) ? '' : 'none';
        } else {
            row.style.display = matches ? '' : 'none';
        }
    });
}

/**
 * Initialize filter checkboxes
 */
function initFilter() {
    document.querySelectorAll('#filter-form input[type="checkbox"]').forEach(checkbox => {
        checkbox.addEventListener('change', applyEntryFilter);
    });
}

// ============================================================
// INITIALIZATION
// ============================================================

document.addEventListener('DOMContentLoaded', function() {
    initDropdownClose();
    initSearch();
    initFilter();
    restoreFilterState();
    applyEntryFilter();
});

// Override search to work with filter
const originalPerformSearch = performEntrySearch;
performEntrySearch = function() {
    originalPerformSearch();
    applyEntryFilter();
};
