// DCF Detail Page — standalone JS
// All functions needed for /dcf/<company_id> full-page view

const companyId = parseInt(window.location.pathname.split('/').pop(), 10);
let currentCompanyId = companyId;
let dcfDetailsCache = null;
let dcfBaseInputs = null;

// ── Formatters ───────────────────────────────────────────────────────────────

function fmt(val) {
    if (val === null || val === undefined) return '—';
    if (Math.abs(val) >= 1e12) return '$' + (val / 1e12).toFixed(2) + 'T';
    if (Math.abs(val) >= 1e9)  return '$' + (val / 1e9).toFixed(2)  + 'B';
    if (Math.abs(val) >= 1e6)  return '$' + (val / 1e6).toFixed(2)  + 'M';
    return '$' + val.toFixed(2);
}

function pct(val) {
    return val !== null && val !== undefined ? (val * 100).toFixed(2) + '%' : '—';
}

// ── LocalStorage valuation ────────────────────────────────────────────────────

function getUserValuation(cid) {
    const store = JSON.parse(localStorage.getItem('userValuations') || '{}');
    return store[cid] || null;
}

function clearUserValuation(cid) {
    const store = JSON.parse(localStorage.getItem('userValuations') || '{}');
    delete store[cid];
    localStorage.setItem('userValuations', JSON.stringify(store));
}

function saveUserValuation() {
    if (!dcfBaseInputs || !currentCompanyId) return;
    const base = dcfBaseInputs;
    const wacc           = parseFloat(document.getElementById('sens-wacc-input')?.value      || base.wacc * 100) / 100;
    const termGrowth     = parseFloat(document.getElementById('sens-term-growth-input')?.value || base.terminal_growth * 100) / 100;
    const revenueGrowthY1 = parseFloat(document.getElementById('sens-revenue-growth-input')?.value || base.growth_y1 * 100) / 100;
    const ebitdaMargin   = parseFloat(document.getElementById('sens-margin-input')?.value    || base.ebitda_margin * 100) / 100;

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
        const yearDa     = currentRevenue * base.da_ratio;
        const yearEbit   = yearEbitda - yearDa;
        const yearNopat  = yearEbit * (1 - base.tax_rate);
        const yearCapex  = currentRevenue * base.capex_pct;
        const yearWc     = base.wc_change * (currentRevenue / base.revenue);
        const yearFcf    = yearNopat + yearDa - yearCapex - yearWc;
        const df         = 1 / Math.pow(1 + wacc, year);
        totalPvFcf += yearFcf * df;
        projectedFcf.push(yearFcf);
    }

    const terminalFcf    = projectedFcf[9] * (1 + termGrowth);
    const terminalValue  = terminalFcf / (wacc - termGrowth);
    const pvTerminal     = terminalValue / Math.pow(1 + wacc, 10);
    const enterpriseValue = totalPvFcf + pvTerminal;
    const equityValue    = enterpriseValue + base.cash - base.debt;
    const pricePerShare  = equityValue / base.shares;

    const store = JSON.parse(localStorage.getItem('userValuations') || '{}');
    store[currentCompanyId] = {
        equityValue, pricePerShare,
        wacc: wacc * 100,
        terminalGrowth: termGrowth * 100,
        revenueGrowthY1: revenueGrowthY1 * 100,
        ebitdaMargin: ebitdaMargin * 100,
        savedAt: new Date().toISOString()
    };
    localStorage.setItem('userValuations', JSON.stringify(store));

    const btn = event.target.closest('button');
    const origHtml = btn.innerHTML;
    btn.innerHTML = '✓ Saved!';
    btn.style.background = '#16a34a';

    const removeBtn  = document.getElementById('remove-valuation-btn');
    const indicator  = document.getElementById('user-valuation-indicator');
    if (removeBtn) removeBtn.style.display = 'block';
    if (indicator) {
        indicator.style.display = 'block';
        indicator.querySelector('strong').textContent = '$' + pricePerShare.toFixed(2);
    }

    setTimeout(() => {
        btn.innerHTML = 'Update Your Valuation';
        btn.style.background = 'linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%)';
    }, 1500);
}

function removeUserValuation() {
    if (!currentCompanyId) return;
    clearUserValuation(currentCompanyId);
    resetSensitivity();

    const removeBtn = document.getElementById('remove-valuation-btn');
    const indicator = document.getElementById('user-valuation-indicator');
    const saveBtn   = document.getElementById('save-valuation-btn');

    if (removeBtn)  removeBtn.style.display = 'none';
    if (indicator)  indicator.style.display = 'none';
    if (saveBtn)    saveBtn.innerHTML = 'Save Your Valuation';
}

