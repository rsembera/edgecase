/**
 * Desktop File Handler
 * Opens/downloads files in desktop mode, falls back to browser behavior otherwise
 */

/**
 * Check if running in PyWebView desktop mode
 * @returns {boolean}
 */
function isDesktopMode() {
    return !!(window.pywebview && window.pywebview.api && window.pywebview.api.open_file);
}

/**
 * Open a file URL - routes to system default app in desktop mode, browser tab otherwise
 * @param {string} url - The file URL to open
 */
function openFile(url) {
    if (isDesktopMode()) {
        window.pywebview.api.open_file(url);
    } else {
        window.open(url, '_blank');
    }
}

/**
 * Download a file URL - saves to Downloads folder in desktop mode, browser download otherwise
 * @param {string} url - The file URL to download
 */
function downloadFile(url) {
    if (isDesktopMode()) {
        // Call Python API and show notification with result
        window.pywebview.api.download_file(url).then(function(filename) {
            if (filename) {
                showDownloadNotification(filename);
            }
        });
    } else {
        // Browser mode - use normal link behavior
        const a = document.createElement('a');
        a.href = url;
        a.download = '';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    }
}

/**
 * Show a brief download notification
 * @param {string} filename - The downloaded filename
 */
function showDownloadNotification(filename) {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = 'download-notification';
    notification.innerHTML = `<span>✓ Downloaded: ${filename}</span>`;
    notification.style.cssText = `
        position: fixed;
        bottom: 20px;
        right: 20px;
        background: #2d3748;
        color: white;
        padding: 12px 20px;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        z-index: 10000;
        font-size: 14px;
        animation: slideIn 0.3s ease-out;
    `;
    
    // Add animation keyframes if not present
    if (!document.getElementById('download-notification-styles')) {
        const style = document.createElement('style');
        style.id = 'download-notification-styles';
        style.textContent = `
            @keyframes slideIn {
                from { transform: translateX(100%); opacity: 0; }
                to { transform: translateX(0); opacity: 1; }
            }
            @keyframes slideOut {
                from { transform: translateX(0); opacity: 1; }
                to { transform: translateX(100%); opacity: 0; }
            }
        `;
        document.head.appendChild(style);
    }
    
    document.body.appendChild(notification);
    
    // Remove after 3 seconds
    setTimeout(function() {
        notification.style.animation = 'slideOut 0.3s ease-in';
        setTimeout(function() {
            notification.remove();
        }, 300);
    }, 3000);
}

/**
 * Open a PDF URL (convenience alias for openFile)
 * @param {string} url - The PDF URL to open
 */
function openPDF(url) {
    openFile(url);
}
