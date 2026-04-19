"""
FRED (Federal Reserve Economic Data) client.
Fetches macro series with 4-hour cache.
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

FRED_BASE = 'https://api.stlouisfed.org/fred/series/observations'

FRED_SERIES = {
    'risk_free_10y': 'DGS10',
    'risk_free_2y':  'DGS2',
    'hy_spread':     'BAMLH0A0HYM2',
    'ig_spread':     'BAMLC0A0CM',
    'fed_funds':     'FEDFUNDS',
    'vix':           'VIXCLS',
    'cpi_yoy':       'CPIAUCSL',
    'gdp_real':      'A191RL1Q225SBEA',
    'yield_curve':   'T10Y2Y',
}


class FredClient:
    def __init__(self, cache: DataCache):
        self.cache = cache
        self.api_key = os.environ.get('FRED_API_KEY', '')

    def get_series(self, series_id: str, label: Optional[str] = None) -> DataResult:
        """Fetch latest observation for a FRED series."""
        label = label or series_id
        cache_key = f'fred:{series_id}'
        cached = self.cache.get(cache_key)
        if cached is not None:
            return DataResult(
                value=cached['value'],
                source=f'FRED:{series_id}',
                fetched_at=datetime.fromisoformat(cached['fetched_at']),
            )

        if not self.api_key:
            return DataResult(
                value=None,
                source=f'FRED:{series_id}',
                gap_reason='FRED_API_KEY not set in environment',
            )

        try:
            url = (
                f'{FRED_BASE}?series_id={series_id}'
                f'&api_key={self.api_key}&sort_order=desc&limit=5&file_type=json'
            )
            req = urllib.request.Request(url, headers={'User-Agent': 'AXIOM-Platform/1.0'})
            with urllib.request.urlopen(req, timeout=8) as resp:
                payload = json.loads(resp.read().decode())

            observations = payload.get('observations', [])
            # Take most recent non-missing value
            value = None
            for obs in observations:
                v = obs.get('value', '.')
                if v != '.':
                    value = float(v)
                    break

            if value is None:
                return DataResult(
                    value=None, source=f'FRED:{series_id}',
                    gap_reason=f'No valid observations returned for {series_id}',
                )

            now = datetime.utcnow()
            self.cache.set(cache_key, {'value': value, 'fetched_at': now.isoformat()}, source_type='fred')

            return DataResult(value=value, source=f'FRED:{series_id}', fetched_at=now)

        except Exception as e:
            logger.warning(f'FRED fetch failed for {series_id}: {e}')
            return DataResult(
                value=None, source=f'FRED:{series_id}',
                gap_reason=f'FRED API error: {str(e)}',
            )

    def get_gdp_10yr_average(self) -> DataResult:
        """Fetch 10-year average real GDP growth from A191RL1Q225SBEA."""
        cache_key = 'fred:gdp_10yr_avg'
        cached = self.cache.get(cache_key)
        if cached is not None:
            return DataResult(
                value=cached['value'],
                source='FRED:A191RL1Q225SBEA (10yr avg)',
                fetched_at=datetime.fromisoformat(cached['fetched_at']),
            )

        if not self.api_key:
            return DataResult(value=2.5, source='default (no FRED key)',
                              gap_reason='Using 2.5% default — FRED_API_KEY not set')

        try:
            url = (
                f'{FRED_BASE}?series_id=A191RL1Q225SBEA'
                f'&api_key={self.api_key}&sort_order=desc&limit=40&file_type=json'
            )
            req = urllib.request.Request(url, headers={'User-Agent': 'AXIOM-Platform/1.0'})
            with urllib.request.urlopen(req, timeout=8) as resp:
                payload = json.loads(resp.read().decode())

            observations = payload.get('observations', [])
            values = [float(o['value']) for o in observations if o.get('value', '.') != '.']

            if not values:
                return DataResult(value=2.5, source='FRED:A191RL1Q225SBEA',
                                  gap_reason='No valid observations')

            avg = sum(values) / len(values)
            now = datetime.utcnow()
            self.cache.set(cache_key, {'value': avg, 'fetched_at': now.isoformat()}, source_type='fred')
            return DataResult(value=round(avg, 3), source='FRED:A191RL1Q225SBEA (10yr avg)', fetched_at=now)

        except Exception as e:
            logger.warning(f'FRED GDP fetch failed: {e}')
            return DataResult(value=2.5, source='default fallback',
                              gap_reason=f'FRED error: {e}; using 2.5% default')
