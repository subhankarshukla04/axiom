// ============================================
// PROFESSIONAL INVESTMENT PLATFORM - JAVASCRIPT
// Enhanced with investor-focused features
// ============================================

// Global state
let currentCompanyId = null;
let allCompanies = [];
let filteredCompanies = [];
let currentFilter = 'all';
let currentSort = 'name';
let dashboardStats = null;
let appSettings = {};
let previousValuation = null;

// Selection state
let selectModeActive = false;
let selectedCompanyIds = new Set();

// Initialize app
document.addEventListener('DOMContentLoaded', function() {
    console.log('🚀 App initializing...');

    loadDashboard();
    loadCompanies();
    // Load settings at startup so UI behavior (like recompute-on-save) is available
    loadSettings();

    // Form submission - attach to form with detailed logging
    const companyForm = document.getElementById('company-form');
    if (companyForm) {
        companyForm.addEventListener('submit', function(e) {
            console.log('📝 Form submit event triggered');
            saveCompany(e);
        });
        console.log('✅ Form submit handler attached to:', companyForm);
    } else {
        console.error('❌ Company form not found!');
    }

    // Settings form submission
    const settingsForm = document.getElementById('settings-form');
    if (settingsForm) settingsForm.addEventListener('submit', saveSettings);

    // Load theme preference
    const savedTheme = localStorage.getItem('theme') || 'light';
    document.documentElement.setAttribute('data-theme', savedTheme);

    // Keyboard shortcuts
    document.addEventListener('keydown', handleKeyboardShortcuts);

    console.log('✅ App initialized successfully');
});

// ============================================
// THEME TOGGLE
// ============================================

function toggleTheme() {
    const html = document.documentElement;
    const currentTheme = html.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    
    html.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
}

// ============================================
// KEYBOARD SHORTCUTS
// ============================================

function handleKeyboardShortcuts(e) {
    // Cmd/Ctrl + K: Focus search
    if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        const searchInput = document.getElementById('company-search');
        if (searchInput) {
            searchInput.focus();
        }
    }
    
    // Cmd/Ctrl + N: New company
    if ((e.metaKey || e.ctrlKey) && e.key === 'n') {
        e.preventDefault();
        showAddCompanyModal();
    }
    
    // Escape: Close modals
    if (e.key === 'Escape') {
        closeModal();
        closeValuationModal();
    }
    
    // Cmd/Ctrl + 1/2: Switch views
    if ((e.metaKey || e.ctrlKey) && e.key === '1') {
        e.preventDefault();
        showView('dashboard');
    }
    if ((e.metaKey || e.ctrlKey) && e.key === '2') {
        e.preventDefault();
        showView('companies');
    }
}

// ============================================
// VIEW MANAGEMENT
// ============================================

function showView(viewName) {
    document.querySelectorAll('.view-section').forEach(v => {
        v.classList.remove('active');
        v.style.display = 'none';
    });
    document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
    
    const targetView = document.getElementById(`${viewName}-view`);
    if (targetView) {
        targetView.classList.add('active');
        targetView.style.display = '';
    }
    const navLink = document.querySelector(`[data-view="${viewName}"]`);
    if (navLink) {
        navLink.classList.add('active');
    }
    
    if (viewName === 'dashboard') {
        loadDashboard();
    } else if (viewName === 'companies') {
        loadCompanies();
    } else if (viewName === 'scenarios') {
        initScenariosTab();
    }
}

// ============================================
// DASHBOARD FUNCTIONS - ENHANCED
// ============================================

async function loadDashboard() {
    try {
        const response = await fetch('/api/dashboard/stats');
        const stats = await response.json();
        dashboardStats = stats;
        
        // Update main stats with enhanced display
        document.getElementById('total-companies').textContent = stats.total_companies;
        document.getElementById('avg-upside').textContent = `${stats.avg_upside.toFixed(1)}%`;
        document.getElementById('avg-pe').textContent = `${stats.avg_pe.toFixed(1)}x`;
        document.getElementById('avg-roe').textContent = `${stats.avg_roe.toFixed(1)}%`;
        
        // Add WACC if available
        const avgWacc = stats.avg_wacc || 0;
        const waccElement = document.getElementById('avg-wacc');
        if (waccElement) {
            waccElement.textContent = `${avgWacc.toFixed(2)}%`;
        }
        
        // Update trend indicators
        updateTrendIndicators(stats);
        
        // Update recommendation counts with percentages
        const total = stats.total_companies || 1;
        document.getElementById('buy-count').textContent = stats.buy_count;
        document.getElementById('hold-count').textContent = stats.hold_count;
        document.getElementById('sell-count').textContent = stats.sell_count;
        
        const buyPct = document.getElementById('buy-pct');
        const holdPct = document.getElementById('hold-pct');
        const sellPct = document.getElementById('sell-pct');
        
        if (buyPct) buyPct.textContent = `${((stats.buy_count / total) * 100).toFixed(0)}% of portfolio`;
        if (holdPct) holdPct.textContent = `${((stats.hold_count / total) * 100).toFixed(0)}% of portfolio`;
        if (sellPct) sellPct.textContent = `${((stats.sell_count / total) * 100).toFixed(0)}% of portfolio`;
        
        // Enhanced sector breakdown with table format
        renderSectorTable(stats.sectors);
        
    } catch (error) {
        console.error('Error loading dashboard:', error);
    }
}

function updateTrendIndicators(stats) {
    // These would be calculated from historical data in a real app
    // For now, using positive indicators for demonstration
    const trends = [
        { id: 'total-trend', value: 5 },
        { id: 'upside-trend', value: stats.avg_upside > 10 ? 2 : -1 },
        { id: 'pe-trend', value: 0 },
        { id: 'roe-trend', value: stats.avg_roe > 15 ? 3 : -2 },
        { id: 'wacc-trend', value: 0 }
    ];
    
    trends.forEach(trend => {
        const element = document.getElementById(trend.id);
        if (element) {
            const isPositive = trend.value > 0;
            const isNeutral = trend.value === 0;
            
            element.className = `stat-trend ${isPositive ? 'positive' : isNeutral ? '' : 'negative'}`;
            element.innerHTML = `
                <span>${isPositive ? '↑' : isNeutral ? '—' : '↓'}</span>
                <span>${Math.abs(trend.value)}%</span>
            `;
        }
    });
}

function renderSectorTable(sectors) {
    if (!sectors || sectors.length === 0) {
        document.getElementById('sector-breakdown').innerHTML = `
            <tr>
                <td colspan="6" style="text-align: center; padding: 2rem; color: var(--text-tertiary);">
                    No sector data available. Add companies to see sector analysis.
                </td>
            </tr>
        `;
        return;
    }
    
    const maxUpside = Math.max(...sectors.map(s => Math.abs(s.avg_upside)));
    
    const sectorHtml = sectors.map(sector => {
        const upsideClass = sector.avg_upside >= 0 ? 'positive' : 'negative';
        const barWidth = maxUpside > 0 ? (Math.abs(sector.avg_upside) / maxUpside) * 100 : 0;
        
        return `
            <tr>
                <td><span class="sector-name">${sector.name}</span></td>
                <td><span class="sector-count">${sector.count} companies</span></td>
                <td><span class="sector-metric ${upsideClass}">${sector.avg_upside >= 0 ? '+' : ''}${sector.avg_upside.toFixed(1)}%</span></td>
                <td><span class="sector-metric">${sector.avg_roe.toFixed(1)}%</span></td>
                <td><span class="sector-metric">${sector.avg_pe ? sector.avg_pe.toFixed(1) + 'x' : 'N/A'}</span></td>
                <td style="text-align: right;">
                    <div class="sector-bar">
                        <div class="sector-bar-fill" style="width: ${barWidth}%"></div>
                    </div>
                </td>
            </tr>
        `;
    }).join('');
    
    document.getElementById('sector-breakdown').innerHTML = sectorHtml;
}

// Sector sorting functions
let currentSectorSort = 'name';
function sortSectorBy(type) {
    if (!dashboardStats || !dashboardStats.sectors) return;
    
    currentSectorSort = type;
    const sectors = [...dashboardStats.sectors];
    
    if (type === 'upside') {
        sectors.sort((a, b) => b.avg_upside - a.avg_upside);
    } else if (type === 'count') {
        sectors.sort((a, b) => b.count - a.count);
    } else if (type === 'roe') {
        sectors.sort((a, b) => b.avg_roe - a.avg_roe);
    } else {
        sectors.sort((a, b) => a.name.localeCompare(b.name));
    }
    
    renderSectorTable(sectors);
}

// ============================================
// COMPANIES FUNCTIONS - ENHANCED
// ============================================

async function loadCompanies() {
    try {
        const response = await fetch('/api/companies');
        const companies = await response.json();
        allCompanies = companies;
        
        // Apply current filters and sort
        applyFiltersAndSort();
        
    } catch (error) {
        console.error('Error loading companies:', error);
    }
}

function applyFiltersAndSort() {
    // Filter
    filteredCompanies = allCompanies.filter(company => {
        // Search filter
        const searchTerm = document.getElementById('company-search')?.value.toLowerCase() || '';
        const matchesSearch = !searchTerm || 
            company.name.toLowerCase().includes(searchTerm) ||
            (company.sector && company.sector.toLowerCase().includes(searchTerm));
        
        // Recommendation filter
        const matchesRec = currentFilter === 'all' || 
            getRecommendationClass(company.recommendation) === currentFilter;
        
        return matchesSearch && matchesRec;
    });
    
    // Sort
    filteredCompanies.sort((a, b) => {
        switch(currentSort) {
            case 'name':
                return a.name.localeCompare(b.name);
            case 'upside-desc':
                return (b.upside || 0) - (a.upside || 0);
            case 'upside-asc':
                return (a.upside || 0) - (b.upside || 0);
            case 'roe-desc':
                return (b.roe || 0) - (a.roe || 0);
            case 'pe-asc':
                return (a.pe_ratio || 999) - (b.pe_ratio || 999);
            case 'sector':
                return (a.sector || '').localeCompare(b.sector || '');
            default:
                return 0;
        }
    });
    
    renderCompanies();
}

function renderCompanies() {
    const countElement = document.getElementById('companies-count');
    if (countElement) {
        countElement.textContent = filteredCompanies.length;
    }
    
    if (filteredCompanies.length === 0) {
        document.getElementById('companies-grid').innerHTML = `
            <div style="grid-column: 1/-1; text-align: center; padding: 4rem 2rem;">
                <h3 style="color: var(--text-secondary); margin-bottom: 1rem;">No companies found</h3>
                <p style="color: var(--text-tertiary);">
                    ${allCompanies.length === 0 
                        ? 'Add your first company to get started with valuations.' 
                        : 'Try adjusting your filters or search terms.'}
                </p>
                ${allCompanies.length === 0 
                    ? '<button class="btn-primary" onclick="showAddCompanyModal()" style="margin-top: 1.5rem;">+ Add Company</button>' 
                    : ''}
            </div>
        `;
        return;
    }
    
    const companiesHtml = filteredCompanies.map(company => {
        const recClass = getRecommendationClass(company.recommendation);
        const upsideValue = company.upside || 0;
        const upsideClass = upsideValue >= 0 ? 'positive' : 'negative';
        const isSelected = selectedCompanyIds.has(company.id);

        // Border color driven by recommendation
        let borderClass = '';
        if (company.recommendation) {
            const r = company.recommendation.toLowerCase();
            if (r.includes('buy')) borderClass = ' card-border-buy';
            else if (r.includes('hold')) borderClass = ' card-border-hold';
            else borderClass = ' card-border-sell';
        }

        // Wall St. upside (only if we have both prices)
        let streetUpsideHtml = '';
        if (company.analyst_target && company.current_price) {
            const su = ((company.analyst_target - company.current_price) / company.current_price) * 100;
            const sc = su >= 0 ? 'positive' : 'negative';
            streetUpsideHtml = `<span class="upside-pill ${sc}">${su >= 0 ? '+' : ''}${su.toFixed(1)}% Street</span>`;
        }

        const cardOnclick = selectModeActive
            ? `toggleCompanySelection(${company.id})`
            : `showFairValueBreakdown(${company.id})`;

        return `
            <div class="company-card${borderClass}${isSelected ? ' selected' : ''}"
                 data-company-id="${company.id}"
                 onclick="${cardOnclick}"
                 style="cursor:pointer;">

                ${selectModeActive ? `
                <div onclick="event.stopPropagation();toggleCompanySelection(${company.id})"
                     style="position:absolute;top:12px;right:12px;z-index:2;width:28px;height:28px;border-radius:50%;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:all 0.15s;
                     ${isSelected ? 'background:#111111;border:2px solid #111111;' : 'background:var(--bg-secondary);border:2px solid var(--border-primary);'}">
                    ${isSelected ? '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>' : ''}
                </div>` : ''}

                <!-- Header: ticker + rec badge -->
                <div class="company-header">
                    <div class="company-header-left">
                        <div class="company-ticker-large">${company.ticker || company.name}</div>
                        <div class="company-name-sub">
                            ${company.ticker ? company.name : ''}
                            ${company.sector ? `<span class="company-sector-tag">${company.sector}</span>` : ''}
                        </div>
                    </div>
                    ${company.recommendation ? `<div class="rec-badge-header ${recClass}">${company.recommendation}</div>` : ''}
                </div>

                ${company.fair_value ? `
                    <!-- Price Bubbles -->
                    <div class="price-bubbles">
                        <div class="price-bubble axiom">
                            <div class="bubble-value">$${formatNumber(company.fair_value)}</div>
                            <div class="bubble-label">AXIOM</div>
                        </div>
                        ${(() => {
                            const uv = getUserValuation(company.id);
                            return uv ? `
                        <div class="price-bubble user" style="background: linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%); color: white;">
                            <div class="bubble-value">$${uv.pricePerShare.toFixed(2)}</div>
                            <div class="bubble-label">Yours</div>
                        </div>` : '';
                        })()}
                        ${company.analyst_target ? `
                        <div class="price-bubble street">
                            <div class="bubble-value">$${formatNumber(company.analyst_target)}</div>
                            <div class="bubble-label">Wall St.</div>
                        </div>` : ''}
                        <div class="price-bubble market">
                            <div class="bubble-value">$${company.current_price ? company.current_price.toFixed(2) : 'N/A'}</div>
                            <div class="bubble-label">Market</div>
                        </div>
                    </div>

                    <!-- Upside Row -->
                    <div class="upside-row">
                        <span class="upside-pill ${upsideClass}">${upsideValue >= 0 ? '+' : ''}${upsideValue.toFixed(1)}% AXIOM</span>
                        ${(() => {
                            const uv = getUserValuation(company.id);
                            if (uv && company.current_price) {
                                const userUpside = ((uv.pricePerShare - company.current_price) / company.current_price) * 100;
                                const userClass = userUpside >= 0 ? 'positive' : 'negative';
                                return `<span class="upside-pill ${userClass}" style="background: linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%); color: white;">${userUpside >= 0 ? '+' : ''}${userUpside.toFixed(1)}% Yours</span>`;
                            }
                            return '';
                        })()}
                        ${streetUpsideHtml}
                    </div>

                    <div class="card-view-analysis">View full analysis →</div>
                ` : `
                    <div style="text-align:center; padding:2rem 1rem; color:var(--text-tertiary);">
                        <p style="margin-bottom:0.5rem; font-size:1.25rem;">📊</p>
                        <p style="font-size:0.875rem; font-weight:600;">No valuation data yet</p>
                        <p style="font-size:0.75rem; margin-top:0.25rem;">Click to run analysis</p>
                    </div>
                `}

                <div class="scenario-selector" style="display:none">
                    <button class="scenario-btn bear" data-scenario="bear" onclick="event.stopPropagation();applyScenarioToCompany(${company.id}, 'bear')">🐻 Bear</button>
                    <button class="scenario-btn base active" data-scenario="base" onclick="event.stopPropagation();applyScenarioToCompany(${company.id}, 'base')">📊 Base</button>
                    <button class="scenario-btn bull" data-scenario="bull" onclick="event.stopPropagation();applyScenarioToCompany(${company.id}, 'bull')">🐂 Bull</button>
                </div>
            </div>
        `;
    }).join('');
    
    document.getElementById('companies-grid').innerHTML = companiesHtml;
}

// Show fair value breakdown modal (fetch latest stored valuation and show detailed methods)
async function showFairValueBreakdown(companyId) {
    currentCompanyId = companyId;  // Set for DCF details modal
    try {
        showLoadingState('Loading valuation breakdown...');
        const res = await fetch(`/api/company/${companyId}`);
        if (!res.ok) throw new Error('Failed to load company valuation');
        const data = await res.json();

        // If the endpoint returns an object with `valuation`, map it into the shape expected by showValuationResults
        const val = data.valuation || data;

        const result = {
            company_id: data.id,
            name: data.name,
            recommendation: val.recommendation || 0,
            upside_pct: val.upside_pct || 0,
            final_equity_value: val.final_equity_value || 0,
            final_price_per_share: val.final_price_per_share || 0,
            market_cap: val.market_cap || 0,
            current_price: val.current_price || 0,
            dcf_equity_value: val.dcf_equity_value || 0,
            dcf_price_per_share: val.dcf_price_per_share || 0,
            comp_ev_value: val.comp_ev_value || 0,
            comp_pe_value: val.comp_pe_value || 0,
            mc_p10: val.mc_p10 || 0,
            mc_p90: val.mc_p90 || 0,
            wacc: val.wacc || 0,
            ev_ebitda: val.ev_ebitda || 0,
            pe_ratio: val.pe_ratio || 0,
            fcf_yield: val.fcf_yield || 0,
            roe: val.roe || 0,
            roic: val.roic || 0,
            debt_to_equity: val.debt_to_equity || 0,
            z_score: val.z_score || 0,
            sub_sector_tag: val.sub_sector_tag || null,
            company_type: val.company_type || null,
            ebitda_method: val.ebitda_method || null,
            analyst_target: val.analyst_target || null,
        };

        hideLoadingState();
        showValuationResults(result);
    } catch (err) {
        hideLoadingState();
        console.error('Error loading valuation breakdown:', err);
        alert('Could not load valuation breakdown');
    }
}

// ============================================
// FILTERING & SORTING
// ============================================

function filterCompanies() {
    applyFiltersAndSort();
}

