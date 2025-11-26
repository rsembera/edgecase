document.addEventListener('DOMContentLoaded', function() {
    lucide.createIcons();
    
    const quickEntry = document.getElementById('quick_entry');
    const preview = document.getElementById('parse-preview');
    const yearSelect = document.getElementById('year');
    const monthSelect = document.getElementById('month');
    const daySelect = document.getElementById('day');
    const timeInput = document.getElementById('appointment_time');
    
    // Debounce timer
    let debounceTimer;
    
    quickEntry.addEventListener('input', function() {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(parseInput, 200);
    });
    
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
            
            // Format for display
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
            
            // Auto-fill the dropdowns
            yearSelect.value = date.getFullYear();
            monthSelect.value = date.getMonth() + 1;
            daySelect.value = date.getDate();
            
            // Auto-fill time if found
            if (result.time) {
                timeInput.value = result.time;
            }
        } else {
            preview.innerHTML = 'Type a date like "Friday at 2pm" or "Nov 28 3:30"';
            preview.className = 'parse-preview parse-hint';
        }
    }
    
    function parseDateTime(text) {
        let date = null;
        let time = null;
        
        // Parse time first (so we can remove it from text for date parsing)
        time = parseTime(text);
        
        // Parse date
        date = parseDate(text);
        
        return { date, time };
    }
    
    function parseTime(text) {
        // Match patterns like: 2pm, 2:30pm, 2:30 pm, 14:00, noon, midnight
        
        // Check for noon/midnight
        if (/\bnoon\b/.test(text)) return '12:00 PM';
        if (/\bmidnight\b/.test(text)) return '12:00 AM';
        
        // Match 12-hour time: 2pm, 2:30pm, 2:30 pm, 2 pm
        const time12 = text.match(/\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b/i);
        if (time12) {
            let hours = parseInt(time12[1]);
            const minutes = time12[2] || '00';
            const ampm = time12[3].toUpperCase();
            
            if (hours > 12) return null; // Invalid
            
            return `${hours}:${minutes} ${ampm}`;
        }
        
        // Match 24-hour time: 14:00, 14:30
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
    
    function parseDate(text) {
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        
        // Today
        if (/\btoday\b/.test(text)) {
            return today;
        }
        
        // Tomorrow
        if (/\btomorrow\b/.test(text)) {
            const tomorrow = new Date(today);
            tomorrow.setDate(tomorrow.getDate() + 1);
            return tomorrow;
        }
        
        // Day names (Monday, Tuesday, etc.)
        const days = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'];
        const dayAbbrevs = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat'];
        
        for (let i = 0; i < days.length; i++) {
            const pattern = new RegExp('\\b' + days[i] + '\\b|\\b' + dayAbbrevs[i] + '\\b', 'i');
            if (pattern.test(text)) {
                return getNextDayOfWeek(today, i);
            }
        }
        
        // Month + day: Nov 28, November 28, 28 Nov, Dec 5
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
        
        // Pattern: Month Day (Nov 28, November 28)
        const monthDayPattern = /\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+(\d{1,2})\b/i;
        const monthDayMatch = text.match(monthDayPattern);
        
        if (monthDayMatch) {
            const monthStr = monthDayMatch[1].toLowerCase();
            const day = parseInt(monthDayMatch[2]);
            
            // Find the month number
            let monthNum = null;
            for (const [key, val] of Object.entries(months)) {
                if (monthStr.startsWith(key) || key.startsWith(monthStr)) {
                    monthNum = val;
                    break;
                }
            }
            
            if (monthNum !== null && day >= 1 && day <= 31) {
                const result = new Date(today.getFullYear(), monthNum, day);
                // If the date is in the past, assume next year
                if (result < today) {
                    result.setFullYear(result.getFullYear() + 1);
                }
                return result;
            }
        }
        
        // Pattern: Day Month (28 Nov, 28 November)
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
    
    function getNextDayOfWeek(fromDate, dayOfWeek) {
        const result = new Date(fromDate);
        const currentDay = result.getDay();
        let daysToAdd = dayOfWeek - currentDay;
        
        // If it's the same day or in the past this week, go to next week
        if (daysToAdd <= 0) {
            daysToAdd += 7;
        }
        
        result.setDate(result.getDate() + daysToAdd);
        return result;
    }
});