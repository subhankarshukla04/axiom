"""
SEC EDGAR XBRL client.
Fetches company financials, Form 4 insider trades, 13F holdings.
All free, no API key required.
Required header: User-Agent: AXIOM-Platform your@email.com
"""

import json
import logging
import urllib.request
from datetime import datetime
from typing import Optional
from data_layer import DataResult
from data_layer.cache import DataCache

logger = logging.getLogger(__name__)

EDGAR_BASE = 'https://data.sec.gov'
EDGAR_SEARCH = 'https://efts.sec.gov/LATEST/search-index'
USER_AGENT = 'AXIOM-Platform axiom@example.com'

# XBRL concept mappings — companies use different tags
REVENUE_CONCEPTS = [
    'RevenueFromContractWithCustomerExcludingAssessedTax',
    'Revenues',
    'SalesRevenueNet',
    'RevenueFromContractWithCustomerIncludingAssessedTax',
]
OCF_CONCEPTS = ['NetCashProvidedByUsedInOperatingActivities']
CAPEX_CONCEPTS = ['PaymentsToAcquirePropertyPlantAndEquipment']
LONGTERM_DEBT = ['LongTermDebt', 'LongTermDebtNoncurrent']
SHORT_DEBT = ['ShortTermBorrowings', 'DebtCurrent']
EBITDA_PROXY = ['OperatingIncomeLoss']  # We compute EBITDA = EBIT + D&A
DEPRECIATION = ['DepreciationDepletionAndAmortization', 'Depreciation']


