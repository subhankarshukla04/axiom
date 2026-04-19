"""
Outcome Tracker
Runs on the 1st of each month (or manually anytime).
For every stock in predictions_db.json, fetches the current price and records it.
Over time this builds the prediction-vs-reality database that will train the ML.
"""

import json
import logging
import time
from datetime import date
from pathlib import Path

import yfinance as yf

from batch_runner import PREDICTIONS_DB, load_db, save_db

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

ERROR_LOG = Path(__file__).parent / 'outcome_errors.json'


def get_current_price(ticker: str) -> float | None:
    try:
        info = yf.Ticker(ticker).info
        price = info.get('currentPrice') or info.get('regularMarketPrice')
        return round(float(price), 2) if price else None
    except Exception:
        return None


def update_outcomes(db: dict = None) -> dict:
    """
    For each ticker in the DB, record today's price under monthly_actuals[YYYY-MM].
    Also compute gap_pct vs the original model price.
    """
    db    = db or load_db()
    today = date.today()
    label = today.strftime('%Y-%m')
    errors = []

    updated = 0
    for ticker, rec in db.items():
        price = get_current_price(ticker)
        if not price:
            errors.append(ticker)
            continue

        model_price = rec.get('model_price', 0)
        gap_pct = round((price - model_price) / model_price * 100, 1) if model_price else None

        rec.setdefault('monthly_actuals', {})[label] = {
            'price':   price,
            'gap_pct': gap_pct,
        }
        rec['last_updated'] = today.isoformat()
        updated += 1
        time.sleep(0.3)

    save_db(db)

    if errors:
        with open(ERROR_LOG, 'w') as f:
            json.dump(errors, f)
        logger.warning(f'Price fetch failed for {len(errors)} tickers — see outcome_errors.json')

    logger.info(f'Updated {updated} tickers for {label}')
    return db


def print_report(db: dict = None, top_n: int = 20):
    """Print a summary of the biggest misses and best calls for the latest month."""
    db    = db or load_db()
    today = date.today().strftime('%Y-%m')

    rows = []
    for ticker, rec in db.items():
        latest = rec.get('monthly_actuals', {}).get(today)
        if not latest:
            continue
        rows.append({
            'ticker':   ticker,
            'model':    rec.get('model_price', 0),
            'actual':   latest['price'],
            'gap_pct':  latest['gap_pct'],
            'type':     rec.get('company_type', ''),
            'tag':      rec.get('sub_tag', ''),
        })

    if not rows:
        print('No data for current month yet. Run update_outcomes() first.')
        return

    rows.sort(key=lambda x: x['gap_pct'])

    print(f'\n=== OUTCOME REPORT: {today} ===')
    print(f'{"Ticker":<7} {"Model $":>8} {"Actual $":>9} {"Gap":>8}  Type')
    print('-' * 55)

    print('\n-- Our model is most OVERVALUED vs market --')
    for r in rows[:top_n // 2]:
        print(f"{r['ticker']:<7} ${r['model']:>7.0f} ${r['actual']:>8.0f} {r['gap_pct']:>+7.1f}%  {r['type']} ({r['tag']})")

    print('\n-- Our model is most UNDERVALUED vs market --')
    for r in rows[-(top_n // 2):]:
        print(f"{r['ticker']:<7} ${r['model']:>7.0f} ${r['actual']:>8.0f} {r['gap_pct']:>+7.1f}%  {r['type']} ({r['tag']})")

    # Summary stats by type
    from collections import defaultdict
    import statistics
    by_type = defaultdict(list)
    for r in rows:
        by_type[r['type']].append(r['gap_pct'])

    print('\n-- Average gap by company type --')
    for t, gaps in sorted(by_type.items()):
        print(f'  {t:<28} n={len(gaps):>3}  median={statistics.median(gaps):>+6.1f}%')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', action='store_true', help='Print report only, no update')
    args = parser.parse_args()

    if args.report:
        print_report()
    else:
        db = update_outcomes()
        print_report(db)
