/**
 * AXIOM UI — Phase 3 JavaScript
 * LBO, Football Field, Sensitivity, FRED live rates, exports, alerts, mode toggle, anomalies
 */

'use strict';

// ── Global state ──────────────────────────────────────────────────────────────
let currentValuationCompanyId = null;
let _axiomSSE = null;
let _axiomMode = localStorage.getItem('axiom-mode') || 'student';
let _axiomRatesFetchedAt = null;

// ── Init ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    applyMode(_axiomMode);
    loadMacroRates();
    connectLiveStream();
    loadAlertCount();
    addValNavLink();
});

// ── Mode Toggle ────────────────────────────────────────────────────────────────
function toggleMode() {
    _axiomMode = _axiomMode === 'student' ? 'professional' : 'student';
    localStorage.setItem('axiom-mode', _axiomMode);
    applyMode(_axiomMode);
}

function applyMode(mode) {
    const label = document.getElementById('mode-label');
    const thumb = document.getElementById('mode-thumb');
    const toggle = document.getElementById('mode-toggle');
    if (label) label.textContent = mode === 'professional' ? 'Pro' : 'Student';
    if (thumb) thumb.style.transform = mode === 'professional' ? 'translateX(20px)' : '';
    if (toggle) toggle.checked = mode === 'professional';
    document.body.dataset.mode = mode;

    // Professional: enable keyboard shortcuts
    if (mode === 'professional') {
        document.addEventListener('keydown', axiomKeyShortcuts);
    } else {
        document.removeEventListener('keydown', axiomKeyShortcuts);
    }
}

function axiomKeyShortcuts(e) {
    if (e.metaKey || e.ctrlKey) {
        if (e.key === 'Enter') { e.preventDefault(); }
    }
    if (e.key === 'F1' && !e.metaKey) { e.preventDefault(); switchValTab('vtab-dcf'); }
    if (e.key === 'F2' && !e.metaKey) { e.preventDefault(); switchValTab('vtab-lbo'); }
    if (e.key === 'F3' && !e.metaKey) { e.preventDefault(); switchValTab('vtab-ff'); }
    if (e.key === 'F4' && !e.metaKey) { e.preventDefault(); switchValTab('vtab-sens'); }
}

// ── Add Alerts to nav ─────────────────────────────────────────────────────────
function addValNavLink() {
    // Add alerts link to nav if not present
    const badge = document.getElementById('alerts-badge');
    if (badge) {
        badge.onclick = () => showView('alerts');
    }
}

// ── Ticker state ──────────────────────────────────────────────────────────────
let _tickerRates = [];
let _tickerCompanies = [];

// ── FRED Live Rates ───────────────────────────────────────────────────────────
async function loadMacroRates() {
    try {
        const resp = await fetch('/api/macro/rates');
        if (!resp.ok) return;
        const data = await resp.json();
        const rates = data.rates || {};

        const fmt = (v, d=2) => v != null ? (+v).toFixed(d) : '—';

        _tickerRates = [];

        const push = (label, key, suffix, scale=1, decimals=2) => {
            const r = rates[key];
            if (r && r.available) {
                _tickerRates.push({ label, value: fmt(r.value * scale, decimals) + suffix });
            }
        };

        push('10Y',  'risk_free_10y', '%');
        push('2Y',   'risk_free_2y',  '%');
        push('HY',   'hy_spread',     'bps', 100, 0);
        push('Fed',  'fed_funds',     '%');
        push('VIX',  'vix',           '', 1, 1);

        _axiomRatesFetchedAt = new Date();
        buildTicker();
        showTickerBar();
    } catch (e) {
        // Show ticker with placeholder rates so it still appears
        _tickerRates = [
            { label: '10Y', value: '—' },
            { label: '2Y',  value: '—' },
            { label: 'Fed', value: '—' },
            { label: 'VIX', value: '—' },
        ];
        buildTicker();
        showTickerBar();
        console.debug('AXIOM: FRED rates unavailable', e.message);
    }
}

function showTickerBar() {
    const bar = document.getElementById('axiom-rates-bar');
    if (bar) bar.style.display = '';
}

function updateTickerCompanies(companies) {
    _tickerCompanies = (companies || [])
        .filter(c => c.fair_value && c.current_price)
        .map(c => ({
            ticker:  c.ticker || c.name,
            fairVal: c.fair_value,
            price:   c.current_price,
            upside:  c.upside || 0,
        }));
    buildTicker();
}

function buildTicker() {
    const track = document.getElementById('ticker-track');
    if (!track) return;

    const items = [];

    // Rate items
    _tickerRates.forEach(r => {
        items.push(`
            <span class="ticker-item">
                <span class="ticker-label">${r.label}</span>
                <strong class="ticker-value">${r.value}</strong>
            </span>`);
    });

    // Separator between rates and companies
    if (_tickerCompanies.length > 0) {
        items.push(`<span class="ticker-sep"></span>`);

        // Company items
        _tickerCompanies.forEach(c => {
            const uClass = c.upside >= 0 ? 'positive' : 'negative';
            const sign   = c.upside >= 0 ? '+' : '';
            items.push(`
                <span class="ticker-item">
                    <span class="ticker-label">${c.ticker}</span>
                    <strong class="ticker-value">$${(+c.price).toFixed(2)}</strong>
                    <span class="ticker-upside ${uClass}">${sign}${(+c.upside).toFixed(1)}%</span>
                </span>`);
        });
    }

    if (items.length === 0) {
        track.innerHTML = '';
        return;
    }

    // Duplicate content for seamless infinite scroll
    const html = items.join('');
    track.innerHTML = html + html;
}

// ── Manual Price Refresh ──────────────────────────────────────────────────────
async function refreshPrices() {
    const btn = document.getElementById('refresh-prices-btn');
    if (btn) { btn.textContent = '⟳ Updating...'; btn.style.pointerEvents = 'none'; }
    try {
        const resp = await fetch('/api/prices/update', { method: 'POST' });
        const data = await resp.json();
        if (resp.ok) {
            const count = data.updated_count || (data.prices || []).length || 0;
            if (btn) btn.textContent = `✓ ${count} updated`;
            // Reload companies to show fresh prices
            if (typeof loadCompanies === 'function') setTimeout(loadCompanies, 300);
            if (typeof loadDashboard === 'function') setTimeout(loadDashboard, 400);
        } else {
            if (btn) btn.textContent = '✗ Failed';
        }
    } catch (e) {
        if (btn) btn.textContent = '✗ Error';
        console.error('Price refresh error:', e);
    } finally {
        setTimeout(() => { if (btn) { btn.textContent = '↻ Prices'; btn.style.pointerEvents = ''; } }, 3000);
    }
}