// ── Sensitivity controls ──────────────────────────────────────────────────────

function syncSensInput(field) {
    const slider = document.getElementById(`sens-${field}`);
    const input  = document.getElementById(`sens-${field}-input`);
    if (slider && input) input.value = parseFloat(slider.value).toFixed(2);
    recalculateDCF();
}

function syncSensSlider(field) {
    const slider = document.getElementById(`sens-${field}`);
    const input  = document.getElementById(`sens-${field}-input`);
    if (slider && input) slider.value = parseFloat(input.value) || 0;
    recalculateDCF();
}

function resetSensitivity() {
    if (!dcfBaseInputs) return;
    const b = dcfBaseInputs;
    document.getElementById('sens-wacc').value             = b.wacc * 100;
    document.getElementById('sens-wacc-input').value       = (b.wacc * 100).toFixed(2);
    document.getElementById('sens-term-growth').value      = b.terminal_growth * 100;
    document.getElementById('sens-term-growth-input').value = (b.terminal_growth * 100).toFixed(2);
    document.getElementById('sens-revenue-growth').value   = b.growth_y1 * 100;
    document.getElementById('sens-revenue-growth-input').value = (b.growth_y1 * 100).toFixed(2);
    document.getElementById('sens-margin').value           = b.ebitda_margin * 100;
    document.getElementById('sens-margin-input').value     = (b.ebitda_margin * 100).toFixed(2);
    recalculateDCF();
}

function recalculateDCF() {
    if (!dcfBaseInputs) return;
    const base          = dcfBaseInputs;
    const wacc          = parseFloat(document.getElementById('sens-wacc-input')?.value      || base.wacc * 100) / 100;
    const termGrowth    = parseFloat(document.getElementById('sens-term-growth-input')?.value || base.terminal_growth * 100) / 100;
    const revenueGrowthY1 = parseFloat(document.getElementById('sens-revenue-growth-input')?.value || base.growth_y1 * 100) / 100;
    const ebitdaMargin  = parseFloat(document.getElementById('sens-margin-input')?.value    || base.ebitda_margin * 100) / 100;

    const growthRatio = base.growth_y1 > 0 ? revenueGrowthY1 / base.growth_y1 : 1;
    const g1 = revenueGrowthY1;
    const g2 = base.growth_y2 * growthRatio;
    const g3 = base.growth_y3 * growthRatio;
    const growthSchedule = [g1, g1, g2, g2, g3, g3, (g3 + termGrowth)/2, termGrowth + 0.01, termGrowth + 0.005, termGrowth];

    let currentRevenue = base.revenue;
    let totalPvFcf = 0;
    const projectedFcf = [];
    const newDetails = [];

    for (let year = 1; year <= 10; year++) {
        const growthRate = growthSchedule[year - 1];
        currentRevenue *= (1 + growthRate);
        const yearEbitda = currentRevenue * ebitdaMargin;
        const yearDa     = currentRevenue * base.da_ratio;
        const yearEbit   = yearEbitda - yearDa;
        const yearNopat  = yearEbit * (1 - base.tax_rate);
        const yearCapex  = currentRevenue * base.capex_pct;
        const yearWc     = base.wc_change * (currentRevenue / base.revenue);
        const yearFcf    = yearNopat + yearDa - yearCapex - yearWc;
        const df         = 1 / Math.pow(1 + wacc, year);
        const pvFcf      = yearFcf * df;
        totalPvFcf += pvFcf;
        projectedFcf.push(yearFcf);
        newDetails.push({ year, growth_rate: growthRate, revenue: currentRevenue, ebitda: yearEbitda, da: yearDa, ebit: yearEbit, nopat: yearNopat, capex: yearCapex, wc_change: yearWc, fcf: yearFcf, discount_factor: df, pv_fcf: pvFcf });
    }

    const terminalFcf    = projectedFcf[9] * (1 + termGrowth);
    const terminalValue  = terminalFcf / (wacc - termGrowth);
    const pvTerminal     = terminalValue / Math.pow(1 + wacc, 10);
    const enterpriseValue = totalPvFcf + pvTerminal;
    const equityValue    = enterpriseValue + base.cash - base.debt;
    const pricePerShare  = equityValue / base.shares;

    newDetails.forEach((d, i) => {
        const col = i + 1;
        const upd = (row, val, format) => {
            const cell = document.querySelector(`#dcf-table tr[data-row="${row}"] td:nth-child(${col + 1})`);
            if (cell) cell.textContent = format === 'pct' ? pct(val) : fmt(val);
        };
        upd('growth', d.growth_rate, 'pct');
        upd('revenue', d.revenue, 'dollar');
        upd('ebitda', d.ebitda, 'dollar');
        upd('da', d.da, 'dollar');
        upd('ebit', d.ebit, 'dollar');
        upd('nopat', d.nopat, 'dollar');
        upd('da2', d.da, 'dollar');
        upd('capex', d.capex, 'dollar');
        upd('wc', d.wc_change, 'dollar');
        upd('fcf', d.fcf, 'dollar');
        upd('df', d.discount_factor, 'pct');
        upd('pvfcf', d.pv_fcf, 'dollar');
    });

    document.getElementById('sens-total-pv-fcf').textContent    = fmt(totalPvFcf);
    document.getElementById('sens-terminal-value').textContent   = fmt(terminalValue);
    document.getElementById('sens-pv-terminal').textContent      = fmt(pvTerminal);

    const baseEquity = dcfDetailsCache?.calculated?.equity_value?.value || base.market_cap;
    const change = ((equityValue - baseEquity) / baseEquity) * 100;
    const changeColor = change >= 0 ? '#22c55e' : '#ef4444';

    document.getElementById('sens-equity-value').innerHTML =
        `<div style="font-size:1.4rem;font-weight:700;">${fmt(equityValue)}</div>
         <div style="font-size:0.85rem;color:${changeColor};">${change >= 0 ? '+' : ''}${change.toFixed(1)}% vs base</div>`;

    document.getElementById('sens-price-per-share').innerHTML =
        `<div style="font-size:1.4rem;font-weight:700;">$${pricePerShare.toFixed(2)}</div>
         <div style="font-size:0.85rem;color:var(--text-muted);">per share</div>`;
}

