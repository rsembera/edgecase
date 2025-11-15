// Main View (Dashboard) JavaScript - Extracted from main_view.html

function toggleDropdown(id) {
    const dropdown = document.getElementById(id);
    // Close all other dropdowns
    document.querySelectorAll('[id$="-dropdown"]').forEach(d => {
        if (d.id !== id) d.style.display = 'none';
    });
    dropdown.style.display = dropdown.style.display === 'none' ? 'block' : 'none';
}

// Close dropdowns when clicking outside
document.addEventListener('click', function(event) {
    if (!event.target.closest('.dropdown-btn') && !event.target.closest('[id$="-dropdown"]')) {
        document.querySelectorAll('[id$="-dropdown"]').forEach(d => d.style.display = 'none');
    }
});

// Live clock update - synchronized with system clock
function updateClock() {
    const now = new Date();
    
    // Format time: "12:45:30 PM"
    let hours = now.getHours();
    const minutes = now.getMinutes();
    const ampm = hours >= 12 ? 'PM' : 'AM';
    hours = hours % 12;
    hours = hours ? hours : 12; // 0 should be 12
    const minutesStr = minutes < 10 ? '0' + minutes : minutes;
    const timeStr = `${hours}:${minutesStr} ${ampm}`;
    
    // Format date: "November 9, 2025"
    const months = ['January', 'February', 'March', 'April', 'May', 'June',
                   'July', 'August', 'September', 'October', 'November', 'December'];
    const dateStr = `${months[now.getMonth()]} ${now.getDate()}, ${now.getFullYear()}`;
    
    // Update DOM
    const timeEl = document.getElementById('current-time');
    const dateEl = document.getElementById('current-date');
    if (timeEl) timeEl.textContent = timeStr;
    if (dateEl) dateEl.textContent = dateStr;
}

// Update immediately on page load
updateClock();

// Synchronize with system clock - update at the start of each second
function syncClock() {
    const now = new Date();
    const msUntilNextSecond = 1000 - now.getMilliseconds();
    
    setTimeout(function() {
        updateClock();
        // After first sync, update every second
        setInterval(updateClock, 1000);
    }, msUntilNextSecond);
}

syncClock();

// ===== DRAG AND DROP FUNCTIONALITY WITH TOUCH SUPPORT =====

let draggedCard = null;
let touchStartX = 0;
let touchStartY = 0;
let isDragging = false;
let hasMoved = false; // Track if card actually moved

// Get all draggable cards
const cards = document.querySelectorAll('.stat-card[draggable="true"]');

// Disable dragging on touch devices (iPad/mobile)
if ('ontouchstart' in window) {
    cards.forEach(card => {
        card.setAttribute('draggable', 'false');
        card.style.cursor = 'default';
        // Also prevent the dragstart event entirely
        card.addEventListener('dragstart', function(e) {
            e.preventDefault();
            return false;
        });
    });
}

// Load saved order from localStorage
function loadCardOrder() {
    const savedOrder = localStorage.getItem('cardOrder');
    if (savedOrder) {
        const orderArray = JSON.parse(savedOrder);
        const container = document.getElementById('stats-container');
        
        // Reorder cards based on saved order
        orderArray.forEach(cardId => {
            const card = container.querySelector(`[data-card-id="${cardId}"]`);
            if (card) {
                container.appendChild(card);
            }
        });
    }
}

// Save card order to localStorage
function saveCardOrder() {
    const container = document.getElementById('stats-container');
    const cards = container.querySelectorAll('.stat-card[data-card-id]');
    const order = Array.from(cards).map(card => card.dataset.cardId);
    localStorage.setItem('cardOrder', JSON.stringify(order));
}

// MOUSE DRAG HANDLERS (for desktop)
cards.forEach(card => {
    // Prevent clicks on links/buttons during drag
    card.addEventListener('click', function(e) {
        if (hasMoved) {
            e.preventDefault();
            e.stopPropagation();
            hasMoved = false; // Reset for next interaction
        }
    }, true); // Use capture phase to intercept before link clicks
    
    card.addEventListener('dragstart', function(e) {
        draggedCard = this;
        hasMoved = false; // Reset at start
        this.classList.add('dragging');
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/html', this.innerHTML);
    });
    
    card.addEventListener('dragend', function(e) {
        this.classList.remove('dragging');
        // Remove drag-over class from all cards
        cards.forEach(c => c.classList.remove('drag-over'));
        // Save the new order
        saveCardOrder();
        
        // If card moved, prevent any clicks for a moment
        if (hasMoved) {
            setTimeout(() => { hasMoved = false; }, 100);
        }
    });
    
    card.addEventListener('dragover', function(e) {
        if (e.preventDefault) {
            e.preventDefault();
        }
        e.dataTransfer.dropEffect = 'move';
        
        // Add visual feedback
        if (this !== draggedCard) {
            this.classList.add('drag-over');
        }
        
        return false;
    });
    
    card.addEventListener('dragleave', function(e) {
        this.classList.remove('drag-over');
    });
    
    card.addEventListener('drop', function(e) {
        if (e.stopPropagation) {
            e.stopPropagation();
        }
        
        // Don't drop on itself
        if (draggedCard !== this) {
            hasMoved = true; // Card was actually moved
            
            // TRUE SWAP: Simply exchange the two cards' positions
            const container = draggedCard.parentNode;
            
            // Create a temporary placeholder
            const placeholder = document.createElement('div');
            
            // Insert placeholder where dragged card is
            container.insertBefore(placeholder, draggedCard);
            
            // Move dragged card to where target is
            container.insertBefore(draggedCard, this);
            
            // Move target to where placeholder is (where dragged card was)
            container.insertBefore(this, placeholder);
            
            // Remove placeholder
            container.removeChild(placeholder);
        }
        
        this.classList.remove('drag-over');
        return false;
    });
});


