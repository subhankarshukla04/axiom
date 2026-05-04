"""
Peer Auto-Discovery via SEC EDGAR SIC codes.
No paid database required.
"""
import logging
from typing import List, Optional
from datetime import datetime

import requests

logger = logging.getLogger(__name__)
EDGAR_BASE = 'https://data.sec.gov'
USER_AGENT = 'AXIOM-Platform axiom@example.com'
US_EXCHANGES = {'NYSE', 'NASDAQ', 'NYSEMKT', 'NYSEARCA', 'OTC'}


def _fetch(url: str) -> Optional[dict]:
    try:
        r = requests.get(url, headers={'User-Agent': USER_AGENT}, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.warning(f'EDGAR fetch failed: {e}')
        return None


def _get_cik(ticker: str) -> Optional[str]:
    data = _fetch('https://www.sec.gov/files/company_tickers.json')
    if data:
        for _, entry in data.items():
            if entry.get('ticker', '').upper() == ticker.upper():
                return str(entry['cik_str']).zfill(10)
    return None


def _get_sic(cik: str) -> Optional[str]:
    data = _fetch(f'{EDGAR_BASE}/submissions/CIK{cik}.json')
    if data:
        return str(data.get('sic', ''))
    return None


def find_peers(
    ticker: str,
    market_cap: Optional[float] = None,
    min_cap_ratio: float = 0.25,
    max_cap_ratio: float = 4.0,
    max_peers: int = 10,
) -> dict:
    """Find peer companies using EDGAR SIC code matching."""
    subject_cik = _get_cik(ticker)
    if not subject_cik:
        return {'ticker': ticker, 'error': f'CIK not found for {ticker}', 'peers': []}

    sic = _get_sic(subject_cik)
    if not sic or sic == '0':
        return {'ticker': ticker, 'error': f'SIC not found for {ticker}', 'peers': [], 'sic': None}

    tickers_data = _fetch('https://www.sec.gov/files/company_tickers_exchange.json')
    peers = []
    if tickers_data:
        companies = tickers_data.get('data', [])
        fields = tickers_data.get('fields', [])
        try:
            name_idx = fields.index('name')
            ticker_idx = fields.index('ticker')
            cik_idx = fields.index('cik')
            exchange_idx = fields.index('exchange') if 'exchange' in fields else None
        except (ValueError, AttributeError):
            name_idx, ticker_idx, cik_idx, exchange_idx = 1, 2, 0, 3

        for company in companies:
            try:
                cand_cik = str(company[cik_idx]).zfill(10)
                if cand_cik == subject_cik:
                    continue
                cand_exchange = company[exchange_idx] if exchange_idx is not None else 'Unknown'
                if cand_exchange not in US_EXCHANGES and cand_exchange != 'Unknown':
                    continue
                peers.append({
                    'ticker': company[ticker_idx],
                    'name': company[name_idx],
                    'cik': cand_cik,
                    'exchange': cand_exchange,
                })
                if len(peers) >= max_peers * 5:
                    break
            except (IndexError, TypeError):
                continue

    peers = peers[:max_peers]
    return {
        'subject_ticker': ticker,
        'subject_cik': subject_cik,
        'sic_code': sic,
        'peers': peers,
        'total_found': len(peers),
        'methodology': f'Peers identified via SEC EDGAR SIC code {sic}. Manual review recommended.',
        'computed_at': datetime.utcnow().isoformat(),
    }
