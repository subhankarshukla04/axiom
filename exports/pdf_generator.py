"""
PDF Pitchbook Generator (WeasyPrint)
Generates a 7-section institutional-quality PDF report.

Prerequisites:
  - pip install weasyprint
  - macOS: brew install pango
  - Docker: apt-get install -y libpangoft2-1.0-0 libgdk-pixbuf-2.0-0
"""

import io
import logging
import os
from datetime import datetime
from typing import Optional
from jinja2 import Environment, FileSystemLoader, DictLoader

logger = logging.getLogger(__name__)

# Inline CSS for PDF (print-optimized)
PDF_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap');

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
    font-family: 'Inter', 'Helvetica Neue', Arial, sans-serif;
    font-size: 10pt;
    color: #1a2036;
    line-height: 1.5;
}

@page {
    size: letter;
    margin: 0.75in 0.75in 0.75in 0.75in;
    @bottom-right {
        content: counter(page) " of " counter(pages);
        font-size: 8pt;
        color: #888;
    }
}

@page :first {
    margin: 0;
    @bottom-right { content: none; }
}

.page-break { page-break-before: always; }

/* Cover */
.cover {
    background: #0a1628;
    color: white;
    height: 100vh;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    text-align: center;
    padding: 80px;
}
.cover .logo { font-size: 18pt; font-weight: 700; color: #4fc3f7; letter-spacing: 4px; margin-bottom: 60px; }
.cover .company-name { font-size: 32pt; font-weight: 300; color: white; margin-bottom: 12px; }
.cover .ticker { font-size: 16pt; color: #90caf9; margin-bottom: 40px; }
.cover .subtitle { font-size: 12pt; color: #78909c; margin-bottom: 80px; }
.cover .meta { font-size: 9pt; color: #546e7a; border-top: 1px solid #263850; padding-top: 20px; }
.cover .confidential { font-size: 8pt; color: #ef5350; letter-spacing: 2px; margin-top: 16px; }

/* Section Headers */
.section-title {
    font-size: 14pt;
    font-weight: 700;
    color: #0a1628;
    border-bottom: 2px solid #1565c0;
    padding-bottom: 8px;
    margin-bottom: 20px;
}

/* Key Metrics Table */
.metrics-table { width: 100%; border-collapse: collapse; margin: 16px 0; }
.metrics-table th {
    background: #0a1628;
    color: white;
    padding: 8px 12px;
    text-align: left;
    font-size: 9pt;
    font-weight: 600;
}
.metrics-table td { padding: 6px 12px; border-bottom: 1px solid #e0e7ef; font-size: 9pt; }
.metrics-table tr:nth-child(even) td { background: #f5f8fc; }

/* Signal badges */
.signal-strong-buy { background: #00c853; color: white; padding: 2px 8px; border-radius: 3px; font-size: 8pt; font-weight: 700; }
.signal-buy { background: #64dd17; color: #333; padding: 2px 8px; border-radius: 3px; font-size: 8pt; font-weight: 700; }
.signal-hold { background: #ffd600; color: #333; padding: 2px 8px; border-radius: 3px; font-size: 8pt; font-weight: 700; }
.signal-sell { background: #ff6d00; color: white; padding: 2px 8px; border-radius: 3px; font-size: 8pt; font-weight: 700; }

/* Source badge */
.source-badge { font-size: 7pt; color: #1565c0; background: #e3f2fd; padding: 1px 5px; border-radius: 2px; }
.source-fallback { font-size: 7pt; color: #666; background: #f5f5f5; padding: 1px 5px; border-radius: 2px; }
.source-gap { font-size: 7pt; color: #b71c1c; background: #ffebee; padding: 1px 5px; border-radius: 2px; }

/* Football field */
.ff-row { display: flex; align-items: center; margin: 6px 0; }
.ff-label { width: 160px; font-size: 9pt; font-weight: 600; }
.ff-bar-container { flex: 1; background: #e8eef4; height: 20px; position: relative; border-radius: 2px; }
.ff-bar { position: absolute; height: 100%; background: #1565c0; border-radius: 2px; opacity: 0.75; }
.ff-current-price { position: absolute; width: 2px; height: 24px; background: #ef5350; top: -2px; }

/* Sensitivity table */
.sens-table { width: 100%; border-collapse: collapse; font-size: 8pt; }
.sens-table th { background: #263850; color: white; padding: 5px 8px; text-align: center; }
.sens-table td { padding: 4px 8px; text-align: center; border: 1px solid #ddd; }
.sens-green { background: #e8f5e9; }
.sens-yellow { background: #fffde7; }
.sens-red { background: #ffebee; }
.sens-base { border: 2px solid #1565c0 !important; font-weight: 700; }

/* Two-column layout */
.two-col { display: flex; gap: 24px; }
.col-half { flex: 1; }

/* Disclosure section */
.disclosure { font-size: 8pt; color: #546e7a; margin-top: 20px; border-top: 1px solid #e0e7ef; padding-top: 16px; }
"""

# Jinja2 template for PDF
PDF_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>{{ css }}</style>
</head>
<body>

<!-- COVER PAGE -->
<div class="cover">
    <div class="logo">AXIOM</div>
    <div class="company-name">{{ company.name }}</div>
    <div class="ticker">{{ company.ticker }} &nbsp;·&nbsp; {{ company.sector }}</div>
    <div class="subtitle">Institutional Valuation Analysis</div>
    <div class="meta">
        Analyst: {{ analyst }}<br>
        Date: {{ report_date }}<br>
        Current Price: ${{ "%.2f"|format(company.current_price or 0) }} &nbsp;·&nbsp;
        Fair Value: ${{ "%.2f"|format(valuation.fair_value or 0) }}
    </div>
    <div class="confidential">CONFIDENTIAL — FOR INTERNAL USE ONLY</div>
</div>

<!-- EXECUTIVE SUMMARY -->
<div class="page-break">
<h1 class="section-title">Executive Summary</h1>
<div class="two-col">
<div class="col-half">
<h3 style="margin-bottom:12px;">Key Metrics</h3>
<table class="metrics-table">
<tr><th>Metric</th><th>Value</th><th>Source</th></tr>
<tr><td>Current Price</td><td>${{ "%.2f"|format(company.current_price or 0) }}</td><td><span class="source-badge">Market</span></td></tr>
<tr><td>DCF Fair Value</td><td>${{ "%.2f"|format(valuation.fair_value or valuation.dcf_value or 0) }}</td><td><span class="source-badge">DCF Model</span></td></tr>
<tr><td>Upside / (Downside)</td><td>{{ "%.1f"|format(valuation.upside_pct or 0) }}%</td><td></td></tr>
<tr><td>WACC</td><td>{{ "%.1f"|format((valuation.wacc or 0.09) * 100) }}%</td><td><span class="source-badge">CAPM</span></td></tr>
<tr><td>Risk-Free Rate</td><td>{{ "%.2f"|format((valuation.risk_free_rate or 0.044) * 100) }}%</td><td><span class="source-badge">FRED: DGS10</span></td></tr>
<tr><td>Beta</td><td>{{ "%.2f"|format(valuation.beta or 1.0) }}</td><td><span class="source-fallback">yfinance</span></td></tr>
<tr><td>Revenue (LTM)</td><td>${{ "{:,.0f}".format((company.revenue or 0)/1e6) }}M</td><td><span class="source-badge">SEC EDGAR</span></td></tr>
<tr><td>EBITDA (LTM)</td><td>${{ "{:,.0f}".format((company.ebitda or 0)/1e6) }}M</td><td><span class="source-badge">SEC EDGAR</span></td></tr>
<tr><td>Terminal Growth</td><td>{{ "%.1f"|format((valuation.terminal_growth or 0.025) * 100) }}%</td><td><span class="source-fallback">User Input</span></td></tr>
</table>
</div>
<div class="col-half">
<h3 style="margin-bottom:12px;">Investment Recommendation</h3>
{% if valuation.upside_pct and valuation.upside_pct >= 20 %}
<span class="signal-strong-buy">STRONG BUY</span>
{% elif valuation.upside_pct and valuation.upside_pct >= 10 %}
<span class="signal-buy">BUY</span>
{% elif valuation.upside_pct and valuation.upside_pct >= -10 %}
<span class="signal-hold">HOLD</span>
{% else %}
<span class="signal-sell">SELL</span>
{% endif %}
<p style="margin-top:16px; font-size:10pt;">
Based on DCF analysis using {{ "%.1f"|format((valuation.wacc or 0.09)*100) }}% WACC and
{{ "%.1f"|format((valuation.terminal_growth or 0.025)*100) }}% terminal growth rate,
{{ company.name }} appears
{% if valuation.upside_pct and valuation.upside_pct > 0 %}undervalued by approximately {{ "%.0f"|format(valuation.upside_pct) }}%.
{% else %}overvalued by approximately {{ "%.0f"|format(-(valuation.upside_pct or 0)) }}%.{% endif %}
</p>
</div>
</div>
</div>

<!-- DCF ANALYSIS -->
<div class="page-break">
<h1 class="section-title">DCF Analysis</h1>
<table class="metrics-table">
<tr><th>Item</th><th>Value ($M)</th></tr>
<tr><td>PV of FCFs (10yr)</td><td>${{ "{:,.1f}".format((valuation.pv_fcfs_total or 0)/1e6) }}</td></tr>
<tr><td>Terminal Value</td><td>${{ "{:,.1f}".format((valuation.terminal_value or 0)/1e6) }}</td></tr>
<tr><td>PV of Terminal Value</td><td>${{ "{:,.1f}".format((valuation.pv_terminal or 0)/1e6) }}</td></tr>
<tr><td><strong>Enterprise Value</strong></td><td><strong>${{ "{:,.1f}".format((valuation.enterprise_value or 0)/1e6) }}</strong></td></tr>
<tr><td>Less: Net Debt</td><td>${{ "{:,.1f}".format((valuation.net_debt or 0)/1e6) }}</td></tr>
<tr><td><strong>Equity Value</strong></td><td><strong>${{ "{:,.1f}".format((valuation.equity_value or 0)/1e6) }}</strong></td></tr>
<tr><td><strong>Implied Share Price</strong></td><td><strong>${{ "%.2f"|format(valuation.fair_value or valuation.dcf_value or 0) }}</strong></td></tr>
</table>
</div>

<!-- SCENARIO ANALYSIS -->
{% if scenarios %}
<div class="page-break">
<h1 class="section-title">Scenario Analysis</h1>
<table class="metrics-table">
<tr><th>Metric</th><th>Bear Case</th><th>Base Case</th><th>Bull Case</th></tr>
<tr>
    <td>Implied Value</td>
    <td>${{ "%.2f"|format(scenarios.bear.fair_value or 0) }}</td>
    <td>${{ "%.2f"|format(scenarios.base.fair_value or 0) }}</td>
    <td>${{ "%.2f"|format(scenarios.bull.fair_value or 0) }}</td>
</tr>
<tr>
    <td>WACC</td>
    <td>{{ "%.1f"|format((scenarios.bear.wacc or 0.11)*100) }}%</td>
    <td>{{ "%.1f"|format((scenarios.base.wacc or 0.09)*100) }}%</td>
    <td>{{ "%.1f"|format((scenarios.bull.wacc or 0.08)*100) }}%</td>
</tr>
</table>
</div>
{% endif %}

<!-- LBO ANALYSIS -->
{% if lbo %}
<div class="page-break">
<h1 class="section-title">LBO Analysis</h1>
<div class="two-col">
<div class="col-half">
<table class="metrics-table">
<tr><th>Item</th><th>Value</th></tr>
<tr><td>Entry EV</td><td>${{ "{:,.1f}".format(lbo.entry_ev or 0) }}M</td></tr>
<tr><td>Entry Equity</td><td>${{ "{:,.1f}".format(lbo.entry_equity or 0) }}M</td></tr>
<tr><td>Exit EV</td><td>${{ "{:,.1f}".format(lbo.exit_ev or 0) }}M</td></tr>
<tr><td>Exit Equity</td><td>${{ "{:,.1f}".format(lbo.exit_equity or 0) }}M</td></tr>
<tr><td><strong>IRR</strong></td><td><strong>{{ "%.1f"|format(lbo.irr or 0) }}%</strong></td></tr>
<tr><td><strong>MOIC</strong></td><td><strong>{{ "%.2f"|format(lbo.moic or 0) }}x</strong></td></tr>
</table>
</div>
</div>
</div>
{% endif %}

<!-- DISCLOSURES -->
<div class="page-break">
<h1 class="section-title">Data Sources & Disclosures</h1>
<div class="disclosure">
<p><strong>Data Sources:</strong></p>
<ul style="margin-left:16px; margin-top:8px;">
<li>Risk-Free Rate: Federal Reserve Economic Data (FRED), Series DGS10 — {{ report_date }}</li>
<li>Company Financials: SEC EDGAR XBRL (Form 10-K) where available; yfinance as fallback</li>
<li>Real-Time Price: Finnhub where available; yfinance as fallback</li>
<li>Sector Multiples: Financial Modeling Prep (FMP) sector-pe endpoint where available</li>
<li>Analyst Consensus: Financial Modeling Prep (FMP) where available</li>
<li>Beta: yfinance 5-year weekly regression vs S&amp;P 500 (SPY)</li>
<li>13F Holdings Data: SEC EDGAR 13F-HR filings (45-day regulatory delay)</li>
</ul>
<p style="margin-top:16px;"><strong>Important Disclosures:</strong></p>
<p style="margin-top:8px;">This report is generated by AXIOM, an institutional valuation platform, for internal analytical purposes only.
It does not constitute investment advice. All valuations are model-dependent and subject to the assumptions stated herein.
Past performance is not indicative of future results. 13F institutional holdings data is subject to a 45-day regulatory
reporting delay as required by SEC Rule 13f-1.</p>
<p style="margin-top:12px; font-size:8pt; color:#999;">Generated: {{ report_date }} | AXIOM Platform</p>
</div>
</div>

</body>
</html>"""


def generate_pdf(
    company: dict,
    valuation: dict,
    scenarios: Optional[dict] = None,
    lbo_data: Optional[dict] = None,
    analyst: str = 'AXIOM Platform',
) -> bytes:
    """
    Generate PDF pitchbook as bytes.

    Args:
        company: dict with name, ticker, sector, current_price, revenue, ebitda, etc.
        valuation: dict with fair_value, dcf_value, wacc, beta, upside_pct, etc.
        scenarios: Optional dict with bear/base/bull valuation results
        lbo_data: Optional LBO result dict
        analyst: Analyst name for cover page

    Returns:
        PDF as bytes (stream to HTTP response).

    Raises:
        ImportError: If WeasyPrint not installed
        RuntimeError: If WeasyPrint system dependencies not available
    """
    try:
        from weasyprint import HTML, CSS
    except ImportError:
        raise ImportError(
            'WeasyPrint is required for PDF export.\n'
            'Install: pip install weasyprint\n'
            'macOS: brew install pango\n'
            'Docker: apt-get install -y libpangoft2-1.0-0 libgdk-pixbuf-2.0-0'
        )

    # Compute upside if not pre-computed
    if 'upside_pct' not in valuation:
        fair = valuation.get('fair_value') or valuation.get('dcf_value', 0)
        current = company.get('current_price', 0)
        if fair and current:
            valuation['upside_pct'] = (fair - current) / current * 100

    # Render Jinja2 template
    env = Environment(loader=DictLoader({'pitchbook.html': PDF_TEMPLATE}))
    template = env.get_template('pitchbook.html')

    html_content = template.render(
        css=PDF_CSS,
        company=company,
        valuation=valuation,
        scenarios=scenarios,
        lbo=lbo_data,
        analyst=analyst,
        report_date=datetime.utcnow().strftime('%B %d, %Y'),
    )

    try:
        pdf_bytes = HTML(string=html_content).write_pdf()
        return pdf_bytes
    except Exception as e:
        logger.error(f'WeasyPrint PDF generation failed: {e}')
        raise RuntimeError(
            f'PDF generation failed: {e}\n'
            'Check that pango/WeasyPrint system dependencies are installed.\n'
            'macOS: brew install pango\n'
            'Docker: apt-get install -y libpangoft2-1.0-0'
        )
