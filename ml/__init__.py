"""
AXIOM ML layer — the actually-learned-from-data parts.

This package now holds *only* code that is trained on prediction history:
  - calibrator.py      — GBM correction model (trained from prediction_log.jsonl)
  - walk_forward.py    — walk-forward training pipeline
  - backtest.py        — historical regression backtest harness
  - accuracy_report.py — post-hoc metrics from prediction log
  - monitor.py         — live monitoring + auto-retrain
  - log.py             — prediction logging (writes to prediction_log.jsonl)

Heuristic / multiples-based valuation logic moved to `valuation_app/valuation/`
in Phase 1. Do not add hardcoded sector tables, multiples, or anchor weights
here — those belong in `valuation/config/*.json`.
"""
from ml.calibrator import apply_ml_correction, train_calibration_model, ML_MODEL_PATH
from ml.log import log_prediction, PREDICTION_LOG_PATH
from ml.backtest import run_backtest

MIN_TRAINING_SAMPLES = 15
