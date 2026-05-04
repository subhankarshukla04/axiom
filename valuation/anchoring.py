"""
Phase 3 — analyst-anchor kill switch.

The audit's ruling on analyst anchoring (Problem 5):
    "If the model has signal, use it; if not, remove the ML path. Don't both."

Sell-side analyst targets have well-documented biases (anchoring, optimism,
herding) and represent prior-quarter consensus, not ground truth. Blending
70% analyst into STORY-stock outputs effectively publishes a discounted
Wall-Street consensus and labels it ML.

Phase 3 default behaviour: `apply_analyst_anchor` is a NO-OP unless
`AXIOM_USE_ANALYST_ANCHOR=1` is set. Production deployments that haven't yet
re-validated with the unanchored path can keep the legacy blend by setting
the env var. New runs publish the unanchored model output by default.

`apply_sanity_guardrail` is unchanged — that's a defensive bound, not a blend,
and protects against absurd model outputs (4× analyst, 10× current price).
"""
import os
from typing import Optional, Tuple

ANCHOR_ENV = 'AXIOM_USE_ANALYST_ANCHOR'

_ANCHOR_WEIGHTS = {
    'STORY':                 0.70,
    'HYPERGROWTH':           0.20,
    'GROWTH_TECH':           0.15,
    'DISTRESSED':            0.20,
    'CYCLICAL':              0.10,
    'STABLE_VALUE':          0.15,
    'STABLE_VALUE_LOWGROWTH': 0.15,
}


def _anchor_enabled() -> bool:
    return os.getenv(ANCHOR_ENV, '0') == '1'


def apply_sanity_guardrail(final_price: float, analyst_target: Optional[float],
                           current_price: Optional[float]) -> Tuple[float, bool]:
    flagged = False

    if analyst_target and analyst_target > 0:
        if final_price > analyst_target * 4.0:
            final_price = analyst_target * 0.90
            flagged = True
        elif final_price < analyst_target * 0.25:
            final_price = analyst_target * 0.70
            flagged = True

    if current_price and current_price > 0 and not flagged:
        if final_price > current_price * 10.0:
            final_price = current_price * 1.10
            flagged = True

    return final_price, flagged


def apply_analyst_anchor(model_price: float, analyst_target: Optional[float],
                         company_type: str, company_data: dict = None) -> float:
    """Phase 3 default: identity (no anchoring). Set AXIOM_USE_ANALYST_ANCHOR=1
    to restore the legacy blend.

    The `_forced_anchor_weight` company-data flag (set by `valuation.pipeline`
    for non-USD reporters) still wins when the kill switch is enabled — that
    one specific guard against FX-translation noise survives.
    """
    if not _anchor_enabled():
        return model_price

    if not analyst_target or analyst_target <= 0:
        return model_price

    if company_data and company_data.get('_forced_anchor_weight'):
        anchor_weight = company_data['_forced_anchor_weight']
    else:
        anchor_weight = _ANCHOR_WEIGHTS.get(company_type, 0.15)

    return (1 - anchor_weight) * model_price + anchor_weight * analyst_target
