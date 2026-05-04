// EV/EBITDA Detail Page — standalone JS

const companyId = parseInt(window.location.pathname.split('/').pop(), 10);
let currentCompanyId = companyId;
let evBaseInputs = null;
let evDetailsCache = null;

// ── Formatters ────────────────────────────────────────────────────────────────

function fmt(val) {
    if (val === null || val === undefined) return '—';
    if (Math.abs(val) >= 1e12) return '$' + (val / 1e12).toFixed(2) + 'T';
    if (Math.abs(val) >= 1e9)  return '$' + (val / 1e9).toFixed(2)  + 'B';
    if (Math.abs(val) >= 1e6)  return '$' + (val / 1e6).toFixed(1)  + 'M';
    return '$' + val.toLocaleString();
}

// ── LocalStorage valuation ────────────────────────────────────────────────────

function getUserValuation(cid) {
    return JSON.parse(localStorage.getItem('userEVEBITDAValuations') || '{}')[cid] || null;
}

function saveUserValuation() {
    if (!evBaseInputs || !currentCompanyId) return;
    const base     = evBaseInputs;
    const multiple = parseFloat(document.getElementById('ev-sens-multiple-input')?.value || base.ev_ebitda_multiple);
    const impliedEV     = base.ebitda * multiple;
    const impliedEquity = impliedEV + base.cash - base.debt;
    const pricePerShare = impliedEquity / base.shares;

    const store = JSON.parse(localStorage.getItem('userEVEBITDAValuations') || '{}');
    store[currentCompanyId] = { impliedEquity, pricePerShare, evEbitdaMultiple: multiple, savedAt: new Date().toISOString() };
    localStorage.setItem('userEVEBITDAValuations', JSON.stringify(store));

    const btn = event.target.closest('button');
    btn.innerHTML = '✓ Saved!';
    btn.style.background = '#16a34a';

    const removeBtn  = document.getElementById('ev-remove-valuation-btn');
    const indicator  = document.getElementById('ev-user-valuation-indicator');
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
    const store = JSON.parse(localStorage.getItem('userEVEBITDAValuations') || '{}');
    delete store[currentCompanyId];
    localStorage.setItem('userEVEBITDAValuations', JSON.stringify(store));
    resetSensitivity();
    document.getElementById('ev-remove-valuation-btn').style.display  = 'none';
    document.getElementById('ev-user-valuation-indicator').style.display = 'none';
    document.getElementById('ev-save-valuation-btn').innerHTML = 'Save Your Valuation';
}

// ── Sensitivity controls ──────────────────────────────────────────────────────

function syncSensInput(field) {
    const slider = document.getElementById(`ev-sens-${field}`);
    const input  = document.getElementById(`ev-sens-${field}-input`);
    if (slider && input) input.value = parseFloat(slider.value).toFixed(1);
    recalculate();
}

function syncSensSlider(field) {
    const slider = document.getElementById(`ev-sens-${field}`);
    const input  = document.getElementById(`ev-sens-${field}-input`);
    if (slider && input) slider.value = parseFloat(input.value) || 0;
    recalculate();
}

function resetSensitivity() {
    if (!evBaseInputs) return;
    const b = evBaseInputs;
    document.getElementById('ev-sens-multiple').value       = b.ev_ebitda_multiple;
    document.getElementById('ev-sens-multiple-input').value = b.ev_ebitda_multiple.toFixed(1);
    recalculate();
}

