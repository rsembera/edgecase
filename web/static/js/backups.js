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
    
    // Save frequency setting on change
    document.getElementById('backup-frequency').addEventListener('change', function() {
        saveSettingWithConfirm('frequency');
    });
    
    // Save retention setting on change
    document.getElementById('backup-retention').addEventListener('change', function() {
        saveSettingWithConfirm('retention');
    });
    
    // Save location setting on change (but not for 'custom' - that needs the save button)
    document.getElementById('backup-location').addEventListener('change', function() {
        updateLocationPath();
        if (this.value !== 'custom') {
            saveSettingWithConfirm('location');
        }
    });
    
    // Save custom location when save button clicked
    document.getElementById('save-custom-location-btn').addEventListener('click', function() {
        saveSettingWithConfirm('location');
    });
    
    // Also save custom location on Enter key
    document.getElementById('custom-location-input').addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            saveSettingWithConfirm('location');
        }
    });
    
    // Save post-backup command on blur (when user finishes typing)
    document.getElementById('post-backup-command').addEventListener('blur', function() {
        saveSettingWithConfirm('post_backup_command');
    });
    
    // Restore button click handler
    document.getElementById('prepare-restore-btn').addEventListener('click', function() {
        if (!this.disabled) {
            showRestoreModal();
        }
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
        
        // Set frequency dropdown using Choices API
        if (data.frequency) {
            window.setChoicesValue('backup-frequency', data.frequency);
        }
        
        // Set retention dropdown using Choices API
        if (data.retention) {
            window.setChoicesValue('backup-retention', data.retention);
        }
        
        // Set post-backup command
        if (data.post_backup_command !== undefined) {
            document.getElementById('post-backup-command').value = data.post_backup_command;
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
    // Check if saved location is a custom path (not default and not a cloud folder)
    const isCustomLocation = savedLocation && 
        savedLocation !== 'default' && 
        !cloudFolders.some(f => f.path === savedLocation);
    
    // Build options array - default option plus cloud folders plus custom
    const options = [
        { value: 'default', label: 'Default (app folder)', selected: !savedLocation || savedLocation === 'default' }
    ];
    
    cloudFolders.forEach(folder => {
        options.push({
            value: folder.path,
            label: folder.name,
            selected: savedLocation === folder.path
        });
    });
    
    // Add custom option
    options.push({
        value: 'custom',
        label: 'Custom...',
        selected: isCustomLocation
    });
    
    // Update using Choices API
    window.updateChoicesOptions('backup-location', options, true);
    
    // If we have a custom location, show the input and populate it
    if (isCustomLocation) {
        document.getElementById('custom-location-input').value = savedLocation;
        document.getElementById('custom-location-wrapper').classList.remove('hidden');
    }
    
    updateLocationPath();
}

/**
 * Update the location path display below dropdown and handle custom input visibility
 */
function updateLocationPath() {
    const select = document.getElementById('backup-location');
    const pathDisplay = document.getElementById('location-path');
    const customWrapper = document.getElementById('custom-location-wrapper');
    const customInput = document.getElementById('custom-location-input');
    
    if (select.value === 'default') {
        pathDisplay.textContent = '';
        customWrapper.classList.add('hidden');
    } else if (select.value === 'custom') {
        // Show custom input, display its value (or empty if not set yet)
        customWrapper.classList.remove('hidden');
        pathDisplay.textContent = customInput.value || '';
    } else {
        pathDisplay.textContent = select.value;
        customWrapper.classList.add('hidden');
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
        
        // Collect restore options for Choices dropdown
        const restoreOptions = [
            { value: '', label: 'Select a backup...' }
        ];
        
        if (!data.restore_points || data.restore_points.length === 0) {
            listEl.innerHTML = '<div class="backup-list-empty">No backups yet. Click "Backup Now" to create your first backup.</div>';
            window.updateChoicesOptions('restore-point-select', restoreOptions, true);
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
        
        // Collect all full backup dates for comparison
        const allFullBackups = [];
        for (const chainId of sortedChainIds) {
            const chain = chains[chainId];
            if (chain.full) {
                allFullBackups.push(chain.full);
            }
        }
        
        for (const chainId of sortedChainIds) {
            const chain = chains[chainId];
            
            // Safety backups (standalone)
            if (chain.safety) {
                html += renderSafetyBackup(chain.safety);
                restoreOptions.push(buildRestoreOption(chain.safety));
                continue;
            }
            
            // Full backup (chain header)
            if (chain.full) {
                // Check if a newer full backup exists
                const newerFullExists = allFullBackups.some(
                    fb => fb.created_at > chain.full.created_at
                );
                html += renderFullBackup(chain.full, newerFullExists);
                restoreOptions.push(buildRestoreOption(chain.full));
                
                // Incremental backups (indented under full)
                if (chain.incrementals && chain.incrementals.length > 0) {
                    // Sort incrementals by date (oldest first for display order)
                    chain.incrementals.sort((a, b) => a.created_at.localeCompare(b.created_at));
                    
                    for (let i = 0; i < chain.incrementals.length; i++) {
                        const incr = chain.incrementals[i];
                        const isLast = (i === chain.incrementals.length - 1);
                        const laterCount = chain.incrementals.length - 1 - i;  // Number of later incrementals
                        html += renderIncrementalBackup(incr, isLast, laterCount);
                        restoreOptions.push(buildRestoreOption(incr));
                    }
                }
                
                // Close the chain div
                html += '        </div>';
            }
        }
        
        listEl.innerHTML = html;
        
        // Update the restore dropdown with all options
        window.updateChoicesOptions('restore-point-select', restoreOptions, true);
        
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
 * @param {Object} point - The full backup point
 * @param {boolean} newerFullExists - Whether a newer full backup exists (unused, kept for compatibility)
 */
function renderFullBackup(point, newerFullExists) {
    const dependentText = point.dependent_count > 0 
        ? `<span class="dependent-count">${point.dependent_count} dependent</span>` 
        : '';
    
    return `
        <div class="backup-chain">
            <div class="backup-item backup-full" data-id="${point.id}" data-type="full">
                <div class="backup-item-info">
                    <span class="backup-type-badge badge-full">Full</span>
                    <span class="backup-item-name">${point.display_name}</span>
                    ${dependentText}
                </div>
            </div>
    `;
}

/**
 * Render an incremental backup item (indented under full)
 * @param {Object} point - The incremental backup point
 * @param {boolean} isLast - Whether this is the last incremental in the chain
 * @param {number} laterCount - Number of later incrementals (unused, kept for compatibility)
 */
function renderIncrementalBackup(point, isLast, laterCount) {
    const connectorClass = isLast ? 'connector-last' : 'connector-mid';
    
    return `
            <div class="backup-item backup-incremental" data-id="${point.id}" data-type="incremental">
                <div class="backup-connector ${connectorClass}"></div>
                <div class="backup-item-info">
                    <span class="backup-type-badge badge-incr">Incr</span>
                    <span class="backup-item-name">${point.display_name}</span>
                </div>
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
            </div>
        </div>
    `;
}

/**
 * Build an option object for the restore dropdown (for Choices.js)
 */
function buildRestoreOption(point) {
    // Add type indicator to dropdown text
    let typeLabel = '';
    if (point.type === 'full') typeLabel = '[Full] ';
    else if (point.type === 'incremental') typeLabel = '[Incr] ';
    else if (point.type === 'pre_restore') typeLabel = '[Safety] ';
    
    return {
        value: point.id,
        label: typeLabel + point.display_name
    };
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
 * @param {string} settingType - 'frequency', 'retention', 'location', or 'post_backup_command'
 */
async function saveSettingWithConfirm(settingType) {
    const frequency = document.getElementById('backup-frequency').value;
    const retention = document.getElementById('backup-retention').value;
    let location = document.getElementById('backup-location').value;
    const postBackupCommand = document.getElementById('post-backup-command').value;
    
    // If custom location selected, get the actual path from the input
    if (location === 'custom') {
        location = document.getElementById('custom-location-input').value.trim();
        if (!location) {
            showMessage('Please enter a custom backup path', 'error');
            return;
        }
    }
    
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
                retention: retention,
                location: location === 'default' ? '' : location,
                post_backup_command: postBackupCommand
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Show brief confirmation message
            const settingNames = {
                'frequency': 'Automatic backup setting',
                'retention': 'Retention period',
                'location': 'Backup location',
                'post_backup_command': 'Post-backup command'
            };
            const settingName = settingNames[settingType] || 'Setting';
            showMessage(`${settingName} saved`, 'success');
            
            // Update the location path display after saving custom location
            if (settingType === 'location') {
                const pathDisplay = document.getElementById('location-path');
                const select = document.getElementById('backup-location');
                if (select.value === 'custom') {
                    pathDisplay.textContent = document.getElementById('custom-location-input').value;
                }
            }
            
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
 * Show restore confirmation modal
 */
function showRestoreModal() {
    const select = document.getElementById('restore-point-select');
    
    // Get selected text - works with both native select and Choices.js
    let selectedText = '';
    if (select.selectedIndex >= 0 && select.options[select.selectedIndex]) {
        selectedText = select.options[select.selectedIndex].textContent;
    } else {
        // Fallback: try to get from Choices instance
        const instance = window.choicesInstances['restore-point-select'];
        if (instance) {
            const selected = instance.getValue();
            selectedText = selected ? selected.label : 'Unknown backup';
        }
    }
    
    document.getElementById('modal-restore-point').textContent = selectedText;
    const modal = document.getElementById('restore-modal');
    modal.classList.remove('hidden');
    modal.classList.add('visible');
}

/**
 * Hide the restore confirmation modal
 */
function hideRestoreModal() {
    const modal = document.getElementById('restore-modal');
    modal.classList.remove('visible');
    modal.classList.add('hidden');
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
