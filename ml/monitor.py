"""
Autonomous market monitor — runs via cron, needs no human input.

What it does:
  --snapshot : (daily, after market close)
               Fetch all 285 tickers, log current price + MA50/MA200 + VIX regime.
               Apply ML correction to get predicted_correction for each ticker.

  --evaluate : (weekly)
               For snapshot entries that are now 90 / 180 / 365 days old,
               fetch today's price, compute actual correction, score the model.
               Append to monitor_eval.jsonl.

  --report   : Print rolling accuracy, sector drift, trend signals.
               Also flags if model MAE is degrading (retrain signal).

  --all      : Run snapshot + evaluate + report in one pass.

Auto-retrain: if rolling 90d MAE exceeds RETRAIN_MAE_THRESHOLD for 2+
              consecutive evaluations, walk_forward.run() is called automatically.

Logs:
  valuation_app/monitor_log.jsonl   — daily snapshots
  valuation_app/monitor_eval.jsonl  — scored predictions vs actuals
  valuation_app/monitor_report.txt  — latest text report (overwritten each run)

Cron setup (run `python3 -m ml.monitor --setup-cron` to install):
  Daily  Mon-Fri 4:30pm ET  →  --snapshot
  Weekly Sunday  10:00am ET →  --evaluate --report
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_APP_DIR      = os.path.dirname(os.path.dirname(__file__))
SNAPSHOT_LOG  = os.path.join(_APP_DIR, 'monitor_log.jsonl')
EVAL_LOG      = os.path.join(_APP_DIR, 'monitor_eval.jsonl')
REPORT_FILE   = os.path.join(_APP_DIR, 'monitor_report.txt')

HORIZONS = [90, 180, 365]
RETRAIN_MAE_THRESHOLD = 0.30    # flag retrain if 90d MAE exceeds this
RETRAIN_TRIGGER_COUNT = 2       # consecutive eval cycles above threshold → retrain


# ── Data fetching ──────────────────────────────────────────────────────────────

def _fetch_vix() -> tuple[float, str]:
    """Returns (vix_level, regime_label)."""
    try:
        import yfinance as yf
        v = yf.download('^VIX', period='5d', progress=False, auto_adjust=True)
        if not v.empty:
            level = float(v['Close'].squeeze().values[-1])
            return level, ('risk_off' if level > 25 else 'risk_on')
    except Exception:
        pass
    return 0.0, 'unknown'


def _fetch_snapshot_prices(tickers: List[str], period: str = '270d') -> Dict[str, dict]:
    """
    Batch-fetch recent history for all tickers.
    Returns {ticker: {price, ma50, ma200, momentum_30d, momentum_12_1}}.
    270d covers MA200 (200 days) + 12-1 month momentum (252 - 21 = ~231 trading days).
    """
    import yfinance as yf
    CHUNK = 60
    result: Dict[str, dict] = {}

    for i in range(0, len(tickers), CHUNK):
        chunk = tickers[i:i + CHUNK]
        try:
            raw = yf.download(
                chunk, period=period,
                progress=False, auto_adjust=True,
                group_by='ticker',
            )
            if raw.empty:
                continue
            for tkr in chunk:
                try:
                    prices = (
                        raw['Close'].dropna()
                        if len(chunk) == 1
                        else raw[tkr]['Close'].dropna()
                    )
                    if len(prices) < 30:
                        continue
                    price_now     = float(prices.iloc[-1])
                    ma50          = float(prices.iloc[-50:].mean())  if len(prices) >= 50  else None
                    ma200         = float(prices.iloc[-200:].mean()) if len(prices) >= 200 else None
                    price_30d_ago = float(prices.iloc[-30])          if len(prices) >= 30  else None
                    momentum_30d  = (price_now / price_30d_ago - 1.0) if price_30d_ago else None
                    # 12-1 month momentum: 252-day return minus the most recent 21 days
                    # Jegadeesh-Titman: skip the last month to avoid short-term reversal
                    mom_12_1 = None
                    if len(prices) >= 252:
                        price_252d_ago = float(prices.iloc[-252])
                        price_21d_ago  = float(prices.iloc[-21])
                        if price_252d_ago > 0 and price_21d_ago > 0:
                            ret_12m = price_now / price_252d_ago - 1.0
                            ret_1m  = price_now / price_21d_ago  - 1.0
                            mom_12_1 = ret_12m - ret_1m
                    result[tkr] = {
                        'price':         price_now,
                        'ma50':          round(ma50,         4) if ma50         is not None else None,
                        'ma200':         round(ma200,        4) if ma200        is not None else None,
                        'momentum_30d':  round(momentum_30d, 4) if momentum_30d is not None else None,
                        'momentum_12_1': round(mom_12_1,     4) if mom_12_1     is not None else None,
                    }
                except Exception:
                    pass
        except Exception as e:
            logger.debug('chunk failed: %s', e)

    return result


def _fetch_etf_momentums() -> Dict[str, float]:
    """Fetch 90-day momentum for all sector ETFs. Returns {etf_ticker: momentum_float}."""
    import yfinance as yf
    from ml.walk_forward import _TAG_ETF, _etf_momentum
    unique_etfs = sorted(set(_TAG_ETF.values()) | {'SPY'})
    start = str(date.today() - timedelta(days=130))  # 130 days covers 90 trading-day window
    end   = str(date.today() + timedelta(days=1))
    momentums: Dict[str, float] = {}
    try:
        raw = yf.download(unique_etfs, start=start, end=end,
                          progress=False, auto_adjust=True, group_by='ticker')
        if raw.empty:
            return momentums
        for etf in unique_etfs:
            try:
                s = raw['Close'].dropna() if len(unique_etfs) == 1 else raw[etf]['Close'].dropna()
                if s.empty:
                    continue
                momentums[etf] = _etf_momentum(s, date.today(), days=90)
            except Exception:
                pass
    except Exception as e:
        logger.debug('etf momentum fetch failed: %s', e)
    return momentums


def _fetch_prices_on(tickers: List[str], on_date: date) -> Dict[str, float]:
    """Fetch closing prices on or just after *on_date*."""
    import yfinance as yf
    CHUNK = 60
    result: Dict[str, float] = {}
    end = str(on_date + timedelta(days=10))  # buffer for weekends/holidays

    for i in range(0, len(tickers), CHUNK):
        chunk = tickers[i:i + CHUNK]
        try:
            raw = yf.download(
                chunk, start=str(on_date), end=end,
                progress=False, auto_adjust=True,
                group_by='ticker',
            )
            if raw.empty:
                continue
            for tkr in chunk:
                try:
                    prices = (
                        raw['Close'].dropna()
                        if len(chunk) == 1
                        else raw[tkr]['Close'].dropna()
                    )
                    if not prices.empty:
                        result[tkr] = float(prices.iloc[0])
                except Exception:
                    pass
        except Exception:
            pass

    return result


# ── ML correction (best-effort, degrades gracefully if no model) ───────────────

def _ml_correction(ticker: str, tag: str, regime: str,
                    etf_momentums: Optional[Dict[str, float]] = None,
                    snap_record: Optional[dict] = None) -> Optional[float]:
    """
    Apply the walk-forward trained model if available.
    If snap_record is provided (has Z-scores), uses real cross-sectional features.
    Otherwise falls back to static sector defaults.
    Returns predicted excess return factor, or None if model absent.
    """
    try:
        import numpy as np
        import pickle
        from ml.walk_forward import (
            build_wf_features, build_wf_features_from_snapshot,
            _TAG_ETF, ML_MODEL_PATH, _TAG_VOL, _VOL_DEFAULT,
        )

        if not os.path.exists(ML_MODEL_PATH):
            return None

        with open(ML_MODEL_PATH, 'rb') as f:
            pipeline = pickle.load(f)

        # Check what feature format this model was trained on
        metadata_path = ML_MODEL_PATH.replace('.pkl', '_metadata.json')
        feature_format = 'static_defaults'
        if os.path.exists(metadata_path):
            with open(metadata_path) as mf:
                feature_format = json.load(mf).get('feature_format', 'static_defaults')

        vol = _TAG_VOL.get(tag, _VOL_DEFAULT)
        etf = _TAG_ETF.get(tag, 'SPY')
        etf_mom = etf_momentums.get(etf, 0.0) if etf_momentums else 0.0

        if feature_format == 'z_scores' and snap_record and snap_record.get('z_value') is not None:
            snap_with_etf = dict(snap_record)
            snap_with_etf['etf_momentum_90d'] = etf_mom
            feat = build_wf_features_from_snapshot(snap_with_etf, horizon_days=365)
        else:
            feat = build_wf_features(tag, regime, horizon_days=365,
                                     month=datetime.now().month,
                                     volatility=vol, etf_momentum=etf_mom)

        return round(float(pipeline.predict(np.array([feat]))[0]), 4)
    except Exception as e:
        logger.debug('ml_correction failed for %s: %s', ticker, e)
        return None


def _fetch_quality_data() -> Dict[str, dict]:
    """
    Load FCF yield inputs from the DB for all tickers.
    Returns {ticker: {ebitda, tax_rate, debt, cash, market_cap, depreciation, capex_pct, revenue}}.
    Note: operating_income is derived as ebitda - depreciation (EBIT approximation).
    """
    result: Dict[str, dict] = {}
    try:
        from config import Config
        if Config.DATABASE_TYPE == 'postgresql':
            import psycopg2
            conn = psycopg2.connect(Config.get_db_connection_string())
        else:
            import sqlite3
            conn = sqlite3.connect(Config.SQLITE_DB)
            conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT c.ticker,
                   cf.ebitda, cf.tax_rate, cf.debt, cf.cash,
                   cf.market_cap_estimate, cf.depreciation, cf.capex_pct, cf.revenue
            FROM company_financials cf
            JOIN companies c ON cf.company_id = c.id
            WHERE c.ticker IS NOT NULL
        """)
        for row in cur.fetchall():
            tkr = (row['ticker'] if hasattr(row, 'keys') else row[0] or '').upper()
            if not tkr:
                continue
            def _f(key, idx):
                try:
                    v = row[key] if hasattr(row, 'keys') else row[idx]
                    return float(v) if v is not None else 0.0
                except Exception:
                    return 0.0
            ebitda       = _f('ebitda',             1)
            depreciation = _f('depreciation',       6)
            result[tkr] = {
                'ebitda':       ebitda,
                'tax_rate':     _f('tax_rate',         2),
                'debt':         _f('debt',             3),
                'cash':         _f('cash',             4),
                'market_cap':   _f('market_cap_estimate', 5),
                'depreciation': depreciation,
                'capex_pct':    _f('capex_pct',        7),
                'revenue':      _f('revenue',          8),
                # EBIT approximation: EBITDA - D&A (no separate operating_income column in schema)
                'operating_income': max(0.0, ebitda - depreciation),
            }
        conn.close()
    except Exception as e:
        logger.debug('_fetch_quality_data failed: %s', e)
    return result


