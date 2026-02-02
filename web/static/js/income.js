/**
 * Income Entry Form - EdgeCase Equalizer
 * Autocomplete for payor, date picker, amount formatting, entry deletion
 * File uploads handled by shared file-upload.js
 */

// ============================================================
// AUTOCOMPLETE COMPONENT
// ============================================================

/**
 * Create an autocomplete field with removable suggestions
 * @param {string} containerId - ID of wrapper div
 * @param {string} hiddenInputId - ID of hidden input to store value
 * @param {string[]} suggestions - Array of suggestion strings
 * @param {string} initialValue - Initial value
 * @param {string} placeholder - Placeholder text
 * @param {string} removeEndpoint - API endpoint to remove suggestion (optional)
 */
function createAutocomplete(containerId, hiddenInputId, suggestions, initialValue, placeholder, removeEndpoint) {
    const container = document.getElementById(containerId);
    const hiddenInput = document.getElementById(hiddenInputId);
    
    // Track suggestions locally (can be modified by X buttons)
    let localSuggestions = [...suggestions];
    
    // Create visible input
    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'autocomplete-input';
    input.placeholder = placeholder;
    input.value = initialValue || '';
    input.autocomplete = 'off';
    
    // Create dropdown
    const dropdown = document.createElement('div');
    dropdown.className = 'autocomplete-dropdown';
    dropdown.style.display = 'none';
    
    container.appendChild(input);
    container.appendChild(dropdown);
    
    // Sync to hidden input
    function syncValue() {
        hiddenInput.value = input.value;
    }
    
    // Render dropdown
    function renderDropdown(filter = '') {
        const filtered = localSuggestions.filter(s => 
            s.toLowerCase().includes(filter.toLowerCase())
        );
        
        if (filtered.length === 0) {
            dropdown.style.display = 'none';
            return;
        }
        
        dropdown.innerHTML = '';
        filtered.forEach(suggestion => {
            const item = document.createElement('div');
            item.className = 'autocomplete-item';
            
            const text = document.createElement('span');
            text.className = 'autocomplete-text';
            text.textContent = suggestion;
            
            const removeBtn = document.createElement('button');
            removeBtn.type = 'button';
            removeBtn.className = 'autocomplete-remove';
            removeBtn.innerHTML = '×';
            removeBtn.title = 'Remove from list';
            
            // Click suggestion text to select
            text.addEventListener('click', () => {
                input.value = suggestion;
                syncValue();
                dropdown.style.display = 'none';
            });
            
            // Click X to remove from suggestions
            removeBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                localSuggestions = localSuggestions.filter(s => s !== suggestion);
                
                // Call API to persist removal
                if (removeEndpoint) {
                    fetch(removeEndpoint, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ name: suggestion })
                    });
                }
                
                renderDropdown(input.value);
            });
            
            item.appendChild(text);
            item.appendChild(removeBtn);
            dropdown.appendChild(item);
        });
        
        dropdown.style.display = 'block';
    }
    
    // Event listeners
    input.addEventListener('input', () => {
        syncValue();
        renderDropdown(input.value);
    });
    
    input.addEventListener('focus', () => {
        renderDropdown(input.value);
    });
    
    // Close dropdown when clicking outside
    document.addEventListener('click', (e) => {
        if (!container.contains(e.target)) {
            dropdown.style.display = 'none';
        }
    });
    
    // Keyboard navigation
    input.addEventListener('keydown', (e) => {
        const items = dropdown.querySelectorAll('.autocomplete-item');
        const active = dropdown.querySelector('.autocomplete-item.active');
        
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            if (!active && items.length > 0) {
                items[0].classList.add('active');
            } else if (active && active.nextElementSibling) {
                active.classList.remove('active');
                active.nextElementSibling.classList.add('active');
            }
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            if (active && active.previousElementSibling) {
                active.classList.remove('active');
                active.previousElementSibling.classList.add('active');
            }
        } else if (e.key === 'Enter' && active) {
            e.preventDefault();
            const text = active.querySelector('.autocomplete-text').textContent;
            input.value = text;
            syncValue();
            dropdown.style.display = 'none';
        } else if (e.key === 'Escape') {
            dropdown.style.display = 'none';
        }
    });
    
    // Initial sync
    syncValue();
}

// ============================================================
// INITIALIZE AUTOCOMPLETE
// ============================================================

document.addEventListener('DOMContentLoaded', () => {
    createAutocomplete(
        'payor-autocomplete',
        'source',
        payorSuggestions,
        initialPayor,
        'e.g., Jane Smith (20240502-JS)',
        '/ledger/suggestion/payor/remove'
    );
});

// ============================================================
// DATE PICKER
// ============================================================

function initIncomePickers() {
    const dateInput = document.getElementById('date');
    
    let initialDate;
    if (dateInput.value) {
        initialDate = parseDateString(dateInput.value);
    } else {
        initialDate = new Date();
        const year = initialDate.getFullYear();
        const month = String(initialDate.getMonth() + 1).padStart(2, '0');
        const day = String(initialDate.getDate()).padStart(2, '0');
        dateInput.value = `${year}-${month}-${day}`;
    }
    
    initDatePicker('income-date-picker', {
        initialDate: initialDate,
        onSelect: (date) => {
            const year = date.getFullYear();
            const month = String(date.getMonth() + 1).padStart(2, '0');
            const day = String(date.getDate()).padStart(2, '0');
            dateInput.value = `${year}-${month}-${day}`;
        }
    });
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initIncomePickers);
} else {
    initIncomePickers();
}

// ============================================================
// AMOUNT FORMATTING
// ============================================================

const totalAmountInput = document.getElementById('total_amount');
const taxAmountInput = document.getElementById('tax_amount');

if (totalAmountInput) {
    totalAmountInput.addEventListener('blur', function() {
        if (this.value) this.value = parseFloat(this.value).toFixed(2);
    });
}

if (taxAmountInput) {
    taxAmountInput.addEventListener('blur', function() {
        if (this.value) this.value = parseFloat(this.value).toFixed(2);
    });
}

// ============================================================
// ENTRY DELETION (specific to income entry)
// ============================================================

function confirmDeleteEntry() {
    document.getElementById('delete-entry-modal').style.display = 'flex';
}

function closeDeleteEntryModal() {
    document.getElementById('delete-entry-modal').style.display = 'none';
}

function deleteEntry() {
    const entryId = window.location.pathname.split('/')[3];
    fetch(`/ledger/income/${entryId}/delete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    })
        .then(r => r.ok ? window.location.href = '/ledger' : alert('Error'))
        .catch(() => alert('Error'));
}
