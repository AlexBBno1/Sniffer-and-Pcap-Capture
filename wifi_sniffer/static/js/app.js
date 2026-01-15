/**
 * WiFi Sniffer Web Control Panel - JavaScript
 * ============================================
 * Handles UI interactions and WebSocket communication.
 */

// ============== Configuration ==============
const WS_RECONNECT_INTERVAL = 3000;
const STATUS_UPDATE_INTERVAL = 5000;

// ============== State ==============
let socket = null;
let isConnected = false;
let connectionCheckInterval = null;

// ============== WebSocket ==============
function initWebSocket() {
    // Check if Socket.IO is available
    if (typeof io === 'undefined') {
        console.log('[WS] Socket.IO not available, falling back to polling');
        startPolling();
        return;
    }

    socket = io({
        transports: ['websocket', 'polling'],
        reconnection: true,
        reconnectionDelay: WS_RECONNECT_INTERVAL
    });

    socket.on('connect', () => {
        console.log('[WS] Connected');
        socket.emit('request_connection');
        socket.emit('request_status');
    });

    socket.on('disconnect', () => {
        console.log('[WS] Disconnected');
    });

    socket.on('status_update', (data) => {
        updateStatusDisplay(data);
    });

    socket.on('connection_update', (data) => {
        updateConnectionDisplay(data.connected);
        if (data.interfaces) {
            updateInterfaceDisplay(data.interfaces, data.detection_status);
        }
    });

    socket.on('connect_error', () => {
        console.log('[WS] Connection error, falling back to polling');
        startPolling();
    });
}

// ============== Polling Fallback ==============
function startPolling() {
    // Status polling
    setInterval(async () => {
        try {
            const response = await fetch('/api/status');
            const data = await response.json();
            updateStatusDisplay(data);
        } catch (e) {
            console.error('[Polling] Status error:', e);
        }
    }, STATUS_UPDATE_INTERVAL);

    // Connection check on page load
    checkConnection();
}

// ============== Connection ==============
async function checkConnection() {
    const dot = document.getElementById('connectionDot');
    const text = document.getElementById('connectionText');

    if (dot) {
        dot.className = 'status-dot checking';
    }
    if (text) {
        text.textContent = 'Checking connection...';
    }

    try {
        const response = await fetch('/api/test_connection');
        const data = await response.json();
        
        updateConnectionDisplay(data.connected);
        
        if (data.connected) {
            // Auto-detect interfaces if connected
            if (!window.interfacesDetected) {
                detectInterfaces();
            }
        }
    } catch (e) {
        console.error('[Connection] Check failed:', e);
        updateConnectionDisplay(false);
    }
}

function updateConnectionDisplay(connected) {
    const dot = document.getElementById('connectionDot');
    const text = document.getElementById('connectionText');

    if (dot) {
        dot.className = 'status-dot ' + (connected ? 'connected' : 'disconnected');
    }
    if (text) {
        text.textContent = connected 
            ? '192.168.1.1 Connected' 
            : '192.168.1.1 Disconnected - Click to diagnose';
    }

    isConnected = connected;
}

// ============== Interface Detection ==============
async function detectInterfaces() {
    try {
        const response = await fetch('/api/interface_mapping');
        const data = await response.json();
        
        if (data.interfaces) {
            updateInterfaceDisplay(data.interfaces, data.detection_status);
            window.interfacesDetected = true;
            
            // Also update channel config if available
            if (data.channel_config) {
                console.log('[Interfaces] Channel config from mapping:', data.channel_config);
                updateChannelConfigUI(data.channel_config);
            }
        }
    } catch (e) {
        console.error('[Interfaces] Detection error:', e);
    }
}

