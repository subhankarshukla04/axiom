"""
Institutional-Grade Data Integration Module
Auto-populates company financials from multiple sources
"""

import yfinance as yf
import pandas as pd
import numpy as np
import time
import requests
from datetime import datetime, timedelta
from typing import Dict, Optional, List
import logging

logger = logging.getLogger(__name__)


_YF_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/122.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Referer': 'https://finance.yahoo.com/',
}


def _yf_session() -> requests.Session:
    """
    Session with Yahoo Finance cookies + crumb.
    Yahoo Finance blocks bare AWS Lambda IPs. We replicate what a browser
    does: visit the consent page to get cookies, then fetch the crumb token,
    then attach both to subsequent API calls.
    """
    s = requests.Session()
    s.headers.update(_YF_HEADERS)
    try:
        # Step 1: get consent cookies
        s.get('https://fc.yahoo.com', timeout=5)
        s.get('https://finance.yahoo.com', timeout=5)
        # Step 2: get crumb
        crumb_r = s.get(
            'https://query1.finance.yahoo.com/v1/test/getcrumb',
            timeout=5,
        )
        if crumb_r.status_code == 200 and crumb_r.text:
            s.params = {'crumb': crumb_r.text.strip()}  # type: ignore[assignment]
    except Exception:
        pass
    return s


def _yahoo_quote_summary(ticker: str, session: requests.Session) -> dict:
    """
    Direct Yahoo Finance quoteSummary call — bypasses yfinance's .info
    which uses a separate (and frequently rate-limited) scraping path.
    Returns the merged modules dict, or {} on failure.
    """
    modules = 'financialData,quoteType,defaultKeyStatistics,assetProfile,summaryDetail'
    params = {'modules': modules, 'corsDomain': 'finance.yahoo.com', 'formatted': 'false', 'symbol': ticker}
    if hasattr(session, 'params') and isinstance(session.params, dict):
        params.update(session.params)
    try:
        r = session.get(
            f'https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker}',
            params=params, timeout=15,
        )
        data = r.json()
        result = data.get('quoteSummary', {}).get('result') or []
        if not result:
            return {}
        merged: dict = {}
        for module in result:
            merged.update(module)
        return merged
    except Exception as e:
        logger.debug('quoteSummary direct call failed: %s', e)
        return {}

# Module-level cache for risk-free rate (shared across all callers)
_rfr_cache = {'value': None, 'timestamp': 0}
_RFR_CACHE_SECONDS = 4 * 3600  # 4 hours


def get_risk_free_rate() -> float:
    """
    Fetch the current 10-year Treasury yield as risk-free rate.
    - First tries FRED API (series DGS10) if FRED_API_KEY is set in env.
    - Falls back to yfinance ^TNX if FRED is unavailable.
    - Caches result for 4 hours.
    Returns float (e.g., 0.0442 for 4.42%).
    """
    import os
    import time as _time

    now = _time.time()
    # Return cached value if still fresh
    if _rfr_cache['value'] is not None and now - _rfr_cache['timestamp'] < _RFR_CACHE_SECONDS:
        cached_age = int(now - _rfr_cache['timestamp'])
        logger.info(f'Using cached risk-free rate: {_rfr_cache["value"]*100:.2f}% (cached {cached_age}s ago)')
        return _rfr_cache['value']

    fred_key = os.environ.get('FRED_API_KEY')
    rate = None

    # Try FRED first
    if fred_key:
        try:
            import urllib.request
            import json as _json
            url = (
                f'https://api.stlouisfed.org/fred/series/observations'
                f'?series_id=DGS10&api_key={fred_key}&sort_order=desc&limit=1&file_type=json'
            )
            with urllib.request.urlopen(url, timeout=5) as resp:
                payload = _json.loads(resp.read().decode())
            obs = payload.get('observations', [])
            if obs:
                val_str = obs[0].get('value', '.')
                if val_str != '.':
                    rate = float(val_str) / 100
                    logger.info(f'Fetched risk-free rate from FRED: {rate*100:.2f}%')
        except Exception as e:
            logger.warning(f'FRED risk-free rate fetch failed: {e}')

    # Fall back to yfinance ^TNX
    if rate is None:
        try:
            import yfinance as yf
            tnx = yf.Ticker('^TNX')
            hist = tnx.history(period='5d')
            if not hist.empty:
                rate = hist['Close'].iloc[-1] / 100
                logger.info(f'Fetched risk-free rate from yfinance ^TNX: {rate*100:.2f}%')
        except Exception as e:
            logger.warning(f'yfinance risk-free rate fetch failed: {e}')

    if rate is None:
        rate = 0.045  # Hard fallback: 4.5%
        logger.warning('All risk-free rate sources failed; using default 4.5%')

    # Update cache
    _rfr_cache['value'] = rate
    _rfr_cache['timestamp'] = now
    return rate



