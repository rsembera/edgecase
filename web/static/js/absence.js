/**
 * Absence Entry Form JavaScript - EdgeCase Equalizer
 * Handles absence (cancellation/no-show) creation/editing with
 * three-way fee calculation and date/time pickers.
 */

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

// Auto-expanding textarea
const contentTextarea = document.getElementById('content');
const maxHeight = 600;

/**
 * Auto-resize textarea to fit content up to maxHeight
 */
function autoResize() {
    if (!contentTextarea) return;
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
if (contentTextarea) {
    contentTextarea.addEventListener('input', autoResize);
}

// ============================================================
// DATE/TIME PICKERS
// ============================================================

/**
 * Initialize date and time pickers for absence form
 */
async function initAbsencePickers() {
    // Get time format setting
    const timeFormat = await getTimeFormatSetting();
    
    // Get initial values from hidden inputs
    const dateInput = document.getElementById('date');
    const timeInput = document.getElementById('absence_time');
    
    // Initialize date picker
    const datePicker = initDatePicker('absence-date-picker', {
        initialDate: dateInput.value ? parseDateString(dateInput.value) : new Date(),
        onSelect: (date) => {
            const year = date.getFullYear();
            const month = String(date.getMonth() + 1).padStart(2, '0');
            const day = String(date.getDate()).padStart(2, '0');
            dateInput.value = `${year}-${month}-${day}`;
        }
    });
    
    // Initialize time picker
    const timePicker = initTimePicker('absence-time-picker', {
        format: timeFormat,
        initialTime: timeInput.value || null,
        onSelect: (timeStr) => {
            timeInput.value = timeStr;
        }
    });
    
    // If no initial time and not in edit mode, populate with current time
    if (!timeInput.value) {
        timeInput.value = timePicker.formatTime();
    }
}

// Initialize pickers when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAbsencePickers);
} else {
    initAbsencePickers();
}
