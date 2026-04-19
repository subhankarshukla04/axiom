"""
Anomaly Detector
Z-score analysis of DCF assumptions vs sector medians.
Flags outliers with inline warning messages.
"""

import logging
import math
from typing import Dict, List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

# Sector-level benchmark defaults (used when FMP data is unavailable)
# These are rough market medians — override with live FMP data where available
SECTOR_BENCHMARKS = {
    'Technology': {
        'wacc': {'mean': 9.4, 'std': 1.8},
        'terminal_growth': {'mean': 2.8, 'std': 0.6},
        'ebitda_margin': {'mean': 28.0, 'std': 15.0},
        'revenue_growth_y1': {'mean': 12.0, 'std': 10.0},
        'beta': {'mean': 1.3, 'std': 0.3},
    },
    'Healthcare': {
        'wacc': {'mean': 8.5, 'std': 1.5},
        'terminal_growth': {'mean': 2.5, 'std': 0.5},
        'ebitda_margin': {'mean': 22.0, 'std': 12.0},
        'revenue_growth_y1': {'mean': 8.0, 'std': 8.0},
        'beta': {'mean': 0.9, 'std': 0.25},
    },
    'Consumer Cyclical': {
        'wacc': {'mean': 9.0, 'std': 1.5},
        'terminal_growth': {'mean': 2.2, 'std': 0.5},
        'ebitda_margin': {'mean': 12.0, 'std': 8.0},
        'revenue_growth_y1': {'mean': 6.0, 'std': 7.0},
        'beta': {'mean': 1.2, 'std': 0.35},
    },
    'Financial Services': {
        'wacc': {'mean': 10.5, 'std': 2.0},
        'terminal_growth': {'mean': 2.0, 'std': 0.5},
        'ebitda_margin': {'mean': 35.0, 'std': 18.0},
        'revenue_growth_y1': {'mean': 7.0, 'std': 8.0},
        'beta': {'mean': 1.1, 'std': 0.3},
    },
    'Energy': {
        'wacc': {'mean': 10.0, 'std': 2.2},
        'terminal_growth': {'mean': 1.8, 'std': 0.6},
        'ebitda_margin': {'mean': 25.0, 'std': 12.0},
        'revenue_growth_y1': {'mean': 4.0, 'std': 12.0},
        'beta': {'mean': 1.4, 'std': 0.5},
    },
    'Industrials': {
        'wacc': {'mean': 8.8, 'std': 1.5},
        'terminal_growth': {'mean': 2.0, 'std': 0.5},
        'ebitda_margin': {'mean': 14.0, 'std': 6.0},
        'revenue_growth_y1': {'mean': 5.0, 'std': 6.0},
        'beta': {'mean': 1.1, 'std': 0.3},
    },
    'default': {
        'wacc': {'mean': 9.0, 'std': 2.0},
        'terminal_growth': {'mean': 2.5, 'std': 0.7},
        'ebitda_margin': {'mean': 20.0, 'std': 12.0},
        'revenue_growth_y1': {'mean': 8.0, 'std': 8.0},
        'beta': {'mean': 1.0, 'std': 0.35},
    },
}

ZSCORE_THRESHOLD = 2.0  # Flag if |z-score| > 2.0


def _z_score(value: float, mean: float, std: float) -> float:
    if std == 0:
        return 0.0
    return (value - mean) / std


def _get_benchmarks(sector: str) -> dict:
    """Get sector benchmarks, falling back to default if sector not in table."""
    for key in SECTOR_BENCHMARKS:
        if key.lower() in sector.lower() or sector.lower() in key.lower():
            return SECTOR_BENCHMARKS[key]
    return SECTOR_BENCHMARKS['default']