function recalculate() {
    if (!evBaseInputs) return;
    const base     = evBaseInputs;
    const multiple = parseFloat(document.getElementById('ev-sens-multiple-input')?.value || base.ev_ebitda_multiple);
    const impliedEV     = base.ebitda * multiple;
    const impliedEquity = impliedEV + base.cash - base.debt;
    const pricePerShare = impliedEquity / base.shares;

    const axiomMultiple = parseFloat(base.ev_ebitda_multiple.toFixed(1));
    const axiomPrice = (base.ebitda * axiomMultiple + base.cash - base.debt) / base.shares;
    const diff = axiomPrice !== 0 ? ((pricePerShare - axiomPrice) / axiomPrice) * 100 : 0;

    const resultDiv = document.getElementById('ev-sens-result');
    const diffDiv   = document.getElementById('ev-sens-diff');
    if (resultDiv) resultDiv.querySelector('div').textContent = '$' + pricePerShare.toFixed(2);
    if (diffDiv) {
        diffDiv.textContent = 'vs AXIOM: ' + (diff >= 0 ? '+' : '') + diff.toFixed(1) + '%';
        diffDiv.style.color = diff >= 0 ? '#22c55e' : '#ef4444';
    }
}

// ── Render ────────────────────────────────────────────────────────────────────

