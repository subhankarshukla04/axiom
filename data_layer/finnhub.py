"""
Finnhub real-time quote client.
Rate limit: 60 calls/min on free tier.
"""

import os
import json
import time
import logging
import urllib.request
from datetime import datetime
from collections import deque
from typing import Optional
from data_layer import DataResult
from data_layer.cache import DataCache

logger = logging.getLogger(__name__)

FINNHUB_BASE = 'https://finnhub.io/api/v1'


class FinnhubClient:
    def __init__(self, cache: DataCache):
        self.cache = cache
        self.api_key = os.environ.get('FINNHUB_API_KEY', '')
        # Simple in-process rate limiter: track timestamps of last 60 calls
        self._call_times: deque = deque(maxlen=60)

    def _rate_limit(self):
        """Block if approaching 60/min rate limit."""
        now = time.monotonic()
        # Drop calls older than 60 seconds
        while self._call_times and now - self._call_times[0] > 60:
            self._call_times.popleft()
        if len(self._call_times) >= 58:  # Leave 2 buffer
            sleep_for = 60 - (now - self._call_times[0]) + 0.1
            if sleep_for > 0:
                logger.info(f'Finnhub rate limit: sleeping {sleep_for:.1f}s')
                time.sleep(sleep_for)
        self._call_times.append(time.monotonic())

    def _get(self, path: str, params: dict) -> Optional[dict]:
        if not self.api_key:
            return None
        self._rate_limit()
        try:
            qs = '&'.join(f'{k}={v}' for k, v in params.items())
            url = f'{FINNHUB_BASE}/{path}?{qs}&token={self.api_key}'
            req = urllib.request.Request(url, headers={'User-Agent': 'AXIOM-Platform/1.0'})
            with urllib.request.urlopen(req, timeout=8) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:
            logger.warning(f'Finnhub request failed ({path}): {e}')
            return None

    def get_quote(self, ticker: str) -> DataResult:
        """Fetch current price quote for ticker."""
        cache_key = f'finnhub:quote:{ticker}'
        cached = self.cache.get(cache_key)
        if cached is not None:
            return DataResult(
                value=cached['c'],  # current price
                source='Finnhub',
                fetched_at=datetime.fromisoformat(cached['fetched_at']),
            )

        if not self.api_key:
            return DataResult(value=None, source='Finnhub',
                              gap_reason='FINNHUB_API_KEY not set')

        data = self._get('quote', {'symbol': ticker})
        if data and data.get('c', 0) > 0:
            data['fetched_at'] = datetime.utcnow().isoformat()
            self.cache.set(cache_key, data, source_type='finnhub')
            return DataResult(
                value=float(data['c']),
                source='Finnhub',
                fetched_at=datetime.utcnow(),
            )

        return DataResult(value=None, source='Finnhub',
                          gap_reason=f'No valid quote returned for {ticker}')

    def get_company_profile(self, ticker: str) -> DataResult:
        """Fetch company profile (name, exchange, sector, etc.)."""
        cache_key = f'finnhub:profile:{ticker}'
        cached = self.cache.get(cache_key)
        if cached is not None:
            return DataResult(value=cached, source='Finnhub',
                              fetched_at=datetime.fromisoformat(cached.get('fetched_at', datetime.utcnow().isoformat())))

        if not self.api_key:
            return DataResult(value=None, source='Finnhub',
                              gap_reason='FINNHUB_API_KEY not set')

        data = self._get('stock/profile2', {'symbol': ticker})
        if data and data.get('name'):
            data['fetched_at'] = datetime.utcnow().isoformat()
            self.cache.set(cache_key, data, source_type='finnhub')
            return DataResult(value=data, source='Finnhub', fetched_at=datetime.utcnow())

        return DataResult(value=None, source='Finnhub',
                          gap_reason=f'No profile found for {ticker}')
