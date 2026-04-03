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



function setupEventListeners() {
    const scanBtn = document.getElementById('scan-btn');
    if (scanBtn) {
        scanBtn.addEventListener('click', scanForArbitrage);
    }


    const resetFiltersBtn = document.getElementById('reset-filters');
    if (resetFiltersBtn) {
        resetFiltersBtn.addEventListener('click', resetFilters);
    }

    // Mobile Filter Toggle
    const toggleFiltersBtn = document.getElementById('toggle-filters');
    const filtersContent = document.getElementById('filters-content');
    if (toggleFiltersBtn && filtersContent) {
        toggleFiltersBtn.addEventListener('click', () => {
            filtersContent.classList.toggle('hidden');
        });
    }

    document.querySelectorAll('.filter-group input, .filter-group select').forEach(el => {
        el.addEventListener('change', () => {
            // Auto-refresh logic if needed
        });
    });
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

async function scanForArbitrage() {
    if (isScanning) return;

    isScanning = true;
    const scanBtn = document.getElementById('scan-btn');
    const originalBtnContent = scanBtn.innerHTML;

    // Update button visual state
    scanBtn.disabled = true;
    scanBtn.innerHTML = `
        <div class="size-14 rounded-2xl bg-primary flex items-center justify-center text-white">
            <div class="spinner border-2 border-white border-t-transparent rounded-full w-6 h-6 animate-spin"></div>
        </div>
        <span class="text-sm font-bold text-slate-600">Scanning...</span>
    `;

    showLoading(true);

    try {
        const filters = getFilters();
        const params = new URLSearchParams(filters);

        const startResponse = await fetch(`/api/scan/async?${params}`);
        const startData = await startResponse.json();

        if (!startData.job_id) {
            throw new Error('Failed to start scan job');
        }

        const jobId = startData.job_id;
        const pollInterval = 1000;
        let attempts = 0;
        const maxAttempts = 60;

        const poll = async () => {
            if (attempts >= maxAttempts) {
                throw new Error('Scan timed out');
            }

            const statusResponse = await fetch(`/api/scan/status/${jobId}`);
            const statusData = await statusResponse.json();

            if (statusData.status === 'done') {
                const result = statusData.result;
                opportunities = result.opportunities || [];
                updateApiCredits(result.api_usage);
                renderOpportunities();
                updateStats();

                if (lastScan) lastScan.textContent = new Date().toLocaleTimeString();

                if (opportunities.length > 0) {
                    showToast(`Found ${opportunities.length} arbitrage opportunities!`, 'success');
                    playNotificationSound();
                } else {
                    showToast('Scan complete. No opportunities found.', 'info');
                }

                isScanning = false;
                scanBtn.disabled = false;
                scanBtn.innerHTML = originalBtnContent;
                showLoading(false);
            } else if (statusData.status === 'error') {
                throw new Error(statusData.error || 'Scan failed');
            } else {
                attempts++;
                setTimeout(poll, pollInterval);
            }
        };

        poll();

    } catch (error) {
        console.error('Scan failed:', error);
        showToast('Failed to scan: ' + error.message, 'error');

        isScanning = false;
        scanBtn.disabled = false;
        scanBtn.innerHTML = originalBtnContent;
        showLoading(false);
    }
}

function updateApiCredits(usage) {
    if (usage && creditsRemaining && creditsTotal) {
        creditsRemaining.textContent = usage.remaining !== null ? usage.remaining : '--';
        creditsTotal.textContent = usage.remaining !== null ? (usage.remaining + (usage.used || 0)) : '--';
    }
}

function getQualityBadge(score) {
    if (score === undefined || score === null) return '';
    const q = parseFloat(score);
    let color, label;
    if (q >= 70) { color = '#22c55e'; label = 'green'; }
    else if (q >= 40) { color = '#f59e0b'; label = 'yellow'; }
    else { color = '#ef4444'; label = 'red'; }
    return `<span title="Quality Score" style="display:inline-flex;align-items:center;background:${color}22;color:${color};border-radius:999px;padding:1px 8px;font-size:0.7rem;font-weight:700;margin-left:4px;">Q${Math.round(q)}</span>`;
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
        const quality = opp.quality_score;

        // Build bookmaker display with rounded stakes
        const stakeEntries = Object.entries(opp.stakes || {});
        const bookmakers = stakeEntries.map(([outcome, s]) => {
            const displayStake = s.rounded_stake !== undefined ? s.rounded_stake : s.stake;
            const isRounded = s.rounded_stake !== undefined && s.rounded_stake !== s.stake;
            return `${s.book} €${displayStake.toFixed(2)}${isRounded ? '<span style="font-size:0.6rem;opacity:0.6;margin-left:2px;">~</span>' : ''}`;
        }).join(' · ');

        return `
            <div class="opp-card bg-white dark:bg-card-dark p-5 rounded-2xl border border-slate-50 dark:border-gray-700 shadow-soft flex items-center justify-between group hover:border-primary transition-all cursor-pointer"
                 data-quality="${quality !== undefined ? quality : 100}"
                 onclick="placeVirtualBet(${index})">
                <div class="flex items-center gap-4">
                    <div class="size-12 rounded-xl bg-slate-50 dark:bg-gray-800 flex items-center justify-center text-slate-900 dark:text-white text-2xl">
                        ${getSportEmoji(opp.sport)}
                    </div>
                    <div>
                        <h3 class="font-bold text-slate-900 dark:text-white flex items-center flex-wrap gap-1">
                            ${opp.home_team} vs ${opp.away_team}
                            ${getQualityBadge(quality)}
                        </h3>
                        <p class="text-xs text-slate-400 font-medium mt-0.5">${bookmakers}</p>
                    </div>
                </div>
                <div class="text-right">
                    <p class="font-bold text-primary">+€${opp.profit.toFixed(2)} (${opp.roi.toFixed(2)}%)</p>
                    <p class="text-[10px] text-slate-400 font-medium uppercase">${timeDisplay}</p>
                </div>
            </div>
        `;
    }).join('');

    // Apply quality filter after render
    if (typeof filterByQuality === 'function') filterByQuality();
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
