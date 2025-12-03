/**
 * EdgeCase Equalizer - Backup System JavaScript
 * Handles backup creation, restore point selection, and settings management.
 * Displays backup chains with visual hierarchy showing dependencies.
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
 * Load all available restore points (backups) and display with chain structure
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
        
        // Group backups by chain for visual hierarchy
        const chains = groupByChain(data.restore_points);
        
        // Build backup list HTML with chain structure
        let html = '';
        
        // Render chains in order (newest first based on full backup date)
        const sortedChainIds = Object.keys(chains).sort((a, b) => {
            const aDate = chains[a].full ? chains[a].full.created_at : (chains[a].safety ? chains[a].safety.created_at : '');
            const bDate = chains[b].full ? chains[b].full.created_at : (chains[b].safety ? chains[b].safety.created_at : '');
            return bDate.localeCompare(aDate);
        });
        
        for (const chainId of sortedChainIds) {
            const chain = chains[chainId];
            
            // Safety backups (standalone)
            if (chain.safety) {
                html += renderSafetyBackup(chain.safety);
                addToRestoreDropdown(selectEl, chain.safety);
                continue;
            }
            
            // Full backup (chain header)
            if (chain.full) {
                html += renderFullBackup(chain.full);
                addToRestoreDropdown(selectEl, chain.full);
                
                // Incremental backups (indented under full)
                if (chain.incrementals && chain.incrementals.length > 0) {
                    // Sort incrementals by date (oldest first for display order)
                    chain.incrementals.sort((a, b) => a.created_at.localeCompare(b.created_at));
                    
                    for (let i = 0; i < chain.incrementals.length; i++) {
                        const incr = chain.incrementals[i];
                        const isLast = (i === chain.incrementals.length - 1);
                        html += renderIncrementalBackup(incr, isLast);
                        addToRestoreDropdown(selectEl, incr);
                    }
                }
                
                // Close the chain div
                html += '        </div>';
            }
        }
        
        listEl.innerHTML = html;
        
    } catch (error) {
        console.error('Error loading restore points:', error);
        document.getElementById('backup-list').innerHTML = 
            '<div class="backup-list-empty">Error loading backups</div>';
    }
}

/**
 * Group restore points by chain_id
 * @param {Array} points - Array of restore points
 * @returns {Object} - Grouped by chain_id
 */
function groupByChain(points) {
    const chains = {};
    
    for (const point of points) {
        const chainId = point.chain_id;
        
        if (!chains[chainId]) {
            chains[chainId] = { full: null, incrementals: [], safety: null };
        }
        
        if (point.type === 'full') {
            chains[chainId].full = point;
        } else if (point.type === 'incremental') {
            chains[chainId].incrementals.push(point);
        } else if (point.type === 'pre_restore') {
            chains[chainId].safety = point;
        }
    }
    
    return chains;
}

/**
 * Render a full backup item (chain header)
 */
function renderFullBackup(point) {
    const dependentText = point.dependent_count > 0 
        ? `<span class="dependent-count">${point.dependent_count} dependent</span>` 
        : '';
    
    return `
        <div class="backup-chain">
            <div class="backup-item backup-full" data-id="${point.id}" data-type="full" data-dependents="${point.dependent_count}">
                <div class="backup-item-info">
                    <span class="backup-type-badge badge-full">Full</span>
                    <span class="backup-item-name">${point.display_name}</span>
                    ${dependentText}
                </div>
                <button class="btn-delete-backup" onclick="confirmDeleteBackup('${point.id}', '${point.display_name}', false, ${point.dependent_count})" title="Delete this backup">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
                    </svg>
                </button>
            </div>
    `;
}

/**
 * Render an incremental backup item (indented under full)
 */
function renderIncrementalBackup(point, isLast) {
    const connectorClass = isLast ? 'connector-last' : 'connector-mid';
    
    return `
            <div class="backup-item backup-incremental" data-id="${point.id}" data-type="incremental">
                <div class="backup-connector ${connectorClass}"></div>
                <div class="backup-item-info">
                    <span class="backup-type-badge badge-incr">Incr</span>
                    <span class="backup-item-name">${point.display_name}</span>
                </div>
                <button class="btn-delete-backup" onclick="confirmDeleteBackup('${point.id}', '${point.display_name}', false, 0)" title="Delete this backup">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
                    </svg>
                </button>
            </div>
    `;
}

/**
 * Render a safety backup (pre-restore)
 */
function renderSafetyBackup(point) {
    return `
        <div class="backup-chain">
            <div class="backup-item backup-safety" data-id="${point.id}" data-type="pre_restore">
                <div class="backup-item-info">
                    <span class="backup-type-badge badge-safety">Safety</span>
                    <span class="backup-item-name">${point.display_name}</span>
                </div>
                <button class="btn-delete-backup" onclick="confirmDeleteBackup('${point.id}', '${point.display_name}', true, 0)" title="Delete this backup">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
                    </svg>
                </button>
            </div>
        </div>
    `;
}