class DataIntegrator:
    """
    Fetches real-time and historical data from Yahoo Finance and other sources.
    Automatically populates all required fields for DCF valuation.
    """

    # Class-level cache for treasury rate (shared across all instances)
    _treasury_cache = None
    _treasury_cache_time = 0
    _TREASURY_CACHE_DURATION = 3600  # 1 hour in seconds

    def __init__(self):
        self.risk_free_rate = get_risk_free_rate()
        self.market_risk_premium = 0.0525  # Forward-looking MRP (Damodaran 2024)

    def _get_risk_free_rate(self) -> float:
        """Get current 10-year Treasury rate as risk-free rate (with 1-hour caching)"""
        # Check if we have a cached rate that's still fresh
        if (DataIntegrator._treasury_cache is not None and
            time.time() - DataIntegrator._treasury_cache_time < DataIntegrator._TREASURY_CACHE_DURATION):
            cached_age = int(time.time() - DataIntegrator._treasury_cache_time)
            logger.info(f"✅ Using cached treasury rate: {DataIntegrator._treasury_cache*100:.2f}% (cached {cached_age}s ago)")
            return DataIntegrator._treasury_cache

        # Cache expired or doesn't exist, fetch new rate
        try:
            # Use ^TNX (10-year Treasury yield)
            tnx = yf.Ticker("^TNX")
            hist = tnx.history(period="5d")
            if not hist.empty:
                rate = hist['Close'].iloc[-1] / 100  # Convert from percentage
                logger.info(f"✅ Fetched fresh treasury rate: {rate*100:.2f}% (will cache for 1 hour)")

                # Update cache
                DataIntegrator._treasury_cache = rate
                DataIntegrator._treasury_cache_time = time.time()

                return rate
            else:
                logger.warning("Could not fetch Treasury rate, using default 4.5%")
                return 0.045
        except Exception as e:
            logger.error(f"Error fetching risk-free rate: {e}")
            return 0.045  # Default fallback

    def get_company_data(self, ticker: str) -> Optional[Dict]:
        """
        Fetch comprehensive company data from Yahoo Finance.
        Returns all data needed for DCF valuation.

        Args:
            ticker: Stock ticker symbol (e.g., 'AAPL', 'MSFT')

        Returns:
            Dictionary with complete financial data, or None if ticker not found
        """
        try:
            logger.info(f"Fetching data for ticker: {ticker}")

            from concurrent.futures import ThreadPoolExecutor
            session = _yf_session()
            stock   = yf.Ticker(ticker, session=session)

            # Use direct quoteSummary API for .info — avoids the broken
            # yfinance crumb scraper that gets 429'd on AWS Lambda IPs.
            def _info():
                raw = _yahoo_quote_summary(ticker, session)
                if raw:
                    return raw
                # Fallback: try yfinance .info (works if not rate-limited)
                return stock.info

            def _financials(): return stock.financials
            def _balance():    return stock.balance_sheet
            def _cashflow():   return stock.cashflow
            def _history():    return stock.history(period="2y")

            with ThreadPoolExecutor(max_workers=5) as ex:
                f_info  = ex.submit(_info)
                f_fin   = ex.submit(_financials)
                f_bal   = ex.submit(_balance)
                f_cf    = ex.submit(_cashflow)
                f_hist  = ex.submit(_history)
                info          = f_info.result(timeout=25)
                financials    = f_fin.result(timeout=25)
                balance_sheet = f_bal.result(timeout=25)
                cash_flow     = f_cf.result(timeout=25)
                hist          = f_hist.result(timeout=25)

            # quoteSummary nests fields in sub-dicts; flatten so downstream
            # .get('longName') / .get('sector') calls work unchanged.
            if isinstance(info, dict) and 'quoteType' in info:
                flat: dict = {}
                for v in info.values():
                    if isinstance(v, dict):
                        flat.update(v)
                flat.update(info)   # top-level keys win
                info = flat

            if not info or not info.get('symbol'):
                logger.error(f"Invalid ticker or no data: {ticker}")
                return None

            # Extract key data
            data = {
                'ticker': ticker.upper(),
                'name': info.get('longName', ticker.upper()),
                'sector': info.get('sector', 'Unknown'),
                'industry': info.get('industry', 'Unknown'),
                'current_price': info.get('currentPrice', info.get('regularMarketPrice', 0)),
                'market_cap': info.get('marketCap', 0),
            }

            # Extract financials (most recent year)
            if not financials.empty:
                latest_financials = financials.iloc[:, 0]

                data['revenue'] = latest_financials.get('Total Revenue', 0)
                data['ebitda'] = latest_financials.get('EBITDA', 0)
                data['operating_income'] = latest_financials.get('Operating Income', 0)
                raw_ie = latest_financials.get('Interest Expense', 0) or 0
                data['interest_expense'] = abs(float(raw_ie))

                net_income = latest_financials.get('Net Income', 0)
                data['net_income'] = net_income
                data['profit_margin'] = net_income / data['revenue'] if data['revenue'] > 0 else 0.10

                # 3-year EBITDA history for smart normalization
                data['ebitda_history'] = [
                    float(financials.iloc[:, i].get('EBITDA', 0) or 0)
                    for i in range(min(3, len(financials.columns)))
                ]

            else:
                logger.warning(f"No financials found for {ticker}")
                data['revenue'] = info.get('totalRevenue', 0)
                data['ebitda'] = info.get('ebitda', 0)
                data['operating_income'] = 0
                data['interest_expense'] = 0
                data['net_income'] = 0
                data['profit_margin'] = 0.10
                data['ebitda_history'] = []

            # Balance sheet items
            if not balance_sheet.empty:
                latest_bs = balance_sheet.iloc[:, 0]
                data['debt'] = latest_bs.get('Total Debt', latest_bs.get('Long Term Debt', 0))
                data['cash'] = latest_bs.get('Cash And Cash Equivalents', 0)
                data['book_value'] = (
                    latest_bs.get('Stockholders Equity') or
                    latest_bs.get('Total Stockholder Equity') or
                    latest_bs.get('Common Stock Equity') or 0
                )
            else:
                data['debt'] = info.get('totalDebt', 0)
                data['cash'] = info.get('totalCash', 0)
                data['book_value'] = 0

            # Fallback: compute from info dict if BS didn't have it
            if not data.get('book_value') and info.get('bookValue') and info.get('sharesOutstanding'):
                data['book_value'] = info['bookValue'] * info['sharesOutstanding']

            # Cash flow items
            if not cash_flow.empty:
                import math as _math
                latest_cf = cash_flow.iloc[:, 0]

                def _cf(key, default=0):
                    v = latest_cf.get(key, default)
                    return default if (v is None or (isinstance(v, float) and _math.isnan(v))) else v

                raw_da = _cf('Depreciation And Amortization') or _cf('Depreciation Amortization Depletion') or _cf('Depreciation')
                data['depreciation'] = abs(raw_da)
                capex = abs(_cf('Capital Expenditure'))
                data['capex_pct'] = capex / data['revenue'] if data['revenue'] > 0 else 0.05
                data['working_capital_change'] = _cf('Change In Working Capital')
            else:
                data['depreciation'] = data['ebitda'] * 0.05 if data['ebitda'] > 0 else 0
                data['capex_pct'] = 0.05
                data['working_capital_change'] = 0

            # Shares outstanding
            data['shares_outstanding'] = info.get('sharesOutstanding', 1_000_000)

            # Growth rates from analyst estimates
            growth_estimates = self._get_growth_estimates(info, financials, stock=stock)
            data['growth_rate_y1'] = growth_estimates['y1']
            data['growth_rate_y2'] = growth_estimates['y2']
            data['growth_rate_y3'] = growth_estimates['y3']
            data['terminal_growth'] = growth_estimates['terminal']

            # Tax rate
            data['tax_rate'] = self._estimate_tax_rate(financials, info)

            # Risk parameters
            data['beta'] = self._calculate_beta(hist, ticker)
            data['risk_free_rate'] = get_risk_free_rate()
            data['market_risk_premium'] = self.market_risk_premium
            data['country_risk_premium'] = 0.0  # US = 0, adjust for international
            data['size_premium'] = self._estimate_size_premium(data['market_cap'])

            # Comparable company multiples
            comp_multiples = self._get_comparable_multiples(info, data)
            data['comparable_ev_ebitda'] = comp_multiples['ev_ebitda']
            data['comparable_pe'] = comp_multiples['pe']
            data['comparable_peg'] = comp_multiples['peg']

            # Additional fields for calibration layer
            data['forward_pe'] = info.get('forwardPE', 0) or 0
            data['industry'] = info.get('industry', '')

            # Analyst signals (best-effort, non-blocking)
            try:
                from market_signal_collector import get_or_collect
                signals = get_or_collect(ticker)
                data['analyst_target'] = signals.get('analyst_target_mean')
                data['analyst_recommendation'] = signals.get('recommendation_mean')
                data['implied_growth_rate'] = signals.get('implied_growth_rate')
            except Exception:
                data['analyst_target'] = None
                data['analyst_recommendation'] = None
                data['implied_growth_rate'] = None

            # B2-2: Detect non-USD financial reporting currency
            # Chinese ADRs (BABA, JD, BIDU etc.) report financials in CNY.
            # Our DCF will compute in CNY but the stock trades in USD.
            # We flag this so calibrate() can force a heavy analyst anchor.
            fin_currency = info.get('financialCurrency', 'USD') or 'USD'
            data['financial_currency'] = fin_currency

            # Additional metadata
            data['data_source'] = 'Yahoo Finance'
            data['last_updated'] = datetime.now().isoformat()

            logger.info(f"Successfully fetched data for {data['name']}")
            return data

        except Exception as e:
            logger.error(f"Error fetching data for {ticker}: {str(e)}", exc_info=True)
            return None

    def _get_growth_estimates(self, info: dict, financials: pd.DataFrame, stock=None) -> Dict[str, float]:
        """
        Forward revenue growth from analyst consensus (primary), with trailing fallbacks.

        Source priority:
          1. stock.revenue_estimate +1y growth  (forward analyst consensus, n >= 3)
          2. stock.revenue_estimate  0y growth  (current fiscal year, n >= 2)
          3. info earningsGrowth * 0.60         (earnings proxy, scaled down)
          4. 2yr trailing CAGR from financials
          5. 1yr trailing growth from financials
          6. Floor: 3% profitable, 0% loss-making

        Y2 / Y3 converge toward terminal (not arbitrary %-decay).
        """
        TERMINAL_DEFAULT = 0.025  # valuation.calibrate() overrides per sector tag

        # ── Source 1 & 2: forward revenue estimate from analyst consensus ──────
        fwd_1y = None   # next fiscal year
        fwd_0y = None   # current fiscal year (partially forward)
        n_1y   = 0      # analyst count for +1y (separate from 0y)
        n_0y   = 0      # analyst count for  0y

        if stock is not None:
            try:
                re = stock.revenue_estimate
                if re is not None and not re.empty:
                    has_growth = 'growth' in re.columns
                    has_n      = 'numberOfAnalysts' in re.columns

                    if '+1y' in re.index and has_growth:
                        try:
                            g = re.loc['+1y', 'growth']
                            # Guard: .loc can return a Series on duplicate index rows
                            if hasattr(g, '__len__'):
                                g = g.iloc[0]
                            if g is not None and not (isinstance(g, float) and np.isnan(g)):
                                g = float(g)
                                if -0.50 < g < 2.0:
                                    fwd_1y = g
                                    # If analyst count unavailable/NaN, treat as 1 — estimate exists
                                    n_1y = 1
                                    if has_n:
                                        raw_n = re.loc['+1y', 'numberOfAnalysts']
                                        if hasattr(raw_n, '__len__'):
                                            raw_n = raw_n.iloc[0]
                                        if raw_n is not None and not (isinstance(raw_n, float) and np.isnan(raw_n)):
                                            n_1y = max(1, int(raw_n))
                        except Exception as e:
                            logger.debug(f'revenue_estimate +1y parse error: {e}')

                    if '0y' in re.index and has_growth:
                        try:
                            g = re.loc['0y', 'growth']
                            if hasattr(g, '__len__'):
                                g = g.iloc[0]
                            if g is not None and not (isinstance(g, float) and np.isnan(g)):
                                g = float(g)
                                if -0.50 < g < 2.0:
                                    fwd_0y = g
                                    n_0y = 1
                                    if has_n:
                                        raw_n = re.loc['0y', 'numberOfAnalysts']
                                        if hasattr(raw_n, '__len__'):
                                            raw_n = raw_n.iloc[0]
                                        if raw_n is not None and not (isinstance(raw_n, float) and np.isnan(raw_n)):
                                            n_0y = max(1, int(raw_n))
                        except Exception as e:
                            logger.debug(f'revenue_estimate 0y parse error: {e}')

            except Exception as e:
                logger.debug(f'revenue_estimate fetch failed: {e}')

        # ── Source 3: 2yr forward earnings growth proxy (last resort before trailing) ──
        # earningsGrowth in yfinance is trailing quarterly YoY — not a true forward.
        # Only use if it looks plausible (tight bounds) and no forward revenue exists.
        earnings_proxy = None
        eg = info.get('earningsGrowth')
        if eg is not None and 0.0 < eg < 1.50:   # exclude wild outliers and negatives
            earnings_proxy = float(eg) * 0.55     # earnings grow faster than revenue; scale down

        # ── Source 4 & 5: trailing from financials ────────────────────────────
        cagr_2yr = None
        hist_1yr = None
        if not financials.empty:
            if len(financials.columns) >= 3:
                r0 = financials.iloc[:, 0].get('Total Revenue', 0)
                r2 = financials.iloc[:, 2].get('Total Revenue', 0)
                if r0 and r2 and r2 > 0 and r0 > 0:
                    cagr_2yr = (r0 / r2) ** 0.5 - 1
            if len(financials.columns) >= 2:
                r0 = financials.iloc[:, 0].get('Total Revenue', 0)
                r1 = financials.iloc[:, 1].get('Total Revenue', 1)
                if r0 and r1 and r1 > 0:
                    hist_1yr = r0 / r1 - 1

        # ── Pick Y1 in priority order ─────────────────────────────────────────
        if fwd_1y is not None and n_1y >= 3:
            y1_growth = fwd_1y
            logger.debug(f'Growth Y1: forward +1y consensus ({n_1y} analysts): {y1_growth:.1%}')
        elif fwd_0y is not None and n_0y >= 3:
            y1_growth = fwd_0y
            logger.debug(f'Growth Y1: forward 0y consensus ({n_0y} analysts): {y1_growth:.1%}')
        elif fwd_1y is not None and n_1y >= 1:
            # Thin coverage but still a forward signal — better than trailing
            y1_growth = fwd_1y
            logger.debug(f'Growth Y1: forward +1y low-coverage ({n_1y} analysts): {y1_growth:.1%}')
        elif fwd_0y is not None and n_0y >= 1:
            y1_growth = fwd_0y
            logger.debug(f'Growth Y1: forward 0y low-coverage ({n_0y} analysts): {y1_growth:.1%}')
        elif earnings_proxy is not None:
            y1_growth = earnings_proxy
            logger.debug(f'Growth Y1: earnings proxy: {y1_growth:.1%}')
        elif info.get('revenueGrowth') and info['revenueGrowth'] > 0:
            y1_growth = float(info['revenueGrowth'])
            logger.debug(f'Growth Y1: trailing revenueGrowth from info: {y1_growth:.1%}')
        elif cagr_2yr is not None and cagr_2yr > 0:
            y1_growth = cagr_2yr
            logger.debug(f'Growth Y1: trailing 2yr CAGR: {y1_growth:.1%}')
        elif hist_1yr is not None and hist_1yr > 0:
            y1_growth = hist_1yr
            logger.debug(f'Growth Y1: trailing 1yr: {y1_growth:.1%}')
        else:
            net_income = info.get('netIncomeToCommon', 0) or 0
            y1_growth = 0.03 if net_income > 0 else 0.0
            logger.debug(f'Growth Y1: floor ({y1_growth:.1%})')

        y1_growth = max(0.0, min(y1_growth, 0.60))

        # ── Y2 / Y3: converge toward terminal, not a blind % decay ───────────
        # Y2 = 2/3 of the way from Y1 toward terminal
        # Y3 = 1/3 of the way from Y1 toward terminal  (nearest to terminal)
        t = TERMINAL_DEFAULT
        y2_growth = y1_growth * 0.67 + t * 0.33
        y3_growth = y1_growth * 0.33 + t * 0.67

        return {
            'y1': round(y1_growth, 4),
            'y2': round(y2_growth, 4),
            'y3': round(y3_growth, 4),
            'terminal': t,
        }

    def _estimate_tax_rate(self, financials: pd.DataFrame, info: dict) -> float:
        """Calculate effective tax rate from financial statements"""
        try:
            if not financials.empty:
                latest = financials.iloc[:, 0]
                pretax_income = latest.get('Pretax Income', 0)
                tax_provision = latest.get('Tax Provision', 0)

                if pretax_income > 0:
                    effective_rate = tax_provision / pretax_income
                    return max(0, min(effective_rate, 0.35))  # Between 0% and 35%

            # Fallback to standard corporate rate
            return 0.21  # US federal corporate tax rate
        except:
            return 0.21

    def _calculate_beta(self, hist: pd.DataFrame, ticker: str) -> float:
        """
        Calculate beta using 5-year regression against S&P 500.
        """
        try:
            if hist.empty or len(hist) < 252:  # Need at least 1 year
                logger.warning(f"Insufficient price history for beta calculation")
                return 1.0

            # Get S&P 500 returns
            spy = yf.Ticker("SPY")
            spy_hist = spy.history(period="5y")

            # Align dates
            merged = pd.merge(
                hist[['Close']].rename(columns={'Close': 'stock'}),
                spy_hist[['Close']].rename(columns={'Close': 'spy'}),
                left_index=True,
                right_index=True,
                how='inner'
            )

            # Calculate returns
            merged['stock_ret'] = merged['stock'].pct_change()
            merged['spy_ret'] = merged['spy'].pct_change()
            merged = merged.dropna()

            # Calculate beta (covariance / variance)
            covariance = merged['stock_ret'].cov(merged['spy_ret'])
            variance = merged['spy_ret'].var()
            beta = covariance / variance if variance > 0 else 1.0

            # Blume adjustment: shrinks extreme betas toward 1.0
            # (0.67 × raw + 0.33 × 1.0) — reduces systematic WACC overstatement
            beta = 0.67 * beta + 0.33

            # Reasonable bounds
            beta = max(0.3, min(beta, 3.5))

            logger.info(f"Calculated beta for {ticker}: {beta:.2f}")
            return beta

        except Exception as e:
            logger.warning(f"Could not calculate beta: {e}")
            return 1.0  # Market beta as default

    def _estimate_size_premium(self, market_cap: float) -> float:
        """
        Estimate size premium based on market capitalization.
        Smaller companies have higher cost of equity.
        """
        if market_cap < 1e9:  # < $1B
            return 0.03
        elif market_cap < 5e9:  # < $5B
            return 0.02
        elif market_cap < 25e9:  # < $25B
            return 0.01
        else:  # Large cap
            return 0.0

    def _get_comparable_multiples(self, info: dict, data: dict) -> Dict[str, float]:
        """
        Extract or estimate comparable company multiples.
        """
        try:
            # Try to get from info
            trailing_pe = info.get('trailingPE', 20.0)
            forward_pe = info.get('forwardPE', 18.0)
            peg_ratio = info.get('pegRatio', 1.5)

            # Calculate EV/EBITDA
            enterprise_value = data['market_cap'] + data['debt'] - data['cash']
            ev_ebitda = enterprise_value / data['ebitda'] if data['ebitda'] > 0 else 12.0

            # Use sector averages as bounds
            sector_multiples = self._get_sector_multiples(data['sector'])

            return {
                'ev_ebitda': min(max(ev_ebitda, sector_multiples['ev_ebitda'] * 0.5), sector_multiples['ev_ebitda'] * 1.5),
                'pe': min(max(trailing_pe, sector_multiples['pe'] * 0.5), sector_multiples['pe'] * 1.5),
                'peg': max(0.5, min(peg_ratio, 3.0))
            }
        except:
            return {'ev_ebitda': 12.0, 'pe': 20.0, 'peg': 1.5}

    def _get_sector_multiples(self, sector: str) -> Dict[str, float]:
        """
        Industry-average multiples for different sectors.
        Based on typical market valuations.
        """
        sector_data = {
            'Technology': {'ev_ebitda': 15.0, 'pe': 25.0},
            'Healthcare': {'ev_ebitda': 14.0, 'pe': 22.0},
            'Financial Services': {'ev_ebitda': 10.0, 'pe': 15.0},
            'Consumer Cyclical': {'ev_ebitda': 10.0, 'pe': 18.0},
            'Consumer Defensive': {'ev_ebitda': 11.0, 'pe': 20.0},
            'Industrials': {'ev_ebitda': 10.0, 'pe': 18.0},
            'Energy': {'ev_ebitda': 8.0, 'pe': 12.0},
            'Utilities': {'ev_ebitda': 9.0, 'pe': 16.0},
            'Real Estate': {'ev_ebitda': 12.0, 'pe': 25.0},
            'Communication Services': {'ev_ebitda': 12.0, 'pe': 20.0},
        }

        return sector_data.get(sector, {'ev_ebitda': 12.0, 'pe': 20.0})

    def get_peer_companies(self, ticker: str, limit: int = 10) -> List[Dict]:
        """
        Auto-select peer companies based on sector and market cap.

        Args:
            ticker: Primary company ticker
            limit: Number of peers to return

        Returns:
            List of peer company data dictionaries
        """
        try:
            stock = yf.Ticker(ticker)
            info = stock.info

            sector = info.get('sector', '')
            industry = info.get('industry', '')
            market_cap = info.get('marketCap', 0)

            # This is a simplified version - in production, you'd query a database
            # of all stocks filtered by sector/industry/market cap

            logger.info(f"Found peers for {ticker} in {sector} sector")

            # For now, return empty list (implement comprehensive peer search later)
            return []

        except Exception as e:
            logger.error(f"Error finding peers for {ticker}: {e}")
            return []

    def get_real_time_price(self, ticker: str) -> Optional[float]:
        """Get current real-time stock price"""
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            return info.get('currentPrice', info.get('regularMarketPrice'))
        except:
            return None

    def validate_ticker(self, ticker: str) -> bool:
        """Check if ticker is valid"""
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            return 'symbol' in info and info.get('regularMarketPrice') is not None
        except:
            return False