function filterByRecommendation(rec) {
    currentFilter = rec;
    
    // Update button states
    document.querySelectorAll('.toolbar .filter-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    document.getElementById(`filter-${rec}`).classList.add('active');
    
    applyFiltersAndSort();
}

function sortCompanies() {
    currentSort = document.getElementById('company-sort').value;
    applyFiltersAndSort();
}

// ============================================
// UTILITY FUNCTIONS
// ============================================

function getRecommendationClass(recommendation) {
    if (!recommendation) return '';
    const rec = recommendation.toLowerCase();
    if (rec.includes('buy')) return 'buy';
    if (rec.includes('hold')) return 'hold';
    return 'sell';
}

function formatNumber(num) {
    if (!num) return '0';
    if (num >= 1e9) return (num / 1e9).toFixed(2) + 'B';
    if (num >= 1e6) return (num / 1e6).toFixed(2) + 'M';
    if (num >= 1e3) return (num / 1e3).toFixed(2) + 'K';
    return num.toFixed(2);
}

// Watchlist functionality (localStorage based)
function toggleWatchlist(companyId) {
    const watchlist = JSON.parse(localStorage.getItem('watchlist') || '[]');
    const index = watchlist.indexOf(companyId);
    
    if (index > -1) {
        watchlist.splice(index, 1);
        alert('Removed from watchlist');
    } else {
        watchlist.push(companyId);
        alert('Added to watchlist');
    }
    
    localStorage.setItem('watchlist', JSON.stringify(watchlist));
    renderCompanies(); // Refresh to update watchlist star
}

// ============================================
// MODAL FUNCTIONS
// ============================================

function showAddCompanyModal() {
    currentCompanyId = null;
    document.getElementById('modal-title').textContent = 'Add New Company';
    document.getElementById('company-form').reset();
    document.getElementById('company-id').value = '';
    
    // Set defaults
    document.getElementById('risk_free_rate').value = 4.5;
    document.getElementById('market_risk_premium').value = 6.5;
    document.getElementById('country_risk_premium').value = 0;
    
    document.getElementById('company-modal').classList.add('active');
}

async function editCompany(companyId) {
    try {
        showLoadingState('Loading company data...');
        const response = await fetch(`/api/company/${companyId}`);
        if (!response.ok) throw new Error('Failed to fetch company details');

        const data = await response.json();
        hideLoadingState();

        currentCompanyId = companyId;

        // Populate modal with ALL company data from API
        document.getElementById('modal-title').textContent = `Edit Company: ${data.name}`;
        document.getElementById('company-id').value = data.id;

        // Basic Information
        document.getElementById('name').value = data.name || '';
        document.getElementById('sector').value = data.sector || '';

        // Financial Data - Check both data and data.financials
        const fin = data.financials || data;

        // Helper to convert decimal to percentage for display
        const toPercentage = (decimal) => {
            return decimal ? (decimal * 100).toFixed(2) : 0;
        };

        document.getElementById('revenue').value = fin.revenue || 0;
        document.getElementById('ebitda').value = fin.ebitda || 0;
        document.getElementById('depreciation').value = fin.depreciation || 0;
        document.getElementById('profit_margin').value = toPercentage(fin.profit_margin);
        document.getElementById('capex_pct').value = toPercentage(fin.capex_pct);
        document.getElementById('working_capital_change').value = fin.working_capital_change || 0;

        // Growth Rates - Convert from decimal to percentage
        document.getElementById('growth_rate_y1').value = toPercentage(fin.growth_rate_y1);
        document.getElementById('growth_rate_y2').value = toPercentage(fin.growth_rate_y2);
        document.getElementById('growth_rate_y3').value = toPercentage(fin.growth_rate_y3);
        document.getElementById('terminal_growth').value = toPercentage(fin.terminal_growth);

        // Capital Structure
        document.getElementById('shares_outstanding').value = fin.shares_outstanding || 0;
        document.getElementById('debt').value = fin.debt || 0;
        document.getElementById('cash').value = fin.cash || 0;
        document.getElementById('market_cap_estimate').value = fin.market_cap_estimate || 0;
        document.getElementById('tax_rate').value = toPercentage(fin.tax_rate);

        // Risk Parameters - Convert from decimal to percentage
        document.getElementById('beta').value = fin.beta || 1.0;
        document.getElementById('risk_free_rate').value = toPercentage(fin.risk_free_rate);
        document.getElementById('market_risk_premium').value = toPercentage(fin.market_risk_premium);
        document.getElementById('country_risk_premium').value = toPercentage(fin.country_risk_premium);
        document.getElementById('size_premium').value = toPercentage(fin.size_premium);

        // Comparable Multiples
        document.getElementById('comparable_ev_ebitda').value = fin.comparable_ev_ebitda || 0;
        document.getElementById('comparable_pe').value = fin.comparable_pe || 0;
        document.getElementById('comparable_peg').value = fin.comparable_peg || 0;

        // Store current valuation for before/after comparison
        if (data.valuation) {
            previousValuation = {
                final_equity_value: data.valuation.final_equity_value,
                final_price_per_share: data.valuation.final_price_per_share,
                recommendation: data.valuation.recommendation,
                upside_pct: data.valuation.upside_pct
            };
        }

        // Show modal
        document.getElementById('company-modal').classList.add('active');

        // Enable live valuation preview for edits
        if (data.valuation && data.valuation.final_equity_value) {
            enableLiveValuationPreview(data.valuation.final_equity_value, fin);
        }

    } catch (err) {
        hideLoadingState();
        console.error('Error editing company:', err);
        alert('Could not edit company');
    }
}

// ============================================
// LIVE VALUATION PREVIEW (Sprint 0)
// ============================================

let _previewDebounceTimer = null;

// Collect all current form field values for the preview API call
function _collectFormDataForPreview() {
    const pctToDecimal = (id) => {
        const v = parseFloat(document.getElementById(id)?.value);
        return isNaN(v) ? null : v / 100;
    };
    const num = (id) => {
        const v = parseFloat(document.getElementById(id)?.value);
        return isNaN(v) ? null : v;
    };

    return {
        name: document.getElementById('name')?.value || 'Preview',
        sector: document.getElementById('sector')?.value || 'Unknown',
        revenue: num('revenue'),
        ebitda: num('ebitda'),
        depreciation: num('depreciation'),
        profit_margin: pctToDecimal('profit_margin'),
        capex_pct: pctToDecimal('capex_pct'),
        working_capital_change: num('working_capital_change'),
        growth_rate_y1: pctToDecimal('growth_rate_y1'),
        growth_rate_y2: pctToDecimal('growth_rate_y2'),
        growth_rate_y3: pctToDecimal('growth_rate_y3'),
        terminal_growth: pctToDecimal('terminal_growth'),
        tax_rate: pctToDecimal('tax_rate'),
        shares_outstanding: num('shares_outstanding'),
        debt: num('debt'),
        cash: num('cash'),
        market_cap_estimate: num('market_cap_estimate'),
        beta: num('beta'),
        risk_free_rate: pctToDecimal('risk_free_rate'),
        market_risk_premium: pctToDecimal('market_risk_premium'),
        country_risk_premium: pctToDecimal('country_risk_premium'),
        size_premium: pctToDecimal('size_premium'),
        comparable_ev_ebitda: num('comparable_ev_ebitda'),
        comparable_pe: num('comparable_pe'),
        comparable_peg: num('comparable_peg'),
    };
}

// Debounced function that calls /api/valuation/preview and updates the Live Preview section
function recalculatePreview() {
    if (_previewDebounceTimer) clearTimeout(_previewDebounceTimer);
    _previewDebounceTimer = setTimeout(async () => {
        const liveSection = document.getElementById('valuation-live-preview');
        if (!liveSection) return;

        // Show loading state in preview
        liveSection.style.display = 'block';
        document.getElementById('live-preview-fair-value').textContent = '...';
        document.getElementById('live-preview-upside').textContent = '...';
        document.getElementById('live-preview-wacc').textContent = '...';
        document.getElementById('live-preview-dcf').textContent = '...';
        document.getElementById('live-preview-comps').textContent = '...';
        _updatePreviewWarnings(null);

        try {
            const payload = _collectFormDataForPreview();
            const resp = await fetch('/api/valuation/preview', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (!resp.ok) {
                const err = await resp.json();
                document.getElementById('live-preview-fair-value').textContent = 'Error';
                console.warn('Preview API error:', err);
                return;
            }

            const result = await resp.json();
            const waccPct = (result.wacc || 0) * 100;
            const upsidePct = result.upside_pct || 0;

            document.getElementById('live-preview-fair-value').textContent = '$' + (result.fair_value || 0).toFixed(2);
            document.getElementById('live-preview-upside').textContent = (upsidePct >= 0 ? '+' : '') + upsidePct.toFixed(1) + '%';
            document.getElementById('live-preview-wacc').textContent = waccPct.toFixed(1) + '%';
            document.getElementById('live-preview-dcf').textContent = '$' + (result.dcf_value || 0).toFixed(0);
            document.getElementById('live-preview-comps').textContent = '$' + (result.comps_value || 0).toFixed(0);

            // Color upside
            const upsideEl = document.getElementById('live-preview-upside');
            upsideEl.style.color = upsidePct >= 0 ? '#22c55e' : '#ef4444';

            _updatePreviewWarnings(result);
        } catch (err) {
            console.error('Live preview error:', err);
            document.getElementById('live-preview-fair-value').textContent = 'N/A';
        }
    }, 600);
}

// Show inline warnings based on guardrail thresholds
function _updatePreviewWarnings(result) {
    const waccWarn = document.getElementById('live-preview-wacc-warning');
    const tgWarn = document.getElementById('live-preview-tg-warning');
    if (!waccWarn || !tgWarn) return;

    if (!result) {
        waccWarn.style.display = 'none';
        tgWarn.style.display = 'none';
        return;
    }

    const waccPct = (result.wacc || 0) * 100;
    waccWarn.style.display = waccPct < 5 ? 'block' : 'none';

    // Check terminal growth from form
    const tgRaw = parseFloat(document.getElementById('terminal_growth')?.value);
    const tgPct = isNaN(tgRaw) ? 0 : tgRaw;
    tgWarn.style.display = tgPct > 3.5 ? 'block' : 'none';
}

// Live valuation preview - shows estimated impact of changes
function enableLiveValuationPreview(currentFairValue, originalFinancials) {
    const previewSection = document.getElementById('valuation-preview-section');
    if (previewSection) {
        previewSection.style.display = 'block';
        document.getElementById('preview-current-value').textContent = formatCurrency(currentFairValue);
    }

    // Show the new live preview section
    const liveSection = document.getElementById('valuation-live-preview');
    if (liveSection) liveSection.style.display = 'block';

    // Attach debounced preview to all numeric inputs
    const numericFields = [
        'revenue', 'ebitda', 'depreciation', 'profit_margin', 'capex_pct',
        'working_capital_change', 'growth_rate_y1', 'growth_rate_y2', 'growth_rate_y3',
        'terminal_growth', 'tax_rate', 'shares_outstanding', 'debt', 'cash',
        'market_cap_estimate', 'beta', 'risk_free_rate', 'market_risk_premium',
        'country_risk_premium', 'size_premium', 'comparable_ev_ebitda',
        'comparable_pe', 'comparable_peg'
    ];

    numericFields.forEach(fieldId => {
        const field = document.getElementById(fieldId);
        if (field) {
            field.addEventListener('input', recalculatePreview);
        }
    });

    // Trigger initial preview
    recalculatePreview();

    // Keep legacy simple preview too
    updateValuationPreview(currentFairValue, originalFinancials);
}

function updateValuationPreview(currentFairValue, originalFinancials) {
    try {
        const newRevenue = parseFloat(document.getElementById('revenue').value) || 0;
        const newEbitda = parseFloat(document.getElementById('ebitda').value) || 0;
        const newGrowthY1 = parseFloat(document.getElementById('growth_rate_y1').value) / 100 || 0;

        const origRevenue = originalFinancials.revenue || 1;
        const origEbitda = originalFinancials.ebitda || 1;
        const origGrowthY1 = originalFinancials.growth_rate_y1 || 0.1;

        const revenueImpact = newRevenue / origRevenue;
        const ebitdaImpact = newEbitda / origEbitda;
        const growthImpact = (1 + newGrowthY1) / (1 + origGrowthY1);

        const overallImpact = (0.60 * ebitdaImpact) + (0.25 * revenueImpact) + (0.15 * growthImpact);
        const estimatedNewValue = currentFairValue * overallImpact;
        const change = estimatedNewValue - currentFairValue;
        const changePercent = ((change / currentFairValue) * 100);

        const previewNewVal = document.getElementById('preview-new-value');
        if (previewNewVal) previewNewVal.textContent = formatCurrency(estimatedNewValue);

        const changeElement = document.getElementById('preview-change');
        if (changeElement) {
            const changeColor = change >= 0 ? '#4ade80' : '#f87171';
            const changeSign = change >= 0 ? '+' : '';
            changeElement.textContent = `${changeSign}${changePercent.toFixed(1)}%`;
            changeElement.style.color = changeColor;
        }
    } catch (error) {
        console.error('Error updating valuation preview:', error);
    }
}

function formatCurrency(value) {
    if (!value || isNaN(value)) return '$0';

    const absValue = Math.abs(value);
    if (absValue >= 1e9) {
        return (value >= 0 ? '$' : '-$') + (absValue / 1e9).toFixed(2) + 'B';
    } else if (absValue >= 1e6) {
        return (value >= 0 ? '$' : '-$') + (absValue / 1e6).toFixed(2) + 'M';
    } else if (absValue >= 1e3) {
        return (value >= 0 ? '$' : '-$') + (absValue / 1e3).toFixed(2) + 'K';
    } else {
        return (value >= 0 ? '$' : '-$') + absValue.toFixed(2);
    }
}

function closeModal() {
    document.getElementById('company-modal').classList.remove('active');
}

function closeValuationModal() {
    document.getElementById('valuation-modal').classList.remove('active');
    closeDCFModal();
}

// ============================================
// SETTINGS MODAL + API
// ============================================

function showSettingsModal() {
    document.getElementById('settings-modal').classList.add('active');
    loadSettings();
}

function closeSettingsModal() {
    document.getElementById('settings-modal').classList.remove('active');
}

async function loadSettings() {
    try {
        const res = await fetch('/api/settings');
        if (!res.ok) throw new Error('Failed to load settings');
        const s = await res.json();
        appSettings = s || {};

        document.getElementById('th-strong-buy').value = s.recommendation_thresholds.strong_buy;
        document.getElementById('th-buy').value = s.recommendation_thresholds.buy;
        document.getElementById('th-hold').value = s.recommendation_thresholds.hold;
        document.getElementById('th-underweight').value = s.recommendation_thresholds.underweight;

        document.getElementById('w-dcf').value = s.valuation_weights.dcf;
        document.getElementById('w-ev-ebitda').value = s.valuation_weights.ev_ebitda;
        document.getElementById('w-pe').value = s.valuation_weights.pe;
        // Recompute on save checkbox (defaults to false)
        const recomputeEl = document.getElementById('recompute-on-save');
        if (recomputeEl) recomputeEl.checked = !!s.recompute_on_save;

    } catch (err) {
        console.error('Error loading settings:', err);
        alert('Could not load settings');
    }
}

async function saveSettings(e) {
    e.preventDefault();
    try {
        const payload = {
            recommendation_thresholds: {
                strong_buy: parseFloat(document.getElementById('th-strong-buy').value),
                buy: parseFloat(document.getElementById('th-buy').value),
                hold: parseFloat(document.getElementById('th-hold').value),
                underweight: parseFloat(document.getElementById('th-underweight').value)
            },
            valuation_weights: {
                dcf: parseFloat(document.getElementById('w-dcf').value),
                ev_ebitda: parseFloat(document.getElementById('w-ev-ebitda').value),
                pe: parseFloat(document.getElementById('w-pe').value)
            }
        };

        // Add recompute on save flag
        const recomputeEl = document.getElementById('recompute-on-save');
        payload.recompute_on_save = recomputeEl ? !!recomputeEl.checked : false;

        // Basic validation: weights sum to ~1
        const sum = payload.valuation_weights.dcf + payload.valuation_weights.ev_ebitda + payload.valuation_weights.pe;
        if (Math.abs(sum - 1.0) > 0.01) {
            if (!confirm('Weights do not sum to 1.0. Save anyway?')) return;
        }

        showLoadingState('Saving settings...');
        const res = await fetch('/api/settings', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        hideLoadingState();

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.error || 'Failed to save settings');
        }

        const result = await res.json();
        // Update local cached settings
        appSettings = result.settings || payload;
        closeSettingsModal();
        loadDashboard();
        loadCompanies();
        alert('Settings saved');

    } catch (err) {
        hideLoadingState();
        console.error('Error saving settings:', err);
        alert('Error saving settings');
    }
}

// ============================================
// SAVE COMPANY
// ============================================

async function saveCompany(e) {
    e.preventDefault();
    console.log('💾 Save button clicked - starting save process');

    const companyId = document.getElementById('company-id').value;
    console.log('Company ID:', companyId || 'NEW');

    // Helper function to add field only if it has a value
    const addFieldIfPresent = (data, fieldId, transform = parseFloat) => {
        const element = document.getElementById(fieldId);
        const value = element ? element.value.trim() : '';

        if (value !== '' && value !== null && value !== undefined) {
            const transformed = transform(value);
            // Only add if transformation resulted in a valid number
            if (!isNaN(transformed)) {
                data[fieldId] = transformed;
            }
        }
    };

    // Build data object - only include fields that have values
    const data = {};

    // Name and sector (required for create, optional for update)
    const nameVal = document.getElementById('name').value.trim();
    const sectorVal = document.getElementById('sector').value.trim();
    if (nameVal) data.name = nameVal;
    if (sectorVal) data.sector = sectorVal;

    // Financial fields - only include if user entered a value
    addFieldIfPresent(data, 'revenue');
    addFieldIfPresent(data, 'ebitda');
    addFieldIfPresent(data, 'depreciation');
    addFieldIfPresent(data, 'working_capital_change');
    addFieldIfPresent(data, 'shares_outstanding');
    addFieldIfPresent(data, 'debt');
    addFieldIfPresent(data, 'cash');
    addFieldIfPresent(data, 'market_cap_estimate');
    addFieldIfPresent(data, 'beta');
    addFieldIfPresent(data, 'comparable_ev_ebitda');
    addFieldIfPresent(data, 'comparable_pe');
    addFieldIfPresent(data, 'comparable_peg');

    // Percentage fields - convert to decimal if present
    const pctFields = ['capex_pct', 'profit_margin', 'growth_rate_y1', 'growth_rate_y2',
                       'growth_rate_y3', 'terminal_growth', 'tax_rate', 'risk_free_rate',
                       'market_risk_premium', 'country_risk_premium', 'size_premium'];

    pctFields.forEach(fieldId => {
        const element = document.getElementById(fieldId);
        const value = element ? element.value.trim() : '';
        if (value !== '' && value !== null && value !== undefined) {
            const num = parseFloat(value);
            if (!isNaN(num)) {
                data[fieldId] = num / 100; // Convert percentage to decimal
            }
        }
    });

    console.log('📊 Form data collected:', {
        name: data.name,
        revenue: data.revenue,
        growth_y1: data.growth_rate_y1
    });

    try {
        console.log('⏳ Showing loading state...');
        showLoadingState('Saving company data...');
        
        const url = companyId ? `/api/company/${companyId}` : '/api/company';
        const method = companyId ? 'PUT' : 'POST';
        
        const response = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        
        if (!response.ok) {
            const error = await response.json();
            hideLoadingState();
            console.error('❌ Save failed:', error);

            if (error.details) {
                let errorMsg = 'Validation errors:\n\n';
                error.details.forEach(err => {
                    // Get the actual error message
                    const msg = err.msg || err.message || JSON.stringify(err);
                    errorMsg += `• ${msg}\n`;
                });
                alert(errorMsg);
            } else {
                alert(error.error || 'Error saving company');
            }
            return;
        }
        
        const result = await response.json();

        console.log('✅ Save response received:', result);

        // Backend automatically runs valuation on save/update
        // Check if valuation results are included in the response
        if (result.valuation) {
            // Valuation was successful - show results
            hideLoadingState();
            closeModal();

            console.log('✅ Showing valuation results from save response');
            showValuationResults(result.valuation);

            const actionMsg = companyId ? 'updated and revalued' : 'created and valued';
            console.log(`✅ Company ${actionMsg} successfully!`);
        } else if (result.message && result.message.includes('revaluation failed')) {
            // Save succeeded but valuation failed - inform user
            hideLoadingState();
            closeModal();
            console.warn('⚠️ Save succeeded but valuation failed:', result.error);
            alert('Company saved successfully, but automatic valuation failed. Please click "Value" button to generate valuation.');
        } else {
            // New company created - need to run initial valuation
            const targetCompanyId = result.id;

            try {
                document.getElementById('loading-text').textContent = 'Calculating fair value...';

                const valResponse = await fetch(`/api/valuation/${targetCompanyId}`, { method: 'POST' });

                if (!valResponse.ok) {
                    const err = await valResponse.json();
                    throw new Error(err.error || 'Valuation failed');
                }

                const valResult = await valResponse.json();
                hideLoadingState();
                closeModal();

                showValuationResults(valResult);
                console.log('✅ New company created and valued successfully!');

            } catch (error) {
                hideLoadingState();
                closeModal();
                console.error('Error running valuation:', error);
                alert('Company created successfully, but valuation failed. Please click "Value" button to generate valuation.');
            }
        }

        loadCompanies();
        loadDashboard();
    } catch (error) {
        hideLoadingState();
        console.error('Error saving company:', error);
        alert('Error saving company');
    }
}

// ============================================
// MULTI-SELECT
// ============================================

function toggleSelectMode() {
    selectModeActive = !selectModeActive;
    selectedCompanyIds.clear();
    const btn = document.getElementById('select-mode-btn');
    btn.textContent = selectModeActive ? 'Cancel' : 'Select';
    btn.classList.toggle('active', selectModeActive);
    document.getElementById('bulk-action-bar').style.display = 'none';
    renderCompanies(filteredCompanies);
}

function toggleCompanySelection(companyId) {
    if (selectedCompanyIds.has(companyId)) {
        selectedCompanyIds.delete(companyId);
    } else {
        selectedCompanyIds.add(companyId);
    }
    const count = selectedCompanyIds.size;
    const bar = document.getElementById('bulk-action-bar');
    bar.style.display = count > 0 ? 'flex' : 'none';
    document.getElementById('bulk-count').textContent = `${count} selected`;
    // Update card visual
    const card = document.querySelector(`[data-company-id="${companyId}"]`);
    if (card) card.classList.toggle('selected', selectedCompanyIds.has(companyId));
}

function clearSelection() {
    selectedCompanyIds.clear();
    document.getElementById('bulk-action-bar').style.display = 'none';
    document.querySelectorAll('.company-card.selected').forEach(c => c.classList.remove('selected'));
}

async function bulkDeleteSelected() {
    const ids = [...selectedCompanyIds];
    if (ids.length === 0) return;
    if (!confirm(`Remove ${ids.length} company(s) from portfolio? This cannot be undone.`)) return;

    showLoadingState(`Removing ${ids.length} companies...`);
    let failed = 0;
    for (const id of ids) {
        try {
            const r = await fetch(`/api/company/${id}`, { method: 'DELETE' });
            if (!r.ok) failed++;
        } catch { failed++; }
    }
    hideLoadingState();
    selectModeActive = false;
    selectedCompanyIds.clear();
    const btn = document.getElementById('select-mode-btn');
    btn.textContent = 'Select';
    btn.className = 'btn-secondary';
    document.getElementById('bulk-action-bar').style.display = 'none';
    if (failed > 0) alert(`${failed} companies could not be removed.`);
    loadCompanies();
    loadDashboard();
}

function bulkWatchlistSelected() {
    const ids = [...selectedCompanyIds];
    if (ids.length === 0) return;
    const watchlist = JSON.parse(localStorage.getItem('watchlist') || '[]');
    let added = 0;
    ids.forEach(id => {
        if (!watchlist.includes(id)) { watchlist.push(id); added++; }
    });
    localStorage.setItem('watchlist', JSON.stringify(watchlist));
    clearSelection();
    renderCompanies(filteredCompanies);
    if (added > 0) alert(`${added} company(s) added to watchlist`);
}

// ============================================
// DELETE COMPANY
// ============================================

async function deleteCompany(companyId) {
    if (!confirm('⚠️ Are you sure you want to delete this company? This action cannot be undone.')) return;
    
    try {
        showLoadingState('Deleting company...');
        const response = await fetch(`/api/company/${companyId}`, {
            method: 'DELETE'
        });
        
        hideLoadingState();
        
        if (response.ok) {
            loadCompanies();
            loadDashboard();
        } else {
            alert('Error deleting company');
        }
    } catch (error) {
        hideLoadingState();
        console.error('Error deleting company:', error);
        alert('Error deleting company');
    }
}

// ============================================
// VALUATION FUNCTIONS - ENHANCED
// ============================================

async function runValuation(companyId) {
    try {
        // Fetch latest company data
        const response = await fetch(`/api/company/${companyId}`);
        if (!response.ok) throw new Error('Failed to fetch company data');

        const company = await response.json();

        // Trigger valuation logic
        const valuationResponse = await fetch(`/api/company/${companyId}/revalue`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(company)
        });

        if (!valuationResponse.ok) throw new Error('Failed to revalue company');

        const valuationResult = await valuationResponse.json();

        // Update local state with new valuation
        const index = allCompanies.findIndex(c => c.id === companyId);
        if (index !== -1) {
            allCompanies[index] = { ...allCompanies[index], ...valuationResult };
        }

        alert('Company revalued successfully!');
        applyFiltersAndSort();
    } catch (err) {
        console.error('Error revaluing company:', err);
        alert('Failed to revalue company');
    }
}

