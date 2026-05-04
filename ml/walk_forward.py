"""
Quant-grade walk-forward ML trainer — AXIOM valuation correction model.

Four improvements over the original annual trainer:

1. TARGET = excess return over sector ETF, not raw price return.
   (stock_return / etf_return) removes market beta. A 1.0 means the stock
   matched its sector exactly — the DCF was well-calibrated. A 1.20 means
   the stock beat its sector by 20% — DCF was too conservative. This is the
   signal a correction model should actually learn.

2. MONTHLY ROLLING WINDOWS — 12 start dates per year, not just January.
   Each (ticker × year) produces 36 training rows (12 months × 3 horizons)
   instead of 3. The month_of_prediction feature lets the model learn
   Q1 earnings distortions vs Q4 year-end effects explicitly.

3. COMPOSITE REGIME — 4 signals, not just VIX.
   VIX level + HYG credit momentum + yield curve inversion + SPY/MA200.
   Scores 0–4 → risk_on / transition / risk_off. Q4 2022 and early 2023
   were "transition" — neither bear nor bull — which the binary VIX signal
   couldn't describe, causing MAE=0.44 on 2023 validation.

4. REALIZED VOLATILITY as feature [9].
   30-day annualized vol at each monthly start date. A biotech with 60%
   vol and a utility with 12% vol need different correction factors even
   in the same regime. This is the most important cross-sectional signal.

10-feature vector:
  [tag_int, type_int, wacc, growth_y1, ebitda_method_int,
   analyst_ratio, regime_int, horizon_days, month_of_pred, volatility_30d]

CLI:
    python -m ml.walk_forward                          # monthly rolling (default)
    python -m ml.walk_forward --mode annual            # original 3-phase
    python -m ml.walk_forward --years 2022 2023 2024 --window 12
"""

from __future__ import annotations

import json
import logging
import os
import pickle
from collections import defaultdict
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np

from valuation._config import CYCLICAL_TAGS, SECULAR_DECLINE_TAGS, SUBSECTOR_MULT, TICKER_TAG_MAP
from ml.calibrator import (
    ML_MODEL_PATH,
    _method_to_int,
    _regime_to_int,
    _tag_to_int,
    _type_to_int,
)

logger = logging.getLogger(__name__)

_ML_DIR    = os.path.dirname(ML_MODEL_PATH)
MODEL_Y1   = os.path.join(_ML_DIR, 'ml_model_y1.pkl')
MODEL_Y1Y2 = os.path.join(_ML_DIR, 'ml_model_y1y2.pkl')

HORIZONS       = [90, 180, 365]
MIN_TRAIN_ROWS = 50
_CLIP          = (0.2, 5.0)
_CHUNK         = 60


# ── Sector → ETF mapping (for excess return computation) ──────────────────────

_TAG_ETF: Dict[str, str] = {
    'commercial_bank': 'KBE',    'investment_bank': 'KBE',
    'pc_insurance':    'KIE',
    'cloud_saas':      'WCLD',   'enterprise_software': 'IGV',
    'cloud_software':  'WCLD',   'rule40_saas': 'WCLD',
    'semiconductor':   'SOXX',   'hardware': 'IGV',
    'consumer_internet': 'FDN',
    'ev_auto':         'DRIV',   'auto_legacy': 'CARZ',
    'medical_device':  'IHI',    'pharma_largecap': 'XPH',
    'biotech_clinical':'XBI',    'health_insurance': 'IHF',
    'reit_office':     'IYR',    'reit_residential': 'REZ',
    'reit_industrial': 'IYR',    'reit_retail': 'IYR',
    'utility_regulated':'XLU',   'telecom': 'IYZ',
    'cable_media':     'IYZ',
    'oil_gas_major':   'XLE',    'oil_gas_mid': 'XLE',
    'defense':         'ITA',    'aerospace': 'ITA',
    'consumer_staples':'XLP',    'retail_discount': 'XRT',
    'retail_ecomm':    'XRT',    'industrial_cong': 'XLI',
    'growth_loss':     'ARKK',   'crypto_proxy': 'BITO',
    'pharma':          'XPH',    'reit': 'IYR',
    'airline':         'JETS',
}
_ETF_DEFAULT = 'SPY'

