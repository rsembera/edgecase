/**
 * Main View (Dashboard) JavaScript - EdgeCase Equalizer
 * Handles client list display, filtering, searching, card drag-drop, and retention checks.
 */

// ============================================================
// COLOR PALETTE
// ============================================================

const COLOR_PALETTE = {
    green:  { name: 'Green',  bg: '#D1F0E8', badge: '#00AA88', text: '#1F2937' },
    blue:   { name: 'Blue',   bg: '#DBEAFE', badge: '#3B82F6', text: '#1F2937' },
    purple: { name: 'Purple', bg: '#E9D5FF', badge: '#A855F7', text: '#1F2937' },
    pink:   { name: 'Pink',   bg: '#FCE7F3', badge: '#EC4899', text: '#1F2937' },
    yellow: { name: 'Yellow', bg: '#FEF3C7', badge: '#F59E0B', text: '#1F2937' },
    orange: { name: 'Orange', bg: '#FFEDD5', badge: '#F97316', text: '#1F2937' },
    teal:   { name: 'Teal',   bg: '#CCFBF1', badge: '#14B8A6', text: '#1F2937' },
    gray:   { name: 'Gray',   bg: '#F3F4F6', badge: '#6B7280', text: '#1F2937' }
};

/**
 * Get color scheme for a given color key
 * @param {string} colorKey - Key from COLOR_PALETTE
 * @returns {Object} Color scheme with bg, badge, and text colors
 */
function getColors(colorKey) {
    return COLOR_PALETTE[colorKey] || COLOR_PALETTE.green;
}

/**
 * Apply color scheme to all client cards based on their data-color attribute
 */
function applyClientCardColors() {
    document.querySelectorAll('.client-card').forEach(card => {
        const colorKey = card.dataset.color;
        if (colorKey) {
            const colors = getColors(colorKey);
            card.style.backgroundColor = colors.bg;
            
            const badge = card.querySelector('.type-badge');
            if (badge) {
                badge.style.backgroundColor = colors.badge;
                badge.style.color = 'white';
            }
        }
    });
}

// ============================================================
// DROPDOWN MENUS
// ============================================================

/**
 * Toggle visibility of a dropdown menu
 * @param {string} id - DOM id of the dropdown element
 */
function toggleDropdown(id) {
    const dropdown = document.getElementById(id);
    
    // Close all other dropdowns first
    document.querySelectorAll('[id$="-dropdown"]').forEach(d => {
        if (d.id !== id) d.style.display = 'none';
    });
    
    dropdown.style.display = dropdown.style.display === 'none' ? 'block' : 'none';
}

/**
 * Close all dropdowns when clicking outside
 */
function initDropdownCloseHandler() {
    document.addEventListener('click', function(event) {
        if (!event.target.closest('.dropdown-btn') && !event.target.closest('[id$="-dropdown"]')) {
            document.querySelectorAll('[id$="-dropdown"]').forEach(d => d.style.display = 'none');
        }
    });
}

// ============================================================
// LIVE CLOCK
// ============================================================

/**
 * Update the clock display with current time and date
 */
