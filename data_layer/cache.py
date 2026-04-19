"""
SQLite-backed response cache for DataLayer.
TTL by data type:
  Finnhub prices    60s
  FRED rates        4h
  EDGAR financials  24h
  FMP consensus     4h
  Form 4 / 13F      1h
"""

import sqlite3
import json
import os
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)

_TTL = {
    'finnhub':  60,
    'fred':     4 * 3600,
    'edgar':    24 * 3600,
    'fmp':      4 * 3600,
    'form4':    3600,
    '13f':      3600,
    'default':  3600,
}


class DataCache:
    """Thread-safe SQLite cache for external API responses."""

    def __init__(self, db_path: str = 'valuations.db'):
        # Use same db as main app if it exists, else create separate
        if not os.path.exists(db_path):
            db_path = 'valuation.db'
        self.db_path = db_path
        self._ensure_table()

    def _ensure_table(self):
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute('''
                CREATE TABLE IF NOT EXISTS data_cache (
                    cache_key TEXT PRIMARY KEY,
                    source    TEXT,
                    response_json TEXT,
                    fetched_at TEXT,
                    expires_at TEXT
                )
            ''')
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f'Cache table creation failed: {e}')

    def _ttl_seconds(self, source_type: str) -> int:
        for key in _TTL:
            if key in source_type.lower():
                return _TTL[key]
        return _TTL['default']

    def get(self, cache_key: str) -> Optional[Any]:
        try:
            conn = sqlite3.connect(self.db_path)
            row = conn.execute(
                'SELECT response_json, expires_at FROM data_cache WHERE cache_key = ?',
                (cache_key,)
            ).fetchone()
            conn.close()
            if row:
                expires_at = datetime.fromisoformat(row[1])
                if datetime.utcnow() < expires_at:
                    return json.loads(row[0])
        except Exception as e:
            logger.debug(f'Cache get error for {cache_key}: {e}')
        return None

    def set(self, cache_key: str, value: Any, source_type: str = 'default'):
        try:
            ttl = self._ttl_seconds(source_type)
            now = datetime.utcnow()
            expires_at = now + timedelta(seconds=ttl)
            conn = sqlite3.connect(self.db_path)
            conn.execute('''
                INSERT OR REPLACE INTO data_cache
                    (cache_key, source, response_json, fetched_at, expires_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (cache_key, source_type, json.dumps(value), now.isoformat(), expires_at.isoformat()))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug(f'Cache set error for {cache_key}: {e}')

    def invalidate(self, cache_key: str):
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute('DELETE FROM data_cache WHERE cache_key = ?', (cache_key,))
            conn.commit()
            conn.close()
        except Exception:
            pass