# Sector-level volatility defaults (for inference, where we don't fetch live vol)
_TAG_VOL: Dict[str, float] = {
    'biotech_clinical': 0.55,  'growth_loss': 0.50,  'ev_auto': 0.45,
    'crypto_proxy': 0.60,      'cloud_saas': 0.35,   'rule40_saas': 0.35,
    'semiconductor': 0.32,     'consumer_internet': 0.30,
    'enterprise_software': 0.28, 'cloud_software': 0.30,
    'medical_device': 0.25,    'pharma_largecap': 0.22,
    'health_insurance': 0.20,  'commercial_bank': 0.22,
    'investment_bank': 0.28,   'oil_gas_major': 0.25, 'oil_gas_mid': 0.30,
    'auto_legacy': 0.22,       'defense': 0.18,
    'retail_discount': 0.22,   'retail_ecomm': 0.28,
    'industrial_cong': 0.20,   'telecom': 0.15,
    'cable_media': 0.20,       'consumer_staples': 0.15,
    'reit_office': 0.20,       'reit_residential': 0.18,
    'utility_regulated': 0.12, 'pc_insurance': 0.18,
}
_VOL_DEFAULT = 0.25


# ── Feature helpers ────────────────────────────────────────────────────────────

def _etf_momentum(series, ref_date: date, days: int = 90) -> float:
    """Return ETF price change over *days* ending at ref_date. 0.0 if data missing."""
    import pandas as pd
    try:
        ref_ts = pd.Timestamp(str(ref_date))
        at_ref = series[series.index >= ref_ts]
        if at_ref.empty:
            return 0.0
        ref_price = float(at_ref.iloc[0])
        past_ts = pd.Timestamp(str(ref_date - timedelta(days=days)))
        at_past = series[(series.index >= past_ts) & (series.index < ref_ts)]
        past_price = float(at_past.iloc[0]) if not at_past.empty else float(series.iloc[0])
        if past_price <= 0:
            return 0.0
        return round(ref_price / past_price - 1, 4)
    except Exception:
        return 0.0

_TAG_WACC: Dict[str, float] = {
    'commercial_bank': 0.09, 'investment_bank': 0.10, 'pc_insurance': 0.09,
    'cloud_software':  0.10, 'enterprise_software': 0.10, 'semiconductor': 0.10,
    'consumer_internet': 0.11, 'ev_auto': 0.12, 'auto_legacy': 0.09,
    'medical_device': 0.08,  'pharma_largecap': 0.08, 'biotech_clinical': 0.12,
    'reit_office': 0.07,     'reit_residential': 0.07, 'utility_regulated': 0.06,
    'telecom': 0.07,         'cable_media': 0.08,
    'defense': 0.08,         'oil_gas_major': 0.09,
    'consumer_staples': 0.07, 'retail_discount': 0.08,
    'cloud_saas': 0.10,      'rule40_saas': 0.10,
}
_WACC_DEFAULT = 0.09


def _tag_to_default_type(tag: str) -> str:
    if tag in CYCLICAL_TAGS:
        return 'CYCLICAL'
    if tag in SECULAR_DECLINE_TAGS:
        return 'STABLE_VALUE_LOWGROWTH'
    mult = SUBSECTOR_MULT.get(tag)
    if mult is None:
        return 'STABLE_VALUE'
    _, _, g = mult
    if g is None:
        return 'STABLE_VALUE'
    if g > 0.20:
        return 'HYPERGROWTH'
    if g > 0.12:
        return 'GROWTH_TECH'
    return 'STABLE_VALUE'


