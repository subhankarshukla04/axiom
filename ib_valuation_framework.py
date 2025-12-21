"""
Investment Banking-Grade Valuation Framework
Implements pattern recognition for different company archetypes
Based on Goldman Sachs, Morgan Stanley, JP Morgan methodologies
"""

import logging
from typing import Dict, Tuple, List
from enum import Enum

logger = logging.getLogger(__name__)


class CompanyArchetype(Enum):
    """
    Company classification based on financial characteristics
    Determines which valuation approach to use
    """
    HYPER_GROWTH = "hyper_growth"          # High growth, unprofitable (Uber, DoorDash)
    GROWTH = "growth"                       # Growth + profitable (Tesla, Snowflake)
    STABLE_GROWTH = "stable_growth"         # Moderate growth, stable (Microsoft, Apple)
    MATURE = "mature"                       # Low growth, mature (Coca-Cola, P&G)
    CYCLICAL = "cyclical"                   # Cyclical earnings (Ford, airlines)
    DISTRESSED = "distressed"               # Negative margins, restructuring (Intel currently)
    TURNAROUND = "turnaround"               # Improving from distress
    HIGH_CAPEX = "high_capex"              # Capital intensive (utilities, telcos)
    FINANCIAL = "financial"                 # Banks, insurance (use different metrics)


def classify_company(company_data: Dict) -> Tuple[CompanyArchetype, str]:
    """
    Classify company into archetype based on financial metrics
    Returns: (archetype, explanation)

    This is what Goldman Sachs analysts do mentally when valuing a company
    """
    revenue = float(company_data.get('revenue', 0))
    ebitda = float(company_data.get('ebitda', 0))
    profit_margin = float(company_data.get('profit_margin', 0))
    growth_y1 = float(company_data.get('growth_rate_y1', 0))
    capex_pct = float(company_data.get('capex_pct', 0))
    market_cap = float(company_data.get('market_cap_estimate', 0))
    sector = company_data.get('sector', '')

    # Calculate metrics
    ebitda_margin = ebitda / revenue if revenue > 0 else 0

    # Financial companies use different framework
    if sector in ['Financial Services', 'Banks']:
        return CompanyArchetype.FINANCIAL, "Financial sector - use P/B and ROE framework"

    # Distressed: Negative profit margin or very low EBITDA margin
    if profit_margin < -0.10 or ebitda_margin < 0.02:
        if growth_y1 > 0.05:
            return CompanyArchetype.TURNAROUND, f"Negative margins ({profit_margin*100:.1f}%) but showing revenue growth ({growth_y1*100:.1f}%) - turnaround candidate"
        else:
            return CompanyArchetype.DISTRESSED, f"Negative/low margins ({profit_margin*100:.1f}%) with low growth - distressed company"

    # High CapEx intensive (utilities, telcos, semis in growth phase)
    if capex_pct > 0.25:
        return CompanyArchetype.HIGH_CAPEX, f"High CapEx ({capex_pct*100:.1f}% of revenue) - capital intensive business"

    # Hyper-growth unprofitable
    if growth_y1 > 0.30 and profit_margin < 0:
        return CompanyArchetype.HYPER_GROWTH, f"High growth ({growth_y1*100:.1f}%) with negative margins - hyper-growth phase"

    # Growth profitable
    if growth_y1 > 0.15 and profit_margin > 0.05:
        return CompanyArchetype.GROWTH, f"Strong growth ({growth_y1*100:.1f}%) with solid margins ({profit_margin*100:.1f}%) - growth company"

    # Cyclical (auto, industrials, materials with volatility)
    if sector in ['Consumer Cyclical', 'Industrials', 'Energy', 'Basic Materials']:
        if abs(profit_margin) > 0.15:  # High margin volatility
            return CompanyArchetype.CYCLICAL, f"Cyclical sector ({sector}) with volatile margins"

    # Stable growth (tech giants, healthcare)
    if growth_y1 > 0.08 and profit_margin > 0.15:
        return CompanyArchetype.STABLE_GROWTH, f"Moderate growth ({growth_y1*100:.1f}%) with strong margins ({profit_margin*100:.1f}%) - stable grower"

    # Mature/Value
    if growth_y1 < 0.08 and profit_margin > 0.10:
        return CompanyArchetype.MATURE, f"Low growth ({growth_y1*100:.1f}%) but profitable ({profit_margin*100:.1f}%) - mature/value"

    # Default to stable growth
    return CompanyArchetype.STABLE_GROWTH, "Default classification"


