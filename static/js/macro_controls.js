// Phase 1: Per-Company Scenarios & Real-Time Prices
let macroEnvironments = [];
let activeMacroId = null;
let priceUpdateInterval = null;
let companiesData = {};
let lastUpdate = null;

document.addEventListener('DOMContentLoaded', () => {
    console.log('🚀 Initializing macro controls and price updates...');
    loadMacroEnvironments();

    // Wait 2 seconds for companies to load, then start price updates
    setTimeout(() => {
        startRealtimePriceUpdates();
    }, 2000);
});

async function loadMacroEnvironments() {
    try {
        const response = await fetch('/api/macro-environments');
        if (!response.ok) return;
        const data = await response.json();
        macroEnvironments = data.macro_environments || [];
        const activeEnv = macroEnvironments.find(env => env.is_active);
        if (activeEnv) {
            activeMacroId = activeEnv.id;
            updateMacroStatus(activeEnv.name);
        }
        renderMacroCards();
    } catch (error) {
        console.error('❌ Error loading macro:', error);
    }
}

function renderMacroCards() {
    const container = document.getElementById('macro-environments');
    if (!container) return;
    container.innerHTML = macroEnvironments.map(env => {
        const macroType = env.name.toLowerCase().includes('bear') ? 'bear' : env.name.toLowerCase().includes('bull') ? 'bull' : 'base';
        const icon = macroType === 'bear' ? '🐻' : macroType === 'bull' ? '🐂' : '📊';
        const desc = macroType === 'bear' ? 'Lower growth, higher risk' : macroType === 'bull' ? 'Strong growth, lower risk' : 'Balanced assumptions';
        return `<div class="macro-card ${macroType}"><div class="macro-card-header"><div class="macro-card-title">${icon} ${env.name}</div></div><div class="macro-card-description">${desc}<div style="margin-top:0.5rem;font-size:0.85rem;color:#667eea;font-weight:600;">Apply to individual stocks below</div></div><div class="macro-assumptions"><div class="macro-assumption-item"><span class="macro-assumption-label">Risk-Free Rate</span><span class="macro-assumption-value">${(env.risk_free_rate*100).toFixed(2)}%</span></div><div class="macro-assumption-item"><span class="macro-assumption-label">Market Premium</span><span class="macro-assumption-value">${(env.market_risk_premium*100).toFixed(2)}%</span></div></div></div>`;
    }).join('');
}

function updateMacroStatus(envName) {
    const statusContainer = document.getElementById('current-macro-status');
    if (!statusContainer) return;
    const macroType = envName.toLowerCase().includes('bear') ? 'bear' : envName.toLowerCase().includes('bull') ? 'bull' : 'base';
    statusContainer.innerHTML = `<span class="macro-status-badge ${macroType}">Reference: ${envName}</span>`;
}

function startRealtimePriceUpdates() {
    console.log('⏰ Starting daily price updates (once per day at market close)...');

    // Check if market has closed today and update if needed
    checkAndUpdatePrices();

    // Schedule daily updates at 4:05 PM ET (after market close at 4:00 PM ET)
    // Check every hour if it's time to update
    if (priceUpdateInterval) {
        clearInterval(priceUpdateInterval);
    }
    priceUpdateInterval = setInterval(() => {
        checkAndUpdatePrices();
    }, 3600000); // Check every 1 hour

    console.log('✅ Daily price update scheduler started');
}

function checkAndUpdatePrices() {
    const now = new Date();
    const lastUpdateKey = 'lastPriceUpdate';
    const lastUpdate = localStorage.getItem(lastUpdateKey);

    // Convert to ET timezone
    const etTime = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }));
    const etHour = etTime.getHours();
    const etDay = etTime.toDateString();

    // Market closes at 4:00 PM ET, we update at 4:05 PM ET
    const shouldUpdate = etHour >= 16 && (!lastUpdate || new Date(lastUpdate).toDateString() !== etDay);

    if (shouldUpdate) {
        console.log(`📊 Market closed - updating prices at ${etTime.toLocaleTimeString('en-US', { timeZone: 'America/New_York' })} ET`);
        updatePortfolioPrices();
        localStorage.setItem(lastUpdateKey, now.toISOString());
    } else {
        console.log(`⏰ Next price update: Today at 4:05 PM ET (after market close)`);
    }
}

