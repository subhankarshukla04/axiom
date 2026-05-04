"""
Growth rate normalizer — fetches multi-year revenue from yfinance,
computes median YoY growth, writes back to company_financials.

Run:
    python3 -m ml.growth_normalizer --all
    python3 -m ml.growth_normalizer --tickers AAPL MSFT
"""
import logging
import os
import statistics
import time
from typing import Optional

logger = logging.getLogger(__name__)

_BASE = os.path.dirname(os.path.dirname(__file__))

GROWTH_FLOOR = -0.10
GROWTH_CAP   =  0.50
NONDECLINE_FLOOR = 0.0   # profitable companies never project below 0%


def compute_median_growth(ticker: str, years: int = 6) -> tuple:
    """
    Fetch up to `years` annual revenues from yfinance.
    Returns (median_yoy_growth, source_label) or (None, reason).
    """
    try:
        import yfinance as yf
        inc = yf.Ticker(ticker).income_stmt
        if inc is None or inc.empty or 'Total Revenue' not in inc.index:
            return None, 'failed'
        # sort ascending (oldest first), reverse to get newest first
        rev = inc.loc['Total Revenue'].dropna().sort_index().values[::-1]
        rev = [float(v) for v in rev[:years + 1]]
        if len(rev) < 2:
            return None, 'insufficient_data'
        growths = []
        for i in range(1, len(rev)):
            base = rev[i]   # older year (denominator)
            if base and abs(base) > 0:
                g = (rev[i - 1] - base) / abs(base)  # i-1 is more recent
                growths.append(g)
        if not growths:
            return None, 'no_valid_pairs'
        median_g = statistics.median(growths)
        median_g = max(GROWTH_FLOOR, min(GROWTH_CAP, median_g))
        return median_g, f'yfinance_median_{len(growths)}y'
    except Exception as e:
        logger.debug('growth fetch failed for %s: %s', ticker, e)
        return None, 'failed'


def is_consistently_profitable(ticker: str, min_years: int = 3) -> bool:
    """True if company had positive net income for min_years consecutive years."""
    try:
        import yfinance as yf
        inc = yf.Ticker(ticker).income_stmt
        if inc is None or inc.empty:
            return False
        ni_row = None
        for key in ['Net Income', 'Net Income Common Stockholders',
                    'Net Income From Continuing Operations']:
            if key in inc.index:
                ni_row = inc.loc[key].dropna()
                break
        if ni_row is None or len(ni_row) < min_years:
            return False
        return all(float(v) > 0 for v in ni_row.values[:min_years])
    except Exception:
        return False


def normalize_company(company_id: int, ticker: str, stored_growth: float, conn) -> dict:
    """Compute and write normalized growth for one company."""
    median_g, source = compute_median_growth(ticker)

    if median_g is None:
        return {'ticker': ticker, 'status': 'skipped', 'reason': source,
                'growth_used': stored_growth}

    # Floor at 0% for consistently profitable companies (don't project decline)
    if median_g < 0 and is_consistently_profitable(ticker):
        median_g = NONDECLINE_FLOOR
        source += '_floored'

    cur = conn.cursor()
    # Preserve original value first time
    cur.execute("""
        UPDATE company_financials
        SET growth_rate_y1_original = growth_rate_y1
        WHERE company_id = %s AND growth_rate_y1_original IS NULL
    """, (company_id,))

    # Read terminal growth from DB for smooth blend
    cur.execute("SELECT terminal_growth FROM company_financials WHERE company_id = %s",
                (company_id,))
    row = cur.fetchone()
    terminal = (dict(row).get('terminal_growth') or 0.02) if row else 0.02

    g2 = round(median_g * 0.67 + terminal * 0.33, 4)
    g3 = round(median_g * 0.33 + terminal * 0.67, 4)

    cur.execute("""
        UPDATE company_financials
        SET growth_rate_y1 = %s,
            growth_rate_y2 = %s,
            growth_rate_y3 = %s,
            growth_source   = %s
        WHERE company_id = %s
    """, (round(median_g, 4), g2, g3, source, company_id))
    conn.commit()

    return {
        'ticker': ticker, 'status': 'updated',
        'original': stored_growth, 'normalized': median_g,
        'source': source,
    }


def run_normalization(tickers: list = None, delay: float = 0.3,
                      force: bool = False) -> list:
    """
    Normalize growth for all companies (or specific tickers).
    Skips companies already normalized unless force=True.
    """
    import sys
    sys.path.insert(0, _BASE)
    from app import get_db_connection

    conn = get_db_connection()
    cur = conn.cursor()

    if force:
        where_src = "TRUE"
    else:
        where_src = "(cf.growth_source IS NULL OR cf.growth_source = 'stored')"

    if tickers:
        cur.execute(f"""
            SELECT c.id, c.ticker, cf.growth_rate_y1
            FROM companies c
            JOIN company_financials cf ON c.id = cf.company_id
            WHERE {where_src} AND c.ticker = ANY(%s)
        """, (tickers,))
    else:
        cur.execute(f"""
            SELECT c.id, c.ticker, cf.growth_rate_y1
            FROM companies c
            JOIN company_financials cf ON c.id = cf.company_id
            WHERE {where_src}
        """)

    companies = [dict(r) for r in cur.fetchall()]
    cur.close()
    print(f'Normalizing growth for {len(companies)} companies...')

    results = []
    for i, c in enumerate(companies):
        result = normalize_company(c['id'], c['ticker'], c['growth_rate_y1'], conn)
        results.append(result)
        if result['status'] == 'updated':
            print(f"  {c['ticker']}: {result['original']:.1%} → {result['normalized']:.1%}"
                  f" ({result['source']})")
        else:
            print(f"  {c['ticker']}: {result['status']} ({result.get('reason', '')})")
        # Rate-limit yfinance calls
        if i % 30 == 29:
            time.sleep(2)
        else:
            time.sleep(delay)

    updated = sum(1 for r in results if r['status'] == 'updated')
    print(f'\nDone — {updated}/{len(companies)} updated')
    conn.close()
    return results


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description='Normalize growth rates from yfinance history')
    ap.add_argument('--tickers', nargs='+', help='Specific tickers to normalize')
    ap.add_argument('--all', action='store_true', help='Normalize all companies')
    ap.add_argument('--force', action='store_true', help='Re-normalize even if already done')
    ap.add_argument('--delay', type=float, default=0.3, help='Seconds between yfinance calls')
    args = ap.parse_args()
    run_normalization(tickers=args.tickers, delay=args.delay, force=args.force)
