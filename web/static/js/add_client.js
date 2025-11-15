// Add Client form JavaScript - EdgeCase Equalizer

// Dynamic file number calculation for date-initials format
function updateFileNumber() {
    const fileNumberInput = document.getElementById('file_number');
    
    // Only update if field is readonly (auto-generated)
    if (!fileNumberInput.hasAttribute('readonly')) {
        return;
    }
    
    // Check if we're in date-initials mode
    const isDateInitials = '{{ "date-initials" if file_number_readonly and "ABC" in file_number_preview else "" }}';
    
    if (isDateInitials === 'date-initials') {
        const first = document.getElementById('first_name').value.trim();
        const middle = document.getElementById('middle_name').value.trim();
        const last = document.getElementById('last_name').value.trim();
        
        // Get today's date in YYYYMMDD format
        const today = new Date();
        const dateStr = today.getFullYear() + 
                      String(today.getMonth() + 1).padStart(2, '0') + 
                      String(today.getDate()).padStart(2, '0');
        
        // Build initials progressively as names are entered
        let initials = '';
        if (first) initials += first[0].toUpperCase();
        if (middle) initials += middle[0].toUpperCase();
        if (last) initials += last[0].toUpperCase();
        
        // If no names entered yet, show placeholder
        if (!initials) {
            initials = 'ABC';
        }
        
        // Update file number field
        fileNumberInput.value = dateStr + '-' + initials;
    }
}

// Add event listeners when page loads
document.addEventListener('DOMContentLoaded', function() {
    // Listen for changes to name fields
    document.getElementById('first_name').addEventListener('input', updateFileNumber);
    document.getElementById('middle_name').addEventListener('input', updateFileNumber);
    document.getElementById('last_name').addEventListener('input', updateFileNumber);
    
    // Run once on page load to set initial value
    updateFileNumber();
});