// ── Render ────────────────────────────────────────────────────────────────────

function renderDCFDetails(dcf) {
    const ticker  = dcf.ticker || '';
    const baseUrl = 'https://finance.yahoo.com/quote/' + ticker;
    const inputs      = dcf.inputs      || {};
    const assumptions = dcf.assumptions || {};

    const pageName = {
        '/key-statistics': 'Key Statistics',
        '/balance-sheet':  'Balance Sheet',
        '/financials':     'Income Statement',
        '/cash-flow':      'Cash Flow Statement',
        '/analysis':       'Analyst Estimates',
    };

    const valLink = (val, label, source, urlPath, note) => {
        const display = typeof val === 'number' ? (Math.abs(val) < 1 ? pct(val) : (Math.abs(val) > 1000 ? fmt(val) : val.toFixed(2))) : val;
        if (source === 'yahoo_finance' && ticker && urlPath !== undefined) {
            const page = pageName[urlPath] || '';
            const tipText = page ? `${label}||Yahoo Finance · ${page} ↗` : label;
            return `<a href="${baseUrl}${urlPath || ''}" target="_blank" rel="noopener" style="color:var(--accent-primary);text-decoration:underline;cursor:pointer;" title="${tipText}">${display}</a>`;
        }
        return `<span style="color:var(--text-primary);border-bottom:1px dotted var(--text-muted);cursor:help;" title="${note || label}">${display}</span>`;
    };

    if (dcf.model_type === 'alternative') {
        return `<div style="padding:40px;text-align:center;">
            <div style="font-size:1rem;color:var(--text-secondary);">${dcf.note || 'This company uses an alternative valuation model.'}</div>
            <div style="margin-top:10px;color:var(--text-muted);font-size:0.85rem;">${dcf.reason || ''}</div>
        </div>`;
    }

    // Assumptions
    let assumptionsHtml = '';
    if (assumptions && Object.keys(assumptions).length > 0) {
        assumptionsHtml = `
        <div style="padding:20px 24px;border-bottom:1px solid var(--border-color);">
            <div style="font-size:0.75rem;font-weight:700;color:var(--text-muted);margin-bottom:14px;text-transform:uppercase;letter-spacing:0.05em;">Key Assumptions</div>
            <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px;">
                ${Object.entries(assumptions).map(([key, a]) => `
                <div style="background:var(--bg-primary);border:1px solid var(--border-color);border-radius:8px;padding:14px;" title="${a.note || ''}">
                    <div style="font-size:0.75rem;color:var(--text-muted);margin-bottom:4px;">${a.label || key}</div>
                    <div style="font-size:1.05rem;font-weight:600;color:var(--text-primary);">${pct(a.value)}</div>
                    ${a.note ? `<div style="font-size:0.7rem;color:var(--text-muted);margin-top:6px;line-height:1.4;">${a.note}</div>` : ''}
                </div>`).join('')}
            </div>
        </div>`;
    }

    // Calculated values
    let calculatedHtml = '';
    if (dcf.calculated) {
        const calc = dcf.calculated;
        const tg   = assumptions.terminal_growth || {};
        const tip  = (val, label, note) => `<span style="color:var(--text-primary);border-bottom:1px dotted var(--text-muted);cursor:help;font-size:0.85rem;font-weight:500;" title="${note || label}">${typeof val === 'number' ? (Math.abs(val) < 1 ? pct(val) : val.toFixed(2)) : val}</span>`;
        const tipD = (val, label, note) => `<span style="color:var(--text-primary);border-bottom:1px dotted var(--text-muted);cursor:help;font-size:0.85rem;font-weight:500;" title="${note || label}">${fmt(val)}</span>`;
        const lnk  = (val, label, urlPath) => {
            if (!ticker) return tip(val, label, label);
            const page = pageName[urlPath] || '';
            const tipText = page ? `${label}||Yahoo Finance · ${page} ↗` : label;
            const display = typeof val === 'number' ? (Math.abs(val) < 1 ? pct(val) : (Math.abs(val) > 1000 ? fmt(val) : val.toFixed(2))) : val;
            return `<a href="${baseUrl}${urlPath||''}" target="_blank" rel="noopener" style="color:var(--accent-primary);text-decoration:underline;font-size:0.85rem;font-weight:500;" title="${tipText}">${display}</a>`;
        };

        const coe  = calc.cost_of_equity?.components   || {};
        const cod  = calc.cost_of_debt?.components      || {};
        const wacc = calc.wacc?.components              || {};
        const ev   = calc.enterprise_value?.components  || {};
        const eqv  = calc.equity_value?.components      || {};

        const rows = [
            { key: 'cost_of_equity',   label: 'Cost of Equity',   formula: 'Rf + β × MRP',                   components: `${tip(coe.rf,'Risk-Free Rate','10-Year Treasury yield')} + ${lnk(coe.beta,'Beta (5Y Monthly)','/key-statistics')} × ${tip(coe.mrp,'Market Risk Premium','Historical avg excess return')}` },
            { key: 'cost_of_debt',     label: 'Cost of Debt',     formula: 'Rf + Credit Spread',             components: `${tip(cod.rf,'Risk-Free Rate','10-Year Treasury yield')} + ${tip(cod.credit_spread,'Credit Spread','Damodaran synthetic rating')}` },
            { key: 'wacc',             label: 'WACC',             formula: '(E/V × Re) + (D/V × Rd × (1-T))', components: `(${tip(wacc.weight_equity,'Equity Weight','Market Cap / (Market Cap + Net Debt)')} × ${tip(wacc.cost_of_equity,'Cost of Equity','CAPM: Rf + β × MRP')}) + (${tip(wacc.weight_debt,'Debt Weight','Net Debt / (Market Cap + Net Debt)')} × ${tip(wacc.cost_of_debt,'Cost of Debt','Rf + Credit Spread')} × (1 - ${tip(wacc.tax_rate,'Tax Rate','Effective tax rate')}))` },
            { key: 'terminal_value',   label: 'Terminal Value',   formula: 'FCF₁₀ × (1+g) / (WACC - g)',    components: `Final year FCF × (1 + ${tip(tg.value,'Terminal Growth',tg.note||'Long-term GDP growth proxy')}) / (WACC - ${tip(tg.value,'Terminal Growth',tg.note||'Long-term GDP growth proxy')})` },
            { key: 'enterprise_value', label: 'Enterprise Value', formula: 'PV of FCF + PV of Terminal Value', components: `${tipD(ev.pv_fcf,'PV of FCF','Sum of discounted 10-year FCFs')} + ${tipD(ev.pv_terminal,'PV of Terminal Value','Terminal value discounted to present')}` },
            { key: 'equity_value',     label: 'Equity Value',     formula: 'EV + Cash - Debt',               components: `${tipD(eqv.enterprise_value,'Enterprise Value','PV of FCF + PV of Terminal Value')} + ${lnk(eqv.cash,'Cash & Equivalents','/balance-sheet')} - ${lnk(eqv.debt,'Total Debt','/balance-sheet')}` },
        ];

        calculatedHtml = `
        <div style="padding:20px 24px;border-bottom:1px solid var(--border-color);">
            <div style="font-size:0.75rem;font-weight:700;color:var(--text-muted);margin-bottom:14px;text-transform:uppercase;letter-spacing:0.05em;">Calculated Values</div>
            <div style="display:flex;flex-direction:column;gap:10px;">
                ${rows.map(r => {
                    const c = dcf.calculated[r.key] || {};
                    return `<div style="background:var(--bg-primary);border:1px solid var(--border-color);border-radius:8px;padding:16px;">
                        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                            <span style="font-size:0.95rem;font-weight:600;color:var(--text-primary);cursor:help;border-bottom:1px dotted var(--text-muted);" title="${r.formula}">${r.label}</span>
                            <span style="font-size:1.25rem;font-weight:700;color:var(--accent-primary);">${c.result || '—'}</span>
                        </div>
                        <div style="font-size:0.85rem;color:var(--text-secondary);line-height:1.6;">${r.components}</div>
                    </div>`;
                }).join('')}
            </div>
        </div>`;
    }

    // Sensitivity + projection
    let projectionHtml = '';
    if (dcf.projection && dcf.projection.details && dcf.projection.details.length > 0) {
        const details = dcf.projection.details;
        const years   = details.map(d => d.year);
        const base    = dcf.base_inputs || {};

        const row = (label, rowId, key, format, style = '', tooltip = '', urlPath = null) => {
            const cells = details.map(d => {
                const val = d[key];
                const display = format === 'pct' ? pct(val) : fmt(val);
                return `<td style="padding:6px 8px;text-align:right;font-size:0.8rem;">${display}</td>`;
            }).join('');
            const page = pageName[urlPath] || '';
            const labelHtml = urlPath && ticker
                ? `<a href="${baseUrl}${urlPath}" target="_blank" rel="noopener" style="color:var(--accent-primary);text-decoration:underline;" title="${tooltip}${page ? '||Yahoo Finance · ' + page + ' ↗' : ''}">${label} ↗</a>`
                : `<span title="${tooltip}">${label}</span>`;
            return `<tr data-row="${rowId}" style="${style}"><td style="padding:6px 12px;font-size:0.8rem;white-space:nowrap;${style}">${labelHtml}</td>${cells}</tr>`;
        };

        const savedVal = getUserValuation(currentCompanyId);
        const hasSaved = !!savedVal;

        const saveButtonHtml = base ? `
        <div style="padding:24px;border-top:1px solid var(--border-color);">
            <div id="user-valuation-indicator" style="display:${hasSaved ? 'block' : 'none'};margin-bottom:12px;padding:10px 14px;background:rgba(139,92,246,0.1);border:1px solid rgba(139,92,246,0.3);border-radius:6px;font-size:0.85rem;color:var(--text-secondary);">
                Your custom valuation: <strong>$${hasSaved ? savedVal.pricePerShare.toFixed(2) : '—'}</strong>/share
                <span style="margin-left:8px;color:var(--text-muted);">Saved ${hasSaved ? new Date(savedVal.savedAt).toLocaleDateString() : ''}</span>
            </div>
            <div style="display:flex;gap:10px;">
                <button id="save-valuation-btn" onclick="saveUserValuation()" style="flex:1;padding:14px 24px;background:linear-gradient(135deg,#8b5cf6 0%,#7c3aed 100%);color:white;border:none;border-radius:8px;cursor:pointer;font-weight:600;font-size:0.95rem;">
                    ${hasSaved ? 'Update Your Valuation' : 'Save Your Valuation'}
                </button>
                <button id="remove-valuation-btn" onclick="removeUserValuation()" style="display:${hasSaved ? 'block' : 'none'};padding:14px 18px;background:transparent;color:#ef4444;border:1px solid #ef4444;border-radius:8px;cursor:pointer;font-weight:600;font-size:0.85rem;">
                    Remove
                </button>
            </div>
        </div>` : '';

        projectionHtml = `
        <div style="padding:20px 24px;border-bottom:1px solid var(--border-color);">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px;">
                <span style="font-size:0.75rem;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.05em;">Sensitivity Analysis</span>
                <button onclick="resetSensitivity()" style="padding:5px 14px;font-size:0.75rem;background:var(--bg-secondary);border:1px solid var(--border-color);border-radius:4px;cursor:pointer;font-weight:600;color:var(--text-secondary);">↺ Reset to AXIOM</button>
            </div>
            <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:16px;background:var(--bg-primary);padding:16px;border-radius:8px;border:1px solid var(--border-color);">
                <div>
                    <label style="font-size:0.7rem;color:var(--text-muted);display:block;margin-bottom:6px;">WACC</label>
                    <input type="range" id="sens-wacc" min="5" max="20" step="0.01" value="${(base.wacc||0.10)*100}" oninput="syncSensInput('wacc')" style="width:100%;">
                    <div style="display:flex;align-items:center;justify-content:center;gap:2px;margin-top:6px;">
                        <input type="number" id="sens-wacc-input" step="0.01" value="${((base.wacc||0.10)*100).toFixed(2)}" oninput="syncSensSlider('wacc')" style="width:55px;text-align:right;font-size:0.9rem;font-weight:600;padding:4px 6px;border:1px solid var(--border-color);border-radius:4px;background:var(--bg-secondary);color:var(--text-primary);">
                        <span style="font-size:0.9rem;font-weight:600;">%</span>
                    </div>
                </div>
                <div>
                    <label style="font-size:0.7rem;color:var(--text-muted);display:block;margin-bottom:6px;">Terminal Growth</label>
                    <input type="range" id="sens-term-growth" min="0" max="5" step="0.01" value="${(base.terminal_growth||0.025)*100}" oninput="syncSensInput('term-growth')" style="width:100%;">
                    <div style="display:flex;align-items:center;justify-content:center;gap:2px;margin-top:6px;">
                        <input type="number" id="sens-term-growth-input" step="0.01" value="${((base.terminal_growth||0.025)*100).toFixed(2)}" oninput="syncSensSlider('term-growth')" style="width:55px;text-align:right;font-size:0.9rem;font-weight:600;padding:4px 6px;border:1px solid var(--border-color);border-radius:4px;background:var(--bg-secondary);color:var(--text-primary);">
                        <span style="font-size:0.9rem;font-weight:600;">%</span>
                    </div>
                </div>
                <div>
                    <label style="font-size:0.7rem;color:var(--text-muted);display:block;margin-bottom:6px;">Revenue Growth (Y1)</label>
                    <input type="range" id="sens-revenue-growth" min="0" max="50" step="0.01" value="${(base.growth_y1||0.10)*100}" oninput="syncSensInput('revenue-growth')" style="width:100%;">
                    <div style="display:flex;align-items:center;justify-content:center;gap:2px;margin-top:6px;">
                        <input type="number" id="sens-revenue-growth-input" step="0.01" value="${((base.growth_y1||0.10)*100).toFixed(2)}" oninput="syncSensSlider('revenue-growth')" style="width:55px;text-align:right;font-size:0.9rem;font-weight:600;padding:4px 6px;border:1px solid var(--border-color);border-radius:4px;background:var(--bg-secondary);color:var(--text-primary);">
                        <span style="font-size:0.9rem;font-weight:600;">%</span>
                    </div>
                </div>
                <div>
                    <label style="font-size:0.7rem;color:var(--text-muted);display:block;margin-bottom:6px;">EBITDA Margin</label>
                    <input type="range" id="sens-margin" min="5" max="60" step="0.01" value="${(base.ebitda_margin||0.20)*100}" oninput="syncSensInput('margin')" style="width:100%;">
                    <div style="display:flex;align-items:center;justify-content:center;gap:2px;margin-top:6px;">
                        <input type="number" id="sens-margin-input" step="0.01" value="${((base.ebitda_margin||0.20)*100).toFixed(2)}" oninput="syncSensSlider('margin')" style="width:55px;text-align:right;font-size:0.9rem;font-weight:600;padding:4px 6px;border:1px solid var(--border-color);border-radius:4px;background:var(--bg-secondary);color:var(--text-primary);">
                        <span style="font-size:0.9rem;font-weight:600;">%</span>
                    </div>
                </div>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:12px;">
                <div id="sens-equity-value" style="background:linear-gradient(135deg,#1e3a5f 0%,#2d5a87 100%);color:white;padding:16px;border-radius:8px;text-align:center;">
                    <div style="font-size:1.4rem;font-weight:700;">${fmt(dcf.calculated?.equity_value?.value||0)}</div>
                    <div style="font-size:0.85rem;opacity:0.8;">Equity Value</div>
                </div>
                <div id="sens-price-per-share" style="background:linear-gradient(135deg,#1e3a5f 0%,#2d5a87 100%);color:white;padding:16px;border-radius:8px;text-align:center;">
                    <div style="font-size:1.4rem;font-weight:700;">$${(dcf.calculated?.price_per_share?.value||0).toFixed(2)}</div>
                    <div style="font-size:0.85rem;opacity:0.8;">per share</div>
                </div>
            </div>
        </div>
        <div style="padding:20px 24px;">
            <div style="font-size:0.75rem;font-weight:700;color:var(--text-muted);margin-bottom:14px;text-transform:uppercase;letter-spacing:0.05em;">10-Year Cash Flow Projection</div>
            <div style="overflow-x:auto;border:1px solid var(--border-color);border-radius:8px;">
                <table id="dcf-table" style="width:100%;border-collapse:collapse;">
                    <thead>
                        <tr style="background:linear-gradient(135deg,#1e3a5f 0%,#2d5a87 100%);">
                            <th style="padding:10px 12px;text-align:left;color:white;font-size:0.8rem;font-weight:600;">Metric</th>
                            ${years.map(y => `<th style="padding:10px 8px;text-align:right;color:white;font-size:0.8rem;font-weight:600;">Y${y}</th>`).join('')}
                        </tr>
                    </thead>
                    <tbody style="background:var(--bg-primary);">
                        ${row('Growth Rate',     'growth', 'growth_rate', 'pct',    'color:var(--text-muted);font-style:italic;',                              'Annual revenue growth rate',              '/analysis')}
                        ${row('Revenue',         'revenue','revenue',    'dollar',  'font-weight:600;border-top:1px solid var(--border-color);',               'Projected revenue',                       '/financials')}
                        ${row('EBITDA',          'ebitda', 'ebitda',     'dollar',  '',                                                                        'EBITDA margin applied to revenue',         '/financials')}
                        ${row('(-) D&A',         'da',     'da',         'dollar',  'color:var(--text-muted);',                                                'Depreciation & Amortization',             '/cash-flow')}
                        ${row('= EBIT',          'ebit',   'ebit',       'dollar',  'font-weight:500;border-top:1px solid var(--border-color);',               'EBITDA minus D&A')}
                        ${row('= NOPAT',         'nopat',  'nopat',      'dollar',  'font-weight:500;',                                                        'EBIT × (1 - Tax Rate)',                   '/financials')}
                        ${row('(+) D&A',         'da2',    'da',         'dollar',  'color:#22c55e;',                                                          'Add back non-cash depreciation',          '/cash-flow')}
                        ${row('(-) CapEx',       'capex',  'capex',      'dollar',  'color:#ef4444;',                                                          'Capital expenditures',                    '/cash-flow')}
                        ${row('(-) ΔWC',         'wc',     'wc_change',  'dollar',  'color:#ef4444;',                                                          'Working capital change',                  '/balance-sheet')}
                        ${row('= Free Cash Flow','fcf',    'fcf',        'dollar',  'font-weight:700;background:var(--bg-secondary);border-top:2px solid var(--border-color);', 'NOPAT + D&A - CapEx - ΔWC')}
                        ${row('Discount Factor', 'df',     'discount_factor','pct', 'color:var(--text-muted);font-style:italic;border-top:1px solid var(--border-color);', '1 / (1 + WACC)^year')}
                        ${row('PV of FCF',       'pvfcf',  'pv_fcf',     'dollar',  'font-weight:600;color:var(--accent-primary);',                            'FCF × Discount Factor')}
                    </tbody>
                </table>
            </div>
            <div style="margin-top:16px;display:grid;grid-template-columns:repeat(3,1fr);gap:12px;">
                <div style="background:var(--bg-primary);border:1px solid var(--border-color);border-radius:8px;padding:14px;">
                    <div style="font-size:0.7rem;color:var(--text-muted);margin-bottom:4px;">Total PV of FCF</div>
                    <div id="sens-total-pv-fcf" style="font-size:1.1rem;font-weight:700;color:var(--text-primary);">${fmt(dcf.projection.total_pv_fcf)}</div>
                </div>
                <div style="background:var(--bg-primary);border:1px solid var(--border-color);border-radius:8px;padding:14px;">
                    <div style="font-size:0.7rem;color:var(--text-muted);margin-bottom:4px;">Terminal Value</div>
                    <div id="sens-terminal-value" style="font-size:1.1rem;font-weight:700;color:var(--text-primary);">${fmt(dcf.projection.terminal_value)}</div>
                </div>
                <div style="background:var(--bg-primary);border:1px solid var(--border-color);border-radius:8px;padding:14px;">
                    <div style="font-size:0.7rem;color:var(--text-muted);margin-bottom:4px;">PV of Terminal Value</div>
                    <div id="sens-pv-terminal" style="font-size:1.1rem;font-weight:700;color:var(--accent-primary);">${fmt(dcf.projection.pv_terminal_value)}</div>
                </div>
            </div>
        </div>
        ${saveButtonHtml}`;
    }

    return `<div style="background:var(--bg-secondary);">${assumptionsHtml}${calculatedHtml}${projectionHtml}</div>`;
}