def analyze_assumptions(
    assumptions: Dict,
    sector: str = 'default',
    sector_benchmarks: Optional[Dict] = None,
) -> List[Dict]:
    """
    Analyze DCF assumptions for statistical outliers vs sector median.

    Args:
        assumptions: dict with wacc, terminal_growth, ebitda_margin,
                     revenue, ebitda, growth_rate_y1, beta, etc.
        sector: Company sector name for benchmark lookup
        sector_benchmarks: Optional override benchmarks from FMP

    Returns:
        List of anomaly dicts with: field, value, z_score, message, severity
    """
    benchmarks = sector_benchmarks or _get_benchmarks(sector)
    anomalies = []

    # ── WACC check ────────────────────────────────────────────────────────────
    wacc = assumptions.get('wacc') or assumptions.get('risk_free_rate', 0.044)
    if wacc and isinstance(wacc, (int, float)):
        wacc_pct = wacc * 100 if wacc < 1 else wacc  # normalize to %
        if 'wacc' in benchmarks:
            b = benchmarks['wacc']
            z = _z_score(wacc_pct, b['mean'], b['std'])
            if abs(z) > ZSCORE_THRESHOLD:
                direction = 'below' if z < 0 else 'above'
                sector_median = b['mean']
                anomalies.append({
                    'field': 'wacc',
                    'value': wacc_pct,
                    'z_score': round(z, 2),
                    'severity': 'warning' if abs(z) < 3 else 'critical',
                    'message': (
                        f"WACC {wacc_pct:.1f}% is {abs(z):.1f}σ {direction} "
                        f"{sector} sector median ({sector_median:.1f}%) — "
                        f"{'verify debt cost inputs' if z < 0 else 'check if company risk profile warrants higher discount rate'}"
                    ),
                })

    # ── Terminal growth check ─────────────────────────────────────────────────
    tg = assumptions.get('terminal_growth')
    if tg is not None:
        tg_pct = tg * 100 if tg < 1 else tg
        if 'terminal_growth' in benchmarks:
            b = benchmarks['terminal_growth']
            z = _z_score(tg_pct, b['mean'], b['std'])
            if abs(z) > ZSCORE_THRESHOLD:
                anomalies.append({
                    'field': 'terminal_growth',
                    'value': tg_pct,
                    'z_score': round(z, 2),
                    'severity': 'warning',
                    'message': (
                        f"Terminal growth {tg_pct:.1f}% is {abs(z):.1f}σ "
                        f"{'above' if z > 0 else 'below'} {sector} sector median "
                        f"({b['mean']:.1f}%)"
                        + (' — exceeds long-run GDP; review assumption' if z > 0 else '')
                    ),
                })

        # Hard check: terminal growth > 4% is almost always wrong
        if tg_pct > 4.0:
            anomalies.append({
                'field': 'terminal_growth',
                'value': tg_pct,
                'z_score': None,
                'severity': 'critical',
                'message': (
                    f"Terminal growth {tg_pct:.1f}% exceeds 4% — "
                    "this implies the company will eventually be larger than the entire economy. "
                    "Values above 3.5% are very rarely justifiable."
                ),
            })

    # ── EBITDA margin check ───────────────────────────────────────────────────
    revenue = assumptions.get('revenue', 0)
    ebitda = assumptions.get('ebitda', 0)
    if revenue and ebitda and revenue > 0:
        margin = (ebitda / revenue) * 100
        if 'ebitda_margin' in benchmarks:
            b = benchmarks['ebitda_margin']
            z = _z_score(margin, b['mean'], b['std'])
            if abs(z) > ZSCORE_THRESHOLD:
                anomalies.append({
                    'field': 'ebitda_margin',
                    'value': round(margin, 1),
                    'z_score': round(z, 2),
                    'severity': 'warning' if abs(z) < 3 else 'critical',
                    'message': (
                        f"EBITDA margin {margin:.1f}% is {abs(z):.1f}σ "
                        f"{'above' if z > 0 else 'below'} {sector} sector median "
                        f"({b['mean']:.1f}%) — "
                        + ('confirm no one-time items inflating EBITDA' if z > 0
                           else 'verify company is not in restructuring phase')
                    ),
                })

    # ── Revenue growth check ──────────────────────────────────────────────────
    g1 = assumptions.get('growth_rate_y1')
    if g1 is not None:
        g1_pct = g1 * 100 if g1 < 1 else g1
        if 'revenue_growth_y1' in benchmarks:
            b = benchmarks['revenue_growth_y1']
            z = _z_score(g1_pct, b['mean'], b['std'])
            if abs(z) > ZSCORE_THRESHOLD:
                anomalies.append({
                    'field': 'growth_rate_y1',
                    'value': round(g1_pct, 1),
                    'z_score': round(z, 2),
                    'severity': 'info' if abs(z) < 2.5 else 'warning',
                    'message': (
                        f"Year 1 growth {g1_pct:.1f}% is {abs(z):.1f}σ "
                        f"{'above' if z > 0 else 'below'} {sector} sector median "
                        f"({b['mean']:.1f}%) — "
                        + ('verify high-growth thesis is supported by backlog or contracts' if z > 0
                           else 'check for cyclical or competitive headwinds')
                    ),
                })

    # ── Beta check ────────────────────────────────────────────────────────────
    beta = assumptions.get('beta')
    if beta is not None:
        if 'beta' in benchmarks:
            b = benchmarks['beta']
            z = _z_score(float(beta), b['mean'], b['std'])
            if abs(z) > ZSCORE_THRESHOLD:
                anomalies.append({
                    'field': 'beta',
                    'value': round(float(beta), 2),
                    'z_score': round(z, 2),
                    'severity': 'info',
                    'message': (
                        f"Beta {beta:.2f} is {abs(z):.1f}σ "
                        f"{'above' if z > 0 else 'below'} {sector} sector median "
                        f"({b['mean']:.2f}) — "
                        + ('high beta suggests significant market sensitivity' if z > 0
                           else 'low beta may indicate defensive characteristics or illiquidity')
                    ),
                })

    return anomalies


def get_anomaly_summary(anomalies: List[Dict]) -> Dict:
    """Summarize anomaly list for API response."""
    return {
        'total': len(anomalies),
        'critical': sum(1 for a in anomalies if a.get('severity') == 'critical'),
        'warnings': sum(1 for a in anomalies if a.get('severity') == 'warning'),
        'info': sum(1 for a in anomalies if a.get('severity') == 'info'),
        'anomalies': anomalies,
        'checked_at': datetime.utcnow().isoformat(),
    }
