"""
AXIOM valuation engine — single import surface for all callers.

This module re-exports both layers:
  - heuristic / multiples-based valuation  → `valuation_app/valuation/`
  - learned ML correction (GBM)            → `valuation_app/ml/`

Honest framing: the heuristic layer does most of the work. The ML layer is a
post-hoc correction trained on prior prediction errors. See README.md for the
full description, and HARDCODED_VALUES.md for the inventory of magic numbers
in the heuristic layer.

This file replaces the old `ml_engine.py` shim (renamed in Phase 1) — calling
the whole thing "ml" misrepresented what the system is.
"""
from valuation import (
    calibrate,
    run_alternative_model, bank_model, reit_model, growth_loss_model,
    apply_analyst_anchor, apply_sanity_guardrail,
    get_blend_weights, get_multiples, smart_ebitda, normalize_capex,
    get_sub_sector_tag, classify_company,
    TICKER_TAG_MAP, SUBSECTOR_MULT, CYCLICAL_TAGS, SECULAR_DECLINE_TAGS,
    TERMINAL_GROWTH_BY_TAG, TERMINAL_GROWTH_DEFAULT,
    SECTOR_CAPEX_NORM, CAPEX_NORM_DEFAULT,
    SECTOR_PB, TICKER_PB, SECTOR_PFFO, TICKER_PFFO,
    BLEND_WEIGHTS,
)
from ml import (
    apply_ml_correction,
    train_calibration_model,
    log_prediction,
    run_backtest,
    ML_MODEL_PATH,
    PREDICTION_LOG_PATH,
    MIN_TRAINING_SAMPLES,
)