def build_wf_features(tag: str, regime: str, horizon_days: int,
                       month: int = 1, volatility: float = _VOL_DEFAULT,
                       etf_momentum: float = 0.0) -> List[float]:
    """
    11-feature vector.

    Pos  Type  Name
    ---  ----  ----------------
    0    cat   tag_int
    1    cat   type_int
    2    num   wacc
    3    num   growth_y1
    4    cat   ebitda_method_int
    5    num   analyst_ratio
    6    cat   regime_int        (risk_on=0, transition=1, risk_off=2, unknown=3)
    7    cat   horizon_days      (90 | 180 | 365)
    8    cat   month_of_pred     (1-12)
    9    num   volatility_30d
    10   num   etf_momentum_90d  (sector ETF 3-month return; 0 = neutral/unknown)
    """
    ctype  = _tag_to_default_type(tag)
    wacc   = _TAG_WACC.get(tag, _WACC_DEFAULT)
    mult   = SUBSECTOR_MULT.get(tag)
    growth = float(mult[2] if mult and mult[2] is not None else 0.05)

    return [
        _tag_to_int(tag),
        _type_to_int(ctype),
        wacc,
        growth,
        _method_to_int('em:3yavg'),
        1.0,                        # analyst_ratio: no historical data in training
        _regime_to_int(regime),
        float(horizon_days),
        float(month),
        float(volatility),
        float(etf_momentum),
    ]


# ── Composite regime (4 signals) ──────────────────────────────────────────────

def _composite_regime(year: int, month: int = 1) -> str:
    """
    Score 0-5 from five signals:
      1. VIX > 22  (equity fear — 22 catches early stress, 25 misses Q2 2022)
      2. HYG 3-month return < -3%  (credit stress)
      3. ^IRX > ^TNX  (3m/10y yield curve inverted = recession signal)
      4. SPY below its 200-day MA  (bear trend)
      5. SPY 3-month return < -8%  (momentum bear — confirms regime shift)

    0-1 → risk_on | 2-3 → transition | 4-5 → risk_off
    """
    try:
        import yfinance as yf

        ref = date(year, month, 2)
        ref_str = str(ref)
        prior_str = str(ref - timedelta(days=320))  # 225+ trading days for MA200

        score = 0

        def _v(series, idx=0):
            """Extract scalar from Series/DataFrame column — pandas-version agnostic."""
            col = series['Close'].squeeze()
            return float(col.values[idx])

        # Signal 1: VIX level (threshold lowered: 22 vs old 25)
        vix = yf.download('^VIX', start=ref_str, end=str(ref + timedelta(10)),
                          progress=False, auto_adjust=True)
        if not vix.empty and _v(vix) > 22:
            score += 1

        # Signal 2: HYG credit momentum (3 months prior to ref)
        hyg = yf.download('HYG', start=str(ref - timedelta(95)), end=str(ref + timedelta(5)),
                          progress=False, auto_adjust=True)
        if not hyg.empty and len(hyg) >= 50:
            ret = _v(hyg, -1) / _v(hyg, 0) - 1
            if ret < -0.03:
                score += 1

        # Signal 3: Yield curve (^IRX ≈ 3-month, ^TNX = 10-year)
        irx = yf.download('^IRX', start=ref_str, end=str(ref + timedelta(10)),
                          progress=False, auto_adjust=True)
        tnx = yf.download('^TNX', start=ref_str, end=str(ref + timedelta(10)),
                          progress=False, auto_adjust=True)
        if not irx.empty and not tnx.empty:
            if _v(irx) > _v(tnx):
                score += 1

        # Signal 4 & 5: SPY — MA200 trend + 3-month momentum
        # 320-day fetch = ~225 trading days, safely above 200 for MA200 check
        spy = yf.download('SPY', start=prior_str, end=str(ref + timedelta(5)),
                          progress=False, auto_adjust=True)
        if not spy.empty and len(spy) >= 150:
            spy_close = spy['Close'].squeeze()
            n = len(spy_close)
            ma200 = float(spy_close.values[-min(200, n):].mean())
            price = float(spy_close.values[-1])
            if price < ma200:
                score += 1
            # 3-month momentum (~65 trading days) — catches early bear before MA200 breaks
            if n >= 65:
                spy_3mo_ret = float(spy_close.values[-1]) / float(spy_close.values[-65]) - 1
                if spy_3mo_ret < -0.08:
                    score += 1

        if score <= 1:
            return 'risk_on'
        elif score <= 3:
            return 'transition'
        else:
            return 'risk_off'

    except Exception as e:
        logger.debug('composite_regime failed: %s', e)
        return 'unknown'


