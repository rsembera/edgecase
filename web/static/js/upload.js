/**
 * Upload Entry Form JavaScript - EdgeCase Equalizer
 * Handles file upload entry creation/editing.
 * File upload functions are in file-upload.js
 */

// Auto-expanding textarea for content/notes field
const textarea = document.getElementById('content');
const maxHeight = 400;

if (textarea) {
    /**
     * Auto-resize textarea to fit content up to maxHeight
     */
    function autoResize() {
        textarea.style.height = 'auto';
        const newHeight = Math.min(textarea.scrollHeight, maxHeight);
        textarea.style.height = newHeight + 'px';
        
        if (textarea.scrollHeight > maxHeight) {
            textarea.style.overflowY = 'scroll';
        } else {
            textarea.style.overflowY = 'hidden';
        }
    }
    
    autoResize();
    textarea.addEventListener('input', autoResize);
}

/**
 * Show file validation modal
 */
function showFileValidationModal() {
    document.getElementById('file-validation-modal').style.display = 'flex';
}

/**
 * Close file validation modal
 */
function closeFileValidationModal() {
    document.getElementById('file-validation-modal').style.display = 'none';
}

// ============================================================
// DATE/TIME PICKERS
// ============================================================

/**
 * Initialize date and time pickers for upload form
 */
async function initUploadPickers() {
    // Get time format setting
    const timeFormat = await getTimeFormatSetting();
    
    // Get initial values from hidden inputs
    const dateInput = document.getElementById('date');
    const timeInput = document.getElementById('upload_time');
    
    // Initialize date picker
    const datePicker = initDatePicker('upload-date-picker', {
        initialDate: dateInput.value ? parseDateString(dateInput.value) : new Date(),
        onSelect: (date) => {
            const year = date.getFullYear();
            const month = String(date.getMonth() + 1).padStart(2, '0');
            const day = String(date.getDate()).padStart(2, '0');
            dateInput.value = `${year}-${month}-${day}`;
        }
    });
    
    // CRITICAL: Set initial date value if not already set (new entries)
    // Without this, if user doesn't click a date, the hidden input stays empty
    if (!dateInput.value && datePicker) {
        const today = new Date();
        const year = today.getFullYear();
        const month = String(today.getMonth() + 1).padStart(2, '0');
        const day = String(today.getDate()).padStart(2, '0');
        dateInput.value = `${year}-${month}-${day}`;
    }
    
    // Initialize time picker
    const timePicker = initTimePicker('upload-time-picker', {
        format: timeFormat,
        initialTime: timeInput.value || null,
        onSelect: (timeStr) => {
            timeInput.value = timeStr;
        }
    });
    
    // If no initial time and not in edit mode, populate with current time
    if (!timeInput.value) {
        timeInput.value = timePicker.formatTime();
    }
}

// Initialize pickers when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initUploadPickers);
} else {
    initUploadPickers();
}
