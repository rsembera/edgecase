/**
 * Date and Time Picker Components - EdgeCase Equalizer
 * Grid-based pickers optimized for touch (iPad) and mouse
 * 
 * Usage:
 *   initDatePicker('fieldId', { onSelect: (date) => {} })
 *   initTimePicker('fieldId', { format: '12h', onSelect: (time) => {} })
 */

// ============================================================
// CONFIGURATION
// ============================================================

const PICKER_CONFIG = {
    months: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'],
    monthsFull: ['January', 'February', 'March', 'April', 'May', 'June', 
                 'July', 'August', 'September', 'October', 'November', 'December'],
    daysOfWeek: ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'],
    yearRangeStart: 2020,
    yearRangeEnd: 2030
};

// ============================================================
// DATE PICKER CLASS
// ============================================================

class DatePicker {
    /**
     * Create a date picker
     * @param {HTMLElement} container - Container element
     * @param {Object} options - Configuration options
     */
    constructor(container, options = {}) {
        this.container = container;
        this.options = {
            onSelect: options.onSelect || (() => {}),
            initialDate: options.initialDate || new Date()
        };
        
        this.selectedDate = this.options.initialDate;
        this.viewYear = this.selectedDate.getFullYear();
        this.viewMonth = this.selectedDate.getMonth();
        this.currentView = 'days'; // 'years', 'months', 'days'
        this.yearsPageStart = Math.floor(this.viewYear / 16) * 16;
        
        this.render();
        this.attachEvents();
    }

    /**
     * Render the picker HTML
     */
    render() {
        this.container.innerHTML = `
            <div class="picker-wrapper">
                <div class="picker-display" tabindex="0">
                    <span class="picker-display-value"></span>
                    <svg class="picker-display-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
                        <line x1="16" y1="2" x2="16" y2="6"></line>
                        <line x1="8" y1="2" x2="8" y2="6"></line>
                        <line x1="3" y1="10" x2="21" y2="10"></line>
                    </svg>
                </div>
                <div class="picker-dropdown"></div>
            </div>
        `;
        
        this.display = this.container.querySelector('.picker-display');
        this.displayValue = this.container.querySelector('.picker-display-value');
        this.dropdown = this.container.querySelector('.picker-dropdown');
        
        this.updateDisplay();
        this.renderView();
    }
    
    /**
     * Update the display text
     */
    updateDisplay() {
        if (this.selectedDate) {
            const month = PICKER_CONFIG.monthsFull[this.selectedDate.getMonth()];
            const day = this.selectedDate.getDate();
            const year = this.selectedDate.getFullYear();
            this.displayValue.textContent = `${month} ${day}, ${year}`;
            this.displayValue.classList.remove('picker-display-placeholder');
        } else {
            this.displayValue.textContent = 'Select date';
            this.displayValue.classList.add('picker-display-placeholder');
        }
    }
    
    /**
     * Programmatically set the selected date
     * @param {Date} date - New date to select
     * @param {boolean} triggerCallback - Whether to trigger onSelect callback (default: true)
     */
    setDate(date, triggerCallback = true) {
        this.selectedDate = date;
        this.viewYear = date.getFullYear();
        this.viewMonth = date.getMonth();
        this.updateDisplay();
        this.renderView();
        
        if (triggerCallback) {
            this.options.onSelect(date);
        }
    }
    
    /**
     * Render the current view (years, months, or days)
     */
    renderView() {
        switch (this.currentView) {
            case 'years':
                this.renderYearsView();
                break;
            case 'months':
                this.renderMonthsView();
                break;
            case 'days':
            default:
                this.renderDaysView();
                break;
        }
    }
    
    /**
     * Render year selection grid (4x4 = 16 years)
     */
    renderYearsView() {
        let html = `
            <div class="picker-header">
                <button type="button" class="picker-nav-btn" data-action="prev-years">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="15 18 9 12 15 6"></polyline>
                    </svg>
                </button>
                <span class="picker-title">${this.yearsPageStart} - ${this.yearsPageStart + 15}</span>
                <button type="button" class="picker-nav-btn" data-action="next-years">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="9 18 15 12 9 6"></polyline>
                    </svg>
                </button>
            </div>
            <div class="picker-grid picker-grid-years">
        `;
        
        const currentYear = new Date().getFullYear();
        for (let i = 0; i < 16; i++) {
            const year = this.yearsPageStart + i;
            const isSelected = this.selectedDate && this.selectedDate.getFullYear() === year;
            const isCurrentYear = year === currentYear;
            
            let classes = 'picker-cell';
            if (isSelected) classes += ' selected';
            if (isCurrentYear) classes += ' today';
            
            html += `<div class="${classes}" data-year="${year}">${year}</div>`;
        }
        
        html += '</div>';
        this.dropdown.innerHTML = html;
    }