function ebitdaMethodLabel(method) {
    const labels = {
        'em:trend':          'EBITDA: trend direction',
        'em:3yavg':          'EBITDA: 3yr average',
        'em:cyc3yr':         'EBITDA: cycle average',
        'em:secular_decline':'EBITDA: secular decline',
        'em:recent':         'EBITDA: most recent year',
        'em:single':         'EBITDA: single year',
        'em:zero':           'EBITDA: zero',
    };
    return labels[method] || method;
}

function buildBlendBar(result) {
    // Try to infer blend weights from the three component values
    const dcfVal = result.dcf_price_per_share || 0;
    const evVal  = result.comp_ev_value > 0 && result.market_cap > 0 && result.current_price > 0
        ? result.comp_ev_value / (result.market_cap / result.current_price) : 0;
    const peVal  = result.comp_pe_value > 0 && result.market_cap > 0 && result.current_price > 0
        ? result.comp_pe_value / (result.market_cap / result.current_price) : 0;
    const final  = result.final_price_per_share || 0;

    // Can't build a meaningful bar without all three components
    if (!dcfVal && !evVal && !peVal) return '';

    // Build visual bar showing relative contribution
    const typeLabels = {
        'HYPERGROWTH':            'DCF 20% · EV/EBITDA 50% · P/E 30%',
        'GROWTH_TECH':            'DCF 40% · EV/EBITDA 35% · P/E 25%',
        'DISTRESSED':             'DCF 0% · EV/EBITDA 60% · P/E 40%',
        'CYCLICAL':               'DCF 35% · EV/EBITDA 45% · P/E 20%',
        'STORY':                  'DCF 15% · P/E (analyst anchor) 85%',
        'STABLE_VALUE':           'DCF 45% · EV/EBITDA 30% · P/E 25%',
        'STABLE_VALUE_LOWGROWTH': 'DCF 20% · EV/EBITDA 55% · P/E 25%',
    };
    const weightLabel = typeLabels[result.company_type] || 'DCF + EV/EBITDA + P/E blend';

    return `
        <div style="padding: 0.75rem 1rem; background: var(--bg-secondary); border-radius: 8px; font-size: 0.8rem; color: var(--text-secondary);">
            <span style="font-weight: 600; color: var(--text-primary);">Blend weights:</span> ${weightLabel}
        </div>`;
}

function showValuationResults(result) {
    const modal = document.getElementById('valuation-modal');
    const modalContent = modal.querySelector('.modal-content');
    modal.classList.add('active');
    document.getElementById('valuation-company-name').textContent = `${result.name} - Detailed Valuation`;

    const recClass = getRecommendationClass(result.recommendation);

    // Remove old rec classes and add current one
    modalContent.classList.remove('rec-buy', 'rec-hold', 'rec-sell');
    if (recClass) modalContent.classList.add('rec-' + recClass);

    const upsideColor = result.upside_pct >= 0 ? 'var(--positive)' : 'var(--negative)';

    // Calculate change from previous valuation if available
    let changeSection = '';
    if (previousValuation && previousValuation.final_equity_value) {
        const valuationChange = result.final_equity_value - previousValuation.final_equity_value;
        const valuationChangePct = (valuationChange / previousValuation.final_equity_value) * 100;
        const priceChange = result.final_price_per_share - previousValuation.final_price_per_share;
        const priceChangePct = (priceChange / previousValuation.final_price_per_share) * 100;
        const changeColor = valuationChange >= 0 ? '#4ade80' : '#f87171';
        const changeIcon = valuationChange >= 0 ? '📈' : '📉';

        changeSection = `
            <div class="valuation-change-banner" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 12px; padding: 20px; margin-bottom: 20px; color: white;">
                <h3 style="color: white; margin: 0 0 15px 0; display: flex; align-items: center; gap: 10px;">
                    ${changeIcon} Valuation Update
                </h3>
                <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px;">
                    <div>
                        <div style="font-size: 12px; opacity: 0.9; margin-bottom: 5px;">Previous Fair Value</div>
                        <div style="font-size: 20px; font-weight: bold;">$${formatNumber(previousValuation.final_equity_value)}</div>
                        <div style="font-size: 14px; opacity: 0.8;">$${previousValuation.final_price_per_share.toFixed(2)}/share</div>
                    </div>
                    <div>
                        <div style="font-size: 12px; opacity: 0.9; margin-bottom: 5px;">New Fair Value</div>
                        <div style="font-size: 20px; font-weight: bold; color: #4ade80;">$${formatNumber(result.final_equity_value)}</div>
                        <div style="font-size: 14px; opacity: 0.8;">$${result.final_price_per_share.toFixed(2)}/share</div>
                    </div>
                    <div>
                        <div style="font-size: 12px; opacity: 0.9; margin-bottom: 5px;">Change</div>
                        <div style="font-size: 24px; font-weight: bold; color: ${changeColor};">
                            ${valuationChange >= 0 ? '+' : ''}${valuationChangePct.toFixed(1)}%
                        </div>
                        <div style="font-size: 14px; opacity: 0.8;">
                            ${valuationChange >= 0 ? '+' : ''}$${formatNumber(valuationChange)}
                        </div>
                    </div>
                </div>
                <div style="margin-top: 15px; padding-top: 15px; border-top: 1px solid rgba(255,255,255,0.2); font-size: 13px; opacity: 0.85;">
                    ${previousValuation.recommendation !== result.recommendation ?
                        `<strong>📊 Recommendation changed:</strong> ${previousValuation.recommendation} → ${result.recommendation}` :
                        `<strong>📊 Recommendation:</strong> ${result.recommendation} (unchanged)`}
                </div>
            </div>
        `;
    }

    // Derive share count from valuation output (exact)
    const shares = (result.final_price_per_share > 0 && result.final_equity_value > 0)
        ? result.final_equity_value / result.final_price_per_share : 0;

    // AXIOM base values
    const axiomDcfPS  = result.dcf_price_per_share || 0;
    const axiomEvPS   = (shares > 0 && result.comp_ev_value > 0)  ? result.comp_ev_value  / shares : 0;
    const axiomPePS   = (shares > 0 && result.comp_pe_value > 0)  ? result.comp_pe_value  / shares : 0;
    const analystPS = result.analyst_target ? +result.analyst_target : 0;

    // Check for user's saved custom valuations
    const userDCF = getUserValuation(result.company_id || currentCompanyId);
    const userEV = getUserEVEBITDAValuation(result.company_id || currentCompanyId);
    const userPE = getUserPEValuation(result.company_id || currentCompanyId);

    // Use user values if available, otherwise AXIOM
    const dcfPS = userDCF ? userDCF.pricePerShare : axiomDcfPS;
    const evPS = userEV ? userEV.pricePerShare : axiomEvPS;
    const pePS = userPE ? userPE.pricePerShare : axiomPePS;

    // Calculate % differences from AXIOM
    const dcfDiff = axiomDcfPS > 0 ? ((dcfPS - axiomDcfPS) / axiomDcfPS) * 100 : 0;
    const evDiff = axiomEvPS > 0 ? ((evPS - axiomEvPS) / axiomEvPS) * 100 : 0;
    const peDiff = axiomPePS > 0 ? ((pePS - axiomPePS) / axiomPePS) * 100 : 0;

    // Blend weights lookup
    const WEIGHTS = {
        'HYPERGROWTH':            [0.20, 0.50, 0.30],
        'GROWTH_TECH':            [0.40, 0.35, 0.25],
        'DISTRESSED':             [0.00, 0.60, 0.40],
        'CYCLICAL':               [0.35, 0.45, 0.20],
        'STORY':                  [0.15, 0.00, 0.85],
        'STABLE_VALUE':           [0.45, 0.30, 0.25],
        'STABLE_VALUE_LOWGROWTH': [0.20, 0.55, 0.25],
    };
    const [wDCF, wEV, wPE] = WEIGHTS[result.company_type] || [0.40, 0.35, 0.25];
    const blended = dcfPS * wDCF + evPS * wEV + pePS * wPE;

    // Build math string using current (possibly user-adjusted) values
    const mathParts = [];
    if (wDCF > 0) mathParts.push(`${(wDCF*100).toFixed(0)}% × $${dcfPS.toFixed(2)}`);
    if (wEV  > 0 && evPS > 0) mathParts.push(`${(wEV*100).toFixed(0)}% × $${evPS.toFixed(2)}`);
    if (wPE  > 0 && pePS > 0) mathParts.push(`${(wPE*100).toFixed(0)}% × $${pePS.toFixed(2)}`);
    const mathStr = mathParts.join(' + ') + ` = $${blended.toFixed(2)}`;

    // Analyst anchor step (shown only when analyst target exists)
    const anchorWeights = { 'STORY': 0.70, 'HYPERGROWTH': 0.30, 'DISTRESSED': 0.40 };
    const aWeight = anchorWeights[result.company_type] || 0.15;

    // Calculate final price using user's blended value
    const finalPS = analystPS > 0
        ? blended * (1 - aWeight) + analystPS * aWeight
        : blended;

    const anchorStr = analystPS > 0
        ? `${(100-aWeight*100).toFixed(0)}% × $${blended.toFixed(2)} + ${(aWeight*100).toFixed(0)}% × $${analystPS.toFixed(2)} = $${finalPS.toFixed(2)}`
        : null;

    // Helper to show user vs AXIOM subscript
    const userBadge = (isUser, diff) => isUser
        ? `<div style="font-size: 0.65rem; margin-top: 4px; color: ${diff >= 0 ? '#22c55e' : '#ef4444'};">Your value · ${diff >= 0 ? '+' : ''}${diff.toFixed(1)}% vs AXIOM</div>`
        : `<div style="font-size: 0.65rem; margin-top: 4px; color: var(--text-muted);">AXIOM</div>`;

    // Recalculate upside based on user's fair value
    const currentPrice = result.current_price || 0;
    const userUpside = currentPrice > 0 ? ((finalPS - currentPrice) / currentPrice) * 100 : 0;
    const hasUserValues = userDCF || userEV || userPE;

    // Determine recommendation based on user's upside
    let userRec = result.recommendation;
    if (hasUserValues) {
        if (userUpside >= 15) userRec = 'BUY';
        else if (userUpside >= -10) userRec = 'HOLD';
        else userRec = 'SELL';
    }
    const displayUpside = hasUserValues ? userUpside : result.upside_pct;
    const displayRec = hasUserValues ? userRec : result.recommendation;
    const displayRecClass = displayRec === 'BUY' ? 'buy' : displayRec === 'SELL' ? 'sell' : 'hold';

    const html = `
        ${changeSection}

        <!-- Valuation Header -->
        <div class="valuation-header rec-${displayRecClass}">
            <div class="recommendation">${displayRec || 'N/A'}${hasUserValues ? ' <span style="font-size: 0.6rem; opacity: 0.8;">(Your Analysis)</span>' : ''}</div>
            <div class="upside">
                ${displayUpside >= 0 ? '↑' : '↓'} ${displayUpside >= 0 ? '+' : ''}${displayUpside.toFixed(1)}% ${displayUpside >= 0 ? 'Upside' : 'Downside'}
            </div>
        </div>

        <!-- Summary Metrics -->
        <div class="summary-grid">
            <div class="summary-item">
                <div class="summary-label">Fair Price / Share${hasUserValues ? ' <span style="font-size: 0.6rem; color: var(--accent-primary);">(Yours)</span>' : ''}</div>
                <div class="summary-value" style="${hasUserValues ? 'color: var(--accent-primary);' : ''}">$${finalPS.toFixed(2)}</div>
            </div>
            <div class="summary-item">
                <div class="summary-label">Current Price</div>
                <div class="summary-value">$${result.current_price.toFixed(2)}</div>
            </div>
            <div class="summary-item">
                <div class="summary-label">Fair Value (Equity)</div>
                <div class="summary-value">$${formatNumber(finalPS * shares)}</div>
            </div>
            <div class="summary-item">
                <div class="summary-label">Market Cap</div>
                <div class="summary-value">$${formatNumber(result.market_cap)}</div>
            </div>
        </div>

        <!-- HOW THE FAIR VALUE WAS CALCULATED -->
        <div style="margin: 1.5rem 0; border: 1px solid var(--border-color); border-radius: 10px; overflow: hidden;">
            <div style="background: var(--bg-secondary); padding: 12px 16px; border-bottom: 1px solid var(--border-color); display: flex; align-items: center; gap: 10px;">
                <span style="font-size: 0.7rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: var(--text-muted);">Fair Value Calculation</span>
                ${result.company_type ? `<span style="font-size: 0.75rem; font-weight: 600; color: var(--accent-primary); background: var(--bg-primary); border: 1px solid var(--border-color); border-radius: 4px; padding: 2px 8px;">${result.company_type.replace(/_/g,' ')}</span>` : ''}
                ${result.sub_sector_tag ? `<span style="font-size: 0.75rem; color: var(--text-muted); background: var(--bg-primary); border: 1px solid var(--border-color); border-radius: 4px; padding: 2px 8px;">${result.sub_sector_tag.replace(/_/g,' ')}</span>` : ''}
            </div>

            <!-- Step 1: Three methods -->
            <div style="padding: 16px; border-bottom: 1px solid var(--border-color);">
                <div style="font-size: 0.75rem; color: var(--text-muted); margin-bottom: 10px; font-weight: 600;">STEP 1 — Three valuation methods</div>
                <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 1px; background: var(--border-color); border-radius: 6px; overflow: hidden;">
                    <div class="method-card method-card-dcf" onclick="toggleDCFDetails()" style="background: var(--bg-primary); padding: 14px; text-align: center; cursor: pointer; transition: all 0.2s ease;" title="Click to see full DCF breakdown">
                        <div style="font-size: 0.7rem; color: var(--text-muted); margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.05em;">DCF <span style="font-size: 0.6rem; color: var(--accent-primary);">↗ details</span></div>
                        <div style="font-size: 1.35rem; font-weight: 700; ${userDCF ? 'color: var(--accent-primary);' : ''}">${dcfPS > 0 ? '$' + dcfPS.toFixed(2) : '—'}</div>
                        ${userBadge(!!userDCF, dcfDiff)}
                    </div>
                    <div class="method-card method-card-ev" onclick="toggleEVEBITDADetails()" style="background: var(--bg-primary); padding: 14px; text-align: center; cursor: pointer; transition: all 0.2s ease;" title="Click to see EV/EBITDA breakdown">
                        <div style="font-size: 0.7rem; color: var(--text-muted); margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.05em;">EV / EBITDA <span style="font-size: 0.6rem; color: var(--accent-primary);">↗ details</span></div>
                        <div style="font-size: 1.35rem; font-weight: 700; ${userEV ? 'color: var(--accent-primary);' : ''}">${evPS > 0 ? '$' + evPS.toFixed(2) : '—'}</div>
                        ${userBadge(!!userEV, evDiff)}
                    </div>
                    <div class="method-card method-card-pe" onclick="togglePEDetails()" style="background: var(--bg-primary); padding: 14px; text-align: center; cursor: pointer; transition: all 0.2s ease;" title="Click to see P/E breakdown">
                        <div style="font-size: 0.7rem; color: var(--text-muted); margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.05em;">P / E <span style="font-size: 0.6rem; color: var(--accent-primary);">↗ details</span></div>
                        <div style="font-size: 1.35rem; font-weight: 700; ${userPE ? 'color: var(--accent-primary);' : ''}">${pePS > 0 ? '$' + pePS.toFixed(2) : '—'}</div>
                        ${userBadge(!!userPE, peDiff)}
                    </div>
                </div>
            </div>

            <!-- Step 2: Blend -->
            <div style="padding: 16px; border-bottom: 1px solid var(--border-color);">
                <div style="font-size: 0.75rem; color: var(--text-muted); margin-bottom: 10px; font-weight: 600;">STEP 2 — Weighted blend</div>
                <div style="font-family: monospace; font-size: 0.875rem; color: var(--text-primary); background: var(--bg-secondary); padding: 10px 14px; border-radius: 6px; line-height: 1.7;">
                    ${mathStr}
                </div>
            </div>

            <!-- Step 3: Analyst anchor (if applicable) -->
            ${anchorStr ? `
            <div style="padding: 16px; border-bottom: 1px solid var(--border-color);">
                <div style="font-size: 0.75rem; color: var(--text-muted); margin-bottom: 10px; font-weight: 600;">STEP 3 — Analyst consensus anchor</div>
                <div style="font-family: monospace; font-size: 0.875rem; color: var(--text-primary); background: var(--bg-secondary); padding: 10px 14px; border-radius: 6px; line-height: 1.7;">
                    ${anchorStr}
                </div>
                <div style="font-size: 0.72rem; color: var(--text-muted); margin-top: 6px;">Wall St. consensus: $${analystPS.toFixed(2)}</div>
            </div>` : ''}

            <!-- Result -->
            <div style="padding: 16px; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px;">
                <div>
                    <div style="font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 4px;">Fair Value${hasUserValues ? ' (Yours)' : ''}</div>
                    <div style="font-size: 2rem; font-weight: 800; color: var(--accent-primary);">$${finalPS.toFixed(2)}</div>
                    ${hasUserValues ? `<div style="font-size: 0.7rem; color: var(--text-muted); margin-top: 2px;">AXIOM: $${result.final_price_per_share?.toFixed(2) || '—'}</div>` : ''}
                </div>
                <div style="text-align: right;">
                    <div style="font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 4px;">vs Market</div>
                    <div style="font-size: 1.4rem; font-weight: 700; color: ${displayUpside >= 0 ? '#22c55e' : '#ef4444'};">
                        ${displayUpside >= 0 ? '+' : ''}${displayUpside.toFixed(1)}%
                    </div>
                    <div style="font-size: 0.75rem; color: var(--text-muted);">Current: $${result.current_price.toFixed(2)}</div>
                </div>
            </div>
            ${result.ebitda_method ? `<div style="padding: 8px 16px; background: var(--bg-secondary); border-top: 1px solid var(--border-color); font-size: 0.7rem; color: var(--text-muted);">EBITDA normalization: ${ebitdaMethodLabel(result.ebitda_method)}</div>` : ''}
        </div>

        <!-- Key Financial Metrics -->
        <div style="font-size: 0.7rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: var(--text-muted); margin-bottom: 10px;">Key Metrics</div>
        <div class="metrics-grid">
            <div class="metric-item">
                <div class="summary-label">WACC</div>
                <div class="summary-value">${result.wacc ? (result.wacc * 100).toFixed(2) + '%' : '—'}</div>
            </div>
            <div class="metric-item">
                <div class="summary-label">EV/EBITDA</div>
                <div class="summary-value">${result.ev_ebitda ? result.ev_ebitda.toFixed(1) + 'x' : '—'}</div>
            </div>
            <div class="metric-item">
                <div class="summary-label">P/E Ratio</div>
                <div class="summary-value">${result.pe_ratio ? result.pe_ratio.toFixed(1) + 'x' : '—'}</div>
            </div>
            <div class="metric-item">
                <div class="summary-label">FCF Yield</div>
                <div class="summary-value">${result.fcf_yield ? result.fcf_yield.toFixed(2) + '%' : '—'}</div>
            </div>
            <div class="metric-item">
                <div class="summary-label">ROE</div>
                <div class="summary-value">${result.roe ? result.roe.toFixed(1) + '%' : '—'}</div>
            </div>
            <div class="metric-item">
                <div class="summary-label">ROIC</div>
                <div class="summary-value">${result.roic ? result.roic.toFixed(1) + '%' : '—'}</div>
            </div>
            <div class="metric-item">
                <div class="summary-label">Debt / Equity</div>
                <div class="summary-value">${result.debt_to_equity ? result.debt_to_equity.toFixed(2) + 'x' : '—'}</div>
            </div>
            <div class="metric-item">
                <div class="summary-label">Altman Z-Score</div>
                <div class="summary-value ${result.z_score >= 2.99 ? 'text-positive' : result.z_score < 1.81 ? 'text-negative' : ''}">${result.z_score ? result.z_score.toFixed(2) : '—'}</div>
            </div>
        </div>

        <div style="margin-top: 2rem; padding-top: 1.5rem; border-top: 1px solid var(--border-color);">
            <button class="btn-submit" onclick="closeValuationModal()">Close</button>
        </div>
    `;
    
    document.getElementById('valuation-results').innerHTML = html;
}