function updateChannelConfigUI(config) {
    /**
     * Update the channel and bandwidth dropdowns with the actual OpenWrt config
     */
    for (const [band, cfg] of Object.entries(config)) {
        const bandLower = band.toLowerCase();
        const channelSelect = document.getElementById('channel-' + bandLower);
        const bandwidthSelect = document.getElementById('bandwidth-' + bandLower);
        const channelLabel = document.getElementById('current-ch-' + bandLower);

        if (channelSelect && cfg.channel) {
            const channelValue = String(cfg.channel);
            let found = false;
            
            // Try to find and select the channel
            for (let option of channelSelect.options) {
                if (option.value === channelValue) {
                    channelSelect.value = channelValue;
                    found = true;
                    break;
                }
            }
            
            // If channel not in dropdown, add it
            if (!found) {
                const newOption = document.createElement('option');
                newOption.value = channelValue;
                newOption.textContent = 'CH ' + channelValue;
                channelSelect.appendChild(newOption);
                channelSelect.value = channelValue;
                console.log(`[Config] Added missing channel ${channelValue} for ${band}`);
            }
        }

        if (bandwidthSelect && cfg.bandwidth) {
            const bwValue = cfg.bandwidth;
            let found = false;
            
            for (let option of bandwidthSelect.options) {
                if (option.value === bwValue) {
                    bandwidthSelect.value = bwValue;
                    found = true;
                    break;
                }
            }
            
            // If bandwidth not in dropdown, add it
            if (!found) {
                const newOption = document.createElement('option');
                newOption.value = bwValue;
                newOption.textContent = bwValue;
                bandwidthSelect.appendChild(newOption);
                bandwidthSelect.value = bwValue;
                console.log(`[Config] Added missing bandwidth ${bwValue} for ${band}`);
            }
        }
        
        // Update the current channel display label if exists
        if (channelLabel) {
            channelLabel.textContent = `CH ${cfg.channel}`;
        }
    }
    
    console.log('[Config] UI updated with current config');
}

function updateInterfaceDisplay(interfaces, detectionStatus) {
    const mapping2G = document.getElementById('mapping2G');
    const mapping5G = document.getElementById('mapping5G');
    const mapping6G = document.getElementById('mapping6G');
    const badge = document.getElementById('detectionBadge');

    if (mapping2G) mapping2G.textContent = `2G=${interfaces['2G']}`;
    if (mapping5G) mapping5G.textContent = `5G=${interfaces['5G']}`;
    if (mapping6G) mapping6G.textContent = `6G=${interfaces['6G']}`;

    if (badge && detectionStatus) {
        badge.textContent = detectionStatus.detected ? '✓ Auto-detected' : 'Default';
        badge.style.background = detectionStatus.detected 
            ? 'rgba(34, 197, 94, 0.2)' 
            : 'rgba(148, 163, 184, 0.2)';
        badge.style.color = detectionStatus.detected 
            ? 'var(--accent-2g)' 
            : 'var(--text-secondary)';
    }

    // Update card interface labels
    const iface2g = document.getElementById('iface-2g');
    const iface5g = document.getElementById('iface-5g');
    const iface6g = document.getElementById('iface-6g');

    if (iface2g) iface2g.textContent = interfaces['2G'];
    if (iface5g) iface5g.textContent = interfaces['5G'];
    if (iface6g) iface6g.textContent = interfaces['6G'];
}

async function redetectInterfaces() {
    setLoading(true);
    try {
        const response = await fetch('/api/detect_interfaces', { method: 'POST' });
        const data = await response.json();

        if (data.success) {
            updateInterfaceDisplay(data.interfaces, data.detection_status);
            showNotification(data.message, 'success');
        } else {
            showNotification('Interface detection failed. Using default mapping.', 'error');
        }
    } catch (e) {
        showNotification('Detection error: ' + e.message, 'error');
    }
    setLoading(false);
}

// ============== Status Updates ==============
function updateStatusDisplay(data) {
    for (const [band, info] of Object.entries(data)) {
        const bandLower = band.toLowerCase();
        const statusEl = document.getElementById('status-' + bandLower);
        const durationEl = document.getElementById('duration-' + bandLower);
        const packetsEl = document.getElementById('packets-' + bandLower);

        if (statusEl) {
            statusEl.textContent = info.running ? 'CAPTURING' : 'IDLE';
            statusEl.className = 'status-badge ' + (info.running ? 'status-running' : 'status-idle');
        }
        if (durationEl) {
            durationEl.textContent = info.duration || '--:--';
        }
        if (packetsEl) {
            packetsEl.textContent = info.packets || 0;
        }

        // Update button states
        updateCaptureButtons(band, info.running);
    }
}

function updateCaptureButtons(band, running) {
    const bandLower = band.toLowerCase();
    const startBtn = document.querySelector(`.card-${bandLower} .btn-start`);
    const stopBtn = document.querySelector(`.card-${bandLower} .btn-stop`);

    if (startBtn) {
        startBtn.disabled = running;
        startBtn.classList.toggle('btn-disabled', running);
    }
    if (stopBtn) {
        stopBtn.disabled = !running;
        stopBtn.classList.toggle('btn-disabled', !running);
    }
}

