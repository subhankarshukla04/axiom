"""
Smart Money Tracker
Parses SEC EDGAR 13F-HR filings to track institutional holdings changes.
Note: 13F data is 45 days delayed per SEC regulatory requirement.
"""

import json
import logging
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

EDGAR_BASE = 'https://data.sec.gov'
USER_AGENT = 'AXIOM-Platform axiom@example.com'

# Top institutional filer CIKs (major funds)
TRACKED_FILERS = {
    '0001067983': 'Berkshire Hathaway',
    '0001350694': 'Bridgewater Associates',
    '0000102909': 'Vanguard Group',
    '0000823768': 'BlackRock',
    '0000880285': 'State Street',
    '0001166559': 'Fidelity',
    '0001336528': 'Citadel Advisors',
    '0001037389': 'Tiger Global',
}


def _fetch(url: str) -> Optional[str]:
    try:
        req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read().decode('utf-8', errors='ignore')
    except Exception as e:
        logger.warning(f'EDGAR fetch failed: {e}')
        return None


def _fetch_json(url: str) -> Optional[dict]:
    text = _fetch(url)
    if text:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None
    return None


def get_latest_13f_filing(cik: str) -> Optional[Dict]:
    """
    Get the most recent 13F-HR filing metadata for a given CIK.
    Returns dict with accession number, filing date.
    """
    data = _fetch_json(f'{EDGAR_BASE}/submissions/CIK{cik}.json')
    if not data:
        return None

    filings = data.get('filings', {}).get('recent', {})
    forms = filings.get('form', [])
    dates = filings.get('filingDate', [])
    accessions = filings.get('accessionNumber', [])

    for i, form in enumerate(forms):
        if '13F-HR' in form:
            return {
                'cik': cik,
                'form': form,
                'filing_date': dates[i] if i < len(dates) else '',
                'accession_number': accessions[i] if i < len(accessions) else '',
            }
    return None


def parse_13f_holdings(accession_number: str, cik: str) -> List[Dict]:
    """
    Parse the infotable.xml from a 13F-HR filing to extract holdings.
    Returns list of holdings with nameOfIssuer, shares, value.
    """
    # Accession number format: 0001234567-23-000456 -> 0001234567-23-000456 (for URL: no dashes in path)
    acc_clean = accession_number.replace('-', '')
    index_url = f'{EDGAR_BASE}/Archives/edgar/data/{cik.lstrip("0")}/{acc_clean}/{accession_number}-index.json'

    index_data = _fetch_json(index_url)
    if not index_data:
        return []

    # Find infotable.xml file
    info_table_url = None
    for item in index_data.get('directory', {}).get('item', []):
        name = item.get('name', '')
        if 'infotable' in name.lower() or name.endswith('.xml'):
            info_table_url = f'{EDGAR_BASE}/Archives/edgar/data/{cik.lstrip("0")}/{acc_clean}/{name}'
            break

    if not info_table_url:
        return []

    xml_content = _fetch(info_table_url)
    if not xml_content:
        return []

    holdings = []
    try:
        # Handle namespace in 13F XML
        root = ET.fromstring(xml_content)
        ns = {'ns': 'http://www.sec.gov/edgar/document/thirteenf/informationtable'}

        for entry in root.findall('.//ns:infoTable', ns) or root.findall('.//infoTable'):
            try:
                def get_text(tag):
                    el = entry.find(f'ns:{tag}', ns) or entry.find(tag)
                    return el.text if el is not None else ''

                holdings.append({
                    'name': get_text('nameOfIssuer'),
                    'cusip': get_text('cusip'),
                    'value_1000': int(get_text('value') or 0),
                    'shares': int(get_text('sshPrnamt') or 0),
                    'put_call': get_text('putCall'),
                })
            except Exception:
                continue
    except ET.ParseError as e:
        logger.warning(f'13F XML parse error for {accession_number}: {e}')

    return holdings


def get_smart_money_positions(ticker: str, limit_filers: int = 5) -> Dict:
    """
    Get positions in a given ticker from tracked mega-fund 13F filings.
    Returns summary of who holds it and recent changes.

    Note: This is a simplified implementation. Full quarter-over-quarter
    comparison requires storing prior period filings.

    Args:
        ticker: Stock ticker to look up in 13F filings
        limit_filers: Number of mega-funds to check (API calls = limit_filers)

    Returns:
        dict with holders list and disclosure notice
    """
    positions = []
    filer_list = list(TRACKED_FILERS.items())[:limit_filers]

    for cik, fund_name in filer_list:
        try:
            latest = get_latest_13f_filing(cik)
            if not latest:
                continue

            holdings = parse_13f_holdings(
                latest.get('accession_number', ''),
                cik,
            )

            # Filter holdings to target ticker (name match — CUSIP lookup not available)
            ticker_upper = ticker.upper()
            matched = [
                h for h in holdings
                if ticker_upper in (h.get('name') or '').upper()
            ]

            if matched:
                total_value = sum(h.get('value_1000', 0) for h in matched) * 1000
                total_shares = sum(h.get('shares', 0) for h in matched)
                positions.append({
                    'fund': fund_name,
                    'cik': cik,
                    'latest_13f_date': latest.get('filing_date', ''),
                    'accession': latest.get('accession_number', ''),
                    'shares': total_shares,
                    'value_usd': total_value,
                    'holdings_count': len(matched),
                })
            else:
                # Fund filed but doesn't hold this ticker
                positions.append({
                    'fund': fund_name,
                    'cik': cik,
                    'latest_13f_date': latest.get('filing_date', ''),
                    'accession': latest.get('accession_number', ''),
                    'shares': 0,
                    'value_usd': 0,
                    'holdings_count': 0,
                    'note': 'Not held in latest 13F',
                })
        except Exception as e:
            logger.debug(f'13F lookup failed for {fund_name}: {e}')
            continue

    return {
        'ticker': ticker,
        'tracked_filers_checked': len(positions),
        'positions': positions,
        'disclosure': (
            '13F data is subject to a 45-day regulatory reporting delay '
            'as required by SEC Rule 13f-1. Holdings reflect end-of-quarter '
            'positions reported ~45 days after quarter end. '
            'This is not real-time data.'
        ),
        'fetched_at': datetime.utcnow().isoformat(),
    }