// ── Server-Sent Events Live Stream ────────────────────────────────────────────
function connectLiveStream() {
    if (typeof EventSource === 'undefined') return;
    if (_axiomSSE) { _axiomSSE.close(); }

    try {
        _axiomSSE = new EventSource('/api/live/stream');
        _axiomSSE.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.rates) updateRatesFromSSE(data.rates);
                if (data.alert_count !== undefined) updateAlertBadge(data.alert_count);
                const age = document.getElementById('rates-age');
                if (age) {
                    _axiomRatesFetchedAt = new Date();
                    age.textContent = 'Live';
                }
            } catch (e) { /* ignore parse errors */ }
        };
        _axiomSSE.onerror = () => {
            // SSE failed — fall back to polling every 5 minutes
            _axiomSSE.close();
            _axiomSSE = null;
            setTimeout(loadMacroRates, 5 * 60 * 1000);
        };
    } catch (e) {
        console.debug('AXIOM: SSE connection failed', e.message);
    }
}

function updateRatesFromSSE(rates) {
    const setSSE = (id, key, suffix) => {
        const el = document.getElementById(id);
        if (!el || !rates[key]) return;
        const v = rates[key].value;
        if (v != null) el.innerHTML = el.innerHTML.replace(/<strong>.*<\/strong>/, `<strong>${(+v).toFixed(2)}${suffix}</strong>`);
    };
    setSSE('rate-10y', 'risk_free_10y', '%');
    setSSE('rate-2y', 'risk_free_2y', '%');
    setSSE('rate-fed', 'fed_funds', '%');
    setSSE('rate-vix', 'vix', '');
}

// ── Alert Count Badge ─────────────────────────────────────────────────────────
async function loadAlertCount() {
    try {
        const resp = await fetch('/api/alerts?limit=1');
        if (!resp.ok) return;
        const data = await resp.json();
        updateAlertBadge(data.count || 0);
    } catch (e) { /* silent */ }
}

function updateAlertBadge(count) {
    const badge = document.getElementById('alerts-badge');
    if (!badge) return;
    if (count > 0) {
        badge.textContent = count;
        badge.style.display = 'inline-block';
    } else {
        badge.style.display = 'none';
    }
}

// ── Alerts View ───────────────────────────────────────────────────────────────
async function loadAlertsView() {
    const container = document.getElementById('axiom-alerts-list');
    if (!container) return;
    try {
        const resp = await fetch('/api/alerts?limit=50');
        const data = await resp.json();
        const alerts = data.alerts || [];

        if (!alerts.length) {
            container.innerHTML = '<p style="color:var(--text-muted);">No unread alerts.</p>';
            return;
        }

        const sevColor = { critical: '#ef4444', warning: '#fbbf24', info: '#3b82f6' };
        container.innerHTML = alerts.map(a => `
            <div style="padding:14px 16px;border-radius:8px;border-left:4px solid ${sevColor[a.severity]||'#6b7280'};background:var(--bg-secondary);display:flex;gap:12px;align-items:flex-start;">
                <div style="flex:1;">
                    <div style="font-size:12px;color:var(--text-muted);margin-bottom:4px;text-transform:uppercase;letter-spacing:1px;">${a.alert_type.replace(/_/g,' ')} · ${a.severity}</div>
                    <div style="font-size:14px;">${a.message}</div>
                    <div style="font-size:11px;color:var(--text-muted);margin-top:4px;">${new Date(a.created_at).toLocaleString()}</div>
                </div>
                <button onclick="axiomMarkRead(${a.id},this)" style="padding:4px 10px;background:transparent;border:1px solid var(--border-color);border-radius:4px;cursor:pointer;font-size:12px;">Dismiss</button>
            </div>
        `).join('');
    } catch (e) {
        container.innerHTML = `<p style="color:#ef4444;">Error loading alerts: ${e.message}</p>`;
    }
}

async function axiomMarkRead(alertId, btn) {
    try {
        await fetch(`/api/alerts/${alertId}/read`, { method: 'POST' });
        if (btn) btn.closest('[style*="border-left"]').remove();
        loadAlertCount();
    } catch (e) { console.error(e); }
}

async function axiomMarkAllRead() {
    try {
        await fetch('/api/alerts/read-all', { method: 'POST' });
        loadAlertsView();
        loadAlertCount();
    } catch (e) { console.error(e); }
}

// ── Valuation Modal Tabs ──────────────────────────────────────────────────────
function switchValTab(tabId, btn) {
    // Hide all panes
    document.querySelectorAll('.axiom-vtab-pane').forEach(p => p.style.display = 'none');
    // Deactivate all tab buttons
    document.querySelectorAll('.axiom-vtab').forEach(b => {
        b.classList.remove('active');
        b.style.borderBottom = 'none';
        b.style.color = 'var(--text-muted)';
        b.style.fontWeight = '400';
    });
    // Show selected pane
    const pane = document.getElementById(tabId);
    if (pane) pane.style.display = 'block';
    // Activate selected tab btn
    const activeBtn = btn || document.querySelector(`[data-tab="${tabId}"]`);
    if (activeBtn) {
        activeBtn.classList.add('active');
        activeBtn.style.borderBottom = '2px solid #3b82f6';
        activeBtn.style.color = '#3b82f6';
        activeBtn.style.fontWeight = '600';
    }

    // Lazy-load content on first switch
    if (tabId === 'vtab-lbo' && currentValuationCompanyId) {
        // LBO inputs are manual — just show the form
    } else if (tabId === 'vtab-ff' && currentValuationCompanyId) {
        if (!document.getElementById('axiom-ff-chart').children.length) {
            loadFootballField(currentValuationCompanyId);
        }
    } else if (tabId === 'vtab-sens' && currentValuationCompanyId) {
        if (!document.getElementById('axiom-sens-table').innerHTML.trim()) {
            loadSensitivityTable(currentValuationCompanyId);
        }
    } else if (tabId === 'vtab-peers' && currentValuationCompanyId) {
        if (!document.getElementById('axiom-peers-table').innerHTML.trim()) {
            loadPeers(currentValuationCompanyId);
        }
    }
}