// ── Tooltip ───────────────────────────────────────────────────────────────────

function initTooltips() {
    const tip     = document.getElementById('dcf-tip');
    const content = document.getElementById('dcf-page-content');
    if (!tip || !content) return;

    let activeEl = null;

    function showTip(el) {
        if (activeEl === el) return;
        hideTip();
        activeEl = el;
        let text = el.hasAttribute('title') ? el.getAttribute('title') : el.dataset.savedTitle;
        if (!text) return;
        if (el.hasAttribute('title')) {
            el.dataset.savedTitle = text;
            el.removeAttribute('title');
        }
        // Split on '||' — first part is label, second is source line
        const parts = text.split('||');
        tip.innerHTML = parts[0]
            + (parts[1] ? `<span class="tip-source">${parts[1]}</span>` : '');
        tip.classList.add('visible');
    }

    function hideTip() {
        if (activeEl) {
            if (activeEl.dataset.savedTitle) {
                activeEl.setAttribute('title', activeEl.dataset.savedTitle);
                delete activeEl.dataset.savedTitle;
            }
            activeEl = null;
        }
        tip.classList.remove('visible');
    }

    content.addEventListener('mouseover', e => {
        const el = e.target.closest('[title],[data-saved-title]');
        if (el) showTip(el);
        else if (!activeEl || !activeEl.contains(e.target)) hideTip();
    });

    document.addEventListener('mousemove', e => {
        if (!tip.classList.contains('visible')) return;
        const x = e.clientX + 14;
        const y = e.clientY + 18;
        tip.style.left = Math.min(x, window.innerWidth  - tip.offsetWidth  - 14) + 'px';
        tip.style.top  = (y + tip.offsetHeight > window.innerHeight
            ? e.clientY - tip.offsetHeight - 8
            : y) + 'px';
    });

    content.addEventListener('mouseleave', hideTip);
}

