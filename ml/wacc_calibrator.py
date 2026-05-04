"""
WACC calibration model — learns implied WACC from analyst consensus prices
via reverse DCF, then trains a GBT regressor on company features.

The model predicts the WACC that makes our DCF output match analyst consensus,
replacing all hardcoded sector floors with a data-driven approach.

Train:  python3 -m ml.wacc_calibrator
"""
import json
import logging
import os
import pickle
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)
_BASE = os.path.dirname(os.path.dirname(__file__))
WACC_MODEL_PATH = os.path.join(_BASE, 'ml_wacc_model.pkl')
WACC_META_PATH  = os.path.join(_BASE, 'ml_wacc_model_metadata.json')


def _sector_to_int(tag: str) -> int:
    try:
        from valuation._config import SUBSECTOR_MULT
        tags = sorted(SUBSECTOR_MULT.keys())
        return tags.index(tag)
    except Exception:
        return 0


def build_features(company_data: dict) -> Optional[np.ndarray]:
    """6-feature vector for WACC prediction."""
    try:
        beta     = float(company_data.get('beta') or 1.0)
        debt     = float(company_data.get('debt') or 0)
        cash     = float(company_data.get('cash') or 0)
        ebitda   = float(company_data.get('ebitda') or 1)
        mkt_cap  = float(company_data.get('market_cap_estimate') or 1e9)
        op_inc   = float(company_data.get('operating_income') or 0)
        interest = float(company_data.get('interest_expense') or 0)
        revenue  = float(company_data.get('revenue') or 1)
        tag      = str(company_data.get('sub_sector_tag') or '')

        nd_ebitda = (debt - cash) / max(abs(ebitda), 1)
        ebitda_margin = ebitda / max(revenue, 1)
        if interest != 0:
            interest_coverage = max(-5.0, min(20.0, op_inc / abs(interest)))
        else:
            interest_coverage = 10.0
        log_mkt    = np.log(max(mkt_cap, 1e6))
        sector_int = _sector_to_int(tag)

        return np.array([beta, nd_ebitda, ebitda_margin, log_mkt,
                         interest_coverage, sector_int], dtype=float)
    except Exception as e:
        logger.debug('WACC feature build failed: %s', e)
        return None


def compute_implied_wacc(company_id: int, analyst_price: float,
                          valuation_service,
                          min_wacc: float = 0.03,
                          max_wacc: float = 0.25) -> Optional[float]:
    """
    Binary-search for the WACC that makes our DCF output equal analyst_price.
    Returns None if the search fails or the analyst signal is too weak.
    """
    from scipy.optimize import brentq

    company_data = valuation_service.fetch_company_data(company_id)
    if not company_data:
        return None

    current_price = float(company_data.get('market_cap_estimate') or 0)
    shares = float(company_data.get('shares_outstanding') or 1)
    mkt_price = current_price / shares if shares > 0 else 0

    # Skip if analyst target is within 5% of market (no meaningful calibration signal)
    if mkt_price > 0 and abs(analyst_price / mkt_price - 1) < 0.05:
        return None

    def dcf_diff(wacc):
        patched = dict(company_data)
        patched['_ml_wacc_override'] = wacc
        try:
            result = valuation_service.run_valuation(patched)
            if result:
                return float(result.get('dcf_price_per_share') or 0) - analyst_price
        except Exception:
            pass
        return 0.0

    try:
        low_val  = dcf_diff(min_wacc)
        high_val = dcf_diff(max_wacc)
        # brentq requires opposite signs
        if low_val * high_val > 0:
            return None
        implied = brentq(dcf_diff, min_wacc, max_wacc, xtol=0.001, maxiter=30)
        if 0.04 <= implied <= 0.20:
            return float(implied)
    except (ValueError, RuntimeError):
        pass
    return None


def train(min_samples: int = 30):
    """
    Collect implied WACCs for all companies with analyst targets, train GBT regressor.
    Falls back gracefully if not enough data.
    """
    import sys
    sys.path.insert(0, _BASE)
    from app import get_db_connection, valuation_service
    from sklearn.ensemble import GradientBoostingRegressor
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import cross_val_score

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT c.id, c.ticker, vr.analyst_target, vr.current_price
        FROM companies c
        JOIN valuation_results vr ON c.id = vr.company_id
        WHERE vr.analyst_target IS NOT NULL
          AND vr.analyst_target > 0
          AND vr.current_price > 0
        ORDER BY c.ticker
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    print(f'Computing implied WACCs for {len(rows)} companies with analyst targets...')
    X, y, labels = [], [], []

    for r in rows:
        cd = valuation_service.fetch_company_data(r['id'])
        if not cd:
            continue
        feat = build_features(cd)
        if feat is None:
            continue
        implied = compute_implied_wacc(r['id'], float(r['analyst_target']), valuation_service)
        if implied is None:
            continue
        X.append(feat)
        y.append(implied)
        labels.append(r['ticker'])
        print(f"  {r['ticker']}: implied WACC = {implied:.2%}")

    if len(X) < min_samples:
        print(f'Only {len(X)} samples — need {min_samples} to train reliably. '
              f'Model not saved; will use CAPM fallback.')
        return None

    X_arr, y_arr = np.array(X), np.array(y)
    pipe = Pipeline([
        ('scaler', StandardScaler()),
        ('model', GradientBoostingRegressor(
            n_estimators=200, max_depth=4, learning_rate=0.05,
            subsample=0.8, random_state=42,
        )),
    ])
    pipe.fit(X_arr, y_arr)

    n_cv = min(5, max(2, len(X_arr) // 5))
    scores = cross_val_score(pipe, X_arr, y_arr, cv=n_cv,
                             scoring='neg_mean_absolute_error')
    cv_mae = float(-scores.mean())

    with open(WACC_MODEL_PATH, 'wb') as f:
        pickle.dump(pipe, f)
    with open(WACC_META_PATH, 'w') as f:
        json.dump({
            'n_samples': len(X),
            'cv_mae':    round(cv_mae, 4),
            'feature_names': ['beta', 'nd_ebitda', 'ebitda_margin',
                               'log_mkt', 'interest_coverage', 'sector_int'],
            'tickers': labels,
        }, f, indent=2)

    print(f'\nWACC model trained — {len(X)} samples, CV MAE = {cv_mae:.4f} ({cv_mae*100:.2f}pp)')
    return pipe


def predict(company_data: dict) -> Optional[float]:
    """Predict WACC. Returns None if model unavailable (CAPM fallback used)."""
    if not os.path.exists(WACC_MODEL_PATH):
        return None
    try:
        with open(WACC_MODEL_PATH, 'rb') as f:
            pipe = pickle.load(f)
        feat = build_features(company_data)
        if feat is None:
            return None
        predicted = float(pipe.predict([feat])[0])
        return max(0.04, min(0.20, predicted))
    except Exception as e:
        logger.debug('WACC prediction failed: %s', e)
        return None


if __name__ == '__main__':
    train()
