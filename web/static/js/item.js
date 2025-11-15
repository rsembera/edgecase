// Date dropdowns → hidden field
const dateYear = document.getElementById('date_year');
const dateMonth = document.getElementById('date_month');
const dateDay = document.getElementById('date_day');
const dateHidden = document.getElementById('item_date');

function updateItemDate() {
    if (dateYear.value && dateMonth.value && dateDay.value) {
        dateHidden.value = `${dateYear.value}-${dateMonth.value}-${dateDay.value}`;
    } else {
        dateHidden.value = '';
    }
}

dateYear.addEventListener('change', updateItemDate);
dateMonth.addEventListener('change', updateItemDate);
dateDay.addEventListener('change', updateItemDate);

// Auto-expanding textarea
const textarea = document.getElementById('content');
const maxHeight = 600;

function autoResize() {
    textarea.style.height = 'auto';
    const newHeight = Math.min(textarea.scrollHeight, maxHeight);
    textarea.style.height = newHeight + 'px';
    
    if (textarea.scrollHeight > maxHeight) {
        textarea.style.overflowY = 'scroll';
    } else {
        textarea.style.overflowY = 'hidden';
    }
}

autoResize();
textarea.addEventListener('input', autoResize);

// Tax calculation logic
const basePrice = document.getElementById('base_price');
const taxRate = document.getElementById('tax_rate');
const totalPrice = document.getElementById('total_price'); // Correct ID

let lastEdited = null;

function calculateTax() {
    const base = parseFloat(basePrice.value) || 0;
    const rate = parseFloat(taxRate.value) || 0;
    const total = parseFloat(totalPrice.value) || 0;
    
    // If user just edited base or tax rate, calculate total
    if (lastEdited === 'base' || lastEdited === 'rate') {
        const calculatedTotal = base * (1 + rate / 100);
        totalPrice.value = calculatedTotal.toFixed(2);
    }
    // If user just edited total, calculate base (keeping tax rate)
    else if (lastEdited === 'total') {
        const calculatedBase = total / (1 + rate / 100);
        basePrice.value = calculatedBase.toFixed(2);
    }
}

basePrice.addEventListener('input', function() {
    lastEdited = 'base';
    calculateTax();
});

taxRate.addEventListener('input', function() {
    lastEdited = 'rate';
    calculateTax();
});

totalPrice.addEventListener('input', function() {
    lastEdited = 'total';
    calculateTax();
});

// Currency formatting functions
function formatCurrency(input) {
    let value = parseFloat(input.value);
    if (!isNaN(value)) {
        input.value = value.toFixed(2);
    }
}

function formatTaxRate(input) {
    let value = parseFloat(input.value);
    if (!isNaN(value)) {
        input.value = value.toFixed(1); // Tax rate to 1 decimal (e.g., 13.0%)
    }
}

// Format on blur
basePrice.addEventListener('blur', function() {
    formatCurrency(this);
});

totalPrice.addEventListener('blur', function() {
    formatCurrency(this);
});

taxRate.addEventListener('blur', function() {
    formatTaxRate(this);
});

// On page load, if editing existing item with values, set lastEdited to make calculations work
const hasEntry = document.getElementById('has-entry');
if (hasEntry && hasEntry.value === 'true') {
    lastEdited = 'base';
}