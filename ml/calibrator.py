"""
Phase 3 — ML correction layer fixes.

What Phase 3 changes:
1. **Label is now `log(actual / predicted)`** instead of `clip(ratio, 0.2, 5.0)`.
   The clip censored exactly the cases the model exists to find — large
   mispricings. Log space is symmetric (over- and under-prediction equally
   weighted), additive across horizons, and unbiased in expectation.

2. **TimeSeriesSplit (5 folds) + grid search** over (max_depth, n_estimators,
   learning_rate). Replaces single 80/20 chronological split with no tuning.

3. **Richer metrics**: log-MAE, directional accuracy (% with correct error
   sign), rank-IC (Spearman corr between predicted and actual log-error).
   Reported on holdout fold; written into model metadata.

4. **Inference is framework-aware.** Old models (`framework: sklearn_pipeline_v2`)
   used a clipped-ratio target — interpret raw output as a multiplier.
   New models (`framework: sklearn_pipeline_v3_log`) use log-error — apply
   `exp(prediction)`. Defensive sanity clamp narrowed to log-space ±ln(3).
"""
import json
import logging
import math
import os
import pickle
from datetime import datetime

from valuation._config import SUBSECTOR_MULT
from ml.log import PREDICTION_LOG_PATH

logger = logging.getLogger(__name__)

ML_MODEL_PATH     = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'ml_calibration_model.pkl')
ML_METADATA_PATH  = ML_MODEL_PATH.replace('.pkl', '_metadata.json')
MIN_TRAINING_SAMPLES = 15

FRAMEWORK_LEGACY = 'sklearn_pipeline_v2'        # clipped-ratio target
FRAMEWORK_LOG    = 'sklearn_pipeline_v3_log'    # log(actual/predicted) target

# Defensive sanity clamp on inference multiplier. log-space ±ln(3) ≈ multiplier
# in [0.33, 3.0]. Wide enough that the model can flag genuine 2× mispricings,
# narrow enough that one bad row can't crash a portfolio backtest.
LOG_CORRECTION_BOUND = math.log(3.0)

_COMPANY_TYPES = ['DISTRESSED', 'STORY', 'HYPERGROWTH', 'GROWTH_TECH',
                  'CYCLICAL', 'STABLE_VALUE', 'STABLE_VALUE_LOWGROWTH']
_EBITDA_METHODS  = ['em:single', 'em:zero', 'em:cyc3yr', 'em:secular_decline',
                    'em:recent', 'em:trend', 'em:3yavg', 'backtest']
_MARKET_REGIMES  = ['risk_on', 'transition', 'risk_off', 'unknown']

# Sector vol priors for inference — real vol computed during training
_TAG_VOL_DEFAULT = {
    'biotech_clinical': 0.55,  'growth_loss': 0.50,   'ev_auto': 0.45,
    'crypto_proxy': 0.60,      'cloud_saas': 0.35,    'rule40_saas': 0.35,
    'semiconductor': 0.32,     'consumer_internet': 0.30,
    'enterprise_software': 0.28, 'cloud_software': 0.30,
    'medical_device': 0.25,    'pharma_largecap': 0.22,
    'health_insurance': 0.20,  'commercial_bank': 0.22,
    'investment_bank': 0.28,   'oil_gas_major': 0.25,  'oil_gas_mid': 0.30,
    'auto_legacy': 0.22,       'defense': 0.18,
    'retail_discount': 0.22,   'retail_ecomm': 0.28,
    'industrial_cong': 0.20,   'telecom': 0.15,
    'consumer_staples': 0.15,  'utility_regulated': 0.12,
    'reit_office': 0.20,       'reit_residential': 0.18,
    'pc_insurance': 0.18,      'pharma': 0.22,
}
_VOL_DEFAULT = 0.25


def _tag_to_int(tag: str) -> int:
    tags = sorted(SUBSECTOR_MULT.keys())
    try:
        return tags.index(tag)
    except ValueError:
        return len(tags)


