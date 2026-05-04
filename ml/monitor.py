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


def _fetch_snapshot_prices(tickers: List[str], period: str = '210d') -> Dict[str, dict]:
    """
    Batch-fetch recent history for all tickers.
    Returns {ticker: {price, ma50, ma200, momentum_30d}}.
    210d covers enough history for MA200.
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
                    price_now = float(prices.iloc[-1])
                    ma50  = float(prices.iloc[-50:].mean()) if len(prices) >= 50 else None
                    ma200 = float(prices.iloc[-200:].mean()) if len(prices) >= 200 else None
                    price_30d_ago = float(prices.iloc[-30]) if len(prices) >= 30 else None
                    momentum = (price_now / price_30d_ago - 1.0) if price_30d_ago else None
                    result[tkr] = {
                        'price':        price_now,
                        'ma50':         round(ma50, 4) if ma50 else None,
                        'ma200':        round(ma200, 4) if ma200 else None,
                        'momentum_30d': round(momentum, 4) if momentum is not None else None,
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
                    etf_momentums: Optional[Dict[str, float]] = None) -> Optional[float]:
    """
    Apply the trained ML model if available.
    etf_momentums: pre-fetched {etf_ticker: momentum} dict (compute once per snapshot run).
    Returns predicted correction factor (ratio), or None if model absent.
    """
    try:
        import numpy as np
        from ml.walk_forward import build_wf_features, _TAG_ETF
        from ml.calibrator import ML_MODEL_PATH, ML_METADATA_PATH
        import pickle

        if not os.path.exists(ML_MODEL_PATH):
            return None

        with open(ML_MODEL_PATH, 'rb') as f:
            pipeline = pickle.load(f)

        n_features = 10
        if os.path.exists(ML_METADATA_PATH):
            with open(ML_METADATA_PATH) as mf:
                n_features = json.load(mf).get('n_features', 10)

        from ml.calibrator import _TAG_VOL_DEFAULT, _VOL_DEFAULT
        vol = _TAG_VOL_DEFAULT.get(tag, _VOL_DEFAULT)

        etf_mom = 0.0
        if n_features >= 11 and etf_momentums is not None:
            etf = _TAG_ETF.get(tag, 'SPY')
            etf_mom = etf_momentums.get(etf, etf_momentums.get('SPY', 0.0))

        if n_features >= 11:
            feat = build_wf_features(tag, regime, horizon_days=365,
                                     month=datetime.now().month, volatility=vol,
                                     etf_momentum=etf_mom)
        elif n_features >= 10:
            feat = build_wf_features(tag, regime, horizon_days=365,
                                     month=datetime.now().month, volatility=vol)
        elif n_features == 9:
            feat = build_wf_features(tag, regime, horizon_days=365,
                                     month=datetime.now().month)
        else:
            from ml.calibrator import _build_features
            feat = _build_features({
                'sub_sector_tag': tag, 'company_type': '', 'wacc': 0.09,
                'growth_y1': 0.05, 'ebitda_method': '', 'analyst_target': 0,
                'predicted_price': 1.0, 'market_regime': regime,
            })

        return round(float(pipeline.predict(np.array([feat]))[0]), 4)
    except Exception as e:
        logger.debug('ml_correction failed for %s: %s', ticker, e)
        return None


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
    from ml.walk_forward import _composite_regime
    regime = _composite_regime(date.today().year, month=date.today().month)
    etf_moms = _fetch_etf_momentums()
    print(f'Snapshot {today}  VIX={vix_level:.1f}  regime={regime}')

    prices = _fetch_snapshot_prices(tickers)
    print(f'  Fetched {len(prices)}/{len(tickers)} tickers')

    written = 0
    with open(SNAPSHOT_LOG, 'a') as f:
        for tkr, p in prices.items():
            if tkr in logged_today:
                continue
            tag = TICKER_TAG_MAP.get(tkr.upper(), 'diversified')
            from ml.calibrator import _TAG_VOL_DEFAULT, _VOL_DEFAULT
            vol = _TAG_VOL_DEFAULT.get(tag, _VOL_DEFAULT)
            correction = _ml_correction(tkr, tag, regime, etf_momentums=etf_moms)
            f.write(json.dumps({
                'date':                 today,
                'ticker':               tkr,
                'tag':                  tag,
                'regime':               regime,
                'vix':                  round(vix_level, 2),
                'price':                p['price'],
                'ma50':                 p['ma50'],
                'ma200':                p['ma200'],
                'momentum_30d':         p['momentum_30d'],
                'volatility_sector':    round(vol, 4),
                'predicted_correction': correction,
            }) + '\n')
            written += 1

    if written:
        print(f'  Logged {written} snapshots → {os.path.basename(SNAPSHOT_LOG)}')
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

                for r in to_score:
                    tkr = r['ticker']
                    actual = actual_prices.get(tkr)
                    if actual is None:
                        continue

                    snap_price = r['price']
                    actual_correction  = round(actual / snap_price, 4)
                    pred_correction    = r['predicted_correction']
                    abs_err = abs(pred_correction - actual_correction)
                    all_errors.append(abs_err)

                    eval_record = {
                        'snapshot_date':      snap_date_str,
                        'eval_date':          eval_date.isoformat(),
                        'ticker':             tkr,
                        'tag':                r.get('tag', ''),
                        'regime':             r.get('regime', ''),
                        'horizon_days':       horizon,
                        'snap_price':         snap_price,
                        'actual_price':       round(actual, 4),
                        'actual_correction':  actual_correction,
                        'predicted_correction': pred_correction,
                        'abs_error':          round(abs_err, 4),
                    }
                    f.write(json.dumps(eval_record) + '\n')
                    evaluated.add((snap_date_str, tkr, horizon))
                    written += 1

    mae = round(sum(all_errors) / len(all_errors), 4) if all_errors else None
    print(f'Evaluated {written} new records  rolling MAE={mae}')
    return {'n_evaluated': written, 'rolling_mae': mae}


# ── Reporting & drift detection ────────────────────────────────────────────────

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

    def _mae(lst): return round(float(sum(lst) / len(lst)), 4) if lst else None

    overall_mae = _mae([r['abs_error'] for r in records if r.get('abs_error') is not None])
    rolling = {k: _mae(v) for k, v in by_window.items()}

    # Sector drift — top 10 worst tags
    tag_mae = {
        tag: {'mae': _mae(errs), 'n': len(errs)}
        for tag, errs in by_tag.items()
    }
    worst_tags = sorted(tag_mae.items(), key=lambda x: -(x[1]['mae'] or 0))[:10]

    # Retrain signal — check if recent MAE is deteriorating
    retrain_flag = False
    if rolling.get('90d') and rolling['90d'] > RETRAIN_MAE_THRESHOLD:
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
        'generated_at':  today.isoformat(),
        'n_total':       len(records),
        'overall_mae':   overall_mae,
        'rolling_mae':   rolling,
        'by_horizon':    {str(k): {'mae': _mae(v), 'n': len(v)} for k, v in sorted(by_horizon.items())},
        'by_regime':     {k: {'mae': _mae(v), 'n': len(v)} for k, v in by_regime.items()},
        'worst_tags':    dict(worst_tags),
        'sector_trends': sector_signals,
        'retrain_flag':  retrain_flag,
        'regime_today':  regime_today,
        'vix_today':     vix_today,
    }

    lines = [
        f'AXIOM ML Monitor Report  {today.isoformat()}',
        f'VIX={vix_today}  regime={regime_today}',
        '',
        f'Total scored: {len(records)}   Overall MAE: {overall_mae}',
        'Rolling MAE:',
    ]
    for w, mae in rolling.items():
        flag = '  ← RETRAIN RECOMMENDED' if w == '90d' and retrain_flag else ''
        lines.append(f'  {w:<6} {mae}{flag}')

    lines += ['', 'By horizon (days):']
    for h, v in sorted(by_horizon.items()):
        lines.append(f'  {str(h)+"d":<7} n={v.__len__():>4}  MAE={_mae(v):.4f}')

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

    # Write records date by date
    from ml.calibrator import _TAG_VOL_DEFAULT, _VOL_DEFAULT
    total_written = 0

    with open(SNAPSHOT_LOG, 'a') as f:
        for td in target_dates:
            td_str = td.isoformat()
            written = 0
            for tkr in tickers:
                if (td_str, tkr) in logged:
                    continue
                price = price_matrix.get(tkr, {}).get(td_str)
                if price is None:
                    continue
                tag = TICKER_TAG_MAP.get(tkr.upper(), 'diversified')
                vol = _TAG_VOL_DEFAULT.get(tag, _VOL_DEFAULT)
                correction = _ml_correction(tkr, tag, regime, etf_momentums=etf_moms)
                f.write(json.dumps({
                    'date':                 td_str,
                    'ticker':               tkr,
                    'tag':                  tag,
                    'regime':               regime,
                    'vix':                  round(vix_level, 2),
                    'price':                round(price, 4),
                    'ma50':                 None,
                    'ma200':                None,
                    'momentum_30d':         None,
                    'volatility_sector':    round(vol, 4),
                    'predicted_correction': correction,
                }) + '\n')
                logged.add((td_str, tkr))
                written += 1
            total_written += written
            if written:
                print(f'  {td_str}: wrote {written} records')
            else:
                print(f'  {td_str}: already fully logged — skipped')

    print(f'Backfill done — {total_written} new records')
    return total_written


# ── Historical backtest report (instant — no 90-day wait) ─────────────────────

def backtest_report(print_output: bool = True) -> dict:
    """
    Read the walk-forward validation history saved by run_monthly_rolling()
    and print sector / regime accuracy.  Runs instantly — no live fetching.
    """
    from ml.calibrator import ML_MODEL_PATH
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
