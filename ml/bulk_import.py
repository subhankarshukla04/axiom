"""
Bulk fundamental data importer.

Iterates all 275 TICKER_TAG_MAP tickers, fetches financials from Yahoo Finance
via the existing DataIntegrator, saves to the DB (companies + company_financials),
runs the DCF, and saves valuation_results.

This activates the value factor (z_value) for the full monitoring universe.
Without this, the value factor is dead for 262 of 275 tickers.

CLI:
    python3 -m ml.bulk_import                  # import all, skip already-recent
    python3 -m ml.bulk_import --force          # re-import everything
    python3 -m ml.bulk_import --tickers AAPL MSFT GOOGL   # specific tickers
    python3 -m ml.bulk_import --dry-run        # show what would run, don't import
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_APP_DIR = os.path.dirname(os.path.dirname(__file__))
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)


# ── DB helpers ────────────────────────────────────────────────────────────────

def _get_conn():
    from config import Config
    if Config.DATABASE_TYPE == 'postgresql':
        import psycopg2
        from psycopg2.extras import RealDictCursor
        return psycopg2.connect(Config.get_db_connection_string(),
                                cursor_factory=RealDictCursor), '%s'
    else:
        import sqlite3
        conn = sqlite3.connect(Config.SQLITE_DB)
        conn.row_factory = sqlite3.Row
        return conn, '?'


def _ticker_company_id(ticker: str) -> Optional[int]:
    """Return existing company ID for ticker, or None."""
    try:
        conn, ph = _get_conn()
        cur = conn.cursor()
        cur.execute(f'SELECT id FROM companies WHERE ticker = {ph}', (ticker.upper(),))
        row = cur.fetchone()
        conn.close()
        if row:
            return row['id'] if hasattr(row, 'keys') else row[0]
    except Exception as e:
        logger.debug('_ticker_company_id failed: %s', e)
    return None


def _days_since_last_valuation(company_id: int) -> Optional[int]:
    """Return days since last valuation_results row, or None if no rows."""
    try:
        conn, ph = _get_conn()
        cur = conn.cursor()
        cur.execute(
            f'SELECT MAX(valuation_date) as vd FROM valuation_results WHERE company_id = {ph}',
            (company_id,)
        )
        row = cur.fetchone()
        conn.close()
        vd = row['vd'] if hasattr(row, 'keys') else row[0]
        if not vd:
            return None
        if isinstance(vd, str):
            vd = datetime.fromisoformat(vd.replace('Z', '+00:00').replace('+00:00', ''))
        if hasattr(vd, 'tzinfo') and vd.tzinfo:
            from datetime import timezone
            vd = vd.replace(tzinfo=None)
        return (datetime.utcnow() - vd).days
    except Exception:
        return None


def _upsert_company(data: dict) -> Tuple[int, bool]:
    """
    Insert or update company + company_financials.
    Returns (company_id, created: bool).
    """
    conn, ph = _get_conn()
    cur = conn.cursor()
    ticker = data['ticker'].upper()
    created = False

    try:
        # Check existence
        cur.execute(f'SELECT id FROM companies WHERE ticker = {ph}', (ticker,))
        row = cur.fetchone()
        company_id = (row['id'] if hasattr(row, 'keys') else row[0]) if row else None

        if company_id is None:
            # Insert new company
            if ph == '%s':  # PostgreSQL
                cur.execute(
                    'INSERT INTO companies (name, sector, ticker, industry) '
                    'VALUES (%s, %s, %s, %s) RETURNING id',
                    (data.get('name', ticker), data.get('sector', 'Unknown'),
                     ticker, data.get('industry'))
                )
                company_id = cur.fetchone()['id']
            else:  # SQLite
                cur.execute(
                    'INSERT INTO companies (name, sector, ticker, industry) VALUES (?, ?, ?, ?)',
                    (data.get('name', ticker), data.get('sector', 'Unknown'),
                     ticker, data.get('industry'))
                )
                company_id = cur.lastrowid
            created = True
        else:
            # Update name/sector/industry
            cur.execute(
                f'UPDATE companies SET name={ph}, sector={ph}, industry={ph} WHERE id={ph}',
                (data.get('name', ticker), data.get('sector', 'Unknown'),
                 data.get('industry'), company_id)
            )

        # Upsert company_financials
        cur.execute(
            f'SELECT id FROM company_financials WHERE company_id = {ph}',
            (company_id,)
        )
        cf_row = cur.fetchone()

        fin_vals = (
            data.get('revenue', 0),
            data.get('ebitda', 0),
            data.get('depreciation', 0),
            data.get('capex_pct', 0.05),
            data.get('working_capital_change', 0),
            data.get('profit_margin', 0.10),
            data.get('growth_rate_y1', 0.05),
            data.get('growth_rate_y2', 0.04),
            data.get('growth_rate_y3', 0.03),
            data.get('terminal_growth', 0.025),
            data.get('tax_rate', 0.21),
            data.get('shares_outstanding', 1e9),
            data.get('debt', 0),
            data.get('cash', 0),
            data.get('market_cap', 0),
            data.get('beta', 1.0),
            data.get('risk_free_rate', 0.045),
            data.get('market_risk_premium', 0.0525),
            data.get('country_risk_premium', 0.0),
            data.get('size_premium', 0.0),
            data.get('comparable_ev_ebitda', 15.0),
            data.get('comparable_pe', 20.0),
            data.get('comparable_peg', 1.5),
            data.get('operating_income', 0),
            data.get('interest_expense', 0),
        )

        if cf_row is None:
            cols = ('company_id, revenue, ebitda, depreciation, capex_pct, '
                    'working_capital_change, profit_margin, growth_rate_y1, '
                    'growth_rate_y2, growth_rate_y3, terminal_growth, tax_rate, '
                    'shares_outstanding, debt, cash, market_cap_estimate, beta, '
                    'risk_free_rate, market_risk_premium, country_risk_premium, '
                    'size_premium, comparable_ev_ebitda, comparable_pe, comparable_peg, '
                    'operating_income, interest_expense')
            phs = ', '.join([ph] * 26)
            cur.execute(f'INSERT INTO company_financials ({cols}) VALUES ({phs})',
                        (company_id,) + fin_vals)
        else:
            cur.execute(f'''UPDATE company_financials SET
                revenue={ph}, ebitda={ph}, depreciation={ph}, capex_pct={ph},
                working_capital_change={ph}, profit_margin={ph},
                growth_rate_y1={ph}, growth_rate_y2={ph}, growth_rate_y3={ph},
                terminal_growth={ph}, tax_rate={ph}, shares_outstanding={ph},
                debt={ph}, cash={ph}, market_cap_estimate={ph}, beta={ph},
                risk_free_rate={ph}, market_risk_premium={ph},
                country_risk_premium={ph}, size_premium={ph},
                comparable_ev_ebitda={ph}, comparable_pe={ph},
                comparable_peg={ph}, operating_income={ph}, interest_expense={ph}
                WHERE company_id={ph}''',
                fin_vals + (company_id,))

        conn.commit()
        conn.close()
        return company_id, created

    except Exception as e:
        conn.close()
        raise e


def _save_results(company_id: int, results: dict) -> None:
    conn, ph = _get_conn()
    cur = conn.cursor()
    try:
        cur.execute(f'''INSERT INTO valuation_results (
            company_id, dcf_equity_value, dcf_price_per_share,
            comp_ev_value, comp_pe_value, final_equity_value, final_price_per_share,
            market_cap, current_price, upside_pct, recommendation, wacc,
            ev_ebitda, pe_ratio, fcf_yield, roe, roic, debt_to_equity, z_score,
            mc_p10, mc_p90, sub_sector_tag, company_type, ebitda_method, analyst_target
        ) VALUES ({', '.join([ph] * 25)})''', (
            company_id,
            results.get('dcf_equity_value', 0),
            results.get('dcf_price_per_share', 0),
            results.get('comp_ev_value', 0),
            results.get('comp_pe_value', 0),
            results.get('final_equity_value', 0),
            results.get('final_price_per_share', 0),
            results.get('market_cap', 0),
            results.get('current_price', 0),
            results.get('upside_pct', 0),
            results.get('recommendation', 'HOLD'),
            results.get('wacc', 0),
            results.get('ev_ebitda', 0),
            results.get('pe_ratio', 0),
            results.get('fcf_yield', 0),
            results.get('roe', 0),
            results.get('roic', 0),
            results.get('debt_to_equity', 0),
            results.get('z_score', 0),
            results.get('mc_p10', 0),
            results.get('mc_p90', 0),
            results.get('sub_sector_tag'),
            results.get('company_type'),
            results.get('ebitda_method'),
            results.get('analyst_target'),
        ))
        conn.commit()
    finally:
        conn.close()


# ── Core import function ──────────────────────────────────────────────────────

def _fetch_yfinance(ticker: str) -> Optional[dict]:
    """
    Fetch company financials directly via yfinance without a custom session.
    yfinance >=0.2.40 requires curl_cffi and rejects requests.Session.
    """
    import math
    import yfinance as yf
    from data_integrator import get_risk_free_rate

    try:
        stock = yf.Ticker(ticker)
        info         = stock.info or {}
        financials   = stock.financials
        balance_sheet = stock.balance_sheet
        cash_flow    = stock.cashflow
        hist         = stock.history(period='2y')

        # Basic identity
        data: dict = {
            'ticker':   ticker.upper(),
            'name':     info.get('longName') or info.get('shortName') or ticker.upper(),
            'sector':   info.get('sector', 'Unknown'),
            'industry': info.get('industry', 'Unknown'),
            'current_price': info.get('currentPrice') or info.get('regularMarketPrice', 0),
            'market_cap':    info.get('marketCap', 0),
        }

        def _row(df, key, default=0):
            try:
                if df is None or df.empty:
                    return default
                col = df.iloc[:, 0]
                v = col.get(key, default)
                if v is None or (isinstance(v, float) and math.isnan(v)):
                    return default
                return float(v)
            except Exception:
                return default

        # Income statement
        data['revenue']          = _row(financials, 'Total Revenue')
        data['ebitda']           = _row(financials, 'EBITDA')
        data['operating_income'] = _row(financials, 'Operating Income')
        data['interest_expense'] = abs(_row(financials, 'Interest Expense', 0))
        net_income               = _row(financials, 'Net Income')
        data['net_income']       = net_income
        data['profit_margin']    = net_income / data['revenue'] if data['revenue'] > 0 else 0.10

        # 3yr EBITDA history for smart normalization
        data['ebitda_history'] = [
            float(financials.iloc[:, i].get('EBITDA', 0) or 0)
            for i in range(min(3, len(financials.columns)))
        ] if financials is not None and not financials.empty else []

        # Balance sheet
        data['debt']       = _row(balance_sheet, 'Total Debt') or _row(balance_sheet, 'Long Term Debt')
        data['cash']       = _row(balance_sheet, 'Cash And Cash Equivalents')
        data['book_value'] = (_row(balance_sheet, 'Stockholders Equity') or
                              _row(balance_sheet, 'Common Stock Equity'))

        # Cash flow
        data['depreciation']          = abs(_row(cash_flow, 'Depreciation And Amortization') or
                                            _row(cash_flow, 'Depreciation'))
        capex                         = abs(_row(cash_flow, 'Capital Expenditure'))
        data['capex_pct']             = capex / data['revenue'] if data['revenue'] > 0 else 0.05
        data['working_capital_change'] = _row(cash_flow, 'Change In Working Capital')

        # Shares
        data['shares_outstanding'] = info.get('sharesOutstanding', 1_000_000_000)

        # Growth: analyst estimate then trailing
        fy1_growth = info.get('revenueGrowth')  # TTM
        if fy1_growth and fy1_growth > -0.5:
            g1 = max(-0.20, min(float(fy1_growth), 0.60))
        elif data['revenue'] > 0 and financials is not None and not financials.empty and len(financials.columns) >= 2:
            rev_prior = float(financials.iloc[:, 1].get('Total Revenue', data['revenue']) or data['revenue'])
            g1 = (data['revenue'] / rev_prior - 1) if rev_prior > 0 else 0.05
        else:
            g1 = 0.05
        data['growth_rate_y1'] = g1
        data['growth_rate_y2'] = g1 * 0.75
        data['growth_rate_y3'] = g1 * 0.55
        data['terminal_growth'] = 0.025

        # Tax rate
        try:
            tax_exp = abs(_row(financials, 'Tax Provision'))
            pretax  = abs(_row(financials, 'Pretax Income'))
            data['tax_rate'] = min(0.40, tax_exp / pretax) if pretax > 0 else 0.21
        except Exception:
            data['tax_rate'] = 0.21

        # Risk parameters
        data['beta'] = float(info.get('beta', 1.0) or 1.0)
        # Beta from price history if info doesn't have it
        if data['beta'] == 1.0 and hist is not None and not hist.empty and len(hist) >= 60:
            try:
                import yfinance as yf2
                spy = yf2.download('SPY', period='2y', progress=False)['Close'].squeeze()
                stock_ret = hist['Close'].squeeze().pct_change().dropna()
                spy_ret   = spy.pct_change().dropna()
                aligned   = stock_ret.align(spy_ret, join='inner')
                if len(aligned[0]) >= 30:
                    cov = aligned[0].cov(aligned[1])
                    var = aligned[1].var()
                    data['beta'] = float(cov / var) if var > 0 else 1.0
            except Exception:
                pass

        data['risk_free_rate']       = get_risk_free_rate()
        data['market_risk_premium']  = 0.0525
        data['country_risk_premium'] = 0.0
        mktcap = data['market_cap'] or 0
        data['size_premium'] = (0.02 if mktcap < 2e9 else
                                0.01 if mktcap < 10e9 else 0.0)

        # Comparable multiples from sector tag
        from valuation._config import TICKER_TAG_MAP, SUBSECTOR_MULT
        tag = TICKER_TAG_MAP.get(ticker.upper(), 'cloud_software')
        mult = SUBSECTOR_MULT.get(tag)
        if mult and mult[0] is not None:
            data['comparable_ev_ebitda'] = float(mult[0])
            data['comparable_pe']        = float(mult[1])
        else:
            data['comparable_ev_ebitda'] = 15.0
            data['comparable_pe']        = 20.0
        data['comparable_peg'] = 1.5

        data['analyst_target'] = info.get('targetMeanPrice')
        data['financial_currency'] = info.get('financialCurrency', 'USD')

        if not data.get('revenue') or data['revenue'] <= 0:
            return None
        return data

    except Exception as e:
        logger.debug('_fetch_yfinance %s: %s', ticker, e)
        return None


def import_ticker(ticker: str, force: bool = False) -> Tuple[str, str]:
    """
    Fetch financials, save to DB, run DCF, save results.
    Returns (ticker, status) where status in: 'ok', 'skip', 'error:<msg>'.
    """
    from valuation_professional import enhanced_dcf_valuation

    ticker = ticker.upper()

    # Skip if recent valuation exists (unless forced)
    if not force:
        existing_id = _ticker_company_id(ticker)
        if existing_id is not None:
            days = _days_since_last_valuation(existing_id)
            if days is not None and days < 7:
                return ticker, 'skip'

    try:
        # Fetch from Yahoo Finance (direct yfinance, no custom session)
        data = _fetch_yfinance(ticker)
        if not data:
            return ticker, 'error:no_data'

        # Validate minimum fields
        if not data.get('revenue') or data['revenue'] <= 0:
            return ticker, 'error:no_revenue'

        # Upsert to DB
        data['ticker'] = ticker
        company_id, created = _upsert_company(data)

        # Run DCF
        data['id'] = company_id
        data['market_cap_estimate'] = data.get('market_cap', 0)

        # Suppress print output from enhanced_dcf_valuation
        import io, contextlib
        with contextlib.redirect_stdout(io.StringIO()):
            results = enhanced_dcf_valuation(data)

        if not results:
            return ticker, 'error:dcf_failed'

        # Save results
        _save_results(company_id, results)

        action = 'created' if created else 'updated'
        dcf = results.get('dcf_price_per_share', 0)
        return ticker, f'ok:{action}:dcf=${dcf:.2f}'

    except Exception as e:
        return ticker, f'error:{str(e)[:60]}'


# ── Bulk runner ───────────────────────────────────────────────────────────────

def run_bulk_import(
    tickers: Optional[List[str]] = None,
    force: bool = False,
    dry_run: bool = False,
    delay_seconds: float = 2.0,
    max_errors: int = 20,
) -> dict:
    """
    Import financials and run DCF for all TICKER_TAG_MAP tickers.

    delay_seconds: sleep between each ticker to avoid Yahoo Finance rate limits.
    max_errors: stop early if this many consecutive errors occur.
    """
    from valuation._config import TICKER_TAG_MAP

    if tickers is None:
        tickers = sorted(TICKER_TAG_MAP.keys())

    total = len(tickers)
    results = {'ok': 0, 'skip': 0, 'error': 0, 'details': []}
    consecutive_errors = 0

    print(f'Bulk import: {total} tickers  force={force}  dry_run={dry_run}')
    print(f'Estimated time: ~{total * delay_seconds / 60:.0f} minutes at {delay_seconds}s/ticker')
    print()

    for i, ticker in enumerate(tickers, 1):
        if dry_run:
            existing_id = _ticker_company_id(ticker)
            days = _days_since_last_valuation(existing_id) if existing_id else None
            status = f'would_skip (last_val={days}d ago)' if (days is not None and days < 7 and not force) else 'would_import'
            print(f'  [{i:3}/{total}] {ticker:8} {status}')
            continue

        tkr, status = import_ticker(ticker, force=force)
        category = status.split(':')[0]
        results[category if category in ('ok', 'skip', 'error') else 'error'] += 1
        results['details'].append({'ticker': tkr, 'status': status})

        flag = '✓' if category == 'ok' else ('–' if category == 'skip' else '✗')
        print(f'  [{i:3}/{total}] {ticker:8} {flag} {status}')

        if category == 'error':
            consecutive_errors += 1
            if consecutive_errors >= max_errors:
                print(f'\nStopping: {max_errors} consecutive errors')
                break
        else:
            consecutive_errors = 0

        if i < total and category != 'skip':
            time.sleep(delay_seconds)

    print(f'\nDone: ok={results["ok"]}  skip={results["skip"]}  error={results["error"]}')

    # Save a log
    log_path = os.path.join(os.path.dirname(__file__), '..', 'bulk_import_log.json')
    with open(log_path, 'w') as f:
        json.dump({
            'run_at': datetime.utcnow().isoformat(),
            'total': total,
            **results,
        }, f, indent=2)
    print(f'Log → {os.path.basename(log_path)}')
    return results


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    import argparse
    logging.basicConfig(level=logging.WARNING)
    logging.getLogger('yfinance').setLevel(logging.CRITICAL)

    ap = argparse.ArgumentParser(description='Bulk fundamental data importer')
    ap.add_argument('--tickers', nargs='+', help='Specific tickers (default: all TICKER_TAG_MAP)')
    ap.add_argument('--force',   action='store_true', help='Re-import even if recently valued')
    ap.add_argument('--dry-run', action='store_true', help='Show plan without importing')
    ap.add_argument('--delay',   type=float, default=2.0, help='Seconds between tickers (default 2)')
    ap.add_argument('--max-errors', type=int, default=20, help='Stop after N consecutive errors')
    args = ap.parse_args()

    run_bulk_import(
        tickers=args.tickers,
        force=args.force,
        dry_run=args.dry_run,
        delay_seconds=args.delay,
        max_errors=args.max_errors,
    )
