"""
S&P 500 Batch Runner
Fetches the S&P 500 ticker list, runs our valuation model on each stock
in batches of 30, and stores every prediction to predictions_db.json.
Run this once to seed the database, then let outcome_tracker.py handle monthly updates.
"""

import io
import json
import logging
import sys
import time
from datetime import date
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

PREDICTIONS_DB = Path(__file__).parent / 'predictions_db.json'
BATCH_SIZE     = 30
DELAY_SECONDS  = 1.5   # between stocks — gentle on yfinance


def get_sp500_tickers() -> list:
    """Fetch current S&P 500 tickers from Wikipedia (SSL-safe)."""
    try:
        import ssl, urllib.request, pandas as pd, io as _io
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        url  = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        html = urllib.request.urlopen(url, context=ctx).read().decode()
        tables  = pd.read_html(_io.StringIO(html))
        tickers = tables[0]['Symbol'].tolist()
        tickers = [t.replace('.', '-') for t in tickers]
        logger.info(f'Fetched {len(tickers)} S&P 500 tickers from Wikipedia')
        return tickers
    except Exception as e:
        logger.warning(f'Wikipedia fetch failed ({e}), using fallback list')
        return _fallback_tickers()


def _fallback_tickers() -> list:
    # ~500 large/mid caps across all S&P 500 sectors
    return [
        # Mega-cap Tech
        'AAPL','MSFT','NVDA','AMZN','META','GOOGL','GOOG','TSLA','AVGO','ORCL',
        'CRM','ADBE','CSCO','IBM','INTC','AMD','QCOM','TXN','AMAT','LRCX',
        'KLAC','SNPS','CDNS','MU','ADI','MCHP','NXPI','HPQ','HPE','STX',
        'WDC','KEYS','FTNT','PANW','CRWD','ZS','NET','DDOG','SNOW','PLTR',
        # Financials
        'JPM','BAC','WFC','GS','MS','C','BLK','SCHW','AXP','V','MA','COF',
        'USB','TFC','PNC','FITB','RF','KEY','CFG','HBAN','MTB','CMA','ZION',
        'MCO','SPGI','ICE','CME','CBOE','BX','KKR','APO','ARES','TPG',
        # Healthcare
        'UNH','LLY','JNJ','ABBV','MRK','PFE','TMO','ABT','BMY','AMGN',
        'GILD','ISRG','ELV','CI','HUM','CVS','ZTS','VRTX','REGN','BIIB',
        'ILMN','IDXX','EW','BDX','SYK','MDT','BSX','DXCM','HOLX','MRNA',
        # Consumer Discretionary
        'MCD','SBUX','NKE','TJX','HD','LOW','COST','WMT','TGT','ORLY',
        'AZO','TSCO','ROST','DG','DLTR','KR','SYY','YUM','DPZ','CMG',
        'HLT','MAR','H','LVS','WYNN','MGM','NFLX','DIS','CMCSA','PARA',
        # Consumer Staples
        'PG','KO','PEP','PM','MO','MDLZ','GIS','K','CPB','CAG','SJM',
        'HRL','MKC','CLX','CL','CHD','COTY','EL','ULTA','HELE',
        # Industrials
        'GE','HON','CAT','DE','RTX','LMT','NOC','GD','BA','TDG',
        'ETN','EMR','PH','ITW','DOV','AME','ROK','FTV','SWK','IR',
        'WM','RSG','CTAS','FAST','GWW','MSC','NSC','UNP','CSX','CP',
        'UPS','FDX','XPO','JBHT','SAIA','ODFL',
        # Energy
        'XOM','CVX','COP','EOG','PXD','DVN','FANG','MPC','PSX','VLO',
        'SLB','HAL','BKR','OXY','APA','HES','CTRA','EQT','RRC','AR',
        # Materials
        'LIN','APD','ECL','SHW','NEM','FCX','NUE','STLD','RS','VMC',
        'MLM','PKG','IP','WRK','SEE','CCK','SON','AVY',
        # Real Estate
        'PLD','AMT','EQIX','CCI','PSA','EXR','AVB','EQR','MAA','UDR',
        'SPG','O','NNN','STOR','VICI','GLPI','PEAK','VTR','WELL',
        # Utilities
        'NEE','DUK','SO','D','AEP','EXC','SRE','XEL','ES','ETR',
        'AWK','PPL','FE','CNP','NI','LNT','AES','CMS','WEC','DTE',
        # Telecom/Media
        'T','VZ','TMUS','CHTR','CMCSA','DISH','LUMN','PARA','WBD',
    ]


def run_valuation_silent(ticker: str) -> dict:
    """Run valuation with all output suppressed."""
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout = sys.stderr = io.StringIO()
    try:
        from data_integrator import DataIntegrator
        from valuation_professional import enhanced_dcf_valuation
        di   = DataIntegrator()
        data = di.get_company_data(ticker)
        if not data:
            return {}
        result = enhanced_dcf_valuation(data)
        return result or {}
    except Exception as e:
        return {'error': str(e)}
    finally:
        sys.stdout, sys.stderr = old_out, old_err


def load_db() -> dict:
    if PREDICTIONS_DB.exists():
        with open(PREDICTIONS_DB) as f:
            return json.load(f)
    return {}


def save_db(db: dict):
    with open(PREDICTIONS_DB, 'w') as f:
        json.dump(db, f, indent=2)


def run_batch(tickers: list = None, skip_existing: bool = True):
    """
    Run valuations for all tickers and store results.
    skip_existing=True skips tickers already in predictions_db (for incremental runs).
    """
    tickers = tickers or get_sp500_tickers()
    db      = load_db()
    today   = date.today().isoformat()

    new_count  = 0
    skip_count = 0
    fail_count = 0
    total      = len(tickers)

    logger.info(f'Starting batch: {total} tickers, skip_existing={skip_existing}')

    for i, ticker in enumerate(tickers, 1):
        if skip_existing and ticker in db:
            skip_count += 1
            continue

        result = run_valuation_silent(ticker)
        price  = result.get('final_price_per_share') or result.get('price_per_share')

        if not price:
            fail_count += 1
            logger.debug(f'[{i}/{total}] {ticker}: failed — {result.get("error","no price")}')
            continue

        db[ticker] = {
            'ticker':       ticker,
            'model_price':  round(float(price), 2),
            'company_type': result.get('company_type', ''),
            'sub_tag':      result.get('sub_sector_tag', ''),
            'analyst_target': result.get('analyst_target'),
            'wacc':         result.get('wacc'),
            'growth_y1':    result.get('growth_rate_y1'),
            'first_run':    today,
            'last_updated': today,
            'monthly_actuals': {},   # filled by outcome_tracker
        }
        new_count += 1
        logger.info(f'[{i}/{total}] {ticker}: ${price:.0f} | {result.get("company_type","")} | {result.get("sub_sector_tag","")}')

        # Save every 10 stocks so we don't lose progress
        if new_count % 10 == 0:
            save_db(db)

        time.sleep(DELAY_SECONDS)

    save_db(db)
    logger.info(f'Done. New: {new_count} | Skipped: {skip_count} | Failed: {fail_count}')
    return db


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--tickers', nargs='+', help='Specific tickers to run')
    parser.add_argument('--rerun',   action='store_true', help='Re-run even if ticker exists in DB')
    args = parser.parse_args()

    run_batch(tickers=args.tickers, skip_existing=not args.rerun)
