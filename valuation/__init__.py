"""
AXIOM heuristic valuation layer.

This package holds the multiples-based / lookup-driven valuation logic.
Despite its old name (`ml/`), none of this code is learned from data — every
constant lives in `valuation/config/*.json` and was hand-picked.

Real ML (the GBM correction model and walk-forward trainer) lives in
`valuation_app/ml/` alongside this package.

Phase 1 split: see HARDCODED_VALUES.md for the inventory of magic numbers
that this package exposes and that Phase 2 will replace with live peer comps.
"""
from valuation.pipeline import calibrate
from valuation.alt_models import (
    run_alternative_model, bank_model, reit_model, growth_loss_model,
)
from valuation.anchoring import apply_analyst_anchor, apply_sanity_guardrail
from valuation.normalizers import (
    get_blend_weights, get_multiples, smart_ebitda, normalize_capex,
)
from valuation.tagging import get_sub_sector_tag, classify_company
from valuation._config import (
    TICKER_TAG_MAP, SUBSECTOR_MULT, CYCLICAL_TAGS, SECULAR_DECLINE_TAGS,
    TERMINAL_GROWTH_BY_TAG, TERMINAL_GROWTH_DEFAULT,
    SECTOR_CAPEX_NORM, CAPEX_NORM_DEFAULT,
    SECTOR_PB, TICKER_PB, SECTOR_PFFO, TICKER_PFFO,
    BLEND_WEIGHTS,
)