def _type_to_int(t: str) -> int:
    try:
        return _COMPANY_TYPES.index(t)
    except ValueError:
        return len(_COMPANY_TYPES)


def _method_to_int(m: str) -> int:
    try:
        return _EBITDA_METHODS.index(m)
    except ValueError:
        return len(_EBITDA_METHODS)


def _regime_to_int(r: str) -> int:
    try:
        return _MARKET_REGIMES.index(r)
    except ValueError:
        return len(_MARKET_REGIMES)


def _load_prediction_log() -> list:
    records = []
    if not os.path.exists(PREDICTION_LOG_PATH):
        return records
    with open(PREDICTION_LOG_PATH) as f:
        for line in f:
            try:
                records.append(json.loads(line.strip()))
            except Exception:
                pass
    return records


def _build_features(r: dict) -> list:
    """7-feature vector: [tag_int, type_int, wacc, growth_y1, ebitda_method_int, analyst_ratio, regime_int]"""
    predicted = float(r.get('predicted_price', 1) or 1)
    analyst   = float(r.get('analyst_target', 0) or 0)
    analyst_ratio = (analyst / predicted) if predicted > 0 and analyst > 0 else 1.0
    return [
        _tag_to_int(r.get('sub_sector_tag', '')),
        _type_to_int(r.get('company_type', '')),
        float(r.get('wacc', 0.10) or 0.10),
        float(r.get('growth_y1', 0.05) or 0.05),
        _method_to_int(r.get('ebitda_method', '')),
        analyst_ratio,
        _regime_to_int(r.get('market_regime', 'unknown')),
    ]


def _build_features_extended(r: dict, horizon_days: int = 365, month: int = None,
                               include_etf_momentum: bool = False) -> list:
    """10- or 11-feature vector for walk-forward models.

    10 features = 7 base + horizon_days + month_of_pred + volatility_30d.
    11 features = 10 + etf_momentum_90d (neutral 0.0 at inference; the
    sector-ETF momentum is only knowable historically during training).
    """
    if month is None:
        month = datetime.utcnow().month
    tag = r.get('sub_sector_tag', '')
    vol = _TAG_VOL_DEFAULT.get(tag, _VOL_DEFAULT)
    base = _build_features(r) + [float(horizon_days), float(month), vol]
    if include_etf_momentum:
        base.append(0.0)   # etf_momentum_90d unknown at inference
    return base


def _directional_accuracy(y_true, y_pred) -> float:
    """% of predictions with correct sign of log-error (i.e. correctly says
    over- vs under-priced). Treats |y| < 0.02 as 'flat' and excludes from denom.
    """
    import numpy as np
    mask = np.abs(y_true) >= 0.02
    if mask.sum() == 0:
        return float('nan')
    return float(np.mean(np.sign(y_pred[mask]) == np.sign(y_true[mask])))


def _rank_ic(y_true, y_pred) -> float:
    """Spearman correlation between predicted and actual log-error.
    The audit calls this out: rank-IC matters more than MAE for a ranker.
    """
    try:
        from scipy.stats import spearmanr
        rho, _ = spearmanr(y_pred, y_true)
        return float(rho) if rho is not None else float('nan')
    except Exception:
        # numpy fallback — Pearson on ranks (≈ Spearman)
        import numpy as np
        if len(y_true) < 3:
            return float('nan')
        rt = np.argsort(np.argsort(y_true))
        rp = np.argsort(np.argsort(y_pred))
        return float(np.corrcoef(rt, rp)[0, 1])


def _build_pipeline(max_depth: int, n_estimators: int, learning_rate: float):
    """Phase 3 grid-searchable pipeline. Cat/num column split unchanged from v2."""
    from sklearn.pipeline import Pipeline
    from sklearn.compose import ColumnTransformer
    from sklearn.preprocessing import OrdinalEncoder, StandardScaler
    from sklearn.ensemble import GradientBoostingRegressor

    cat_cols = [0, 1, 4, 6]   # tag_int, type_int, ebitda_method_int, regime_int
    num_cols = [2, 3, 5]      # wacc, growth_y1, analyst_ratio

    return Pipeline([
        ('features', ColumnTransformer([
            ('cat', OrdinalEncoder(handle_unknown='use_encoded_value', unknown_value=-1), cat_cols),
            ('num', StandardScaler(), num_cols),
        ])),
        ('model', GradientBoostingRegressor(
            n_estimators=n_estimators,
            max_depth=max_depth,
            learning_rate=learning_rate,
            subsample=0.8,
            random_state=42,
        )),
    ])