async function updatePortfolioPrices() {
    const now = new Date();
    console.log(`\n🔄 [${now.toLocaleTimeString()}] Fetching real-time prices...`);

    try {
        const response = await fetch('/api/prices/realtime');

        if (!response.ok) {
            console.error('❌ API returned error:', response.status, response.statusText);
            return;
        }

        const data = await response.json();
        console.log('📦 API Response:', data);

        if (!data.success) {
            console.error('❌ API success = false');
            return;
        }

        if (!data.prices || data.prices.length === 0) {
            console.warn('⚠️ No prices returned. Are there companies with tickers?');
            return;
        }

        console.log(`💰 Updating ${data.prices.length} stock prices...`);

        let updatedCount = 0;
        data.prices.forEach(priceData => {
            console.log(`\n  📊 ${priceData.ticker} (ID: ${priceData.company_id})`);
            console.log(`     Current Price: $${priceData.current_price.toFixed(2)}`);
            console.log(`     Market Cap: $${(priceData.market_cap / 1e9).toFixed(2)}B`);

            // Find the company card
            const card = document.querySelector(`[data-company-id="${priceData.company_id}"]`);
            if (!card) {
                console.warn(`     ⚠️ Card not found for company ID ${priceData.company_id}`);
                return;
            }

            // Update current price
            const priceEl = card.querySelector('.company-current-price');
            if (priceEl) {
                const oldPrice = priceEl.textContent;
                priceEl.textContent = `$${priceData.current_price.toFixed(2)}`;
                console.log(`     ✅ Updated price: ${oldPrice} → $${priceData.current_price.toFixed(2)}`);

                // Flash animation
                priceEl.classList.add('price-updated');
                setTimeout(() => priceEl.classList.remove('price-updated'), 1000);

                updatedCount++;
            } else {
                console.warn(`     ⚠️ Price element not found in card`);
            }

            // Update market cap
            const mcapEl = card.querySelector('.company-market-cap');
            if (mcapEl && priceData.market_cap) {
                const mcapB = (priceData.market_cap / 1e9).toFixed(2);
                mcapEl.textContent = `$${mcapB}B`;
                console.log(`     ✅ Updated market cap: $${mcapB}B`);
            }
        });

        lastUpdate = now;
        console.log(`\n✅ Successfully updated ${updatedCount}/${data.prices.length} prices at ${now.toLocaleTimeString()}`);
        console.log(`⏰ Next update: Tomorrow at 4:05 PM ET (after market close)`);

        // Reload companies data to get the updated prices from database
        if (typeof loadCompanies === 'function') {
            console.log('🔄 Reloading company data...');
            loadCompanies();
        }

    } catch (error) {
        console.error('❌ Error updating prices:', error);
        console.error('Stack trace:', error.stack);
    }
}

async function applyScenarioToCompany(companyId, scenarioType) {
    try {
        showNotification(`Applying ${scenarioType}...`, 'info');
        const response = await fetch(`/api/company/${companyId}/scenario/apply`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({scenario_type: scenarioType})
        });
        if (!response.ok) throw new Error('Failed');
        updateCompanyScenarioDisplay(companyId, scenarioType);
        if (typeof loadCompanies === 'function') loadCompanies();
        showNotification(`${scenarioType.toUpperCase()} applied!`, 'success');
    } catch (error) {
        showNotification('Failed to apply scenario', 'error');
    }
}

function updateCompanyScenarioDisplay(companyId, scenarioType) {
    const card = document.querySelector(`[data-company-id="${companyId}"]`);
    if (!card) return;
    card.querySelectorAll('.scenario-btn').forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.scenario === scenarioType) btn.classList.add('active');
    });
    let badge = card.querySelector('.company-scenario-badge');
    if (!badge) {
        badge = document.createElement('div');
        badge.className = 'company-scenario-badge';
        const header = card.querySelector('.company-header');
        if (header) header.appendChild(badge);
    }
    const icon = scenarioType === 'bear' ? '🐻' : scenarioType === 'bull' ? '🐂' : '📊';
    badge.className = `company-scenario-badge scenario-${scenarioType}`;
    badge.textContent = icon + ' ' + scenarioType.toUpperCase();
}

function showNotification(message, type = 'info') {
    const n = document.createElement('div');
    n.style.cssText = `position:fixed;top:80px;right:20px;padding:1rem 1.5rem;background:${type==='success'?'#38ef7d':type==='error'?'#fa709a':'#667eea'};color:white;border-radius:8px;box-shadow:0 4px 20px rgba(0,0,0,0.2);z-index:9999;font-weight:600;`;
    n.textContent = message;
    document.body.appendChild(n);
    setTimeout(() => n.remove(), 3000);
}

// Add manual refresh button functionality
window.refreshPricesNow = function() {
    console.log('🔄 Manual price refresh triggered');
    updatePortfolioPrices();
};

const style = document.createElement('style');
style.textContent = `
@keyframes priceFlash {
    0% { background: transparent; transform: scale(1); }
    50% { background: rgba(56, 239, 125, 0.3); transform: scale(1.1); color: #10b981; }
    100% { background: transparent; transform: scale(1); }
}

.price-updated {
    animation: priceFlash 1s ease-out;
    font-weight: 700;
}

.company-scenario-badge{display:inline-block;padding:0.25rem 0.75rem;border-radius:20px;font-size:0.8rem;font-weight:700;margin-left:0.5rem}
.company-scenario-badge.scenario-bear{background:#fee140;color:#c82333}
.company-scenario-badge.scenario-base{background:#38ef7d;color:#11998e}
.company-scenario-badge.scenario-bull{background:#667eea;color:white}
.scenario-selector{display:flex;gap:0.5rem;margin-top:0.75rem;padding-top:0.75rem;border-top:1px solid #e9ecef}
.scenario-btn{flex:1;padding:0.5rem;border:2px solid #e9ecef;background:white;border-radius:6px;font-size:0.8rem;font-weight:600;cursor:pointer;transition:all 0.2s}
.scenario-btn:hover{transform:translateY(-2px);box-shadow:0 2px 8px rgba(0,0,0,0.1)}
.scenario-btn.bear{border-color:#fee140;color:#c82333}
.scenario-btn.bear:hover,.scenario-btn.bear.active{background:#fee140;color:#c82333}
.scenario-btn.base{border-color:#38ef7d;color:#11998e}
.scenario-btn.base:hover,.scenario-btn.base.active{background:#38ef7d;color:white}
.scenario-btn.bull{border-color:#667eea;color:#667eea}
.scenario-btn.bull:hover,.scenario-btn.bull.active{background:#667eea;color:white}
.scenario-btn.active{font-weight:700;box-shadow:0 4px 12px rgba(0,0,0,0.15)}
`;
document.head.appendChild(style);

window.applyScenarioToCompany = applyScenarioToCompany;
window.updatePortfolioPrices = updatePortfolioPrices;

console.log('✅ Macro controls initialized');
