import logging
from typing import Dict, Optional, Tuple

from valuation._config import (
    CYCLICAL_TAGS, SECULAR_DECLINE_TAGS,
    SUBSECTOR_MULT, SECTOR_CAPEX_NORM, CAPEX_NORM_DEFAULT,
    BLEND_WEIGHTS,
)

logger = logging.getLogger(__name__)


def smart_ebitda(ebitda_history: list, tag: str) -> Tuple[float, str]:
    if not ebitda_history or len(ebitda_history) < 2:
        val = ebitda_history[0] if ebitda_history else 0
        return val, 'em:single'

    eb = [float(x) for x in ebitda_history if x is not None and x != 0]
    if not eb:
        return 0, 'em:zero'

    if tag in CYCLICAL_TAGS:
        return sum(eb[:3]) / len(eb[:3]), 'em:cyc3yr'

    if tag in SECULAR_DECLINE_TAGS:
        return eb[0], 'em:secular_decline'

    if len(eb) < 3:
        return eb[0], 'em:recent'

    improving = eb[0] > eb[1] > eb[2]
    declining = eb[0] < eb[1] < eb[2]

    if improving or declining:
        return eb[0], 'em:trend'

    return sum(eb[:3]) / 3, 'em:3yavg'


def normalize_capex(actual_pct: float, tag: str) -> float:
    norm = SECTOR_CAPEX_NORM.get(tag, CAPEX_NORM_DEFAULT)
    return min(actual_pct, norm)


def get_multiples(
    tag: str,
    company_growth: float,
    ticker: Optional[str] = None,
) -> Tuple[Optional[float], Optional[float]]:
    """Return (EV/EBITDA, P/E) multiples for a company.

    Phase 2: when `ticker` is supplied and `AXIOM_USE_PEER_COMPS` is not '0',
    the live SEC-EDGAR-peer + yfinance + Bayesian-shrinkage path is tried
    first. The hand-curated `subsector_multiples.json` table is now used as
    the *prior* fed into the shrinkage, plus as the fallback when the live
    path fails.

    The (12.0, 20.0) default for unknown sub-sector tags is unchanged — that
    branch will go away when Phase 2 finishes covering all 54 tags.
    """
    entry = SUBSECTOR_MULT.get(tag)
    if not entry:
        return 12.0, 20.0

    base_ev, base_pe, sector_median_g = entry

    # Banks / REITs / insurance — sector tag has null base multiples and is
    # routed through `valuation.alt_models.run_alternative_model` instead.
    if base_ev is None:
        return None, None

    # ── Phase 2: live peer comps (with shrinkage to JSON sector median) ─────
    if ticker:
        try:
            from valuation.peer_comps import get_peer_shrunk_multiples
            ev_live, pe_live, trace = get_peer_shrunk_multiples(
                ticker, base_ev, base_pe, company_growth, sector_median_g,
            )
            if ev_live is not None and pe_live is not None:
                logger.debug('peer-comp ok %s: %s', ticker, trace)
                return ev_live, pe_live
            logger.debug('peer-comp partial/skip %s: %s', ticker, trace.get('peer_comp_status'))
        except Exception as e:
            logger.debug('peer-comp failed for %s: %s', ticker, e)

    # ── Fallback: legacy PEG-style adjustment on JSON multiples ─────────────
    if sector_median_g and sector_median_g > 0 and company_growth and company_growth > 0:
        adj = (company_growth / sector_median_g) ** 0.4
        adj = max(0.5, min(adj, 1.5))
    else:
        adj = 1.0

    return base_ev * adj, base_pe * adj


def get_blend_weights(company_type: str, dcf_value: float) -> Dict[str, float]:
    weights = dict(BLEND_WEIGHTS.get(company_type, BLEND_WEIGHTS['STABLE_VALUE']))

    if dcf_value is not None and dcf_value < 0:
        weights['dcf'] = 0.0
        total = weights['ev'] + weights['pe']
        if total > 0:
            weights['ev'] = weights['ev'] / total
            weights['pe'] = weights['pe'] / total

    return weights
