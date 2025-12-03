/**
 * Export Page JavaScript - EdgeCase Equalizer
 * Handles entry export to PDF with date range and type filtering.
 */

document.addEventListener('DOMContentLoaded', function() {
    // Initialize Lucide icons
    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }
    
    // Initialize date pickers
    initExportPickers();
    
    // All Time checkbox toggle
    const allTimeCheckbox = document.getElementById('all-time');
    const dateRangeSelectors = document.getElementById('date-range-selectors');
    
    allTimeCheckbox.addEventListener('change', function() {
        dateRangeSelectors.style.display = this.checked ? 'none' : 'block';
    });
    
    // Select All checkbox
    const selectAllCheckbox = document.getElementById('select-all');
    const entryTypeCheckboxes = document.querySelectorAll('input[name="entry_type"]');
    
    selectAllCheckbox.addEventListener('change', function() {
        entryTypeCheckboxes.forEach(cb => cb.checked = this.checked);
    });
    
    // Update Select All when individual checkboxes change
    entryTypeCheckboxes.forEach(cb => {
        cb.addEventListener('change', function() {
            const allChecked = Array.from(entryTypeCheckboxes).every(c => c.checked);
            const someChecked = Array.from(entryTypeCheckboxes).some(c => c.checked);
            selectAllCheckbox.checked = allChecked;
            selectAllCheckbox.indeterminate = someChecked && !allChecked;
        });
    });
});

/**
 * Initialize date pickers
 */
function initExportPickers() {
    const exportData = JSON.parse(document.getElementById('export-data').textContent);
    
    const startDateInput = document.getElementById('start_date');
    const endDateInput = document.getElementById('end_date');
    
    // Parse initial dates
    const startDate = new Date(
        exportData.defaultStartYear,
        exportData.defaultStartMonth - 1,
        exportData.defaultStartDay
    );
    const endDate = new Date(
        exportData.defaultEndYear,
        exportData.defaultEndMonth - 1,
        exportData.defaultEndDay
    );
    
    // Initialize start date picker
    const startContainer = document.getElementById('start-date-picker');
    if (startContainer) {
        new DatePicker(startContainer, {
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
        new DatePicker(endContainer, {
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
 * Get array of selected entry types
 * @returns {Array} Array of selected type values
 */
function getSelectedEntryTypes() {
    const checkboxes = document.querySelectorAll('input[name="entry_type"]:checked');
    return Array.from(checkboxes).map(cb => cb.value);
}

/**
 * Get date range from form
 * @returns {Object} Date range object with all_time flag or date string
 */
function getDateRange() {
    const allTime = document.getElementById('all-time').checked;
    
    if (allTime) {
        return { all_time: true };
    }
    
    // Get dates from hidden inputs (YYYY-MM-DD format)
    const startDate = document.getElementById('start_date').value;
    const endDate = document.getElementById('end_date').value;
    
    // Parse into components for API
    const [startYear, startMonth, startDay] = startDate.split('-');
    const [endYear, endMonth, endDay] = endDate.split('-');
    
    return {
        all_time: false,
        start_year: startYear,
        start_month: parseInt(startMonth),
        start_day: parseInt(startDay),
        end_year: endYear,
        end_month: parseInt(endMonth),
        end_day: parseInt(endDay)
    };
}

/**
 * Calculate and display export counts
 */
function calculateExport() {
    const clientId = document.getElementById('client-id').value;
    const entryTypes = getSelectedEntryTypes();
    const dateRange = getDateRange();
    
    if (entryTypes.length === 0) {
        alert('Please select at least one entry type to export.');
        return;
    }
    
    const params = new URLSearchParams();
    params.append('client_id', clientId);
    entryTypes.forEach(t => params.append('types', t));
    
    if (dateRange.all_time) {
        params.append('all_time', '1');
    } else {
        params.append('start_year', dateRange.start_year);
        params.append('start_month', dateRange.start_month);
        params.append('start_day', dateRange.start_day);
        params.append('end_year', dateRange.end_year);
        params.append('end_month', dateRange.end_month);
        params.append('end_day', dateRange.end_day);
    }
    
    fetch(`/client/${clientId}/export/calculate?${params.toString()}`)
        .then(response => response.json())
        .then(data => {
            // Update counts
            document.getElementById('count-profile').textContent = data.counts.profile || 0;
            document.getElementById('count-session').textContent = data.counts.session || 0;
            document.getElementById('count-communication').textContent = data.counts.communication || 0;
            document.getElementById('count-absence').textContent = data.counts.absence || 0;
            document.getElementById('count-item').textContent = data.counts.item || 0;
            document.getElementById('count-upload').textContent = data.counts.upload || 0;
            document.getElementById('count-total').textContent = data.total;
            
            // Show attachment count if any
            if (data.attachments > 0) {
                document.getElementById('count-attachments').textContent = data.attachments;
                document.getElementById('attachment-note').style.display = 'inline';
            } else {
                document.getElementById('attachment-note').style.display = 'none';
            }
            
            // Show summary section
            document.getElementById('export-summary').style.display = 'block';
        })
        .catch(error => {
            console.error('Error calculating export:', error);
            alert('Error calculating export. Please try again.');
        });
}

/**
 * Generate and download the PDF export
 */
function generateExport() {
    const clientId = document.getElementById('client-id').value;
    const entryTypes = getSelectedEntryTypes();
    const dateRange = getDateRange();
    
    if (entryTypes.length === 0) {
        alert('Please select at least one entry type to export.');
        return;
    }
    
    const params = new URLSearchParams();
    entryTypes.forEach(t => params.append('types', t));
    
    if (dateRange.all_time) {
        params.append('all_time', '1');
    } else {
        params.append('start_year', dateRange.start_year);
        params.append('start_month', dateRange.start_month);
        params.append('start_day', dateRange.start_day);
        params.append('end_year', dateRange.end_year);
        params.append('end_month', dateRange.end_month);
        params.append('end_day', dateRange.end_day);
    }
    
    // Open PDF in new tab
    window.open(`/client/${clientId}/export/pdf?${params.toString()}`, '_blank');
}
