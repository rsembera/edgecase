/**
 * Schedule Form JavaScript - EdgeCase Equalizer
 * Handles natural language date/time parsing for appointment scheduling.
 */

let scheduleDatePicker = null;
let scheduleTimePicker = null;

document.addEventListener('DOMContentLoaded', function() {
    lucide.createIcons();
    
    // Initialize pickers
    initSchedulePickers();
    
    const quickEntry = document.getElementById('quick_entry');
    const preview = document.getElementById('parse-preview');
    
    let debounceTimer;
    
    quickEntry.addEventListener('input', function() {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(parseInput, 200);
    });
    
    /**
     * Parse quick entry input and update form fields
     */
    function parseInput() {
        const text = quickEntry.value.trim().toLowerCase();
        
        if (!text) {
            preview.innerHTML = '';
            preview.className = 'parse-preview';
            return;
        }
        
        const result = parseDateTime(text);
        
        if (result.date) {
            const date = result.date;
            
            const options = { 
                weekday: 'long', 
                year: 'numeric', 
                month: 'long', 
                day: 'numeric'
            };
            let displayStr = '→ ' + date.toLocaleDateString('en-US', options);
            
            if (result.time) {
                displayStr += ' at ' + result.time;
            }
            
            preview.innerHTML = displayStr;
            preview.className = 'parse-preview parse-success';
            
            // Update date picker
            if (scheduleDatePicker) {
                scheduleDatePicker.setDate(date, true);
            }
            
            // Update time picker (setTime triggers onSelect which updates hidden input)
            if (result.time && scheduleTimePicker) {
                scheduleTimePicker.setTime(result.time);
            }
        } else {
            preview.innerHTML = 'Type a date like "Friday at 2pm" or "Nov 28 3:30"';
            preview.className = 'parse-preview parse-hint';
        }
    }
    
    /**
     * Parse date and time from natural language text
     * @param {string} text - Input text to parse
     * @returns {{date: Date|null, time: string|null}} Parsed date and time
     */
    function parseDateTime(text) {
        let date = null;
        let time = null;
        
        time = parseTime(text);
        date = parseDate(text);
        
        return { date, time };
    }
    
    /**
     * Parse time from text
     * @param {string} text - Input text
     * @returns {string|null} Formatted time string or null
     */
    function parseTime(text) {
        if (/\bnoon\b/.test(text)) return '12:00 PM';
        if (/\bmidnight\b/.test(text)) return '12:00 AM';
        
        // 12-hour time: 2pm, 2:30pm, 2:30 pm, 2 p.m., 2:30 P.M.
        const time12 = text.match(/\b(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)\b/i);
        if (time12) {
            let hours = parseInt(time12[1]);
            const minutes = time12[2] || '00';
            // Normalize: "p.m." -> "PM"
            const ampm = time12[3].replace(/\./g, '').toUpperCase();
            
            if (hours > 12) return null;
            
            return `${hours}:${minutes} ${ampm}`;
        }
        
        // 24-hour time: 14:00, 14:30
        const time24 = text.match(/\b([01]?\d|2[0-3]):([0-5]\d)\b/);
        if (time24) {
            let hours = parseInt(time24[1]);
            const minutes = time24[2];
            const ampm = hours >= 12 ? 'PM' : 'AM';
            if (hours > 12) hours -= 12;
            if (hours === 0) hours = 12;
            return `${hours}:${minutes} ${ampm}`;
        }
        
        return null;
    }
    
    /**
     * Parse date from text
     * @param {string} text - Input text
     * @returns {Date|null} Parsed date or null
     */
    function parseDate(text) {
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        
        if (/\btoday\b/.test(text)) {
            return today;
        }
        
        if (/\btomorrow\b/.test(text)) {
            const tomorrow = new Date(today);
            tomorrow.setDate(tomorrow.getDate() + 1);
            return tomorrow;
        }
        
        // Day names
        const days = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'];
        const dayAbbrevs = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat'];
        
        for (let i = 0; i < days.length; i++) {
            const pattern = new RegExp('\\b' + days[i] + '\\b|\\b' + dayAbbrevs[i] + '\\b', 'i');
            if (pattern.test(text)) {
                return getNextDayOfWeek(today, i);
            }
        }
        
        // Month names mapping
        const months = {
            'jan': 0, 'january': 0,
            'feb': 1, 'february': 1,
            'mar': 2, 'march': 2,
            'apr': 3, 'april': 3,
            'may': 4,
            'jun': 5, 'june': 5,
            'jul': 6, 'july': 6,
            'aug': 7, 'august': 7,
            'sep': 8, 'sept': 8, 'september': 8,
            'oct': 9, 'october': 9,
            'nov': 10, 'november': 10,
            'dec': 11, 'december': 11
        };
        
        // Pattern: Month Day (Nov 28)
        const monthDayPattern = /\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+(\d{1,2})\b/i;
        const monthDayMatch = text.match(monthDayPattern);
        
        if (monthDayMatch) {
            const monthStr = monthDayMatch[1].toLowerCase();
            const day = parseInt(monthDayMatch[2]);
            
            let monthNum = null;
            for (const [key, val] of Object.entries(months)) {
                if (monthStr.startsWith(key) || key.startsWith(monthStr)) {
                    monthNum = val;
                    break;
                }
            }
            
            if (monthNum !== null && day >= 1 && day <= 31) {
                const result = new Date(today.getFullYear(), monthNum, day);
                if (result < today) {
                    result.setFullYear(result.getFullYear() + 1);
                }
                return result;
            }
        }
        
        // Pattern: Day Month (28 Nov)
        const dayMonthPattern = /\b(\d{1,2})\s+(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b/i;
        const dayMonthMatch = text.match(dayMonthPattern);
        
        if (dayMonthMatch) {
            const day = parseInt(dayMonthMatch[1]);
            const monthStr = dayMonthMatch[2].toLowerCase();
            
            let monthNum = null;
            for (const [key, val] of Object.entries(months)) {
                if (monthStr.startsWith(key) || key.startsWith(monthStr)) {
                    monthNum = val;
                    break;
                }
            }
            
            if (monthNum !== null && day >= 1 && day <= 31) {
                const result = new Date(today.getFullYear(), monthNum, day);
                if (result < today) {
                    result.setFullYear(result.getFullYear() + 1);
                }
                return result;
            }
        }
        
        return null;
    }
    
    /**
     * Get the next occurrence of a day of week
     * @param {Date} fromDate - Starting date
     * @param {number} dayOfWeek - Target day (0=Sunday, 6=Saturday)
     * @returns {Date} Next occurrence of that day
     */
    function getNextDayOfWeek(fromDate, dayOfWeek) {
        const result = new Date(fromDate);
        const currentDay = result.getDay();
        let daysToAdd = dayOfWeek - currentDay;
        
        if (daysToAdd <= 0) {
            daysToAdd += 7;
        }
        
        result.setDate(result.getDate() + daysToAdd);
        return result;
    }
});

/**
 * Initialize the date and time pickers for scheduling
 */
function initSchedulePickers() {
    const dataEl = document.getElementById('schedule-data');
    if (!dataEl) return;
    
    const data = JSON.parse(dataEl.textContent);
    const dateInput = document.getElementById('schedule_date');
    const timeInput = document.getElementById('appointment_time');
    
    const initialDate = new Date(
        data.todayYear,
        data.todayMonth - 1,
        data.todayDay
    );
    
    // Initialize date picker
    const dateContainer = document.getElementById('schedule-date-picker');
    if (dateContainer) {
        scheduleDatePicker = new DatePicker(dateContainer, {
            initialDate: initialDate,
            onSelect: (date) => {
                const y = date.getFullYear();
                const m = (date.getMonth() + 1).toString().padStart(2, '0');
                const d = date.getDate().toString().padStart(2, '0');
                dateInput.value = `${y}-${m}-${d}`;
            }
        });
    }
    
    // Initialize time picker
    const timeContainer = document.getElementById('schedule-time-picker');
    if (timeContainer) {
        scheduleTimePicker = new TimePicker(timeContainer, {
            format: data.timeFormat || '12h',
            initialTime: '10:00 AM',
            onSelect: (time) => {
                timeInput.value = time;
            }
        });
    }
}
