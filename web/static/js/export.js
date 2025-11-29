// Export Page JavaScript

document.addEventListener('DOMContentLoaded', function() {
    // Initialize Lucide icons
    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }
    
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

function getSelectedEntryTypes() {
    const checkboxes = document.querySelectorAll('input[name="entry_type"]:checked');
    return Array.from(checkboxes).map(cb => cb.value);
}

function getDateRange() {
    const allTime = document.getElementById('all-time').checked;
    
    if (allTime) {
        return { all_time: true };
    }
    
    return {
        all_time: false,
        start_year: document.getElementById('start-year').value,
        start_month: document.getElementById('start-month').value,
        start_day: document.getElementById('start-day').value,
        end_year: document.getElementById('end-year').value,
        end_month: document.getElementById('end-month').value,
        end_day: document.getElementById('end-day').value
    };
}

function calculateExport() {
    const clientId = document.getElementById('client-id').value;
    const entryTypes = getSelectedEntryTypes();
    const dateRange = getDateRange();
    
    if (entryTypes.length === 0) {
        alert('Please select at least one entry type to export.');
        return;
    }
    
    // Build query string
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

function generateExport() {
    const clientId = document.getElementById('client-id').value;
    const entryTypes = getSelectedEntryTypes();
    const dateRange = getDateRange();
    
    if (entryTypes.length === 0) {
        alert('Please select at least one entry type to export.');
        return;
    }
    
    // Build query string
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