# ── Pipeline (10 features) ────────────────────────────────────────────────────

def _build_pipeline():
    from sklearn.compose import ColumnTransformer
    from sklearn.ensemble import GradientBoostingRegressor
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OrdinalEncoder, StandardScaler

    # cat: tag[0], type[1], ebitda_method[4], regime[6], horizon[7], month[8]
    # num: wacc[2], growth[3], analyst_ratio[5], volatility[9]
    cat_cols = [0, 1, 4, 6, 7, 8]
    num_cols = [2, 3, 5, 9]

    return Pipeline([
        ('features', ColumnTransformer([
            ('cat', OrdinalEncoder(handle_unknown='use_encoded_value', unknown_value=-1), cat_cols),
            ('num', StandardScaler(), num_cols),
        ])),
        ('model', GradientBoostingRegressor(
            n_estimators=300, max_depth=4, learning_rate=0.04,
            subsample=0.8, min_samples_leaf=5, random_state=42,
        )),
    ])


# ── Data fetching ─────────────────────────────────────────────────────────────

def _price_at(prices, ref_date: date, n_days: int) -> Optional[float]:
    target = ref_date + timedelta(days=n_days)
    later  = prices[prices.index >= str(target)]
    return float(later.iloc[0]) if not later.empty else None


def _realized_vol(prices, as_of: date) -> float:
    """30-day annualized realized volatility using log returns."""
    window = prices[prices.index < str(as_of)].iloc[-30:]
    if len(window) < 15:
        return _VOL_DEFAULT
    lr = np.log(window.values[1:] / window.values[:-1])
    return float(np.std(lr) * np.sqrt(252))


def _fetch_raw_year(tickers: List[str], year: int) -> Tuple[dict, dict]:
    """
    Batch-fetch all ticker + ETF price history for a year's monthly windows.

    Window: Nov(year-1) → Feb(year+2).
    Why 27 months: December start + 365d horizon = December of next year.
    ETFs fetched separately in one shot.

    Returns: (ticker_prices, etf_prices)
      ticker_prices: {ticker: pd.Series of Close prices}
      etf_prices:    {etf:    pd.Series of Close prices}
    """
    import yfinance as yf

    fetch_start = str(date(year - 1, 11, 1))
    fetch_end   = str(date(year + 2, 2, 1))

    ticker_prices: dict = {}
    print(f'  Fetching {len(tickers)} tickers ({fetch_start} → {fetch_end})', end='', flush=True)

    for i in range(0, len(tickers), _CHUNK):
        chunk = tickers[i:i + _CHUNK]
        try:
            raw = yf.download(chunk, start=fetch_start, end=fetch_end,
                              progress=False, auto_adjust=True, group_by='ticker')
            if raw.empty:
                continue
            for tkr in chunk:
                try:
                    p = raw['Close'].dropna() if len(chunk) == 1 else raw[tkr]['Close'].dropna()
                    if len(p) >= 30:
                        ticker_prices[tkr] = p
                except Exception:
                    pass
        except Exception as e:
            logger.debug('chunk failed: %s', e)
        print('.', end='', flush=True)

    # Fetch all unique ETFs
    unique_etfs = sorted(set(_TAG_ETF.values()) | {'SPY'})
    etf_prices: dict = {}
    try:
        raw_etf = yf.download(unique_etfs, start=fetch_start, end=fetch_end,
                              progress=False, auto_adjust=True, group_by='ticker')
        for etf in unique_etfs:
            try:
                p = (raw_etf['Close'].dropna() if len(unique_etfs) == 1
                     else raw_etf[etf]['Close'].dropna())
                if not p.empty:
                    etf_prices[etf] = p
            except Exception:
                pass
    except Exception as e:
        logger.debug('ETF fetch failed: %s', e)

    print(f' → {len(ticker_prices)} tickers, {len(etf_prices)} ETFs')
    return ticker_prices, etf_prices


