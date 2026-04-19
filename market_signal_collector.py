"""
Market Signal Collector
Fetches and caches analyst consensus data per company.
Feeds Layer 1 of the calibration architecture.
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Optional

import yfinance as yf

logger = logging.getLogger(__name__)

SIGNAL_CACHE_HOURS = 24  # refresh signals once per day


def collect_signals(ticker: str) -> Dict:
    """
    Fetch analyst signals for a ticker from yfinance.
    Returns a dict with consensus targets, forward estimates, and implied growth.
    """
    try:
        stock = yf.Ticker(ticker.upper())
        info = stock.info

        signals = {
            'ticker': ticker.upper(),
            'collected_at': datetime.utcnow().isoformat(),
            'analyst_target_mean': info.get('targetMeanPrice'),
            'analyst_target_median': info.get('targetMedianPrice'),
            'analyst_target_high': info.get('targetHighPrice'),
            'analyst_target_low': info.get('targetLowPrice'),
            'analyst_count': info.get('numberOfAnalystOpinions'),
            'recommendation_mean': info.get('recommendationMean'),  # 1=strong buy, 5=strong sell
            'forward_eps': info.get('forwardEps'),
            'forward_pe': info.get('forwardPE'),
            'forward_revenue_growth': info.get('revenueGrowth'),
            'trailing_pe': info.get('trailingPE'),
            'peg_ratio': info.get('pegRatio'),
            'current_price': info.get('currentPrice') or info.get('regularMarketPrice'),
            'implied_growth_rate': None,  # computed below
        }

        # Compute market-implied growth rate via simplified reverse DCF
        current_price = signals['current_price']
        if current_price and current_price > 0:
            try:
                financials = stock.financials
                balance_sheet = stock.balance_sheet
                cashflow = stock.cashflow

                revenue = 0
                ebitda_margin = 0.15
                capex_pct = 0.05
                tax_rate = 0.21
                debt = 0
                cash = 0
                shares = info.get('sharesOutstanding', 1e9)

                if financials is not None and not financials.empty:
                    col = financials.iloc[:, 0]
                    revenue = float(col.get('Total Revenue', 0) or 0)
                    ebitda = float(col.get('EBITDA', 0) or 0)
                    if revenue > 0:
                        ebitda_margin = ebitda / revenue

                if balance_sheet is not None and not balance_sheet.empty:
                    bs = balance_sheet.iloc[:, 0]
                    debt = float(bs.get('Total Debt', bs.get('Long Term Debt', 0)) or 0)
                    cash = float(bs.get('Cash And Cash Equivalents', 0) or 0)

                if cashflow is not None and not cashflow.empty:
                    cf = cashflow.iloc[:, 0]
                    capex = abs(float(cf.get('Capital Expenditure', 0) or 0))
                    if revenue > 0:
                        capex_pct = capex / revenue

                if revenue > 0 and shares and shares > 0:
                    target_equity = current_price * shares
                    implied_g = _reverse_dcf(
                        target_equity, revenue, ebitda_margin, capex_pct,
                        tax_rate, debt, cash, wacc=0.10, terminal_growth=0.025
                    )
                    signals['implied_growth_rate'] = implied_g
            except Exception as e:
                logger.debug(f'Implied growth calc failed for {ticker}: {e}')

        return signals

    except Exception as e:
        logger.error(f'collect_signals failed for {ticker}: {e}')
        return {'ticker': ticker.upper(), 'collected_at': datetime.utcnow().isoformat()}


def _reverse_dcf(target_equity: float, revenue: float, ebitda_margin: float,
                 capex_pct: float, tax_rate: float, debt: float, cash: float,
                 wacc: float = 0.10, terminal_growth: float = 0.025) -> Optional[float]:
    """Binary search for the growth rate that produces target_equity."""
    target_ev = target_equity + debt - cash

    def model_ev(g: float) -> float:
        ev = 0.0
        rev = revenue
        for yr in range(1, 11):
            decay = 0.88 ** (yr - 1)
            rev *= (1 + g * decay)
            ebitda = rev * ebitda_margin
            fcf = ebitda * (1 - tax_rate) - rev * capex_pct
            ev += fcf / (1 + wacc) ** yr
        fcf_terminal = rev * ebitda_margin * (1 - tax_rate) - rev * capex_pct
        tv = fcf_terminal * (1 + terminal_growth) / max(wacc - terminal_growth, 0.01)
        ev += tv / (1 + wacc) ** 10
        return ev

    lo, hi = -0.15, 0.80
    for _ in range(60):
        mid = (lo + hi) / 2
        if model_ev(mid) > target_ev:
            hi = mid
        else:
            lo = mid

    return round(mid, 4)


def get_cached_signals(ticker: str) -> Optional[Dict]:
    """
    Retrieve signals from DB if fresh (< SIGNAL_CACHE_HOURS old).
    Returns None if not found or stale.
    """
    try:
        from config import Config
        if Config.DATABASE_TYPE != 'postgresql':
            return None

        import psycopg2
        conn = psycopg2.connect(Config.get_db_connection_string())
        cur = conn.cursor()
        cur.execute(
            """SELECT analyst_target_mean, analyst_target_median, analyst_target_high,
                      analyst_target_low, analyst_count, recommendation_mean,
                      forward_eps, forward_pe, forward_revenue_growth,
                      implied_growth_rate, collected_at
               FROM market_signals
               WHERE ticker = %s
               ORDER BY collected_at DESC LIMIT 1""",
            (ticker.upper(),)
        )
        row = cur.fetchone()
        conn.close()

        if not row:
            return None

        collected_at = row[10]
        if isinstance(collected_at, str):
            collected_at = datetime.fromisoformat(collected_at)
        if datetime.utcnow() - collected_at.replace(tzinfo=None) > timedelta(hours=SIGNAL_CACHE_HOURS):
            return None

        return {
            'ticker': ticker.upper(),
            'analyst_target_mean': row[0],
            'analyst_target_median': row[1],
            'analyst_target_high': row[2],
            'analyst_target_low': row[3],
            'analyst_count': row[4],
            'recommendation_mean': row[5],
            'forward_eps': row[6],
            'forward_pe': row[7],
            'forward_revenue_growth': row[8],
            'implied_growth_rate': row[9],
            'collected_at': collected_at.isoformat(),
        }

    except Exception:
        return None


def store_signals(ticker: str, signals: Dict) -> None:
    """Upsert signals into market_signals table."""
    try:
        from config import Config
        if Config.DATABASE_TYPE != 'postgresql':
            return

        import psycopg2
        conn = psycopg2.connect(Config.get_db_connection_string())
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO market_signals
               (ticker, analyst_target_mean, analyst_target_median, analyst_target_high,
                analyst_target_low, analyst_count, recommendation_mean,
                forward_eps, forward_pe, forward_revenue_growth, implied_growth_rate)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (ticker, collected_date)
               DO UPDATE SET
                 analyst_target_mean=EXCLUDED.analyst_target_mean,
                 analyst_target_median=EXCLUDED.analyst_target_median,
                 analyst_target_high=EXCLUDED.analyst_target_high,
                 analyst_target_low=EXCLUDED.analyst_target_low,
                 analyst_count=EXCLUDED.analyst_count,
                 recommendation_mean=EXCLUDED.recommendation_mean,
                 forward_eps=EXCLUDED.forward_eps,
                 forward_pe=EXCLUDED.forward_pe,
                 forward_revenue_growth=EXCLUDED.forward_revenue_growth,
                 implied_growth_rate=EXCLUDED.implied_growth_rate,
                 collected_at=NOW()""",
            (
                ticker.upper(),
                signals.get('analyst_target_mean'),
                signals.get('analyst_target_median'),
                signals.get('analyst_target_high'),
                signals.get('analyst_target_low'),
                signals.get('analyst_count'),
                signals.get('recommendation_mean'),
                signals.get('forward_eps'),
                signals.get('forward_pe'),
                signals.get('forward_revenue_growth'),
                signals.get('implied_growth_rate'),
            )
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.debug(f'store_signals DB write failed for {ticker}: {e}')


def get_or_collect(ticker: str) -> Dict:
    """
    Return cached signals if fresh, otherwise collect fresh and store.
    This is the main entry point for getting analyst signals.
    """
    cached = get_cached_signals(ticker)
    if cached:
        return cached

    signals = collect_signals(ticker)
    if signals:
        store_signals(ticker, signals)
    return signals or {}