    /**
     * Render month selection grid (4x3 = 12 months)
     */
    renderMonthsView() {
        let html = `
            <div class="picker-header">
                <button type="button" class="picker-back-btn" data-action="back-to-years">← Years</button>
                <span class="picker-title">${this.viewYear}</span>
                <div></div>
            </div>
            <div class="picker-grid picker-grid-months">
        `;
        
        const currentDate = new Date();
        const isCurrentYear = this.viewYear === currentDate.getFullYear();
        
        for (let i = 0; i < 12; i++) {
            const isSelected = this.selectedDate && 
                               this.selectedDate.getFullYear() === this.viewYear && 
                               this.selectedDate.getMonth() === i;
            const isCurrentMonth = isCurrentYear && i === currentDate.getMonth();
            
            let classes = 'picker-cell';
            if (isSelected) classes += ' selected';
            if (isCurrentMonth) classes += ' today';
            
            html += `<div class="${classes}" data-month="${i}">${PICKER_CONFIG.months[i]}</div>`;
        }
        
        html += '</div>';
        this.dropdown.innerHTML = html;
    }
    
    /**
     * Render day selection grid (7x6 = 42 cells)
     */
    renderDaysView() {
        const firstDay = new Date(this.viewYear, this.viewMonth, 1);
        const lastDay = new Date(this.viewYear, this.viewMonth + 1, 0);
        const startDayOfWeek = firstDay.getDay();
        const daysInMonth = lastDay.getDate();
        
        // Previous month days to show
        const prevMonthLastDay = new Date(this.viewYear, this.viewMonth, 0).getDate();
        
        let html = `
            <div class="picker-header">
                <button type="button" class="picker-back-btn" data-action="back-to-months">← ${this.viewYear}</button>
                <span class="picker-title">${PICKER_CONFIG.monthsFull[this.viewMonth]}</span>
                <div style="display: flex; gap: 0.25rem;">
                    <button type="button" class="picker-nav-btn" data-action="prev-month">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="15 18 9 12 15 6"></polyline>
                        </svg>
                    </button>
                    <button type="button" class="picker-nav-btn" data-action="next-month">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="9 18 15 12 9 6"></polyline>
                        </svg>
                    </button>
                </div>
            </div>
        `;
        
        // Day of week headers
        html += '<div class="picker-grid picker-grid-days">';
        for (const dow of PICKER_CONFIG.daysOfWeek) {
            html += `<div class="picker-dow">${dow}</div>`;
        }
        
        const today = new Date();
        const todayStr = `${today.getFullYear()}-${today.getMonth()}-${today.getDate()}`;
        const selectedStr = this.selectedDate ? 
            `${this.selectedDate.getFullYear()}-${this.selectedDate.getMonth()}-${this.selectedDate.getDate()}` : '';
        
        // Previous month's trailing days
        for (let i = startDayOfWeek - 1; i >= 0; i--) {
            const day = prevMonthLastDay - i;
            html += `<div class="picker-cell other-month" data-day="${day}" data-month-offset="-1">${day}</div>`;
        }
        
        // Current month days
        for (let day = 1; day <= daysInMonth; day++) {
            const dateStr = `${this.viewYear}-${this.viewMonth}-${day}`;
            let classes = 'picker-cell';
            if (dateStr === selectedStr) classes += ' selected';
            if (dateStr === todayStr) classes += ' today';
            
            html += `<div class="${classes}" data-day="${day}">${day}</div>`;
        }
        
        // Next month's leading days
        const totalCells = startDayOfWeek + daysInMonth;
        const remainingCells = totalCells <= 35 ? 35 - totalCells : 42 - totalCells;
        for (let day = 1; day <= remainingCells; day++) {
            html += `<div class="picker-cell other-month" data-day="${day}" data-month-offset="1">${day}</div>`;
        }
        
        html += '</div>';
        this.dropdown.innerHTML = html;
    }

