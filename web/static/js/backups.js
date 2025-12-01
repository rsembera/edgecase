/**
 * EdgeCase Equalizer - Backup System JavaScript
 * Handles backup creation, restore point selection, and settings management.
 * Simplified UI: One backup button, all backups are valid restore points.
 */

document.addEventListener('DOMContentLoaded', function() {
    loadBackupStatus();
    loadRestorePoints();
    
    // Enable/disable restore button based on selection
    document.getElementById('restore-point-select').addEventListener('change', function() {
        const btn = document.getElementById('prepare-restore-btn');
        btn.disabled = !this.value;
    });
});

/**
 * Load backup status and settings from server
 */
async function loadBackupStatus() {
    try {
        const response = await fetch('/api/backup/status');
        const data = await response.json();
        
        // Update last backup display
        document.getElementById('last-backup-display').textContent = data.last_backup_display || 'Never';
        
        // Update backup count
        document.getElementById('backup-count').textContent = data.backup_count || 0;
        
        // Set frequency dropdown
        const freqSelect = document.getElementById('backup-frequency');
        if (data.frequency) {
            freqSelect.value = data.frequency;
        }
        
        // Populate cloud folders and set saved location
        populateLocationDropdown(data.cloud_folders || [], data.location || '');
        
        // Check for pending restore
        if (data.restore_pending) {
            document.getElementById('pending-restore-point').textContent = data.restore_point || 'Unknown';
            document.getElementById('restore-pending-alert').classList.remove('hidden');
        }
        
    } catch (error) {
        console.error('Error loading backup status:', error);
        document.getElementById('last-backup-display').textContent = 'Error loading';
    }
}

/**
 * Populate location dropdown with cloud folders
 * @param {Array} cloudFolders - Array of {path, name} objects
 * @param {string} savedLocation - Currently saved location path
 */
function populateLocationDropdown(cloudFolders, savedLocation) {
    const select = document.getElementById('backup-location');
    
    // Add cloud folder options
    cloudFolders.forEach(folder => {
        const option = document.createElement('option');
        option.value = folder.path;
        option.textContent = folder.name;
        select.appendChild(option);
    });
    
    // Set saved location if it matches an option
    if (savedLocation) {
        for (let i = 0; i < select.options.length; i++) {
            if (select.options[i].value === savedLocation) {
                select.selectedIndex = i;
                break;
            }
        }
    }
    
    updateLocationPath();
}

/**
 * Update the location path display below dropdown
 */
function updateLocationPath() {
    const select = document.getElementById('backup-location');
    const pathDisplay = document.getElementById('location-path');
    
    if (select.value === 'default') {
        pathDisplay.textContent = '';
    } else {
        pathDisplay.textContent = select.value;
    }
}

/**
 * Load all available restore points (backups)
 */
async function loadRestorePoints() {
    try {
        const response = await fetch('/api/backup/restore-points');
        const data = await response.json();
        
        const listEl = document.getElementById('backup-list');
        const selectEl = document.getElementById('restore-point-select');
        
        // Clear existing options except the first one
        while (selectEl.options.length > 1) {
            selectEl.remove(1);
        }
        
        if (!data.restore_points || data.restore_points.length === 0) {
            listEl.innerHTML = '<div class="backup-list-empty">No backups yet. Click "Backup Now" to create your first backup.</div>';
            return;
        }
        
        // Build backup list HTML with delete buttons
        let html = '';
        data.restore_points.forEach(point => {
            const safetyClass = point.is_safety ? 'safety' : '';
            const safetyLabel = point.is_safety ? '<span class="safety-badge">Safety</span>' : '';
            
            html += `
                <div class="backup-item ${safetyClass}">
                    <div class="backup-item-info">
                        <span class="backup-item-name">${point.display_name}</span>
                        ${safetyLabel}
                    </div>
                    <button class="btn-delete-backup" onclick="confirmDeleteBackup('${point.id}', '${point.display_name}', ${point.is_safety})" title="Delete this backup">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
                        </svg>
                    </button>
                </div>
            `;
            
            // Add to restore dropdown
            const option = document.createElement('option');
            option.value = point.id;
            option.textContent = point.display_name;
            selectEl.appendChild(option);
        });
        
        listEl.innerHTML = html;
        
    } catch (error) {
        console.error('Error loading restore points:', error);
        document.getElementById('backup-list').innerHTML = 
            '<div class="backup-list-empty">Error loading backups</div>';
    }
}

/**
 * Perform backup - single button, system decides full vs incremental
 */
async function performBackup() {
    const btn = document.getElementById('backup-now-btn');
    const btnText = btn.querySelector('.btn-text');
    const btnSpinner = btn.querySelector('.btn-spinner');
    
    // Disable button and show spinner
    btn.disabled = true;
    btnText.textContent = 'Backing up...';
    btnSpinner.classList.remove('hidden');
    
    try {
        const response = await fetch('/api/backup/now', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        });
        
        const data = await response.json();
        
        if (data.success) {
            if (data.backup) {
                showMessage('Backup created successfully!', 'success');
            } else {
                showMessage('No changes since last backup.', 'info');
            }
            loadBackupStatus();
            loadRestorePoints();
        } else {
            showMessage(data.error || 'Backup failed', 'error');
        }
    } catch (error) {
        console.error('Backup error:', error);
        showMessage('Backup failed: ' + error.message, 'error');
    } finally {
        // Re-enable button
        btn.disabled = false;
        btnText.textContent = 'Backup Now';
        btnSpinner.classList.add('hidden');
    }
}