function renderEVEBITDADetails(ev) {
    const ticker  = ev.ticker || '';
    const baseUrl = 'https://finance.yahoo.com/quote/' + ticker;
    const inputs      = ev.inputs      || {};
    const assumptions = ev.assumptions || {};
    const calculated  = ev.calculated  || {};
    const base        = ev.base_inputs || {};

    const savedVal = getUserValuation(currentCompanyId);
    const hasSaved = !!savedVal;

    const evMultipleNote    = assumptions.ev_ebitda_multiple?.note || `Based on ${base.sector || 'industry'} sector`;
    const evMultipleTooltip = `EV/EBITDA Multiple: ${assumptions.ev_ebitda_multiple?.value?.toFixed(1)}x\n\n${evMultipleNote}\n\nThis multiple shows what acquirers typically pay relative to cash flow generation. Capital-structure neutral — ideal for comparing companies with different debt levels.`;

    const assumptionsHtml = `
    <div style="padding:24px;border-bottom:1px solid var(--border-color);">
        <div style="font-size:0.75rem;font-weight:700;color:var(--text-muted);margin-bottom:16px;text-transform:uppercase;letter-spacing:0.05em;">Key Assumption</div>
        <div style="background:var(--bg-primary);border:1px solid var(--border-color);border-radius:8px;padding:20px;display:flex;align-items:center;gap:20px;">
            <div style="flex:1;">
                <div style="font-size:0.8rem;color:var(--text-muted);margin-bottom:6px;">EV/EBITDA Multiple</div>
                <div style="font-size:1.8rem;font-weight:700;color:var(--text-primary);">${assumptions.ev_ebitda_multiple?.value?.toFixed(1)}x</div>
            </div>
            <div style="flex:2;padding-left:20px;border-left:1px solid var(--border-color);">
                <div style="font-size:0.85rem;color:var(--text-secondary);line-height:1.5;">
                    ${evMultipleNote}. This multiple reflects what acquirers typically pay relative to operating cash flow — capital-structure neutral, ideal for comparing companies with different debt levels.
                </div>
            </div>
        </div>
    </div>`;

    const calculationHtml = `
    <div style="padding:24px;border-bottom:1px solid var(--border-color);">
        <div style="font-size:0.75rem;font-weight:700;color:var(--text-muted);margin-bottom:20px;text-transform:uppercase;letter-spacing:0.05em;">Valuation Calculation</div>
        <div style="background:var(--bg-primary);border:1px solid var(--border-color);border-radius:8px;padding:32px;">
            <div style="display:flex;align-items:center;justify-content:center;gap:20px;flex-wrap:wrap;font-size:1.5rem;">
                <a href="${baseUrl}/financials" target="_blank" rel="noopener"
                   title="EBITDA (TTM)\nEarnings Before Interest, Taxes, Depreciation & Amortization\nYahoo Finance · Income Statement ↗"
                   style="font-weight:700;color:var(--accent-primary);text-decoration:none;border-bottom:2px dotted var(--accent-primary);padding-bottom:2px;">${fmt(inputs.ebitda?.value)}</a>
                <span style="color:var(--text-muted);font-size:1.6rem;">×</span>
                <span title="${evMultipleTooltip}"
                      style="font-weight:700;color:var(--text-primary);cursor:help;border-bottom:2px dotted var(--text-muted);padding-bottom:2px;">${assumptions.ev_ebitda_multiple?.value?.toFixed(1)}x</span>
                <span style="color:var(--text-muted);font-size:1.6rem;">=</span>
                <span title="Implied Enterprise Value\nComputed from EBITDA × Multiple"
                      style="font-weight:700;color:var(--text-primary);cursor:help;border-bottom:2px dotted var(--text-muted);padding-bottom:2px;">${fmt(calculated.implied_ev?.value)}</span>
            </div>
            <div style="margin-top:24px;padding-top:24px;border-top:1px solid var(--border-color);display:flex;align-items:center;justify-content:center;gap:20px;flex-wrap:wrap;font-size:1.5rem;">
                <span title="Enterprise Value from above"
                      style="font-weight:700;color:var(--text-primary);cursor:help;border-bottom:2px dotted var(--text-muted);padding-bottom:2px;">${fmt(calculated.implied_ev?.value)}</span>
                <span style="color:var(--text-muted);font-size:1.6rem;">+</span>
                <a href="${baseUrl}/balance-sheet" target="_blank" rel="noopener"
                   title="Cash & Equivalents\nAdded because equity holders get this cash\nYahoo Finance · Balance Sheet ↗"
                   style="font-weight:700;color:var(--accent-primary);text-decoration:none;border-bottom:2px dotted var(--accent-primary);padding-bottom:2px;">${fmt(inputs.cash?.value)}</a>
                <span style="color:var(--text-muted);font-size:1.6rem;">−</span>
                <a href="${baseUrl}/balance-sheet" target="_blank" rel="noopener"
                   title="Total Debt\nSubtracted because debt holders have first claim\nYahoo Finance · Balance Sheet ↗"
                   style="font-weight:700;color:var(--accent-primary);text-decoration:none;border-bottom:2px dotted var(--accent-primary);padding-bottom:2px;">${fmt(inputs.debt?.value)}</a>
                <span style="color:var(--text-muted);font-size:1.6rem;">=</span>
                <span title="Implied Equity Value\nWhat shareholders' stake is worth"
                      style="font-weight:700;color:var(--text-primary);cursor:help;border-bottom:2px dotted var(--text-muted);padding-bottom:2px;">${fmt(calculated.implied_equity?.value)}</span>
            </div>
            <div style="text-align:center;margin-top:16px;font-size:0.75rem;color:var(--text-muted);">
                Click underlined values to verify on Yahoo Finance
            </div>
        </div>
        <div style="margin-top:20px;display:grid;grid-template-columns:1fr 1fr;gap:20px;">
            <div style="background:linear-gradient(135deg,#1e3a5f 0%,#2d5a87 100%);color:white;padding:24px;border-radius:8px;text-align:center;">
                <div style="font-size:1.7rem;font-weight:700;">${fmt(calculated.implied_equity?.value)}</div>
                <div style="font-size:0.85rem;opacity:0.85;margin-top:4px;">Implied Equity Value</div>
            </div>
            <div style="background:linear-gradient(135deg,#1e3a5f 0%,#2d5a87 100%);color:white;padding:24px;border-radius:8px;text-align:center;">
                <div style="font-size:1.7rem;font-weight:700;">$${calculated.price_per_share?.value?.toFixed(2) || '—'}</div>
                <div style="font-size:0.85rem;opacity:0.85;margin-top:4px;">Fair Value per Share</div>
            </div>
        </div>
    </div>`;

    const sensitivityHtml = base.ebitda ? `
    <div style="padding:24px;border-bottom:1px solid var(--border-color);">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;">
            <div style="font-size:0.75rem;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.05em;">Sensitivity Analysis</div>
            <button onclick="resetSensitivity()" style="padding:5px 14px;font-size:0.75rem;background:var(--bg-secondary);border:1px solid var(--border-color);border-radius:4px;cursor:pointer;font-weight:600;color:var(--text-secondary);">↺ Reset to AXIOM</button>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:32px;align-items:center;">
            <div style="padding:20px;background:var(--bg-primary);border:1px solid var(--border-color);border-radius:8px;">
                <label style="font-size:0.8rem;color:var(--text-muted);display:block;margin-bottom:12px;">EV/EBITDA Multiple</label>
                <input type="range" id="ev-sens-multiple" min="5" max="30" step="0.1"
                       value="${base.ev_ebitda_multiple || 15}"
                       oninput="syncSensInput('multiple')" style="width:100%;">
                <div style="display:flex;align-items:center;justify-content:center;gap:6px;margin-top:12px;">
                    <input type="number" id="ev-sens-multiple-input" step="0.1"
                           value="${(base.ev_ebitda_multiple || 15).toFixed(1)}"
                           oninput="syncSensSlider('multiple')"
                           style="width:70px;text-align:right;font-size:1.1rem;font-weight:600;padding:8px 10px;border:1px solid var(--border-color);border-radius:4px;background:var(--bg-secondary);color:var(--text-primary);">
                    <span style="font-size:1.1rem;font-weight:600;">x</span>
                </div>
            </div>
            <div id="ev-sens-result" style="background:linear-gradient(135deg,#1e3a5f 0%,#2d5a87 100%);color:white;padding:28px;border-radius:8px;text-align:center;">
                <div style="font-size:1.6rem;font-weight:700;">$${calculated.price_per_share?.value?.toFixed(2) || '—'}</div>
                <div style="font-size:0.85rem;opacity:0.85;margin-top:6px;">Your Price Target</div>
                <div id="ev-sens-diff" style="font-size:0.8rem;margin-top:8px;opacity:0.75;">vs AXIOM: +0.0%</div>
            </div>
        </div>
    </div>` : '';

    const saveButtonHtml = `
    <div style="padding:24px;">
        <div id="ev-user-valuation-indicator" style="display:${hasSaved ? 'block' : 'none'};margin-bottom:12px;padding:10px 14px;background:rgba(139,92,246,0.1);border:1px solid rgba(139,92,246,0.3);border-radius:6px;font-size:0.85rem;color:var(--text-secondary);">
            Your custom valuation: <strong>$${hasSaved ? savedVal.pricePerShare.toFixed(2) : '—'}</strong>/share
            <span style="margin-left:8px;color:var(--text-muted);">Saved ${hasSaved ? new Date(savedVal.savedAt).toLocaleDateString() : ''}</span>
        </div>
        <div style="display:flex;gap:10px;">
            <button id="ev-save-valuation-btn" onclick="saveUserValuation()"
                    style="flex:1;padding:14px 24px;background:linear-gradient(135deg,#8b5cf6 0%,#7c3aed 100%);color:white;border:none;border-radius:8px;cursor:pointer;font-weight:600;font-size:0.95rem;">
                ${hasSaved ? 'Update Your Valuation' : 'Save Your Valuation'}
            </button>
            <button id="ev-remove-valuation-btn" onclick="removeUserValuation()"
                    style="display:${hasSaved ? 'block' : 'none'};padding:14px 18px;background:transparent;color:#ef4444;border:1px solid #ef4444;border-radius:8px;cursor:pointer;font-weight:600;font-size:0.85rem;">
                Remove
            </button>
        </div>
    </div>`;

    return `<div style="background:var(--bg-secondary);">${assumptionsHtml}${calculationHtml}${sensitivityHtml}${saveButtonHtml}</div>`;
}

