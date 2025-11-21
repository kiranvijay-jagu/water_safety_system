let autoRefreshInterval = null;
let mainChart = null;
let latestQualityData = null;
let isRealTimeActive = true;
let readingCounter = 0;
let lastAlertUpdate = 0;

document.addEventListener('DOMContentLoaded', () => {
    console.log('🌊 Dashboard initialized');
    
    setupEventListeners();
    initializeChart();
    startRealTimeUpdates();
    
    setTimeout(() => {
        loadHistory();
        loadGraphData();
    }, 500);
    
    updateStatusBanner('info', '🔄 Waiting for sensor data...');
});

// ===========================
// REAL-TIME UPDATE SYSTEM
// ===========================
function startRealTimeUpdates() {
    console.log('🔄 Starting real-time updates (every 1 second)');
    
    if (autoRefreshInterval) {
        clearInterval(autoRefreshInterval);
    }
    
    fetchLatestSensorData();
    
    autoRefreshInterval = setInterval(() => {
        if (isRealTimeActive) {
            fetchLatestSensorData();
        }
    }, 1000);
}

function stopRealTimeUpdates() {
    console.log('⏸️ Stopping real-time updates');
    isRealTimeActive = false;
    if (autoRefreshInterval) {
        clearInterval(autoRefreshInterval);
        autoRefreshInterval = null;
    }
}

function fetchLatestSensorData() {
    fetch('/api/get-latest-state')
        .then(response => response.json())
        .then(result => {
            if (result.status === 'success' && result.data) {
                updateAllSections(result.data);
            }
        })
        .catch(error => {
            console.error('Error fetching latest data:', error);
        });
}

function updateAllSections(data) {
    const countdown = data.countdown || {};
    const outOfRange = data.out_of_range || [];
    
    // Update sensor display every second (real-time)
    if (data.turbidity !== undefined) {
        updateSensorDisplay({
            turbidity: data.turbidity,
            tds: data.tds,
            ph: data.ph,
            temperature: data.temperature
        });
        
        readingCounter++;
    }
    
    // Display range status
    displayRangeStatus(outOfRange);
    
    // Update quality display if we have predictions
    if (data.quality && data.quality !== 'Analyzing') {
        updateQualityDisplay({
            quality: data.quality,
            confidence: 95.0
        });
        
        // Display disease risks if available
        if (data.disease_details && data.disease_details.length > 0) {
            updateAlertsEnhanced({
                diseases: data.diseases || [],
                disease_details: data.disease_details,
                risk_factors: data.out_of_range || []
            });
        }
        
        updateStatusBanner('success', `✅ ${data.quality} - Reading at ${data.time || 'unknown'}`);
    } else {
        const rangeStatus = checkRangeStatus(outOfRange);
        updateStatusBanner('info', `🔄 ${rangeStatus} - Reading at ${data.time || 'unknown'}`);
    }
    
    // Store for chat
    latestQualityData = {
        sensor_data: {
            turbidity: data.turbidity,
            tds: data.tds,
            ph: data.ph,
            temperature: data.temperature,
            time: data.time
        },
        prediction: { quality: data.quality || 'Analyzing', confidence: 95.0 },
        disease_risks: data.disease_details || [],
        health_risks: {
            diseases: data.diseases || [],
            risk_factors: data.out_of_range || []
        }
    };
}

function checkRangeStatus(outOfRange) {
    if (outOfRange.length === 0) {
        return '✅ ALL SENSORS GOOD';
    }
    const issues = outOfRange.map(item => item.parameter).join(', ');
    return `⚠️ OUT OF RANGE: ${issues}`;
}

function displayRangeStatus(outOfRange) {
    let container = document.getElementById('sensorStatusContainer');
    
    if (!container) {
        const sensorCard = document.querySelector('.sensor-card');
        if (sensorCard) {
            container = document.createElement('div');
            container.id = 'sensorStatusContainer';
            container.className = 'sensor-status-banner';
            sensorCard.appendChild(container);
        }
    }
    
    if (!container) return;
    
    if (outOfRange.length === 0) {
        container.innerHTML = '<div class="status-good">✅ All Parameters Within Safe Range</div>';
        container.className = 'sensor-status-banner status-good';
    } else {
        const paramList = outOfRange.map(item => item.parameter).join(', ');
        container.innerHTML = `<div class="status-warning">⚠️ Out of Range: ${paramList}</div>`;
        container.className = 'sensor-status-banner status-warning';
    }
}