def _compute_quality_factor(q: dict, market_price: float, shares: float = None) -> Optional[float]:
    """
    Quality factor = FCF yield (free cash flow / market cap).

    FCF = NOPAT + D&A - CapEx  where NOPAT = operating_income * (1 - tax_rate)
    Yield = FCF / market_cap

    ROIC is excluded until book equity is tracked in the DB. Using market cap as
    the equity component of invested capital introduces a circularity: overvalued
    stocks appear low-quality and undervalued ones appear high-quality, which
    conflates the quality signal with the value signal.
    """
    try:
        market_cap = q['market_cap']
        if not market_cap or market_cap <= 0:
            return None
        nopat      = q['operating_income'] * (1 - q['tax_rate'])
        capex      = q['revenue'] * q['capex_pct']
        fcf_approx = nopat + q['depreciation'] - capex
        return round(fcf_approx / market_cap, 6)
    except Exception:
        return None


def _zscore_within_tag(records: List[dict], field: str) -> Dict[str, Optional[float]]:
    """
    Compute Z-score of *field* within each sub-sector tag.
    Winsorize at ±3σ before scoring.
    Returns {ticker: z_score} for all tickers that have a non-None value.
    """
    from collections import defaultdict as _dd
    import math

    by_tag: Dict[str, List[tuple]] = _dd(list)  # tag → [(ticker, value)]
    for r in records:
        val = r.get(field)
        if val is not None:
            by_tag[r['tag']].append((r['ticker'], val))

    result: Dict[str, Optional[float]] = {}
    for tag, pairs in by_tag.items():
        if len(pairs) < 5:
            for tkr, _ in pairs:
                result[tkr] = None
            continue
        vals = [v for _, v in pairs]
        mean = sum(vals) / len(vals)
        std  = (sum((v - mean) ** 2 for v in vals) / len(vals)) ** 0.5
        if std == 0:
            for tkr, _ in pairs:
                result[tkr] = 0.0
            continue
        # Winsorise raw values at ±3σ before scoring
        for tkr, v in pairs:
            v_win = max(mean - 3 * std, min(v, mean + 3 * std))
            result[tkr] = round((v_win - mean) / std, 4)
    return result