// ============== Capture Controls ==============
async function startCapture(band) {
    setLoading(true);
    try {
        const response = await fetch('/api/start/' + band, { method: 'POST' });
        const data = await response.json();
        showNotification(data.message, data.success ? 'success' : 'error');
        if (data.success) {
            setTimeout(refreshStatus, 500);
        }
    } catch (e) {
        showNotification('Error: ' + e.message, 'error');
    }
    setLoading(false);
}

async function stopCapture(band) {
    setLoading(true);
    try {
        const response = await fetch('/api/stop/' + band, { method: 'POST' });
        const data = await response.json();
        showNotification(data.message, data.success ? 'success' : 'error');
        if (data.success) {
            setTimeout(refreshStatus, 500);
        }
    } catch (e) {
        showNotification('Error: ' + e.message, 'error');
    }
    setLoading(false);
}

async function startAll() {
    setLoading(true);
    try {
        const response = await fetch('/api/start_all', { method: 'POST' });
        const data = await response.json();
        showNotification('Started captures for: ' + Object.keys(data.results).join(', '), 'success');
        setTimeout(refreshStatus, 500);
    } catch (e) {
        showNotification('Error: ' + e.message, 'error');
    }
    setLoading(false);
}

async function stopAll() {
    setLoading(true);
    try {
        const response = await fetch('/api/stop_all', { method: 'POST' });
        const data = await response.json();
        let savedBands = [];
        let noFileBands = [];
        let errorBands = [];
        
        const resultEntries = Object.entries(data.results);
        
        // Check if SSH failed for all bands
        const allSshFailed = resultEntries.every(([band, r]) => 
            r.message && r.message.includes('SSH error'));
        
        if (allSshFailed && resultEntries.length > 0) {
            showNotification('SSH connection to router failed. Check connection.', 'error');
            setTimeout(refreshStatus, 500);
            setLoading(false);
            return;
        }
        
        for (const [band, result] of resultEntries) {
            if (result.success && result.path) {
                savedBands.push(band);
            } else if (result.message && result.message.includes('No capture file')) {
                noFileBands.push(band);
            } else {
                errorBands.push(band);
            }
        }
        
        if (savedBands.length > 0) {
            // At least some files downloaded
            let msg = 'Downloaded: ' + savedBands.join(', ');
            if (noFileBands.length > 0) {
                msg += ' | No files: ' + noFileBands.join(', ');
            }
            showNotification(msg, 'success');
        } else if (noFileBands.length === 3) {
            // All 3 bands checked but no files found
            showNotification('No capture files on router (captures may not have been started)', 'warning');
        } else if (noFileBands.length > 0) {
            showNotification('No capture files found on router', 'warning');
        } else if (errorBands.length > 0) {
            showNotification('Download failed for: ' + errorBands.join(', '), 'error');
        } else {
            showNotification('Operation completed', 'info');
        }
        setTimeout(refreshStatus, 500);
    } catch (e) {
        showNotification('Error: ' + e.message, 'error');
    }
    setLoading(false);
}

// ============== Configuration ==============
async function applyConfig(band) {
    const channel = document.getElementById('channel-' + band.toLowerCase()).value;
    const bandwidth = document.getElementById('bandwidth-' + band.toLowerCase()).value;

    setLoading(true);
    try {
        const response = await fetch('/api/config/' + band, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ channel: channel, bandwidth: bandwidth })
        });
        const data = await response.json();
        showNotification(data.message + ' (Click "Apply Config & Restart WiFi" to commit)', data.success ? 'success' : 'error');
    } catch (e) {
        showNotification('Error: ' + e.message, 'error');
    }
    setLoading(false);
}

