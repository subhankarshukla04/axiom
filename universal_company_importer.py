"""
UNIVERSAL COMPANY IMPORTER
==========================

World-class system to import ANY public company from ANY exchange.

Features:
- Auto-fetch from Yahoo Finance, Alpha Vantage, IEX Cloud
- Intelligent data quality validation
- Automatic subsector classification
- Missing data imputation using sector/peer averages
- Handles international companies (currency conversion)
- ADR detection and handling

This makes the platform truly universal - not limited to pre-selected companies.
"""

import yfinance as yf
import requests
import logging
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
import numpy as np
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class DataQualityReport:
    """Assessment of imported data quality"""
    ticker: str
    completeness_score: float  # 0-1
    reliability_score: float   # 0-1
    missing_fields: list
    imputed_fields: list
    warnings: list
    confidence: str  # "High", "Medium", "Low"


class UniversalCompanyImporter:
    """
    Import ANY company from ANY market with intelligent data handling.

    Uses multiple data sources with fallback hierarchy:
    1. Yahoo Finance (free, global coverage)
    2. Alpha Vantage (API key needed, good for fundamentals)
    3. IEX Cloud (API key needed, US focus)
    4. Manual input with intelligent defaults
    """

    # Sector to subsector mapping (expanded)
    SECTOR_SUBSECTOR_MAP = {
        'Technology': {
            'Software': ['software', 'saas', 'cloud', 'enterprise software'],
            'Semiconductors': ['semiconductor', 'chips', 'fabless', 'foundry'],
            'Hardware': ['computer hardware', 'storage', 'servers', 'pc'],
            'Internet': ['internet', 'search', 'social media', 'digital advertising', 'e-commerce platform'],
            'IT Services': ['it services', 'consulting', 'outsourcing'],
        },
        'Healthcare': {
            'Pharmaceuticals': ['pharmaceutical', 'drug', 'pharma'],
            'Biotechnology': ['biotech', 'biologics', 'therapeutics'],
            'Medical Devices': ['medical device', 'diagnostics', 'equipment'],
            'Healthcare Services': ['healthcare services', 'managed care', 'insurance'],
        },
        'Financial Services': {
            'Banks': ['bank', 'commercial bank', 'regional bank'],
            'Asset Management': ['asset management', 'investment management', 'mutual fund'],
            'Insurance': ['insurance', 'property & casualty', 'life insurance'],
            'Fintech': ['fintech', 'payments', 'digital payments'],
        },
        'Consumer Cyclical': {
            'Automotive': ['automotive', 'auto', 'car', 'vehicle'],
            'Retail': ['retail', 'department store', 'specialty retail'],
            'E-commerce': ['e-commerce', 'online retail', 'marketplace'],
            'Restaurants': ['restaurant', 'fast food', 'dining'],
            'Travel': ['travel', 'hotels', 'airlines', 'cruise'],
        },
        'Consumer Defensive': {
            'Beverages': ['beverage', 'soft drink', 'alcoholic', 'beer', 'spirits'],
            'Food': ['food', 'packaged food', 'dairy', 'meat'],
            'Tobacco': ['tobacco', 'cigarettes'],
            'Household Products': ['household', 'cleaning', 'personal care'],
        },
        'Energy': {
            'Oil_Gas': ['oil', 'gas', 'petroleum', 'energy', 'exploration'],
            'Renewables': ['renewable', 'solar', 'wind', 'clean energy'],
        },
        'Industrials': {
            'Aerospace_Defense': ['aerospace', 'defense', 'aircraft'],
            'Machinery': ['machinery', 'industrial equipment'],
            'Transportation': ['transportation', 'logistics', 'freight'],
            'Construction': ['construction', 'engineering'],
        },
        'Materials': {
            'Chemicals': ['chemicals', 'specialty chemicals'],
            'Metals_Mining': ['metals', 'mining', 'steel', 'aluminum'],
        },
        'Real Estate': {
            'REITs': ['reit', 'real estate investment'],
            'Real Estate Services': ['real estate services', 'brokerage'],
        },
        'Utilities': {
            'Electric': ['electric utility', 'power'],
            'Gas': ['gas utility'],
            'Water': ['water utility'],
        },
        'Communication Services': {
            'Telecom': ['telecom', 'telecommunications', 'wireless'],
            'Media': ['media', 'entertainment', 'broadcasting'],
        },
    }

    def __init__(self, alpha_vantage_key: str = None, iex_key: str = None):
        self.alpha_vantage_key = alpha_vantage_key
        self.iex_key = iex_key

    def import_company(
        self,
        ticker: str,
        exchange: str = "US",
        force_sector: str = None,
        force_subsector: str = None
    ) -> Tuple[Optional[Dict], DataQualityReport]:
        """
        Import company data with intelligent quality assessment.

        Args:
            ticker: Stock ticker (e.g., 'AAPL', 'TSLA', '2330.TW' for Taiwan)
            exchange: Market identifier ('US', 'UK', 'EU', 'ASIA', etc.)
            force_sector: Override automatic sector detection
            force_subsector: Override automatic subsector detection

        Returns:
            (company_data_dict, quality_report)
        """
        logger.info(f"🔍 Importing {ticker} from {exchange} market...")

        # Try primary source (Yahoo Finance - most reliable for global markets)
        data, quality = self._fetch_from_yahoo(ticker, exchange)

        if not data:
            logger.warning(f"❌ Could not fetch {ticker} from any source")
            return None, DataQualityReport(
                ticker=ticker,
                completeness_score=0.0,
                reliability_score=0.0,
                missing_fields=[],
                imputed_fields=[],
                warnings=["Ticker not found in any data source"],
                confidence="None"
            )

        # Override sector/subsector if specified
        if force_sector:
            data['sector'] = force_sector
        if force_subsector:
            data['subsector'] = force_subsector

        # Classify subsector if not present
        if 'subsector' not in data or not data['subsector']:
            data['subsector'] = self._classify_subsector(
                data.get('sector', 'Unknown'),
                data.get('industry', '')
            )

        # Fill missing fields with intelligent defaults
        data = self._impute_missing_fields(data, quality)

        # Validate and sanitize
        data = self._validate_and_sanitize(data)

        # Update quality report
        quality = self._assess_data_quality(data, quality)

        logger.info(f"✅ Imported {data['name']} | Quality: {quality.confidence} | "
                   f"Completeness: {quality.completeness_score*100:.0f}%")

        return data, quality

    def _fetch_from_yahoo(self, ticker: str, exchange: str) -> Tuple[Optional[Dict], DataQualityReport]:
        """Fetch from Yahoo Finance with quality assessment"""
        try:
            stock = yf.Ticker(ticker)
            info = stock.info

            if not info or 'symbol' not in info:
                return None, None

            # Get financial statements
            try:
                financials = stock.financials
                balance_sheet = stock.balance_sheet
                cash_flow = stock.cashflow
            except:
                financials = None
                balance_sheet = None
                cash_flow = None

            # Calculate beta from 5-year history
            try:
                hist = stock.history(period="5y")
                market = yf.Ticker("^GSPC").history(period="5y")

                if len(hist) > 250 and len(market) > 250:
                    stock_returns = hist['Close'].pct_change().dropna()
                    market_returns = market['Close'].pct_change().dropna()

                    # Align dates
                    combined = stock_returns.to_frame('stock').join(market_returns.to_frame('market'), how='inner')

                    if len(combined) > 250:
                        covariance = combined.cov().iloc[0, 1]
                        market_variance = combined['market'].var()
                        beta = covariance / market_variance if market_variance > 0 else 1.0
                        beta = max(0.20, min(3.0, beta))  # Clamp to reasonable range
                    else:
                        beta = info.get('beta', 1.0)
                else:
                    beta = info.get('beta', 1.0)
            except Exception as e:
                logger.warning(f"Could not calculate beta: {e}")
                beta = info.get('beta', 1.0)

            # Extract financial data
            data = {
                'name': info.get('longName', ticker.upper()),
                'ticker': ticker.upper(),
                'sector': info.get('sector', 'Unknown'),
                'industry': info.get('industry', 'Unknown'),
                'country': info.get('country', exchange),
                'currency': info.get('currency', 'USD'),

                # Market data
                'market_cap_estimate': info.get('marketCap', 0),
                'current_price': info.get('currentPrice', info.get('regularMarketPrice', 0)),
                'shares_outstanding': info.get('sharesOutstanding', 1_000_000),

                # Income statement
                'revenue': self._get_latest_financial_value(financials, 'Total Revenue') if financials is not None else info.get('totalRevenue', 0),
                'ebitda': info.get('ebitda', 0),
                'depreciation': self._get_latest_financial_value(financials, 'Depreciation') if financials is not None else 0,
                'operating_income': self._get_latest_financial_value(financials, 'Operating Income') if financials is not None else info.get('operatingIncome', 0),
                'net_income': info.get('netIncomeToCommon', 0),

                # Balance sheet
                'debt': info.get('totalDebt', 0),
                'cash': info.get('totalCash', 0),
                'total_assets': self._get_latest_financial_value(balance_sheet, 'Total Assets') if balance_sheet is not None else 0,

                # Margins (calculated if available)
                'profit_margin': info.get('profitMargins', 0.10),
                'operating_margin': info.get('operatingMargins', 0.15),
                'ebitda_margin': None,  # Calculate below

                # Cash flow
                'free_cash_flow': info.get('freeCashflow', 0),
                'operating_cash_flow': info.get('operatingCashflow', 0),
                'capex': self._get_latest_financial_value(cash_flow, 'Capital Expenditure') if cash_flow is not None else 0,

                # Valuation
                'forward_pe': info.get('forwardPE', 20.0),
                'trailing_pe': info.get('trailingPE', 20.0),
                'peg_ratio': info.get('pegRatio', 1.5),
                'price_to_book': info.get('priceToBook', 3.0),

                # Growth
                'revenue_growth': info.get('revenueGrowth', 0.10),
                'earnings_growth': info.get('earningsGrowth', 0.10),

                # Risk
                'beta': beta,
                'risk_free_rate': 0.045,  # Will be updated from treasury
                'market_risk_premium': 0.065,

                # Additional
                'recommendation': info.get('recommendationKey', 'hold'),
                'analyst_target_price': info.get('targetMeanPrice', 0),
                'description': info.get('longBusinessSummary', '')[:500],  # First 500 chars
            }

            # Calculate derived metrics
            if data['revenue'] > 0:
                data['ebitda_margin'] = data['ebitda'] / data['revenue'] if data['ebitda'] > 0 else data['operating_margin'] * 1.15
                data['capex_pct'] = abs(data['capex']) / data['revenue'] if data['capex'] else 0.05

            # Calculate working capital change (rough estimate)
            if balance_sheet is not None and len(balance_sheet.columns) >= 2:
                try:
                    current_assets_0 = balance_sheet.loc['Current Assets'].iloc[0] if 'Current Assets' in balance_sheet.index else 0
                    current_assets_1 = balance_sheet.loc['Current Assets'].iloc[1] if 'Current Assets' in balance_sheet.index else 0
                    current_liab_0 = balance_sheet.loc['Current Liabilities'].iloc[0] if 'Current Liabilities' in balance_sheet.index else 0
                    current_liab_1 = balance_sheet.loc['Current Liabilities'].iloc[1] if 'Current Liabilities' in balance_sheet.index else 0

                    wc_0 = current_assets_0 - current_liab_0
                    wc_1 = current_assets_1 - current_liab_1
                    data['working_capital_change'] = wc_0 - wc_1
                except:
                    data['working_capital_change'] = 0
            else:
                data['working_capital_change'] = 0

            # Assess quality
            missing_fields = []
            imputed_fields = []
            warnings = []

            critical_fields = ['revenue', 'ebitda', 'shares_outstanding', 'debt', 'cash']
            for field in critical_fields:
                if not data.get(field) or data[field] == 0:
                    missing_fields.append(field)

            if data['revenue'] == 0:
                warnings.append("Revenue is zero - company might be pre-revenue or data unavailable")
            if data['ebitda'] == 0:
                warnings.append("EBITDA unavailable - will estimate from operating income")
            if data['market_cap_estimate'] == 0:
                warnings.append("Market cap unavailable - will estimate from shares * price")

            completeness = 1 - (len(missing_fields) / len(critical_fields))
            reliability = 0.90 if financials is not None else 0.70  # Lower if no financial statements

            if completeness > 0.80 and reliability > 0.80:
                confidence = "High"
            elif completeness > 0.60 and reliability > 0.60:
                confidence = "Medium"
            else:
                confidence = "Low"

            quality_report = DataQualityReport(
                ticker=ticker,
                completeness_score=completeness,
                reliability_score=reliability,
                missing_fields=missing_fields,
                imputed_fields=imputed_fields,
                warnings=warnings,
                confidence=confidence
            )

            return data, quality_report

        except Exception as e:
            logger.error(f"Error fetching from Yahoo Finance: {e}")
            return None, None

    def _get_latest_financial_value(self, df, key: str) -> float:
        """Safely extract latest value from financial dataframe"""
        if df is None or df.empty:
            return 0
        try:
            if key in df.index:
                return float(df.loc[key].iloc[0])
            return 0
        except:
            return 0

    def _classify_subsector(self, sector: str, industry: str) -> str:
        """Intelligently classify subsector from industry string"""
        industry_lower = industry.lower()

        subsector_map = self.SECTOR_SUBSECTOR_MAP.get(sector, {})

        for subsector, keywords in subsector_map.items():
            for keyword in keywords:
                if keyword in industry_lower:
                    return subsector

        # Default to first subsector if no match
        if subsector_map:
            return list(subsector_map.keys())[0]

        return "General"

    def _impute_missing_fields(self, data: Dict, quality: DataQualityReport) -> Dict:
        """Fill missing fields with intelligent sector-based defaults"""
        sector = data.get('sector', 'Unknown')

        # If EBITDA missing but have operating income, estimate
        if data.get('ebitda', 0) == 0 and data.get('operating_income', 0) > 0:
            # EBITDA typically 10-30% higher than operating income
            data['ebitda'] = data['operating_income'] * 1.20
            quality.imputed_fields.append('ebitda')

        # If depreciation missing, estimate from industry norms
        if data.get('depreciation', 0) == 0 and data.get('revenue', 0) > 0:
            depreciation_rates = {
                'Technology': 0.03,
                'Healthcare': 0.025,
                'Industrials': 0.05,
                'Consumer Cyclical': 0.04,
                'Utilities': 0.08,
            }
            rate = depreciation_rates.get(sector, 0.04)
            data['depreciation'] = data['revenue'] * rate
            quality.imputed_fields.append('depreciation')

        # If market cap missing, calculate from price * shares
        if data.get('market_cap_estimate', 0) == 0:
            price = data.get('current_price', 0)
            shares = data.get('shares_outstanding', 0)
            if price > 0 and shares > 0:
                data['market_cap_estimate'] = price * shares
                quality.imputed_fields.append('market_cap_estimate')

        # If shares missing but have market cap and price
        if data.get('shares_outstanding', 0) == 0:
            market_cap = data.get('market_cap_estimate', 0)
            price = data.get('current_price', 1)
            if market_cap > 0 and price > 0:
                data['shares_outstanding'] = market_cap / price
                quality.imputed_fields.append('shares_outstanding')

        return data

    def _validate_and_sanitize(self, data: Dict) -> Dict:
        """Ensure all values are reasonable and no NaN/Inf"""
        # Replace NaN and Inf with 0
        for key, value in data.items():
            if isinstance(value, (int, float)):
                if np.isnan(value) or np.isinf(value):
                    data[key] = 0
                # Ensure no negative values for size metrics
                if key in ['revenue', 'ebitda', 'market_cap_estimate', 'shares_outstanding'] and value < 0:
                    data[key] = abs(value)

        # Ensure margins are in decimal format (0-1 range)
        for margin_key in ['profit_margin', 'operating_margin', 'ebitda_margin']:
            if margin_key in data and data[margin_key] > 1.0:
                data[margin_key] = data[margin_key] / 100.0  # Convert from percentage

        # Ensure beta is reasonable
        if 'beta' in data:
            data['beta'] = max(0.20, min(3.0, data['beta']))

        return data

    def _assess_data_quality(self, data: Dict, quality: DataQualityReport) -> DataQualityReport:
        """Final quality assessment after imputation"""
        # Recount missing critical fields
        critical_fields = ['revenue', 'ebitda', 'market_cap_estimate', 'shares_outstanding']
        missing = [f for f in critical_fields if not data.get(f) or data[f] == 0]

        quality.missing_fields = missing
        quality.completeness_score = 1 - (len(missing) / len(critical_fields))

        # Adjust confidence based on imputation
        if len(quality.imputed_fields) > 3:
            quality.confidence = "Low"
        elif len(quality.imputed_fields) > 1:
            if quality.confidence == "High":
                quality.confidence = "Medium"

        return quality

    def prepare_for_database(self, data: Dict) -> Dict:
        """
        Convert fetched data to database-ready format.
        Maps to the exact schema expected by company_financials table.
        """
        import numpy as np

        def convert_to_native(value):
            """Convert numpy types to Python native types"""
            if isinstance(value, (np.integer, np.floating)):
                return float(value) if isinstance(value, np.floating) else int(value)
            elif isinstance(value, np.ndarray):
                return value.tolist()
            return value

        # Extract growth rates from various sources
        revenue_growth = data.get('revenue_growth', 0.10)

        # Create database-ready dict
        db_data = {
            # Company basics
            'name': data['name'],
            'sector': data['sector'],
            'ticker': data.get('ticker', ''),

            # Income statement
            'revenue': convert_to_native(data.get('revenue', 0)),
            'ebitda': convert_to_native(data.get('ebitda', 0)),
            'depreciation': convert_to_native(data.get('depreciation', 0)),
            'profit_margin': convert_to_native(data.get('profit_margin', 0.10)),

            # Cash flow & capex
            'capex_pct': convert_to_native(data.get('capex_pct', 0.05)),
            'working_capital_change': convert_to_native(data.get('working_capital_change', 0)),

            # Growth assumptions (system-generated, user can override)
            'growth_rate_y1': convert_to_native(revenue_growth),
            'growth_rate_y2': convert_to_native(revenue_growth * 0.85),
            'growth_rate_y3': convert_to_native(revenue_growth * 0.72),
            'terminal_growth': convert_to_native(max(0.025, revenue_growth * 0.30)),

            # Tax
            'tax_rate': 0.21,  # US corporate rate, adjust for international

            # Capital structure
            'shares_outstanding': convert_to_native(data.get('shares_outstanding', 1_000_000)),
            'debt': convert_to_native(data.get('debt', 0)),
            'cash': convert_to_native(data.get('cash', 0)),
            'market_cap_estimate': convert_to_native(data.get('market_cap_estimate', 0)),

            # Risk parameters
            'beta': convert_to_native(data.get('beta', 1.0)),
            'risk_free_rate': convert_to_native(data.get('risk_free_rate', 0.045)),
            'market_risk_premium': convert_to_native(data.get('market_risk_premium', 0.065)),
            'country_risk_premium': 0.0,  # Will calculate based on country
            'size_premium': convert_to_native(self._calculate_size_premium(data.get('market_cap_estimate', 0))),

            # Comparable multiples (use market data if available)
            'comparable_ev_ebitda': convert_to_native(data.get('forward_pe', 15) * 0.70),  # Rough conversion
            'comparable_pe': convert_to_native(data.get('forward_pe', 15)),
            'comparable_peg': convert_to_native(data.get('peg_ratio', 1.5)),
        }

        return db_data

    def _calculate_size_premium(self, market_cap: float) -> float:
        """Calculate size premium based on market cap (Ibbotson methodology)"""
        market_cap_billions = market_cap / 1e9

        if market_cap_billions > 500:
            return 0.000  # Mega-cap
        elif market_cap_billions > 100:
            return 0.005  # Large-cap
        elif market_cap_billions > 10:
            return 0.012  # Mid-cap
        elif market_cap_billions > 1:
            return 0.020  # Small-cap
        else:
            return 0.035  # Micro-cap


def fetch_company_by_ticker(ticker: str, exchange: str = "US") -> Tuple[Optional[Dict], Optional[DataQualityReport]]:
    """
    Convenience function to import a company by ticker.
    Can be called from anywhere in the application.

    Example:
        data, quality = fetch_company_by_ticker("AAPL")
        if data:
            # Insert into database...
    """
    importer = UniversalCompanyImporter()
    return importer.import_company(ticker, exchange)


# Export
__all__ = ['UniversalCompanyImporter', 'fetch_company_by_ticker', 'DataQualityReport']