def get_archetype_assumptions(archetype: CompanyArchetype, company_data: Dict) -> Dict:
    """
    Get investment banking-grade assumptions based on company archetype

    This is how Goldman Sachs structures their models:
    - Different assumptions for different company types
    - Normalized metrics for cyclical/distressed
    - Industry-appropriate multiples
    """
    sector = company_data.get('sector', '')
    revenue = float(company_data.get('revenue', 0))
    ebitda = float(company_data.get('ebitda', 0))
    profit_margin = float(company_data.get('profit_margin', 0))
    capex_pct = float(company_data.get('capex_pct', 0))
    growth_y1 = float(company_data.get('growth_rate_y1', 0))

    assumptions = {
        'use_normalized_fcf': False,
        'normalized_ebitda_margin': None,
        'normalized_profit_margin': None,
        'normalized_capex_pct': None,
        'growth_decay_rate': 0.85,  # How fast growth declines
        'terminal_growth': 0.025,
        'terminal_margin_expansion': False,
        'min_fcf_margin': 0.05,  # Floor for FCF margin
        'valuation_method': 'dcf',  # dcf, ev_ebitda, or blended
        'explanation': ''
    }

    if archetype == CompanyArchetype.DISTRESSED:
        # For distressed companies (like Intel now), use normalized through-cycle metrics
        # This is standard Goldman Sachs approach for cyclical/distressed

        # Normalize to industry averages or historical peak
        if sector == 'Technology':
            assumptions['normalized_ebitda_margin'] = 0.25  # Tech average
            assumptions['normalized_profit_margin'] = 0.20
            assumptions['normalized_capex_pct'] = 0.12  # Normalized maintenance CapEx
        else:
            assumptions['normalized_ebitda_margin'] = 0.15
            assumptions['normalized_profit_margin'] = 0.10
            assumptions['normalized_capex_pct'] = 0.08

        assumptions['use_normalized_fcf'] = True
        assumptions['terminal_growth'] = 0.020  # Lower for distressed
        assumptions['valuation_method'] = 'ev_ebitda'  # Use multiples for distressed
        assumptions['explanation'] = "Using normalized through-cycle margins - company in distress phase. CapEx expected to normalize after transformation."

    elif archetype == CompanyArchetype.TURNAROUND:
        # Turnaround: Use improving margins
        if sector == 'Technology':
            assumptions['normalized_ebitda_margin'] = 0.20
            assumptions['normalized_profit_margin'] = 0.15
            assumptions['normalized_capex_pct'] = 0.10
        else:
            assumptions['normalized_ebitda_margin'] = 0.12
            assumptions['normalized_profit_margin'] = 0.08
            assumptions['normalized_capex_pct'] = 0.07

        assumptions['use_normalized_fcf'] = True
        assumptions['terminal_margin_expansion'] = True
        assumptions['terminal_growth'] = 0.025
        assumptions['explanation'] = "Turnaround scenario - margins expected to improve to industry norms"

    elif archetype == CompanyArchetype.HIGH_CAPEX:
        # Capital intensive: Use normalized steady-state CapEx
        assumptions['normalized_capex_pct'] = capex_pct * 0.60  # Assume current is peak investment
        assumptions['use_normalized_fcf'] = True
        assumptions['terminal_growth'] = 0.030  # Infrastructure companies can grow faster
        assumptions['explanation'] = f"High CapEx phase - normalizing to {assumptions['normalized_capex_pct']*100:.1f}% steady-state"

    elif archetype == CompanyArchetype.CYCLICAL:
        # Cyclical: Use through-cycle normalized metrics
        ebitda_margin = ebitda / revenue if revenue > 0 else 0
        assumptions['normalized_ebitda_margin'] = ebitda_margin  # Use current if reasonable
        assumptions['normalized_profit_margin'] = max(profit_margin, 0.08)  # Floor
        assumptions['use_normalized_fcf'] = True
        assumptions['terminal_growth'] = 0.020  # GDP-like
        assumptions['valuation_method'] = 'blended'  # DCF + multiples
        assumptions['explanation'] = "Cyclical company - using normalized through-cycle assumptions"

    elif archetype == CompanyArchetype.HYPER_GROWTH:
        # Hyper-growth: Focus on revenue multiples, not DCF
        assumptions['valuation_method'] = 'revenue_multiple'
        assumptions['terminal_growth'] = 0.040  # Can sustain above-GDP growth
        assumptions['growth_decay_rate'] = 0.90  # Slower decay
        assumptions['explanation'] = "Hyper-growth - using revenue multiples and forward assumptions"

    elif archetype == CompanyArchetype.GROWTH:
        # Growth companies: Standard DCF with higher terminal growth
        assumptions['terminal_growth'] = 0.035
        assumptions['growth_decay_rate'] = 0.88
        assumptions['explanation'] = "Growth company - standard DCF with above-GDP terminal growth"

    elif archetype == CompanyArchetype.STABLE_GROWTH:
        # Stable growers: Standard Goldman Sachs DCF
        assumptions['terminal_growth'] = 0.030
        assumptions['growth_decay_rate'] = 0.85
        assumptions['explanation'] = "Stable growth - standard DCF assumptions"

    elif archetype == CompanyArchetype.MATURE:
        # Mature: Lower growth, focus on FCF yield
        assumptions['terminal_growth'] = 0.020
        assumptions['growth_decay_rate'] = 0.80  # Faster decay
        assumptions['valuation_method'] = 'dcf'
        assumptions['explanation'] = "Mature company - conservative growth assumptions, focus on FCF"

    elif archetype == CompanyArchetype.FINANCIAL:
        # Financials: Different framework (not DCF-based)
        assumptions['valuation_method'] = 'pb_roe'  # Price to Book + ROE
        assumptions['explanation'] = "Financial company - use P/B and ROE framework"

    return assumptions


