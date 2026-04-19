"""
LBO Analysis Engine
Standard PE-style model: entry multiple, leverage, 5-year hold,
debt paydown from FCF, exit at multiple → IRR + MOIC.
"""
import logging
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class LBOInputs:
    entry_ev_ebitda: float = 10.0
    entry_ebitda: float = 1000.0
    debt_to_ebitda: float = 5.0
    interest_rate: float = 0.075
    revenue_growth: List[float] = field(default_factory=lambda: [0.08, 0.07, 0.06, 0.05, 0.05])
    ebitda_margin_entry: float = 0.20
    ebitda_margin_exit: float = 0.22
    exit_ev_ebitda: float = 10.0
    hold_period: int = 5
    tax_rate: float = 0.25
    capex_pct_revenue: float = 0.03
    working_capital_pct: float = 0.02


@dataclass
class LBOResult:
    irr: Optional[float]
    moic: Optional[float]
    entry_ev: float
    entry_equity: float
    exit_ev: float
    exit_equity: float
    debt_paydown_schedule: List[dict]
    sensitivity_grid: dict
    irr_signal: str
    computed_at: str

    def to_dict(self) -> dict:
        return {
            'irr': round(self.irr * 100, 2) if self.irr else None,
            'moic': round(self.moic, 2) if self.moic else None,
            'entry_ev': round(self.entry_ev, 1),
            'entry_equity': round(self.entry_equity, 1),
            'exit_ev': round(self.exit_ev, 1),
            'exit_equity': round(self.exit_equity, 1),
            'debt_paydown_schedule': self.debt_paydown_schedule,
            'sensitivity_grid': self.sensitivity_grid,
            'irr_signal': self.irr_signal,
            'computed_at': self.computed_at,
        }


def _compute_irr(cash_flows: List[float]) -> Optional[float]:
    try:
        import numpy_financial as npf
        irr = npf.irr(cash_flows)
        if irr is not None and irr == irr:  # not NaN
            return float(irr)
    except ImportError:
        pass

    def npv(rate, cfs):
        return sum(cf / (1 + rate) ** t for t, cf in enumerate(cfs))

    def npv_deriv(rate, cfs):
        return sum(-t * cf / (1 + rate) ** (t + 1) for t, cf in enumerate(cfs))

    rate = 0.20
    for _ in range(100):
        try:
            nv = npv(rate, cash_flows)
            nd = npv_deriv(rate, cash_flows)
            if abs(nd) < 1e-12:
                break
            rate = rate - nv / nd
            if abs(nv) < 1e-6:
                return rate
        except Exception:
            break
    return rate if 0.0 <= rate <= 5.0 else None


def run_lbo(inputs: LBOInputs) -> LBOResult:
    entry_ev = inputs.entry_ev_ebitda * inputs.entry_ebitda
    entry_debt = inputs.debt_to_ebitda * inputs.entry_ebitda
    entry_equity = entry_ev - entry_debt

    if entry_equity <= 0:
        raise ValueError(f'Entry equity is negative: EV={entry_ev:.0f}, Debt={entry_debt:.0f}')

    revenue = inputs.entry_ebitda / max(inputs.ebitda_margin_entry, 0.01)
    revenues = []
    for g in inputs.revenue_growth[:inputs.hold_period]:
        revenue = revenue * (1 + g)
        revenues.append(revenue)

    margin_step = (inputs.ebitda_margin_exit - inputs.ebitda_margin_entry) / inputs.hold_period
    ebitdas = [
        revenues[i] * (inputs.ebitda_margin_entry + margin_step * (i + 1))
        for i in range(inputs.hold_period)
    ]

    remaining_debt = entry_debt
    schedule = []

    for yr in range(1, inputs.hold_period + 1):
        idx = yr - 1
        ebitda_yr = ebitdas[idx]
        rev_yr = revenues[idx]
        interest = remaining_debt * inputs.interest_rate
        da = rev_yr * 0.05
        ebit = ebitda_yr - da
        nopat = ebit * (1 - inputs.tax_rate)
        capex = rev_yr * inputs.capex_pct_revenue
        delta_wc = rev_yr * inputs.working_capital_pct
        fcf = nopat + da - capex - delta_wc
        paydown = max(0, min(fcf - interest, remaining_debt))
        remaining_debt = max(0, remaining_debt - paydown)
        schedule.append({
            'year': yr,
            'revenue': round(rev_yr, 1),
            'ebitda': round(ebitda_yr, 1),
            'interest': round(interest, 1),
            'fcf': round(fcf, 1),
            'paydown': round(paydown, 1),
            'remaining_debt': round(remaining_debt, 1),
        })

    exit_ebitda = ebitdas[-1]
    exit_ev = inputs.exit_ev_ebitda * exit_ebitda
    exit_equity = max(0, exit_ev - remaining_debt)

    cash_flows = [-entry_equity] + [0] * (inputs.hold_period - 1) + [exit_equity]
    irr = _compute_irr(cash_flows)
    moic = exit_equity / entry_equity if entry_equity > 0 else None

    if irr is None:
        irr_signal = 'unknown'
    elif irr >= 0.25:
        irr_signal = 'strong'
    elif irr >= 0.15:
        irr_signal = 'acceptable'
    else:
        irr_signal = 'weak'

    exit_multiples = [8.0, 9.0, 10.0, 12.0, 14.0]
    leverage_levels = [3.0, 4.0, 5.0, 6.0, 7.0]
    grid = {'exit_multiples': exit_multiples, 'leverage_levels': leverage_levels, 'irr_matrix': []}

    for lev in leverage_levels:
        row = []
        for em in exit_multiples:
            try:
                test_ee = (inputs.entry_ev_ebitda * inputs.entry_ebitda) - (lev * inputs.entry_ebitda)
                if test_ee <= 0:
                    row.append({'irr': None, 'signal': 'invalid'})
                    continue
                # Approximate exit with scaled remaining debt
                debt_ratio = lev / max(inputs.debt_to_ebitda, 0.01)
                scaled_rem = remaining_debt * debt_ratio
                test_exit_eq = max(0, em * exit_ebitda - scaled_rem)
                test_cfs = [-test_ee] + [0] * (inputs.hold_period - 1) + [test_exit_eq]
                test_irr = _compute_irr(test_cfs)
                if test_irr is None:
                    row.append({'irr': None, 'signal': 'unknown'})
                elif test_irr >= 0.25:
                    row.append({'irr': round(test_irr * 100, 1), 'signal': 'strong'})
                elif test_irr >= 0.15:
                    row.append({'irr': round(test_irr * 100, 1), 'signal': 'acceptable'})
                else:
                    row.append({'irr': round(test_irr * 100, 1), 'signal': 'weak'})
            except Exception:
                row.append({'irr': None, 'signal': 'error'})
        grid['irr_matrix'].append(row)

    return LBOResult(
        irr=irr, moic=moic, entry_ev=entry_ev, entry_equity=entry_equity,
        exit_ev=exit_ev, exit_equity=exit_equity,
        debt_paydown_schedule=schedule, sensitivity_grid=grid,
        irr_signal=irr_signal, computed_at=datetime.utcnow().isoformat(),
    )