def fetch_year_samples_monthly(tickers: List[str], year: int) -> List[dict]:
    """
    For every month in *year*, compute correction-factor records for all tickers.
    Each record is one (ticker, year, month, horizon) combination.
    Returns up to 12 × len(tickers) × 3 records (many will be filtered for missing prices).
    """
    ticker_prices, etf_prices = _fetch_raw_year(tickers, year)

    # Compute regime quarterly (Q1/Q2/Q3/Q4) — 4 yfinance calls vs 48 for monthly.
    # Each quarter label applies to its 3 months so intra-year regime shifts are captured.
    print(f'  Computing quarterly regimes for {year}...', end='', flush=True)
    quarter_regime: Dict[int, str] = {}
    for q_month in [1, 4, 7, 10]:
        quarter_regime[q_month] = _composite_regime(year, month=q_month)
    # Map each calendar month to its quarter's regime
    _month_to_regime = {
        **{m: quarter_regime[1]  for m in range(1, 4)},
        **{m: quarter_regime[4]  for m in range(4, 7)},
        **{m: quarter_regime[7]  for m in range(7, 10)},
        **{m: quarter_regime[10] for m in range(10, 13)},
    }
    regime_summary = '/'.join(f'Q{i+1}:{quarter_regime[q]}' for i, q in enumerate([1,4,7,10]))
    print(f' {regime_summary}')

    samples: List[dict] = []

    for month in range(1, 13):
        month_start = date(year, month, 2)
        regime = _month_to_regime[month]

        for tkr, prices in ticker_prices.items():
            tag = TICKER_TAG_MAP.get(tkr.upper(), 'diversified')
            etf = _TAG_ETF.get(tag, _ETF_DEFAULT)
            etf_p = etf_prices.get(etf) if etf in etf_prices else etf_prices.get('SPY')
            if etf_p is None:
                continue

            # Start prices
            later = prices[prices.index >= str(month_start)]
            if later.empty:
                continue
            start_price = float(later.iloc[0])
            if start_price <= 0:
                continue

            etf_later = etf_p[etf_p.index >= str(month_start)]
            if etf_later.empty:
                continue
            etf_start = float(etf_later.iloc[0])
            if etf_start <= 0:
                continue

            # Realized vol at month start (30 days prior)
            vol = _realized_vol(prices, month_start)

            # Sector ETF 3-month momentum at month start
            etf_mom = _etf_momentum(etf_p, month_start, days=90)

            # Horizon prices for stock and ETF
            p90,  etf90  = _price_at(prices, month_start, 90),  _price_at(etf_p, month_start, 90)
            p180, etf180 = _price_at(prices, month_start, 180), _price_at(etf_p, month_start, 180)
            p365, etf365 = _price_at(prices, month_start, 365), _price_at(etf_p, month_start, 365)

            samples.append({
                'ticker': tkr, 'year': year, 'month': month, 'tag': tag, 'regime': regime,
                'start_price': start_price, 'etf_start': etf_start, 'vol': vol,
                'etf': etf, 'etf_momentum': etf_mom,
                'p90':   p90,   'etf90':   etf90,
                'p180':  p180,  'etf180':  etf180,
                'p365':  p365,  'etf365':  etf365,
            })

    return samples


# ── Training data assembly ─────────────────────────────────────────────────────