async function applyAllConfig() {
    // Update all band configs from dropdowns
    for (const band of ['2G', '5G', '6G']) {
        const channel = document.getElementById('channel-' + band.toLowerCase()).value;
        const bandwidth = document.getElementById('bandwidth-' + band.toLowerCase()).value;

        await fetch('/api/config/' + band, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ channel: channel, bandwidth: bandwidth })
        });
    }

    // Show modal
    const modal = document.getElementById('configModal');
    const status = document.getElementById('configStatus');
    const spinner = document.getElementById('configSpinner');
    const complete = document.getElementById('configComplete');

    modal.style.display = 'flex';
    spinner.style.display = 'block';
    complete.style.display = 'none';
    status.innerHTML = '<div class="config-line info">Starting configuration...</div>';

    try {
        for (const band of ['2G', '5G', '6G']) {
            const ch = document.getElementById('channel-' + band.toLowerCase()).value;
            const bw = document.getElementById('bandwidth-' + band.toLowerCase()).value;
            status.innerHTML += `<div class="config-line">${band}: CH ${ch}, ${bw}</div>`;
        }

        status.innerHTML += '<div class="config-line info">Sending to OpenWrt...</div>';

        const response = await fetch('/api/apply_config', { method: 'POST' });
        const data = await response.json();

        if (data.messages) {
            for (const msg of data.messages) {
                const cssClass = msg.includes('failed') || msg.includes('Failed') ? 'error' :
                    msg.includes('ready') || msg.includes('success') || msg.includes('Saved') ? 'success' : 'info';
                status.innerHTML += `<div class="config-line ${cssClass}">${msg}</div>`;
            }
        }

        if (data.interface_status) {
            status.innerHTML += '<div class="config-line success">Interface Status:</div>';
            status.innerHTML += `<pre style="font-size: 0.75rem; color: var(--text-secondary); margin: 0.5rem 0;">${data.interface_status}</pre>`;
        }

        spinner.style.display = 'none';
        complete.style.display = 'block';

        if (data.success) {
            status.innerHTML += '<div class="config-line success">✓ All configurations applied successfully!</div>';
        } else {
            status.innerHTML += '<div class="config-line error">✗ Configuration failed. Check messages above.</div>';
        }

    } catch (e) {
        status.innerHTML += `<div class="config-line error">Error: ${e.message}</div>`;
        spinner.style.display = 'none';
        complete.style.display = 'block';
    }

    status.scrollTop = status.scrollHeight;
}

function closeConfigModal() {
    document.getElementById('configModal').style.display = 'none';
    refreshStatus();
}

// ============== Time Sync ==============
async function updateTimeDisplay() {
    try {
        const response = await fetch('/api/time_info');
        const data = await response.json();

        const pcTime = document.getElementById('pcTime');
        const openwrtTime = document.getElementById('openwrtTime');
        const badge = document.getElementById('timeOffsetBadge');

        if (pcTime) {
            pcTime.textContent = data.pc_time ? data.pc_time.split(' ')[1] : '--:--:--';
        }
        if (openwrtTime) {
            openwrtTime.textContent = data.openwrt_time ? data.openwrt_time.split(' ')[1] : '--:--:--';
        }

        if (badge && data.offset_seconds !== null) {
            const absOffset = Math.abs(data.offset_seconds);
            if (absOffset < 2) {
                badge.textContent = '✓ Synced';
                badge.style.background = 'rgba(34, 197, 94, 0.2)';
                badge.style.color = 'var(--accent-2g)';
            } else if (absOffset < 60) {
                badge.textContent = `${data.offset_seconds > 0 ? '+' : ''}${data.offset_seconds.toFixed(0)}s`;
                badge.style.background = 'rgba(245, 158, 11, 0.2)';
                badge.style.color = 'var(--accent-warning)';
            } else {
                const minutes = Math.round(absOffset / 60);
                badge.textContent = `${data.offset_seconds > 0 ? '+' : '-'}${minutes}m`;
                badge.style.background = 'rgba(239, 68, 68, 0.2)';
                badge.style.color = 'var(--accent-danger)';
            }
        }
    } catch (e) {
        console.error('[Time] Update failed:', e);
    }
}

async function manualSyncTime() {
    setLoading(true);
    try {
        const response = await fetch('/api/sync_time', { method: 'POST' });
        const data = await response.json();

        if (data.success) {
            showNotification('Time synchronized successfully!', 'success');
            updateTimeDisplay();
        } else {
            showNotification('Time sync failed: ' + data.message, 'error');
        }
    } catch (e) {
        showNotification('Time sync error: ' + e.message, 'error');
    }
    setLoading(false);
}

// ============== File Split ==============
async function loadFileSplitSettings() {
    try {
        const response = await fetch('/api/file_split');
        const data = await response.json();

        const checkbox = document.getElementById('fileSplitEnabled');
        const sizeSelect = document.getElementById('fileSplitSize');
        const sizeContainer = document.getElementById('fileSplitSizeContainer');
        const statusDiv = document.getElementById('fileSplitStatus');
        const splitNote = document.getElementById('splitFileNote');

        if (checkbox) checkbox.checked = data.enabled;
        if (sizeSelect) sizeSelect.value = data.size_mb;

        updateFileSplitUI(data.enabled, data.size_mb);
    } catch (e) {
        console.error('[FileSplit] Load error:', e);
    }
}

