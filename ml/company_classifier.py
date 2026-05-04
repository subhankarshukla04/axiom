"""
Company type classifier — learns company_type from existing DB labels
using multiple financial features. Replaces the single-threshold rule
(if g1 > 8% and margin > 0: GROWTH_TECH).

Train:  python3 -m ml.company_classifier
"""
import json
import logging
import os
import pickle
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)
_BASE = os.path.dirname(os.path.dirname(__file__))
CLASSIFIER_PATH = os.path.join(_BASE, 'ml_company_classifier.pkl')
CLASSIFIER_META = os.path.join(_BASE, 'ml_company_classifier_metadata.json')

COMPANY_TYPES = [
    'DISTRESSED', 'STORY', 'HYPERGROWTH', 'GROWTH_TECH',
    'CYCLICAL', 'STABLE_VALUE', 'STABLE_VALUE_LOWGROWTH',
]


def _type_to_int(t: str) -> int:
    try:
        return COMPANY_TYPES.index(t.upper())
    except ValueError:
        return len(COMPANY_TYPES) - 1   # default STABLE_VALUE_LOWGROWTH


def _int_to_type(i: int) -> str:
    i = int(i)
    return COMPANY_TYPES[i] if 0 <= i < len(COMPANY_TYPES) else 'STABLE_VALUE'


def _sector_to_int(tag: str) -> int:
    try:
        from valuation._config import SUBSECTOR_MULT
        tags = sorted(SUBSECTOR_MULT.keys())
        return tags.index(tag)
    except Exception:
        return 0


def build_features(company_data: dict) -> Optional[np.ndarray]:
    """7-feature vector for company type prediction."""
    try:
        g1      = float(company_data.get('growth_rate_y1') or 0)
        g2      = float(company_data.get('growth_rate_y2') or g1)
        g3      = float(company_data.get('growth_rate_y3') or g1)
        ebitda  = float(company_data.get('ebitda') or 1)
        revenue = float(company_data.get('revenue') or 1)
        debt    = float(company_data.get('debt') or 0)
        cash    = float(company_data.get('cash') or 0)
        mkt_cap = float(company_data.get('market_cap_estimate') or 1e9)
        tag     = str(company_data.get('sub_sector_tag') or '')

        ebitda_margin = ebitda / max(revenue, 1)
        nd_ebitda     = (debt - cash) / max(abs(ebitda), 1)
        g_mean        = (g1 + g2 + g3) / 3
        g_trend       = g3 - g1         # positive = growth decelerating
        log_mkt       = np.log(max(mkt_cap, 1e6))
        sector_int    = _sector_to_int(tag)

        return np.array([g1, g_mean, g_trend, ebitda_margin,
                         nd_ebitda, log_mkt, sector_int], dtype=float)
    except Exception:
        return None


def train(min_samples: int = 20):
    """Train on existing company_type labels in DB."""
    import sys
    sys.path.insert(0, _BASE)
    from app import get_db_connection, valuation_service
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import cross_val_score

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT c.id, c.ticker, vr.company_type
        FROM companies c
        JOIN valuation_results vr ON c.id = vr.company_id
        WHERE vr.company_type IS NOT NULL
        ORDER BY c.ticker
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    X, y, labels = [], [], []
    for r in rows:
        cd = valuation_service.fetch_company_data(r['id'])
        if not cd:
            continue
        feat = build_features(cd)
        if feat is None:
            continue
        X.append(feat)
        y.append(_type_to_int(r['company_type']))
        labels.append(r['ticker'])

    if len(X) < min_samples:
        print(f'Only {len(X)} labeled samples — need {min_samples}. '
              f'Classifier not saved; existing rule-based classification kept.')
        return None

    X_arr, y_arr = np.array(X), np.array(y)
    pipe = Pipeline([
        ('scaler', StandardScaler()),
        ('clf', GradientBoostingClassifier(
            n_estimators=200, max_depth=4, learning_rate=0.05,
            subsample=0.8, random_state=42,
        )),
    ])
    pipe.fit(X_arr, y_arr)

    n_cv = min(5, max(2, len(X_arr) // 5))
    scores = cross_val_score(pipe, X_arr, y_arr, cv=n_cv, scoring='accuracy')
    cv_acc = float(scores.mean())

    with open(CLASSIFIER_PATH, 'wb') as f:
        pickle.dump(pipe, f)
    with open(CLASSIFIER_META, 'w') as f:
        json.dump({
            'n_samples':   len(X),
            'cv_accuracy': round(cv_acc, 3),
            'classes':     COMPANY_TYPES,
            'tickers':     labels,
        }, f, indent=2)

    print(f'Company classifier trained — {len(X)} samples, '
          f'CV accuracy = {cv_acc:.1%}')
    return pipe


def predict(company_data: dict) -> Optional[str]:
    """Predict company type. Returns None if model unavailable."""
    if not os.path.exists(CLASSIFIER_PATH):
        return None
    try:
        with open(CLASSIFIER_PATH, 'rb') as f:
            pipe = pickle.load(f)
        feat = build_features(company_data)
        if feat is None:
            return None
        pred = int(pipe.predict([feat])[0])
        return _int_to_type(pred)
    except Exception as e:
        logger.debug('company classifier predict failed: %s', e)
        return None


if __name__ == '__main__':
    train()
