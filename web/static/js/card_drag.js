/**
 * Shared drag-and-drop functionality for stat cards
 * Used by main_view.js and ledger.js
 */

let draggedCard = null;
let hasMoved = false;

/**
 * Load saved card order from localStorage and reorder cards
 * @param {string} storageKey - localStorage key for this view's card order
 * @param {string} containerId - ID of the container element
 */
function loadCardOrder(storageKey, containerId) {
    const savedOrder = localStorage.getItem(storageKey);
    if (!savedOrder) return;
    
    const orderArray = JSON.parse(savedOrder);
    const container = document.getElementById(containerId);
    if (!container) return;
    
    orderArray.forEach(cardId => {
        const card = container.querySelector(`[data-card-id="${cardId}"]`);
        if (card) container.appendChild(card);
    });
}

/**
 * Save current card order to localStorage
 * @param {string} storageKey - localStorage key for this view's card order
 * @param {string} containerId - ID of the container element
 */
function saveCardOrder(storageKey, containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;
    
    const cards = container.querySelectorAll('.stat-card[data-card-id]');
    const order = Array.from(cards).map(card => card.dataset.cardId);
    localStorage.setItem(storageKey, JSON.stringify(order));
}

/**
 * Initialize drag and drop functionality for stat cards
 * @param {string} storageKey - localStorage key for this view's card order
 * @param {string} containerId - ID of the container element
 */
function initCardDragDrop(storageKey, containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;
    
    const cards = container.querySelectorAll('.stat-card[draggable="true"]');
    
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
            saveCardOrder(storageKey, containerId);
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
                const swapContainer = draggedCard.parentNode;
                const placeholder = document.createElement('div');
                
                swapContainer.insertBefore(placeholder, draggedCard);
                swapContainer.insertBefore(draggedCard, this);
                swapContainer.insertBefore(this, placeholder);
                swapContainer.removeChild(placeholder);
            }
            
            this.classList.remove('drag-over');
            return false;
        });
    });
}