    /**
     * Attach event listeners
     */
    attachEvents() {
        // Toggle dropdown on display click
        this.display.addEventListener('click', (e) => {
            e.stopPropagation();
            this.toggle();
        });
        
        this.display.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                this.toggle();
            }
        });
        
        // Handle clicks inside dropdown
        this.dropdown.addEventListener('click', (e) => {
            e.stopPropagation();
            const target = e.target.closest('[data-action], [data-year], [data-month], [data-day]');
            if (!target) return;
            
            // Navigation actions
            const action = target.dataset.action;
            if (action) {
                this.handleAction(action);
                return;
            }
            
            // Year selection
            if (target.dataset.year) {
                this.viewYear = parseInt(target.dataset.year);
                this.currentView = 'months';
                this.renderView();
                return;
            }
            
            // Month selection
            if (target.dataset.month !== undefined) {
                this.viewMonth = parseInt(target.dataset.month);
                this.currentView = 'days';
                this.renderView();
                return;
            }
            
            // Day selection
            if (target.dataset.day) {
                let year = this.viewYear;
                let month = this.viewMonth;
                
                // Handle other-month clicks
                const monthOffset = parseInt(target.dataset.monthOffset || 0);
                if (monthOffset !== 0) {
                    month += monthOffset;
                    if (month < 0) { month = 11; year--; }
                    if (month > 11) { month = 0; year++; }
                }
                
                const day = parseInt(target.dataset.day);
                this.selectedDate = new Date(year, month, day);
                this.viewYear = year;
                this.viewMonth = month;
                
                this.updateDisplay();
                this.close();
                this.options.onSelect(this.selectedDate);
            }
        });
        
        // Close on outside click
        document.addEventListener('click', () => this.close());
    }
    
    /**
     * Handle navigation actions
     */
    handleAction(action) {
        switch (action) {
            case 'prev-years':
                this.yearsPageStart -= 16;
                this.renderView();
                break;
            case 'next-years':
                this.yearsPageStart += 16;
                this.renderView();
                break;
            case 'back-to-years':
                this.yearsPageStart = Math.floor(this.viewYear / 16) * 16;
                this.currentView = 'years';
                this.renderView();
                break;
            case 'back-to-months':
                this.currentView = 'months';
                this.renderView();
                break;
            case 'prev-month':
                this.viewMonth--;
                if (this.viewMonth < 0) {
                    this.viewMonth = 11;
                    this.viewYear--;
                }
                this.renderView();
                break;
            case 'next-month':
                this.viewMonth++;
                if (this.viewMonth > 11) {
                    this.viewMonth = 0;
                    this.viewYear++;
                }
                this.renderView();
                break;
        }
    }
    
    toggle() {
        if (this.dropdown.classList.contains('show')) {
            this.close();
        } else {
            this.open();
        }
    }
    
    open() {
        // Close any other open pickers
        document.querySelectorAll('.picker-dropdown.show').forEach(d => d.classList.remove('show'));
        this.dropdown.classList.add('show');
        this.renderView();
    }
    
    close() {
        this.dropdown.classList.remove('show');
    }
    
    /**
     * Get the selected date
     * @returns {Date|null}
     */
    getDate() {
        return this.selectedDate;
    }
}


// ============================================================
// TIME PICKER CLASS
// ============================================================

class TimePicker {
    /**
     * Create a time picker
     * @param {HTMLElement} container - Container element
     * @param {Object} options - Configuration options
     */
    constructor(container, options = {}) {
        this.container = container;
        this.options = {
            format: options.format || '12h', // '12h' or '24h'
            onSelect: options.onSelect || (() => {}),
            initialTime: options.initialTime || null
        };
        
        // Parse initial time or use current
        if (this.options.initialTime) {
            this.parseTimeString(this.options.initialTime);
        } else {
            const now = new Date();
            this.hour = now.getHours();
            this.minute = now.getMinutes(); // Use actual minute for auto-populate
        }
        
        this.currentView = 'hours'; // 'hours', 'minutes', 'ampm' (for 12h only)
        
        this.render();
        this.attachEvents();
    }
    
