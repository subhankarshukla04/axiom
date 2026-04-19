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
let previousValuation = null; // Track previous valuation for comparison

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
        const upsideBarWidth = Math.min(Math.abs(upsideValue), 100);
        
        return `
            <div class="company-card" data-company-id="${company.id}">
                <div class="company-header">
                    <div class="company-name">${company.name}</div>
                    <div class="company-meta">
                        <span class="company-sector">${company.sector || 'N/A'}</span>
                        ${company.ticker ? `<span class="company-ticker">${company.ticker}</span>` : ''}
                    </div>
                </div>
                
                ${company.fair_value ? `
                    <!-- Main Metrics -->
                    <div class="company-metrics">
                        <div class="metric">
                            <div class="metric-label">DCF Fair Price</div>
                            <div class="metric-value clickable" onclick="showFairValueBreakdown(${company.id})">$${formatNumber(company.fair_value)}</div>
                        </div>
                        <div class="metric">
                            <div class="metric-label">Current Price</div>
                            <div class="metric-value company-current-price">$${company.current_price ? company.current_price.toFixed(2) : 'N/A'}</div>
                        </div>
                        <div class="metric">
                            <div class="metric-label">Market Cap</div>
                            <div class="metric-value company-market-cap">$${formatNumber(company.market_cap)}</div>
                        </div>
                        <div class="metric">
                            <div class="metric-label">Upside</div>
                            <div class="metric-value ${upsideClass}">
                                ${upsideValue >= 0 ? '+' : ''}${upsideValue.toFixed(1)}%
                            </div>
                        </div>
                    </div>
                    
                    <!-- Quality Scores -->
                    <div class="quality-scores">
                        <div class="quality-item">
                            <div class="quality-label">P/E</div>
                            <div class="quality-value">${company.pe_ratio ? company.pe_ratio.toFixed(1) + 'x' : 'N/A'}</div>
                        </div>
                        <div class="quality-item">
                            <div class="quality-label">ROE</div>
                            <div class="quality-value ${company.roe >= 15 ? 'text-positive' : ''}">${company.roe ? company.roe.toFixed(1) + '%' : 'N/A'}</div>
                        </div>
                        <div class="quality-item">
                            <div class="quality-label">Z-Score</div>
                            <div class="quality-value ${company.z_score >= 2.99 ? 'text-positive' : company.z_score < 1.81 ? 'text-negative' : ''}">${company.z_score ? company.z_score.toFixed(2) : 'N/A'}</div>
                        </div>
                    </div>
                    
                    <!-- Upside Visualization -->
                    <div class="upside-bar">
                        <div class="upside-label">
                            <span>Target vs Current</span>
                            <span class="upside-value ${upsideClass}">${upsideValue >= 0 ? '+' : ''}${upsideValue.toFixed(1)}%</span>
                        </div>
                        <div class="upside-visual">
                            <div class="upside-fill ${upsideClass}" style="width: ${upsideBarWidth}%"></div>
                        </div>
                    </div>
                    
                    <!-- Recommendation Badge -->
                    <div class="recommendation-badge ${recClass}">
                        ${company.recommendation || 'N/A'}
                    </div>
                ` : `
                    <div style="text-align: center; padding: 2rem; color: var(--text-tertiary);">
                        <p style="margin-bottom: 1rem;">📊 No valuation data yet</p>
                        <p style="font-size: 0.875rem;">Run a valuation to see detailed analysis</p>
                    </div>
                `}

                <!-- Scenario Selector (Bear/Base/Bull) -->
                <div class="scenario-selector">
                    <button class="scenario-btn bear" data-scenario="bear" onclick="applyScenarioToCompany(${company.id}, 'bear')" title="Pessimistic scenario">
                        🐻 Bear
                    </button>
                    <button class="scenario-btn base active" data-scenario="base" onclick="applyScenarioToCompany(${company.id}, 'base')" title="Balanced scenario">
                        📊 Base
                    </button>
                    <button class="scenario-btn bull" data-scenario="bull" onclick="applyScenarioToCompany(${company.id}, 'bull')" title="Optimistic scenario">
                        🐂 Bull
                    </button>
                </div>

                <!-- Action Buttons -->
                <div class="company-actions">
                    <button class="btn btn-primary" onclick="runValuation(${company.id})" title="${company.fair_value ? 'Re-run valuation' : 'Run initial valuation'}">
                        ${company.fair_value ? '🔄 Revalue' : '💰 Value'}
                    </button>
                    <button class="btn btn-secondary" onclick="editCompany(${company.id})" title="Edit company details">
                        ✏️ Edit
                    </button>
                    <button class="btn btn-danger" onclick="deleteCompany(${company.id})" title="Delete company">
                        🗑️
                    </button>
                    <button class="btn btn-secondary btn-icon" onclick="toggleWatchlist(${company.id})" title="Add to watchlist">
                        ⭐
                    </button>
                </div>
            </div>
        `;
    }).join('');
    
    document.getElementById('companies-grid').innerHTML = companiesHtml;
}