// Patch showValuationResults to capture company ID and reset tabs
const _origShowValuationResults = typeof showValuationResults !== 'undefined' ? showValuationResults : null;
if (_origShowValuationResults) {
    window.showValuationResults = function(result) {
        currentValuationCompanyId = result.company_id || null;
        // Reset tabs to DCF
        setTimeout(() => {
            switchValTab('vtab-dcf');
            if (currentValuationCompanyId) {
                loadAnomalies(currentValuationCompanyId);
            }
        }, 50);
        _origShowValuationResults(result);
    };
}

// Also patch showFairValueBreakdown
const _origShowFVB = typeof showFairValueBreakdown !== 'undefined' ? showFairValueBreakdown : null;
document.addEventListener('axiom:company-open', (e) => {
    currentValuationCompanyId = e.detail.companyId;
});

// ── Anomaly Detection ─────────────────────────────────────────────────────────
async function loadAnomalies(companyId) {
    if (!companyId) return;
    try {
        const resp = await fetch(`/api/company/${companyId}/anomalies`);
        if (!resp.ok) return;
        const data = await resp.json();
        const panel = document.getElementById('axiom-anomaly-panel');
        const list = document.getElementById('axiom-anomaly-list');
        if (!panel || !list) return;

        const anomalies = data.anomalies || [];
        if (!anomalies.length) {
            panel.style.display = 'none';
            return;
        }

        const sevIcon = { critical: '🔴', warning: '⚠️', info: 'ℹ️' };
        list.innerHTML = anomalies.map(a => `
            <div style="display:flex;gap:8px;align-items:flex-start;">
                <span>${sevIcon[a.severity] || '⚠️'}</span>
                <span>${a.message}</span>
            </div>
        `).join('');
        panel.style.display = 'block';
    } catch (e) {
        console.debug('AXIOM: anomaly check failed', e.message);
    }
}