async function updateFileSplit() {
    const checkbox = document.getElementById('fileSplitEnabled');
    const sizeSelect = document.getElementById('fileSplitSize');

    const enabled = checkbox ? checkbox.checked : false;
    const size_mb = sizeSelect ? parseInt(sizeSelect.value) : 200;

    updateFileSplitUI(enabled, size_mb);

    try {
        const response = await fetch('/api/file_split', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled: enabled, size_mb: size_mb })
        });
        const data = await response.json();

        if (data.success) {
            showNotification(data.message, 'success');
        }
    } catch (e) {
        showNotification('Failed to update file split settings: ' + e.message, 'error');
    }
}

function updateFileSplitUI(enabled, size_mb) {
    const sizeContainer = document.getElementById('fileSplitSizeContainer');
    const statusDiv = document.getElementById('fileSplitStatus');
    const splitNote = document.getElementById('splitFileNote');

    if (sizeContainer) {
        sizeContainer.style.opacity = enabled ? '1' : '0.5';
    }

    if (statusDiv) {
        if (enabled) {
            statusDiv.innerHTML = `✂️ Split enabled: <strong>${size_mb} MB</strong> per file`;
            statusDiv.style.color = 'var(--accent-2g)';
        } else {
            statusDiv.innerHTML = '📁 Continuous capture (no split)';
            statusDiv.style.color = 'var(--text-secondary)';
        }
    }

    if (splitNote) {
        splitNote.style.display = enabled ? 'block' : 'none';
    }
}

// ============== WiFi Config ==============
async function loadCurrentWifiConfig() {
    try {
        const response = await fetch('/api/get_wifi_config');
        const data = await response.json();

        if (data.success && data.config) {
            console.log('[CONFIG] Loaded WiFi config from OpenWrt:', data.config);
            console.log('[CONFIG] UCI WiFi Map:', data.uci_wifi_map);
            
            // Use the common update function
            updateChannelConfigUI(data.config);

            showNotification('Loaded current WiFi configuration from OpenWrt', 'success');
        }
    } catch (e) {
        console.error('[CONFIG] Load error:', e);
    }
}

async function refreshWifiConfig() {
    /**
     * Force refresh WiFi config from OpenWrt
     */
    setLoading(true);
    try {
        const response = await fetch('/api/get_wifi_config');
        const data = await response.json();

        if (data.success && data.config) {
            updateChannelConfigUI(data.config);
            showNotification('WiFi configuration refreshed from OpenWrt', 'success');
        } else {
            showNotification('Failed to refresh WiFi config', 'error');
        }
    } catch (e) {
        showNotification('Error refreshing config: ' + e.message, 'error');
    }
    setLoading(false);
}

// ============== Diagnostics ==============
async function diagnoseConnection() {
    setLoading(true);
    try {
        const response = await fetch('/api/diagnose');
        const data = await response.json();

        let statusHtml = `
            <div style="background: var(--bg-dark); border-radius: 0.5rem; padding: 1rem; margin-bottom: 1rem; font-family: 'JetBrains Mono', monospace; font-size: 0.9rem;">
                <div style="margin-bottom: 0.5rem;"><strong>Host:</strong> ${data.host}:${data.port}</div>
                <div style="margin-bottom: 0.5rem;"><strong>User:</strong> ${data.user}</div>
                <div style="margin-bottom: 0.5rem;"><strong>Password Set:</strong> ${data.password_set ? '<span style="color: var(--accent-2g);">Yes</span>' : '<span style="color: var(--accent-danger);">No</span>'}</div>
                <div style="margin-bottom: 0.5rem;"><strong>SSH Keys Found:</strong> ${data.ssh_keys_found && data.ssh_keys_found.length > 0 ? '<span style="color: var(--accent-2g);">' + data.ssh_keys_found.join(', ') + '</span>' : '<span style="color: var(--text-secondary);">None</span>'}</div>
                <div style="margin-bottom: 0.5rem;"><strong>Ping Test:</strong> ${data.ping_test ? '<span style="color: var(--accent-2g);">✓ OK</span>' : '<span style="color: var(--accent-danger);">✗ Failed</span>'}</div>
                <div><strong>SSH Test:</strong> ${data.ssh_test ? '<span style="color: var(--accent-2g);">✓ OK</span>' : '<span style="color: var(--accent-danger);">✗ Failed</span>'}</div>
                ${data.error ? `<div style="margin-top: 0.75rem; padding-top: 0.75rem; border-top: 1px solid var(--border-color); color: var(--accent-danger);"><strong>Error:</strong> ${data.error}</div>` : ''}
            </div>
        `;

        let solutionHtml = '';
        if (!data.ssh_test && data.solution_text) {
            solutionHtml = `
                <div style="background: rgba(234, 179, 8, 0.1); border: 1px solid #eab308; border-radius: 0.5rem; padding: 1rem;">
                    <div style="font-weight: 600; color: #eab308; margin-bottom: 0.5rem;">💡 Solution</div>
                    <div style="color: var(--text-secondary); font-size: 0.9rem;">${data.solution_text}</div>
                </div>
            `;
        }

        showDiagnoseModal(statusHtml, solutionHtml, data.ssh_test);
    } catch (e) {
        alert('Diagnosis failed: ' + e.message);
    }
    setLoading(false);
}