// ============================================
// DCF DETAILS MODAL
// ============================================

let dcfDetailsCache = null;
let dcfBaseInputs = null;

// DCF Recalculation Engine (client-side)
function recalculateDCF() {
    if (!dcfBaseInputs) return;

    const base = dcfBaseInputs;

    // Get user-adjusted values from inputs
    const wacc = parseFloat(document.getElementById('sens-wacc-input')?.value || base.wacc * 100) / 100;
    const termGrowth = parseFloat(document.getElementById('sens-term-growth-input')?.value || base.terminal_growth * 100) / 100;
    const revenueGrowthY1 = parseFloat(document.getElementById('sens-revenue-growth-input')?.value || base.growth_y1 * 100) / 100;
    const ebitdaMargin = parseFloat(document.getElementById('sens-margin-input')?.value || base.ebitda_margin * 100) / 100;

    // Scale growth rates proportionally based on Y1 change
    const growthRatio = base.growth_y1 > 0 ? revenueGrowthY1 / base.growth_y1 : 1;
    const g1 = revenueGrowthY1;
    const g2 = base.growth_y2 * growthRatio;
    const g3 = base.growth_y3 * growthRatio;
    const growthSchedule = [g1, g1, g2, g2, g3, g3, (g3 + termGrowth)/2, termGrowth + 0.01, termGrowth + 0.005, termGrowth];

    // Recalculate projections
    let currentRevenue = base.revenue;
    let totalPvFcf = 0;
    const projectedFcf = [];
    const newDetails = [];

    for (let year = 1; year <= 10; year++) {
        const growthRate = growthSchedule[year - 1];
        currentRevenue *= (1 + growthRate);

        const yearEbitda = currentRevenue * ebitdaMargin;
        const yearDa = currentRevenue * base.da_ratio;
        const yearEbit = yearEbitda - yearDa;
        const yearNopat = yearEbit * (1 - base.tax_rate);
        const yearCapex = currentRevenue * base.capex_pct;
        const yearWc = base.wc_change * (currentRevenue / base.revenue);
        const yearFcf = yearNopat + yearDa - yearCapex - yearWc;

        const discountFactor = 1 / Math.pow(1 + wacc, year);
        const pvFcf = yearFcf * discountFactor;
        totalPvFcf += pvFcf;

        projectedFcf.push(yearFcf);
        newDetails.push({
            year, growth_rate: growthRate, revenue: currentRevenue,
            ebitda: yearEbitda, da: yearDa, ebit: yearEbit, nopat: yearNopat,
            capex: yearCapex, wc_change: yearWc, fcf: yearFcf,
            discount_factor: discountFactor, pv_fcf: pvFcf
        });
    }

    // Terminal value
    const terminalFcf = projectedFcf[9] * (1 + termGrowth);
    const terminalValue = terminalFcf / (wacc - termGrowth);
    const pvTerminal = terminalValue / Math.pow(1 + wacc, 10);

    // Enterprise and equity value
    const enterpriseValue = totalPvFcf + pvTerminal;
    const equityValue = enterpriseValue + base.cash - base.debt;
    const pricePerShare = equityValue / base.shares;

    // Format helpers
    const fmt = (val) => {
        if (Math.abs(val) >= 1e12) return '$' + (val / 1e12).toFixed(2) + 'T';
        if (Math.abs(val) >= 1e9) return '$' + (val / 1e9).toFixed(2) + 'B';
        if (Math.abs(val) >= 1e6) return '$' + (val / 1e6).toFixed(2) + 'M';
        return '$' + val.toFixed(2);
    };
    const pct = (val) => (val * 100).toFixed(2) + '%';

    // Update projection table cells
    newDetails.forEach((d, i) => {
        const col = i + 1;
        const updateCell = (row, val, format) => {
            const cell = document.querySelector(`#dcf-table tr[data-row="${row}"] td:nth-child(${col + 1})`);
            if (cell) cell.textContent = format === 'pct' ? pct(val) : fmt(val);
        };
        updateCell('growth', d.growth_rate, 'pct');
        updateCell('revenue', d.revenue, 'dollar');
        updateCell('ebitda', d.ebitda, 'dollar');
        updateCell('da', d.da, 'dollar');
        updateCell('ebit', d.ebit, 'dollar');
        updateCell('nopat', d.nopat, 'dollar');
        updateCell('da2', d.da, 'dollar');
        updateCell('capex', d.capex, 'dollar');
        updateCell('wc', d.wc_change, 'dollar');
        updateCell('fcf', d.fcf, 'dollar');
        updateCell('df', d.discount_factor, 'pct');
        updateCell('pvfcf', d.pv_fcf, 'dollar');
    });

    // Update summary boxes
    document.getElementById('sens-total-pv-fcf').textContent = fmt(totalPvFcf);
    document.getElementById('sens-terminal-value').textContent = fmt(terminalValue);
    document.getElementById('sens-pv-terminal').textContent = fmt(pvTerminal);

    // Update final valuation
    const baseEquity = dcfDetailsCache?.calculated?.equity_value?.value || base.market_cap;
    const change = ((equityValue - baseEquity) / baseEquity) * 100;
    const changeClass = change >= 0 ? 'color: #22c55e;' : 'color: #ef4444;';

    document.getElementById('sens-equity-value').innerHTML = `
        <div style="font-size: 1.4rem; font-weight: 700;">${fmt(equityValue)}</div>
        <div style="font-size: 0.85rem; ${changeClass}">${change >= 0 ? '+' : ''}${change.toFixed(1)}% vs base</div>
    `;
    document.getElementById('sens-price-per-share').innerHTML = `
        <div style="font-size: 1.4rem; font-weight: 700;">$${pricePerShare.toFixed(2)}</div>
        <div style="font-size: 0.85rem; color: var(--text-muted);">per share</div>
    `;
}

function syncSensInput(field) {
    const slider = document.getElementById(`sens-${field}`);
    const input = document.getElementById(`sens-${field}-input`);
    if (slider && input) input.value = parseFloat(slider.value).toFixed(2);
    recalculateDCF();
}

function syncSensSlider(field) {
    const slider = document.getElementById(`sens-${field}`);
    const input = document.getElementById(`sens-${field}-input`);
    if (slider && input) slider.value = parseFloat(input.value) || 0;
    recalculateDCF();
}

function resetSensitivity() {
    if (!dcfBaseInputs) return;
    const wacc = dcfBaseInputs.wacc * 100;
    const termGrowth = dcfBaseInputs.terminal_growth * 100;
    const growthY1 = dcfBaseInputs.growth_y1 * 100;
    const margin = dcfBaseInputs.ebitda_margin * 100;

    document.getElementById('sens-wacc').value = wacc;
    document.getElementById('sens-wacc-input').value = wacc.toFixed(2);
    document.getElementById('sens-term-growth').value = termGrowth;
    document.getElementById('sens-term-growth-input').value = termGrowth.toFixed(2);
    document.getElementById('sens-revenue-growth').value = growthY1;
    document.getElementById('sens-revenue-growth-input').value = growthY1.toFixed(2);
    document.getElementById('sens-margin').value = margin;
    document.getElementById('sens-margin-input').value = margin.toFixed(2);

    // Reset display to exact base values
    const baseEquity = dcfDetailsCache?.calculated?.equity_value?.value;
    const basePPS = dcfDetailsCache?.calculated?.price_per_share?.value;
    const fmt = (val) => {
        if (Math.abs(val) >= 1e12) return '$' + (val / 1e12).toFixed(2) + 'T';
        if (Math.abs(val) >= 1e9) return '$' + (val / 1e9).toFixed(2) + 'B';
        if (Math.abs(val) >= 1e6) return '$' + (val / 1e6).toFixed(2) + 'M';
        return '$' + val.toFixed(2);
    };
    if (baseEquity) {
        document.getElementById('sens-equity-value').innerHTML = `
            <div style="font-size: 1.4rem; font-weight: 700;">${fmt(baseEquity)}</div>
            <div style="font-size: 0.85rem; color: var(--text-muted);">AXIOM Base</div>
        `;
    }
    if (basePPS) {
        document.getElementById('sens-price-per-share').innerHTML = `
            <div style="font-size: 1.4rem; font-weight: 700;">$${basePPS.toFixed(2)}</div>
            <div style="font-size: 0.85rem; color: var(--text-muted);">per share</div>
        `;
    }
}

function saveUserValuation() {
    if (!dcfBaseInputs || !currentCompanyId) return;

    const base = dcfBaseInputs;
    const wacc = parseFloat(document.getElementById('sens-wacc-input')?.value || base.wacc * 100) / 100;
    const termGrowth = parseFloat(document.getElementById('sens-term-growth-input')?.value || base.terminal_growth * 100) / 100;
    const revenueGrowthY1 = parseFloat(document.getElementById('sens-revenue-growth-input')?.value || base.growth_y1 * 100) / 100;
    const ebitdaMargin = parseFloat(document.getElementById('sens-margin-input')?.value || base.ebitda_margin * 100) / 100;

    // Scale growth rates proportionally based on Y1 change
    const growthRatio = base.growth_y1 > 0 ? revenueGrowthY1 / base.growth_y1 : 1;
    const g1 = revenueGrowthY1;
    const g2 = base.growth_y2 * growthRatio;
    const g3 = base.growth_y3 * growthRatio;
    const growthSchedule = [g1, g1, g2, g2, g3, g3, (g3 + termGrowth)/2, termGrowth + 0.01, termGrowth + 0.005, termGrowth];

    let currentRevenue = base.revenue;
    let totalPvFcf = 0;
    const projectedFcf = [];

    for (let year = 1; year <= 10; year++) {
        const growthRate = growthSchedule[year - 1];
        currentRevenue *= (1 + growthRate);
        const yearEbitda = currentRevenue * ebitdaMargin;
        const yearDa = currentRevenue * base.da_ratio;
        const yearEbit = yearEbitda - yearDa;
        const yearNopat = yearEbit * (1 - base.tax_rate);
        const yearCapex = currentRevenue * base.capex_pct;
        const yearWc = base.wc_change * (currentRevenue / base.revenue);
        const yearFcf = yearNopat + yearDa - yearCapex - yearWc;
        const discountFactor = 1 / Math.pow(1 + wacc, year);
        totalPvFcf += yearFcf * discountFactor;
        projectedFcf.push(yearFcf);
    }

    const terminalFcf = projectedFcf[9] * (1 + termGrowth);
    const terminalValue = terminalFcf / (wacc - termGrowth);
    const pvTerminal = terminalValue / Math.pow(1 + wacc, 10);
    const enterpriseValue = totalPvFcf + pvTerminal;
    const equityValue = enterpriseValue + base.cash - base.debt;
    const pricePerShare = equityValue / base.shares;

    // Save to localStorage
    const userValuations = JSON.parse(localStorage.getItem('userValuations') || '{}');
    userValuations[currentCompanyId] = {
        equityValue,
        pricePerShare,
        wacc: wacc * 100,
        terminalGrowth: termGrowth * 100,
        revenueGrowthY1: revenueGrowthY1 * 100,
        ebitdaMargin: ebitdaMargin * 100,
        savedAt: new Date().toISOString()
    };
    localStorage.setItem('userValuations', JSON.stringify(userValuations));

    // Show confirmation and update button UI
    const isUpdate = document.getElementById('user-valuation-indicator')?.style.display !== 'none';
    const btn = event.target.closest('button');
    const origHtml = btn.innerHTML;
    btn.innerHTML = isUpdate ? '✓ Updated!' : '✓ Saved!';
    btn.style.background = '#16a34a';

    // Show remove button and indicator
    const removeBtn = document.getElementById('remove-valuation-btn');
    const indicator = document.getElementById('user-valuation-indicator');
    if (removeBtn) removeBtn.style.display = 'block';
    if (indicator) indicator.style.display = 'block';

    // Update save button text
    setTimeout(() => {
        btn.innerHTML = 'Update Your Valuation';
        btn.style.background = 'linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%)';
    }, 1500);

    // Refresh company cards to show new valuation
    if (typeof loadCompanies === 'function') loadCompanies();
}

