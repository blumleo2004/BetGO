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
    // The new design simplified the filters, so we mainly check if elements exist before populating
    const sportsFilter = document.getElementById('sports-filter');
    const bookmakersFilter = document.getElementById('bookmakers-filter');

    if (sportsFilter && config.sports) {
        sportsFilter.innerHTML = Object.entries(config.sports).map(([key, name]) => `
            <label class="checkbox">
                <input type="checkbox" value="${key}" checked>
                <span>${name}</span>
            </label>
        `).join('');
    }

    if (bookmakersFilter && config.bookmakers) {
        bookmakersFilter.innerHTML = Object.entries(config.bookmakers).map(([key, data]) => `
            <label class="checkbox">
                <input type="checkbox" value="${key}" checked>
                <span>${data.name}</span>
            </label>
        `).join('');
    }
}

function getFilters() {
    const sportsFilter = document.getElementById('sports-filter');
    const bookmakersFilter = document.getElementById('bookmakers-filter');

    // Get selected sports if filter exists
    let sports = '';
    if (sportsFilter) {
        sports = Array.from(sportsFilter.querySelectorAll('input:checked')).map(el => el.value).join(',');
    }

    // Get selected bookmakers if filter exists
    let bookmakers = '';
    if (bookmakersFilter) {
        bookmakers = Array.from(bookmakersFilter.querySelectorAll('input:checked')).map(el => el.value).join(',');
    }

    return {
        sports: sports,
        markets: 'h2h,spreads,totals',
        bookmakers: bookmakers,
        min_roi: document.getElementById('filter-roi')?.value || '0.5',
        investment: document.getElementById('filter-investment')?.value || '500',
        hours: document.getElementById('filter-timeframe')?.value || ''
    };
}

function renderOpportunities() {
    if (opportunities.length === 0) {
        opportunitiesBody.innerHTML = '';
        emptyState.style.display = 'flex';
        return;
    }

    emptyState.style.display = 'none';

    opportunitiesBody.innerHTML = opportunities.map((opp, index) => {
        const eventTime = new Date(opp.commence_time);
        const now = new Date();
        const hoursUntil = Math.round((eventTime - now) / (1000 * 60 * 60));
        const timeDisplay = hoursUntil < 1 ? 'Soon' : `${hoursUntil}h`;

        // Get bookmaker names from stakes
        const bookmakers = Object.values(opp.stakes).map(s => s.book).join(' vs ');

        return `
            <div class="bg-white p-5 rounded-2xl border border-slate-50 card-shadow flex items-center justify-between group hover:border-growth transition-all cursor-pointer" onclick="placeVirtualBet(${index})">
                <div class="flex items-center gap-4">
                    <div class="size-12 rounded-xl bg-slate-50 flex items-center justify-center text-slate-900 text-2xl">
                        ${getSportEmoji(opp.sport)}
                    </div>
                    <div>
                        <h3 class="font-bold text-slate-900">${opp.home_team} vs ${opp.away_team}</h3>
                        <p class="text-xs text-slate-400 font-medium">${bookmakers}</p>
                    </div>
                </div>
                <div class="text-right">
                    <p class="font-bold text-growth">+€${opp.profit.toFixed(2)} (${opp.roi.toFixed(2)}%)</p>
                    <p class="text-[10px] text-slate-400 font-medium uppercase">${timeDisplay}</p>
                </div>
            </div>
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
        opportunitiesBody.style.display = 'none';
    } else {
        loadingState.style.display = 'none';
        opportunitiesBody.style.display = 'block';
    }
}

function resetFilters() {
    // Reset inputs to their default values
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