// Load saved order on page load
document.addEventListener('DOMContentLoaded', function() {
    loadCardOrder();
});

// ===== SESSION PERSISTENCE FOR FILTER/SORT/VIEW =====

// Save current settings to sessionStorage whenever the page loads
function saveCurrentSettings() {
    const urlParams = new URLSearchParams(window.location.search);
    const settings = {
        types: urlParams.getAll('type'),
        sort: urlParams.get('sort') || 'last_name',
        order: urlParams.get('order') || 'asc',
        view: urlParams.get('view') || 'compact',
        search: urlParams.get('search') || ''
    };
    sessionStorage.setItem('viewSettings', JSON.stringify(settings));
}

// Restore settings from sessionStorage on page load
function restoreSettings() {
    const saved = sessionStorage.getItem('viewSettings');
    
    // If no saved settings, this is first visit in session - use defaults
    if (!saved) {
        return;
    }
    
    // Parse saved settings
    const settings = JSON.parse(saved);
    const urlParams = new URLSearchParams(window.location.search);
    
    // Check if URL already has parameters (user clicked something)
    const hasParams = urlParams.toString().length > 0;
    
    // If URL has no parameters, restore from session
    if (!hasParams) {
        const newParams = new URLSearchParams();
        
        // Restore type filters
        settings.types.forEach(type => newParams.append('type', type));
        
        // Restore sort, order, view
        newParams.set('sort', settings.sort);
        newParams.set('order', settings.order);
        newParams.set('view', settings.view);
        
        // Restore search if it exists
        if (settings.search) {
            newParams.set('search', settings.search);
        }
        
        // Redirect with restored settings
        window.location.search = newParams.toString();
    }
}

// On page load: restore settings if available, then save current state
document.addEventListener('DOMContentLoaded', function() {
    restoreSettings();
    saveCurrentSettings();
});

// Auto-switch to compact view on narrow screens (portrait iPad)
function checkViewMode() {
    const urlParams = new URLSearchParams(window.location.search);
    const currentView = urlParams.get('view') || 'compact';
    
    // If screen is narrow (portrait) and in detailed view, switch to compact
    if (window.innerWidth < 900 && currentView === 'detailed') {
        urlParams.set('view', 'compact');
        window.location.search = urlParams.toString();
    }
}

// Check on page load
checkViewMode();

// Check when device rotates
window.addEventListener('resize', checkViewMode);

// Handle filter dropdown
const filterButton = document.getElementById('filter-button');
const filterDropdown = document.getElementById('filter-dropdown');

if (filterButton && filterDropdown) {
    // Open/close on button click
    filterButton.addEventListener('click', function(event) {
        event.stopPropagation();
        
        // Close other dropdowns
        document.querySelectorAll('[id$="-dropdown"]').forEach(d => {
            if (d.id !== 'filter-dropdown') d.style.display = 'none';
        });
        
        // Toggle this dropdown
        filterDropdown.style.display = filterDropdown.style.display === 'none' ? 'block' : 'none';
    });
    
    // Update button text as checkboxes change
    document.querySelectorAll('#filter-form input[type="checkbox"]').forEach(checkbox => {
        checkbox.addEventListener('change', function() {
            const checkedCount = document.querySelectorAll('#filter-form input[type="checkbox"]:checked').length;
            filterButton.textContent = `Filter: ${checkedCount} type${checkedCount !== 1 ? 's' : ''} ▾`;
        });
    });
    
    // Close dropdown when clicking outside
    document.addEventListener('click', function(event) {
        if (filterDropdown.style.display === 'block') {
            const isClickInside = filterDropdown.contains(event.target) || filterButton.contains(event.target);
            if (!isClickInside) {
                filterDropdown.style.display = 'none';
            }
        }
    });
}
