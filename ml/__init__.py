"""
AXIOM ML layer.

  - walk_forward.py      — walk-forward training pipeline (monthly rolling, excess return target)
  - monitor.py           — daily snapshots, weekly evaluation, IC-based reporting, auto-retrain
  - log.py               — prediction logging (writes to prediction_log.jsonl)
  - growth_normalizer.py — yfinance multi-year median growth, writes to company_financials
  - wacc_calibrator.py   — reverse-DCF implied WACC → GBT regressor, replaces CAPM floors
  - company_classifier.py — GBT classifier for company_type from financial features
  - framework_router.py  — detects REITs/banks/neg-FCF companies, skips ML for those
"""
from ml.log import log_prediction, PREDICTION_LOG_PATH
from ml.walk_forward import run as run_walk_forward
from ml.growth_normalizer import run_normalization, compute_median_growth
from ml.wacc_calibrator import (train as train_wacc_model,
                                  predict as predict_wacc)
from ml.company_classifier import (train as train_classifier,
                                     predict as predict_company_type)
from ml.framework_router import classify_framework

MIN_TRAINING_SAMPLES = 50
