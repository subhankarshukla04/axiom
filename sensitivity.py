"""
2D DCF Sensitivity Table Generator.
Default axes: WACC (x) vs Terminal Growth Rate (y).
Returns color-coded matrix of implied share prices.
"""
import logging
from typing import List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


def _signal(implied_price: float, current_price: float) -> str:
    if current_price <= 0:
        return 'unknown'
    upside = (implied_price - current_price) / current_price
    if upside >= 0.20:
        return 'strong_buy'
    elif upside >= 0.10:
        return 'buy'
    elif upside >= -0.10:
        return 'hold'
    elif upside >= -0.20:
        return 'sell'
    return 'strong_sell'


def _run_dcf(base_inputs: dict, wacc: float, terminal_growth: float) -> Optional[float]:
    try:
        fcfs = base_inputs.get('projected_fcfs', [])
        if not fcfs:
            return None
        shares = base_inputs.get('shares_outstanding', 1)
        net_debt = base_inputs.get('net_debt', 0)
        n = len(fcfs)
        pv_fcfs = sum(fcf / (1 + wacc) ** (t + 1) for t, fcf in enumerate(fcfs))
        terminal_fcf = fcfs[-1] * (1 + terminal_growth)
        if wacc <= terminal_growth:
            return None
        terminal_value = terminal_fcf / (wacc - terminal_growth)
        pv_terminal = terminal_value / (1 + wacc) ** n
        equity_value = (pv_fcfs + pv_terminal) - net_debt
        implied_price = equity_value / shares if shares > 0 else None
        return max(0, implied_price) if implied_price is not None else None
    except Exception as e:
        logger.debug(f'DCF sensitivity error: {e}')
        return None


def compute_sensitivity_table(
    base_inputs: dict,
    current_price: float,
    x_axis_param: str = 'wacc',
    y_axis_param: str = 'terminal_growth',
) -> dict:
    """
    Compute 2D sensitivity table.
    Returns full result dict with x_axis, y_axis, cells, base_case.
    """
    base_wacc = base_inputs.get('wacc', 0.09)
    base_tg = base_inputs.get('terminal_growth', 0.025)

    wacc_values = [0.06, 0.07, 0.08, 0.09, 0.10, 0.12, 0.14]
    tg_values = [0.01, 0.015, 0.02, 0.025, 0.03, 0.035, 0.04]

    if x_axis_param == 'wacc':
        x_values, y_values = wacc_values, tg_values
        x_label, y_label = 'WACC', 'Terminal Growth Rate'
        x_fmt = lambda v: f'{v*100:.0f}%'
        y_fmt = lambda v: f'{v*100:.1f}%'
    else:
        x_values, y_values = tg_values, wacc_values
        x_label, y_label = 'Terminal Growth Rate', 'WACC'
        x_fmt = lambda v: f'{v*100:.1f}%'
        y_fmt = lambda v: f'{v*100:.0f}%'

    cells = []
    base_case = None

    for y_val in y_values:
        row = []
        for x_val in x_values:
            wacc, tg = (x_val, y_val) if x_axis_param == 'wacc' else (y_val, x_val)
            implied = _run_dcf(base_inputs, wacc, tg)
            sig = _signal(implied, current_price) if implied else 'unknown'
            is_base = abs(wacc - base_wacc) < 0.001 and abs(tg - base_tg) < 0.001
            cell = {'value': round(implied, 2) if implied else None, 'signal': sig, 'is_base': is_base}
            if is_base:
                base_case = {'x': x_val, 'y': y_val, 'value': cell['value']}
            row.append(cell)
        cells.append(row)

    return {
        'x_axis': {'label': x_label, 'values': x_values, 'formatted': [x_fmt(v) for v in x_values]},
        'y_axis': {'label': y_label, 'values': y_values, 'formatted': [y_fmt(v) for v in y_values]},
        'cells': cells,
        'current_price': current_price,
        'base_case': base_case,
        'computed_at': datetime.utcnow().isoformat(),
    }
