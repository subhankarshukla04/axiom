"""
Financial Modeling Prep (FMP) client.
Free tier: 250 calls/day.
Provides: sector P/E medians, analyst consensus EPS/price targets.
"""

import os
import json
import logging
import urllib.request
from datetime import datetime
from typing import Optional
from data_layer import DataResult
from data_layer.cache import DataCache

logger = logging.getLogger(__name__)

FMP_BASE = 'https://financialmodelingprep.com/api/v3'


class FmpClient:
    def __init__(self, cache: DataCache):
        self.cache = cache
        self.api_key = os.environ.get('FMP_API_KEY', '')

    def _get(self, path: str, params: dict = None) -> Optional[any]:
        if not self.api_key:
            return None
        try:
            qs = ''
            if params:
                qs = '&' + '&'.join(f'{k}={v}' for k, v in params.items())
            url = f'{FMP_BASE}/{path}?apikey={self.api_key}{qs}'
            req = urllib.request.Request(url, headers={'User-Agent': 'AXIOM-Platform/1.0'})
            with urllib.request.urlopen(req, timeout=8) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:
            logger.warning(f'FMP request failed ({path}): {e}')
            return None

    def get_sector_multiples(self, sector: str) -> DataResult:
        """
        Get median EV/EBITDA and P/E for a sector.
        Uses FMP /sector-pe endpoint (returns all sectors).
        """
        cache_key = f'fmp:sector_multiples:{sector.lower().replace(" ", "_")}'
        cached = self.cache.get(cache_key)
        if cached:
            return DataResult(value=cached, source='FMP sector median',
                              fetched_at=datetime.fromisoformat(cached.get('_fetched_at', datetime.utcnow().isoformat())))

        if not self.api_key:
            return DataResult(value=None, source='FMP sector median',
                              gap_reason='FMP_API_KEY not set')

        data = self._get('sector-pe', {'date': datetime.utcnow().strftime('%Y-%m-%d')})
        if not data:
            return DataResult(value=None, source='FMP sector median',
                              gap_reason='FMP sector-pe endpoint returned no data')

        # Find matching sector (case-insensitive partial match)
        sector_lower = sector.lower()
        match = None
        for item in data:
            if sector_lower in item.get('sector', '').lower() or \
               item.get('sector', '').lower() in sector_lower:
                match = item
                break

        if not match and data:
            # Use first item as proxy if no match
            match = data[0]
            logger.info(f'No exact sector match for "{sector}", using "{match.get("sector")}" as proxy')

        if not match:
            return DataResult(value=None, source='FMP sector median',
                              gap_reason=f'No sector data found for "{sector}"')

        result = {
            'sector': match.get('sector'),
            'pe': float(match.get('pe', 0)) if match.get('pe') else None,
            '_fetched_at': datetime.utcnow().isoformat(),
        }
        self.cache.set(cache_key, result, source_type='fmp')
        return DataResult(value=result, source='FMP sector median', fetched_at=datetime.utcnow())

    def get_consensus(self, ticker: str) -> DataResult:
        """Fetch analyst consensus: EPS estimates and price target."""
        cache_key = f'fmp:consensus:{ticker}'
        cached = self.cache.get(cache_key)
        if cached:
            return DataResult(value=cached, source='FMP consensus',
                              fetched_at=datetime.fromisoformat(cached.get('_fetched_at', datetime.utcnow().isoformat())))

        if not self.api_key:
            return DataResult(value=None, source='FMP consensus',
                              gap_reason='FMP_API_KEY not set')

        # Price target consensus
        pt_data = self._get(f'price-target-consensus/{ticker}')
        # Analyst estimates
        est_data = self._get(f'analyst-estimates/{ticker}', {'period': 'annual', 'limit': '2'})

        result = {}
        if pt_data and isinstance(pt_data, list) and pt_data:
            pt = pt_data[0]
            result['price_target_high'] = pt.get('targetHigh')
            result['price_target_low'] = pt.get('targetLow')
            result['price_target_consensus'] = pt.get('targetConsensus')
            result['analyst_count'] = pt.get('numberOfAnalysts')

        if est_data and isinstance(est_data, list) and est_data:
            est = est_data[0]
            result['eps_avg'] = est.get('estimatedEpsAvg')
            result['eps_high'] = est.get('estimatedEpsHigh')
            result['eps_low'] = est.get('estimatedEpsLow')
            result['revenue_avg'] = est.get('estimatedRevenueAvg')

        if not result:
            return DataResult(value=None, source='FMP consensus',
                              gap_reason=f'No consensus data for {ticker}')

        result['_fetched_at'] = datetime.utcnow().isoformat()
        self.cache.set(cache_key, result, source_type='fmp')
        return DataResult(value=result, source='FMP consensus', fetched_at=datetime.utcnow())