// ===========================
// EVENT LISTENERS
// ===========================
function setupEventListeners() {
    const refreshBtn = document.getElementById('refreshBtn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', () => {
            console.log('Manual refresh clicked');
            fetchLatestSensorData();
            loadHistory();
            loadGraphData();
        });
    }
    
    const simulateBtn = document.getElementById('simulateBtn');
    if (simulateBtn) {
        simulateBtn.addEventListener('click', () => {
            console.log('Simulate button clicked');
            simulateReading();
        });
    }
    
    const viewFullHistoryBtn = document.getElementById('viewFullHistoryBtn');
    const closeHistoryModal = document.getElementById('closeHistoryModal');
    const historyModal = document.getElementById('historyModal');
    const exportHistoryBtn = document.getElementById('exportHistoryBtn');
    const clearHistoryBtnModal = document.getElementById('clearHistoryBtnModal');
    
    if (viewFullHistoryBtn) {
        viewFullHistoryBtn.addEventListener('click', openHistoryModal);
    }
    
    if (closeHistoryModal) {
        closeHistoryModal.addEventListener('click', closeHistoryModalFunc);
    }
    
    if (historyModal) {
        historyModal.addEventListener('click', (e) => {
            if (e.target === historyModal) {
                closeHistoryModalFunc();
            }
        });
    }
    
    if (exportHistoryBtn) {
        exportHistoryBtn.addEventListener('click', exportHistoryToCSV);
    }
    
    if (clearHistoryBtnModal) {
        clearHistoryBtnModal.addEventListener('click', clearHistoryFromModal);
    }
    
    const sendChatBtn = document.getElementById('sendChatBtn');
    const chatInput = document.getElementById('chatInput');
    
    if (sendChatBtn) {
        sendChatBtn.addEventListener('click', sendChatMessage);
    }
    
    if (chatInput) {
        chatInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                sendChatMessage();
            }
        });
    }
    
    const quickBtns = document.querySelectorAll('.quick-btn');
    quickBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const question = btn.getAttribute('data-question');
            document.getElementById('chatInput').value = question;
            sendChatMessage();
        });
    });
    
    const graphSelect = document.getElementById('graphSelect');
    if (graphSelect) {
        graphSelect.addEventListener('change', updateChart);
    }
}

// ===========================
// STATUS BANNER
// ===========================
function updateStatusBanner(type, message) {
    const banner = document.getElementById('statusBanner');
    const icon = document.getElementById('statusIcon');
    const text = document.getElementById('statusText');
    
    if (!banner || !icon || !text) return;
    
    const styles = {
        info: { icon: '🔵', color: '#2196f3' },
        success: { icon: '✅', color: '#4caf50' },
        warning: { icon: '⚠️', color: '#ff9800' },
        error: { icon: '🚨', color: '#f44336' }
    };
    
    const style = styles[type] || styles.info;
    icon.textContent = style.icon;
    text.textContent = message;
    banner.style.borderLeft = `5px solid ${style.color}`;
}

// ===========================
// UPDATE SENSOR DISPLAY
// ===========================
function updateSensorDisplay(data) {
    const phValue = document.getElementById('phValue');
    const tdsValue = document.getElementById('tdsValue');
    const turbidityValue = document.getElementById('turbidityValue');
    const tempValue = document.getElementById('tempValue');
    const lastUpdate = document.getElementById('lastUpdate');
    
    if (phValue) phValue.textContent = parseFloat(data.ph).toFixed(2);
    if (tdsValue) tdsValue.textContent = Math.round(parseFloat(data.tds));
    if (turbidityValue) turbidityValue.textContent = parseFloat(data.turbidity).toFixed(1);
    if (tempValue) tempValue.textContent = parseFloat(data.temperature).toFixed(1);
    
    if (lastUpdate) {
        const now = new Date().toLocaleTimeString();
        lastUpdate.textContent = now;
    }
}