// ── Tooltip ───────────────────────────────────────────────────────────────────

function initTooltips() {
    const tip     = document.getElementById('dcf-tip');
    const content = document.getElementById('ev-page-content');
    if (!tip || !content) return;

    let activeEl = null;

    function showTip(el) {
        if (activeEl === el) return;
        hideTip();
        activeEl = el;
        let text = el.hasAttribute('title') ? el.getAttribute('title') : el.dataset.savedTitle;
        if (!text) return;
        if (el.hasAttribute('title')) { el.dataset.savedTitle = text; el.removeAttribute('title'); }
        const parts = text.split('\n');
        const last  = parts[parts.length - 1];
        const isSource = last.startsWith('Yahoo Finance');
        tip.innerHTML = parts.slice(0, isSource ? -1 : parts.length).join('<br>')
            + (isSource ? `<span class="tip-source">${last}</span>` : '');
        tip.classList.add('visible');
    }

    function hideTip() {
        if (activeEl) {
            if (activeEl.dataset.savedTitle) { activeEl.setAttribute('title', activeEl.dataset.savedTitle); delete activeEl.dataset.savedTitle; }
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
        const x = e.clientX + 14, y = e.clientY + 18;
        tip.style.left = Math.min(x, window.innerWidth  - tip.offsetWidth  - 14) + 'px';
        tip.style.top  = (y + tip.offsetHeight > window.innerHeight ? e.clientY - tip.offsetHeight - 8 : y) + 'px';
    });

    content.addEventListener('mouseleave', hideTip);
}