def apply_investment_banking_adjustments(company_data: Dict) -> Dict:
    """
    Main function: Classify company and apply appropriate IB-grade assumptions

    Returns adjusted company_data with normalized metrics where appropriate
    """
    # Classify company
    archetype, classification_reason = classify_company(company_data)

    logger.info(f"\n{'='*80}")
    logger.info(f"INVESTMENT BANKING FRAMEWORK - COMPANY CLASSIFICATION")
    logger.info(f"Company: {company_data.get('name', 'Unknown')}")
    logger.info(f"Archetype: {archetype.value.upper()}")
    logger.info(f"Reason: {classification_reason}")
    logger.info(f"{'='*80}\n")

    # Get appropriate assumptions
    assumptions = get_archetype_assumptions(archetype, company_data)

    # Create adjusted company data
    adjusted_data = company_data.copy()
    adjusted_data['archetype'] = archetype.value
    adjusted_data['archetype_explanation'] = classification_reason
    adjusted_data['valuation_assumptions'] = assumptions

    # Apply normalized metrics if applicable
    if assumptions['use_normalized_fcf']:
        revenue = float(company_data.get('revenue', 0))

        if assumptions['normalized_ebitda_margin']:
            adjusted_data['normalized_ebitda'] = revenue * assumptions['normalized_ebitda_margin']
            logger.info(f"Normalizing EBITDA: ${revenue * assumptions['normalized_ebitda_margin']:,.0f} "
                       f"({assumptions['normalized_ebitda_margin']*100:.1f}% margin)")

        if assumptions['normalized_profit_margin']:
            adjusted_data['normalized_profit_margin'] = assumptions['normalized_profit_margin']
            logger.info(f"Normalizing Profit Margin: {assumptions['normalized_profit_margin']*100:.1f}%")

        if assumptions['normalized_capex_pct']:
            adjusted_data['normalized_capex_pct'] = assumptions['normalized_capex_pct']
            logger.info(f"Normalizing CapEx: {assumptions['normalized_capex_pct']*100:.1f}% of revenue "
                       f"(current: {float(company_data.get('capex_pct', 0))*100:.1f}%)")

    # Adjust terminal growth
    adjusted_data['terminal_growth'] = assumptions['terminal_growth']

    # Adjust growth decay
    growth_y1 = float(company_data.get('growth_rate_y1', 0))
    decay_rate = assumptions['growth_decay_rate']
    adjusted_data['growth_rate_y2'] = growth_y1 * decay_rate
    adjusted_data['growth_rate_y3'] = growth_y1 * (decay_rate ** 2)

    logger.info(f"\nAdjusted Growth Schedule:")
    logger.info(f"  Year 1: {growth_y1*100:.1f}%")
    logger.info(f"  Year 2: {adjusted_data['growth_rate_y2']*100:.1f}%")
    logger.info(f"  Year 3: {adjusted_data['growth_rate_y3']*100:.1f}%")
    logger.info(f"  Terminal: {assumptions['terminal_growth']*100:.1f}%")
    logger.info(f"\nValuation Method: {assumptions['valuation_method'].upper()}")
    logger.info(f"Explanation: {assumptions['explanation']}\n")

    return adjusted_data


