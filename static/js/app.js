/**
 * BETGO - Arbitrage Dashboard
 * Frontend JavaScript for interactive scanning and filtering
 */

// State
let config = {};
let opportunities = [];
let isScanning = false;
let autoRefreshInterval = null;

// DOM Elements
const scanBtn = document.getElementById('scan-btn');
const creditsRemaining = document.getElementById('credits-remaining');
const creditsTotal = document.getElementById('credits-total');
const opportunitiesBody = document.getElementById('opportunities-body');
const emptyState = document.getElementById('empty-state');
const loadingState = document.getElementById('loading-state');
const totalOpportunities = document.getElementById('total-opportunities');
const bestRoi = document.getElementById('best-roi');
const totalProfit = document.getElementById('total-profit');
const lastScan = document.getElementById('last-scan');
const sportsFilter = document.getElementById('sports-filter');
const bookmakersFilter = document.getElementById('bookmakers-filter');
const autoRefreshCheckbox = document.getElementById('auto-refresh');
const resetFiltersBtn = document.getElementById('reset-filters');
const toastContainer = document.getElementById('toast-container');

// Initialize
document.addEventListener('DOMContentLoaded', init);

async function init() {
    await loadConfig();
    populateFilters();
    setupEventListeners();

    // Initial scan
    await scanForArbitrage();
}

async function loadConfig() {
    try {
        const response = await fetch('/api/config');
        config = await response.json();
    } catch (error) {
        console.error('Failed to load config:', error);
        showToast('Failed to load configuration', 'error');
    }
}

function populateFilters() {
    // Populate sports filter
    if (config.sports) {
        sportsFilter.innerHTML = Object.entries(config.sports).map(([key, name]) => `
            <label class="checkbox">
                <input type="checkbox" value="${key}" checked>
                <span>${name}</span>
            </label>
        `).join('');
    }

    // Populate bookmakers filter
    if (config.bookmakers) {
        bookmakersFilter.innerHTML = Object.entries(config.bookmakers).map(([key, data]) => `
            <label class="checkbox">
                <input type="checkbox" value="${key}" checked>
                <span style="display: flex; align-items: center; gap: 0.5rem;">
                    <span class="book-dot" style="background: ${data.color}"></span>
                    ${data.name}
                </span>
            </label>
        `).join('');
    }
}

function setupEventListeners() {
    // Scan button
    scanBtn.addEventListener('click', scanForArbitrage);

    // Auto-refresh toggle
    autoRefreshCheckbox.addEventListener('change', toggleAutoRefresh);

    // Reset filters
    resetFiltersBtn.addEventListener('click', resetFilters);

    // Filter changes trigger scan
    document.querySelectorAll('.filter-group input, .filter-group select').forEach(el => {
        el.addEventListener('change', () => {
            if (autoRefreshInterval) {
                scanForArbitrage();
            }
        });
    });
}

function getFilters() {
    // Get selected sports
    const sports = Array.from(sportsFilter.querySelectorAll('input:checked'))
        .map(el => el.value);

    // Get selected markets
    const markets = Array.from(document.querySelectorAll('.filter-group .checkbox-group input[value="h2h"], .filter-group .checkbox-group input[value="spreads"], .filter-group .checkbox-group input[value="totals"]'))
        .filter(el => el.checked)
        .map(el => el.value);

    // Get selected bookmakers
    const bookmakers = Array.from(bookmakersFilter.querySelectorAll('input:checked'))
        .map(el => el.value);

    return {
        sports: sports.length ? sports.join(',') : '',
        markets: markets.length ? markets.join(',') : 'h2h,spreads,totals',
        bookmakers: bookmakers.length ? bookmakers.join(',') : '',
        min_roi: document.getElementById('filter-roi').value || '0.5',
        investment: document.getElementById('filter-investment').value || '500',
        hours: document.getElementById('filter-timeframe').value || ''
    };
}

