// Main View (Dashboard) JavaScript - Extracted from main_view.html

// ===== COLOR PALETTE SYSTEM =====
const COLOR_PALETTE = {
    green: { name: 'Green', bg: '#D1F0E8', badge: '#00AA88', text: '#1F2937' },
    blue: { name: 'Blue', bg: '#DBEAFE', badge: '#3B82F6', text: '#1F2937' },
    purple: { name: 'Purple', bg: '#E9D5FF', badge: '#A855F7', text: '#1F2937' },
    pink: { name: 'Pink', bg: '#FCE7F3', badge: '#EC4899', text: '#1F2937' },
    yellow: { name: 'Yellow', bg: '#FEF3C7', badge: '#F59E0B', text: '#1F2937' },
    orange: { name: 'Orange', bg: '#FFEDD5', badge: '#F97316', text: '#1F2937' },
    teal: { name: 'Teal', bg: '#CCFBF1', badge: '#14B8A6', text: '#1F2937' },
    gray: { name: 'Gray', bg: '#F3F4F6', badge: '#6B7280', text: '#1F2937' }
};

function getColors(colorKey) {
    return COLOR_PALETTE[colorKey] || COLOR_PALETTE.green;
}

// Apply colors to client cards when page loads
document.addEventListener('DOMContentLoaded', function() {
    // Apply colors to client cards
    document.querySelectorAll('.client-card').forEach(card => {
        const colorKey = card.dataset.color;
        if (colorKey) {
            const colors = getColors(colorKey);
            card.style.backgroundColor = colors.bg;
            
            // Update the type badge
            const badge = card.querySelector('.type-badge');
            if (badge) {
                badge.style.backgroundColor = colors.badge;
                badge.style.color = 'white';
            }
        }
    });
});

// ===== EXISTING MAIN VIEW CODE =====

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

// Load saved card order on page load
loadCardOrder();

// ===== FILTER DROPDOWN FUNCTIONALITY =====

const filterButton = document.getElementById('filter-button');
const filterDropdown = document.getElementById('filter-dropdown');