function removeUserValuation() {
    if (!currentCompanyId) return;

    clearUserValuation(currentCompanyId);

    // Reset inputs to AXIOM base values
    resetSensitivity();

    // Update UI
    const removeBtn = document.getElementById('remove-valuation-btn');
    const indicator = document.getElementById('user-valuation-indicator');
    const saveBtn = document.querySelector('#save-valuation-btn');

    if (removeBtn) removeBtn.style.display = 'none';
    if (indicator) indicator.style.display = 'none';
    if (saveBtn) saveBtn.innerHTML = 'Save Your Valuation';

    // Show confirmation
    if (removeBtn) {
        const origHtml = removeBtn.innerHTML;
        removeBtn.innerHTML = '✓ Removed';
        removeBtn.style.display = 'block';
        setTimeout(() => {
            removeBtn.style.display = 'none';
        }, 1500);
    }
}

function getUserValuation(companyId) {
    const userValuations = JSON.parse(localStorage.getItem('userValuations') || '{}');
    return userValuations[companyId] || null;
}

function clearUserValuation(companyId) {
    const userValuations = JSON.parse(localStorage.getItem('userValuations') || '{}');
    delete userValuations[companyId];
    localStorage.setItem('userValuations', JSON.stringify(userValuations));
    if (typeof loadCompanies === 'function') loadCompanies();
}

function toggleDCFDetails() {
    if (!currentCompanyId) return;
    window.open(`/dcf/${currentCompanyId}`, '_blank');
}

function closeDCFModal() {
    const modal = document.getElementById('dcf-details-modal');
    if (modal) {
        modal.classList.remove('active');
        modal.style.display = 'none';
    }
}

function renderDCFDetails(dcf) {
    const ticker = dcf.ticker || '';
    const baseUrl = 'https://finance.yahoo.com/quote/' + ticker;
    const inputs = dcf.inputs || {};
    const assumptions = dcf.assumptions || {};

    // Helper to format large numbers
    const fmt = (val) => {
        if (val === null || val === undefined) return '—';
        if (Math.abs(val) >= 1e12) return '$' + (val / 1e12).toFixed(2) + 'T';
        if (Math.abs(val) >= 1e9) return '$' + (val / 1e9).toFixed(2) + 'B';
        if (Math.abs(val) >= 1e6) return '$' + (val / 1e6).toFixed(2) + 'M';
        return '$' + val.toFixed(2);
    };

    // Helper to format percentages
    const pct = (val) => val !== null && val !== undefined ? (val * 100).toFixed(2) + '%' : '—';

    // Helper: value as link (yahoo) or tooltip span
    const valLink = (val, label, source, urlPath, note) => {
        const display = typeof val === 'number' ? (Math.abs(val) < 1 ? pct(val) : (Math.abs(val) > 1000 ? fmt(val) : val.toFixed(2))) : val;
        if (source === 'yahoo_finance' && ticker && urlPath !== undefined) {
            return `<a href="${baseUrl}${urlPath || ''}" target="_blank" rel="noopener" style="color: var(--accent-primary); text-decoration: underline; cursor: pointer;" title="${label}">${display}</a>`;
        }
        return `<span style="color: var(--text-primary); border-bottom: 1px dotted var(--text-muted); cursor: help;" title="${note || label}">${display}</span>`;
    };

    // Check if this is an alternative model (banks, REITs)
    if (dcf.model_type === 'alternative') {
        return `
            <div style="padding: 20px; background: var(--bg-secondary);">
                <div style="font-size: 0.8rem; font-weight: 600; color: var(--text-muted); margin-bottom: 12px;">Alternative Valuation Model</div>
                <div style="background: var(--bg-primary); border-radius: 8px; padding: 16px;">
                    <p style="margin: 0; color: var(--text-secondary); font-size: 0.85rem;">${dcf.note || 'This company uses an alternative valuation model.'}</p>
                    <p style="margin: 10px 0 0; color: var(--text-muted); font-size: 0.75rem;">${dcf.reason || ''}</p>
                </div>
            </div>
        `;
    }

    // Build assumptions section
    let assumptionsHtml = '';
    if (assumptions && Object.keys(assumptions).length > 0) {
        assumptionsHtml = `
            <div style="padding: 16px 20px; border-bottom: 1px solid var(--border-color);">
                <div style="font-size: 0.75rem; font-weight: 700; color: var(--text-muted); margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.05em;">
                    Key Assumptions
                </div>
                <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px;">
                    ${Object.entries(assumptions).map(([key, a]) => `
                        <div style="background: var(--bg-primary); border: 1px solid var(--border-color); border-radius: 6px; padding: 12px;" title="${a.note || ''}">
                            <div style="font-size: 0.75rem; color: var(--text-muted); margin-bottom: 4px;">${a.label || key}</div>
                            <div style="font-size: 1rem; font-weight: 600; color: var(--text-primary);">
                                ${pct(a.value)}
                            </div>
                            ${a.note ? `<div style="font-size: 0.7rem; color: var(--text-muted); margin-top: 6px; line-height: 1.4;">${a.note}</div>` : ''}
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
    }

    // Build calculated section with linked values
    let calculatedHtml = '';
    if (dcf.calculated) {
        const calc = dcf.calculated;
        const tg = assumptions.terminal_growth || {};

        // Helper for tooltip values (percentages/small numbers)
        const tip = (val, label, note) => `<span style="color: var(--text-primary); border-bottom: 1px dotted var(--text-muted); cursor: help; font-size: 0.85rem; font-weight: 500;" title="${note || label}">${typeof val === 'number' ? (Math.abs(val) < 1 ? pct(val) : val.toFixed(2)) : val}</span>`;
        // Helper for large dollar values (billions/millions)
        const tipDollar = (val, label, note) => `<span style="color: var(--text-primary); border-bottom: 1px dotted var(--text-muted); cursor: help; font-size: 0.85rem; font-weight: 500;" title="${note || label}">${fmt(val)}</span>`;
        // Helper for linked values
        const link = (val, label, urlPath) => ticker ? `<a href="${baseUrl}${urlPath || ''}" target="_blank" rel="noopener" style="color: var(--accent-primary); text-decoration: underline; font-size: 0.85rem; font-weight: 500;" title="${label}">${typeof val === 'number' ? (Math.abs(val) < 1 ? pct(val) : (Math.abs(val) > 1000 ? fmt(val) : val.toFixed(2))) : val}</a>` : tip(val, label, label);

        // Get component values from backend
        const coe = calc.cost_of_equity?.components || {};
        const cod = calc.cost_of_debt?.components || {};
        const wacc = calc.wacc?.components || {};
        const ev = calc.enterprise_value?.components || {};
        const eqv = calc.equity_value?.components || {};

        const rows = [
            {
                key: 'cost_of_equity',
                label: 'Cost of Equity',
                formula: 'Rf + β × MRP',
                components: `${tip(coe.rf, 'Risk-Free Rate', '10-Year Treasury yield')} + ${link(coe.beta, 'Beta (5Y Monthly)', '/key-statistics')} × ${tip(coe.mrp, 'Market Risk Premium', 'Historical avg excess return of stocks over bonds')}`,
            },
            {
                key: 'cost_of_debt',
                label: 'Cost of Debt',
                formula: 'Rf + Credit Spread',
                components: `${tip(cod.rf, 'Risk-Free Rate', '10-Year Treasury yield')} + ${tip(cod.credit_spread, 'Credit Spread', 'Damodaran synthetic rating based on interest coverage ratio')}`,
            },
            {
                key: 'wacc',
                label: 'WACC',
                formula: '(E/V × Re) + (D/V × Rd × (1-T))',
                components: `(${tip(wacc.weight_equity, 'Equity Weight', 'Market Cap / (Market Cap + Net Debt)')} × ${tip(wacc.cost_of_equity, 'Cost of Equity', 'CAPM: Rf + β × MRP')}) + (${tip(wacc.weight_debt, 'Debt Weight', 'Net Debt / (Market Cap + Net Debt)')} × ${tip(wacc.cost_of_debt, 'Cost of Debt', 'Rf + Credit Spread')} × (1 - ${tip(wacc.tax_rate, 'Tax Rate', 'Effective tax rate from financials')}))`,
            },
            {
                key: 'terminal_value',
                label: 'Terminal Value',
                formula: 'FCF₁₀ × (1+g) / (WACC - g)',
                components: `Final year FCF × (1 + ${tip(tg.value, 'Terminal Growth', tg.note || 'Long-term GDP growth proxy')}) / (WACC - ${tip(tg.value, 'Terminal Growth', tg.note || 'Long-term GDP growth proxy')})`,
            },
            {
                key: 'enterprise_value',
                label: 'Enterprise Value',
                formula: 'PV of FCF + PV of Terminal Value',
                components: `${tipDollar(ev.pv_fcf, 'PV of FCF', 'Sum of discounted 10-year free cash flows')} + ${tipDollar(ev.pv_terminal, 'PV of Terminal Value', 'Terminal value discounted to present')}`,
            },
            {
                key: 'equity_value',
                label: 'Equity Value',
                formula: 'EV + Cash - Debt',
                components: `${tipDollar(eqv.enterprise_value, 'Enterprise Value', 'PV of FCF + PV of Terminal Value')} + ${link(eqv.cash, 'Cash & Equivalents', '/balance-sheet')} - ${link(eqv.debt, 'Total Debt', '/balance-sheet')}`,
            },
        ];

        calculatedHtml = `
            <div style="padding: 16px 20px; border-bottom: 1px solid var(--border-color);">
                <div style="font-size: 0.7rem; font-weight: 700; color: var(--text-muted); margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.05em;">
                    Calculated Values
                </div>
                <div style="display: flex; flex-direction: column; gap: 8px;">
                    ${rows.map(row => {
                        const calc = dcf.calculated[row.key] || {};
                        return `
                        <div style="background: var(--bg-primary); border: 1px solid var(--border-color); border-radius: 6px; padding: 14px;">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                                <span style="font-size: 0.9rem; font-weight: 600; color: var(--text-primary); cursor: help; border-bottom: 1px dotted var(--text-muted);" title="${row.formula}">${row.label}</span>
                                <span style="font-size: 1.2rem; font-weight: 700; color: var(--accent-primary);">${calc.result || '—'}</span>
                            </div>
                            <div style="font-size: 0.85rem; color: var(--text-secondary); line-height: 1.6;">${row.components}</div>
                        </div>`;
                    }).join('')}
                </div>
            </div>
        `;
    }

    // Build FCF projection table with full breakdown
    let projectionHtml = '';
    if (dcf.projection && dcf.projection.details && dcf.projection.details.length > 0) {
        const details = dcf.projection.details;
        const years = details.map(d => d.year);
        const base = dcf.base_inputs || {};

        const row = (label, rowId, key, format, style = '', tooltip = '', urlPath = null) => {
            const cells = details.map(d => {
                const val = d[key];
                let display = format === 'pct' ? pct(val) : fmt(val);
                return `<td style="padding: 6px 8px; text-align: right; font-size: 0.8rem;">${display}</td>`;
            }).join('');
            const labelHtml = urlPath && ticker
                ? `<a href="${baseUrl}${urlPath}" target="_blank" rel="noopener" style="color: var(--accent-primary); text-decoration: underline;" title="${tooltip} — click to verify on Yahoo Finance">${label} ↗</a>`
                : `<span title="${tooltip}">${label}</span>`;
            return `<tr data-row="${rowId}" style="${style}"><td style="padding: 6px 12px; font-size: 0.8rem; white-space: nowrap; ${style}">${labelHtml}</td>${cells}</tr>`;
        };

        projectionHtml = `
            <div style="padding: 16px 20px; border-bottom: 1px solid var(--border-color);">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                    <div style="display: flex; align-items: center; gap: 12px;">
                        <span style="font-size: 0.75rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em;">
                            Sensitivity Analysis
                        </span>
                        <button onclick="resetSensitivity()" style="padding: 5px 14px; font-size: 0.75rem; background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 4px; cursor: pointer; font-weight: 600; color: var(--text-secondary);">↺ Reset to AXIOM</button>
                    </div>
                </div>
                <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; background: var(--bg-primary); padding: 16px; border-radius: 8px; border: 1px solid var(--border-color);">
                    <div>
                        <label style="font-size: 0.7rem; color: var(--text-muted); display: block; margin-bottom: 6px;">WACC</label>
                        <input type="range" id="sens-wacc" min="5" max="20" step="0.01" value="${(base.wacc || 0.10) * 100}" oninput="syncSensInput('wacc')" style="width: 100%;">
                        <div style="display: flex; align-items: center; justify-content: center; gap: 2px; margin-top: 6px;">
                            <input type="number" id="sens-wacc-input" step="0.01" value="${((base.wacc || 0.10) * 100).toFixed(2)}" oninput="syncSensSlider('wacc')" style="width: 55px; text-align: right; font-size: 0.9rem; font-weight: 600; padding: 4px 6px; border: 1px solid var(--border-color); border-radius: 4px; background: var(--bg-secondary); color: var(--text-primary);">
                            <span style="font-size: 0.9rem; font-weight: 600;">%</span>
                        </div>
                    </div>
                    <div>
                        <label style="font-size: 0.7rem; color: var(--text-muted); display: block; margin-bottom: 6px;">Terminal Growth</label>
                        <input type="range" id="sens-term-growth" min="0" max="5" step="0.01" value="${(base.terminal_growth || 0.025) * 100}" oninput="syncSensInput('term-growth')" style="width: 100%;">
                        <div style="display: flex; align-items: center; justify-content: center; gap: 2px; margin-top: 6px;">
                            <input type="number" id="sens-term-growth-input" step="0.01" value="${((base.terminal_growth || 0.025) * 100).toFixed(2)}" oninput="syncSensSlider('term-growth')" style="width: 55px; text-align: right; font-size: 0.9rem; font-weight: 600; padding: 4px 6px; border: 1px solid var(--border-color); border-radius: 4px; background: var(--bg-secondary); color: var(--text-primary);">
                            <span style="font-size: 0.9rem; font-weight: 600;">%</span>
                        </div>
                    </div>
                    <div>
                        <label style="font-size: 0.7rem; color: var(--text-muted); display: block; margin-bottom: 6px;">Revenue Growth (Y1)</label>
                        <input type="range" id="sens-revenue-growth" min="0" max="50" step="0.01" value="${(base.growth_y1 || 0.10) * 100}" oninput="syncSensInput('revenue-growth')" style="width: 100%;">
                        <div style="display: flex; align-items: center; justify-content: center; gap: 2px; margin-top: 6px;">
                            <input type="number" id="sens-revenue-growth-input" step="0.01" value="${((base.growth_y1 || 0.10) * 100).toFixed(2)}" oninput="syncSensSlider('revenue-growth')" style="width: 55px; text-align: right; font-size: 0.9rem; font-weight: 600; padding: 4px 6px; border: 1px solid var(--border-color); border-radius: 4px; background: var(--bg-secondary); color: var(--text-primary);">
                            <span style="font-size: 0.9rem; font-weight: 600;">%</span>
                        </div>
                    </div>
                    <div>
                        <label style="font-size: 0.7rem; color: var(--text-muted); display: block; margin-bottom: 6px;">EBITDA Margin</label>
                        <input type="range" id="sens-margin" min="5" max="60" step="0.01" value="${(base.ebitda_margin || 0.20) * 100}" oninput="syncSensInput('margin')" style="width: 100%;">
                        <div style="display: flex; align-items: center; justify-content: center; gap: 2px; margin-top: 6px;">
                            <input type="number" id="sens-margin-input" step="0.01" value="${((base.ebitda_margin || 0.20) * 100).toFixed(2)}" oninput="syncSensSlider('margin')" style="width: 55px; text-align: right; font-size: 0.9rem; font-weight: 600; padding: 4px 6px; border: 1px solid var(--border-color); border-radius: 4px; background: var(--bg-secondary); color: var(--text-primary);">
                            <span style="font-size: 0.9rem; font-weight: 600;">%</span>
                        </div>
                    </div>
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 12px;">
                    <div id="sens-equity-value" style="background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%); color: white; padding: 16px; border-radius: 8px; text-align: center;">
                        <div style="font-size: 1.4rem; font-weight: 700;">${fmt(dcf.calculated?.equity_value?.value || 0)}</div>
                        <div style="font-size: 0.85rem; opacity: 0.8;">Equity Value</div>
                    </div>
                    <div id="sens-price-per-share" style="background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%); color: white; padding: 16px; border-radius: 8px; text-align: center;">
                        <div style="font-size: 1.4rem; font-weight: 700;">$${(dcf.calculated?.price_per_share?.value || 0).toFixed(2)}</div>
                        <div style="font-size: 0.85rem; opacity: 0.8;">per share</div>
                    </div>
                </div>
            </div>
            <div style="padding: 16px 20px;">
                <div style="font-size: 0.75rem; font-weight: 700; color: var(--text-muted); margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.05em;">
                    10-Year Cash Flow Projection
                </div>
                <div style="overflow-x: auto; border: 1px solid var(--border-color); border-radius: 8px;">
                    <table id="dcf-table" style="width: 100%; border-collapse: collapse;">
                        <thead>
                            <tr style="background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%);">
                                <th style="padding: 10px 12px; text-align: left; color: white; font-size: 0.8rem; font-weight: 600;">Metric</th>
                                ${years.map(y => `<th style="padding: 10px 8px; text-align: right; color: white; font-size: 0.8rem; font-weight: 600;">Y${y}</th>`).join('')}
                            </tr>
                        </thead>
                        <tbody style="background: var(--bg-primary);">
                            ${row('Growth Rate', 'growth', 'growth_rate', 'pct', 'color: var(--text-muted); font-style: italic;', 'Annual revenue growth rate', '/analysis')}
                            ${row('Revenue', 'revenue', 'revenue', 'dollar', 'font-weight: 600; border-top: 1px solid var(--border-color);', 'Projected revenue', '/financials')}
                            ${row('EBITDA', 'ebitda', 'ebitda', 'dollar', '', 'EBITDA margin applied to revenue', '/financials')}
                            ${row('(-) D&A', 'da', 'da', 'dollar', 'color: var(--text-muted);', 'Depreciation & Amortization', '/cash-flow')}
                            ${row('= EBIT', 'ebit', 'ebit', 'dollar', 'font-weight: 500; border-top: 1px solid var(--border-color);', 'EBITDA minus D&A')}
                            ${row('= NOPAT', 'nopat', 'nopat', 'dollar', 'font-weight: 500;', 'EBIT × (1 - Tax Rate)', '/financials')}
                            ${row('(+) D&A', 'da2', 'da', 'dollar', 'color: #22c55e;', 'Add back non-cash depreciation', '/cash-flow')}
                            ${row('(-) CapEx', 'capex', 'capex', 'dollar', 'color: #ef4444;', 'Capital expenditures', '/cash-flow')}
                            ${row('(-) ΔWC', 'wc', 'wc_change', 'dollar', 'color: #ef4444;', 'Working capital change', '/balance-sheet')}
                            ${row('= Free Cash Flow', 'fcf', 'fcf', 'dollar', 'font-weight: 700; background: var(--bg-secondary); border-top: 2px solid var(--border-color);', 'NOPAT + D&A - CapEx - ΔWC')}
                            ${row('Discount Factor', 'df', 'discount_factor', 'pct', 'color: var(--text-muted); font-style: italic; border-top: 1px solid var(--border-color);', '1 / (1 + WACC)^year')}
                            ${row('PV of FCF', 'pvfcf', 'pv_fcf', 'dollar', 'font-weight: 600; color: var(--accent-primary);', 'FCF × Discount Factor')}
                        </tbody>
                    </table>
                </div>
                <div style="margin-top: 16px; display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px;">
                    <div style="background: var(--bg-primary); border: 1px solid var(--border-color); border-radius: 6px; padding: 12px;">
                        <div style="font-size: 0.7rem; color: var(--text-muted); margin-bottom: 4px;">Total PV of FCF</div>
                        <div id="sens-total-pv-fcf" style="font-size: 1.1rem; font-weight: 700; color: var(--text-primary);">${fmt(dcf.projection.total_pv_fcf)}</div>
                    </div>
                    <div style="background: var(--bg-primary); border: 1px solid var(--border-color); border-radius: 6px; padding: 12px;">
                        <div style="font-size: 0.7rem; color: var(--text-muted); margin-bottom: 4px;">Terminal Value</div>
                        <div id="sens-terminal-value" style="font-size: 1.1rem; font-weight: 700; color: var(--text-primary);">${fmt(dcf.projection.terminal_value)}</div>
                    </div>
                    <div style="background: var(--bg-primary); border: 1px solid var(--border-color); border-radius: 6px; padding: 12px;">
                        <div style="font-size: 0.7rem; color: var(--text-muted); margin-bottom: 4px;">PV of Terminal Value</div>
                        <div id="sens-pv-terminal" style="font-size: 1.1rem; font-weight: 700; color: var(--accent-primary);">${fmt(dcf.projection.pv_terminal_value)}</div>
                    </div>
                </div>
            </div>
        `;
    }

    // Check if user has a saved valuation
    const savedValuation = getUserValuation(currentCompanyId);
    const hasSaved = !!savedValuation;

    // Save button HTML with indicator and remove option
    const saveButtonHtml = dcf.base_inputs ? `
        <div style="padding: 20px; border-top: 1px solid var(--border-color);">
            <div id="user-valuation-indicator" style="display: ${hasSaved ? 'block' : 'none'}; margin-bottom: 12px; padding: 10px 14px; background: rgba(139, 92, 246, 0.1); border: 1px solid rgba(139, 92, 246, 0.3); border-radius: 6px; font-size: 0.85rem; color: var(--text-secondary);">
                Your custom valuation: <strong>$${hasSaved ? savedValuation.pricePerShare.toFixed(2) : '—'}</strong>/share
                <span style="margin-left: 8px; color: var(--text-muted);">Saved ${hasSaved ? new Date(savedValuation.savedAt).toLocaleDateString() : ''}</span>
            </div>
            <div style="display: flex; gap: 10px;">
                <button id="save-valuation-btn" onclick="saveUserValuation()" style="flex: 1; padding: 14px 24px; background: linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%); color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; font-size: 0.95rem;">
                    ${hasSaved ? 'Update Your Valuation' : 'Save Your Valuation'}
                </button>
                <button id="remove-valuation-btn" onclick="removeUserValuation()" style="display: ${hasSaved ? 'block' : 'none'}; padding: 14px 18px; background: transparent; color: #ef4444; border: 1px solid #ef4444; border-radius: 8px; cursor: pointer; font-weight: 600; font-size: 0.85rem;">
                    Remove
                </button>
            </div>
        </div>
    ` : '';

    return `
        <div style="background: var(--bg-secondary); padding-bottom: 0;">
            ${assumptionsHtml}
            ${calculatedHtml}
            ${projectionHtml}
            ${saveButtonHtml}
        </div>
    `;
}