// Show fair value breakdown modal (fetch latest stored valuation and show detailed methods)
async function showFairValueBreakdown(companyId) {
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
            recommendation: val.recommendation || val.recommendation,
            upside_pct: val.upside_pct || val.upside_pct || 0,
            final_equity_value: val.final_equity_value || val.final_equity_value,
            final_price_per_share: val.final_price_per_share || val.final_price_per_share || 0,
            market_cap: val.market_cap || val.market_cap || 0,
            current_price: val.current_price || val.current_price || 0,
            dcf_equity_value: val.dcf_equity_value || val.dcf_equity_value,
            dcf_price_per_share: val.dcf_price_per_share || val.dcf_price_per_share || 0,
            comp_ev_value: val.comp_ev_value || val.comp_ev_value || 0,
            comp_pe_value: val.comp_pe_value || val.comp_pe_value || 0,
            mc_p10: val.mc_p10 || val.mc_p10 || 0,
            mc_p90: val.mc_p90 || val.mc_p90 || 0,
            wacc: val.wacc || 0,
            ev_ebitda: val.ev_ebitda || 0,
            pe_ratio: val.pe_ratio || 0,
            fcf_yield: val.fcf_yield || 0,
            roe: val.roe || 0,
            roic: val.roic || 0,
            debt_to_equity: val.debt_to_equity || 0,
            z_score: val.z_score || 0
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

function showValuationResults(result) {
    document.getElementById('valuation-modal').classList.add('active');
    document.getElementById('valuation-company-name').textContent = `${result.name} - Detailed Valuation`;

    const recClass = getRecommendationClass(result.recommendation);
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

    const html = `
        ${changeSection}

        <!-- Valuation Header -->
        <div class="valuation-header">
            <div class="recommendation">${result.recommendation || 'N/A'}</div>
            <div class="upside" style="color: rgba(255,255,255,0.95);">
                ${result.upside_pct >= 0 ? '↑' : '↓'} ${result.upside_pct >= 0 ? '+' : ''}${result.upside_pct.toFixed(1)}% ${result.upside_pct >= 0 ? 'Upside' : 'Downside'}
            </div>
        </div>

        <!-- Summary Metrics -->
        <div class="summary-grid">
            <div class="summary-item">
                <div class="summary-label">Fair Value (Equity)</div>
                <div class="summary-value">$${formatNumber(result.final_equity_value)}</div>
            </div>
            <div class="summary-item">
                <div class="summary-label">Fair Price/Share</div>
                <div class="summary-value">$${result.final_price_per_share.toFixed(2)}</div>
            </div>
            <div class="summary-item">
                <div class="summary-label">Current Market Cap</div>
                <div class="summary-value">$${formatNumber(result.market_cap)}</div>
            </div>
            <div class="summary-item">
                <div class="summary-label">Current Price</div>
                <div class="summary-value">$${result.current_price.toFixed(2)}</div>
            </div>
        </div>
        
        <!-- Valuation Methods -->
        <div class="valuation-section">
            <h3>Valuation Methods Comparison</h3>
            <div class="chart-container">
                <canvas id="valuationChart"></canvas>
            </div>
        </div>
        
        <!-- Key Financial Metrics -->
        <div class="metrics-grid">
            <div class="metric-item">
                <div class="summary-label">WACC</div>
                <div class="summary-value">${result.wacc.toFixed(2)}%</div>
            </div>
            <div class="metric-item">
                <div class="summary-label">EV/EBITDA</div>
                <div class="summary-value">${result.ev_ebitda.toFixed(1)}x</div>
            </div>
            <div class="metric-item">
                <div class="summary-label">P/E Ratio</div>
                <div class="summary-value">${result.pe_ratio.toFixed(1)}x</div>
            </div>
            <div class="metric-item">
                <div class="summary-label">FCF Yield</div>
                <div class="summary-value">${result.fcf_yield.toFixed(2)}%</div>
            </div>
            <div class="metric-item">
                <div class="summary-label">ROE</div>
                <div class="summary-value">${result.roe.toFixed(1)}%</div>
            </div>
            <div class="metric-item">
                <div class="summary-label">ROIC</div>
                <div class="summary-value">${result.roic.toFixed(1)}%</div>
            </div>
            <div class="metric-item">
                <div class="summary-label">Debt/Equity</div>
                <div class="summary-value">${result.debt_to_equity.toFixed(2)}x</div>
            </div>
            <div class="metric-item">
                <div class="summary-label">Altman Z-Score</div>
                <div class="summary-value ${result.z_score >= 2.99 ? 'text-positive' : result.z_score < 1.81 ? 'text-negative' : ''}">${result.z_score.toFixed(2)}</div>
            </div>
        </div>
        
        <!-- Monte Carlo Risk Analysis -->
        <div class="valuation-section">
            <h3>Monte Carlo Risk Analysis</h3>
            <div class="chart-container">
                <canvas id="monteCarloChart"></canvas>
            </div>
            <div style="margin-top: 1rem; padding: 1rem; background: var(--bg-secondary); border-radius: 8px;">
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 1rem; font-size: 0.875rem;">
                    <div>
                        <span style="color: var(--text-tertiary);">P10 (Pessimistic):</span>
                        <strong style="color: var(--text-primary); margin-left: 0.5rem;">$${formatNumber(result.mc_p10)}</strong>
                    </div>
                    <div>
                        <span style="color: var(--text-tertiary);">P50 (Base Case):</span>
                        <strong style="color: var(--text-primary); margin-left: 0.5rem;">$${formatNumber((result.mc_p10 + result.mc_p90) / 2)}</strong>
                    </div>
                    <div>
                        <span style="color: var(--text-tertiary);">P90 (Optimistic):</span>
                        <strong style="color: var(--text-primary); margin-left: 0.5rem;">$${formatNumber(result.mc_p90)}</strong>
                    </div>
                </div>
            </div>
        </div>
        
        <div style="margin-top: 2rem; padding-top: 1.5rem; border-top: 2px solid var(--border-primary); display: flex; gap: 1rem;">
            <button class="btn-submit" onclick="closeValuationModal()">Close</button>
            <button class="btn secondary" onclick="exportValuationPDF(${result.company_id})">📄 Export PDF</button>
        </div>
    `;
    
    document.getElementById('valuation-results').innerHTML = html;
    
    // Render charts
    setTimeout(() => {
        renderValuationChart(result);
        renderMonteCarloChart(result);
    }, 100);
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
                    'rgba(59, 130, 246, 0.8)',
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
                backgroundColor: 'rgba(59, 130, 246, 0.2)',
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
    const colorMap = { bear: '#ef4444', base: '#3b82f6', bull: '#22c55e' };
    const color = colorMap[type] || '#6366f1';

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

        const colorMap = { bear: '#ef4444', base: '#3b82f6', bull: '#22c55e' };
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