if (filterButton && filterDropdown) {
    filterButton.addEventListener('click', function(e) {
        e.stopPropagation();
        
        // Close all other dropdowns
        document.querySelectorAll('[id$="-dropdown"]').forEach(d => {
            if (d.id !== 'filter-dropdown') d.style.display = 'none';
        });
        
        // Toggle this dropdown
        filterDropdown.style.display = filterDropdown.style.display === 'none' ? 'block' : 'none';
    });
    
    // SERVER-SIDE FILTER: Submit to server when checkboxes change
    document.querySelectorAll('#filter-form input[type="checkbox"]').forEach(checkbox => {
        checkbox.addEventListener('change', function() {
            // Build URL with selected types
            const selectedTypes = Array.from(document.querySelectorAll('#filter-form input[type="checkbox"]:checked'))
                .map(cb => cb.value);
            
            // Get other URL parameters
            const urlParams = new URLSearchParams(window.location.search);
            const sort = urlParams.get('sort') || 'last_name';
            const order = urlParams.get('order') || 'asc';
            const search = urlParams.get('search') || '';
            
            // Get CURRENT view from URL (don't default to 'detailed')
            const view = urlParams.get('view') || '';
            
            // Build new URL
            let newUrl = '?';
            selectedTypes.forEach(typeId => {
                newUrl += `type=${typeId}&`;
            });
            newUrl += `sort=${sort}&order=${order}`;
            if (view) {
                newUrl += `&view=${view}`;
            }
            if (search) {
                newUrl += `&search=${encodeURIComponent(search)}`;
            }
            
            // Navigate to new URL (server will filter)
            window.location.href = newUrl;
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

// ===== SEARCH FUNCTIONALITY (CLIENT-SIDE FOR SPEED) =====

const searchInput = document.querySelector('.search-box input[name="search"]');
const clearSearchBtn = document.querySelector('.clear-search');
const searchForm = document.querySelector('.search-box');

// Strip phone formatting for smart matching
function stripPhoneFormat(text) {
    return text.replace(/[\s\-\(\)\.\+]/g, '');
}

// Search function (client-side filtering of visible cards)
function performSearch() {
    const clientCards = document.querySelectorAll('.client-card');
    const searchTerm = searchInput.value.toLowerCase().trim();
    
    // Show/hide clear button
    if (clearSearchBtn) {
        clearSearchBtn.style.display = searchTerm ? 'block' : 'none';
    }
    
    if (!searchTerm) {
        // No search term - show all cards
        clientCards.forEach(card => {
            card.style.display = '';
        });
        return;
    }
    
    // Strip formatting from search term if it looks like a phone number
    const searchTermStripped = stripPhoneFormat(searchTerm);
    const isPhoneSearch = /^\d+$/.test(searchTermStripped);
    
    clientCards.forEach(card => {
        // Extract searchable text from card
        const fileNumber = card.querySelector('.file-number')?.textContent || '';
        const clientName = card.querySelector('.client-name')?.textContent || '';
        const email = card.querySelector('.contact-link[href^="mailto:"] span')?.textContent || '';
        const phoneElement = card.querySelector('.contact-link[href^="tel:"] span, .contact-link[href^="sms:"] span');
        const phone = phoneElement?.textContent || '';
        
        // Combine all searchable fields (except phone for now)
        const searchableText = `${fileNumber} ${clientName} ${email}`.toLowerCase();
        
        // For phone, use stripped version if searching numbers
        let phoneMatch = false;
        if (isPhoneSearch && phone) {
            const phoneStripped = stripPhoneFormat(phone);
            phoneMatch = phoneStripped.includes(searchTermStripped);
        } else {
            phoneMatch = phone.toLowerCase().includes(searchTerm);
        }
        
        // Check if search term matches
        const textMatch = searchableText.includes(searchTerm);
        const matches = textMatch || phoneMatch;
        
        // Show or hide card
        card.style.display = matches ? '' : 'none';
    });
}

// Real-time search as user types
if (searchInput) {
    searchInput.addEventListener('input', performSearch);
}

// Clear search button
if (clearSearchBtn) {
    clearSearchBtn.addEventListener('click', function() {
        searchInput.value = '';
        performSearch();
        searchInput.focus();
    });
}

// Submit search to server when Enter is pressed (for full search across all types)
if (searchForm) {
    searchForm.addEventListener('submit', function(e) {
        // If there's a search term, submit to server for full search
        // Otherwise prevent submission
        if (!searchInput.value.trim()) {
            e.preventDefault();
        }
        // If there IS a search term, let it submit to server
    });
}

// Run search on page load if there's a search term from URL
document.addEventListener('DOMContentLoaded', function() {
    if (searchInput && searchInput.value) {
        performSearch();
    }
});

// ===== IPAD LANDSCAPE VIEW TOGGLE MANAGEMENT =====
// Disable detailed view on iPad landscape (too wide for screen)

// Track if we've already added the click prevention listener
let detailedClickListenerAdded = false;

function manageViewToggleForDevice() {
    // Detect if device is touch-enabled
    const isTouchDevice = ('ontouchstart' in window) || 
                         (navigator.maxTouchPoints > 0) || 
                         (navigator.msMaxTouchPoints > 0);
    
    if (!isTouchDevice) {
        return; // Desktop, do nothing
    }
    
    // Check if in portrait mode (taller than wide)
    const isPortrait = window.innerHeight > window.innerWidth;
    
    // Check if width is in iPad range (700-1366px)
    const isIPadWidth = window.innerWidth >= 700 && window.innerWidth <= 1366;
    
    // Find the Detailed button
    const viewToggleBtns = document.querySelectorAll('.view-toggle-btn');
    let detailedBtn = null;
    
    viewToggleBtns.forEach(btn => {
        if (btn.textContent.trim() === 'Detailed') {
            detailedBtn = btn;
        }
    });
    
    if (!detailedBtn) {
        return; // Button not found
    }
    
    // iPad in portrait mode - disable Detailed button (too narrow for wide layout)
    if (isPortrait && isIPadWidth) {
        detailedBtn.style.opacity = '0.5';
        detailedBtn.style.cursor = 'not-allowed';
        detailedBtn.style.pointerEvents = 'none';
        
        // Add click prevention listener (only once)
        if (!detailedClickListenerAdded) {
            detailedBtn.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                return false;
            });
            detailedClickListenerAdded = true;
        }
        
        // Check if currently in Detailed view and redirect to Compact
        const urlParams = new URLSearchParams(window.location.search);
        const currentView = urlParams.get('view');
        
        if (currentView === 'detailed') {
            // Build new URL with compact view
            urlParams.set('view', 'compact');
            const newUrl = `${window.location.pathname}?${urlParams.toString()}`;
            window.location.href = newUrl;
        }
    } else {
        // Landscape or desktop - enable Detailed button
        detailedBtn.style.opacity = '1';
        detailedBtn.style.cursor = 'pointer';
        detailedBtn.style.pointerEvents = 'auto';
    }
}

// ============================================================
// RETENTION SYSTEM JAVASCRIPT
// Add these functions to main_view.js
// ============================================================

// Check for clients due for deletion on page load
document.addEventListener('DOMContentLoaded', function() {
    checkRetention();
});

function checkRetention() {
    fetch('/api/retention-check')
        .then(response => response.json())
        .then(data => {
            if (data.clients_due && data.clients_due.length > 0) {
                showRetentionModal(data.clients_due);
            }
        })
        .catch(error => {
            console.error('Error checking retention:', error);
        });
}

function showRetentionModal(clients) {
    const modal = document.getElementById('retention-modal');
    const listContainer = document.getElementById('retention-list');
    
    // Build the list HTML
    let html = '';
    clients.forEach(client => {
        html += `
            <div class="retention-item">
                <input type="checkbox" 
                       id="retention-${client.id}" 
                       value="${client.id}"
                       onchange="updateDeleteButton()">
                <div class="retention-item-details">
                    <div class="retention-item-header">
                        <span class="retention-item-name">
                            ${escapeHtml(client.full_name)}
                            ${client.is_minor ? '<span class="minor-badge">Minor</span>' : ''}
                        </span>
                        <span class="retention-item-file-number">${escapeHtml(client.file_number)}</span>
                    </div>
                    <div class="retention-item-dates">
                        <span>First contact: ${client.first_contact_display}</span>
                        <span>Last contact: ${client.last_contact_display}</span>
                        <span>Retain until: ${client.retain_until_display}</span>
                    </div>
                </div>
            </div>
        `;
    });
    
    listContainer.innerHTML = html;
    modal.style.display = 'flex';
    
    // Re-initialize Lucide icons in modal
    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }
}

function closeRetentionModal() {
    document.getElementById('retention-modal').style.display = 'none';
}

function updateDeleteButton() {
    const checkboxes = document.querySelectorAll('#retention-list input[type="checkbox"]:checked');
    const btn = document.getElementById('delete-selected-btn');
    const count = checkboxes.length;
    
    btn.disabled = count === 0;
    if (count === 0) {
        btn.style.background = '#9CA3AF';
        btn.style.cursor = 'not-allowed';
    } else {
        btn.style.background = '#DC2626';
        btn.style.cursor = 'pointer';
    }
    btn.textContent = `Delete Selected (${count})`;
}

let pendingDeleteIds = [];

function deleteSelectedClients() {
    const checkboxes = document.querySelectorAll('#retention-list input[type="checkbox"]:checked');
    pendingDeleteIds = Array.from(checkboxes).map(cb => parseInt(cb.value));
    
    if (pendingDeleteIds.length === 0) return;
    
    // Show confirmation modal
    document.getElementById('delete-count').textContent = pendingDeleteIds.length;
    document.getElementById('delete-confirm-modal').style.display = 'flex';
}

function cancelDeletion() {
    document.getElementById('delete-confirm-modal').style.display = 'none';
    pendingDeleteIds = [];
}

function confirmDeletion() {
    document.getElementById('delete-confirm-modal').style.display = 'none';
    
    // Disable button and show loading state
    const btn = document.getElementById('delete-selected-btn');
    btn.disabled = true;
    btn.style.background = '#9CA3AF';
    btn.style.cursor = 'not-allowed';
    btn.textContent = 'Deleting...';
    
    fetch('/api/retention-delete', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ client_ids: pendingDeleteIds })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            closeRetentionModal();
            window.location.reload();
        } else {
            alert('Error: ' + (data.error || 'Unknown error'));
            btn.disabled = false;
            updateDeleteButton();
        }
    })
    .catch(error => {
        console.error('Error deleting clients:', error);
        alert('An error occurred while deleting clients.');
        btn.disabled = false;
        updateDeleteButton();
    });
    
    pendingDeleteIds = [];
}

// Helper function to escape HTML
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Add spinning animation for loader
const style = document.createElement('style');
style.textContent = `
    @keyframes spin {
        from { transform: rotate(0deg); }
        to { transform: rotate(360deg); }
    }
    .spinning {
        animation: spin 1s linear infinite;
    }
`;
document.head.appendChild(style);

// Run on page load
document.addEventListener('DOMContentLoaded', manageViewToggleForDevice);

// Run on orientation change
window.addEventListener('orientationchange', function() {
    // Small delay to let browser update dimensions
    setTimeout(manageViewToggleForDevice, 100);
});

// Also run on resize (catches all cases)
window.addEventListener('resize', manageViewToggleForDevice);