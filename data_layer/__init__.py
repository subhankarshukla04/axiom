"""
DataLayer — unified gateway for all external data sources.
Priority: EDGAR > FRED > Finnhub > FMP > yfinance (fallback)
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class DataResult:
    value: Any
    source: str              # e.g. "SEC EDGAR XBRL" | "FRED:DGS10" | "Finnhub" | "yfinance (fallback)"
    fetched_at: datetime = field(default_factory=datetime.utcnow)
    gap_reason: Optional[str] = None   # None if value present; reason string if missing
    is_primary: bool = True            # False if yfinance fallback was used

    @property
    def available(self) -> bool:
        return self.value is not None and self.gap_reason is None

    def to_dict(self) -> dict:
        return {
            'value': self.value,
            'source': self.source,
            'fetched_at': self.fetched_at.isoformat(),
            'gap_reason': self.gap_reason,
            'is_primary': self.is_primary,
        }


class DataLayer:
    """
    Single gateway for all external data. Instantiate once and pass around.
    All methods return DataResult objects — callers must check .available.
    """

    def __init__(self):
        from data_layer.cache import DataCache
        from data_layer.edgar import EdgarClient
        from data_layer.fred import FredClient
        from data_layer.finnhub import FinnhubClient
        from data_layer.fmp import FmpClient
        self.cache = DataCache()
        self.edgar = EdgarClient(self.cache)
        self.fred = FredClient(self.cache)
        self.finnhub = FinnhubClient(self.cache)
        self.fmp = FmpClient(self.cache)

    # ── Macro / Risk-Free Rate ────────────────────────────────────────────────

    def get_risk_free_rate(self) -> DataResult:
        """10-year Treasury yield from FRED DGS10."""
        return self.fred.get_series('DGS10', label='risk_free_10y')

    def get_macro_rates(self) -> dict:
        """Returns dict of all macro rates with DataResult values."""
        series = {
            'risk_free_10y': 'DGS10',
            'risk_free_2y': 'DGS2',
            'hy_spread': 'BAMLH0A0HYM2',
            'ig_spread': 'BAMLC0A0CM',
            'fed_funds': 'FEDFUNDS',
            'vix': 'VIXCLS',
            'cpi_yoy': 'CPIAUCSL',
            'gdp_real': 'A191RL1Q225SBEA',
            'yield_curve': 'T10Y2Y',
        }
        return {label: self.fred.get_series(sid, label=label) for label, sid in series.items()}

    # ── Company Financials ────────────────────────────────────────────────────

    def get_company_financials(self, ticker: str) -> DataResult:
        """
        Fetch latest annual financials from SEC EDGAR XBRL.
        Falls back to yfinance if EDGAR lookup fails.
        """
        result = self.edgar.get_financials(ticker)
        if result.available:
            return result
        # yfinance fallback
        return self._yfinance_financials_fallback(ticker)

    def get_realtime_price(self, ticker: str) -> DataResult:
        """Real-time quote from Finnhub; yfinance fallback."""
        result = self.finnhub.get_quote(ticker)
        if result.available:
            return result
        return self._yfinance_price_fallback(ticker)

    def get_sector_multiples(self, sector: str) -> DataResult:
        """Sector median EV/EBITDA and P/E from FMP."""
        return self.fmp.get_sector_multiples(sector)

    def get_analyst_consensus(self, ticker: str) -> DataResult:
        """Consensus EPS and price target from FMP."""
        return self.fmp.get_consensus(ticker)

    def get_insider_trades(self, ticker: str, limit: int = 20) -> DataResult:
        """Recent Form 4 insider transactions from SEC EDGAR."""
        return self.edgar.get_form4(ticker, limit=limit)

    def get_institutional_holdings(self, ticker: str) -> DataResult:
        """13F-HR institutional holdings from SEC EDGAR."""
        return self.edgar.get_13f(ticker)

    # ── Internal fallbacks ────────────────────────────────────────────────────

    def _yfinance_financials_fallback(self, ticker: str) -> DataResult:
        try:
            import yfinance as yf
            t = yf.Ticker(ticker)
            info = t.info
            revenue = info.get('totalRevenue')
            ebitda = info.get('ebitda')
            if revenue:
                return DataResult(
                    value={
                        'revenue': revenue,
                        'ebitda': ebitda,
                        'total_debt': info.get('totalDebt', 0),
                        'cash': info.get('totalCash', 0),
                        'shares_outstanding': info.get('sharesOutstanding', 0),
                        'capex': info.get('capitalExpenditures', 0),
                        'operating_cash_flow': info.get('operatingCashflow', 0),
                    },
                    source='yfinance (fallback)',
                    is_primary=False,
                )
            return DataResult(value=None, source='yfinance (fallback)',
                              gap_reason='yfinance returned no revenue data', is_primary=False)
        except Exception as e:
            return DataResult(value=None, source='yfinance (fallback)',
                              gap_reason=f'yfinance error: {e}', is_primary=False)

    def _yfinance_price_fallback(self, ticker: str) -> DataResult:
        try:
            import yfinance as yf
            t = yf.Ticker(ticker)
            hist = t.history(period='1d')
            if not hist.empty:
                price = float(hist['Close'].iloc[-1])
                return DataResult(value=price, source='yfinance (fallback)', is_primary=False)
            return DataResult(value=None, source='yfinance (fallback)',
                              gap_reason='No price history returned', is_primary=False)
        except Exception as e:
            return DataResult(value=None, source='yfinance (fallback)',
                              gap_reason=f'yfinance error: {e}', is_primary=False)