    /**
     * Parse a time string into hour/minute
     * @param {string} timeStr - e.g., "2:30 PM" or "14:30"
     */
    parseTimeString(timeStr) {
        if (!timeStr) {
            const now = new Date();
            this.hour = now.getHours();
            this.minute = now.getMinutes(); // Use actual minute
            return;
        }
        
        // Try 12h format: "2:30 PM"
        const match12 = timeStr.match(/^(\d{1,2}):(\d{2})\s*(AM|PM)$/i);
        if (match12) {
            let h = parseInt(match12[1]);
            const m = parseInt(match12[2]);
            const ampm = match12[3].toUpperCase();
            
            if (ampm === 'PM' && h !== 12) h += 12;
            if (ampm === 'AM' && h === 12) h = 0;
            
            this.hour = h;
            this.minute = Math.floor(m / 5) * 5;
            return;
        }
        
        // Try 24h format: "14:30"
        const match24 = timeStr.match(/^(\d{1,2}):(\d{2})$/);
        if (match24) {
            this.hour = parseInt(match24[1]);
            this.minute = Math.floor(parseInt(match24[2]) / 5) * 5;
            return;
        }
        
        // Fallback to current time
        const now = new Date();
        this.hour = now.getHours();
        this.minute = Math.floor(now.getMinutes() / 5) * 5;
    }
    
    /**
     * Format the current time for display
     * @returns {string}
     */
    formatTime() {
        if (this.options.format === '24h') {
            return `${this.hour.toString().padStart(2, '0')}:${this.minute.toString().padStart(2, '0')}`;
        } else {
            let h = this.hour % 12;
            if (h === 0) h = 12;
            const ampm = this.hour >= 12 ? 'PM' : 'AM';
            return `${h}:${this.minute.toString().padStart(2, '0')} ${ampm}`;
        }
    }

    /**
     * Render the picker HTML
     */
    render() {
        this.container.innerHTML = `
            <div class="picker-wrapper">
                <div class="picker-display" tabindex="0">
                    <span class="picker-display-value"></span>
                    <svg class="picker-display-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="12" cy="12" r="10"></circle>
                        <polyline points="12 6 12 12 16 14"></polyline>
                    </svg>
                </div>
                <div class="picker-dropdown"></div>
            </div>
        `;
        
        this.display = this.container.querySelector('.picker-display');
        this.displayValue = this.container.querySelector('.picker-display-value');
        this.dropdown = this.container.querySelector('.picker-dropdown');
        
        this.updateDisplay();
        this.renderView();
    }
    
    /**
     * Update the display text
     */
    updateDisplay() {
        this.displayValue.textContent = this.formatTime();
        this.displayValue.classList.remove('picker-display-placeholder');
    }
    
    /**
     * Render the current view
     */
    renderView() {
        switch (this.currentView) {
            case 'hours':
                this.renderHoursView();
                break;
            case 'minutes':
                this.renderMinutesView();
                break;
            case 'ampm':
                this.renderAmPmView();
                break;
        }
    }
    
    /**
     * Render hour selection grid
     */
    renderHoursView() {
        let html = `
            <div class="picker-header">
                <span class="picker-title">Select Hour</span>
                <div></div>
            </div>
            <div class="time-picker-section">
                <div class="picker-grid ${this.options.format === '24h' ? 'picker-grid-hours-24' : 'picker-grid-hours-12'}">
        `;
        
        if (this.options.format === '24h') {
            // 24h: show 0-23 in 4x6 grid
            for (let h = 0; h < 24; h++) {
                const isSelected = this.hour === h;
                const classes = isSelected ? 'picker-cell selected' : 'picker-cell';
                html += `<div class="${classes}" data-hour="${h}">${h.toString().padStart(2, '0')}</div>`;
            }
        } else {
            // 12h: show 12, 1-11 in 4x3 grid
            const hours12 = [12, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11];
            const currentDisplay = this.hour % 12 || 12;
            
            for (const h of hours12) {
                const isSelected = currentDisplay === h;
                const classes = isSelected ? 'picker-cell selected' : 'picker-cell';
                html += `<div class="${classes}" data-hour="${h}">${h}</div>`;
            }
        }
        
        html += '</div></div>';
        this.dropdown.innerHTML = html;
    }
    
    /**
     * Render minute selection grid (5-minute increments, 4x3)
     */
    renderMinutesView() {
        let html = `
            <div class="picker-header">
                <button type="button" class="picker-back-btn" data-action="back-to-hours">← Hour</button>
                <span class="picker-title">Select Minutes</span>
                <div></div>
            </div>
            <div class="time-picker-section">
                <div class="picker-grid picker-grid-minutes">
        `;
        
        for (let m = 0; m < 60; m += 5) {
            const isSelected = this.minute === m;
            const classes = isSelected ? 'picker-cell selected' : 'picker-cell';
            html += `<div class="${classes}" data-minute="${m}">:${m.toString().padStart(2, '0')}</div>`;
        }
        
        html += '</div></div>';
        this.dropdown.innerHTML = html;
    }
    
