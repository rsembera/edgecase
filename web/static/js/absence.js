// Date dropdowns → hidden field
const dateYear = document.getElementById('date_year');
const dateMonth = document.getElementById('date_month');
const dateDay = document.getElementById('date_day');
const dateHidden = document.getElementById('absence_date');

function updateAbsenceDate() {
    if (dateYear.value && dateMonth.value && dateDay.value) {
        dateHidden.value = `${dateYear.value}-${dateMonth.value}-${dateDay.value}`;
    } else {
        dateHidden.value = '';
    }
}

// Currency formatting for fee field
document.getElementById('fee').addEventListener('blur', function(e) {
    let value = parseFloat(e.target.value);
    if (!isNaN(value)) {
        e.target.value = value.toFixed(2);
    }
});

dateYear.addEventListener('change', updateAbsenceDate);
dateMonth.addEventListener('change', updateAbsenceDate);
dateDay.addEventListener('change', updateAbsenceDate);

// Auto-expanding textarea
const textarea = document.getElementById('content');
const maxHeight = 600; // About 30-35 lines

function autoResize() {
    // Reset height to auto to get the correct scrollHeight
    textarea.style.height = 'auto';
    
    // Set new height, but don't exceed maxHeight
    const newHeight = Math.min(textarea.scrollHeight, maxHeight);
    textarea.style.height = newHeight + 'px';
    
    // Add scrollbar if content exceeds maxHeight
    if (textarea.scrollHeight > maxHeight) {
        textarea.style.overflowY = 'scroll';
    } else {
        textarea.style.overflowY = 'hidden';
    }
}

// Run on page load (for edit mode with existing content)
autoResize();

// Run on input
textarea.addEventListener('input', autoResize);