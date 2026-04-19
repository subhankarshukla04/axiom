"""
Alert Engine
Rule-based alerts stored in DB, surfaced in sidebar badge.
Alert types: earnings_revision, insider_cluster, macro_move, anomaly
"""

import sqlite3
import json
import logging
import os
from datetime import datetime, timedelta
from typing import List, Optional, Dict

logger = logging.getLogger(__name__)

ALERT_TYPES = ['earnings_revision', 'insider_cluster', 'macro_move', 'anomaly']
SEVERITY_LEVELS = ['info', 'warning', 'critical']


def _get_db():
    """Get SQLite connection to the main valuations DB."""
    for db in ['valuations.db', 'valuation.db']:
        if os.path.exists(db):
            conn = sqlite3.connect(db)
            conn.row_factory = sqlite3.Row
            return conn
    conn = sqlite3.connect('valuations.db')
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_table():
    """Create alerts table if it doesn't exist."""
    conn = _get_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER,
            alert_type TEXT,
            severity TEXT DEFAULT 'info',
            message TEXT,
            detail_json TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            is_read INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()


def create_alert(
    alert_type: str,
    message: str,
    company_id: Optional[int] = None,
    severity: str = 'info',
    detail: Optional[Dict] = None,
) -> int:
    """
    Create a new alert in the database.
    Returns the new alert ID.
    """
    _ensure_table()
    if alert_type not in ALERT_TYPES:
        raise ValueError(f'Invalid alert_type: {alert_type}. Must be one of {ALERT_TYPES}')
    if severity not in SEVERITY_LEVELS:
        severity = 'info'

    conn = _get_db()
    cur = conn.execute('''
        INSERT INTO alerts (company_id, alert_type, severity, message, detail_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (
        company_id,
        alert_type,
        severity,
        message,
        json.dumps(detail or {}),
        datetime.utcnow().isoformat(),
    ))
    alert_id = cur.lastrowid
    conn.commit()
    conn.close()
    logger.info(f'Created alert #{alert_id}: [{severity}] {alert_type} — {message[:60]}')
    return alert_id


def get_unread_alerts(limit: int = 50) -> List[Dict]:
    """Fetch unread alerts, newest first."""
    _ensure_table()
    conn = _get_db()
    rows = conn.execute('''
        SELECT id, company_id, alert_type, severity, message, detail_json, created_at
        FROM alerts
        WHERE is_read = 0
        ORDER BY created_at DESC
        LIMIT ?
    ''', (limit,)).fetchall()
    conn.close()
    return [
        {
            'id': r['id'],
            'company_id': r['company_id'],
            'alert_type': r['alert_type'],
            'severity': r['severity'],
            'message': r['message'],
            'detail': json.loads(r['detail_json'] or '{}'),
            'created_at': r['created_at'],
        }
        for r in rows
    ]


def get_alert_count() -> int:
    """Get count of unread alerts for sidebar badge."""
    _ensure_table()
    conn = _get_db()
    count = conn.execute('SELECT COUNT(*) FROM alerts WHERE is_read = 0').fetchone()[0]
    conn.close()
    return count


def mark_read(alert_id: int):
    """Mark an alert as read."""
    _ensure_table()
    conn = _get_db()
    conn.execute('UPDATE alerts SET is_read = 1 WHERE id = ?', (alert_id,))
    conn.commit()
    conn.close()


def mark_all_read():
    """Mark all alerts as read."""
    _ensure_table()
    conn = _get_db()
    conn.execute('UPDATE alerts SET is_read = 1')
    conn.commit()
    conn.close()


def check_macro_move_alert(company_id: Optional[int] = None):
    """
    Check if 10Y Treasury moved >25bps week-over-week.
    Creates an alert if so.
    Requires FRED data layer to be available.
    """
    try:
        from data_layer import DataLayer
        dl = DataLayer()
        current_rate_result = dl.fred.get_series('DGS10')
        if not current_rate_result.available:
            return

        current_rate = current_rate_result.value
        # Get 1-week-ago rate (simplified: compare against cached prior value)
        cache_key = 'alert_engine:prior_dgs10'
        prior = dl.cache.get(cache_key)
        if prior is None:
            # First run — store current rate, check next time
            dl.cache.set(cache_key, {'rate': current_rate, 'stored_at': datetime.utcnow().isoformat()}, source_type='default')
            return

        prior_rate = prior.get('rate', current_rate)
        change_bps = abs(current_rate - prior_rate) * 100

        if change_bps >= 25:
            create_alert(
                alert_type='macro_move',
                message=f'10Y Treasury moved {change_bps:.0f}bps — WACC inputs may need update',
                company_id=company_id,
                severity='warning',
                detail={
                    'prior_rate': prior_rate,
                    'current_rate': current_rate,
                    'change_bps': change_bps,
                    'source': 'FRED:DGS10',
                },
            )
            # Update stored rate
            dl.cache.set(cache_key, {'rate': current_rate, 'stored_at': datetime.utcnow().isoformat()}, source_type='default')

    except Exception as e:
        logger.debug(f'Macro move alert check failed: {e}')


def check_anomaly_alerts(assumptions: dict, sector: str, company_id: Optional[int] = None):
    """
    Run anomaly detection and create alerts for critical findings.
    """
    try:
        from intelligence.anomaly_detector import analyze_assumptions
        anomalies = analyze_assumptions(assumptions, sector)
        for anomaly in anomalies:
            if anomaly.get('severity') in ('warning', 'critical'):
                create_alert(
                    alert_type='anomaly',
                    message=anomaly['message'],
                    company_id=company_id,
                    severity=anomaly['severity'],
                    detail=anomaly,
                )
    except Exception as e:
        logger.debug(f'Anomaly alert check failed: {e}')


def check_earnings_revision_alert(ticker: str, company_id: Optional[int] = None):
    """Alert if EPS estimate revised >5% vs prior quarter estimate via Finnhub."""
    try:
        import urllib.request, json as _json
        finnhub_key = os.environ.get('FINNHUB_API_KEY', '')
        if not finnhub_key:
            logger.debug('FINNHUB_API_KEY not set — skipping earnings revision check')
            return

        url = f'https://finnhub.io/api/v1/stock/eps-estimate?symbol={ticker}&freq=quarterly&token={finnhub_key}'
        req = urllib.request.Request(url, headers={'User-Agent': 'AXIOM-Platform axiom@example.com'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = _json.loads(resp.read().decode())

        estimates = data.get('data', [])
        if len(estimates) < 2:
            return

        latest_eps = estimates[0].get('epsAvg')
        prior_eps = estimates[1].get('epsAvg')
        if not latest_eps or not prior_eps or prior_eps == 0:
            return

        revision_pct = abs((latest_eps - prior_eps) / prior_eps) * 100
        if revision_pct >= 5:
            direction = 'upward' if latest_eps > prior_eps else 'downward'
            severity = 'warning' if revision_pct < 15 else 'critical'
            create_alert(
                alert_type='earnings_revision',
                message=f'{ticker}: EPS estimate revised {direction} {revision_pct:.1f}% — '
                        f'consensus now ${latest_eps:.2f} (was ${prior_eps:.2f})',
                company_id=company_id,
                severity=severity,
                detail={
                    'ticker': ticker,
                    'latest_eps': latest_eps,
                    'prior_eps': prior_eps,
                    'revision_pct': revision_pct,
                    'direction': direction,
                    'source': 'Finnhub',
                },
            )
    except Exception as e:
        logger.debug(f'Earnings revision alert check failed for {ticker}: {e}')


def check_insider_cluster_alert(
    ticker: str,
    company_id: Optional[int] = None,
    window_days: int = 30,
    min_insiders: int = 3,
):
    """Alert if 3+ insiders filed Form 4 within window_days via SEC EDGAR."""
    try:
        from data_layer import DataLayer
        dl = DataLayer()
        result = dl.edgar.get_form4(ticker, limit=50)
        if not result.available or not result.value:
            return

        cutoff = datetime.utcnow() - timedelta(days=window_days)
        cutoff_str = cutoff.strftime('%Y-%m-%d')
        recent = [t for t in result.value if t.get('filing_date', '') >= cutoff_str]

        if len(recent) >= min_insiders:
            severity = 'warning' if len(recent) < 5 else 'critical'
            create_alert(
                alert_type='insider_cluster',
                message=f'{ticker}: {len(recent)} insider Form 4 filings in last {window_days} days',
                company_id=company_id,
                severity=severity,
                detail={
                    'ticker': ticker,
                    'filing_count': len(recent),
                    'window_days': window_days,
                    'earliest': recent[-1].get('filing_date') if recent else None,
                    'latest': recent[0].get('filing_date') if recent else None,
                    'source': 'SEC EDGAR Form 4',
                },
            )
    except Exception as e:
        logger.debug(f'Insider cluster alert check failed for {ticker}: {e}')