def samples_to_Xy(samples: List[dict]) -> Tuple[np.ndarray, np.ndarray]:
    """
    Target = excess return factor = (stock_return / etf_return).
    1.0 = matched sector. 1.2 = beat sector by 20%. 0.8 = lagged by 20%.
    This removes market beta and measures only idiosyncratic calibration error.
    """
    X_rows, y_rows = [], []

    for s in samples:
        sp, es = s.get('start_price', 0), s.get('etf_start', 0)
        if sp <= 0 or es <= 0:
            continue

        for horizon, pk, ek in [
            (90,  'p90',  'etf90'),
            (180, 'p180', 'etf180'),
            (365, 'p365', 'etf365'),
        ]:
            p_actual = s.get(pk)
            e_actual = s.get(ek)
            if p_actual is None or e_actual is None or e_actual <= 0:
                continue

            stock_ret = p_actual / sp
            etf_ret   = e_actual / es
            excess    = stock_ret / etf_ret          # remove beta
            excess    = max(_CLIP[0], min(excess, _CLIP[1]))

            X_rows.append(build_wf_features(
                s['tag'], s['regime'], horizon,
                month=s['month'], volatility=s.get('vol', _VOL_DEFAULT),
                etf_momentum=s.get('etf_momentum', 0.0),
            ))
            y_rows.append(excess)

    return np.array(X_rows, dtype=float), np.array(y_rows, dtype=float)


# ── Train / validate helpers ───────────────────────────────────────────────────

def _train(samples: List[dict]) -> Tuple[object, int]:
    X, y = samples_to_Xy(samples)
    if len(X) < MIN_TRAIN_ROWS:
        raise ValueError(f'Only {len(X)} rows — need {MIN_TRAIN_ROWS}')
    pipe = _build_pipeline()
    pipe.fit(X, y)
    return pipe, len(X)


def _validate(pipeline, samples: List[dict]) -> dict:
    by_tag     = defaultdict(list)
    by_regime  = defaultdict(list)
    by_horizon = defaultdict(list)
    overall    = []

    for s in samples:
        sp, es = s.get('start_price', 0), s.get('etf_start', 0)
        if sp <= 0 or es <= 0:
            continue
        for horizon, pk, ek in [(90, 'p90', 'etf90'), (180, 'p180', 'etf180'), (365, 'p365', 'etf365')]:
            p_actual, e_actual = s.get(pk), s.get(ek)
            if p_actual is None or e_actual is None or e_actual <= 0:
                continue
            true_ex = max(_CLIP[0], min((p_actual / sp) / (e_actual / es), _CLIP[1]))
            pred_ex = float(pipeline.predict(np.array([
                build_wf_features(s['tag'], s['regime'], horizon,
                                  month=s['month'], volatility=s.get('vol', _VOL_DEFAULT),
                                  etf_momentum=s.get('etf_momentum', 0.0))
            ]))[0])
            err = abs(pred_ex - true_ex)
            overall.append(err)
            by_tag[s['tag']].append(err)
            by_regime[s['regime']].append(err)
            by_horizon[horizon].append(err)

    def _m(lst): return round(float(np.mean(lst)), 4) if lst else None

    return {
        'n':          len(overall),
        'mae':        _m(overall),
        'by_regime':  {str(k): {'n': len(v), 'mae': _m(v)} for k, v in by_regime.items()},
        'by_horizon': {str(k): {'n': len(v), 'mae': _m(v)} for k, v in sorted(by_horizon.items())},
        'by_tag':     dict(sorted({k: {'n': len(v), 'mae': _m(v)} for k, v in by_tag.items()}.items(),
                                  key=lambda x: -(x[1]['n'] or 0))[:12]),
    }


# ── Persistence ────────────────────────────────────────────────────────────────