class EdgarClient:
    def __init__(self, cache: DataCache):
        self.cache = cache

    def _fetch(self, url: str) -> Optional[dict]:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:
            logger.warning(f'EDGAR fetch failed ({url[:80]}...): {e}')
            return None

    def lookup_cik(self, ticker: str) -> Optional[str]:
        """Resolve ticker to CIK number (zero-padded to 10 digits)."""
        cache_key = f'edgar:cik:{ticker}'
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        # Use EDGAR company tickers mapping
        data = self._fetch('https://www.sec.gov/files/company_tickers.json')
        if data:
            for _, entry in data.items():
                if entry.get('ticker', '').upper() == ticker.upper():
                    cik = str(entry['cik_str']).zfill(10)
                    self.cache.set(cache_key, cik, source_type='edgar')
                    return cik
        return None

    def _get_latest_value(self, facts: dict, concepts: list) -> Optional[float]:
        """
        Extract the most recent annual value for a set of XBRL concepts.
        Returns the value from the most recent 10-K filing.
        """
        us_gaap = facts.get('us-gaap', {})
        for concept in concepts:
            concept_data = us_gaap.get(concept, {})
            units = concept_data.get('units', {})
            usd_data = units.get('USD', [])
            if not usd_data:
                continue
            # Filter to annual (10-K) filings only
            annual = [
                d for d in usd_data
                if d.get('form') == '10-K' and d.get('val') is not None
            ]
            if annual:
                # Sort by end date descending, take most recent
                annual.sort(key=lambda x: x.get('end', ''), reverse=True)
                return float(annual[0]['val'])
        return None

    def get_financials(self, ticker: str) -> DataResult:
        """
        Fetch latest annual financials from SEC EDGAR XBRL.
        Returns revenue, EBITDA, OCF, CapEx, debt, cash, shares.
        """
        cache_key = f'edgar:financials:{ticker}'
        cached = self.cache.get(cache_key)
        if cached:
            return DataResult(
                value=cached,
                source='SEC EDGAR XBRL',
                fetched_at=datetime.fromisoformat(cached.get('_fetched_at', datetime.utcnow().isoformat())),
            )

        cik = self.lookup_cik(ticker)
        if not cik:
            return DataResult(value=None, source='SEC EDGAR XBRL',
                              gap_reason=f'CIK not found for ticker {ticker}')

        data = self._fetch(f'{EDGAR_BASE}/api/xbrl/companyfacts/CIK{cik}.json')
        if not data:
            return DataResult(value=None, source='SEC EDGAR XBRL',
                              gap_reason=f'XBRL facts not available for CIK {cik}')

        facts = data.get('facts', {})

        revenue = self._get_latest_value(facts, REVENUE_CONCEPTS)
        ocf = self._get_latest_value(facts, OCF_CONCEPTS)
        capex_raw = self._get_latest_value(facts, CAPEX_CONCEPTS)
        # CapEx is reported as negative outflow in XBRL — take abs
        capex = abs(capex_raw) if capex_raw is not None else None
        lt_debt = self._get_latest_value(facts, LONGTERM_DEBT)
        st_debt = self._get_latest_value(facts, SHORT_DEBT)
        total_debt = (lt_debt or 0) + (st_debt or 0)
        depreciation = self._get_latest_value(facts, DEPRECIATION)
        ebit = self._get_latest_value(facts, EBITDA_PROXY)
        ebitda = None
        if ebit is not None and depreciation is not None:
            ebitda = ebit + depreciation

        # FCF = OCF - CapEx
        fcf = None
        if ocf is not None and capex is not None:
            fcf = ocf - capex

        if revenue is None:
            return DataResult(value=None, source='SEC EDGAR XBRL',
                              gap_reason=f'Revenue not found in XBRL facts for {ticker}')

        result = {
            'revenue': revenue,
            'ebitda': ebitda,
            'operating_cash_flow': ocf,
            'capex': capex,
            'free_cash_flow': fcf,
            'total_debt': total_debt,
            'depreciation': depreciation,
            'cik': cik,
            '_fetched_at': datetime.utcnow().isoformat(),
            '_source': 'SEC EDGAR XBRL',
        }
        self.cache.set(cache_key, result, source_type='edgar')

        return DataResult(value=result, source='SEC EDGAR XBRL', fetched_at=datetime.utcnow())

    def get_form4(self, ticker: str, limit: int = 20) -> DataResult:
        """Fetch recent Form 4 (insider transaction) filings."""
        cache_key = f'edgar:form4:{ticker}'
        cached = self.cache.get(cache_key)
        if cached:
            return DataResult(value=cached, source='SEC EDGAR Form 4',
                              fetched_at=datetime.fromisoformat(cached[0].get('_fetched_at', datetime.utcnow().isoformat()) if cached else datetime.utcnow().isoformat()))

        cik = self.lookup_cik(ticker)
        if not cik:
            return DataResult(value=None, source='SEC EDGAR Form 4',
                              gap_reason=f'CIK not found for {ticker}')

        # Get recent filings
        data = self._fetch(
            f'{EDGAR_BASE}/submissions/CIK{cik}.json'
        )
        if not data:
            return DataResult(value=None, source='SEC EDGAR Form 4',
                              gap_reason='Could not fetch EDGAR submissions')

        recent = data.get('filings', {}).get('recent', {})
        forms = recent.get('form', [])
        dates = recent.get('filingDate', [])
        accessions = recent.get('accessionNumber', [])

        trades = []
        for i, form in enumerate(forms):
            if form == '4' and len(trades) < limit:
                trades.append({
                    'form': form,
                    'filing_date': dates[i] if i < len(dates) else '',
                    'accession_number': accessions[i] if i < len(accessions) else '',
                    '_fetched_at': datetime.utcnow().isoformat(),
                })

        if not trades:
            return DataResult(value=[], source='SEC EDGAR Form 4',
                              gap_reason=f'No Form 4 filings found for {ticker}')

        self.cache.set(cache_key, trades, source_type='form4')
        return DataResult(value=trades, source='SEC EDGAR Form 4', fetched_at=datetime.utcnow())

    def get_13f(self, ticker: str) -> DataResult:
        """
        Fetch 13F-HR holdings mentioning ticker from major institutional filers.
        Note: 13F data is 45-day delayed per SEC requirement.
        """
        # Simplified: return a gap result with explanation
        # Full 13F parsing requires XML parsing of each filing
        return DataResult(
            value=None,
            source='SEC EDGAR 13F-HR',
            gap_reason='13F parsing requires XML processing — use smart_money module for full analysis',
        )

    def get_sic_code(self, ticker: str) -> Optional[str]:
        """Get SIC industry code for a company."""
        cache_key = f'edgar:sic:{ticker}'
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        cik = self.lookup_cik(ticker)
        if not cik:
            return None

        data = self._fetch(f'{EDGAR_BASE}/submissions/CIK{cik}.json')
        if data:
            sic = str(data.get('sic', ''))
            if sic:
                self.cache.set(cache_key, sic, source_type='edgar')
                return sic
        return None