# Convenience function for API endpoint
def fetch_company_by_ticker(ticker: str) -> Optional[Dict]:
    """
    Quick function to fetch company data by ticker.
    Used by API endpoints.
    """
    integrator = DataIntegrator()
    return integrator.get_company_data(ticker)


if __name__ == "__main__":
    # Test the data integrator
    logging.basicConfig(level=logging.INFO)

    print("=" * 80)
    print("INSTITUTIONAL DATA INTEGRATOR - TEST")
    print("=" * 80)

    ticker = input("\nEnter ticker symbol (e.g., AAPL, MSFT, GOOGL): ").strip().upper()

    integrator = DataIntegrator()
    data = integrator.get_company_data(ticker)

    if data:
        print(f"\n✓ Successfully fetched data for {data['name']}")
        print(f"\n{'=' * 80}")
        print("COMPANY OVERVIEW")
        print(f"{'=' * 80}")
        print(f"Name:           {data['name']}")
        print(f"Ticker:         {data['ticker']}")
        print(f"Sector:         {data['sector']}")
        print(f"Industry:       {data['industry']}")
        print(f"Current Price:  ${data['current_price']:,.2f}")
        print(f"Market Cap:     ${data['market_cap']:,.0f}")

        print(f"\n{'=' * 80}")
        print("FINANCIALS (Most Recent Year)")
        print(f"{'=' * 80}")
        print(f"Revenue:        ${data['revenue']:,.0f}")
        print(f"EBITDA:         ${data['ebitda']:,.0f}")
        print(f"Depreciation:   ${data['depreciation']:,.0f}")
        print(f"Debt:           ${data['debt']:,.0f}")
        print(f"Cash:           ${data['cash']:,.0f}")
        print(f"Shares Out:     {data['shares_outstanding']:,.0f}")

        print(f"\n{'=' * 80}")
        print("ASSUMPTIONS")
        print(f"{'=' * 80}")
        print(f"Growth Y1:      {data['growth_rate_y1']*100:.1f}%")
        print(f"Growth Y2:      {data['growth_rate_y2']*100:.1f}%")
        print(f"Growth Y3:      {data['growth_rate_y3']*100:.1f}%")
        print(f"Terminal:       {data['terminal_growth']*100:.1f}%")
        print(f"Tax Rate:       {data['tax_rate']*100:.1f}%")
        print(f"Beta:           {data['beta']:.2f}")
        print(f"Risk-Free:      {data['risk_free_rate']*100:.2f}%")

        print(f"\n{'=' * 80}")
        print("COMPARABLE MULTIPLES")
        print(f"{'=' * 80}")
        print(f"EV/EBITDA:      {data['comparable_ev_ebitda']:.1f}x")
        print(f"P/E:            {data['comparable_pe']:.1f}x")
        print(f"PEG:            {data['comparable_peg']:.2f}")

        print(f"\n✓ Data ready for valuation!")
    else:
        print(f"\n✗ Could not fetch data for {ticker}")
