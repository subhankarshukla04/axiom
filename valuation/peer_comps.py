"""
Phase 2 — live peer-comp computation with Bayesian shrinkage.

What this replaces
------------------
The old `get_multiples(tag, growth)` returned hand-curated EV/EBITDA and P/E
from `valuation/config/subsector_multiples.json`. Those numbers were
hand-picked once and never updated. This module derives the same multiples
*live* from the subject ticker's SEC-EDGAR-discovered peer set, then shrinks
toward the JSON sector median so we don't blow up on a 3-peer cohort.

How it works
------------
1. `peer_discovery.find_peers(ticker)` returns up to N peers via SIC matching.
2. For each peer, `_fetch_peer_multiples(ticker)` pulls trailing EV/EBITDA,
   trailing P/E, P/B from yfinance with sanity ranges.
3. Peer set → median per multiple (median, not mean — robust to outliers).
4. Bayesian shrinkage to sector median:
       μ_posterior = (n * peer_median + k * sector_median) / (n + k)
   With k=SHRINKAGE_K (default 5): n=5 peers → 50/50 weight; n=15 → 75/25.
5. Optional PEG-style growth adjustment kept for continuity with the existing
   pipeline. Audit flagged the exponent (0.4) and clip ([0.5, 1.5]) as
   underived — they stay until the Phase 6 factor-model rewrite.

Caching
-------
Per-process LRU cache on `_fetch_peer_multiples`. Phase 2.1 will move this
behind `data_layer/cache.py` so it survives across requests.

Kill switch
-----------
Set `AXIOM_USE_PEER_COMPS=0` to skip live calls and force JSON fallback.
Use this in tests or when network is unreliable.
"""

import logging
import os
import statistics
from functools import lru_cache
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

SHRINKAGE_K = 5
MAX_PEERS = 10
ENV_DISABLE = 'AXIOM_USE_PEER_COMPS'

EV_EBITDA_RANGE = (0.5, 200.0)
PE_RANGE        = (0.5, 500.0)
PB_RANGE        = (0.05, 50.0)


def disabled() -> bool:
    return os.getenv(ENV_DISABLE, '1') == '0'


@lru_cache(maxsize=512)
def _fetch_peer_multiples(ticker: str) -> Optional[Dict[str, float]]:
    """Pull trailing EV/EBITDA, trailing P/E, P/B from yfinance for one peer.

    Returns dict with whichever of {'ev_ebitda', 'pe', 'pb'} pass sanity
    bounds, or None if everything is unusable. Yfinance failures are silent
    by design — one bad peer should not poison the comp set.
    """
    if not ticker:
        return None
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info or {}
    except Exception as e:
        logger.debug('yfinance failed for %s: %s', ticker, e)
        return None

    out: Dict[str, float] = {}

    ev_ebitda = info.get('enterpriseToEbitda')
    if ev_ebitda is not None and EV_EBITDA_RANGE[0] < ev_ebitda < EV_EBITDA_RANGE[1]:
        out['ev_ebitda'] = float(ev_ebitda)

    pe = info.get('trailingPE')
    if pe is None or not (PE_RANGE[0] < pe < PE_RANGE[1]):
        pe = info.get('forwardPE')
    if pe is not None and PE_RANGE[0] < pe < PE_RANGE[1]:
        out['pe'] = float(pe)

    pb = info.get('priceToBook')
    if pb is not None and PB_RANGE[0] < pb < PB_RANGE[1]:
        out['pb'] = float(pb)

    return out or None


MIN_PEERS_FOR_LIVE = 2  # n=2 → 29% weight to peers under k=5 shrinkage; sane minimum


def find_tag_peers(subject_ticker: str, max_peers: int = MAX_PEERS) -> Tuple[list, str]:
    """Primary (and currently only) peer source: same sub-sector tag in `TICKER_TAG_MAP`.

    Returns (peer_tickers, source_label).
      'tag'  — at least MIN_PEERS_FOR_LIVE peers found in the map
      'none' — too few same-tag peers; caller falls back to JSON sector median

    Why no SIC fallback:
        `peer_discovery.find_peers()` fetches the subject's SIC code but does
        not actually filter peer candidates by it — it returns the first N
        tickers from EDGAR's master list. That fallback returned garbage
        (mixing JPM/XOM/SPY into a "software" peer set) and was actively
        worse than letting the JSON sector median win the fallback. SIC-based
        discovery will be reintroduced once `peer_discovery` is fixed to
        actually filter by SIC code (TODO; tracked in CODEBASE_AUDIT.md W1).
    """
    from valuation._config import TICKER_TAG_MAP

    subject = subject_ticker.upper()
    subject_tag = TICKER_TAG_MAP.get(subject)
    if not subject_tag:
        return [], 'none'

    same_tag = [t for t, tag in TICKER_TAG_MAP.items()
                if tag == subject_tag and t != subject]
    if len(same_tag) >= MIN_PEERS_FOR_LIVE:
        return same_tag[:max_peers], 'tag'
    return [], 'none'