def train_calibration_model() -> bool:
    """Phase 3: log-error label + TimeSeriesSplit grid search + rank-IC.

    Replaces the single 80/20 chronological split + no-tuning approach.
    Backwards compatible: writes `framework: sklearn_pipeline_v3_log` so
    `apply_ml_correction` knows to apply `exp()` at inference time.
    """
    try:
        import numpy as np
        from sklearn.model_selection import TimeSeriesSplit
    except ImportError:
        logger.warning('scikit-learn not installed — skipping ML training')
        return False

    records = _load_prediction_log()
    labeled = [r for r in records
               if r.get('actual_price_365d') and r.get('predicted_price')
               and r['actual_price_365d'] > 0 and r['predicted_price'] > 0]
    labeled.sort(key=lambda r: r.get('predicted_at', ''))

    if len(labeled) < MIN_TRAINING_SAMPLES:
        logger.info(f'Only {len(labeled)} labeled samples — need {MIN_TRAINING_SAMPLES}')
        return False

    X = np.array([_build_features(r) for r in labeled])
    # Phase 3: log-error label, NO clip. Symmetric, additive, unbiased.
    y = np.array([math.log(r['actual_price_365d'] / r['predicted_price']) for r in labeled])

    # Final 20% as untouched holdout for honest reporting; the front 80% is
    # used by TimeSeriesSplit for CV/grid search.
    split    = int(len(X) * 0.80)
    X_dev,   X_holdout = X[:split], X[split:]
    y_dev,   y_holdout = y[:split], y[split:]

    # Grid: small, deliberate. Sample size doesn't justify a large search.
    grid = [
        {'max_depth': d, 'n_estimators': n, 'learning_rate': lr}
        for d  in (2, 3, 4)
        for n  in (50, 100, 200)
        for lr in (0.03, 0.05, 0.10)
    ]

    n_splits = max(2, min(5, len(X_dev) // 30))   # need ≥30 rows per fold
    tscv     = TimeSeriesSplit(n_splits=n_splits)

    best_cfg, best_score = None, float('inf')
    for cfg in grid:
        fold_maes = []
        for tr_idx, va_idx in tscv.split(X_dev):
            if len(va_idx) == 0:
                continue
            pipe = _build_pipeline(**cfg)
            pipe.fit(X_dev[tr_idx], y_dev[tr_idx])
            fold_maes.append(float(np.mean(np.abs(pipe.predict(X_dev[va_idx]) - y_dev[va_idx]))))
        if not fold_maes:
            continue
        cv_mae = float(np.mean(fold_maes))
        if cv_mae < best_score:
            best_score, best_cfg = cv_mae, cfg

    if best_cfg is None:
        logger.warning('Grid search produced no usable fold — falling back to default config')
        best_cfg = {'max_depth': 3, 'n_estimators': 100, 'learning_rate': 0.05}
        best_score = float('nan')

    # Refit on full dev set with best config, evaluate on untouched holdout
    pipeline = _build_pipeline(**best_cfg)
    pipeline.fit(X_dev, y_dev)

    if len(X_holdout) > 0:
        y_hat       = pipeline.predict(X_holdout)
        mae_holdout = float(np.mean(np.abs(y_hat - y_holdout)))
        dir_acc     = _directional_accuracy(y_holdout, y_hat)
        rank_ic     = _rank_ic(y_holdout, y_hat)
    else:
        mae_holdout = dir_acc = rank_ic = float('nan')

    with open(ML_MODEL_PATH, 'wb') as f:
        pickle.dump(pipeline, f)

    metadata = {
        'trained_at':       datetime.utcnow().isoformat(),
        'framework':        FRAMEWORK_LOG,
        'label':            'log(actual_price_365d / predicted_price)',
        'n_samples':        len(labeled),
        'n_dev':            len(X_dev),
        'n_holdout':        len(X_holdout),
        'cv_n_splits':      n_splits,
        'best_config':      best_cfg,
        'cv_log_mae':       round(best_score, 4) if best_score == best_score else None,  # NaN-safe
        'holdout_log_mae':  round(mae_holdout, 4) if mae_holdout == mae_holdout else None,
        'holdout_dir_acc':  round(dir_acc, 4) if dir_acc == dir_acc else None,
        'holdout_rank_ic':  round(rank_ic, 4) if rank_ic == rank_ic else None,
        'features':         ['tag_int', 'type_int', 'wacc', 'growth_y1', 'ebitda_method_int', 'analyst_ratio', 'regime_int'],
        'n_features':       7,
    }
    with open(ML_METADATA_PATH, 'w') as f:
        json.dump(metadata, f, indent=2)

    logger.info(
        'ML pipeline trained: n=%d, best=%s, holdout log-MAE=%.4f dir-acc=%.3f rank-IC=%.3f',
        len(labeled), best_cfg, mae_holdout, dir_acc, rank_ic,
    )
    return True


def apply_ml_correction(predicted_price: float, company_data: dict) -> float:
    """Apply trained calibrator to a predicted price.

    Phase 3 framework awareness:
      - `sklearn_pipeline_v3_log` (new): raw output is `log(actual/predicted)`,
        applied via `predicted * exp(output)`, clamped to ±ln(3) for safety.
      - `sklearn_pipeline_v2` (legacy): raw output is a clipped ratio,
        applied as `predicted * output`. Kept identically to old behaviour
        to avoid changing predictions of already-shipped models.
    """
    tag   = company_data.get('sub_sector_tag', '')
    ctype = company_data.get('company_type', '')

    if os.path.exists(ML_MODEL_PATH):
        try:
            import numpy as np
            with open(ML_MODEL_PATH, 'rb') as f:
                pipeline = pickle.load(f)
            from ml.log import _get_market_regime

            n_features = 7
            framework  = FRAMEWORK_LEGACY
            if os.path.exists(ML_METADATA_PATH):
                try:
                    with open(ML_METADATA_PATH) as _mf:
                        meta       = json.load(_mf)
                        n_features = meta.get('n_features', 7)
                        framework  = meta.get('framework', FRAMEWORK_LEGACY)
                except Exception:
                    pass

            record = {
                'sub_sector_tag':  tag,
                'company_type':    ctype,
                'wacc':            company_data.get('wacc', 0.10),
                'growth_y1':       company_data.get('growth_rate_y1', 0.05),
                'ebitda_method':   company_data.get('ebitda_method', ''),
                'analyst_target':  company_data.get('analyst_target', 0),
                'predicted_price': predicted_price,
                'market_regime':   _get_market_regime(),
            }
            if n_features == 11:
                feat = _build_features_extended(record, include_etf_momentum=True)
            elif n_features == 10:
                feat = _build_features_extended(record)
            elif n_features == 9:
                feat = _build_features(record) + [float(365), float(datetime.utcnow().month)]
            else:
                feat = _build_features(record)

            raw = float(pipeline.predict(np.array([feat]))[0])

            if framework == FRAMEWORK_LOG:
                clamped = max(-LOG_CORRECTION_BOUND, min(raw, LOG_CORRECTION_BOUND))
                return predicted_price * math.exp(clamped)

            # Legacy ratio path (clipped at training time, mirror old defensive clamp)
            correction = max(0.4, min(raw, 2.0))
            return predicted_price * correction
        except Exception as e:
            logger.warning(f'ML correction failed: {e}')

    if company_data.get('_non_usd_reporting'):
        return predicted_price

    try:
        import sys
        scripts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'scripts')
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from calibration_corrections import get_correction
        return predicted_price * get_correction(tag, ctype)
    except Exception:
        pass

    return predicted_price