/**
 * Add a restore point to the dropdown
 */
function addToRestoreDropdown(selectEl, point) {
    const option = document.createElement('option');
    option.value = point.id;
    
    // Add type indicator to dropdown text
    let typeLabel = '';
    if (point.type === 'full') typeLabel = '[Full] ';
    else if (point.type === 'incremental') typeLabel = '[Incr] ';
    else if (point.type === 'pre_restore') typeLabel = '[Safety] ';
    
    option.textContent = typeLabel + point.display_name;
    selectEl.appendChild(option);
}

/**
 * Trigger backup creation
 */
async function performBackup() {
    const btn = document.getElementById('backup-now-btn');
    const btnText = btn.querySelector('.btn-text');
    const spinner = btn.querySelector('.btn-spinner');
    
    // Show loading state
    btn.disabled = true;
    btnText.textContent = 'Backing up...';
    spinner.classList.remove('hidden');
    
    try {
        const response = await fetch('/api/backup/now', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        const data = await response.json();
        
        if (data.success) {
            if (data.backup) {
                showMessage(`Backup created: ${data.backup.type}`, 'success');
            } else {
                showMessage('No changes since last backup', 'info');
            }
            loadBackupStatus();
            loadRestorePoints();
        } else {
            showMessage('Backup failed: ' + (data.error || 'Unknown error'), 'error');
        }
    } catch (error) {
        console.error('Backup error:', error);
        showMessage('Backup failed: ' + error.message, 'error');
    } finally {
        // Reset button state
        btn.disabled = false;
        btnText.textContent = 'Backup Now';
        spinner.classList.add('hidden');
    }
}

/**
 * Save a single setting with confirmation message (auto-save on dropdown change)
 * @param {string} settingType - 'frequency' or 'location'
 */
async function saveSettingWithConfirm(settingType) {
    const frequency = document.getElementById('backup-frequency').value;
    const location = document.getElementById('backup-location').value;
    
    // Update location path display if location changed
    if (settingType === 'location') {
        updateLocationPath();
    }
    
    try {
        const response = await fetch('/api/backup/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                frequency: frequency,
                location: location === 'default' ? '' : location
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Show brief confirmation message
            const settingName = settingType === 'frequency' ? 'Automatic backup setting' : 'Backup location';
            showMessage(`${settingName} saved`, 'success');
            
            // Auto-hide the message after 2 seconds
            setTimeout(() => {
                const msgEl = document.getElementById('backup-message');
                if (msgEl && msgEl.classList.contains('success')) {
                    msgEl.classList.add('hidden');
                }
            }, 2000);
        } else {
            showMessage('Failed to save: ' + (data.error || 'Unknown error'), 'error');
        }
    } catch (error) {
        console.error('Save setting error:', error);
        showMessage('Failed to save: ' + error.message, 'error');
    }
}

/**
 * Show delete confirmation modal with dependency warning
 * @param {string} backupId - ID of backup to delete
 * @param {string} displayName - Display name for confirmation
 * @param {boolean} isSafety - Whether this is a safety backup
 * @param {number} dependentCount - Number of dependent backups (for full backups)
 */
function confirmDeleteBackup(backupId, displayName, isSafety, dependentCount) {
    const modal = document.getElementById('delete-modal');
    const nameEl = document.getElementById('modal-delete-backup-name');
    const safetyWarningEl = document.getElementById('delete-safety-warning');
    const dependentWarningEl = document.getElementById('delete-dependent-warning');
    const dependentCountEl = document.getElementById('dependent-count-display');
    
    nameEl.textContent = displayName;
    
    // Show/hide safety warning
    if (isSafety) {
        safetyWarningEl.classList.remove('hidden');
    } else {
        safetyWarningEl.classList.add('hidden');
    }
    
    // Show/hide dependent warning
    if (dependentCount > 0) {
        dependentCountEl.textContent = dependentCount;
        dependentWarningEl.classList.remove('hidden');
    } else {
        dependentWarningEl.classList.add('hidden');
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
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        const data = await response.json();
        
        if (data.success) {
            showMessage('Restore cancelled.', 'info');
            document.getElementById('restore-pending-alert').classList.add('hidden');
            loadBackupStatus();
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
 * @param {string} type - Message type: 'success', 'error', 'info'
 */
function showMessage(text, type) {
    const messageEl = document.getElementById('backup-message');
    messageEl.textContent = text;
    messageEl.className = `backup-message ${type}`;
    messageEl.classList.remove('hidden');
    
    // Auto-hide after 5 seconds for success/info messages
    if (type !== 'error') {
        setTimeout(() => {
            messageEl.classList.add('hidden');
        }, 5000);
    }
}