def compute_peer_multiples(subject_ticker: str, max_peers: int = MAX_PEERS) -> Optional[Dict]:
    """Returns dict with peer-median multiples + counts, or None if peer fetch fails.

    Schema:
        {
          'source': 'tag' | 'sic' | 'none',
          'peer_count': 8,
          'peer_tickers': ['MSFT', 'ORCL', ...],
          'ev_ebitda': 17.4,            # optional
          'n_peers_ev_ebitda': 6,       # optional
          'pe': 24.1,
          'n_peers_pe': 7,
          'pb': 5.8,
          'n_peers_pb': 5,
        }
    """
    peers, source = find_tag_peers(subject_ticker, max_peers=max_peers)
    if not peers:
        return None

    ev_ebitdas, pes, pbs, used = [], [], [], []
    for t in peers:
        m = _fetch_peer_multiples(t)
        if not m:
            continue
        used.append(t)
        if 'ev_ebitda' in m: ev_ebitdas.append(m['ev_ebitda'])
        if 'pe' in m:        pes.append(m['pe'])
        if 'pb' in m:        pbs.append(m['pb'])

    out: Dict = {
        'source':        source,
        'peer_count':    len(peers),
        'peer_tickers':  used,
    }
    if ev_ebitdas:
        out['ev_ebitda']         = statistics.median(ev_ebitdas)
        out['n_peers_ev_ebitda'] = len(ev_ebitdas)
    if pes:
        out['pe']         = statistics.median(pes)
        out['n_peers_pe'] = len(pes)
    if pbs:
        out['pb']         = statistics.median(pbs)
        out['n_peers_pb'] = len(pbs)

    if not any(k in out for k in ('ev_ebitda', 'pe', 'pb')):
        return None
    return out


def shrink(peer_estimate: float, sector_estimate: float, n: int, k: int = SHRINKAGE_K) -> float:
    """Bayesian shrinkage. n peers, k-strength prior on sector mean.

      μ_posterior = (n * peer + k * sector) / (n + k)

    n=0 → return sector. n→∞ → return peer.
    """
    if n <= 0:
        return sector_estimate
    return (n * peer_estimate + k * sector_estimate) / (n + k)


def get_peer_shrunk_multiples(
    ticker: str,
    sector_ev_ebitda: Optional[float],
    sector_pe: Optional[float],
    company_growth: Optional[float],
    sector_growth: Optional[float],
    max_peers: int = MAX_PEERS,
) -> Tuple[Optional[float], Optional[float], Dict]:
    """Top-level entry point used by `valuation/normalizers.get_multiples()`.

    Returns
    -------
    (ev_ebitda, pe, trace)
        Both multiples may be None when the peer set fails or the JSON sector
        prior is null (banks/REITs/insurance — they bypass this path entirely
        in the live engine, but we still emit `None, None, trace` for them).
        `trace` is always a dict — the caller logs it for transparency.
    """
    trace: Dict = {
        'ticker':                 ticker,
        'sector_ev_ebitda_prior': sector_ev_ebitda,
        'sector_pe_prior':        sector_pe,
    }

    if disabled():
        trace['peer_comp_status'] = 'disabled'
        return None, None, trace

    peer = compute_peer_multiples(ticker, max_peers=max_peers)
    if not peer:
        trace['peer_comp_status'] = 'no_peers'
        return None, None, trace

    trace.update({
        'peer_comp_status': 'ok',
        'source':           peer.get('source'),
        'peer_count':       peer.get('peer_count'),
        'peer_tickers':     peer.get('peer_tickers'),
    })

    ev_out: Optional[float] = None
    pe_out: Optional[float] = None

    if 'ev_ebitda' in peer and sector_ev_ebitda is not None:
        n = peer.get('n_peers_ev_ebitda', 0)
        ev_out = shrink(peer['ev_ebitda'], sector_ev_ebitda, n)
        trace.update({
            'ev_ebitda_peer_median': peer['ev_ebitda'],
            'ev_ebitda_n_peers':     n,
            'ev_ebitda_shrunk':      ev_out,
        })

    if 'pe' in peer and sector_pe is not None:
        n = peer.get('n_peers_pe', 0)
        pe_out = shrink(peer['pe'], sector_pe, n)
        trace.update({
            'pe_peer_median': peer['pe'],
            'pe_n_peers':     n,
            'pe_shrunk':      pe_out,
        })

    # PEG-style growth adjustment kept for continuity; flagged for Phase 6.
    if (sector_growth and sector_growth > 0
            and company_growth and company_growth > 0):
        adj = (company_growth / sector_growth) ** 0.4
        adj = max(0.5, min(adj, 1.5))
        trace['peg_adjustment'] = adj
        if ev_out is not None: ev_out *= adj
        if pe_out is not None: pe_out *= adj

    return ev_out, pe_out, trace


def clear_cache() -> None:
    _fetch_peer_multiples.cache_clear()