    /**
     * Render AM/PM selection (12h format only)
     */
    renderAmPmView() {
        const isAM = this.hour < 12;
        
        let html = `
            <div class="picker-header">
                <button type="button" class="picker-back-btn" data-action="back-to-minutes">← Minutes</button>
                <span class="picker-title">AM or PM?</span>
                <div></div>
            </div>
            <div class="time-picker-section">
                <div class="picker-grid picker-grid-ampm">
                    <div class="picker-cell ampm ${isAM ? 'selected' : ''}" data-ampm="AM">AM</div>
                    <div class="picker-cell ampm ${!isAM ? 'selected' : ''}" data-ampm="PM">PM</div>
                </div>
            </div>
        `;
        
        this.dropdown.innerHTML = html;
    }

    /**
     * Attach event listeners
     */
    attachEvents() {
        this.display.addEventListener('click', (e) => {
            e.stopPropagation();
            this.toggle();
        });
        
        this.display.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                this.toggle();
            }
        });
        
        this.dropdown.addEventListener('click', (e) => {
            e.stopPropagation();
            const target = e.target.closest('[data-action], [data-hour], [data-minute], [data-ampm]');
            if (!target) return;
            
            const action = target.dataset.action;
            if (action) {
                this.handleAction(action);
                return;
            }
            
            // Hour selection
            if (target.dataset.hour !== undefined) {
                const selectedHour = parseInt(target.dataset.hour);
                
                if (this.options.format === '24h') {
                    this.hour = selectedHour;
                    this.currentView = 'minutes';
                    this.renderView();
                } else {
                    // 12h format: preserve AM/PM, go to minutes
                    const wasAfternoon = this.hour >= 12;
                    if (selectedHour === 12) {
                        this.hour = wasAfternoon ? 12 : 0;
                    } else {
                        this.hour = wasAfternoon ? selectedHour + 12 : selectedHour;
                    }
                    this.currentView = 'minutes';
                    this.renderView();
                }
                return;
            }
            
            // Minute selection
            if (target.dataset.minute !== undefined) {
                this.minute = parseInt(target.dataset.minute);
                
                if (this.options.format === '12h') {
                    this.currentView = 'ampm';
                    this.renderView();
                } else {
                    // 24h format: done
                    this.updateDisplay();
                    this.close();
                    this.options.onSelect(this.formatTime());
                }
                return;
            }
            
            // AM/PM selection
            if (target.dataset.ampm) {
                const ampm = target.dataset.ampm;
                const currentHour12 = this.hour % 12 || 12;
                
                if (ampm === 'AM') {
                    this.hour = currentHour12 === 12 ? 0 : currentHour12;
                } else {
                    this.hour = currentHour12 === 12 ? 12 : currentHour12 + 12;
                }
                
                this.updateDisplay();
                this.close();
                this.options.onSelect(this.formatTime());
            }
        });
        
        document.addEventListener('click', () => this.close());
    }
    
    handleAction(action) {
        switch (action) {
            case 'back-to-hours':
                this.currentView = 'hours';
                this.renderView();
                break;
            case 'back-to-minutes':
                this.currentView = 'minutes';
                this.renderView();
                break;
        }
    }
    
    toggle() {
        if (this.dropdown.classList.contains('show')) {
            this.close();
        } else {
            this.open();
        }
    }
    
    open() {
        document.querySelectorAll('.picker-dropdown.show').forEach(d => d.classList.remove('show'));
        this.currentView = 'hours';
        this.dropdown.classList.add('show');
        this.renderView();
    }
    
    close() {
        this.dropdown.classList.remove('show');
    }
    
    /**
     * Get the formatted time string
     * @returns {string}
     */
    getTime() {
        return this.formatTime();
    }
    
    /**
     * Set the time programmatically
     * @param {string} timeStr - Time string like "10:00 AM" or "14:30"
     * @param {boolean} triggerCallback - Whether to trigger onSelect callback (default: true)
     */
    setTime(timeStr, triggerCallback = true) {
        this.parseTimeString(timeStr);
        this.updateDisplay();
        
        if (triggerCallback) {
            this.options.onSelect(this.formatTime());
        }
    }
    
    /**
     * Update the format (e.g., when settings change)
     * @param {string} format - '12h' or '24h'
     */
    setFormat(format) {
        this.options.format = format;
        this.updateDisplay();
    }
}


// ============================================================
// INITIALIZATION HELPERS
// ============================================================

