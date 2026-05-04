"""
Phase 4 — uncertainty quantification.

Replaces the cosmetic `final_equity_value * BEAR_MULTIPLIER (0.75)` /
`* BULL_MULTIPLIER (1.25)` blanket triple — which had no relation to the
actual valuation drivers — with three deterministic perturbations along
the inputs that move a DCF the most:

    Bear:  WACC +100bp, terminal growth -100bp, growth Y1 × 0.75
    Base:  unchanged
    Bull:  WACC -100bp, terminal growth +100bp, growth Y1 × 1.25

These deltas come straight from the codebase audit ("Phase 4: Add uncertainty,
Output 3-point estimates: bear / base / bull. Generate by perturbing terminal
growth ±100bp, WACC ±100bp, growth Y1 ±25%.") and are intentionally simple —
this is not a Monte Carlo, it's a transparent sensitivity triple that a user
can sanity-check.

Each scenario re-runs only the DCF leg of the blend; the EV/EBITDA and P/E
comp legs are unchanged across scenarios because the comp multiples are
exogenous to WACC / terminal growth / Y1 growth. The blended scenario equity
value uses the same `(weight_dcf, weight_ev, weight_pe)` as the base.
"""
from typing import Dict, List, Optional

# Audit-prescribed perturbation deltas
TERMINAL_GROWTH_DELTA = 0.01     # ±100bp
WACC_DELTA            = 0.01     # ±100bp
GROWTH_Y1_FACTOR_BEAR = 0.75     # −25%
GROWTH_Y1_FACTOR_BULL = 1.25     # +25%


def _build_growth_schedule(growth_y1: float, growth_y2: float, growth_y3: float,
                            terminal_growth: float) -> List[float]:
    """10-year schedule mirroring `valuation_professional.enhanced_dcf_valuation`."""
    return [
        growth_y1, growth_y1, growth_y2, growth_y2, growth_y3,
        growth_y3,
        (growth_y3 + terminal_growth) / 2,
        terminal_growth + 0.010,
        terminal_growth + 0.005,
        terminal_growth,
    ]


def _derive_y2_y3(growth_y1: float, terminal_growth: float) -> tuple:
    """Mirror `valuation.pipeline.calibrate`'s convergence formula so
    perturbing Y1 propagates correctly through Y2/Y3."""
    y2 = round(growth_y1 * 0.67 + terminal_growth * 0.33, 4)
    y3 = round(growth_y1 * 0.33 + terminal_growth * 0.67, 4)
    return y2, y3


def run_dcf_projection(
    revenue: float, ebitda: float, depreciation: float,
    raw_capex_pct: float, normalized_capex_pct: float,
    wc_change: float, tax_rate: float,
    shares: float, debt: float, cash: float,
    wacc: float, terminal_growth: float,
    growth_y1: float, growth_y2: Optional[float] = None, growth_y3: Optional[float] = None,
) -> Dict[str, float]:
    """Pure-function 10-year DCF + terminal value.

    If `growth_y2`/`growth_y3` are None, they are derived from `(growth_y1,
    terminal_growth)` via the same convergence formula used elsewhere in
    the codebase. This is what scenarios use when perturbing only Y1.

    Returns dict with: total_pv_fcf, terminal_value, pv_terminal_value,
    dcf_enterprise_value, dcf_equity_value, dcf_price_per_share, fcf_schedule.
    """
    if growth_y2 is None or growth_y3 is None:
        growth_y2, growth_y3 = _derive_y2_y3(growth_y1, terminal_growth)

    # Defensive: terminal must be < WACC for Gordon growth to converge
    if wacc <= terminal_growth:
        terminal_growth = wacc - 0.01

    schedule = _build_growth_schedule(growth_y1, growth_y2, growth_y3, terminal_growth)

    projected_fcf = []
    total_pv_fcf  = 0.0
    base_revenue  = revenue
    current_rev   = revenue

    for year_idx, growth_rate in enumerate(schedule, start=1):
        current_rev *= (1 + growth_rate)

        if year_idx <= 2:
            year_capex_pct = raw_capex_pct
        else:
            t = (year_idx - 2) / 8
            year_capex_pct = raw_capex_pct + (normalized_capex_pct - raw_capex_pct) * t

        year_ebitda = current_rev * (ebitda / revenue)
        year_da     = current_rev * (depreciation / revenue)
        year_ebit   = year_ebitda - year_da
        year_nopat  = year_ebit * (1 - tax_rate)
        year_capex  = current_rev * year_capex_pct
        year_wc     = wc_change * (current_rev / base_revenue)
        year_fcf    = year_nopat + year_da - year_capex - year_wc

        pv_fcf = year_fcf / ((1 + wacc) ** year_idx)
        total_pv_fcf += pv_fcf
        projected_fcf.append(year_fcf)

    terminal_fcf      = projected_fcf[-1] * (1 + terminal_growth)
    terminal_value    = terminal_fcf / (wacc - terminal_growth)
    pv_terminal_value = terminal_value / ((1 + wacc) ** 10)

    enterprise_value  = total_pv_fcf + pv_terminal_value
    equity_value      = enterprise_value + cash - debt
    price_per_share   = equity_value / shares if shares > 0 else 0.0

    return {
        'total_pv_fcf':         total_pv_fcf,
        'terminal_value':       terminal_value,
        'pv_terminal_value':    pv_terminal_value,
        'dcf_enterprise_value': enterprise_value,
        'dcf_equity_value':     equity_value,
        'dcf_price_per_share':  price_per_share,
        'fcf_schedule':         projected_fcf,
        'effective_terminal_g': terminal_growth,   # may differ from input if WACC clamp engaged
        'effective_wacc':       wacc,
    }