function updateClock() {
    const now = new Date();
    
    // Format time: "12:45 PM"
    let hours = now.getHours();
    const minutes = now.getMinutes();
    const ampm = hours >= 12 ? 'PM' : 'AM';
    hours = hours % 12 || 12;
    const timeStr = `${hours}:${minutes.toString().padStart(2, '0')} ${ampm}`;
    
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

/**
 * Synchronize clock updates with system clock (update at start of each second)
 */
function syncClock() {
    updateClock();
    const msUntilNextSecond = 1000 - new Date().getMilliseconds();
    
    setTimeout(function() {
        updateClock();
        setInterval(updateClock, 1000);
    }, msUntilNextSecond);
}

// ============================================================
// STAT CARD DRAG AND DROP
// ============================================================

let draggedCard = null;
let hasMoved = false;

/**
 * Load saved card order from localStorage and reorder cards
 */
function loadCardOrder() {
    const savedOrder = localStorage.getItem('cardOrder');
    if (!savedOrder) return;
    
    const orderArray = JSON.parse(savedOrder);
    const container = document.getElementById('stats-container');
    if (!container) return;
    
    orderArray.forEach(cardId => {
        const card = container.querySelector(`[data-card-id="${cardId}"]`);
        if (card) container.appendChild(card);
    });
}

/**
 * Save current card order to localStorage
 */
function saveCardOrder() {
    const container = document.getElementById('stats-container');
    if (!container) return;
    
    const cards = container.querySelectorAll('.stat-card[data-card-id]');
    const order = Array.from(cards).map(card => card.dataset.cardId);
    localStorage.setItem('cardOrder', JSON.stringify(order));
}

/**
 * Initialize drag and drop functionality for stat cards
 */
function initCardDragDrop() {
    const cards = document.querySelectorAll('.stat-card[draggable="true"]');
    
    // Disable dragging on touch devices
    if ('ontouchstart' in window) {
        cards.forEach(card => {
            card.setAttribute('draggable', 'false');
            card.style.cursor = 'default';
            card.addEventListener('dragstart', e => e.preventDefault());
        });
        return;
    }
    
    cards.forEach(card => {
        // Prevent clicks during drag
        card.addEventListener('click', function(e) {
            if (hasMoved) {
                e.preventDefault();
                e.stopPropagation();
                hasMoved = false;
            }
        }, true);
        
        card.addEventListener('dragstart', function(e) {
            draggedCard = this;
            hasMoved = false;
            this.classList.add('dragging');
            e.dataTransfer.effectAllowed = 'move';
        });
        
        card.addEventListener('dragend', function() {
            this.classList.remove('dragging');
            cards.forEach(c => c.classList.remove('drag-over'));
            saveCardOrder();
            if (hasMoved) setTimeout(() => hasMoved = false, 100);
        });
        
        card.addEventListener('dragover', function(e) {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            if (this !== draggedCard) this.classList.add('drag-over');
            return false;
        });
        
        card.addEventListener('dragleave', function() {
            this.classList.remove('drag-over');
        });
        
        card.addEventListener('drop', function(e) {
            e.stopPropagation();
            
            if (draggedCard !== this) {
                hasMoved = true;
                const container = draggedCard.parentNode;
                const placeholder = document.createElement('div');
                
                container.insertBefore(placeholder, draggedCard);
                container.insertBefore(draggedCard, this);
                container.insertBefore(this, placeholder);
                container.removeChild(placeholder);
            }
            
            this.classList.remove('drag-over');
            return false;
        });
    });
}

// ============================================================
// CLIENT TYPE FILTER
// ============================================================

/**
 * Initialize the filter dropdown and checkbox handling
 */
function initFilterDropdown() {
    const filterButton = document.getElementById('filter-button');
    const filterDropdown = document.getElementById('filter-dropdown');
    
    if (!filterButton || !filterDropdown) return;
    
    filterButton.addEventListener('click', function(e) {
        e.stopPropagation();
        document.querySelectorAll('[id$="-dropdown"]').forEach(d => {
            if (d.id !== 'filter-dropdown') d.style.display = 'none';
        });
        filterDropdown.style.display = filterDropdown.style.display === 'none' ? 'block' : 'none';
    });
    
    // Submit to server when checkboxes change
    document.querySelectorAll('#filter-form input[type="checkbox"]').forEach(checkbox => {
        checkbox.addEventListener('change', function() {
            const selectedTypes = Array.from(
                document.querySelectorAll('#filter-form input[type="checkbox"]:checked')
            ).map(cb => cb.value);
            
            const urlParams = new URLSearchParams(window.location.search);
            const sort = urlParams.get('sort') || 'last_name';
            const order = urlParams.get('order') || 'asc';
            const search = urlParams.get('search') || '';
            const view = urlParams.get('view') || '';
            
            let newUrl = '?';
            selectedTypes.forEach(typeId => newUrl += `type=${typeId}&`);
            newUrl += `sort=${sort}&order=${order}`;
            if (view) newUrl += `&view=${view}`;
            if (search) newUrl += `&search=${encodeURIComponent(search)}`;
            
            window.location.href = newUrl;
        });
    });
    
    // Close dropdown when clicking outside
    document.addEventListener('click', function(event) {
        if (filterDropdown.style.display === 'block') {
            if (!filterDropdown.contains(event.target) && !filterButton.contains(event.target)) {
                filterDropdown.style.display = 'none';
            }
        }
    });
}

// ============================================================
// CLIENT SEARCH
// ============================================================

/**
 * Strip phone formatting for smart matching
 * @param {string} text - Phone number with formatting
 * @returns {string} Digits only
 */
function stripPhoneFormat(text) {
    return text.replace(/[\s\-\(\)\.\+]/g, '');
}

/**
 * Perform client-side search filtering on visible cards
 */
function performSearch() {
    const searchInput = document.querySelector('.search-box input[name="search"]');
    const clearSearchBtn = document.querySelector('.clear-search');
    const clientCards = document.querySelectorAll('.client-card');
    
    if (!searchInput) return;
    
    const searchTerm = searchInput.value.toLowerCase().trim();
    
    // Show/hide clear button
    if (clearSearchBtn) {
        clearSearchBtn.style.display = searchTerm ? 'block' : 'none';
    }
    
    if (!searchTerm) {
        clientCards.forEach(card => card.style.display = '');
        return;
    }
    
    const searchTermStripped = stripPhoneFormat(searchTerm);
    const isPhoneSearch = /^\d+$/.test(searchTermStripped);
    
    clientCards.forEach(card => {
        const fileNumber = card.querySelector('.file-number')?.textContent || '';
        const clientName = card.querySelector('.client-name')?.textContent || '';
        const email = card.querySelector('.contact-link[href^="mailto:"] span')?.textContent || '';
        const phoneElement = card.querySelector('.contact-link[href^="tel:"] span, .contact-link[href^="sms:"] span');
        const phone = phoneElement?.textContent || '';
        
        const searchableText = `${fileNumber} ${clientName} ${email}`.toLowerCase();
        
        let phoneMatch = false;
        if (isPhoneSearch && phone) {
            phoneMatch = stripPhoneFormat(phone).includes(searchTermStripped);
        } else {
            phoneMatch = phone.toLowerCase().includes(searchTerm);
        }
        
        const matches = searchableText.includes(searchTerm) || phoneMatch;
        card.style.display = matches ? '' : 'none';
    });
}

/**
 * Initialize search input event handlers
 */
function initSearch() {
    const searchInput = document.querySelector('.search-box input[name="search"]');
    const clearSearchBtn = document.querySelector('.clear-search');
    const searchForm = document.querySelector('.search-box');
    
    if (searchInput) {
        searchInput.addEventListener('input', performSearch);
        if (searchInput.value) performSearch();
    }
    
    if (clearSearchBtn) {
        clearSearchBtn.addEventListener('click', function() {
            searchInput.value = '';
            performSearch();
            searchInput.focus();
        });
    }
    
    if (searchForm) {
        searchForm.addEventListener('submit', function(e) {
            if (!searchInput.value.trim()) e.preventDefault();
        });
    }
}

// ============================================================
// IPAD VIEW MANAGEMENT
// ============================================================

let detailedClickListenerAdded = false;

/**
 * Manage view toggle availability based on device and orientation
 * Disables Detailed view on iPad portrait (too narrow)
 */
function manageViewToggleForDevice() {
    const isTouchDevice = ('ontouchstart' in window) || (navigator.maxTouchPoints > 0);
    if (!isTouchDevice) return;
    
    const isPortrait = window.innerHeight > window.innerWidth;
    const isIPadWidth = window.innerWidth >= 700 && window.innerWidth <= 1366;
    
    const viewToggleBtns = document.querySelectorAll('.view-toggle-btn');
    let detailedBtn = null;
    viewToggleBtns.forEach(btn => {
        if (btn.textContent.trim() === 'Detailed') detailedBtn = btn;
    });
    
    if (!detailedBtn) return;
    
    if (isPortrait && isIPadWidth) {
        detailedBtn.style.opacity = '0.5';
        detailedBtn.style.cursor = 'not-allowed';
        detailedBtn.style.pointerEvents = 'none';
        
        if (!detailedClickListenerAdded) {
            detailedBtn.addEventListener('click', e => {
                e.preventDefault();
                e.stopPropagation();
                return false;
            });
            detailedClickListenerAdded = true;
        }
        
        const urlParams = new URLSearchParams(window.location.search);
        if (urlParams.get('view') === 'detailed') {
            urlParams.set('view', 'compact');
            window.location.href = `${window.location.pathname}?${urlParams.toString()}`;
        }
    } else {
        detailedBtn.style.opacity = '1';
        detailedBtn.style.cursor = 'pointer';
        detailedBtn.style.pointerEvents = 'auto';
    }
}

// ============================================================
// RETENTION SYSTEM
// ============================================================

let pendingDeleteIds = [];

/**
 * Check for clients due for retention deletion
 */
function checkRetention() {
    fetch('/api/retention-check')
        .then(response => response.json())
        .then(data => {
            if (data.clients_due && data.clients_due.length > 0) {
                showRetentionModal(data.clients_due);
            }
        })
        .catch(error => console.error('Error checking retention:', error));
}

/**
 * Display the retention review modal
 * @param {Array} clients - List of clients due for deletion
 */
function showRetentionModal(clients) {
    const modal = document.getElementById('retention-modal');
    const listContainer = document.getElementById('retention-list');
    
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
    
    if (typeof lucide !== 'undefined') lucide.createIcons();
}

/**
 * Close the retention modal
 */
function closeRetentionModal() {
    document.getElementById('retention-modal').style.display = 'none';
}

/**
 * Update delete button state based on selected checkboxes
 */
function updateDeleteButton() {
    const checkboxes = document.querySelectorAll('#retention-list input[type="checkbox"]:checked');
    const btn = document.getElementById('delete-selected-btn');
    const count = checkboxes.length;
    
    btn.disabled = count === 0;
    btn.style.background = count === 0 ? '#9CA3AF' : '#DC2626';
    btn.style.cursor = count === 0 ? 'not-allowed' : 'pointer';
    btn.textContent = `Delete Selected (${count})`;
}

/**
 * Initiate deletion of selected clients (shows confirmation modal)
 */
function deleteSelectedClients() {
    const checkboxes = document.querySelectorAll('#retention-list input[type="checkbox"]:checked');
    pendingDeleteIds = Array.from(checkboxes).map(cb => parseInt(cb.value));
    
    if (pendingDeleteIds.length === 0) return;
    
    document.getElementById('delete-count').textContent = pendingDeleteIds.length;
    document.getElementById('delete-confirm-modal').style.display = 'flex';
}

/**
 * Cancel the deletion confirmation
 */
function cancelDeletion() {
    document.getElementById('delete-confirm-modal').style.display = 'none';
    pendingDeleteIds = [];
}

/**
 * Confirm and execute the deletion
 */
function confirmDeletion() {
    document.getElementById('delete-confirm-modal').style.display = 'none';
    
    const btn = document.getElementById('delete-selected-btn');
    btn.disabled = true;
    btn.style.background = '#9CA3AF';
    btn.style.cursor = 'not-allowed';
    btn.textContent = 'Deleting...';
    
    fetch('/api/retention-delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
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

// ============================================================
// UTILITIES
// ============================================================

/**
 * Escape HTML to prevent XSS
 * @param {string} text - Raw text
 * @returns {string} HTML-escaped text
 */
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ============================================================
// INITIALIZATION
// ============================================================

document.addEventListener('DOMContentLoaded', function() {
    applyClientCardColors();
    initDropdownCloseHandler();
    syncClock();
    loadCardOrder();
    initCardDragDrop();
    initFilterDropdown();
    initSearch();
    manageViewToggleForDevice();
    checkRetention();
});

window.addEventListener('orientationchange', () => setTimeout(manageViewToggleForDevice, 100));
window.addEventListener('resize', manageViewToggleForDevice);