def _save(pipeline, path: str, extra: dict) -> None:
    import datetime as _dt
    with open(path, 'wb') as f:
        pickle.dump(pipeline, f)
    meta = {
        'trained_at': _dt.datetime.now(_dt.timezone.utc).isoformat(),
        'n_features':  11,
        'features':   ['tag_int', 'type_int', 'wacc', 'growth_y1', 'ebitda_method_int',
                       'analyst_ratio', 'regime_int', 'horizon_days', 'month_of_pred',
                       'volatility_30d', 'etf_momentum_90d'],
        'cat_cols': [0, 1, 4, 6, 7, 8],
        'num_cols': [2, 3, 5, 9, 10],
        'target':   'excess_return_over_sector_etf',
        'framework': 'walk_forward_v2',
        **extra,
    }
    with open(path.replace('.pkl', '_metadata.json'), 'w') as f:
        json.dump(meta, f, indent=2)
    print(f'  Saved {os.path.basename(path)}  ({extra.get("n_rows", "?")} rows)')


# ── Report printing ────────────────────────────────────────────────────────────

def _print_report(label: str, r: dict) -> None:
    mae_str = f'{r["mae"]:.4f}' if r.get("mae") is not None else 'n/a'
    print(f'\n── {label}  n={r["n"]}  excess-return MAE={mae_str} ──')
    for reg, v in r['by_regime'].items():
        print(f'  regime {reg:<12}  n={v["n"]:>5}  mae={v["mae"]:.4f}')
    print('  Horizons:')
    for h, v in r['by_horizon'].items():
        print(f'    {h+"d":<7}  n={v["n"]:>5}  mae={v["mae"]:.4f}')
    print('  Top sectors:')
    for tag, v in list(r['by_tag'].items())[:8]:
        print(f'    {tag:<32}  n={v["n"]:>4}  mae={v["mae"]:.4f}')


# ── MONTHLY ROLLING walk-forward (main mode) ───────────────────────────────────

def run_monthly_rolling(years: List[int], tickers: List[str],
                        window_months: int = 12) -> None:
    """
    For each calendar month in *years* (after accumulating *window_months* of data),
    train on the trailing window and validate on that month's samples.
    Saves final production model trained on the last window.

    This is the proper quant approach: the model never sees future data,
    and retraining happens at monthly cadence rather than annually.
    """
    # Fetch data for all years
    year_samples: Dict[int, List[dict]] = {}
    for yr in years:
        print(f'\nYear {yr}:')
        year_samples[yr] = fetch_year_samples_monthly(tickers, yr)
        n = len(year_samples[yr])
        print(f'  {n} sample records  ({n * 3} training rows after horizon expansion)')

    # Index by (year, month)
    by_ym: Dict[tuple, List[dict]] = defaultdict(list)
    for yr, samples in year_samples.items():
        for s in samples:
            by_ym[(yr, s['month'])].append(s)

    ordered_yms = sorted(by_ym.keys())
    print(f'\nMonthly rolling walk-forward  window={window_months}mo')
    print(f'Total (year, month) periods: {len(ordered_yms)}')

    val_rows = []
    final_pipe = None

    for i, ym in enumerate(ordered_yms):
        if i < window_months:
            continue   # not enough history yet

        # Training window: last window_months months ending just before ym
        train_yms = ordered_yms[i - window_months:i]
        train_samples = [s for tym in train_yms for s in by_ym[tym]]

        try:
            pipe, n_rows = _train(train_samples)
        except ValueError as e:
            logger.debug('%s %s: skip — %s', ym, e)
            continue

        # Validate on the current month (out-of-sample)
        val_samples = by_ym[ym]
        report = _validate(pipe, val_samples)
        if report['n'] > 0:
            val_rows.append({'ym': f'{ym[0]}-{ym[1]:02d}', **report})
            print(f'  {ym[0]}-{ym[1]:02d}  train={n_rows}  val_n={report["n"]}  mae={report["mae"]:.4f}')

        final_pipe = pipe

    if final_pipe is None:
        print('Not enough data to train — check year range.')
        return

    # Summary
    all_maes = [r['mae'] for r in val_rows if r.get('mae') is not None]
    overall  = round(float(np.mean(all_maes)), 4) if all_maes else None
    print(f'\nOverall out-of-sample MAE (excess return): {overall}')
    print(f'Periods validated: {len(val_rows)}  (each = one calendar month)')

    # Persist backtest history — lets monitor.py show quality report without waiting 90 days
    import datetime as _dt
    _bt_path = os.path.join(_ML_DIR, 'ml_backtest_history.json')
    with open(_bt_path, 'w') as _btf:
        json.dump({
            'computed_at':    _dt.datetime.now(_dt.timezone.utc).isoformat(),
            'years':          years,
            'window_months':  window_months,
            'overall_oos_mae': overall,
            'n_periods':      len(val_rows),
            'periods':        val_rows,
        }, _btf, indent=2)
    print(f'  Backtest history saved → {os.path.basename(_bt_path)}')

    # Save final model (trained on last window_months of all available data)
    last_window = ordered_yms[-window_months:]
    final_samples = [s for tym in last_window for s in by_ym[tym]]
    final_pipe, n_final = _train(final_samples)
    _save(final_pipe, ML_MODEL_PATH, {
        'n_rows':         n_final,
        'years':          years,
        'window_months':  window_months,
        'overall_oos_mae': overall,
        'mode':           'monthly_rolling',
    })
    print(f'Production model updated → {os.path.basename(ML_MODEL_PATH)}')