// ── LBO Analysis ──────────────────────────────────────────────────────────────
async function runLBOAnalysis() {
    const companyId = currentValuationCompanyId;
    if (!companyId) {
        alert('Open a company valuation first, then switch to the LBO tab.');
        return;
    }

    const entry = parseFloat(document.getElementById('lbo-entry-mult').value) || 10;
    const leverage = parseFloat(document.getElementById('lbo-leverage').value) || 5;
    const exit = parseFloat(document.getElementById('lbo-exit-mult').value) || 10;
    const hold = parseInt(document.getElementById('lbo-hold').value) || 5;

    const container = document.getElementById('axiom-lbo-results');
    container.innerHTML = '<p style="color:var(--text-muted);">Running LBO model...</p>';

    try {
        const resp = await fetch(`/api/lbo/${companyId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                entry_multiple: entry,
                leverage: leverage,
                exit_multiple: exit,
                hold_period: hold,
            }),
        });

        if (!resp.ok) {
            const err = await resp.json();
            container.innerHTML = `<p style="color:#ef4444;">LBO Error: ${err.error}</p>`;
            return;
        }

        const lbo = await resp.json();
        renderLBOResults(lbo, container);
    } catch (e) {
        container.innerHTML = `<p style="color:#ef4444;">LBO Error: ${e.message}</p>`;
    }
}

function renderLBOResults(lbo, container) {
    const signalColor = { strong: '#22c55e', acceptable: '#fbbf24', weak: '#ef4444', unknown: '#6b7280' };
    const color = signalColor[lbo.irr_signal] || '#6b7280';

    // Summary metrics
    let html = `
        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:20px;">
            <div style="padding:16px;background:var(--bg-secondary);border-radius:8px;border-left:4px solid ${color};">
                <div style="font-size:11px;color:var(--text-muted);margin-bottom:6px;">IRR</div>
                <div style="font-size:28px;font-weight:700;color:${color};">${lbo.irr != null ? lbo.irr.toFixed(1)+'%' : '—'}</div>
                <div style="font-size:12px;color:${color};text-transform:capitalize;">${lbo.irr_signal}</div>
            </div>
            <div style="padding:16px;background:var(--bg-secondary);border-radius:8px;">
                <div style="font-size:11px;color:var(--text-muted);margin-bottom:6px;">MOIC</div>
                <div style="font-size:28px;font-weight:700;">${lbo.moic != null ? lbo.moic.toFixed(2)+'x' : '—'}</div>
            </div>
            <div style="padding:16px;background:var(--bg-secondary);border-radius:8px;">
                <div style="font-size:11px;color:var(--text-muted);margin-bottom:6px;">Entry Equity</div>
                <div style="font-size:22px;font-weight:600;">$${_axiomFmt(lbo.entry_equity)}M</div>
            </div>
            <div style="padding:16px;background:var(--bg-secondary);border-radius:8px;">
                <div style="font-size:11px;color:var(--text-muted);margin-bottom:6px;">Exit Equity</div>
                <div style="font-size:22px;font-weight:600;color:#22c55e;">$${_axiomFmt(lbo.exit_equity)}M</div>
            </div>
        </div>
    `;

    // Debt paydown schedule
    if (lbo.debt_paydown_schedule && lbo.debt_paydown_schedule.length) {
        html += `
        <h4 style="margin-bottom:10px;font-size:13px;text-transform:uppercase;letter-spacing:1px;color:var(--text-muted);">Debt Paydown Schedule ($M)</h4>
        <div style="overflow-x:auto;margin-bottom:20px;">
        <table style="width:100%;border-collapse:collapse;font-size:13px;font-family:'Courier New',monospace;">
            <thead>
                <tr style="border-bottom:1px solid var(--border-color);">
                    <th style="text-align:left;padding:6px 10px;color:var(--text-muted);">Year</th>
                    <th style="text-align:right;padding:6px 10px;color:var(--text-muted);">Revenue</th>
                    <th style="text-align:right;padding:6px 10px;color:var(--text-muted);">EBITDA</th>
                    <th style="text-align:right;padding:6px 10px;color:var(--text-muted);">Interest</th>
                    <th style="text-align:right;padding:6px 10px;color:var(--text-muted);">FCF</th>
                    <th style="text-align:right;padding:6px 10px;color:var(--text-muted);">Paydown</th>
                    <th style="text-align:right;padding:6px 10px;color:var(--text-muted);">Remaining Debt</th>
                </tr>
            </thead>
            <tbody>
            ${lbo.debt_paydown_schedule.map(r => `
                <tr style="border-bottom:1px solid var(--border-color);">
                    <td style="padding:6px 10px;font-weight:600;">Y${r.year}</td>
                    <td style="text-align:right;padding:6px 10px;">$${_axiomFmt(r.revenue)}</td>
                    <td style="text-align:right;padding:6px 10px;">$${_axiomFmt(r.ebitda)}</td>
                    <td style="text-align:right;padding:6px 10px;color:#ef4444;">($${_axiomFmt(r.interest)})</td>
                    <td style="text-align:right;padding:6px 10px;color:#22c55e;">$${_axiomFmt(r.fcf)}</td>
                    <td style="text-align:right;padding:6px 10px;color:#3b82f6;">$${_axiomFmt(r.paydown)}</td>
                    <td style="text-align:right;padding:6px 10px;">$${_axiomFmt(r.remaining_debt)}</td>
                </tr>
            `).join('')}
            </tbody>
        </table>
        </div>`;
    }

    // 5x5 Sensitivity grid
    const grid = lbo.sensitivity_grid;
    if (grid && grid.irr_matrix) {
        const sigBg = { strong: 'rgba(34,197,94,0.2)', acceptable: 'rgba(251,191,36,0.2)', weak: 'rgba(239,68,68,0.2)', invalid: 'rgba(100,100,100,0.1)', unknown: 'transparent', error: 'transparent' };
        html += `
        <h4 style="margin-bottom:10px;font-size:13px;text-transform:uppercase;letter-spacing:1px;color:var(--text-muted);">IRR Sensitivity — Exit Multiple vs Leverage</h4>
        <div style="overflow-x:auto;">
        <table style="border-collapse:collapse;font-size:13px;font-family:'Courier New',monospace;">
            <thead>
                <tr>
                    <th style="padding:6px 14px;text-align:left;color:var(--text-muted);white-space:nowrap;">Leverage \\ Exit</th>
                    ${grid.exit_multiples.map(m => `<th style="padding:6px 14px;text-align:center;color:var(--text-muted);">${m}x</th>`).join('')}
                </tr>
            </thead>
            <tbody>
            ${grid.irr_matrix.map((row, ri) => `
                <tr>
                    <td style="padding:6px 14px;font-weight:600;">${grid.leverage_levels[ri]}x</td>
                    ${row.map(cell => `<td style="padding:6px 14px;text-align:center;background:${sigBg[cell.signal]||'transparent'};border-radius:4px;">${cell.irr != null ? cell.irr+'%' : '—'}</td>`).join('')}
                </tr>
            `).join('')}
            </tbody>
        </table>
        <div style="margin-top:8px;font-size:11px;color:var(--text-muted);">Green ≥ 25% IRR (strong) &nbsp; Yellow 15–25% (acceptable) &nbsp; Red &lt; 15% (weak)</div>
        </div>`;
    }

    container.innerHTML = html;
}

// ── Football Field ────────────────────────────────────────────────────────────
async function loadFootballField(companyId) {
    const chartEl = document.getElementById('axiom-ff-chart');
    const tableEl = document.getElementById('axiom-ff-table');
    if (!chartEl) return;
    chartEl.innerHTML = '<p style="color:var(--text-muted);padding:20px;">Loading football field...</p>';

    try {
        const resp = await fetch(`/api/company/${companyId}/football-field`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        renderFootballField(data, chartEl, tableEl);
    } catch (e) {
        chartEl.innerHTML = `<p style="color:#ef4444;">Football field error: ${e.message}</p>`;
    }
}

function renderFootballField(data, chartEl, tableEl) {
    const ranges = (data.ranges || []).filter(r => r.available);
    const gapRanges = (data.ranges || []).filter(r => !r.available);
    const currentPrice = data.current_price;

    if (!ranges.length) {
        chartEl.innerHTML = '<p style="color:var(--text-muted);">No valuation range data available.</p>';
        return;
    }

    // Build Plotly horizontal bar chart
    const methods = ranges.map(r => r.method);
    const lows = ranges.map(r => r.low);
    const highs = ranges.map(r => r.high);
    const mids = ranges.map(r => (r.low + r.high) / 2);

    const plotData = [
        // Invisible base bars
        {
            type: 'bar', orientation: 'h',
            x: lows, y: methods,
            marker: { color: 'rgba(0,0,0,0)' },
            showlegend: false, hoverinfo: 'skip',
        },
        // Visible range bars
        {
            type: 'bar', orientation: 'h',
            x: ranges.map(r => r.high - r.low), y: methods,
            marker: { color: 'rgba(59,130,246,0.65)', line: { color: 'rgba(59,130,246,1)', width: 1 } },
            text: ranges.map(r => `$${r.low.toFixed(0)} – $${r.high.toFixed(0)}`),
            textposition: 'outside',
            hovertemplate: '%{y}: $%{base:.2f} – $%{x:.2f}<extra>%{customdata}</extra>',
            customdata: ranges.map(r => r.source),
            base: lows,
            showlegend: false,
        }
    ];

    const layout = {
        paper_bgcolor: 'transparent',
        plot_bgcolor: 'transparent',
        height: 280,
        margin: { l: 160, r: 80, t: 20, b: 40 },
        xaxis: {
            title: 'Implied Value per Share ($)',
            tickprefix: '$',
            gridcolor: 'rgba(150,150,150,0.15)',
        },
        yaxis: { autorange: 'reversed' },
        shapes: currentPrice ? [{
            type: 'line', x0: currentPrice, x1: currentPrice, y0: -0.5, y1: methods.length - 0.5,
            line: { color: '#ef4444', width: 2, dash: 'dot' },
        }] : [],
        annotations: currentPrice ? [{
            x: currentPrice, y: methods.length - 0.5, text: `$${currentPrice.toFixed(1)}<br>Market`,
            showarrow: false, font: { color: '#ef4444', size: 10 }, xanchor: 'center', yanchor: 'top',
        }] : [],
    };

    chartEl.innerHTML = '';
    if (typeof Plotly !== 'undefined') {
        Plotly.newPlot(chartEl, plotData, layout, { displayModeBar: false, responsive: true });
    } else {
        chartEl.innerHTML = '<p style="color:var(--text-muted);">Plotly not loaded — refresh page.</p>';
    }

    // Gap disclosures table
    if (tableEl && gapRanges.length) {
        tableEl.innerHTML = `
            <div style="padding:12px 16px;background:rgba(239,68,68,0.05);border:1px solid rgba(239,68,68,0.2);border-radius:6px;">
                <div style="font-size:12px;font-weight:600;color:#ef4444;margin-bottom:8px;">Data Gaps</div>
                ${gapRanges.map(r => `
                    <div style="font-size:12px;color:var(--text-muted);margin-bottom:4px;">
                        <strong>${r.method}:</strong> ${r.gap_reason || 'Data unavailable'}
                    </div>
                `).join('')}
            </div>`;
    }
}

// ── Sensitivity Table ─────────────────────────────────────────────────────────
async function loadSensitivityTable(companyId) {
    const container = document.getElementById('axiom-sens-table');
    if (!container) return;
    container.innerHTML = '<p style="color:var(--text-muted);">Computing sensitivity matrix...</p>';

    try {
        const resp = await fetch(`/api/company/${companyId}/sensitivity?x=wacc&y=terminal_growth`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        renderSensitivityTable(data, container);
    } catch (e) {
        container.innerHTML = `<p style="color:#ef4444;">Sensitivity error: ${e.message}</p>`;
    }
}

function renderSensitivityTable(data, container) {
    const xVals = data.x_axis.formatted;
    const yVals = data.y_axis.formatted;
    const cells = data.cells;
    const currentPrice = data.current_price;
    const baseCase = data.base_case;

    const sigStyle = {
        strong_buy: 'background:rgba(34,197,94,0.35);font-weight:700;',
        buy: 'background:rgba(34,197,94,0.18);',
        hold: 'background:rgba(251,191,36,0.25);',
        sell: 'background:rgba(239,68,68,0.18);',
        strong_sell: 'background:rgba(239,68,68,0.35);font-weight:700;',
        unknown: 'background:rgba(150,150,150,0.1);',
    };

    let html = `<table style="border-collapse:collapse;font-size:12px;font-family:'Courier New',monospace;min-width:600px;">`;
    html += `<thead><tr>
        <th style="padding:6px 12px;text-align:left;color:var(--text-muted);white-space:nowrap;">${data.y_axis.label} \\ ${data.x_axis.label}</th>
        ${xVals.map(v => `<th style="padding:6px 12px;text-align:center;color:var(--text-muted);">${v}</th>`).join('')}
    </tr></thead><tbody>`;

    cells.forEach((row, ri) => {
        html += `<tr>`;
        html += `<td style="padding:6px 12px;font-weight:600;white-space:nowrap;">${yVals[ri]}</td>`;
        row.forEach((cell) => {
            const style = sigStyle[cell.signal] || '';
            const isBase = cell.is_base ? 'box-shadow:0 0 0 2px #3b82f6 inset;' : '';
            const val = cell.value != null ? `$${cell.value.toFixed(2)}` : '—';
            html += `<td style="padding:6px 12px;text-align:center;${style}${isBase}">${val}</td>`;
        });
        html += `</tr>`;
    });

    html += '</tbody></table>';

    if (currentPrice) {
        html += `<div style="margin-top:8px;font-size:11px;color:var(--text-muted);">
            Current price: <strong>$${currentPrice.toFixed(2)}</strong> &nbsp;
            ${baseCase ? `Base case: <strong>$${(baseCase.value||0).toFixed(2)}</strong>` : ''}
            &nbsp; Blue border = base case &nbsp; Green = buy, Yellow = hold, Red = sell
        </div>`;
    }

    container.innerHTML = html;
}

// ── Exports ───────────────────────────────────────────────────────────────────
function axiomExportExcel(companyId) {
    if (!companyId) { alert('Open a company valuation first.'); return; }
    const link = document.createElement('a');
    link.href = `/api/company/${companyId}/export/excel`;
    link.download = '';
    link.click();
}

function axiomExportPDF(companyId) {
    if (!companyId) { alert('Open a company valuation first.'); return; }
    const link = document.createElement('a');
    link.href = `/api/company/${companyId}/export/pdf`;
    link.download = '';
    link.click();
}

// Also patch the existing exportValuationPDF if it exists
if (typeof exportValuationPDF !== 'undefined') {
    window.exportValuationPDF = axiomExportPDF;
}

// ── showView extension ────────────────────────────────────────────────────────
// Patch showView to handle the new 'alerts' view
const _origShowView = typeof showView !== 'undefined' ? showView : null;
if (_origShowView) {
    window.showView = function(viewName) {
        const alertsView = document.getElementById('alerts-view');
        if (alertsView) alertsView.style.display = 'none';

        if (viewName === 'alerts') {
            // Hide all other view-sections
            document.querySelectorAll('.view-section').forEach(s => s.classList.remove('active'));
            document.querySelectorAll('.view-section').forEach(s => s.style.display = 'none');
            if (alertsView) alertsView.style.display = 'block';
            loadAlertsView();
            // Update nav
            document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
            return;
        }
        _origShowView(viewName);
    };
}

// ── Utility ───────────────────────────────────────────────────────────────────
function _axiomFmt(n) {
    if (n == null) return '—';
    return (+n).toLocaleString('en-US', { maximumFractionDigits: 1 });
}

// ── Portfolio Optimization ────────────────────────────────────────────────────

function runPortfolioOptimize() {
    const btn = document.getElementById('axiom-portfolio-optimize-btn');
    const out = document.getElementById('axiom-portfolio-results');
    if (!out) return;

    if (btn) btn.textContent = 'Optimizing...';
    out.innerHTML = '<p style="color:#8b949e">Running mean-variance optimization...</p>';

    const constraints = {
        max_single_position: parseFloat(document.getElementById('po-max-pos')?.value || '0.20'),
        min_single_position: parseFloat(document.getElementById('po-min-pos')?.value || '0.02'),
        max_sector_exposure: parseFloat(document.getElementById('po-max-sector')?.value || '0.40'),
        risk_tolerance: document.getElementById('po-risk-tol')?.value || 'Moderate',
        target_num_holdings: parseInt(document.getElementById('po-num-hold')?.value || '15'),
    };
    const target_value = parseFloat(document.getElementById('po-target-val')?.value || '1000000');

    fetch('/api/portfolio/optimize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ constraints, target_value }),
    })
    .then(r => r.json())
    .then(data => {
        if (btn) btn.textContent = 'Optimize Portfolio';
        if (data.error) { out.innerHTML = `<p style="color:#f85149">Error: ${data.error}</p>`; return; }
        renderPortfolioResults(data, out);
    })
    .catch(e => {
        if (btn) btn.textContent = 'Optimize Portfolio';
        out.innerHTML = `<p style="color:#f85149">Request failed: ${e.message}</p>`;
    });
}

function renderPortfolioResults(data, container) {
    const m = data.metrics || {};
    const alloc = data.allocations || {};

    const sortedAlloc = Object.entries(alloc)
        .sort((a, b) => b[1] - a[1])
        .map(([ticker, w]) => `
            <tr>
              <td style="padding:0.4rem 0.75rem;font-family:var(--num-font,monospace)">${ticker}</td>
              <td style="padding:0.4rem 0.75rem;text-align:right;font-family:var(--num-font,monospace)">${(w*100).toFixed(1)}%</td>
              <td style="padding:0.4rem 0.75rem;text-align:right;font-family:var(--num-font,monospace)">$${(w * (data.target_value || 1000000)).toLocaleString('en-US', {maximumFractionDigits:0})}</td>
            </tr>`).join('');

    container.innerHTML = `
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:0.75rem;margin-bottom:1.5rem">
          <div style="background:#161b22;border:1px solid #30363d;border-radius:6px;padding:1rem">
            <div style="font-size:0.7rem;color:#8b949e;text-transform:uppercase">Expected Return</div>
            <div style="font-size:1.4rem;font-weight:700;color:#3fb950;font-family:var(--num-font,monospace)">${((m.expected_return||0)*100).toFixed(1)}%</div>
          </div>
          <div style="background:#161b22;border:1px solid #30363d;border-radius:6px;padding:1rem">
            <div style="font-size:0.7rem;color:#8b949e;text-transform:uppercase">Volatility</div>
            <div style="font-size:1.4rem;font-weight:700;font-family:var(--num-font,monospace)">${((m.volatility||0)*100).toFixed(1)}%</div>
          </div>
          <div style="background:#161b22;border:1px solid #30363d;border-radius:6px;padding:1rem">
            <div style="font-size:0.7rem;color:#8b949e;text-transform:uppercase">Sharpe Ratio</div>
            <div style="font-size:1.4rem;font-weight:700;font-family:var(--num-font,monospace)">${(m.sharpe_ratio||0).toFixed(2)}</div>
          </div>
          <div style="background:#161b22;border:1px solid #30363d;border-radius:6px;padding:1rem">
            <div style="font-size:0.7rem;color:#8b949e;text-transform:uppercase">Holdings</div>
            <div style="font-size:1.4rem;font-weight:700;font-family:var(--num-font,monospace)">${m.num_holdings||0}</div>
          </div>
          <div style="background:#161b22;border:1px solid #30363d;border-radius:6px;padding:1rem">
            <div style="font-size:0.7rem;color:#8b949e;text-transform:uppercase">Wtd. Upside</div>
            <div style="font-size:1.4rem;font-weight:700;color:#3fb950;font-family:var(--num-font,monospace)">${((m.weighted_upside||0)).toFixed(1)}%</div>
          </div>
        </div>
        <table style="width:100%;border-collapse:collapse;font-size:0.85rem">
          <thead>
            <tr style="border-bottom:1px solid #30363d;color:#8b949e">
              <th style="padding:0.4rem 0.75rem;text-align:left">Ticker</th>
              <th style="padding:0.4rem 0.75rem;text-align:right">Weight</th>
              <th style="padding:0.4rem 0.75rem;text-align:right">Dollar Allocation</th>
            </tr>
          </thead>
          <tbody>${sortedAlloc}</tbody>
        </table>
        ${data.report ? `<details style="margin-top:1rem"><summary style="cursor:pointer;color:#58a6ff;font-size:0.85rem">View Full Report</summary><pre style="margin-top:0.5rem;font-size:0.8rem;white-space:pre-wrap;color:#8b949e">${data.report}</pre></details>` : ''}
    `;
}

// ── Institutional Score Display ───────────────────────────────────────────────

function loadInstitutionalScore(companyId) {
    const container = document.getElementById('axiom-inst-score');
    if (!container || !companyId) return;

    container.innerHTML = '<span style="color:#8b949e;font-size:0.8rem">Loading quality score...</span>';

    fetch(`/api/company/${companyId}/institutional-score`)
        .then(r => r.json())
        .then(data => {
            if (data.error) { container.innerHTML = ''; return; }
            const grade = data.quality_grade || '—';
            const gradeColor = grade === 'A' ? '#3fb950' : grade === 'B' ? '#d29922' : grade === 'C' ? '#f0883e' : '#f85149';
            const scoreNum = (data.quality_score * 100).toFixed(0);
            container.innerHTML = `
                <span style="display:inline-flex;align-items:center;gap:0.5rem;font-size:0.82rem;background:var(--bg-tertiary);border:1px solid var(--border-primary);border-radius:4px;padding:0.3rem 0.6rem;flex-wrap:wrap">
                  <span class="axiom-tip" data-tip="Company quality score based on profitability (ROE, ROIC), margins, cash flow conversion, and leverage. A = excellent, D = poor." style="color:var(--text-secondary);display:inline-flex;align-items:center;gap:0.35rem">
                    Quality
                    <span style="font-family:var(--font-mono);font-weight:700;color:${gradeColor}">${grade}</span>
                    <span style="color:var(--text-tertiary)">${scoreNum}/100</span>
                  </span>
                  <span style="color:var(--border-secondary)">|</span>
                  <span class="axiom-tip" data-tip="Valuation complexity: STRAIGHTFORWARD = stable, predictable business. COMPLEX/HIGHLY_COMPLEX = multiple segments, cyclicality, or turnaround situations." style="color:var(--text-secondary)">${data.complexity || ''}</span>
                  <span style="color:var(--border-secondary)">|</span>
                  <span class="axiom-tip" data-tip="Our confidence in this valuation based on data completeness and comparable companies available." style="color:var(--text-secondary)">Conf: ${data.confidence || '—'}</span>
                  ${data.suggested_wacc ? `<span style="color:var(--border-secondary)">|</span><span class="axiom-tip" data-tip="Suggested discount rate (WACC) based on the company's risk profile, beta, and capital structure." style="color:var(--text-secondary)">WACC: <span style="color:var(--text-primary)">${(data.suggested_wacc*100).toFixed(1)}%</span></span>` : ''}
                </span>`;
        })
        .catch(() => { container.innerHTML = ''; });
}

// ── Share Link UI ─────────────────────────────────────────────────────────────

function axiomCreateShareLink(companyId) {
    if (!companyId) { alert('Open a company valuation first.'); return; }
    const btn = document.getElementById('axiom-share-btn');
    if (btn) btn.textContent = 'Creating link...';

    fetch(`/api/company/${companyId}/share`, { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            if (btn) btn.textContent = 'Share';
            if (data.error) { alert('Error: ' + data.error); return; }
            const url = window.location.origin + data.share_url;
            // Show copy dialog
            const modal = document.createElement('div');
            modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.7);display:flex;justify-content:center;align-items:center;z-index:9999';
            modal.innerHTML = `
                <div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:2rem;max-width:480px;width:90%">
                  <div style="font-size:1rem;font-weight:600;margin-bottom:1rem">Share Valuation</div>
                  <input id="axiom-share-url-input" value="${url}" readonly
                         style="width:100%;background:#0d1117;border:1px solid #30363d;border-radius:4px;padding:0.5rem 0.75rem;color:#e6edf3;font-family:monospace;font-size:0.85rem;box-sizing:border-box">
                  <div style="margin-top:0.5rem;font-size:0.78rem;color:#8b949e">
                    Read-only link. Expires ${data.expires_at ? data.expires_at.slice(0,10) : '30 days'}.
                    Audit trail and notes are hidden.
                  </div>
                  <div style="display:flex;gap:0.75rem;margin-top:1.25rem;justify-content:flex-end">
                    <button onclick="navigator.clipboard.writeText('${url}').then(()=>this.textContent='Copied!')"
                            style="background:#238636;border:none;border-radius:6px;padding:0.5rem 1rem;color:#fff;cursor:pointer;font-size:0.85rem">
                      Copy Link
                    </button>
                    <button onclick="this.closest('[style*=fixed]').remove()"
                            style="background:#21262d;border:1px solid #30363d;border-radius:6px;padding:0.5rem 1rem;color:#e6edf3;cursor:pointer;font-size:0.85rem">
                      Close
                    </button>
                  </div>
                </div>`;
            document.body.appendChild(modal);
            modal.addEventListener('click', e => { if (e.target === modal) modal.remove(); });
        })
        .catch(e => {
            if (btn) btn.textContent = 'Share';
            alert('Failed to create share link: ' + e.message);
        });
}

// ── Peer Comparison ─────────────────────────────────────────────────────────────────────────────────
async function loadPeers(companyId) {
    const container = document.getElementById('axiom-peers-table');
    if (!container) return;
    container.innerHTML = '<p style="color:var(--text-muted);font-size:13px;">Loading peers...</p>';
    try {
        const resp = await fetch(`/api/company/${companyId}/peers`);
        if (!resp.ok) { container.innerHTML = '<p style="color:#ef4444;">Failed to load peers.</p>'; return; }
        const data = await resp.json();
        const peers = data.peers || data || [];
        if (!peers.length) {
            container.innerHTML = '<p style="color:var(--text-muted);">No peers found via EDGAR SIC matching.</p>';
            return;
        }
        let html = '<table style="width:100%;border-collapse:collapse;font-size:13px;">';
        html += '<thead><tr style="border-bottom:2px solid var(--border-color);">';
        html += '<th style="text-align:left;padding:8px;color:var(--text-muted);">Ticker</th>';
        html += '<th style="text-align:left;padding:8px;color:var(--text-muted);">Company</th>';
        html += '<th style="text-align:left;padding:8px;color:var(--text-muted);">SIC</th>';
        html += '<th style="text-align:right;padding:8px;color:var(--text-muted);">Market Cap</th>';
        html += '</tr></thead><tbody>';
        peers.forEach(p => {
            html += '<tr style="border-bottom:1px solid var(--border-color);">';
            html += `<td style="padding:8px;font-weight:600;">${p.ticker || p.symbol || '—'}</td>`;
            html += `<td style="padding:8px;">${p.name || p.company_name || '—'}</td>`;
            html += `<td style="padding:8px;color:var(--text-muted);">${p.sic || '—'}</td>`;
            html += `<td style="padding:8px;text-align:right;">${p.market_cap ? '$' + _axiomFmt(p.market_cap) : '—'}</td>`;
            html += '</tr>';
        });
        html += '</tbody></table>';
        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = '<p style="color:#ef4444;">Error loading peers: ' + e.message + '</p>';
    }
}

// Patch showValuationResults to also load institutional score
(function() {
    const _orig = window.showValuationResults;
    if (typeof _orig === 'function') {
        window.showValuationResults = function(result) {
            _orig.call(this, result);
            const cid = result?.company_id || result?.id;
            if (cid) {
                window.currentValuationCompanyId = cid;
                // Load institutional score lazily
                setTimeout(() => loadInstitutionalScore(cid), 200);
                // Show institutional score from result if already present
                if (result?.institutional_score) {
                    const instData = result.institutional_score;
                    if (!instData.error) {
                        const container = document.getElementById('axiom-inst-score');
                        if (container) {
                            const grade = instData.quality_grade || '—';
                            const gradeColor = grade === 'A' ? '#3fb950' : grade === 'B' ? '#d29922' : grade === 'C' ? '#f0883e' : '#f85149';
                            const scoreNum = (instData.quality_score * 100).toFixed(0);
                            container.innerHTML = `
                                <span style="display:inline-flex;align-items:center;gap:0.5rem;font-size:0.82rem;background:var(--bg-tertiary);border:1px solid var(--border-primary);border-radius:4px;padding:0.3rem 0.6rem;flex-wrap:wrap">
                                  <span class="axiom-tip" data-tip="Company quality score based on profitability (ROE, ROIC), margins, cash flow conversion, and leverage. A = excellent, D = poor." style="color:var(--text-secondary);display:inline-flex;align-items:center;gap:0.35rem">
                                    Quality
                                    <span style="font-family:var(--font-mono);font-weight:700;color:${gradeColor}">${grade}</span>
                                    <span style="color:var(--text-tertiary)">${scoreNum}/100</span>
                                  </span>
                                  <span style="color:var(--border-secondary)">|</span>
                                  <span class="axiom-tip" data-tip="Valuation complexity: STRAIGHTFORWARD = stable, predictable business. COMPLEX/HIGHLY_COMPLEX = multiple segments, cyclicality, or turnaround situations." style="color:var(--text-secondary)">${instData.complexity || ''}</span>
                                </span>`;
                        }
                    }
                }
            }
        };
    }
})();


// ── Three-Pane Workspace ──────────────────────────────────────────────────────
function toggleLeftPane() {
    const pane = document.getElementById('workspace-left');
    if (pane) pane.classList.toggle('collapsed');
}

function toggleRightPane() {
    const pane = document.getElementById('workspace-right');
    if (pane) pane.classList.toggle('collapsed');
}

function renderSidebarCompanies(companies) {
    const list = document.getElementById('sidebar-company-list');
    if (!list) return;
    if (!companies || !companies.length) {
        list.innerHTML = '<p style="padding:16px;color:var(--text-muted);font-size:12px;">No companies yet.</p>';
        return;
    }
    list.innerHTML = companies.map(c => {
        const upside = c.upside_pct != null ? +c.upside_pct : null;
        const upsideClass = upside == null ? '' : upside >= 0 ? 'positive' : 'negative';
        const upsideStr = upside == null ? '—' : (upside >= 0 ? '+' : '') + upside.toFixed(1) + '%';
        return `<div class="sidebar-company-item" onclick="editCompany(${c.id})">
            <div class="sidebar-company-name">${c.name}</div>
            <div class="sidebar-company-meta">
                <span>${c.sector || ''}</span>
                <span class="sidebar-company-upside ${upsideClass}">${upsideStr}</span>
            </div>
        </div>`;
    }).join('');
}

function filterSidebar(query) {
    const items = document.querySelectorAll('#sidebar-company-list .sidebar-company-item');
    const q = query.toLowerCase();
    items.forEach(item => {
        const name = item.querySelector('.sidebar-company-name')?.textContent.toLowerCase() || '';
        item.style.display = name.includes(q) ? '' : 'none';
    });
}

function updateRightPortfolioStats(stats) {
    const el = document.getElementById('right-portfolio-stats');
    if (!el || !stats) return;
    const fmt = n => n != null ? (+n).toFixed(1) : '—';
    el.innerHTML = `
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">
            <div><div style="font-size:11px;color:var(--text-muted);">Total cos</div><div style="font-weight:700;">${stats.total_companies || 0}</div></div>
            <div><div style="font-size:11px;color:var(--text-muted);">Avg upside</div><div style="font-weight:700;color:${(stats.avg_upside||0)>=0?'#22c55e':'#ef4444'};">+${fmt(stats.avg_upside)}%</div></div>
            <div><div style="font-size:11px;color:var(--text-muted);">Buy signals</div><div style="font-weight:700;color:#22c55e;">${stats.buy_count || 0}</div></div>
            <div><div style="font-size:11px;color:var(--text-muted);">Sell signals</div><div style="font-weight:700;color:#ef4444;">${stats.sell_count || 0}</div></div>
        </div>`;
}

async function quickAddFromSidebar() {
    const input = document.getElementById('right-quick-ticker');
    const result = document.getElementById('right-quick-result');
    const ticker = input?.value?.trim().toUpperCase();
    if (!ticker) return;
    if (result) result.innerHTML = '<span style="color:var(--text-muted);">Adding...</span>';
    try {
        const resp = await fetch('/api/company/import-ticker', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ticker })
        });
        const data = await resp.json();
        if (resp.ok && !data.error) {
            if (result) result.innerHTML = '<span style="color:#22c55e;">Added! Refreshing...</span>';
            if (input) input.value = '';
            setTimeout(() => { if (typeof loadCompanies === 'function') loadCompanies(); }, 800);
        } else {
            if (result) result.innerHTML = `<span style="color:#ef4444;">${data.error || 'Failed'}</span>`;
        }
    } catch (e) {
        if (result) result.innerHTML = '<span style="color:#ef4444;">Error: ' + e.message + '</span>';
    }
}

// Hook into loadCompanies/loadDashboard to update sidebar
(function() {
    const _origLC = window.loadCompanies;
    if (typeof _origLC === 'function') {
        window.loadCompanies = async function() {
            const result = await _origLC.apply(this, arguments);
            if (window.allCompanies) renderSidebarCompanies(window.allCompanies);
            return result;
        };
    }
    const _origLD = window.loadDashboard;
    if (typeof _origLD === 'function') {
        window.loadDashboard = async function() {
            const result = await _origLD.apply(this, arguments);
            if (window.dashboardStats) updateRightPortfolioStats(window.dashboardStats);
            return result;
        };
    }
})();