// ============================================
// EV/EBITDA DETAILS MODAL
// ============================================

let evEbitdaBaseInputs = null;

function toggleEVEBITDADetails() {
    if (!currentCompanyId) return;
    window.open(`/ev-ebitda/${currentCompanyId}`, '_blank');
}

function closeEVEBITDAModal() {
    const modal = document.getElementById('ev-ebitda-details-modal');
    if (modal) {
        modal.classList.remove('active');
        modal.style.display = 'none';
    }
}

function renderEVEBITDADetails(ev) {
    const ticker = ev.ticker || '';
    const baseUrl = 'https://finance.yahoo.com/quote/' + ticker;
    const inputs = ev.inputs || {};
    const assumptions = ev.assumptions || {};
    const calculated = ev.calculated || {};
    const base = ev.base_inputs || {};

    const fmt = (val) => {
        if (val === null || val === undefined) return '—';
        if (Math.abs(val) >= 1e12) return `$${(val/1e12).toFixed(2)}T`;
        if (Math.abs(val) >= 1e9) return `$${(val/1e9).toFixed(2)}B`;
        if (Math.abs(val) >= 1e6) return `$${(val/1e6).toFixed(1)}M`;
        return `$${val.toLocaleString()}`;
    };

    const savedValuation = getUserEVEBITDAValuation(currentCompanyId);
    const hasSaved = !!savedValuation;

    const evMultipleNote = assumptions.ev_ebitda_multiple?.note || `Based on ${base.sector || 'industry'} sector`;
    const evMultipleTooltip = `EV/EBITDA Multiple: ${assumptions.ev_ebitda_multiple?.value?.toFixed(1)}x&#10;&#10;${evMultipleNote}&#10;&#10;This multiple shows what acquirers typically pay relative to cash flow generation. It's capital-structure neutral, making it ideal for comparing companies with different debt levels.`;

    // Assumption card for the multiple
    const assumptionsHtml = `
        <div style="padding: 24px; border-bottom: 1px solid var(--border-color);">
            <div style="font-size: 0.75rem; font-weight: 700; color: var(--text-muted); margin-bottom: 16px; text-transform: uppercase; letter-spacing: 0.05em;">
                Key Assumption
            </div>
            <div style="background: var(--bg-primary); border: 1px solid var(--border-color); border-radius: 8px; padding: 20px; display: flex; align-items: center; gap: 20px;">
                <div style="flex: 1;">
                    <div style="font-size: 0.8rem; color: var(--text-muted); margin-bottom: 6px;">EV/EBITDA Multiple</div>
                    <div style="font-size: 1.8rem; font-weight: 700; color: var(--accent-primary);">${assumptions.ev_ebitda_multiple?.value?.toFixed(1)}x</div>
                </div>
                <div style="flex: 2; padding-left: 20px; border-left: 1px solid var(--border-color);">
                    <div style="font-size: 0.85rem; color: var(--text-secondary); line-height: 1.5;">
                        ${evMultipleNote}. This multiple reflects what acquirers typically pay relative to operating cash flow — it's capital-structure neutral, ideal for comparing companies with different debt levels.
                    </div>
                </div>
            </div>
        </div>
    `;

    const calculationHtml = `
        <div style="padding: 24px; border-bottom: 1px solid var(--border-color);">
            <div style="font-size: 0.75rem; font-weight: 700; color: var(--text-muted); margin-bottom: 20px; text-transform: uppercase; letter-spacing: 0.05em;">
                Valuation Calculation
            </div>
            <div style="background: var(--bg-primary); border: 1px solid var(--border-color); border-radius: 8px; padding: 32px;">
                <div style="display: flex; align-items: center; justify-content: center; gap: 20px; flex-wrap: wrap; font-size: 1.5rem;">
                    <a href="${baseUrl}/financials" target="_blank" title="EBITDA (TTM)&#10;Earnings Before Interest, Taxes, Depreciation & Amortization&#10;&#10;Click to verify on Yahoo Finance · Income Statement" style="font-weight: 700; color: var(--accent-primary); text-decoration: none; border-bottom: 2px dotted var(--accent-primary); padding-bottom: 2px;">${fmt(inputs.ebitda?.value)}</a>
                    <span style="color: var(--text-muted); font-size: 1.6rem;">×</span>
                    <span title="${evMultipleTooltip}" style="font-weight: 700; color: var(--accent-primary); cursor: help; border-bottom: 2px dotted var(--accent-primary); padding-bottom: 2px;">${assumptions.ev_ebitda_multiple?.value?.toFixed(1)}x</span>
                    <span style="color: var(--text-muted); font-size: 1.6rem;">=</span>
                    <span title="Implied Enterprise Value&#10;Computed from EBITDA × Multiple" style="font-weight: 700; color: var(--text-primary); cursor: help; border-bottom: 2px dotted var(--text-muted); padding-bottom: 2px;">${fmt(calculated.implied_ev?.value)}</span>
                </div>
                <div style="margin-top: 24px; padding-top: 24px; border-top: 1px solid var(--border-color); display: flex; align-items: center; justify-content: center; gap: 20px; flex-wrap: wrap; font-size: 1.5rem;">
                    <span title="Enterprise Value from above" style="font-weight: 700; color: var(--text-primary); cursor: help; border-bottom: 2px dotted var(--text-muted); padding-bottom: 2px;">${fmt(calculated.implied_ev?.value)}</span>
                    <span style="color: var(--text-muted); font-size: 1.6rem;">+</span>
                    <a href="${baseUrl}/balance-sheet" target="_blank" title="Cash & Equivalents&#10;Added because equity holders get this cash&#10;&#10;Click to verify on Yahoo Finance · Balance Sheet" style="font-weight: 700; color: var(--accent-primary); text-decoration: none; border-bottom: 2px dotted var(--accent-primary); padding-bottom: 2px;">${fmt(inputs.cash?.value)}</a>
                    <span style="color: var(--text-muted); font-size: 1.6rem;">−</span>
                    <a href="${baseUrl}/balance-sheet" target="_blank" title="Total Debt&#10;Subtracted because debt holders have first claim&#10;&#10;Click to verify on Yahoo Finance · Balance Sheet" style="font-weight: 700; color: var(--accent-primary); text-decoration: none; border-bottom: 2px dotted var(--accent-primary); padding-bottom: 2px;">${fmt(inputs.debt?.value)}</a>
                    <span style="color: var(--text-muted); font-size: 1.6rem;">=</span>
                    <span title="Implied Equity Value&#10;What shareholders' stake is worth" style="font-weight: 700; color: var(--accent-primary); cursor: help; border-bottom: 2px dotted var(--accent-primary); padding-bottom: 2px;">${fmt(calculated.implied_equity?.value)}</span>
                </div>
                <div style="text-align: center; margin-top: 16px; font-size: 0.75rem; color: var(--text-muted);">
                    Click values to verify on Yahoo Finance
                </div>
            </div>
            <div style="margin-top: 20px; display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
                <div style="background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%); color: white; padding: 24px; border-radius: 8px; text-align: center;">
                    <div style="font-size: 1.7rem; font-weight: 700;">${fmt(calculated.implied_equity?.value)}</div>
                    <div style="font-size: 0.85rem; opacity: 0.85; margin-top: 4px;">Implied Equity Value</div>
                </div>
                <div style="background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%); color: white; padding: 24px; border-radius: 8px; text-align: center;">
                    <div style="font-size: 1.7rem; font-weight: 700;">$${calculated.price_per_share?.value?.toFixed(2) || '—'}</div>
                    <div style="font-size: 0.85rem; opacity: 0.85; margin-top: 4px;">Fair Value per Share</div>
                </div>
            </div>
        </div>
    `;

    const sensitivityHtml = base.ebitda ? `
        <div style="padding: 24px; border-bottom: 1px solid var(--border-color);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                <div style="font-size: 0.75rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em;">
                    Sensitivity Analysis
                </div>
                <button onclick="resetEVEBITDASensitivity()" style="padding: 6px 14px; background: transparent; color: var(--text-muted); border: 1px solid var(--border-color); border-radius: 4px; cursor: pointer; font-size: 0.75rem; transition: all 0.2s ease;" onmouseenter="this.style.borderColor='var(--accent-primary)'; this.style.color='var(--accent-primary)';" onmouseleave="this.style.borderColor='var(--border-color)'; this.style.color='var(--text-muted)';">
                    Reset to AXIOM
                </button>
            </div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 32px; align-items: center;">
                <div style="padding: 20px; background: var(--bg-primary); border: 1px solid var(--border-color); border-radius: 8px;">
                    <label style="font-size: 0.8rem; color: var(--text-muted); display: block; margin-bottom: 12px;">EV/EBITDA Multiple</label>
                    <input type="range" id="ev-sens-multiple" min="5" max="30" step="0.1" value="${base.ev_ebitda_multiple || 15}" oninput="syncEVInput('multiple')" style="width: 100%;">
                    <div style="display: flex; align-items: center; justify-content: center; gap: 6px; margin-top: 12px;">
                        <input type="number" id="ev-sens-multiple-input" step="0.1" value="${(base.ev_ebitda_multiple || 15).toFixed(1)}" oninput="syncEVSlider('multiple')" style="width: 70px; text-align: right; font-size: 1.1rem; font-weight: 600; padding: 8px 10px; border: 1px solid var(--border-color); border-radius: 4px; background: var(--bg-secondary); color: var(--text-primary);">
                        <span style="font-size: 1.1rem; font-weight: 600;">x</span>
                    </div>
                </div>
                <div id="ev-sens-result" style="background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%); color: white; padding: 28px; border-radius: 8px; text-align: center;">
                    <div style="font-size: 1.6rem; font-weight: 700;">$${calculated.price_per_share?.value?.toFixed(2) || '—'}</div>
                    <div style="font-size: 0.85rem; opacity: 0.85; margin-top: 6px;">Your Price Target</div>
                    <div id="ev-sens-diff" style="font-size: 0.8rem; margin-top: 8px; opacity: 0.75;">vs AXIOM: +0.0%</div>
                </div>
            </div>
        </div>
    ` : '';

    const saveButtonHtml = base.ebitda ? `
        <div style="padding: 24px;">
            <div id="ev-user-valuation-indicator" style="display: ${hasSaved ? 'block' : 'none'}; margin-bottom: 16px; padding: 12px 16px; background: var(--bg-primary); border: 1px solid var(--border-color); border-radius: 6px; font-size: 0.85rem; color: var(--text-secondary);">
                Your custom valuation: <strong>$${hasSaved ? savedValuation.pricePerShare.toFixed(2) : '—'}</strong>/share
                <span style="margin-left: 8px; color: var(--text-muted);">Saved ${hasSaved ? new Date(savedValuation.savedAt).toLocaleDateString() : ''}</span>
            </div>
            <div style="display: flex; gap: 12px;">
                <button id="ev-save-valuation-btn" onclick="saveEVEBITDAValuation()" style="flex: 1; padding: 14px 24px; background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%); color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; font-size: 0.95rem; transition: all 0.2s ease;" onmouseenter="this.style.opacity='0.9'; this.style.transform='translateY(-1px)';" onmouseleave="this.style.opacity='1'; this.style.transform='translateY(0)';">
                    ${hasSaved ? 'Update Your Valuation' : 'Save Your Valuation'}
                </button>
                <button id="ev-remove-valuation-btn" onclick="removeEVEBITDAValuation()" style="display: ${hasSaved ? 'block' : 'none'}; padding: 14px 18px; background: transparent; color: #ef4444; border: 1px solid #ef4444; border-radius: 8px; cursor: pointer; font-weight: 600; font-size: 0.85rem; transition: all 0.2s ease;" onmouseenter="this.style.background='#ef4444'; this.style.color='white';" onmouseleave="this.style.background='transparent'; this.style.color='#ef4444';">
                    Remove
                </button>
            </div>
        </div>
    ` : '';

    return `
        <div style="background: var(--bg-secondary); padding-bottom: 0;">
            ${assumptionsHtml}
            ${calculationHtml}
            ${sensitivityHtml}
            ${saveButtonHtml}
        </div>
    `;
}

function syncEVInput(field) {
    const slider = document.getElementById(`ev-sens-${field}`);
    const input = document.getElementById(`ev-sens-${field}-input`);
    if (slider && input) {
        input.value = parseFloat(slider.value).toFixed(1);
        recalculateEVEBITDA();
    }
}

function syncEVSlider(field) {
    const slider = document.getElementById(`ev-sens-${field}`);
    const input = document.getElementById(`ev-sens-${field}-input`);
    if (slider && input) {
        slider.value = parseFloat(input.value);
        recalculateEVEBITDA();
    }
}

function recalculateEVEBITDA() {
    if (!evEbitdaBaseInputs) return;

    const base = evEbitdaBaseInputs;
    const multiple = parseFloat(document.getElementById('ev-sens-multiple-input')?.value || base.ev_ebitda_multiple);

    const impliedEV = base.ebitda * multiple;
    const impliedEquity = impliedEV + base.cash - base.debt;
    const pricePerShare = impliedEquity / base.shares;

    // Update result display
    const resultDiv = document.getElementById('ev-sens-result');
    const diffDiv = document.getElementById('ev-sens-diff');
    if (resultDiv) {
        resultDiv.querySelector('div').textContent = `$${pricePerShare.toFixed(2)}`;
    }

    // Calculate diff vs AXIOM base
    const axiomPrice = (base.ebitda * base.ev_ebitda_multiple + base.cash - base.debt) / base.shares;
    const diff = ((pricePerShare - axiomPrice) / axiomPrice) * 100;
    if (diffDiv) {
        diffDiv.textContent = `vs AXIOM: ${diff >= 0 ? '+' : ''}${diff.toFixed(1)}%`;
        diffDiv.style.color = diff >= 0 ? '#22c55e' : '#ef4444';
    }
}

function resetEVEBITDASensitivity() {
    if (!evEbitdaBaseInputs) return;
    const base = evEbitdaBaseInputs;

    const slider = document.getElementById('ev-sens-multiple');
    const input = document.getElementById('ev-sens-multiple-input');
    if (slider) slider.value = base.ev_ebitda_multiple;
    if (input) input.value = base.ev_ebitda_multiple.toFixed(1);

    recalculateEVEBITDA();
}