// ── Theme ─────────────────────────────────────────────────────────────────────

function applyTheme() {
    const saved = localStorage.getItem('theme') || 'light';
    document.documentElement.setAttribute('data-theme', saved);
}

function toggleTheme() {
    const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('theme', next);
    document.getElementById('theme-btn').textContent = next === 'dark' ? '☀ Light' : '☾ Dark';
}

// ── Init ──────────────────────────────────────────────────────────────────────

async function init() {
    applyTheme();
    document.getElementById('theme-btn').textContent =
        localStorage.getItem('theme') === 'dark' ? '☀ Light' : '☾ Dark';

    const content = document.getElementById('ev-page-content');
    content.innerHTML = '<div style="padding:60px;text-align:center;color:var(--text-muted);font-size:1rem;">Loading EV/EBITDA breakdown…</div>';

    try {
        const res  = await fetch(`/api/valuation/${companyId}/details`);
        const data = await res.json();

        if (data.company_name) {
            document.title = `${data.company_name} — EV/EBITDA | AXIOM`;
            document.getElementById('hdr-company').textContent = data.company_name;
        }
        if (data.ticker)  document.getElementById('hdr-ticker').textContent = data.ticker;
        if (data.sector)  document.getElementById('hdr-sector').textContent = data.sector;

        const s = data.summary || {};
        const rec = (s.recommendation || '').toUpperCase();
        const recColors = { BUY: '#10b981', 'STRONG BUY': '#059669', HOLD: '#f59e0b', SELL: '#ef4444', 'STRONG SELL': '#dc2626' };

        document.getElementById('hdr-price').textContent  = s.current_price != null ? '$' + s.current_price.toFixed(2)  : '—';
        document.getElementById('hdr-fv').textContent     = s.ev_ebitda_fv  != null ? '$' + s.ev_ebitda_fv.toFixed(2)   : (s.fair_value != null ? '$' + s.fair_value.toFixed(2) : '—');
        document.getElementById('hdr-rec').textContent    = rec || '—';
        document.getElementById('hdr-rec').style.background = recColors[rec] || 'var(--text-muted)';

        if (data.ev_ebitda_details) {
            evDetailsCache = data.ev_ebitda_details;
            evBaseInputs   = data.ev_ebitda_details.base_inputs || null;
            content.innerHTML = renderEVEBITDADetails(data.ev_ebitda_details);
            initTooltips();
        } else {
            content.innerHTML = '<div style="padding:60px;text-align:center;color:var(--text-muted);">EV/EBITDA details not available for this company.</div>';
        }
    } catch (err) {
        content.innerHTML = `<div style="padding:60px;text-align:center;color:#ef4444;">Failed to load data: ${err.message}</div>`;
    }
}

document.addEventListener('DOMContentLoaded', init);