// ── Page init ─────────────────────────────────────────────────────────────────

function applyTheme() {
    const saved = localStorage.getItem('theme') || 'light';
    document.documentElement.setAttribute('data-theme', saved);
}

function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('theme', next);
    document.getElementById('theme-btn').textContent = next === 'dark' ? '☀ Light' : '☾ Dark';
}

async function init() {
    applyTheme();
    document.getElementById('theme-btn').textContent =
        localStorage.getItem('theme') === 'dark' ? '☀ Light' : '☾ Dark';

    const content = document.getElementById('dcf-page-content');
    content.innerHTML = '<div style="padding:60px;text-align:center;color:var(--text-muted);font-size:1rem;">Loading DCF breakdown…</div>';

    try {
        const res  = await fetch(`/api/valuation/${companyId}/details`);
        const data = await res.json();

        // Update header
        if (data.company_name) {
            document.title = `${data.company_name} — DCF | AXIOM`;
            document.getElementById('hdr-company').textContent = data.company_name;
        }
        if (data.ticker) {
            document.getElementById('hdr-ticker').textContent = data.ticker;
        }
        if (data.sector) {
            document.getElementById('hdr-sector').textContent = data.sector;
        }

        // Summary bar
        const s = data.summary || {};
        const rec = (s.recommendation || '').toUpperCase();
        const upside = s.upside_pct;
        const upsideStr = upside != null ? ((upside >= 0 ? '+' : '') + upside.toFixed(1) + '%') : '—';
        const upsideColor = upside != null ? (upside >= 0 ? '#10b981' : '#ef4444') : 'var(--text-muted)';
        const recColors = { BUY: '#10b981', 'STRONG BUY': '#059669', HOLD: '#f59e0b', SELL: '#ef4444', 'STRONG SELL': '#dc2626' };
        const recColor = recColors[rec] || 'var(--text-muted)';

        document.getElementById('hdr-price').textContent   = s.current_price  != null ? '$' + s.current_price.toFixed(2)  : '—';
        document.getElementById('hdr-fv').textContent      = s.fair_value      != null ? '$' + s.fair_value.toFixed(2)     : '—';
        document.getElementById('hdr-upside').textContent  = upsideStr;
        document.getElementById('hdr-upside').style.color  = upsideColor;
        document.getElementById('hdr-rec').textContent     = rec || '—';
        document.getElementById('hdr-rec').style.background = recColor;

        if (data.dcf_details) {
            dcfDetailsCache = data.dcf_details;
            dcfBaseInputs   = data.dcf_details.base_inputs || null;
            content.innerHTML = renderDCFDetails(data.dcf_details);
            initTooltips();
        } else {
            content.innerHTML = '<div style="padding:60px;text-align:center;color:var(--text-muted);">DCF details not available for this company.</div>';
        }
    } catch (err) {
        content.innerHTML = `<div style="padding:60px;text-align:center;color:#ef4444;">Failed to load DCF data: ${err.message}</div>`;
    }
}

document.addEventListener('DOMContentLoaded', init);
