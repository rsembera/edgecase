/**
 * Ledger Report Page JavaScript - EdgeCase Equalizer
 * Handles financial report generation with date range selection and preview.
 */

// Global picker references for quick range buttons
let startDatePicker = null;
let endDatePicker = null;

document.addEventListener('DOMContentLoaded', function() {
    // Initialize Lucide icons
    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }
    
    // Initialize date pickers
    initReportPickers();
});

/**
 * Initialize date pickers
 */
function initReportPickers() {
    const reportData = JSON.parse(document.getElementById('report-data').textContent);
    
    const startDateInput = document.getElementById('start_date');
    const endDateInput = document.getElementById('end_date');
    
    // Parse initial dates from hidden inputs
    const startDate = new Date(
        reportData.defaultStartYear,
        reportData.defaultStartMonth - 1,
        reportData.defaultStartDay
    );
    const endDate = new Date(
        reportData.defaultEndYear,
        reportData.defaultEndMonth - 1,
        reportData.defaultEndDay
    );
    
    // Initialize start date picker
    const startContainer = document.getElementById('start-date-picker');
    if (startContainer) {
        startDatePicker = new DatePicker(startContainer, {
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
        endDatePicker = new DatePicker(endContainer, {
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
 * Set date range to full year
 * @param {number} year - Year to set
 */
function setYearRange(year) {
    if (startDatePicker) {
        startDatePicker.setDate(new Date(year, 0, 1));
    }
    if (endDatePicker) {
        endDatePicker.setDate(new Date(year, 11, 31));
    }
}

/**
 * Set date range to year-to-date
 */
function setYTD() {
    const now = new Date();
    if (startDatePicker) {
        startDatePicker.setDate(new Date(now.getFullYear(), 0, 1));
    }
    if (endDatePicker) {
        endDatePicker.setDate(new Date(now.getFullYear(), now.getMonth(), now.getDate()));
    }
}

/**
 * Get date string from hidden input
 * @param {string} inputId - ID of hidden input
 * @returns {string} Date in YYYY-MM-DD format
 */
function getDateFromInput(inputId) {
    return document.getElementById(inputId).value;
}

/**
 * Calculate and display report preview
 */
function calculateTotals() {
    const startDate = getDateFromInput('start_date');
    const endDate = getDateFromInput('end_date');
    
    fetch(`/ledger/report/calculate?start=${startDate}&end=${endDate}`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                displayPreview(data);
            } else {
                alert('Error: ' + (data.error || 'Unknown error'));
            }
        })
        .catch(error => {
            console.error('Error calculating totals:', error);
            alert('Error calculating totals');
        });
}

/**
 * Display the report preview with calculated values
 * @param {Object} data - Response data with totals and categories
 */
function displayPreview(data) {
    document.getElementById('preview-results').style.display = 'block';
    
    document.getElementById('preview-income').textContent = formatCurrency(data.total_income);
    document.getElementById('preview-expenses').textContent = formatCurrency(data.total_expenses);
    document.getElementById('preview-net').textContent = formatCurrency(data.net_income);
    
    const netItem = document.querySelector('.summary-item.net');
    if (data.net_income < 0) {
        netItem.classList.add('negative');
    } else {
        netItem.classList.remove('negative');
    }
    
    // Build category breakdown
    const breakdownDiv = document.getElementById('category-breakdown');
    let html = '<h4>Expenses by Category</h4>';
    
    if (data.categories && data.categories.length > 0) {
        data.categories.forEach(cat => {
            html += `
                <div class="category-row">
                    <span class="category-name">${cat.name}</span>
                    <span class="category-amount">${formatCurrency(cat.total)}</span>
                </div>
            `;
        });
        
        html += `
            <div class="category-row total">
                <span class="category-name">TOTAL</span>
                <span class="category-amount">${formatCurrency(data.total_expenses)}</span>
            </div>
        `;
    } else {
        html += '<div class="category-row"><span class="category-name" style="color: #64748B;">No expenses in this period</span></div>';
    }
    
    breakdownDiv.innerHTML = html;
}

/**
 * Format number as currency
 * @param {number} amount - Amount to format
 * @returns {string} Formatted currency string
 */
function formatCurrency(amount) {
    return '$' + Math.abs(amount).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

/**
 * Generate and open PDF report
 */
function generateReport() {
    const startDate = getDateFromInput('start_date');
    const endDate = getDateFromInput('end_date');
    const includeDetails = document.getElementById('include-details').checked;
    
    const url = `/ledger/report/pdf?start=${startDate}&end=${endDate}&details=${includeDetails ? '1' : '0'}`;
    
    window.open(url, '_blank');
}
