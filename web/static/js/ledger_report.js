/**
 * Ledger Report Page JavaScript - EdgeCase Equalizer
 * Handles financial report generation with date range selection and preview.
 */

document.addEventListener('DOMContentLoaded', function() {
    // Initialize Lucide icons
    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }
});

/**
 * Get date string from dropdown selectors
 * @param {string} prefix - Prefix for element IDs ('start' or 'end')
 * @returns {string} Date in YYYY-MM-DD format
 */
function getDateFromDropdowns(prefix) {
    const year = document.getElementById(prefix + '-year').value;
    const month = document.getElementById(prefix + '-month').value.padStart(2, '0');
    const day = document.getElementById(prefix + '-day').value.padStart(2, '0');
    return `${year}-${month}-${day}`;
}

/**
 * Set date in dropdown selectors
 * @param {string} prefix - Prefix for element IDs
 * @param {number} year - Year value
 * @param {number} month - Month value (1-12)
 * @param {number} day - Day value
 */
function setDateInDropdowns(prefix, year, month, day) {
    document.getElementById(prefix + '-year').value = year;
    document.getElementById(prefix + '-month').value = month;
    document.getElementById(prefix + '-day').value = day;
}

/**
 * Set date range to full year
 * @param {number} year - Year to set
 */
function setYearRange(year) {
    setDateInDropdowns('start', year, 1, 1);
    setDateInDropdowns('end', year, 12, 31);
}

/**
 * Set date range to year-to-date
 */
function setYTD() {
    const now = new Date();
    const year = now.getFullYear();
    setDateInDropdowns('start', year, 1, 1);
    setDateInDropdowns('end', year, now.getMonth() + 1, now.getDate());
}

/**
 * Calculate and display report preview
 */
function calculateTotals() {
    const startDate = getDateFromDropdowns('start');
    const endDate = getDateFromDropdowns('end');
    
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
    const startDate = getDateFromDropdowns('start');
    const endDate = getDateFromDropdowns('end');
    const includeDetails = document.getElementById('include-details').checked;
    
    const url = `/ledger/report/pdf?start=${startDate}&end=${endDate}&details=${includeDetails ? '1' : '0'}`;
    
    window.open(url, '_blank');
}