def get_industry_benchmark_multiples(sector: str, archetype: CompanyArchetype) -> Dict:
    """
    Get realistic trading multiples based on current market conditions
    Updated for 2024/2025 market environment
    """
    # Base multiples by sector (as of Dec 2024)
    sector_multiples = {
        'Technology': {
            'stable': {'ev_ebitda': 18.0, 'pe': 28.0, 'peg': 2.0},
            'growth': {'ev_ebitda': 22.0, 'pe': 35.0, 'peg': 1.8},
            'mature': {'ev_ebitda': 12.0, 'pe': 20.0, 'peg': 2.5}
        },
        'Healthcare': {
            'stable': {'ev_ebitda': 14.0, 'pe': 22.0, 'peg': 1.8},
            'growth': {'ev_ebitda': 18.0, 'pe': 30.0, 'peg': 1.5},
            'mature': {'ev_ebitda': 10.0, 'pe': 16.0, 'peg': 2.2}
        },
        'Consumer Cyclical': {
            'stable': {'ev_ebitda': 8.0, 'pe': 15.0, 'peg': 1.5},
            'growth': {'ev_ebitda': 12.0, 'pe': 22.0, 'peg': 1.3},
            'mature': {'ev_ebitda': 6.0, 'pe': 12.0, 'peg': 1.8}
        },
        'Consumer Defensive': {
            'stable': {'ev_ebitda': 12.0, 'pe': 20.0, 'peg': 2.0},
            'growth': {'ev_ebitda': 14.0, 'pe': 24.0, 'peg': 1.7},
            'mature': {'ev_ebitda': 10.0, 'pe': 18.0, 'peg': 2.3}
        },
        'Financial Services': {
            'stable': {'pb': 1.5, 'pe': 12.0},
            'growth': {'pb': 2.0, 'pe': 15.0},
            'mature': {'pb': 1.0, 'pe': 10.0}
        },
        'Energy': {
            'stable': {'ev_ebitda': 6.0, 'pe': 10.0, 'peg': 1.2},
            'growth': {'ev_ebitda': 7.0, 'pe': 12.0, 'peg': 1.0},
            'mature': {'ev_ebitda': 5.0, 'pe': 8.0, 'peg': 1.5}
        },
        'Industrials': {
            'stable': {'ev_ebitda': 10.0, 'pe': 18.0, 'peg': 1.6},
            'growth': {'ev_ebitda': 13.0, 'pe': 24.0, 'peg': 1.4},
            'mature': {'ev_ebitda': 8.0, 'pe': 14.0, 'peg': 1.9}
        },
    }

    # Determine stage based on archetype
    if archetype in [CompanyArchetype.GROWTH, CompanyArchetype.HYPER_GROWTH]:
        stage = 'growth'
    elif archetype in [CompanyArchetype.MATURE, CompanyArchetype.CYCLICAL]:
        stage = 'mature'
    else:
        stage = 'stable'

    sector_data = sector_multiples.get(sector, sector_multiples['Industrials'])
    return sector_data.get(stage, sector_data['stable'])
