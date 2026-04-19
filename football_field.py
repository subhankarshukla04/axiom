"""
Football Field Valuation Range Aggregator.
Aggregates all valuation methodologies into unified range chart data.
"""
import logging
from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class ValuationRange:
    method: str
    low: Optional[float]
    high: Optional[float]
    source: str
    gap_reason: Optional[str] = None

    @property
    def available(self) -> bool:
        return self.low is not None and self.high is not None

    def to_dict(self) -> dict:
        return {
            'method': self.method,
            'low': round(self.low, 2) if self.low is not None else None,
            'high': round(self.high, 2) if self.high is not None else None,
            'source': self.source,
            'gap_reason': self.gap_reason,
            'available': self.available,
        }


class FootballField:
    def __init__(self, current_price: Optional[float] = None):
        self.current_price = current_price
        self.ranges: List[ValuationRange] = []

    def add_52_week_range(self, low: float, high: float, source: str = 'yfinance'):
        self.ranges.append(ValuationRange(method='52-Week Range', low=low, high=high, source=source))

    def add_dcf_range(self, bear: float, bull: float, source: str = 'DCF Model'):
        self.ranges.append(ValuationRange(method='DCF (Bear–Bull)', low=bear, high=bull, source=source))

    def add_ev_ebitda_range(self, low: float, high: float, source: str = 'EV/EBITDA Comps'):
        self.ranges.append(ValuationRange(method='EV/EBITDA Comps', low=low, high=high, source=source))

    def add_lbo_floor(self, low: float, high: float, source: str = 'LBO Analysis'):
        self.ranges.append(ValuationRange(method='LBO Floor', low=low, high=high, source=source))

    def add_analyst_targets(self, low: Optional[float], high: Optional[float], source: str = 'FMP consensus'):
        if low is None or high is None:
            self.ranges.append(ValuationRange(
                method='Analyst Price Target', low=None, high=None, source=source,
                gap_reason='Analyst targets not available — FMP_API_KEY required or limit exhausted',
            ))
        else:
            self.ranges.append(ValuationRange(method='Analyst Price Target', low=low, high=high, source=source))

    def add_pe_comps(self, low: Optional[float], high: Optional[float],
                     source: str = 'P/E Comps', gap_reason: Optional[str] = None):
        self.ranges.append(ValuationRange(method='P/E Comps', low=low, high=high,
                                          source=source, gap_reason=gap_reason))

    def to_dict(self) -> dict:
        return {
            'current_price': self.current_price,
            'ranges': [r.to_dict() for r in self.ranges],
            'available_count': sum(1 for r in self.ranges if r.available),
            'gap_count': sum(1 for r in self.ranges if not r.available),
            'computed_at': datetime.utcnow().isoformat(),
        }


def build_football_field(company_data: dict, valuation_results: dict) -> dict:
    """Build football field from company data + valuation results."""
    ff = FootballField(current_price=company_data.get('current_price'))

    low_52 = company_data.get('fifty_two_week_low')
    high_52 = company_data.get('fifty_two_week_high')
    if low_52 and high_52:
        ff.add_52_week_range(low_52, high_52, source='Market data')

    base = valuation_results.get('dcf_value') or valuation_results.get('fair_value')
    if base:
        bear = valuation_results.get('bear_value') or base * 0.80
        bull = valuation_results.get('bull_value') or base * 1.20
        ff.add_dcf_range(bear, bull, source='SEC EDGAR / FRED')

    ev_val = valuation_results.get('ev_ebitda_value')
    if ev_val:
        ff.add_ev_ebitda_range(ev_val * 0.90, ev_val * 1.10, source='FMP sector median')

    consensus = company_data.get('analyst_consensus', {})
    if consensus:
        ff.add_analyst_targets(
            low=consensus.get('price_target_low'),
            high=consensus.get('price_target_high'),
            source='FMP consensus',
        )
    else:
        ff.add_analyst_targets(None, None, source='FMP consensus')

    lbo = valuation_results.get('lbo_result')
    if lbo:
        shares = company_data.get('shares_outstanding', 1)
        if shares and lbo.get('exit_equity'):
            ff.add_lbo_floor(
                lbo.get('entry_equity', 0) / shares,
                lbo.get('exit_equity', 0) / shares,
                source='LBO Analysis',
            )

    if not any(r.available for r in ff.ranges):
        ff.add_pe_comps(None, None, gap_reason='Insufficient sector P/E data')

    return ff.to_dict()