function saveEVEBITDAValuation() {
    if (!evEbitdaBaseInputs || !currentCompanyId) return;

    const base = evEbitdaBaseInputs;
    const multiple = parseFloat(document.getElementById('ev-sens-multiple-input')?.value || base.ev_ebitda_multiple);

    const impliedEV = base.ebitda * multiple;
    const impliedEquity = impliedEV + base.cash - base.debt;
    const pricePerShare = impliedEquity / base.shares;

    const userValuations = JSON.parse(localStorage.getItem('userEVEBITDAValuations') || '{}');
    userValuations[currentCompanyId] = {
        impliedEquity,
        pricePerShare,
        evEbitdaMultiple: multiple,
        savedAt: new Date().toISOString()
    };
    localStorage.setItem('userEVEBITDAValuations', JSON.stringify(userValuations));

    // Show confirmation
    const btn = event.target.closest('button');
    const origHtml = btn.innerHTML;
    btn.innerHTML = '✓ Saved!';
    btn.style.background = '#16a34a';

    const removeBtn = document.getElementById('ev-remove-valuation-btn');
    const indicator = document.getElementById('ev-user-valuation-indicator');
    if (removeBtn) removeBtn.style.display = 'block';
    if (indicator) {
        indicator.style.display = 'block';
        indicator.innerHTML = `Your custom valuation: <strong>$${pricePerShare.toFixed(2)}</strong>/share <span style="margin-left: 8px; color: var(--text-muted);">Saved ${new Date().toLocaleDateString()}</span>`;
    }

    setTimeout(() => {
        btn.innerHTML = 'Update Your Valuation';
        btn.style.background = 'linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%)';
    }, 1500);

    if (typeof loadCompanies === 'function') loadCompanies();
}

function getUserEVEBITDAValuation(companyId) {
    const userValuations = JSON.parse(localStorage.getItem('userEVEBITDAValuations') || '{}');
    return userValuations[companyId] || null;
}

function removeEVEBITDAValuation() {
    if (!currentCompanyId) return;

    const userValuations = JSON.parse(localStorage.getItem('userEVEBITDAValuations') || '{}');
    delete userValuations[currentCompanyId];
    localStorage.setItem('userEVEBITDAValuations', JSON.stringify(userValuations));

    resetEVEBITDASensitivity();

    const removeBtn = document.getElementById('ev-remove-valuation-btn');
    const indicator = document.getElementById('ev-user-valuation-indicator');
    const saveBtn = document.getElementById('ev-save-valuation-btn');

    if (removeBtn) removeBtn.style.display = 'none';
    if (indicator) indicator.style.display = 'none';
    if (saveBtn) saveBtn.innerHTML = 'Save Your Valuation';

    if (typeof loadCompanies === 'function') loadCompanies();
}

// ============================================
// P/E DETAILS MODAL
// ============================================

let peBaseInputs = null;

function togglePEDetails() {
    if (!currentCompanyId) return;
    window.open(`/pe/${currentCompanyId}`, '_blank');
}

function closePEModal() {
    const modal = document.getElementById('pe-details-modal');
    if (modal) {
        modal.classList.remove('active');
        modal.style.display = 'none';
    }
}

function renderPEDetails(pe) {
    const ticker = pe.ticker || '';
    const baseUrl = 'https://finance.yahoo.com/quote/' + ticker;
    const inputs = pe.inputs || {};
    const assumptions = pe.assumptions || {};
    const calculated = pe.calculated || {};
    const base = pe.base_inputs || {};

    const fmt = (val) => {
        if (val === null || val === undefined) return '—';
        if (Math.abs(val) >= 1e12) return `$${(val/1e12).toFixed(2)}T`;
        if (Math.abs(val) >= 1e9) return `$${(val/1e9).toFixed(2)}B`;
        if (Math.abs(val) >= 1e6) return `$${(val/1e6).toFixed(1)}M`;
        return `$${val.toLocaleString()}`;
    };

    const savedValuation = getUserPEValuation(currentCompanyId);
    const hasSaved = !!savedValuation;

    const peMultipleNote = assumptions.pe_multiple?.note || `Based on ${base.sector || 'industry'} sector`;
    const peMultipleTooltip = `P/E Multiple: ${assumptions.pe_multiple?.value?.toFixed(1)}x&#10;&#10;${peMultipleNote}&#10;&#10;This multiple reflects what investors typically pay per dollar of earnings for comparable companies in this sector. Higher multiples indicate expectations of stronger future growth.`;

    // Assumption card for the multiple
    const assumptionsHtml = `
        <div style="padding: 24px; border-bottom: 1px solid var(--border-color);">
            <div style="font-size: 0.75rem; font-weight: 700; color: var(--text-muted); margin-bottom: 16px; text-transform: uppercase; letter-spacing: 0.05em;">
                Key Assumption
            </div>
            <div style="background: var(--bg-primary); border: 1px solid var(--border-color); border-radius: 8px; padding: 20px; display: flex; align-items: center; gap: 20px;">
                <div style="flex: 1;">
                    <div style="font-size: 0.8rem; color: var(--text-muted); margin-bottom: 6px;">P/E Multiple</div>
                    <div style="font-size: 1.8rem; font-weight: 700; color: var(--accent-primary);">${assumptions.pe_multiple?.value?.toFixed(1)}x</div>
                </div>
                <div style="flex: 2; padding-left: 20px; border-left: 1px solid var(--border-color);">
                    <div style="font-size: 0.85rem; color: var(--text-secondary); line-height: 1.5;">
                        ${peMultipleNote}. This reflects what investors typically pay per dollar of earnings. Higher multiples indicate expectations of stronger future growth.
                    </div>
                </div>
            </div>
        </div>
    `;

    const calculationHtml = `
        <div style="padding: 24px; border-bottom: 1px solid var(--border-color);">
            <div style="font-size: 0.75rem; font-weight: 700; color: var(--text-muted); margin-bottom: 20px; text-transform: uppercase; letter-spacing: 0.05em;">
                Valuation Calculation
            </div>
            <div style="background: var(--bg-primary); border: 1px solid var(--border-color); border-radius: 8px; padding: 32px;">
                <div style="display: flex; align-items: center; justify-content: center; gap: 20px; flex-wrap: wrap; font-size: 1.5rem;">
                    <a href="${baseUrl}/financials" target="_blank" title="Net Income (TTM)&#10;Trailing twelve months profit after all expenses and taxes&#10;&#10;Click to verify on Yahoo Finance · Income Statement" style="font-weight: 700; color: var(--accent-primary); text-decoration: none; border-bottom: 2px dotted var(--accent-primary); padding-bottom: 2px;">${fmt(inputs.net_income?.value)}</a>
                    <span style="color: var(--text-muted); font-size: 1.6rem;">×</span>
                    <span title="${peMultipleTooltip}" style="font-weight: 700; color: var(--accent-primary); cursor: help; border-bottom: 2px dotted var(--accent-primary); padding-bottom: 2px;">${assumptions.pe_multiple?.value?.toFixed(1)}x</span>
                    <span style="color: var(--text-muted); font-size: 1.6rem;">=</span>
                    <span title="Implied Market Cap&#10;Computed from Net Income × P/E Multiple" style="font-weight: 700; color: var(--text-primary); cursor: help; border-bottom: 2px dotted var(--text-muted); padding-bottom: 2px;">${fmt(calculated.implied_market_cap?.value)}</span>
                </div>
                <div style="text-align: center; margin-top: 16px; font-size: 0.75rem; color: var(--text-muted);">
                    Click values to verify on Yahoo Finance
                </div>
            </div>
            <div style="margin-top: 20px; display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
                <div style="background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%); color: white; padding: 24px; border-radius: 8px; text-align: center;">
                    <div style="font-size: 1.7rem; font-weight: 700;">${fmt(calculated.implied_market_cap?.value)}</div>
                    <div style="font-size: 0.85rem; opacity: 0.85; margin-top: 4px;">Implied Market Cap</div>
                </div>
                <div style="background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%); color: white; padding: 24px; border-radius: 8px; text-align: center;">
                    <div style="font-size: 1.7rem; font-weight: 700;">$${calculated.price_per_share?.value?.toFixed(2) || '—'}</div>
                    <div style="font-size: 0.85rem; opacity: 0.85; margin-top: 4px;">Fair Value per Share</div>
                </div>
            </div>
        </div>
    `;

    const sensitivityHtml = base.net_income ? `
        <div style="padding: 24px; border-bottom: 1px solid var(--border-color);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                <div style="font-size: 0.75rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em;">
                    Sensitivity Analysis
                </div>
                <button onclick="resetPESensitivity()" style="padding: 6px 14px; background: transparent; color: var(--text-muted); border: 1px solid var(--border-color); border-radius: 4px; cursor: pointer; font-size: 0.75rem; transition: all 0.2s ease;" onmouseenter="this.style.borderColor='var(--accent-primary)'; this.style.color='var(--accent-primary)';" onmouseleave="this.style.borderColor='var(--border-color)'; this.style.color='var(--text-muted)';">
                    Reset to AXIOM
                </button>
            </div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 32px; align-items: center;">
                <div style="padding: 20px; background: var(--bg-primary); border: 1px solid var(--border-color); border-radius: 8px;">
                    <label style="font-size: 0.8rem; color: var(--text-muted); display: block; margin-bottom: 12px;">P/E Multiple</label>
                    <input type="range" id="pe-sens-multiple" min="5" max="50" step="0.1" value="${base.pe_multiple || 20}" oninput="syncPEInput('multiple')" style="width: 100%;">
                    <div style="display: flex; align-items: center; justify-content: center; gap: 6px; margin-top: 12px;">
                        <input type="number" id="pe-sens-multiple-input" step="0.1" value="${(base.pe_multiple || 20).toFixed(1)}" oninput="syncPESlider('multiple')" style="width: 70px; text-align: right; font-size: 1.1rem; font-weight: 600; padding: 8px 10px; border: 1px solid var(--border-color); border-radius: 4px; background: var(--bg-secondary); color: var(--text-primary);">
                        <span style="font-size: 1.1rem; font-weight: 600;">x</span>
                    </div>
                </div>
                <div id="pe-sens-result" style="background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%); color: white; padding: 28px; border-radius: 8px; text-align: center;">
                    <div style="font-size: 1.6rem; font-weight: 700;">$${calculated.price_per_share?.value?.toFixed(2) || '—'}</div>
                    <div style="font-size: 0.85rem; opacity: 0.85; margin-top: 6px;">Your Price Target</div>
                    <div id="pe-sens-diff" style="font-size: 0.8rem; margin-top: 8px; opacity: 0.75;">vs AXIOM: +0.0%</div>
                </div>
            </div>
        </div>
    ` : '';

    const saveButtonHtml = base.net_income ? `
        <div style="padding: 24px;">
            <div id="pe-user-valuation-indicator" style="display: ${hasSaved ? 'block' : 'none'}; margin-bottom: 16px; padding: 12px 16px; background: var(--bg-primary); border: 1px solid var(--border-color); border-radius: 6px; font-size: 0.85rem; color: var(--text-secondary);">
                Your custom valuation: <strong>$${hasSaved ? savedValuation.pricePerShare.toFixed(2) : '—'}</strong>/share
                <span style="margin-left: 8px; color: var(--text-muted);">Saved ${hasSaved ? new Date(savedValuation.savedAt).toLocaleDateString() : ''}</span>
            </div>
            <div style="display: flex; gap: 12px;">
                <button id="pe-save-valuation-btn" onclick="savePEValuation()" style="flex: 1; padding: 14px 24px; background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%); color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; font-size: 0.95rem; transition: all 0.2s ease;" onmouseenter="this.style.opacity='0.9'; this.style.transform='translateY(-1px)';" onmouseleave="this.style.opacity='1'; this.style.transform='translateY(0)';">
                    ${hasSaved ? 'Update Your Valuation' : 'Save Your Valuation'}
                </button>
                <button id="pe-remove-valuation-btn" onclick="removePEValuation()" style="display: ${hasSaved ? 'block' : 'none'}; padding: 14px 18px; background: transparent; color: #ef4444; border: 1px solid #ef4444; border-radius: 8px; cursor: pointer; font-weight: 600; font-size: 0.85rem; transition: all 0.2s ease;" onmouseenter="this.style.background='#ef4444'; this.style.color='white';" onmouseleave="this.style.background='transparent'; this.style.color='#ef4444';">
                    Remove
                </button>
            </div>
        </div>
    ` : '';

    return `
        <div style="background: var(--bg-secondary); padding-bottom: 0;">
            ${assumptionsHtml}
            ${calculationHtml}
            ${sensitivityHtml}
            ${saveButtonHtml}
        </div>
    `;
}

function syncPEInput(field) {
    const slider = document.getElementById(`pe-sens-${field}`);
    const input = document.getElementById(`pe-sens-${field}-input`);
    if (slider && input) {
        input.value = parseFloat(slider.value).toFixed(1);
        recalculatePE();
    }
}

function syncPESlider(field) {
    const slider = document.getElementById(`pe-sens-${field}`);
    const input = document.getElementById(`pe-sens-${field}-input`);
    if (slider && input) {
        slider.value = parseFloat(input.value);
        recalculatePE();
    }
}

function recalculatePE() {
    if (!peBaseInputs) return;

    const base = peBaseInputs;
    const multiple = parseFloat(document.getElementById('pe-sens-multiple-input')?.value || base.pe_multiple);

    const impliedMarketCap = base.net_income * multiple;
    const pricePerShare = impliedMarketCap / base.shares;

    const resultDiv = document.getElementById('pe-sens-result');
    const diffDiv = document.getElementById('pe-sens-diff');
    if (resultDiv) {
        resultDiv.querySelector('div').textContent = `$${pricePerShare.toFixed(2)}`;
    }

    const axiomPrice = (base.net_income * base.pe_multiple) / base.shares;
    const diff = ((pricePerShare - axiomPrice) / axiomPrice) * 100;
    if (diffDiv) {
        diffDiv.textContent = `vs AXIOM: ${diff >= 0 ? '+' : ''}${diff.toFixed(1)}%`;
        diffDiv.style.color = diff >= 0 ? '#22c55e' : '#ef4444';
    }
}

function resetPESensitivity() {
    if (!peBaseInputs) return;
    const base = peBaseInputs;

    const slider = document.getElementById('pe-sens-multiple');
    const input = document.getElementById('pe-sens-multiple-input');
    if (slider) slider.value = base.pe_multiple;
    if (input) input.value = base.pe_multiple.toFixed(1);

    recalculatePE();
}

function savePEValuation() {
    if (!peBaseInputs || !currentCompanyId) return;

    const base = peBaseInputs;
    const multiple = parseFloat(document.getElementById('pe-sens-multiple-input')?.value || base.pe_multiple);

    const impliedMarketCap = base.net_income * multiple;
    const pricePerShare = impliedMarketCap / base.shares;

    const userValuations = JSON.parse(localStorage.getItem('userPEValuations') || '{}');
    userValuations[currentCompanyId] = {
        impliedMarketCap,
        pricePerShare,
        peMultiple: multiple,
        savedAt: new Date().toISOString()
    };
    localStorage.setItem('userPEValuations', JSON.stringify(userValuations));

    const btn = event.target.closest('button');
    const origHtml = btn.innerHTML;
    btn.innerHTML = '✓ Saved!';
    btn.style.background = '#16a34a';

    const removeBtn = document.getElementById('pe-remove-valuation-btn');
    const indicator = document.getElementById('pe-user-valuation-indicator');
    if (removeBtn) removeBtn.style.display = 'block';
    if (indicator) {
        indicator.style.display = 'block';
        indicator.innerHTML = `Your custom valuation: <strong>$${pricePerShare.toFixed(2)}</strong>/share <span style="margin-left: 8px; color: var(--text-muted);">Saved ${new Date().toLocaleDateString()}</span>`;
    }

    setTimeout(() => {
        btn.innerHTML = 'Update Your Valuation';
        btn.style.background = 'linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%)';
    }, 1500);

    if (typeof loadCompanies === 'function') loadCompanies();
}

function getUserPEValuation(companyId) {
    const userValuations = JSON.parse(localStorage.getItem('userPEValuations') || '{}');
    return userValuations[companyId] || null;
}

function removePEValuation() {
    if (!currentCompanyId) return;

    const userValuations = JSON.parse(localStorage.getItem('userPEValuations') || '{}');
    delete userValuations[currentCompanyId];
    localStorage.setItem('userPEValuations', JSON.stringify(userValuations));

    resetPESensitivity();

    const removeBtn = document.getElementById('pe-remove-valuation-btn');
    const indicator = document.getElementById('pe-user-valuation-indicator');
    const saveBtn = document.getElementById('pe-save-valuation-btn');

    if (removeBtn) removeBtn.style.display = 'none';
    if (indicator) indicator.style.display = 'none';
    if (saveBtn) saveBtn.innerHTML = 'Save Your Valuation';

    if (typeof loadCompanies === 'function') loadCompanies();
}


// ============================================
// CHART RENDERING - ENHANCED
// ============================================

function renderValuationChart(result) {
    const ctx = document.getElementById('valuationChart');
    if (!ctx) return;
    
    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['DCF Method', 'EV/EBITDA Comp', 'P/E Comp', 'Current Market Cap'],
            datasets: [{
                label: 'Valuation ($M)',
                data: [
                    (result.dcf_equity_value / 1000000).toFixed(2),
                    (result.comp_ev_value / 1000000).toFixed(2),
                    (result.comp_pe_value / 1000000).toFixed(2),
                    (result.market_cap / 1000000).toFixed(2)
                ],
                backgroundColor: [
                    'rgba(17, 17, 17, 0.8)',
                    'rgba(139, 92, 246, 0.8)',
                    'rgba(236, 72, 153, 0.8)',
                    'rgba(245, 158, 11, 0.8)'
                ],
                borderColor: [
                    'rgb(59, 130, 246)',
                    'rgb(139, 92, 246)',
                    'rgb(236, 72, 153)',
                    'rgb(245, 158, 11)'
                ],
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: { display: false },
                title: {
                    display: false
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return '$' + context.parsed.y + 'M';
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        callback: function(value) {
                            return '$' + value + 'M';
                        }
                    },
                    grid: {
                        color: 'rgba(148, 163, 184, 0.1)'
                    }
                },
                x: {
                    grid: {
                        display: false
                    }
                }
            }
        }
    });
}

function renderMonteCarloChart(result) {
    const ctx = document.getElementById('monteCarloChart');
    if (!ctx) return;
    
    const mean = (result.mc_p10 + result.mc_p90) / 2;
    const p25 = result.mc_p10 + (mean - result.mc_p10) * 0.5;
    const p75 = result.mc_p90 - (result.mc_p90 - mean) * 0.5;
    
    new Chart(ctx, {
        type: 'line',
        data: {
            labels: ['P10', 'P25', 'Mean', 'P75', 'P90'],
            datasets: [{
                label: 'Valuation Range',
                data: [
                    (result.mc_p10 / 1000000).toFixed(2),
                    (p25 / 1000000).toFixed(2),
                    (mean / 1000000).toFixed(2),
                    (p75 / 1000000).toFixed(2),
                    (result.mc_p90 / 1000000).toFixed(2)
                ],
                fill: true,
                backgroundColor: 'rgba(17, 17, 17, 0.2)',
                borderColor: 'rgb(59, 130, 246)',
                borderWidth: 3,
                tension: 0.4,
                pointRadius: 5,
                pointBackgroundColor: 'rgb(59, 130, 246)',
                pointBorderColor: '#fff',
                pointBorderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return '$' + context.parsed.y + 'M';
                        }
                    }
                }
            },
            scales: {
                y: {
                    ticks: {
                        callback: function(value) {
                            return '$' + value + 'M';
                        }
                    },
                    grid: {
                        color: 'rgba(148, 163, 184, 0.1)'
                    }
                },
                x: {
                    grid: {
                        display: false
                    }
                }
            }
        }
    });
}