// ===========================
// UPDATE QUALITY DISPLAY
// ===========================
function updateQualityDisplay(prediction) {
    const badge = document.getElementById('qualityBadge');
    const icon = document.getElementById('qualityIcon');
    const text = document.getElementById('qualityText');
    const confidenceFill = document.getElementById('confidenceFill');
    const confidenceValue = document.getElementById('confidenceValue');
    
    if (!badge || !icon || !text) return;
    
    badge.classList.remove('safe', 'moderate', 'unsafe');
    
    const qualityMap = {
        'LOW RISK': { class: 'safe', icon: '✅', color: '#4caf50' },
        'MEDIUM RISK ⚠️': { class: 'moderate', icon: '⚠️', color: '#ff9800' },
        'HIGH RISK 🚨': { class: 'unsafe', icon: '🚨', color: '#f44336' }
    };
    
    const config = qualityMap[prediction.quality] || qualityMap['LOW RISK'];
    
    badge.classList.add(config.class);
    icon.textContent = config.icon;
    text.textContent = prediction.quality;
    
    if (confidenceFill && confidenceValue) {
        confidenceFill.style.width = `${prediction.confidence}%`;
        confidenceValue.textContent = `${prediction.confidence}%`;
    }
}

// ===========================
// UPDATE ALERTS - ENHANCED
// ===========================
function updateAlertsEnhanced(data) {
    const container = document.getElementById('alertsContainer');
    if (!container) return;
    
    container.innerHTML = '';
    
    const diseaseDetails = data.disease_details || [];
    
    if (diseaseDetails.length === 0) {
        container.innerHTML = `
            <div class="no-alerts">
                <span class="alert-icon">✅</span>
                <p>No health risks detected</p>
            </div>
        `;
        return;
    }
    
    const sortedDiseases = diseaseDetails.sort((a, b) => {
        const levelOrder = { 'high': 3, 'medium': 2, 'low': 1 };
        return levelOrder[b.level] - levelOrder[a.level];
    });
    
    sortedDiseases.forEach(disease => {
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert-item ${disease.level}-risk`;
        
        const icon = disease.level === 'high' ? '🚨' : disease.level === 'medium' ? '⚠️' : '✅';
        const actionText = getActionText(disease.level);
        
        alertDiv.innerHTML = `
            <div class="alert-header">
                <div class="alert-disease-name">
                    <span class="alert-icon-large">${icon}</span>
                    <span><strong>${disease.name}</strong></span>
                </div>
                <span class="alert-risk-badge ${disease.level}">${disease.level.toUpperCase()} (${disease.risk_percent}%)</span>
            </div>
            <div class="alert-status">
                <span>${disease.status}</span>
            </div>
        `;
        
        container.appendChild(alertDiv);
    });
    
    const updateInfo = document.createElement('div');
    updateInfo.className = 'alert-update-info';
    updateInfo.textContent = `📊 Updated in real-time | Last update: ${new Date().toLocaleTimeString()}`;
    container.appendChild(updateInfo);
}

function getActionText(level) {
    if (level === 'high') {
        return '🚫 DO NOT DRINK this water';
    } else if (level === 'medium') {
        return '⚠️ Boil water before use';
    }
    return '✅ Safe to drink';
}

// ===========================
// SIMULATE READING
// ===========================
function simulateReading() {
    console.log('📊 Simulating reading...');
    updateStatusBanner('info', '🔄 Generating simulated data...');
    
    fetch('/api/simulate')
        .then(response => response.json())
        .then(result => {
            if (result.status === 'success') {
                const sensorData = result.data;
                analyzeSensorData(sensorData);
            }
        })
        .catch(error => {
            console.error('Error simulating:', error);
            updateStatusBanner('error', '❌ Error simulating data');
        });
}

function analyzeSensorData(sensorData) {
    const payload = {
        turbidity: sensorData.turbidity,
        tds: sensorData.tds,
        ph: sensorData.ph,
        temperature: sensorData.temperature,
        mode: 'offline'
    };
    
    fetch('/api/sensor-data', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
    })
    .then(response => response.json())
    .then(result => {
        if (result.status === 'success') {
            latestQualityData = result;
            updateSensorDisplay(result.sensor_data);
            updateQualityDisplay(result.prediction);
            
            updateAlertsEnhanced({
                diseases: result.health_risks.diseases,
                disease_details: result.disease_risks,
                risk_factors: result.health_risks.risk_factors
            });
            
            loadHistory();
            loadGraphData();
            
            const quality = result.prediction.quality;
            if (quality.includes('LOW')) {
                updateStatusBanner('success', '✅ Water is SAFE');
            } else if (quality.includes('MEDIUM')) {
                updateStatusBanner('warning', '⚠️ MEDIUM RISK - Caution advised');
            } else {
                updateStatusBanner('error', '🚨 HIGH RISK - Do not consume!');
            }
        }
    })
    .catch(error => {
        console.error('Error analyzing:', error);
    });
}

// ===========================
// LOAD HISTORY - MINI VIEW
// ===========================
function loadHistory() {
    console.log('📊 Loading history...');
    
    fetch('/api/history')
        .then(response => {
            console.log('History response status:', response.status);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(result => {
            console.log('History data received:', result);
            
            if (result.status === 'success') {
                displayHistoryMini(result.data);
            } else if (result.status === 'error') {
                console.error('History API returned error:', result.message);
                const tbody = document.getElementById('historyTableBodyMini');
                if (tbody) {
                    tbody.innerHTML = `<tr><td colspan="6" class="no-data">Error: ${result.message}</td></tr>`;
                }
            }
        })
        .catch(error => {
            console.error('Error loading history:', error);
            const tbody = document.getElementById('historyTableBodyMini');
            if (tbody) {
                tbody.innerHTML = `<tr><td colspan="6" class="no-data">Error loading history: ${error.message}</td></tr>`;
            }
        });
}

function displayHistoryMini(data) {
    const tbody = document.getElementById('historyTableBodyMini');
    if (!tbody) {
        console.error('historyTableBodyMini element not found');
        return;
    }
    
    tbody.innerHTML = '';
    
    if (!data || data.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="no-data">No readings yet - waiting for sensor data...</td></tr>';
        return;
    }
    
    const recentData = data.slice(-5).reverse();
    
    recentData.forEach(row => {
        const tr = document.createElement('tr');
        
        const qualityClass = row.quality.includes('HIGH') ? 'quality-unsafe' : 
                            row.quality.includes('MEDIUM') ? 'quality-moderate' : 'quality-safe';
        
        tr.innerHTML = `
            <td>${row.timestamp}</td>
            <td>${parseFloat(row.ph).toFixed(2)}</td>
            <td>${Math.round(row.tds)}</td>
            <td>${parseFloat(row.turbidity).toFixed(1)}</td>
            <td>${parseFloat(row.temperature).toFixed(1)}</td>
            <td class="${qualityClass}">${row.quality}</td>
        `;
        tbody.appendChild(tr);
    });
    
    console.log(`Displayed ${recentData.length} recent readings`);
}

// ===========================
// FULL HISTORY MODAL FUNCTIONS
// ===========================
function openHistoryModal() {
    const modal = document.getElementById('historyModal');
    if (modal) {
        modal.classList.add('active');
        loadFullHistory();
    }
}

function closeHistoryModalFunc() {
    const modal = document.getElementById('historyModal');
    if (modal) {
        modal.classList.remove('active');
    }
}

function loadFullHistory() {
    fetch('/api/history')
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(result => {
            console.log('Full history data received:', result);
            if (result.status === 'success') {
                displayFullHistory(result.data);
                updateHistoryStats(result.data);
            }
        })
        .catch(error => {
            console.error('Error loading full history:', error);
            const tbody = document.getElementById('historyTableBodyFull');
            if (tbody) {
                tbody.innerHTML = '<tr><td colspan="8" class="no-data">Error loading history</td></tr>';
            }
        });
}

function displayFullHistory(data) {
    const tbody = document.getElementById('historyTableBodyFull');
    if (!tbody) {
        console.error('historyTableBodyFull element not found');
        return;
    }
    
    tbody.innerHTML = '';
    
    if (!data || data.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="no-data">No readings available</td></tr>';
        return;
    }
    
    data.slice().reverse().forEach((row, index) => {
        const tr = document.createElement('tr');
        
        const qualityClass = row.quality.includes('HIGH') ? 'quality-unsafe' : 
                            row.quality.includes('MEDIUM') ? 'quality-moderate' : 'quality-safe';
        
        tr.innerHTML = `
            <td>${data.length - index}</td>
            <td>${row.timestamp}</td>
            <td>${parseFloat(row.ph).toFixed(2)}</td>
            <td>${Math.round(row.tds)}</td>
            <td>${parseFloat(row.turbidity).toFixed(1)}</td>
            <td>${parseFloat(row.temperature).toFixed(1)}</td>
            <td class="${qualityClass}">${row.quality}</td>
            <td>${row.diseases || 'None'}</td>
        `;
        tbody.appendChild(tr);
    });
    
    console.log(`Displayed ${data.length} total readings`);
}

function updateHistoryStats(data) {
    const totalReadings = document.getElementById('totalReadings');
    const dateRange = document.getElementById('dateRange');
    
    if (totalReadings) {
        totalReadings.textContent = `Total Readings: ${data.length}`;
    }
    
    if (dateRange && data.length > 0) {
        const firstDate = new Date(data[0].timestamp).toLocaleDateString();
        const lastDate = new Date(data[data.length - 1].timestamp).toLocaleDateString();
        dateRange.textContent = `Date Range: ${firstDate} - ${lastDate}`;
    }
}

// ===========================
// EXPORT HISTORY
// ===========================
function exportHistoryToCSV() {
    console.log('Export CSV button clicked');
    
    fetch('/api/history')
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(result => {
            console.log('Export data received:', result);
            
            if (result.status === 'success' && result.data && result.data.length > 0) {
                const data = result.data;
                
                let csv = 'Timestamp,pH,TDS (ppm),Turbidity (NTU),Temperature (°C),Quality,Disease Risks\n';
                
                data.forEach(row => {
                    const diseases = (row.diseases || 'None').replace(/"/g, '""');
                    csv += `"${row.timestamp}",${row.ph},${row.tds},${row.turbidity},${row.temperature},"${row.quality}","${diseases}"\n`;
                });
                
                const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `water_quality_history_${new Date().toISOString().split('T')[0]}.csv`;
                document.body.appendChild(a);
                a.click();
                
                setTimeout(() => {
                    document.body.removeChild(a);
                    window.URL.revokeObjectURL(url);
                }, 100);
                
                alert('CSV exported successfully');
                console.log('CSV export completed');
            } else {
                alert('No data to export');
                console.log('No data available for export');
            }
        })
        .catch(error => {
            console.error('Error exporting history:', error);
            alert('Error exporting history: ' + error.message);
        });
}

// ===========================
// CLEAR HISTORY
// ===========================
function clearHistoryFromModal() {
    console.log('Clear history button clicked');
    
    if (confirm('Are you sure you want to clear ALL history? This cannot be undone!')) {
        console.log('User confirmed clear history');
        
        fetch('/api/clear-history', { 
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(result => {
            console.log('Clear history result:', result);
            
            if (result.status === 'success') {
                loadFullHistory();
                loadHistory();
                updateStatusBanner('info', 'History cleared successfully');
                alert('History cleared successfully!');
                console.log('History cleared and displays refreshed');
            } else {
                throw new Error(result.message || 'Unknown error');
            }
        })
        .catch(error => {
            console.error('Error clearing history:', error);
            alert('Error clearing history: ' + error.message);
        });
    } else {
        console.log('User cancelled clear history');
    }
}

function clearHistory() {
    clearHistoryFromModal();
}

// ===========================
// CHAT FUNCTIONALITY
// ===========================
function sendChatMessage() {
    const chatInput = document.getElementById('chatInput');
    const question = chatInput.value.trim();
    
    if (!question) return;
    
    addChatMessage(question, 'user');
    chatInput.value = '';
    
    showTypingIndicator();
    
    fetch('/api/chat', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            question: question,
            quality_data: latestQualityData
        })
    })
    .then(response => response.json())
    .then(result => {
        removeTypingIndicator();
        
        if (result.status === 'success') {
            addChatMessage(result.answer, 'bot');
        } else {
            addChatMessage('Sorry, an error occurred.', 'bot');
        }
    })
    .catch(error => {
        removeTypingIndicator();
        console.error('Chat error:', error);
        addChatMessage('Could not process your question.', 'bot');
    });
}

function addChatMessage(message, sender) {
    const chatMessages = document.getElementById('chatMessages');
    if (!chatMessages) return;
    
    const messageDiv = document.createElement('div');
    messageDiv.className = sender === 'user' ? 'user-message' : 'bot-message';
    
    const icon = sender === 'user' ? '👤' : '🤖';
    
    messageDiv.innerHTML = `
        <span class="message-icon">${icon}</span>
        <div class="message-content">${message}</div>
    `;
    
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function showTypingIndicator() {
    const chatMessages = document.getElementById('chatMessages');
    if (!chatMessages) return;
    
    const typingDiv = document.createElement('div');
    typingDiv.className = 'bot-message typing-indicator';
    typingDiv.id = 'typingIndicator';
    typingDiv.innerHTML = `
        <span class="message-icon">🤖</span>
        <div class="message-content">
            <span class="dot"></span>
            <span class="dot"></span>
            <span class="dot"></span>
        </div>
    `;
    chatMessages.appendChild(typingDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function removeTypingIndicator() {
    const indicator = document.getElementById('typingIndicator');
    if (indicator) {
        indicator.remove();
    }
}

// ===========================
// CHART FUNCTIONALITY
// ===========================
function initializeChart() {
    const canvas = document.getElementById('mainChart');
    if (!canvas) {
        console.error('Chart canvas not found');
        return;
    }
    
    const ctx = canvas.getContext('2d');
    
    mainChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'pH Level',
                    data: [],
                    borderColor: '#0077be',
                    backgroundColor: 'rgba(0, 119, 190, 0.1)',
                    tension: 0.4,
                    fill: true
                },
                {
                    label: 'TDS (ppm)',
                    data: [],
                    borderColor: '#00bcd4',
                    backgroundColor: 'rgba(0, 188, 212, 0.1)',
                    tension: 0.4,
                    fill: true,
                    hidden: true
                },
                {
                    label: 'Turbidity (NTU)',
                    data: [],
                    borderColor: '#ff9800',
                    backgroundColor: 'rgba(255, 152, 0, 0.1)',
                    tension: 0.4,
                    fill: true,
                    hidden: true
                },
                {
                    label: 'Temperature (°C)',
                    data: [],
                    borderColor: '#4caf50',
                    backgroundColor: 'rgba(76, 175, 80, 0.1)',
                    tension: 0.4,
                    fill: true,
                    hidden: true
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: true,
                    position: 'top'
                }
            },
            scales: {
                y: {
                    beginAtZero: true
                }
            }
        }
    });
    
    console.log('Chart initialized');
}

function loadGraphData() {
    fetch('/api/graph-data')
        .then(response => response.json())
        .then(result => {
            if (result.status === 'success' && result.data.timestamps && result.data.timestamps.length > 0) {
                const data = result.data;
                
                mainChart.data.labels = data.timestamps.map(t => {
                    const date = new Date(t);
                    return date.toLocaleTimeString();
                });
                
                mainChart.data.datasets[0].data = data.ph;
                mainChart.data.datasets[1].data = data.tds;
                mainChart.data.datasets[2].data = data.turbidity;
                mainChart.data.datasets[3].data = data.temperature;
                
                mainChart.update('none');
            }
        })
        .catch(error => {
            console.error('Error loading graph:', error);
        });
}

function updateChart() {
    const selector = document.getElementById('graphSelect');
    if (!selector) return;
    
    const value = selector.value;
    
    mainChart.data.datasets.forEach(dataset => {
        dataset.hidden = true;
    });
    
    if (value === 'all') {
        mainChart.data.datasets.forEach(dataset => {
            dataset.hidden = false;
        });
    } else if (value === 'ph') {
        mainChart.data.datasets[0].hidden = false;
    } else if (value === 'tds') {
        mainChart.data.datasets[1].hidden = false;
    } else if (value === 'turbidity') {
        mainChart.data.datasets[2].hidden = false;
    } else if (value === 'temperature') {
        mainChart.data.datasets[3].hidden = false;
    }
    
    mainChart.update();
}