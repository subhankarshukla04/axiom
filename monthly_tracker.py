"""
Monthly Prediction Tracker
Runs our valuation model on each stock, then compares against
actual monthly prices over the past 2 years.
No ML. Just honest measurement of where we were right and wrong.
"""

import json
import time
from datetime import datetime, date
from dateutil.relativedelta import relativedelta

import yfinance as yf

TICKERS = [
    'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'META',   # Growth Tech / Hypergrowth
    'TSLA',                                        # Story stock
    'JPM',                                         # Bank
    'V',    'UNH',  'JNJ',  'COST', 'WMT',       # Stable Value
    'XOM',  'CAT',  'F',                           # Cyclical
    'T',                                           # Telecom
    'INTC',                                        # Distressed
    'AAPL', 'HD',   'ABBV',                        # Mixed
]

OUTPUT_FILE = 'monthly_tracking_results.json'


def get_monthly_prices(ticker: str, months: int = 24) -> dict:
    """Pull closing price for the first trading day of each of the last N months."""
    stock = yf.Ticker(ticker)
    hist = stock.history(period='3y')
    if hist.empty:
        return {}

    hist.index = hist.index.tz_localize(None) if hist.index.tzinfo else hist.index

    prices = {}
    today = date.today()
    for i in range(months, 0, -1):
        month_start = today - relativedelta(months=i)
        label = month_start.strftime('%Y-%m')
        window_start = datetime(month_start.year, month_start.month, 1)
        window_end   = window_start + relativedelta(days=10)
        try:
            window = hist.loc[window_start:window_end]
            if not window.empty:
                prices[label] = round(float(window['Close'].iloc[0]), 2)
        except Exception:
            pass
    return prices


def run_valuation(ticker: str) -> dict:
    """Run our full valuation pipeline on a ticker. Returns result dict or empty."""
    try:
        from data_integrator import DataIntegrator
        from valuation_professional import enhanced_dcf_valuation
        di = DataIntegrator()
        data = di.get_company_data(ticker)
        if not data:
            return {}
        result = enhanced_dcf_valuation(data)
        return result or {}
    except Exception as e:
        return {'error': str(e)}


def run_tracker(tickers=None, months=24):
    tickers = tickers or TICKERS
    all_results = []
    today_str = date.today().isoformat()

    print(f"\nRunning valuations + 2-year monthly tracking for {len(tickers)} stocks\n")
    print(f"{'Ticker':<6} | {'Our Model $':<12} | {'Market Now':<11} | {'Gap Now':<9} | Status")
    print('-' * 65)

    for ticker in tickers:
        try:
            # Step 1: run our model
            val = run_valuation(ticker)
            model_price = val.get('final_price_per_share') or val.get('price_per_share')
            company_type = val.get('company_type', 'unknown')
            sub_tag      = val.get('sub_sector_tag', '')
            error        = val.get('error')

            if error or not model_price:
                print(f"{ticker:<6} | ERROR: {error or 'no price returned'}")
                continue

            # Step 2: pull 24 monthly prices
            monthly = get_monthly_prices(ticker, months=months)
            if not monthly:
                print(f"{ticker:<6} | no price history")
                continue

            # Step 3: compute gap at each month
            monthly_gaps = {}
            for label, actual in monthly.items():
                gap_pct = round((actual - model_price) / model_price * 100, 1)
                monthly_gaps[label] = {'actual': actual, 'gap_pct': gap_pct}

            # Current market price = most recent monthly point
            latest_label  = sorted(monthly.keys())[-1]
            current_price = monthly[latest_label]
            current_gap   = round((current_price - model_price) / model_price * 100, 1)
            direction     = 'OVERVAL' if current_price > model_price else 'UNDERVAL'

            record = {
                'ticker':       ticker,
                'run_date':     today_str,
                'model_price':  round(model_price, 2),
                'company_type': company_type,
                'sub_tag':      sub_tag,
                'monthly':      monthly_gaps,
                'current_gap_pct': current_gap,
            }
            all_results.append(record)

            print(f"{ticker:<6} | ${model_price:<11.0f} | ${current_price:<10.0f} | {current_gap:+.1f}%     | {direction} ({company_type})")
            time.sleep(0.3)  # gentle on yfinance rate limits

        except Exception as e:
            print(f"{ticker:<6} | FAILED: {e}")

    # Save full results to file
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(all_results, f, indent=2)

    print(f"\nSaved to {OUTPUT_FILE}")
    print(f"Total tracked: {len(all_results)} stocks × {months} months = {len(all_results)*months} data points")
    return all_results


def print_monthly_detail(results, ticker):
    """Print the full monthly breakdown for one stock."""
    rec = next((r for r in results if r['ticker'] == ticker), None)
    if not rec:
        print(f"{ticker} not found")
        return

    print(f"\n{ticker} — Model: ${rec['model_price']} | Type: {rec['company_type']} ({rec['sub_tag']})")
    print(f"{'Month':<9} | {'Actual':>8} | {'Gap':>8} | {'Direction'}")
    print('-' * 45)
    for label in sorted(rec['monthly'].keys()):
        pt = rec['monthly'][label]
        bar = '▲' if pt['gap_pct'] > 0 else '▼'
        print(f"{label:<9} | ${pt['actual']:>7.2f} | {pt['gap_pct']:>+7.1f}% | {bar}")


if __name__ == '__main__':
    results = run_tracker()

    # Print full detail for a few interesting ones
    for t in ['MSFT', 'TSLA', 'CAT', 'UNH', 'NVDA']:
        print_monthly_detail(results, t)