async function scanForArbitrage() {
    if (isScanning) return;

    isScanning = true;
    scanBtn.disabled = true;
    scanBtn.innerHTML = '<span class="btn-icon">⏳</span><span>Scanning...</span>';

    showLoading(true);

    try {
        const filters = getFilters();
        const params = new URLSearchParams(filters);

        const response = await fetch(`/api/scan?${params}`);
        const data = await response.json();

        opportunities = data.opportunities || [];
        updateApiCredits(data.api_usage);
        renderOpportunities();
        updateStats();

        lastScan.textContent = new Date().toLocaleTimeString();

        if (opportunities.length > 0) {
            showToast(`Found ${opportunities.length} arbitrage opportunities!`, 'success');
            playNotificationSound();
        }
    } catch (error) {
        console.error('Scan failed:', error);
        showToast('Failed to scan for opportunities', 'error');
    } finally {
        isScanning = false;
        scanBtn.disabled = false;
        scanBtn.innerHTML = '<span class="btn-icon">🔍</span><span>Scan Now</span>';
        showLoading(false);
    }
}

function updateApiCredits(usage) {
    if (usage) {
        creditsRemaining.textContent = usage.remaining !== null ? usage.remaining : '--';
        // The Odds API typically has 500 requests/month for free tier
        creditsTotal.textContent = usage.remaining !== null ? (usage.remaining + (usage.used || 0)) : '--';
    }
}

function renderOpportunities() {
    if (opportunities.length === 0) {
        opportunitiesBody.innerHTML = '';
        emptyState.style.display = 'flex';
        document.querySelector('.opportunities-table').style.display = 'none';
        return;
    }

    emptyState.style.display = 'none';
    document.querySelector('.opportunities-table').style.display = 'table';

    opportunitiesBody.innerHTML = opportunities.map(opp => {
        const eventTime = new Date(opp.commence_time);
        const now = new Date();
        const hoursUntil = Math.round((eventTime - now) / (1000 * 60 * 60));
        const timeDisplay = hoursUntil < 1 ? 'Soon' : `${hoursUntil}h`;

        // Build bets HTML
        const betsHtml = Object.entries(opp.stakes).map(([outcome, data]) => {
            const bookInfo = config.bookmakers?.[data.book_key] || {};
            const bookUrl = bookInfo.url || '#';
            const bookColor = bookInfo.color || '#666';

            return `
                <div class="bet-item" style="border-left-color: ${bookColor}">
                    <div class="bet-header">
                        <span class="bet-outcome">${outcome}</span>
                        <span class="bet-odds">${data.odds}</span>
                    </div>
                    <div class="bet-details">
                        <span class="bet-stake">Stake: €${data.stake}</span>
                        <a href="${bookUrl}" target="_blank" class="bet-book" title="Open ${data.book}">
                            <span class="book-dot" style="background: ${bookColor}"></span>
                            ${data.book}
                        </a>
                    </div>
                </div>
            `;
        }).join('');

        const roiClass = opp.roi >= 2 ? 'high' : '';
        const marketLabel = opp.market === 'h2h' ? 'Moneyline' :
            opp.market === 'spreads' ? 'Spread' : 'Total';
        const marketExtra = opp.line ? ` (${opp.line})` : '';

        // Store opportunity data for placing bets
        const oppIndex = opportunities.indexOf(opp);

        return `
            <tr>
                <td>
                    <div class="event-cell">
                        <span class="event-teams">${opp.home_team} vs ${opp.away_team}</span>
                        <span class="event-league">${opp.sport_title}</span>
                    </div>
                </td>
                <td>
                    <span class="sport-badge">${getSportEmoji(opp.sport)} ${opp.sport_title}</span>
                </td>
                <td>
                    <div class="time-cell">
                        <span class="time-date">${eventTime.toLocaleDateString()}</span>
                        <span class="time-relative">${timeDisplay}</span>
                    </div>
                </td>
                <td>${marketLabel}${marketExtra}</td>
                <td><span class="roi-badge ${roiClass}">${opp.roi}%</span></td>
                <td class="profit-cell">€${opp.profit}</td>
                <td>
                    <div class="bets-cell">${betsHtml}</div>
                    <button class="place-bet-btn" onclick="placeVirtualBet(${oppIndex})" style="margin-top: 0.5rem; width: 100%; padding: 0.5rem; background: linear-gradient(135deg, #f59e0b, #d97706); border: none; border-radius: 6px; color: #000; font-weight: 600; cursor: pointer;">
                        🎮 Place Virtual Bet
                    </button>
                </td>
            </tr>
        `;
    }).join('');
}