/**
 * Save backup settings (frequency and location)
 */
async function saveBackupSettings() {
    const frequency = document.getElementById('backup-frequency').value;
    const locationSelect = document.getElementById('backup-location');
    
    const body = { frequency: frequency };
    
    // Send location (empty string for default)
    if (locationSelect.value !== 'default') {
        body.location = locationSelect.value;
    } else {
        body.location = '';
    }
    
    try {
        const response = await fetch('/api/backup/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        
        const data = await response.json();
        
        if (data.success) {
            window.location.href = '/';
        } else {
            showMessage('Failed to save settings: ' + (data.error || 'Unknown error'), 'error');
        }
    } catch (error) {
        console.error('Save settings error:', error);
        showMessage('Failed to save settings: ' + error.message, 'error');
    }
}

/**
 * Show delete confirmation modal
 * @param {string} backupId - ID of backup to delete
 * @param {string} displayName - Display name for confirmation
 * @param {boolean} isSafety - Whether this is a safety backup
 */
function confirmDeleteBackup(backupId, displayName, isSafety) {
    const modal = document.getElementById('delete-modal');
    const nameEl = document.getElementById('modal-delete-backup-name');
    const warningEl = document.getElementById('delete-safety-warning');
    
    nameEl.textContent = displayName;
    
    if (isSafety) {
        warningEl.classList.remove('hidden');
    } else {
        warningEl.classList.add('hidden');
    }
    
    // Store backup ID for confirm action
    modal.dataset.backupId = backupId;
    modal.classList.remove('hidden');
}

/**
 * Hide the delete confirmation modal
 */
function hideDeleteModal() {
    document.getElementById('delete-modal').classList.add('hidden');
}

/**
 * Confirm and execute backup deletion
 */
async function confirmDelete() {
    const modal = document.getElementById('delete-modal');
    const backupId = modal.dataset.backupId;
    
    hideDeleteModal();
    
    try {
        const response = await fetch('/api/backup/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ backup_id: backupId })
        });
        
        const data = await response.json();
        
        if (data.success) {
            let message = 'Backup deleted.';
            if (data.warnings && data.warnings.length > 0) {
                message += ' ' + data.warnings.join(' ');
            }
            showMessage(message, 'success');
            loadBackupStatus();
            loadRestorePoints();
        } else {
            showMessage('Failed to delete: ' + (data.error || 'Unknown error'), 'error');
        }
    } catch (error) {
        console.error('Delete error:', error);
        showMessage('Failed to delete: ' + error.message, 'error');
    }
}

/**
 * Show restore confirmation modal
 */
function showRestoreModal() {
    const select = document.getElementById('restore-point-select');
    const selectedOption = select.options[select.selectedIndex];
    
    document.getElementById('modal-restore-point').textContent = selectedOption.textContent;
    document.getElementById('restore-modal').classList.remove('hidden');
}

/**
 * Hide the restore confirmation modal
 */
function hideRestoreModal() {
    document.getElementById('restore-modal').classList.add('hidden');
}

/**
 * Confirm and prepare restore from selected point
 */
async function confirmRestore() {
    const restorePointId = document.getElementById('restore-point-select').value;
    
    hideRestoreModal();
    
    try {
        const response = await fetch('/api/backup/prepare-restore', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ restore_point: restorePointId })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showMessage('Restore prepared. Please restart EdgeCase to complete the restore.', 'info');
            loadBackupStatus();
        } else {
            showMessage('Failed to prepare restore: ' + (data.error || 'Unknown error'), 'error');
        }
    } catch (error) {
        console.error('Restore error:', error);
        showMessage('Failed to prepare restore: ' + error.message, 'error');
    }
}

/**
 * Cancel a pending restore operation
 */
async function cancelRestore() {
    try {
        const response = await fetch('/api/backup/cancel-restore', {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (data.success) {
            showMessage('Restore cancelled.', 'success');
            document.getElementById('restore-pending-alert').classList.add('hidden');
        } else {
            showMessage('Failed to cancel restore: ' + (data.error || 'Unknown error'), 'error');
        }
    } catch (error) {
        console.error('Cancel restore error:', error);
        showMessage('Failed to cancel restore: ' + error.message, 'error');
    }
}

/**
 * Show a message to the user
 * @param {string} text - Message text
 * @param {string} type - Message type: 'success', 'error', or 'info'
 */
function showMessage(text, type) {
    const msgEl = document.getElementById('backup-message');
    msgEl.textContent = text;
    msgEl.className = 'backup-message ' + type;
    msgEl.classList.remove('hidden');
    
    // Auto-hide after 5 seconds for success/info messages
    if (type === 'success' || type === 'info') {
        setTimeout(() => {
            msgEl.classList.add('hidden');
        }, 5000);
    }
}