// Store picker instances for later access
const pickerInstances = {};

/**
 * Initialize a date picker on an element
 * @param {string} containerId - ID of container element
 * @param {Object} options - Picker options
 * @returns {DatePicker}
 */
function initDatePicker(containerId, options = {}) {
    const container = document.getElementById(containerId);
    if (!container) {
        console.error(`Date picker container not found: ${containerId}`);
        return null;
    }
    
    const picker = new DatePicker(container, options);
    pickerInstances[containerId] = picker;
    return picker;
}

/**
 * Initialize a time picker on an element
 * @param {string} containerId - ID of container element
 * @param {Object} options - Picker options
 * @returns {TimePicker}
 */
function initTimePicker(containerId, options = {}) {
    const container = document.getElementById(containerId);
    if (!container) {
        console.error(`Time picker container not found: ${containerId}`);
        return null;
    }
    
    const picker = new TimePicker(container, options);
    pickerInstances[containerId] = picker;
    return picker;
}

/**
 * Get a picker instance by container ID
 * @param {string} containerId
 * @returns {DatePicker|TimePicker|null}
 */
function getPicker(containerId) {
    return pickerInstances[containerId] || null;
}

/**
 * Fetch the time format setting from the server
 * @returns {Promise<string>} '12h' or '24h'
 */
async function getTimeFormatSetting() {
    try {
        const response = await fetch('/api/time_format');
        const data = await response.json();
        return data.time_format || '12h';
    } catch (e) {
        console.error('Failed to fetch time format:', e);
        return '12h';
    }
}

/**
 * Initialize date and time pickers for an entry form
 * This is the main function to call from entry form pages
 * 
 * @param {Object} config - Configuration object
 * @param {string} config.dateContainerId - ID of date picker container
 * @param {string} config.timeContainerId - ID of time picker container (optional)
 * @param {string} config.dateHiddenId - ID of hidden input for date value
 * @param {string} config.timeHiddenId - ID of hidden input for time value (optional)
 * @param {Date} config.initialDate - Initial date (defaults to today)
 * @param {string} config.initialTime - Initial time string (defaults to now)
 */
async function initEntryPickers(config) {
    const {
        dateContainerId,
        timeContainerId,
        dateHiddenId,
        timeHiddenId,
        initialDate,
        initialTime
    } = config;
    
    // Get time format setting
    const timeFormat = await getTimeFormatSetting();
    
    // Initialize date picker
    if (dateContainerId) {
        const datePicker = initDatePicker(dateContainerId, {
            initialDate: initialDate || new Date(),
            onSelect: (date) => {
                // Update hidden field with YYYY-MM-DD format for server
                if (dateHiddenId) {
                    const hidden = document.getElementById(dateHiddenId);
                    if (hidden) {
                        const y = date.getFullYear();
                        const m = (date.getMonth() + 1).toString().padStart(2, '0');
                        const d = date.getDate().toString().padStart(2, '0');
                        hidden.value = `${y}-${m}-${d}`;
                    }
                }
            }
        });
        
        // Set initial hidden value
        if (datePicker && dateHiddenId) {
            const date = datePicker.getDate();
            const hidden = document.getElementById(dateHiddenId);
            if (hidden && date) {
                const y = date.getFullYear();
                const m = (date.getMonth() + 1).toString().padStart(2, '0');
                const d = date.getDate().toString().padStart(2, '0');
                hidden.value = `${y}-${m}-${d}`;
            }
        }
    }
    
    // Initialize time picker
    if (timeContainerId) {
        const timePicker = initTimePicker(timeContainerId, {
            format: timeFormat,
            initialTime: initialTime || null,
            onSelect: (time) => {
                if (timeHiddenId) {
                    const hidden = document.getElementById(timeHiddenId);
                    if (hidden) {
                        hidden.value = time;
                    }
                }
            }
        });
        
        // Set initial hidden value
        if (timePicker && timeHiddenId) {
            const hidden = document.getElementById(timeHiddenId);
            if (hidden) {
                hidden.value = timePicker.getTime();
            }
        }
    }
}

/**
 * Parse a date string (YYYY-MM-DD) into a Date object
 * @param {string} dateStr
 * @returns {Date|null}
 */
function parseDateString(dateStr) {
    if (!dateStr) return null;
    const match = dateStr.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (match) {
        return new Date(parseInt(match[1]), parseInt(match[2]) - 1, parseInt(match[3]));
    }
    return null;
}
