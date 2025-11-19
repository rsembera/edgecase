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

// Three-way fee calculation
function calculateAbsenceFee(changedField) {
    const baseInput = document.getElementById('base_price');
    const taxInput = document.getElementById('tax_rate');
    const totalInput = document.getElementById('fee');
    
    const base = parseFloat(baseInput.value) || 0;
    const taxRate = parseFloat(taxInput.value) || 0;
    const total = parseFloat(totalInput.value) || 0;
    
    if (changedField === 'base' || changedField === 'tax') {
        // Calculate total from base + tax
        const calculatedTotal = base * (1 + taxRate / 100);
        totalInput.value = calculatedTotal.toFixed(2);
    } else if (changedField === 'total') {
        // Calculate base from total - tax
        if (taxRate > 0) {
            const calculatedBase = total / (1 + taxRate / 100);
            baseInput.value = calculatedBase.toFixed(2);
        } else {
            // If no tax, total = base
            baseInput.value = total.toFixed(2);
        }
    }
}

// Auto-format to 2 decimal places on blur
function formatToTwoDecimals(input) {
    const value = parseFloat(input.value);
    if (!isNaN(value)) {
        input.value = value.toFixed(2);
    }
}

dateYear.addEventListener('change', updateAbsenceDate);
dateMonth.addEventListener('change', updateAbsenceDate);
dateDay.addEventListener('change', updateAbsenceDate);

// Auto-expanding textarea
const contentTextarea = document.getElementById('content');
const maxHeight = 600; // About 30-35 lines

function autoResize() {
    // Reset height to auto to get the correct scrollHeight
    contentTextarea.style.height = 'auto';
    
    // Set new height, but don't exceed maxHeight
    const newHeight = Math.min(contentTextarea.scrollHeight, maxHeight);
    contentTextarea.style.height = newHeight + 'px';
    
    // Add scrollbar if content exceeds maxHeight
    if (contentTextarea.scrollHeight > maxHeight) {
        contentTextarea.style.overflowY = 'scroll';
    } else {
        contentTextarea.style.overflowY = 'hidden';
    }
}

// Run on page load (for edit mode with existing content)
autoResize();

// Run on input
contentTextarea.addEventListener('input', autoResize);