function showDiagnoseModal(statusHtml, solutionHtml, isConnected) {
    const existingModal = document.getElementById('diagnoseModal');
    if (existingModal) existingModal.remove();

    const modal = document.createElement('div');
    modal.id = 'diagnoseModal';
    modal.style.cssText = 'position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.7); display: flex; justify-content: center; align-items: center; z-index: 9999;';
    modal.innerHTML = `
        <div style="background: var(--bg-card); border: 1px solid var(--border-color); border-radius: 1rem; padding: 1.5rem; max-width: 500px; width: 90%; max-height: 90vh; overflow-y: auto;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
                <h3 style="margin: 0; font-size: 1.25rem;">🔍 Connection Diagnosis</h3>
                <button onclick="closeDiagnoseModal()" style="background: none; border: none; color: var(--text-secondary); font-size: 1.5rem; cursor: pointer; padding: 0; line-height: 1;">&times;</button>
            </div>
            ${statusHtml}
            ${solutionHtml}
            <div style="display: flex; gap: 0.75rem; justify-content: flex-end; margin-top: 1rem;">
                <button onclick="closeDiagnoseModal()" style="padding: 0.75rem 1.5rem; background: var(--bg-dark); border: 1px solid var(--border-color); border-radius: 0.5rem; color: var(--text-primary); cursor: pointer;">OK</button>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
}

function closeDiagnoseModal() {
    const modal = document.getElementById('diagnoseModal');
    if (modal) modal.remove();
}

// ============== Utilities ==============
function showNotification(message, type = 'success') {
    const notif = document.getElementById('notification');
    const text = document.getElementById('notificationText');
    
    if (notif && text) {
        notif.className = 'notification ' + type;
        text.textContent = message;
        notif.style.display = 'flex';

        setTimeout(() => {
            notif.style.display = 'none';
        }, 4000);
    }
}

function setLoading(show) {
    const overlay = document.getElementById('loadingOverlay');
    if (overlay) {
        overlay.classList.toggle('active', show);
    }
}

async function refreshStatus() {
    try {
        const response = await fetch('/api/status');
        const data = await response.json();
        updateStatusDisplay(data);
    } catch (e) {
        console.error('[Status] Refresh error:', e);
    }
}

// ============== Initialization ==============
document.addEventListener('DOMContentLoaded', () => {
    console.log('[App] Initializing...');

    // Initialize WebSocket (or fallback to polling)
    initWebSocket();

    // Check connection status
    checkConnection();

    // Load initial data
    setTimeout(() => {
        loadCurrentWifiConfig();
        loadFileSplitSettings();
        updateTimeDisplay();
    }, 1000);

    // Periodic time update
    setInterval(updateTimeDisplay, 5000);

    console.log('[App] Initialized');
});

// Export functions for HTML onclick handlers
window.startCapture = startCapture;
window.stopCapture = stopCapture;
window.startAll = startAll;
window.stopAll = stopAll;
window.applyConfig = applyConfig;
window.applyAllConfig = applyAllConfig;
window.closeConfigModal = closeConfigModal;
window.refreshStatus = refreshStatus;
window.manualSyncTime = manualSyncTime;
window.updateFileSplit = updateFileSplit;
window.redetectInterfaces = redetectInterfaces;
window.diagnoseConnection = diagnoseConnection;
window.closeDiagnoseModal = closeDiagnoseModal;
window.loadCurrentWifiConfig = loadCurrentWifiConfig;
window.refreshWifiConfig = refreshWifiConfig;