def _fetch_last_dcf_prices() -> Dict[str, float]:
    """Load the most recent dcf_price_per_share for each ticker from valuation_results."""
    result: Dict[str, float] = {}
    try:
        from config import Config
        if Config.DATABASE_TYPE == 'postgresql':
            import psycopg2
            conn = psycopg2.connect(Config.get_db_connection_string())
        else:
            import sqlite3
            conn = sqlite3.connect(Config.SQLITE_DB)
            conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT c.ticker, vr.dcf_price_per_share
            FROM valuation_results vr
            JOIN companies c ON vr.company_id = c.id
            WHERE vr.dcf_price_per_share IS NOT NULL
              AND vr.id IN (
                SELECT MAX(id) FROM valuation_results GROUP BY company_id
              )
        """)
        for row in cur.fetchall():
            try:
                tkr   = (row['ticker'] if hasattr(row, 'keys') else row[0] or '').upper()
                price = (row['dcf_price_per_share'] if hasattr(row, 'keys') else row[1])
                if tkr and price is not None and float(price) > 0:
                    result[tkr] = float(price)
            except Exception:
                pass
        conn.close()
    except Exception as e:
        logger.debug('_fetch_last_dcf_prices failed: %s', e)
    return result


# ── Core actions ───────────────────────────────────────────────────────────────

def snapshot() -> int:
    """Fetch current market state and log one record per ticker. Returns n written."""
    from valuation._config import TICKER_TAG_MAP

    tickers = sorted(TICKER_TAG_MAP.keys())
    today   = date.today().isoformat()

    # Skip if today already fully logged (idempotent daily run)
    logged_today: set = set()
    try:
        with open(SNAPSHOT_LOG) as f:
            for line in f:
                try:
                    r = json.loads(line.strip())
                    if r.get('date') == today:
                        logged_today.add(r['ticker'])
                except Exception:
                    pass
    except FileNotFoundError:
        pass

    vix_level, _ = _fetch_vix()
    from ml.walk_forward import _composite_regime, _TAG_ETF, _TAG_VOL, _VOL_DEFAULT
    regime     = _composite_regime(date.today().year, month=date.today().month)
    etf_moms   = _fetch_etf_momentums()
    dcf_prices = _fetch_last_dcf_prices()
    quality_db = _fetch_quality_data()
    print(f'Snapshot {today}  VIX={vix_level:.1f}  regime={regime}  '
          f'dcf={len(dcf_prices)}  quality={len(quality_db)}')

    prices = _fetch_snapshot_prices(tickers)
    print(f'  Fetched {len(prices)}/{len(tickers)} tickers')

    # Pre-fetch ETF prices once
    unique_etfs = sorted(set(_TAG_ETF.values()) | {'SPY'})
    etf_snap_prices: Dict[str, float] = {}
    try:
        import yfinance as yf
        raw_etf = yf.download(unique_etfs, period='5d', progress=False,
                               auto_adjust=True, group_by='ticker')
        if not raw_etf.empty:
            for etf in unique_etfs:
                try:
                    s = (raw_etf['Close'].dropna() if len(unique_etfs) == 1
                         else raw_etf[etf]['Close'].dropna())
                    if not s.empty:
                        etf_snap_prices[etf] = round(float(s.iloc[-1]), 4)
                except Exception:
                    pass
    except Exception as e:
        logger.debug('ETF snapshot fetch failed: %s', e)

    # ── Pass 1: build raw factor records in memory (no ML yet) ───────────────
    raw_records: List[dict] = []
    for tkr, p in prices.items():
        if tkr in logged_today:
            continue
        tag        = TICKER_TAG_MAP.get(tkr.upper(), 'diversified')
        vol        = _TAG_VOL.get(tag, _VOL_DEFAULT)
        etf_ticker = _TAG_ETF.get(tag, 'SPY')
        etf_price  = etf_snap_prices.get(etf_ticker) or etf_snap_prices.get('SPY')
        dcf_price  = dcf_prices.get(tkr.upper())
        mkt_price  = p['price']

        value_factor = (round(dcf_price / mkt_price - 1.0, 4)
                        if (dcf_price and mkt_price > 0) else None)

        q_data      = quality_db.get(tkr.upper())
        quality_raw = _compute_quality_factor(q_data, mkt_price) if q_data else None

        raw_records.append({
            'date':              today,
            'ticker':            tkr,
            'tag':               tag,
            'regime':            regime,
            'vix':               round(vix_level, 2),
            'price':             mkt_price,
            'ma50':              p['ma50'],
            'ma200':             p['ma200'],
            'momentum_30d':      p['momentum_30d'],
            'momentum_12_1':     p.get('momentum_12_1'),
            'volatility_sector': round(vol, 4),
            'etf_ticker':        etf_ticker,
            'etf_price':         etf_price,
            'dcf_price':         dcf_price,
            'value_factor':      value_factor,
            'quality_raw':       quality_raw,
        })

    # ── Pass 2: cross-sectional Z-scores within sub-sector tag ────────────────
    z_value    = _zscore_within_tag(raw_records, 'value_factor')
    z_momentum = _zscore_within_tag(raw_records, 'momentum_12_1')
    z_quality  = _zscore_within_tag(raw_records, 'quality_raw')

    # ── Pass 3: attach Z-scores, compute composite, run ML, write ─────────────
    written = 0
    with open(SNAPSHOT_LOG, 'a') as f:
        for rec in raw_records:
            tkr = rec['ticker']
            zv  = z_value.get(tkr)
            zm  = z_momentum.get(tkr)
            zq  = z_quality.get(tkr)

            z_vals    = [v for v in [zv, zm, zq] if v is not None]
            composite = round(sum(z_vals) / len(z_vals), 4) if z_vals else None

            rec['z_value']         = zv
            rec['z_momentum']      = zm
            rec['z_quality']       = zq
            rec['composite_score'] = composite

            # ML prediction uses real Z-scores now that they're computed
            tag = rec['tag']
            rec['predicted_correction'] = _ml_correction(
                tkr, tag, regime,
                etf_momentums=etf_moms,
                snap_record=rec,
            )

            f.write(json.dumps(rec) + '\n')
            written += 1

    if written:
        print(f'  Logged {written} snapshots (with Z-scores) → {os.path.basename(SNAPSHOT_LOG)}')
    else:
        print(f'  Today already logged ({len(logged_today)} tickers) — skipped')
    return written


def evaluate() -> dict:
    """
    Score snapshots that are now 90/180/365 days old.
    For each horizon, compare predicted_correction vs actual price change.
    Appends results to monitor_eval.jsonl.
    Returns summary dict.
    """
    today = date.today()

    # Load all snapshots
    snapshots: List[dict] = []
    try:
        with open(SNAPSHOT_LOG) as f:
            for line in f:
                try:
                    snapshots.append(json.loads(line.strip()))
                except Exception:
                    pass
    except FileNotFoundError:
        print('No snapshot log yet — run --snapshot first.')
        return {}

    # Load already-evaluated (snap_date, ticker, horizon) so we don't double-score
    evaluated = set()
    try:
        with open(EVAL_LOG) as f:
            for line in f:
                try:
                    r = json.loads(line.strip())
                    evaluated.add((r['snapshot_date'], r['ticker'], r['horizon_days']))
                except Exception:
                    pass
    except FileNotFoundError:
        pass

    # Group snapshots by date
    by_date: Dict[str, List[dict]] = defaultdict(list)
    for s in snapshots:
        by_date[s['date']].append(s)

    all_errors: List[float] = []
    written = 0

    with open(EVAL_LOG, 'a') as f:
        for snap_date_str, records in sorted(by_date.items()):
            snap_date = date.fromisoformat(snap_date_str)

            for horizon in HORIZONS:
                eval_date = snap_date + timedelta(days=horizon)
                if eval_date > today:
                    continue  # future — not scorable yet

                # Which tickers in this batch still need scoring?
                to_score = [
                    r for r in records
                    if (snap_date_str, r['ticker'], horizon) not in evaluated
                    and r.get('predicted_correction') is not None
                    and r.get('price') is not None
                ]
                if not to_score:
                    continue

                tickers_batch = [r['ticker'] for r in to_score]
                actual_prices = _fetch_prices_on(tickers_batch, eval_date)

                # Fetch ETF prices at eval_date for all unique ETFs in this batch
                unique_etfs_batch = list({r.get('etf_ticker', 'SPY') for r in to_score})
                etf_eval_prices: Dict[str, float] = {}
                try:
                    etf_raw = _fetch_prices_on(unique_etfs_batch, eval_date)
                    etf_eval_prices = etf_raw
                except Exception:
                    pass

                for r in to_score:
                    tkr = r['ticker']
                    actual = actual_prices.get(tkr)
                    if actual is None:
                        continue

                    snap_price = r['price']
                    etf_ticker = r.get('etf_ticker', 'SPY')
                    etf_snap   = r.get('etf_price')
                    etf_eval   = etf_eval_prices.get(etf_ticker)

                    # Compute excess return if we have both ETF prices; fall back to
                    # raw stock return for records logged before the ETF price fix.
                    if etf_snap and etf_eval and etf_snap > 0 and etf_eval > 0:
                        stock_ret   = actual / snap_price
                        etf_ret     = etf_eval / etf_snap
                        actual_correction = round(stock_ret / etf_ret, 4)
                        eval_version = 1   # excess return — correct metric
                    else:
                        actual_correction = round(actual / snap_price, 4)
                        eval_version = 0   # raw return — legacy, exclude from IC

                    pred_correction = r['predicted_correction']
                    abs_err = abs(pred_correction - actual_correction)
                    if eval_version == 1:
                        all_errors.append(abs_err)

                    eval_record = {
                        'snapshot_date':        snap_date_str,
                        'eval_date':            eval_date.isoformat(),
                        'ticker':               tkr,
                        'tag':                  r.get('tag', ''),
                        'regime':               r.get('regime', ''),
                        'horizon_days':         horizon,
                        'snap_price':           snap_price,
                        'actual_price':         round(actual, 4),
                        'actual_correction':    actual_correction,
                        'predicted_correction': pred_correction,
                        'abs_error':            round(abs_err, 4),
                        'eval_version':         eval_version,
                    }
                    f.write(json.dumps(eval_record) + '\n')
                    evaluated.add((snap_date_str, tkr, horizon))
                    written += 1

    mae = round(sum(all_errors) / len(all_errors), 4) if all_errors else None
    print(f'Evaluated {written} new records  rolling MAE={mae}')
    return {'n_evaluated': written, 'rolling_mae': mae}


# ── Reporting & drift detection ────────────────────────────────────────────────

def _rank_ic(pairs: list) -> Optional[float]:
    """Spearman rank IC between predicted and actual excess return pairs."""
    if len(pairs) < 5:
        return None
    try:
        from scipy.stats import spearmanr
        preds   = [p for p, _ in pairs]
        actuals = [a for _, a in pairs]
        rho, _ = spearmanr(preds, actuals)
        return round(float(rho), 4) if rho is not None else None
    except ImportError:
        try:
            import numpy as np
            preds   = np.array([p for p, _ in pairs], dtype=float)
            actuals = np.array([a for _, a in pairs], dtype=float)
            def _avgrank(arr):
                order = np.argsort(arr)
                ranks = np.empty_like(order, dtype=float)
                ranks[order] = np.arange(len(arr))
                for v in np.unique(arr):
                    mask = arr == v
                    ranks[mask] = ranks[mask].mean()
                return ranks
            corr = np.corrcoef(_avgrank(preds), _avgrank(actuals))[0, 1]
            return round(float(corr), 4) if not np.isnan(corr) else None
        except Exception:
            return None
    except Exception:
        return None


def _load_eval() -> List[dict]:
    records = []
    try:
        with open(EVAL_LOG) as f:
            for line in f:
                try:
                    records.append(json.loads(line.strip()))
                except Exception:
                    pass
    except FileNotFoundError:
        pass
    return records


def report(print_output: bool = True) -> dict:
    """
    Rolling accuracy report + trend signals + retrain flag.
    Saves to monitor_report.txt, returns summary dict.
    """
    records = _load_eval()
    if not records:
        msg = 'No evaluation records yet — run --evaluate first.'
        if print_output:
            print(msg)
        return {'error': msg}

    today = date.today()
    windows = {'30d': 30, '90d': 90, '180d': 180}

    by_horizon: Dict[int, List[float]]  = defaultdict(list)
    by_tag:     Dict[str, List[float]]  = defaultdict(list)
    by_regime:  Dict[str, List[float]]  = defaultdict(list)
    by_window:  Dict[str, List[float]]  = defaultdict(list)

    # IC computation — only on eval_version=1 records (excess return, not raw return)
    from collections import defaultdict as _dd
    ic_by_period:        Dict[tuple, list] = _dd(list)  # (eval_date, horizon) → [(pred, actual)]
    ic_by_regime_period: Dict[tuple, list] = _dd(list)  # (regime, eval_date, horizon) → [(pred, actual)]

    for r in records:
        err = r.get('abs_error')
        if err is None:
            continue
        days_ago = (today - date.fromisoformat(r['eval_date'])).days
        by_horizon[r['horizon_days']].append(err)
        by_tag[r.get('tag', 'unknown')].append(err)
        by_regime[r.get('regime', 'unknown')].append(err)
        for label, window in windows.items():
            if days_ago <= window:
                by_window[label].append(err)

        if r.get('eval_version') == 1:
            pred = r.get('predicted_correction')
            act  = r.get('actual_correction')
            if pred is not None and act is not None:
                key = (r['eval_date'], r['horizon_days'])
                ic_by_period[key].append((pred, act))
                # Also index by regime for regime-conditional IC
                ic_by_regime_period[(r.get('regime', 'unknown'), r['eval_date'], r['horizon_days'])].append((pred, act))

    def _mae(lst): return round(float(sum(lst) / len(lst)), 4) if lst else None

    def _ic_summary(ics: list) -> dict:
        if not ics:
            return {'mean_ic': None, 'ic_std': None, 't_stat': None, 'n_periods': 0}
        import math
        n     = len(ics)
        mean  = sum(ics) / n
        std   = (sum((x - mean) ** 2 for x in ics) / max(n - 1, 1)) ** 0.5
        t     = (mean / (std / math.sqrt(n))) if std > 0 else None
        return {
            'mean_ic':   round(mean, 4),
            'ic_std':    round(std, 4),
            't_stat':    round(t, 2) if t is not None else None,
            'n_periods': n,
        }

    # IC by horizon
    period_ics: Dict[int, List[float]] = defaultdict(list)
    for (eval_date, horizon), pairs in ic_by_period.items():
        ic = _rank_ic(pairs)
        if ic is not None:
            period_ics[horizon].append(ic)
    ic_report = {str(h): _ic_summary(v) for h, v in sorted(period_ics.items())}

    # IC by regime (collapse across horizons — enough to show regime-conditional signal)
    regime_ics: Dict[str, List[float]] = defaultdict(list)
    for (regime_key, eval_date, horizon), pairs in ic_by_regime_period.items():
        ic = _rank_ic(pairs)
        if ic is not None:
            regime_ics[regime_key].append(ic)
    ic_by_regime_report = {reg: _ic_summary(v) for reg, v in sorted(regime_ics.items())}

    # Hit rate by quintile — within each (eval_date, horizon) period,
    # rank tickers by predicted_correction, split into quintiles,
    # record whether top quintile beat the median actual_correction.
    quintile_hits: Dict[int, List[int]] = defaultdict(list)   # quintile(1=top) → [1/0]
    for (eval_date, horizon), pairs in ic_by_period.items():
        if len(pairs) < 10:   # need at least 10 to split into 5 meaningful quintiles
            continue
        sorted_by_pred = sorted(pairs, key=lambda x: x[0], reverse=True)
        n = len(sorted_by_pred)
        q_size = n // 5
        median_actual = sorted(p[1] for p in pairs)[n // 2]
        for q in range(5):
            q_pairs = sorted_by_pred[q * q_size:(q + 1) * q_size]
            q_actual_mean = sum(p[1] for p in q_pairs) / len(q_pairs)
            quintile_hits[q + 1].append(1 if q_actual_mean > median_actual else 0)

    hit_rate_by_quintile = {
        f'Q{q}': {
            'hit_rate': round(sum(hits) / len(hits), 3) if hits else None,
            'n_periods': len(hits),
        }
        for q, hits in sorted(quintile_hits.items())
    }

    overall_mae = _mae([r['abs_error'] for r in records if r.get('abs_error') is not None])
    rolling = {k: _mae(v) for k, v in by_window.items()}

    # Sector drift — top 10 worst tags
    tag_mae = {
        tag: {'mae': _mae(errs), 'n': len(errs)}
        for tag, errs in by_tag.items()
    }
    worst_tags = sorted(tag_mae.items(), key=lambda x: -(x[1]['mae'] or 0))[:10]

    # Retrain signal — use IC t-stat when available, MAE as fallback
    retrain_flag = False
    has_ic_data = any(v['n_periods'] >= 3 for v in ic_report.values())
    if has_ic_data:
        # If any horizon has negative mean IC with 2+ periods, recommend retrain
        retrain_flag = any(
            v['mean_ic'] is not None and v['mean_ic'] < 0 and v['n_periods'] >= 2
            for v in ic_report.values()
        )
    elif rolling.get('90d') and rolling['90d'] > RETRAIN_MAE_THRESHOLD:
        retrain_flag = True

    # Load latest snapshots for trend signals — keep most-recent DATE per ticker
    latest_snap: Dict[str, dict] = {}
    try:
        with open(SNAPSHOT_LOG) as f:
            for line in f:
                try:
                    r = json.loads(line.strip())
                    tkr = r['ticker']
                    if tkr not in latest_snap or r['date'] > latest_snap[tkr]['date']:
                        latest_snap[tkr] = r
                except Exception:
                    pass
    except FileNotFoundError:
        pass

    # Sector trend signals
    sector_trend: Dict[str, dict] = defaultdict(lambda: {'above_ma200': 0, 'total': 0, 'momentum': []})
    for tkr, s in latest_snap.items():
        tag = s.get('tag', 'unknown')
        price = s.get('price')
        ma200 = s.get('ma200')
        mom   = s.get('momentum_30d')
        sector_trend[tag]['total'] += 1
        if price and ma200 and price > ma200:
            sector_trend[tag]['above_ma200'] += 1
        if mom is not None:
            sector_trend[tag]['momentum'].append(mom)

    sector_signals = {}
    for tag, data in sector_trend.items():
        total = data['total']
        if total == 0:
            continue
        moms = data['momentum']
        sector_signals[tag] = {
            'pct_above_ma200': round(data['above_ma200'] / total * 100, 1),
            'avg_momentum_30d': round(sum(moms) / len(moms) * 100, 2) if moms else None,
            'n': total,
        }

    # Current regime from latest snapshot
    regime_today = 'unknown'
    vix_today    = None
    if latest_snap:
        sample = next(iter(latest_snap.values()))
        regime_today = sample.get('regime', 'unknown')
        vix_today    = sample.get('vix')

    summary = {
        'generated_at':         today.isoformat(),
        'n_total':              len(records),
        'overall_mae':          overall_mae,
        'rolling_mae':          rolling,
        'ic_by_horizon':        ic_report,
        'ic_by_regime':         ic_by_regime_report,
        'hit_rate_by_quintile': hit_rate_by_quintile,
        'by_horizon':           {str(k): {'mae': _mae(v), 'n': len(v)} for k, v in sorted(by_horizon.items())},
        'by_regime':            {k: {'mae': _mae(v), 'n': len(v)} for k, v in by_regime.items()},
        'worst_tags':           dict(worst_tags),
        'sector_trends':        sector_signals,
        'retrain_flag':         retrain_flag,
        'regime_today':         regime_today,
        'vix_today':            vix_today,
    }

    lines = [
        f'AXIOM ML Monitor Report  {today.isoformat()}',
        f'VIX={vix_today}  regime={regime_today}',
        '',
        f'Total scored: {len(records)}',
    ]

    # IC section — primary metric
    v1_count = sum(1 for r in records if r.get('eval_version') == 1)
    lines.append(f'Eval v1 records (excess return, correct): {v1_count}')
    if ic_report:
        lines += ['', 'Rank IC (eval_version=1 only):']
        for h, ic in ic_report.items():
            tstat_str = f't={ic["t_stat"]:+.2f}' if ic['t_stat'] is not None else 't=n/a'
            skill = ('  ✓ SKILL SIGNAL' if ic['t_stat'] and ic['t_stat'] >= 2.0
                     else '  (insufficient data)' if ic['n_periods'] < 3
                     else '')
            lines.append(
                f'  {h+"d":<7} mean_IC={ic["mean_ic"]:+.4f}  '
                f'std={ic["ic_std"]:.4f}  {tstat_str}  '
                f'n_periods={ic["n_periods"]}{skill}'
            )
    else:
        lines.append('  (no eval_version=1 records yet — run snapshot with ETF logging first)')

    # IC by regime
    if ic_by_regime_report:
        lines += ['', 'Rank IC by regime (eval_version=1 only):']
        for reg, ic in ic_by_regime_report.items():
            if ic['n_periods'] == 0:
                continue
            tstat_str = f't={ic["t_stat"]:+.2f}' if ic['t_stat'] is not None else 't=n/a'
            lines.append(
                f'  {reg:<12} mean_IC={ic["mean_ic"]:+.4f}  '
                f'std={ic["ic_std"]:.4f}  {tstat_str}  n={ic["n_periods"]}'
            )

    # Hit rate by quintile
    if hit_rate_by_quintile:
        lines += ['', 'Hit rate by quintile (Q1=top predicted, beat median actual):']
        for q, v in hit_rate_by_quintile.items():
            hr = f'{v["hit_rate"]:.1%}' if v['hit_rate'] is not None else 'n/a'
            lines.append(f'  {q}: {hr}  (n_periods={v["n_periods"]})')
        q1 = hit_rate_by_quintile.get('Q1', {}).get('hit_rate')
        q5 = hit_rate_by_quintile.get('Q5', {}).get('hit_rate')
        if q1 is not None and q5 is not None:
            lines.append(f'  Spread Q1−Q5: {q1 - q5:+.1%}  (target > 0)')

    lines += ['', f'Overall MAE (all records): {overall_mae}', 'Rolling MAE:']
    for w, mae in rolling.items():
        flag = '  ← RETRAIN RECOMMENDED' if w == '90d' and retrain_flag else ''
        lines.append(f'  {w:<6} {mae}{flag}')

    lines += ['', 'By horizon (days):']
    for h, v in sorted(by_horizon.items()):
        lines.append(f'  {str(h)+"d":<7} n={len(v):>4}  MAE={_mae(v):.4f}')

    lines += ['', 'By regime:']
    for reg, v in by_regime.items():
        lines.append(f'  {reg:<12} n={len(v):>4}  MAE={_mae(v):.4f}')

    lines += ['', 'Worst sectors (by MAE):']
    for tag, v in worst_tags:
        lines.append(f'  {tag:<32} n={v["n"]:>3}  MAE={v["mae"]:.4f}')

    lines += ['', 'Sector trend signals (latest snapshot):']
    strong_buy  = [(t, s) for t, s in sector_signals.items() if s['pct_above_ma200'] >= 70]
    weak_signal = [(t, s) for t, s in sector_signals.items() if s['pct_above_ma200'] <= 30]
    lines.append('  Bullish (>70% above MA200):')
    for t, s in sorted(strong_buy, key=lambda x: -x[1]['pct_above_ma200'])[:8]:
        lines.append(f'    {t:<32} {s["pct_above_ma200"]}%  mom={s["avg_momentum_30d"]}%')
    lines.append('  Bearish (<30% above MA200):')
    for t, s in sorted(weak_signal, key=lambda x: x[1]['pct_above_ma200'])[:8]:
        lines.append(f'    {t:<32} {s["pct_above_ma200"]}%  mom={s["avg_momentum_30d"]}%')

    if retrain_flag:
        lines += ['', '*** RETRAIN SIGNAL: 90d MAE exceeds threshold — run ml.walk_forward ***']

    text = '\n'.join(lines) + '\n'
    with open(REPORT_FILE, 'w') as f:
        f.write(text)

    if print_output:
        print(text)

    return summary


# ── Retroactive backfill (populate past weekday snapshots) ────────────────────

def backfill_snapshots(n_weekdays: int = 10) -> int:
    """
    Fetch closing prices for each weekday in the past n_weekdays and log them
    as if the daily snapshot had run on each of those days.
    Uses a single bulk yfinance download per ticker-chunk (not per-date), so
    55 weekdays runs in ~30 seconds instead of ~15 minutes.
    Skips (date, ticker) pairs already in the log.
    Returns total records written.
    """
    import yfinance as yf
    import pandas as pd
    from valuation._config import TICKER_TAG_MAP
    from ml.walk_forward import _composite_regime

    tickers = sorted(TICKER_TAG_MAP.keys())
    today   = date.today()

    # Collect the target weekdays
    target_dates: List[date] = []
    d = today - timedelta(days=1)
    while len(target_dates) < n_weekdays:
        if d.weekday() < 5:
            target_dates.append(d)
        d -= timedelta(days=1)
    target_dates = sorted(target_dates)

    print(f'Backfilling {n_weekdays} weekdays: {target_dates[0]} → {target_dates[-1]}')

    # Already-logged (date, ticker) pairs — skip duplicates
    logged: set = set()
    try:
        with open(SNAPSHOT_LOG) as f:
            for line in f:
                try:
                    r = json.loads(line.strip())
                    logged.add((r['date'], r['ticker']))
                except Exception:
                    pass
    except FileNotFoundError:
        pass

    # Regime/VIX/ETF momentums — metadata only; doesn't affect MAE computation
    regime    = _composite_regime(today.year, month=today.month)
    vix_level, _ = _fetch_vix()
    etf_moms  = _fetch_etf_momentums()
    print(f'  Regime: {regime}  VIX: {vix_level:.1f}')

    # Determine which dates actually need work
    dates_needed = [
        td for td in target_dates
        if any((td.isoformat(), t) not in logged for t in tickers)
    ]
    if not dates_needed:
        print('  All dates already logged.')
        return 0

    # Bulk download: one yfinance call per 60-ticker chunk for the full range
    start_str = str(target_dates[0])
    end_str   = str(today + timedelta(days=1))   # yfinance end is exclusive

    CHUNK = 60
    n_chunks = (len(tickers) - 1) // CHUNK + 1
    # price_matrix[ticker][date_str] = closing_price
    price_matrix: Dict[str, Dict[str, float]] = {}

    for i in range(0, len(tickers), CHUNK):
        chunk = tickers[i:i + CHUNK]
        chunk_n = i // CHUNK + 1
        print(f'  Chunk {chunk_n}/{n_chunks}: downloading {len(chunk)} tickers {start_str}→{end_str}...', end='', flush=True)
        try:
            raw = yf.download(
                chunk, start=start_str, end=end_str,
                progress=False, auto_adjust=True,
                group_by='ticker',
            )
            if raw.empty:
                print(' empty')
                continue
            for tkr in chunk:
                try:
                    if len(chunk) == 1:
                        series = raw['Close'].dropna()
                    else:
                        series = raw[tkr]['Close'].dropna()
                    if series.empty:
                        continue
                    tkr_prices: Dict[str, float] = {}
                    for td in target_dates:
                        td_str = td.isoformat()
                        if (td_str, tkr) in logged:
                            continue
                        # Forward-fill: first available date on or after td
                        future = series[series.index >= pd.Timestamp(td)]
                        if future.empty:
                            continue
                        tkr_prices[td_str] = float(future.iloc[0])
                    if tkr_prices:
                        price_matrix[tkr] = tkr_prices
                except Exception:
                    pass
            print(f' ok ({len([t for t in chunk if t in price_matrix])} got prices)')
        except Exception as e:
            print(f' error: {e}')

    # Load DB data needed for factor computation (fetched once, used for all dates)
    from ml.walk_forward import _TAG_ETF, _TAG_VOL, _VOL_DEFAULT
    dcf_prices = _fetch_last_dcf_prices()
    quality_db = _fetch_quality_data()

    # Also bulk-download ETF prices over the same date range for value/excess-return
    unique_etfs = sorted(set(_TAG_ETF.values()) | {'SPY'})
    etf_matrix: Dict[str, Dict[str, float]] = {}  # etf → {date_str: price}
    try:
        raw_etf = yf.download(
            unique_etfs, start=start_str, end=end_str,
            progress=False, auto_adjust=True, group_by='ticker',
        )
        if not raw_etf.empty:
            for etf in unique_etfs:
                try:
                    s = (raw_etf['Close'].dropna() if len(unique_etfs) == 1
                         else raw_etf[etf]['Close'].dropna())
                    if s.empty:
                        continue
                    etf_series: Dict[str, float] = {}
                    for td in target_dates:
                        future = s[s.index >= pd.Timestamp(td)]
                        if not future.empty:
                            etf_series[td.isoformat()] = round(float(future.iloc[0]), 4)
                    if etf_series:
                        etf_matrix[etf] = etf_series
                except Exception:
                    pass
    except Exception as e:
        print(f'  ETF matrix fetch failed: {e}')

    total_written = 0

    with open(SNAPSHOT_LOG, 'a') as f:
        for td in target_dates:
            td_str = td.isoformat()

            # ── Pass 1: collect raw factor values for this date ───────────────
            raw_recs: List[dict] = []
            for tkr in tickers:
                if (td_str, tkr) in logged:
                    continue
                price = price_matrix.get(tkr, {}).get(td_str)
                if price is None:
                    continue

                tag        = TICKER_TAG_MAP.get(tkr.upper(), 'diversified')
                vol        = _TAG_VOL.get(tag, _VOL_DEFAULT)
                etf_ticker = _TAG_ETF.get(tag, 'SPY')
                etf_price  = etf_matrix.get(etf_ticker, {}).get(td_str) or \
                             etf_matrix.get('SPY', {}).get(td_str)
                dcf_price  = dcf_prices.get(tkr.upper())
                value_factor = (round(dcf_price / price - 1.0, 4)
                                if (dcf_price and price > 0) else None)

                q_data      = quality_db.get(tkr.upper())
                quality_raw = _compute_quality_factor(q_data, price) if q_data else None

                raw_recs.append({
                    'date':              td_str,
                    'ticker':            tkr,
                    'tag':               tag,
                    'regime':            regime,
                    'vix':               round(vix_level, 2),
                    'price':             round(price, 4),
                    'ma50':              None,
                    'ma200':             None,
                    'momentum_30d':      None,
                    'momentum_12_1':     None,
                    'volatility_sector': round(vol, 4),
                    'etf_ticker':        etf_ticker,
                    'etf_price':         etf_price,
                    'dcf_price':         dcf_price,
                    'value_factor':      value_factor,
                    'quality_raw':       quality_raw,
                })

            if not raw_recs:
                print(f'  {td_str}: already fully logged — skipped')
                continue

            # ── Pass 2: cross-sectional Z-scores within sub-sector tag ────────
            z_value   = _zscore_within_tag(raw_recs, 'value_factor')
            z_quality = _zscore_within_tag(raw_recs, 'quality_raw')
            # momentum_12_1 is None for backfill (no long price history available)
            # so z_momentum will be None — composite uses what's available

            # ── Pass 3: attach scores, run ML, write ──────────────────────────
            written = 0
            for rec in raw_recs:
                tkr = rec['ticker']
                zv  = z_value.get(tkr)
                zq  = z_quality.get(tkr)
                z_vals    = [v for v in [zv, zq] if v is not None]
                composite = round(sum(z_vals) / len(z_vals), 4) if z_vals else None

                rec['z_value']         = zv
                rec['z_momentum']      = None   # not computable from bulk-price backfill
                rec['z_quality']       = zq
                rec['composite_score'] = composite
                rec['predicted_correction'] = _ml_correction(
                    tkr, rec['tag'], regime,
                    etf_momentums=etf_moms,
                    snap_record=rec,
                )
                f.write(json.dumps(rec) + '\n')
                logged.add((td_str, tkr))
                written += 1

            total_written += written
            print(f'  {td_str}: wrote {written} records (z_scores included)')

    print(f'Backfill done — {total_written} new records')
    return total_written


# ── Historical snapshot patch (retroactively add ETF prices + factor Z-scores) ─

def patch_snapshot_log(lookback_days: int = 365, update_factors: bool = False) -> int:
    """
    Retroactively enrich existing snapshot records with ETF prices, factor Z-scores,
    and composite scores. Rewrites monitor_log.jsonl in-place.

    - Reads all existing records
    - For each date within lookback_days that has records missing etf_price:
        bulk-fetches ETF prices for that date range, recomputes value_factor,
        quality_raw, Z-scores, and composite_score
    - Writes a new log: patched records replace unpatched ones, others are kept

    This is the one-time migration that turns legacy snapshot records into
    eval_version=1-eligible data, so IC computation works without waiting
    a year for fresh data to accumulate.

    Returns: number of records patched.
    """
    import yfinance as yf
    import pandas as pd
    from valuation._config import TICKER_TAG_MAP
    from ml.walk_forward import _TAG_ETF, _TAG_VOL, _VOL_DEFAULT

    if not os.path.exists(SNAPSHOT_LOG):
        print('No snapshot log found.')
        return 0

    # Load all existing records
    all_records: List[dict] = []
    with open(SNAPSHOT_LOG) as f:
        for line in f:
            try:
                all_records.append(json.loads(line.strip()))
            except Exception:
                pass
    print(f'Loaded {len(all_records)} existing records from snapshot log')

    cutoff = (date.today() - timedelta(days=lookback_days)).isoformat()

    if update_factors:
        # Re-patch all records within window to update value_factor/Z-scores
        # using freshly-loaded DCF prices from the DB.
        to_patch   = [r for r in all_records if r.get('date', '') >= cutoff]
        already_ok = []
    else:
        to_patch   = [r for r in all_records
                      if r.get('date', '') >= cutoff and r.get('etf_price') is None]
        already_ok = [r for r in all_records
                      if r.get('date', '') >= cutoff and r.get('etf_price') is not None]

    older = [r for r in all_records if r.get('date', '') < cutoff]

    print(f'  Records within {lookback_days}d: {len(to_patch)} to patch'
          + (f' (factor refresh)' if update_factors else f', {len(already_ok)} already OK'))
    print(f'  Records older than {lookback_days}d: {len(older)} (kept as-is)')

    if not to_patch:
        print('Nothing to patch.')
        return 0

    # Determine date range for bulk ETF download (only needed when etf_price missing)
    dates_needing_etf = sorted({r['date'] for r in to_patch if r.get('etf_price') is None})
    dates_needed = dates_needing_etf if dates_needing_etf else sorted({r['date'] for r in to_patch})
    start_str = dates_needed[0]
    end_str   = (date.today() + timedelta(days=1)).isoformat()

    # Bulk download ETFs only when some records are missing etf_price
    unique_etfs = sorted(set(_TAG_ETF.values()) | {'SPY'})
    etf_history: Dict[str, object] = {}  # etf → pd.Series
    if dates_needing_etf:
        print(f'  Downloading {len(unique_etfs)} ETFs from {start_str} → {end_str}...')
    try:
        raw_etf = yf.download(
            unique_etfs, start=start_str, end=end_str,
            progress=False, auto_adjust=True, group_by='ticker',
        )
        if not raw_etf.empty:
            for etf in unique_etfs:
                try:
                    s = (raw_etf['Close'].dropna() if len(unique_etfs) == 1
                         else raw_etf[etf]['Close'].dropna())
                    if not s.empty:
                        etf_history[etf] = s
                except Exception:
                    pass
        print(f'  ETFs loaded: {len(etf_history)}')
    except Exception as e:
        print(f'  ETF download failed: {e} — patching ETF prices only where available')

    def _etf_price_on(etf: str, date_str: str) -> Optional[float]:
        s = etf_history.get(etf)
        if s is None:
            s = etf_history.get('SPY')
        if s is None:
            return None
        ts = pd.Timestamp(date_str)
        future = s[s.index >= ts]
        return round(float(future.iloc[0]), 4) if not future.empty else None

    # Load DB quality data (once)
    dcf_prices  = _fetch_last_dcf_prices()
    quality_db  = _fetch_quality_data()

    # Group to-patch records by date for cross-sectional Z-scoring
    by_date: Dict[str, List[dict]] = defaultdict(list)
    for r in to_patch:
        by_date[r['date']].append(r)

    patched_records: List[dict] = []
    n_patched = 0

    for date_str, recs in sorted(by_date.items()):
        # Pass 1: add ETF price, value_factor, quality_raw to each record
        raw_recs: List[dict] = []
        for r in recs:
            tag        = r.get('tag', TICKER_TAG_MAP.get(r['ticker'].upper(), 'diversified'))
            etf_ticker = _TAG_ETF.get(tag, 'SPY')
            etf_price  = _etf_price_on(etf_ticker, date_str)
            mkt_price  = r.get('price', 0)
            dcf_price  = dcf_prices.get(r['ticker'].upper())
            value_factor = (round(dcf_price / mkt_price - 1.0, 4)
                            if (dcf_price and mkt_price and mkt_price > 0) else None)
            q_data      = quality_db.get(r['ticker'].upper())
            quality_raw = _compute_quality_factor(q_data, mkt_price) if q_data else None

            rec = dict(r)
            rec['etf_ticker']   = etf_ticker
            # Preserve existing etf_price if already set; only write new one when fetched
            if rec.get('etf_price') is None and etf_price is not None:
                rec['etf_price'] = etf_price
            elif etf_price is not None:
                rec['etf_price'] = etf_price  # always update when update_factors=True
            rec['dcf_price']    = dcf_price
            rec['value_factor'] = value_factor
            rec['quality_raw']  = quality_raw
            # momentum_12_1 can't be computed retrospectively from bare close prices
            if 'momentum_12_1' not in rec:
                rec['momentum_12_1'] = None
            raw_recs.append(rec)

        # Pass 2: Z-score within tag
        z_value   = _zscore_within_tag(raw_recs, 'value_factor')
        z_quality = _zscore_within_tag(raw_recs, 'quality_raw')

        # Pass 3: attach scores
        for rec in raw_recs:
            tkr = rec['ticker']
            zv  = z_value.get(tkr)
            zq  = z_quality.get(tkr)
            z_vals    = [v for v in [zv, zq] if v is not None]
            rec['z_value']         = zv
            rec['z_momentum']      = rec.get('z_momentum')  # preserve if already set
            rec['z_quality']       = zq
            rec['composite_score'] = round(sum(z_vals) / len(z_vals), 4) if z_vals else None
            patched_records.append(rec)
            n_patched += 1

    # Write new log: older records + already-ok records + patched records, sorted by date
    combined = older + already_ok + patched_records
    combined.sort(key=lambda r: (r.get('date', ''), r.get('ticker', '')))

    tmp_path = SNAPSHOT_LOG + '.tmp'
    with open(tmp_path, 'w') as f:
        for rec in combined:
            f.write(json.dumps(rec) + '\n')
    os.replace(tmp_path, SNAPSHOT_LOG)

    print(f'patch_snapshot_log done — {n_patched} records patched, '
          f'{len(combined)} total records in log')
    return n_patched


# ── Historical backtest report (instant — no 90-day wait) ─────────────────────

def backtest_report(print_output: bool = True) -> dict:
    """
    Read the walk-forward validation history saved by run_monthly_rolling()
    and print sector / regime accuracy.  Runs instantly — no live fetching.
    """
    from ml.walk_forward import ML_MODEL_PATH
    bt_path = os.path.join(os.path.dirname(ML_MODEL_PATH), 'ml_backtest_history.json')

    if not os.path.exists(bt_path):
        msg = 'No backtest history — run: python3 -m ml.walk_forward'
        if print_output:
            print(msg)
        return {'error': msg}

    with open(bt_path) as f:
        bt = json.load(f)

    today = date.today().isoformat()
    lines = [
        f'AXIOM Backtest Report  (generated {today})',
        f'Walk-forward computed: {bt.get("computed_at", "?")}',
        f'Training years: {bt.get("years")}   Window: {bt.get("window_months")}mo',
        f'Overall OOS MAE: {bt.get("overall_oos_mae")}   Periods: {bt.get("n_periods")}',
        '',
        'Monthly MAE trend (all validated periods):',
    ]

    periods = bt.get('periods', [])
    if periods:
        # Bar chart of MAE per period
        for p in periods:
            mae = p.get('mae') or 0.0
            bar = '|' * min(int(mae * 50), 30)
            lines.append(f'  {p["ym"]}  mae={mae:.4f}  {bar}')

        # Aggregate across all periods
        all_tag_errs: Dict[str, list] = defaultdict(list)
        all_reg_errs: Dict[str, list] = defaultdict(list)
        all_hz_errs:  Dict[str, list] = defaultdict(list)
        for p in periods:
            for tag, v in p.get('by_tag', {}).items():
                if v.get('mae') is not None:
                    all_tag_errs[tag].extend([v['mae']] * v['n'])
            for reg, v in p.get('by_regime', {}).items():
                if v.get('mae') is not None:
                    all_reg_errs[reg].extend([v['mae']] * v['n'])
            for hz, v in p.get('by_horizon', {}).items():
                if v.get('mae') is not None:
                    all_hz_errs[hz].extend([v['mae']] * v['n'])

        def _avg(lst): return round(sum(lst) / len(lst), 4) if lst else None

        lines.append('\nAggregate by horizon:')
        for hz in sorted(all_hz_errs, key=lambda x: int(x)):
            v = all_hz_errs[hz]
            lines.append(f'  {hz+"d":<7}  n={len(v):>6}  mae={_avg(v):.4f}')

        lines.append('\nAggregate by regime:')
        for reg in sorted(all_reg_errs):
            v = all_reg_errs[reg]
            lines.append(f'  {reg:<14}  n={len(v):>6}  mae={_avg(v):.4f}')

        lines.append('\nSector MAE (worst → best, all periods):')
        tag_summary = sorted(
            [(t, _avg(v), len(v)) for t, v in all_tag_errs.items() if v],
            key=lambda x: -(x[1] or 0)
        )
        for tag, mae, n in tag_summary[:15]:
            lines.append(f'  {tag:<32}  n={n:>5}  mae={mae:.4f}')

    # Latest snapshot line
    try:
        with open(SNAPSHOT_LOG) as f:
            snaps = [json.loads(l) for l in f if l.strip()]
        if snaps:
            s = max(snaps, key=lambda x: x.get('date', ''))
            lines.append(f'\nLatest snapshot: {s["date"]}  regime={s.get("regime")}  vix={s.get("vix")}')
    except Exception:
        pass

    text = '\n'.join(lines) + '\n'
    if print_output:
        print(text)
    return bt


def retrain(years: Optional[List[int]] = None, window: int = 12) -> None:
    """Re-run the full monthly rolling walk-forward and update the production model."""
    from ml.walk_forward import run as wf_run
    print(f'Retraining on years={years or [2022, 2023, 2024]}  window={window}mo ...')
    wf_run(years=years, mode='monthly', window=window)
    print('Retrain complete — model updated.')


# ── Auto-retrain ───────────────────────────────────────────────────────────────

def _check_and_retrain() -> None:
    """
    Load recent evaluation cycles. If MAE has been above threshold for
    RETRAIN_TRIGGER_COUNT consecutive weekly evaluations, retrain the model.
    """
    records = _load_eval()
    if not records:
        return

    # Group by week
    weekly: Dict[str, List[float]] = defaultdict(list)
    for r in records:
        week = (date.fromisoformat(r['eval_date']) - timedelta(days=7)).isoformat()[:10]
        if r.get('abs_error') is not None:
            weekly[week].append(r['abs_error'])

    # Check last N weeks
    recent_weeks = sorted(weekly.keys())[-RETRAIN_TRIGGER_COUNT:]
    if len(recent_weeks) < RETRAIN_TRIGGER_COUNT:
        return

    above_threshold = all(
        sum(weekly[w]) / len(weekly[w]) > RETRAIN_MAE_THRESHOLD
        for w in recent_weeks
        if weekly[w]
    )

    if above_threshold:
        print(f'Auto-retrain triggered: {RETRAIN_TRIGGER_COUNT} consecutive weeks above MAE={RETRAIN_MAE_THRESHOLD}')
        try:
            from ml.walk_forward import run as wf_run
            wf_run()
        except Exception as e:
            logger.error('Auto-retrain failed: %s', e)


# ── Cron setup ─────────────────────────────────────────────────────────────────

def setup_cron() -> None:
    """
    Install cron jobs for daily snapshot + weekly evaluate+report.
    Appends to the current user's crontab (non-destructive).
    """
    python  = sys.executable
    app_dir = _APP_DIR
    script  = f'cd {app_dir} && {python} -m ml.monitor'

    cron_lines = [
        f'# AXIOM ML Monitor (added {date.today().isoformat()})',
        f'30 21 * * 1-5  {script} --snapshot >> {app_dir}/monitor_cron.log 2>&1',
        f'0  10 * * 0    {script} --evaluate --report >> {app_dir}/monitor_cron.log 2>&1',
    ]

    # Read existing crontab
    try:
        existing = subprocess.check_output(['crontab', '-l'], stderr=subprocess.DEVNULL).decode()
    except subprocess.CalledProcessError:
        existing = ''

    # Skip if already installed
    if '--snapshot' in existing and 'AXIOM' in existing:
        print('Cron jobs already installed.')
        return

    new_crontab = existing.rstrip() + '\n\n' + '\n'.join(cron_lines) + '\n'
    proc = subprocess.run(['crontab', '-'], input=new_crontab.encode(), capture_output=True)
    if proc.returncode == 0:
        print('Cron jobs installed:')
        for line in cron_lines:
            print(f'  {line}')
        print(f'\nLogs → {app_dir}/monitor_cron.log')
    else:
        print('crontab install failed:', proc.stderr.decode())
        print('Add these lines manually to your crontab (crontab -e):')
        for line in cron_lines:
            print(f'  {line}')


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    import argparse
    logging.basicConfig(level=logging.WARNING)

    # Suppress noisy yfinance errors for known-delisted tickers — they're handled gracefully
    logging.getLogger('yfinance').setLevel(logging.CRITICAL)

    ap = argparse.ArgumentParser(description='AXIOM autonomous market monitor')
    ap.add_argument('--snapshot',         action='store_true', help='Fetch current prices + log')
    ap.add_argument('--evaluate',         action='store_true', help='Score old predictions vs actuals')
    ap.add_argument('--report',           action='store_true', help='Print accuracy + trend report')
    ap.add_argument('--all',              action='store_true', help='Run snapshot + evaluate + report')
    ap.add_argument('--backtest-report',  action='store_true', help='Show historical backtest quality (instant)')
    ap.add_argument('--backfill',         action='store_true', help='Log retroactive snapshots for past N weekdays')
    ap.add_argument('--backfill-days',    type=int, default=10, help='How many weekdays to backfill (default 10)')
    ap.add_argument('--patch',            action='store_true', help='Retroactively add ETF prices + Z-scores to existing snapshot records')
    ap.add_argument('--patch-days',       type=int, default=730, help='How many calendar days back to patch (default 730)')
    ap.add_argument('--patch-factors',    action='store_true', help='Re-compute value_factor + Z-scores for ALL records (use after bulk import)')
    ap.add_argument('--retrain',          action='store_true', help='Re-run walk-forward and update model')
    ap.add_argument('--setup-cron',       action='store_true', help='Install cron jobs')
    ap.add_argument('--auto-retrain',     action='store_true', help='Check drift and retrain if needed')
    ap.add_argument('--years',            nargs='+', type=int, default=None, help='Years for --retrain')
    ap.add_argument('--window',           type=int, default=12, help='Window months for --retrain')
    args = ap.parse_args()

    if args.setup_cron:
        setup_cron()
        sys.exit(0)

    if args.retrain:
        retrain(years=args.years, window=args.window)
        sys.exit(0)

    if args.backfill:
        backfill_snapshots(n_weekdays=args.backfill_days)

    if args.patch or args.patch_factors:
        patch_snapshot_log(lookback_days=args.patch_days,
                           update_factors=args.patch_factors)

    if args.all or args.snapshot:
        snapshot()

    if args.all or args.evaluate:
        evaluate()
        _check_and_retrain()

    if args.all or args.report:
        report()

    if args.backtest_report:
        backtest_report()

    if not any([args.snapshot, args.evaluate, args.report, args.all,
                args.backtest_report, args.backfill, args.retrain,
                args.setup_cron, args.auto_retrain]):
        ap.print_help()