def _blend(dcf_equity: float, comp_ev_equity: float, comp_pe_equity: float,
           weight_dcf: float, weight_ev: float, weight_pe: float) -> float:
    return (dcf_equity * weight_dcf
            + comp_ev_equity * weight_ev
            + comp_pe_equity * weight_pe)


def compute_scenarios(
    *,
    revenue: float, ebitda: float, depreciation: float,
    raw_capex_pct: float, normalized_capex_pct: float,
    wc_change: float, tax_rate: float,
    shares: float, debt: float, cash: float,
    wacc: float, terminal_growth: float, growth_y1: float,
    comp_ev_equity: float, comp_pe_equity: float,
    weight_dcf: float, weight_ev: float, weight_pe: float,
) -> Dict[str, Dict]:
    """Return bear / base / bull triple plus a `spread_pct` summary.

    Each scenario's `dcf_equity_value` is computed by re-running the DCF
    projection with perturbed (wacc, terminal_growth, growth_y1) and
    re-deriving y2/y3 from the convergence formula. Comp legs are held
    constant. The blended scenario equity uses the same weights as base.
    """
    common = dict(
        revenue=revenue, ebitda=ebitda, depreciation=depreciation,
        raw_capex_pct=raw_capex_pct, normalized_capex_pct=normalized_capex_pct,
        wc_change=wc_change, tax_rate=tax_rate,
        shares=shares, debt=debt, cash=cash,
    )

    perturbations = {
        'bear': dict(
            wacc            = wacc + WACC_DELTA,
            terminal_growth = max(0.0, terminal_growth - TERMINAL_GROWTH_DELTA),
            growth_y1       = growth_y1 * GROWTH_Y1_FACTOR_BEAR,
        ),
        'base': dict(
            wacc            = wacc,
            terminal_growth = terminal_growth,
            growth_y1       = growth_y1,
        ),
        'bull': dict(
            wacc            = wacc - WACC_DELTA,
            terminal_growth = terminal_growth + TERMINAL_GROWTH_DELTA,
            growth_y1       = growth_y1 * GROWTH_Y1_FACTOR_BULL,
        ),
    }

    out: Dict[str, Dict] = {}
    for name, p in perturbations.items():
        proj = run_dcf_projection(**common, **p)
        blended_equity = _blend(
            proj['dcf_equity_value'], comp_ev_equity, comp_pe_equity,
            weight_dcf, weight_ev, weight_pe,
        )
        out[name] = {
            'wacc':                  p['wacc'],
            'terminal_growth':       p['terminal_growth'],
            'growth_y1':             p['growth_y1'],
            'dcf_equity_value':      proj['dcf_equity_value'],
            'dcf_price_per_share':   proj['dcf_price_per_share'],
            'blended_equity_value':  blended_equity,
            'blended_price_per_share': blended_equity / shares if shares > 0 else 0.0,
        }

    base_eq = out['base']['blended_equity_value']
    if base_eq > 0:
        out['spread_pct'] = round(
            (out['bull']['blended_equity_value'] - out['bear']['blended_equity_value']) / base_eq * 100,
            2,
        )
    else:
        out['spread_pct'] = None

    out['perturbation_axes'] = {
        'wacc_delta_bp':     int(WACC_DELTA * 10000),
        'terminal_g_delta_bp': int(TERMINAL_GROWTH_DELTA * 10000),
        'growth_y1_factor':  [GROWTH_Y1_FACTOR_BEAR, GROWTH_Y1_FACTOR_BULL],
    }
    return out