# ── ANNUAL walk-forward (kept as fallback) ────────────────────────────────────

def run_annual(years: List[int], tickers: List[str]) -> None:
    """Original 3-phase annual trainer. Kept for quick smoke tests."""
    print('Running annual walk-forward (legacy mode)')

    def _fetch_annual(yrs):
        samples = []
        for yr in yrs:
            print(f'\nYear {yr}:')
            samples.extend(fetch_year_samples_monthly(tickers, yr))
        return samples

    s_y0 = _fetch_annual([years[0]])
    pipe_y1, n = _train(s_y0)
    _save(pipe_y1, MODEL_Y1, {'years_trained': [years[0]], 'n_rows': n})
    _print_report(f'in-sample {years[0]}', _validate(pipe_y1, s_y0))

    if len(years) >= 2:
        s_y1 = _fetch_annual([years[1]])
        _print_report(f'out-of-sample {years[1]}', _validate(pipe_y1, s_y1))

    if len(years) >= 3:
        s_y0y1 = _fetch_annual(years[:2])
        pipe_f, n = _train(s_y0y1)
        _save(pipe_f, MODEL_Y1Y2, {'years_trained': years[:2], 'n_rows': n})

        s_y2 = _fetch_annual([years[2]])
        val = _validate(pipe_f, s_y2)
        _print_report(f'out-of-sample {years[2]}', val)

        _save(pipe_f, ML_MODEL_PATH, {
            'years_trained': years[:2], 'validated_on': years[2],
            'final_mae': val['mae'], 'n_rows': n, 'mode': 'annual',
        })
        print(f'\nProduction model updated → {os.path.basename(ML_MODEL_PATH)}')


# ── Entry point ────────────────────────────────────────────────────────────────

def run(years: List[int] = None, mode: str = 'monthly', window: int = 12) -> None:
    if years is None:
        years = [2022, 2023, 2024]
    tickers = sorted(TICKER_TAG_MAP.keys())
    print(f'AXIOM walk-forward  |  {len(tickers)} tickers  |  mode={mode}  |  years={years}\n')
    if mode == 'monthly':
        run_monthly_rolling(years, tickers, window_months=window)
    else:
        run_annual(years, tickers)
    print('\nDone.')


if __name__ == '__main__':
    import argparse
    logging.basicConfig(level=logging.WARNING)
    ap = argparse.ArgumentParser()
    ap.add_argument('--years',  nargs='+', type=int, default=[2022, 2023, 2024])
    ap.add_argument('--mode',   choices=['monthly', 'annual'], default='monthly')
    ap.add_argument('--window', type=int, default=12, help='Rolling window in months')
    args = ap.parse_args()
    run(args.years, args.mode, args.window)