// ============================================
// LOADING STATES
// ============================================

function showLoadingState(message = 'Processing...') {
    const overlay = document.getElementById('loading-overlay');
    const text = document.getElementById('loading-text');
    if (overlay && text) {
        text.textContent = message;
        overlay.style.display = 'flex';
    }
}

function hideLoadingState() {
    const overlay = document.getElementById('loading-overlay');
    if (overlay) {
        overlay.style.display = 'none';
    }
}

// ============================================
// EXPORT FUNCTIONS
// ============================================

async function exportCSV() {
    try {
        showLoadingState('Generating CSV export...');
        window.location.href = '/api/export/csv';
        setTimeout(hideLoadingState, 1000);
    } catch (error) {
        hideLoadingState();
        console.error('Error exporting CSV:', error);
        alert('Error exporting data');
    }
}

function exportValuationPDF(companyId) {
    alert('📄 PDF export feature coming soon!\n\nThis will generate a comprehensive valuation report including all metrics, charts, and analysis.');
}


// ============================================
// SCENARIOS TAB (Sprint 0 - Phase 1 UI Connect)
// ============================================

let _scenarioCurrentCompanyId = null;
let _scenarioCurrentType = 'bear';
let _allScenarioData = {};  // { bear: {...}, base: {...}, bull: {...} }

async function initScenariosTab() {
    // Populate company selector
    const select = document.getElementById('scenario-company-select');
    if (!select) return;
    select.innerHTML = '<option value=>-- Choose a company --</option>';
    allCompanies.forEach(c => {
        const opt = document.createElement('option');
        opt.value = c.id;
        opt.textContent = c.name + (c.sector ? ' (' + c.sector + ')' : '');
        select.appendChild(opt);
    });

    // Load macro environments
    await loadMacroEnvironments();

    // Load audit trail
    await loadAuditTrail();
}

async function loadScenariosForCompany() {
    const select = document.getElementById('scenario-company-select');
    const companyId = select.value;
    if (!companyId) {
        document.getElementById('scenario-tabs-container').style.display = 'none';
        return;
    }
    _scenarioCurrentCompanyId = companyId;
    document.getElementById('scenario-tabs-container').style.display = 'block';

    // Fetch all 3 scenario types
    _allScenarioData = {};
    try {
        const resp = await fetch(`/api/scenarios/${companyId}`);
        if (resp.ok) {
            const data = await resp.json();
            for (const type of ['bear', 'base', 'bull']) {
                _allScenarioData[type] = data;
            }
        }
    } catch (e) {
        console.warn('Could not load scenarios for', companyId, e);
    }

    selectScenarioTab(_scenarioCurrentType);
}

function selectScenarioTab(type) {
    _scenarioCurrentType = type;
    document.querySelectorAll('.scenario-tab-btn').forEach(btn => btn.style.fontWeight = '400');
    const activeBtn = document.getElementById('tab-' + type);
    if (activeBtn) activeBtn.style.fontWeight = '700';

    // Hide compare table, show single card
    document.getElementById('scenario-compare-table').style.display = 'none';
    document.getElementById('scenario-single-card').style.display = 'block';

    renderScenarioCard(type);
}

function renderScenarioCard(type) {
    const container = document.getElementById('scenario-card-content');
    if (!container) return;

    // Try to get specific scenario from fetched data
    const data = _allScenarioData[type];
    const colorMap = { bear: '#ef4444', base: '#555555', bull: '#22c55e' };
    const color = colorMap[type] || '#111111';

    if (!data || !data.scenarios || data.scenarios.length === 0) {
        container.innerHTML = `<p style='color: var(--text-muted);'>No ${type} scenario data available for this company.</p>`;
        return;
    }

    // Find the matching scenario
    const scenarios = data.scenarios || [];
    const scenario = scenarios.find(s => s.name && s.name.toLowerCase().includes(type)) || scenarios[0];

    const assumptions = scenario.assumptions || {};
    const valuation = scenario.valuation || {};

    container.innerHTML = `
        <h3 style='color: ${color}; margin-bottom: 16px; text-transform: capitalize;'>${type} Case Scenario</h3>
        <div style='display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px;'>
            <div class='metric-card'>
                <div class='metric-label'>Fair Value</div>
                <div class='metric-value' style='color: ${color};'>${valuation.fair_value ? '$' + (+valuation.fair_value).toFixed(2) : '--'}</div>
            </div>
            <div class='metric-card'>
                <div class='metric-label'>Upside %</div>
                <div class='metric-value'>${valuation.upside_pct != null ? (+valuation.upside_pct).toFixed(1) + '%' : '--'}</div>
            </div>
            <div class='metric-card'>
                <div class='metric-label'>WACC</div>
                <div class='metric-value'>${valuation.wacc ? (+valuation.wacc * 100).toFixed(1) + '%' : '--'}</div>
            </div>
            <div class='metric-card'>
                <div class='metric-label'>Growth Y1</div>
                <div class='metric-value'>${assumptions.growth_rate_y1 != null ? (+assumptions.growth_rate_y1 * 100).toFixed(1) + '%' : '--'}</div>
            </div>
            <div class='metric-card'>
                <div class='metric-label'>Terminal Growth</div>
                <div class='metric-value'>${assumptions.terminal_growth != null ? (+assumptions.terminal_growth * 100).toFixed(2) + '%' : '--'}</div>
            </div>
            <div class='metric-card'>
                <div class='metric-label'>Scenario</div>
                <div class='metric-value' style='font-size: 14px; color: ${color}; text-transform: uppercase;'>${type}</div>
            </div>
        </div>
    `;
}

async function compareAllScenarios() {
    document.getElementById('scenario-compare-table').style.display = 'block';
    document.getElementById('scenario-single-card').style.display = 'none';

    const companyId = _scenarioCurrentCompanyId;
    if (!companyId) {
        document.getElementById('scenario-compare-content').innerHTML = '<p>Please select a company first.</p>';
        return;
    }

    try {
        const resp = await fetch(`/api/scenario/${companyId}/compare`, { method: 'POST' });
        let data = {};
        if (resp.ok) {
            data = await resp.json();
        }

        const colorMap = { bear: '#ef4444', base: '#555555', bull: '#22c55e' };
        const types = ['bear', 'base', 'bull'];

        let tableHtml = `
            <table style='width: 100%; border-collapse: collapse; font-size: 14px;'>
                <thead>
                    <tr style='border-bottom: 2px solid var(--border-color);'>
                        <th style='text-align: left; padding: 10px; color: var(--text-muted);'>Metric</th>
                        ${types.map(t => `<th style='text-align: center; padding: 10px; color: ${colorMap[t]}; text-transform: capitalize;'>${t.charAt(0).toUpperCase() + t.slice(1)} Case</th>`).join('')}
                    </tr>
                </thead>
                <tbody>
        `;

        const metrics = [
            { key: 'fair_value', label: 'Fair Value', fmt: v => v ? '$' + (+v).toFixed(2) : '--' },
            { key: 'upside_pct', label: 'Upside %', fmt: v => v != null ? (+v).toFixed(1) + '%' : '--' },
            { key: 'wacc', label: 'WACC', fmt: v => v != null ? (+v * 100).toFixed(1) + '%' : '--' },
            { key: 'growth_rate_y1', label: 'Growth Y1', fmt: v => v != null ? (+v * 100).toFixed(1) + '%' : '--' },
            { key: 'terminal_growth', label: 'Terminal Growth', fmt: v => v != null ? (+v * 100).toFixed(2) + '%' : '--' },
        ];

        metrics.forEach(m => {
            tableHtml += `<tr style='border-bottom: 1px solid var(--border-color);'>
                <td style='padding: 10px; font-weight: 500;'>${m.label}</td>
                ${types.map(t => {
                    const scenarioData = data[t] || data.scenarios?.find(s => s.name?.toLowerCase().includes(t)) || {};
                    const val = scenarioData[m.key] ?? scenarioData.valuation?.[m.key] ?? scenarioData.assumptions?.[m.key];
                    return `<td style='text-align: center; padding: 10px; color: ${colorMap[t]};'>${m.fmt(val)}</td>`;
                }).join('')}
            </tr>`;
        });

        tableHtml += '</tbody></table>';
        document.getElementById('scenario-compare-content').innerHTML = tableHtml;

    } catch (e) {
        console.error('Compare scenarios error:', e);
        document.getElementById('scenario-compare-content').innerHTML = '<p style="color: #ef4444;">Error loading comparison. Check console.</p>';
    }
}

async function loadMacroEnvironments() {
    try {
        const resp = await fetch('/api/macro-environments');
        if (!resp.ok) return;
        const data = await resp.json();
        const envs = data.environments || data || [];

        const select = document.getElementById('macro-env-select');
        if (!select) return;
        select.innerHTML = '<option value=>-- Select macro environment --</option>';
        envs.forEach(env => {
            const opt = document.createElement('option');
            opt.value = env.id;
            opt.textContent = env.name + (env.description ? ' — ' + env.description : '');
            select.appendChild(opt);
        });
    } catch (e) {
        console.warn('Could not load macro environments:', e);
    }
}

async function applyMacroToPortfolio() {
    const select = document.getElementById('macro-env-select');
    const envId = select?.value;
    const resultEl = document.getElementById('macro-apply-result');

    if (!envId) {
        if (resultEl) resultEl.innerHTML = '<p style="color: #ef4444;">Please select a macro environment first.</p>';
        return;
    }

    try {
        if (resultEl) resultEl.innerHTML = '<p style="color: var(--text-muted);">Applying...</p>';
        const resp = await fetch(`/api/macro-environment/${envId}/apply-to-portfolio`, { method: 'POST' });
        const data = await resp.json();
        if (resp.ok) {
            if (resultEl) resultEl.innerHTML = '<p style="color: #22c55e;">Macro environment applied successfully. Refresh to see updated valuations.</p>';
            loadCompanies();
        } else {
            if (resultEl) resultEl.innerHTML = `<p style='color: #ef4444;'>Error: ${data.error || 'Unknown error'}</p>`;
        }
    } catch (e) {
        console.error('Apply macro error:', e);
        if (resultEl) resultEl.innerHTML = '<p style="color: #ef4444;">Failed to apply macro environment.</p>';
    }
}

async function loadAuditTrail() {
    const container = document.getElementById('audit-trail-content');
    if (!container) return;

    try {
        const resp = await fetch('/api/audit-trail');
        if (!resp.ok) {
            container.innerHTML = '<p style="color: var(--text-muted);">Audit trail unavailable.</p>';
            return;
        }
        const data = await resp.json();
        const entries = (data.audit_trail || data || []).slice(0, 10);

        if (entries.length === 0) {
            container.innerHTML = '<p style="color: var(--text-muted);">No audit trail entries found.</p>';
            return;
        }

        let html = '<table style="width:100%; border-collapse: collapse; font-size: 13px;">';
        html += '<thead><tr style="border-bottom: 2px solid var(--border-color);">';
        html += '<th style="text-align:left; padding:8px; color:var(--text-muted);">Timestamp</th>';
        html += '<th style="text-align:left; padding:8px; color:var(--text-muted);">Company</th>';
        html += '<th style="text-align:left; padding:8px; color:var(--text-muted);">Field</th>';
        html += '<th style="text-align:left; padding:8px; color:var(--text-muted);">Old Value</th>';
        html += '<th style="text-align:left; padding:8px; color:var(--text-muted);">New Value</th>';
        html += '<th style="text-align:left; padding:8px; color:var(--text-muted);">User</th>';
        html += '</tr></thead><tbody>';

        entries.forEach(entry => {
            const ts = entry.timestamp || entry.changed_at || entry.created_at || '';
            const displayTs = ts ? new Date(ts).toLocaleString() : '--';
            html += '<tr style="border-bottom: 1px solid var(--border-color);">';
            html += `<td style="padding:8px; color:var(--text-muted); font-size:12px;">${displayTs}</td>`;
            html += `<td style="padding:8px;">${entry.company_name || entry.company_id || '--'}</td>`;
            html += `<td style="padding:8px; font-weight:500;">${entry.field_name || entry.field || '--'}</td>`;
            html += `<td style="padding:8px; color:#ef4444;">${entry.old_value ?? '--'}</td>`;
            html += `<td style="padding:8px; color:#22c55e;">${entry.new_value ?? '--'}</td>`;
            html += `<td style="padding:8px; color:var(--text-muted);">${entry.user || entry.changed_by || 'system'}</td>`;
            html += '</tr>';
        });

        html += '</tbody></table>';
        container.innerHTML = html;
    } catch (e) {
        console.error('Audit trail error:', e);
        container.innerHTML = '<p style="color: var(--text-muted);">Could not load audit trail.</p>';
    }
}


// ── AI Analyst Functions ─────────────────────────────────────────────────────

async function generateThesis() {
    if (!currentValuationCompanyId) return;
    const btn = document.getElementById('btn-thesis');
    const result = document.getElementById('thesis-result');
    btn.disabled = true;
    btn.textContent = 'Generating...';
    result.innerHTML = '<span style="color:var(--text-muted)">Calling OpenRouter... (~5s)</span>';
    try {
        const resp = await fetch(`/api/company/${currentValuationCompanyId}/thesis`, { method: 'POST' });
        const data = await resp.json();
        if (data.error) { result.innerHTML = `<span style="color:#ef4444">${data.error}</span>`; return; }
        result.innerHTML = `
            <div style="margin-bottom:12px;">
                <span style="font-size:11px;text-transform:uppercase;color:var(--text-muted);letter-spacing:.05em;">Recommendation</span>
                <div style="font-size:18px;font-weight:700;color:${data.recommendation==='BUY'?'#22c55e':data.recommendation==='SELL'?'#ef4444':'#f59e0b'};margin-top:2px;">${data.recommendation || 'N/A'} <span style="font-size:12px;color:var(--text-muted)">(${data.confidence || ''})</span></div>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px;">
                <div style="background:rgba(34,197,94,.08);border:1px solid rgba(34,197,94,.3);border-radius:6px;padding:10px;">
                    <div style="font-size:11px;color:#22c55e;margin-bottom:4px;">BULL CASE</div>
                    <div style="font-size:12px;">${data.bull_case || ''}</div>
                </div>
                <div style="background:rgba(239,68,68,.08);border:1px solid rgba(239,68,68,.3);border-radius:6px;padding:10px;">
                    <div style="font-size:11px;color:#ef4444;margin-bottom:4px;">BEAR CASE</div>
                    <div style="font-size:12px;">${data.bear_case || ''}</div>
                </div>
            </div>
            ${(data.key_risks||[]).length ? `<div><span style="font-size:11px;color:var(--text-muted);">KEY RISKS</span><ul style="margin:4px 0 0 16px;padding:0;">${data.key_risks.map(r=>`<li style="font-size:12px;margin-bottom:2px;">${r}</li>`).join('')}</ul></div>` : ''}
        `;
    } catch(e) {
        result.innerHTML = `<span style="color:#ef4444">Error: ${e.message}</span>`;
    }
    btn.disabled = false;
    btn.textContent = 'Generate Thesis';
}

async function generateCommentary() {
    if (!currentValuationCompanyId) return;
    const btn = document.getElementById('btn-commentary');
    const result = document.getElementById('commentary-result');
    btn.disabled = true;
    btn.textContent = 'Generating...';
    result.textContent = 'Calling OpenRouter...';
    try {
        const resp = await fetch(`/api/company/${currentValuationCompanyId}/commentary`);
        const data = await resp.json();
        result.textContent = data.commentary || data.error || 'No commentary returned';
    } catch(e) {
        result.textContent = `Error: ${e.message}`;
    }
    btn.disabled = false;
    btn.textContent = 'Generate';
}

async function runAgentAnalysis() {
    if (!currentValuationCompanyId) return;
    const query = document.getElementById('agent-query').value.trim();
    if (!query) { alert('Enter a query first'); return; }
    const btn = document.getElementById('btn-agent');
    const steps = document.getElementById('agent-steps');
    const result = document.getElementById('agent-result');
    btn.disabled = true;
    btn.textContent = 'Running...';
    steps.textContent = 'Starting agent loop...';
    result.textContent = '';

    try {
        const es = new EventSource(''); // placeholder, use fetch for POST SSE
        // Use fetch for POST + stream
        const resp = await fetch('/api/agent/analyze/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query, company_id: currentValuationCompanyId })
        });
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n\n');
            buffer = lines.pop() || '';
            for (const line of lines) {
                const dataLine = line.replace(/^data: /, '').trim();
                if (!dataLine) continue;
                try {
                    const event = JSON.parse(dataLine);
                    if (event.type === 'step') {
                        steps.textContent = `Step: ${event.tool}(${JSON.stringify(event.params).slice(0,60)}...)`;
                    } else if (event.type === 'complete') {
                        result.textContent = event.memo || 'Analysis complete';
                        steps.textContent = 'Done';
                    } else if (event.type === 'error') {
                        result.textContent = `Error: ${event.message}`;
                    }
                } catch(e) {}
            }
        }
    } catch(e) {
        result.textContent = `Error: ${e.message}`;
    }
    btn.disabled = false;
    btn.textContent = 'Run Full Analysis';
}

async function ingestDocs() {
    if (!currentValuationCompanyId) return;
    const btn = document.getElementById('btn-ingest');
    btn.disabled = true;
    btn.textContent = 'Ingesting...';
    try {
        const resp = await fetch(`/api/company/${currentValuationCompanyId}/ingest-docs`, { method: 'POST' });
        const data = await resp.json();
        document.getElementById('rag-result').textContent = data.error 
            ? `Error: ${data.error}` 
            : `Ingested ${data.chunks_stored} chunks from 10-K. Ready to ask questions.`;
    } catch(e) {
        document.getElementById('rag-result').textContent = `Error: ${e.message}`;
    }
    btn.disabled = false;
    btn.textContent = 'Ingest 10-K';
}

async function askFiling() {
    if (!currentValuationCompanyId) return;
    const question = document.getElementById('rag-question').value.trim();
    if (!question) return;
    const result = document.getElementById('rag-result');
    result.textContent = 'Searching filings...';
    try {
        const resp = await fetch(`/api/company/${currentValuationCompanyId}/ask`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question })
        });
        const data = await resp.json();
        if (data.error) { result.textContent = `Error: ${data.error}`; return; }
        result.innerHTML = `
            <div style="margin-bottom:8px;font-size:13px;">${data.answer || 'No answer'}</div>
            ${(data.sources||[]).length ? `<div style="font-size:11px;color:var(--text-muted);">Sources: ${data.sources.join(' | ')}</div>` : ''}
            <div style="font-size:10px;color:var(--text-muted);margin-top:4px;">Confidence: ${data.confidence || 'N/A'}</div>
        `;
    } catch(e) {
        result.textContent = `Error: ${e.message}`;
    }
}
