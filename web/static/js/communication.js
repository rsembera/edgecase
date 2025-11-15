// Communication Entry Form JavaScript - Extracted from communication.html

// Auto-expanding textarea
const textarea = document.getElementById('content');
const maxHeight = 600; // About 30-35 lines

function autoResize() {
    // Reset height to auto to get the correct scrollHeight
    textarea.style.height = 'auto';
    
    // Set new height, but don't exceed maxHeight
    const newHeight = Math.min(textarea.scrollHeight, maxHeight);
    textarea.style.height = newHeight + 'px';
    
    // Add scrollbar if content exceeds maxHeight
    if (textarea.scrollHeight > maxHeight) {
        textarea.style.overflowY = 'scroll';
    } else {
        textarea.style.overflowY = 'hidden';
    }
}

// Run on page load (for edit mode with existing content)
autoResize();

// Run on input
textarea.addEventListener('input', autoResize);
