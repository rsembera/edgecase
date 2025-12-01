/**
 * Absence Entry Form JavaScript - EdgeCase Equalizer
 * Handles absence (cancellation/no-show) creation/editing with
 * three-way fee calculation.
 */

// Date dropdowns → hidden field
const dateYear = document.getElementById('date_year');
const dateMonth = document.getElementById('date_month');
const dateDay = document.getElementById('date_day');
const dateHidden = document.getElementById('absence_date');

/**
 * Update hidden absence_date field from dropdown selections
 */
function updateAbsenceDate() {
    if (dateYear.value && dateMonth.value && dateDay.value) {
        dateHidden.value = `${dateYear.value}-${dateMonth.value}-${dateDay.value}`;
    } else {
        dateHidden.value = '';
    }
}

/**
 * Three-way fee calculation for absence fees
 * @param {string} changedField - Which field was changed: 'base', 'tax', or 'total'
 */
function calculateAbsenceFee(changedField) {
    const baseInput = document.getElementById('base_price');
    const taxInput = document.getElementById('tax_rate');
    const totalInput = document.getElementById('fee');
    
    const base = parseFloat(baseInput.value) || 0;
    const taxRate = parseFloat(taxInput.value) || 0;
    const total = parseFloat(totalInput.value) || 0;
    
    if (changedField === 'base' || changedField === 'tax') {
        const calculatedTotal = base * (1 + taxRate / 100);
        totalInput.value = calculatedTotal.toFixed(2);
    } else if (changedField === 'total') {
        if (taxRate > 0) {
            const calculatedBase = total / (1 + taxRate / 100);
            baseInput.value = calculatedBase.toFixed(2);
        } else {
            baseInput.value = total.toFixed(2);
        }
    }
}

/**
 * Format input value to 2 decimal places
 * @param {HTMLInputElement} input - Input element to format
 */
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
const maxHeight = 600;

/**
 * Auto-resize textarea to fit content up to maxHeight
 */
function autoResize() {
    contentTextarea.style.height = 'auto';
    const newHeight = Math.min(contentTextarea.scrollHeight, maxHeight);
    contentTextarea.style.height = newHeight + 'px';
    
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