function getSportEmoji(sport) {
    const emojis = {
        'soccer': '⚽',
        'basketball': '🏀',
        'tennis': '🎾',
        'americanfootball': '🏈',
        'icehockey': '🏒',
        'baseball': '⚾',
        'mma': '🥊',
        'boxing': '🥊',
        'golf': '⛳',
        'rugby': '🏉',
        'cricket': '🏏',
        'handball': '🤾',
        'volleyball': '🏐'
    };

    for (const [key, emoji] of Object.entries(emojis)) {
        if (sport.toLowerCase().includes(key)) return emoji;
    }
    return '🎯';
}

function updateStats() {
    totalOpportunities.textContent = opportunities.length;

    if (opportunities.length > 0) {
        const best = Math.max(...opportunities.map(o => o.roi));
        bestRoi.textContent = `${best}%`;

        const totalProfitValue = opportunities.reduce((sum, o) => sum + o.profit, 0);
        totalProfit.textContent = `€${totalProfitValue.toFixed(2)}`;
    } else {
        bestRoi.textContent = '0%';
        totalProfit.textContent = '€0';
    }
}

function showLoading(show) {
    if (show) {
        loadingState.style.display = 'flex';
        emptyState.style.display = 'none';
        document.querySelector('.opportunities-table').style.display = 'none';
    } else {
        loadingState.style.display = 'none';
    }
}

function toggleAutoRefresh() {
    if (autoRefreshCheckbox.checked) {
        autoRefreshInterval = setInterval(scanForArbitrage, 60000);
        showToast('Auto-refresh enabled (60s)', 'success');
    } else {
        clearInterval(autoRefreshInterval);
        autoRefreshInterval = null;
        showToast('Auto-refresh disabled', 'warning');
    }
}

function resetFilters() {
    // Reset all checkboxes to checked
    document.querySelectorAll('.filter-group .checkbox input').forEach(el => {
        el.checked = true;
    });

    // Reset selects
    document.getElementById('filter-roi').value = '0.5';
    document.getElementById('filter-timeframe').value = '24';
    document.getElementById('filter-investment').value = '500';

    showToast('Filters reset', 'success');
}

function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <span>${type === 'success' ? '✅' : type === 'error' ? '❌' : '⚠️'}</span>
        <span>${message}</span>
    `;

    toastContainer.appendChild(toast);

    setTimeout(() => {
        toast.style.animation = 'slideIn 0.3s ease-out reverse';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

function playNotificationSound() {
    // Simple notification beep using Web Audio API
    try {
        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        const oscillator = audioContext.createOscillator();
        const gainNode = audioContext.createGain();

        oscillator.connect(gainNode);
        gainNode.connect(audioContext.destination);

        oscillator.frequency.value = 800;
        oscillator.type = 'sine';
        gainNode.gain.value = 0.1;

        oscillator.start();
        oscillator.stop(audioContext.currentTime + 0.15);
    } catch (e) {
        // Audio not supported, fail silently
    }
}

function closeModal() {
    document.getElementById('bookmaker-modal').style.display = 'none';
}

// Keyboard shortcuts
document.addEventListener('keydown', (e) => {
    // Ctrl/Cmd + R to refresh
    if ((e.ctrlKey || e.metaKey) && e.key === 'r') {
        e.preventDefault();
        scanForArbitrage();
    }

    // Escape to close modal
    if (e.key === 'Escape') {
        closeModal();
    }
});

// Place virtual bet for simulation
async function placeVirtualBet(oppIndex) {
    const opp = opportunities[oppIndex];
    if (!opp) {
        showToast('Opportunity not found', 'error');
        return;
    }

    try {
        const response = await fetch('/api/simulation/place', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(opp)
        });

        const result = await response.json();

        if (result.success) {
            showToast(`🎮 ${result.message}`, 'success');
            playNotificationSound();
        } else {
            showToast(`❌ ${result.error}`, 'error');
        }
    } catch (error) {
        console.error('Failed to place virtual bet:', error);
        showToast('Failed to place virtual bet', 'error');
    }
}
