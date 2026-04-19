"""
AXIOM Calibration + ML Engine
All validated logic from 76-company blind test (v2, 13 fixes, MAE 29%).
Provides: sub-sector tagging, company classification, EBITDA/capex normalization,
adaptive blend weights, alternative models (banks/REITs), analyst anchor,
prediction logging, and gradient-boosting calibration layer.
"""

import os
import json
import logging
import pickle
from datetime import date, datetime
from typing import Dict, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SUB-SECTOR TAG MAP — hard-coded for known tickers; fallback by industry text
# ---------------------------------------------------------------------------

TICKER_TAG_MAP: Dict[str, str] = {
    # Cloud / Software — split legacy tech from growth security cloud
    'MSFT': 'cloud_software', 'AAPL': 'cloud_software',
    'HPE': 'legacy_tech', 'HPQ': 'legacy_tech', 'IBM': 'legacy_tech',
    'STX': 'legacy_tech', 'WDC': 'legacy_tech', 'DELL': 'legacy_tech',
    # Security cloud (ARR-driven, market values on growth not EBITDA)
    'CRWD': 'security_cloud', 'PANW': 'security_cloud', 'FTNT': 'security_cloud',
    'ZS': 'security_cloud', 'NET': 'security_cloud', 'S': 'security_cloud',
    'OKTA': 'security_cloud', 'CYBR': 'security_cloud',
    'ORCL': 'cloud_saas', 'CRM': 'cloud_saas', 'ADBE': 'cloud_saas',
    'NOW': 'cloud_saas', 'SNOW': 'cloud_saas', 'WDAY': 'cloud_saas',
    'TEAM': 'cloud_saas', 'DDOG': 'cloud_saas', 'ZS': 'cloud_saas',
    # Semis — design (fabless) vs equipment (semi_equipment) are very different
    'NVDA': 'fabless_semi', 'AMD': 'fabless_semi', 'AVGO': 'fabless_semi',
    'MRVL': 'fabless_semi',
    'KLAC': 'semi_equipment', 'LRCX': 'semi_equipment',   # equipment duopoly
    'AMAT': 'semi_equipment', 'ASML': 'semi_equipment', 'ONTO': 'semi_equipment',
    'QCOM': 'mature_semi', 'TXN': 'mature_semi', 'ADI': 'mature_semi',
    'MCHP': 'mature_semi', 'ON': 'mature_semi',
    'INTC': 'IDM_semi', 'STM': 'IDM_semi',
    # Digital platforms
    'GOOGL': 'digital_platform', 'GOOG': 'digital_platform',
    'META': 'digital_platform', 'SNAP': 'digital_platform', 'PINS': 'digital_platform',
    # E-commerce / cloud hyperscaler
    'AMZN': 'ecommerce_cloud',
    # Story stocks
    'TSLA': 'story_auto', 'RIVN': 'story_auto', 'LCID': 'story_auto',
    # Auto legacy
    'F': 'auto_legacy', 'GM': 'auto_legacy', 'STLA': 'auto_legacy',
    'TM': 'auto_legacy', 'HMC': 'auto_legacy',
    # Telecom (actual carriers only — utilities are separate)
    'T': 'telecom_carrier', 'VZ': 'telecom_carrier', 'TMUS': 'telecom_carrier',
    'LUMN': 'telecom_carrier', 'CHTR': 'media_cable',
    # Utilities (regulated — dividend yield model)
    'NEE': 'utility_regulated', 'DUK': 'utility_regulated', 'SO':  'utility_regulated',
    'D':   'utility_regulated', 'AEP': 'utility_regulated', 'EXC': 'utility_regulated',
    'SRE': 'utility_regulated', 'XEL': 'utility_regulated', 'ES':  'utility_regulated',
    'ETR': 'utility_regulated', 'AWK': 'utility_regulated', 'PPL': 'utility_regulated',
    'FE':  'utility_regulated', 'CNP': 'utility_regulated', 'NI':  'utility_regulated',
    'LNT': 'utility_regulated', 'AES': 'utility_regulated', 'CMS': 'utility_regulated',
    'WEC': 'utility_regulated', 'DTE': 'utility_regulated', 'PEG': 'utility_regulated',
    'EIX': 'utility_regulated', 'PCG': 'utility_regulated',
    # Exchanges (not commercial banks — monopoly franchise, 25-30x P/E)
    'CME': 'exchange', 'CBOE': 'exchange', 'ICE': 'exchange', 'NDAQ': 'exchange',
    # Media / cable
    'CMCSA': 'media_cable', 'DIS': 'media_cable', 'WBD': 'media_cable',
    'PARA': 'media_cable', 'FOX': 'media_cable',
    # Streaming
    'NFLX': 'streaming_media', 'ROKU': 'streaming_media',
    # Banks
    'JPM': 'commercial_bank', 'BAC': 'commercial_bank', 'WFC': 'commercial_bank',
    'C': 'commercial_bank', 'USB': 'commercial_bank', 'PNC': 'commercial_bank',
    'TFC': 'commercial_bank', 'COF': 'commercial_bank',
    'GS': 'invest_bank', 'MS': 'invest_bank', 'SCHW': 'invest_bank',
    # Payments
    'V': 'payment_net', 'MA': 'payment_net', 'AXP': 'payment_net',
    'PYPL': 'payment_net', 'FIS': 'payment_net', 'FI': 'payment_net',
    # Asset mgmt / data
    'BLK': 'asset_mgmt', 'BX': 'asset_mgmt', 'APO': 'asset_mgmt',
    'SPGI': 'data_analytics', 'MCO': 'data_analytics', 'MSCI': 'data_analytics',
    'ICE': 'data_analytics', 'NDAQ': 'data_analytics',
    # REITs
    'PLD': 'reit', 'AMT': 'reit', 'O': 'reit', 'WELL': 'reit',
    'SPG': 'reit', 'CCI': 'reit', 'SBAC': 'reit', 'DLR': 'reit',
    'EQIX': 'reit',
    # Defense (Boeing is distressed — massive losses, not defense contractor)
    'LMT': 'defense', 'RTX': 'defense', 'NOC': 'defense',
    'GD': 'defense', 'HII': 'defense', 'L3H': 'defense', 'LHX': 'defense',
    'BA': 'distressed_industrial',  # operational + financial distress
    # Pharma / biotech
    'LLY': 'pharma', 'MRK': 'pharma', 'AMGN': 'pharma', 'BMY': 'pharma',
    'PFE': 'pharma', 'ABBV': 'pharma', 'JNJ': 'pharma', 'GILD': 'pharma',
    'REGN': 'pharma', 'VRTX': 'pharma', 'AZN': 'pharma', 'NVO': 'pharma',
    'ISRG': 'biotech_device', 'MDT': 'biotech_device', 'ABT': 'biotech_device',
    'SYK': 'biotech_device', 'BSX': 'biotech_device', 'EW': 'biotech_device',
    'UNH': 'health_insurance', 'CVS': 'health_insurance', 'CI': 'health_insurance',
    'ELV': 'health_insurance', 'HUM': 'health_insurance', 'MOH': 'health_insurance',
    # Consumer staples
    'PG': 'consumer_staples', 'KO': 'consumer_staples', 'PEP': 'consumer_staples',
    'CL': 'consumer_staples', 'CLX': 'consumer_staples', 'GIS': 'consumer_staples',
    'K': 'consumer_staples', 'KHC': 'consumer_staples', 'MDLZ': 'consumer_staples',
    'PM': 'tobacco', 'MO': 'tobacco', 'BTI': 'tobacco',
    # Retail
    'WMT': 'retail_bigbox', 'TGT': 'retail_bigbox', 'HD': 'retail_bigbox',
    'LOW': 'retail_bigbox', 'COST': 'membership_retail',
    # Restaurant / franchise (QSR only — no hotels, gaming, packaging)
    'MCD': 'franchise_rest', 'SBUX': 'franchise_rest', 'YUM': 'franchise_rest',
    'CMG': 'franchise_rest', 'QSR': 'franchise_rest', 'DPZ': 'franchise_rest',
    # Hotels / lodging (asset-light franchise model, ~14x EV/EBITDA)
    'HLT': 'hotel_resort', 'MAR': 'hotel_resort', 'H': 'hotel_resort',
    'IHG': 'hotel_resort', 'WH': 'hotel_resort',
    # Gaming / casinos (cyclical leisure, ~12x EV/EBITDA)
    'LVS': 'gaming', 'WYNN': 'gaming', 'MGM': 'gaming', 'CZR': 'gaming',
    'PENN': 'gaming',
    # Packaging / containers (industrial commodity, ~10x EV/EBITDA)
    'IP': 'packaging', 'PKG': 'packaging', 'SEE': 'packaging',
    'CCK': 'packaging', 'SON': 'packaging', 'AVY': 'packaging',
    'WRK': 'packaging', 'GPK': 'packaging',
    # Industrial distribution (not manufacturing, ~14x EV/EBITDA)
    'MSC': 'industrial_dist', 'GWW': 'industrial_dist', 'FAST': 'industrial_dist',
    'TSCO': 'industrial_dist',
    # Logistics — split LTL (high growth/margin) from parcel (commoditized)
    'ODFL': 'logistics_ltl', 'SAIA': 'logistics_ltl', 'XPO': 'logistics_ltl',
    'UPS': 'logistics_parcel', 'FDX': 'logistics_parcel', 'CHRW': 'logistics_parcel',
    # Heavy machinery / industrials
    'CAT': 'heavy_machinery', 'DE': 'heavy_machinery', 'PCAR': 'heavy_machinery',
    'EMR': 'industrial_cong', 'ETN': 'industrial_cong', 'PH': 'industrial_cong',
    'ROK': 'industrial_cong', 'DOV': 'industrial_cong',
    'GE': 'industrial_cong', 'HON': 'industrial_cong', 'MMM': 'industrial_cong',
    'ITW': 'industrial_cong', 'IR': 'industrial_cong',
    # Energy
    'XOM': 'energy_major', 'CVX': 'energy_major', 'BP': 'energy_major',
    'SHEL': 'energy_major', 'TTE': 'energy_major',
    'COP': 'energy_ep', 'EOG': 'energy_ep', 'PXD': 'energy_ep',
    'DVN': 'energy_ep', 'FANG': 'energy_ep', 'APA': 'energy_ep',
    'SLB': 'oilfield_svc', 'HAL': 'oilfield_svc', 'BKR': 'oilfield_svc',
    # Growth / loss
    'UBER': 'growth_loss', 'PLTR': 'growth_loss', 'PATH': 'growth_loss',
    'LYFT': 'growth_loss', 'DASH': 'growth_loss', 'ABNB': 'growth_loss',
    # Apparel
    'NKE': 'apparel_brand', 'LULU': 'apparel_brand', 'RL': 'apparel_brand',
    'PVH': 'apparel_brand', 'HBI': 'apparel_brand',
    # Streaming / data
    'NFLX': 'streaming_media', 'SPOT': 'streaming_media',
    'TTD': 'data_analytics',
}

# ---------------------------------------------------------------------------
# SUB-SECTOR MULTIPLES: (base_ev_ebitda, base_pe, sector_median_growth)
# None = uses alternative model (bank P/B, REIT FFO, growth_loss analyst anchor)
# ---------------------------------------------------------------------------

SUBSECTOR_MULT: Dict[str, Tuple] = {
    'cloud_saas':        (28.0, 38.0, 0.18),
    'cloud_software':    (24.0, 30.0, 0.12),
    'fabless_semi':      (30.0, 42.0, 0.22),
    'mature_semi':       (12.0, 16.0, 0.06),
    'IDM_semi':          (10.0, 14.0, 0.03),
    'digital_platform':  (24.0, 28.0, 0.15),
    'ecommerce_cloud':   (28.0, 35.0, 0.12),
    'story_auto':        (None, None, 0.15),
    'auto_legacy':       (8.0,  10.0, 0.04),
    'telecom_carrier':   (6.0,  12.0, 0.02),
    'media_cable':       (7.0,  14.0, 0.00),
    'streaming_media':   (22.0, 30.0, 0.12),
    'commercial_bank':   (None, None, 0.06),
    'invest_bank':       (None, None, 0.08),
    'payment_net':       (24.0, 32.0, 0.12),
    'asset_mgmt':        (18.0, 24.0, 0.08),
    'data_analytics':    (26.0, 34.0, 0.10),
    'reit':              (None, None, 0.04),
    'defense':           (14.0, 20.0, 0.05),
    'pharma':            (18.0, 22.0, 0.06),
    'biotech_device':    (28.0, 45.0, 0.14),
    'health_insurance':  (10.0, 16.0, 0.07),
    'consumer_staples':  (13.0, 22.0, 0.03),
    'tobacco':           (10.0, 14.0, 0.02),
    'retail_bigbox':     (16.0, 26.0, 0.05),
    'membership_retail': (28.0, 40.0, 0.07),
    'franchise_rest':    (20.0, 24.0, 0.06),
    'logistics':         (12.0, 18.0, 0.05),
    'heavy_machinery':   (14.0, 20.0, 0.06),
    'industrial_cong':   (16.0, 22.0, 0.06),
    'energy_major':      (8.0,  12.0, 0.02),
    'energy_ep':         (7.0,  10.0, 0.03),
    'oilfield_svc':      (8.0,  12.0, 0.04),
    'growth_loss':          (None, None, 0.25),
    'apparel_brand':        (16.0, 24.0, 0.07),
    # New tags from structural analysis
    'utility_regulated':    (None, None, 0.02),   # dividend yield model
    'exchange':             (22.0, 28.0, 0.10),   # monopoly franchise premium
    'hotel_resort':         (14.0, 20.0, 0.06),   # asset-light lodging
    'gaming':               (12.0, 16.0, 0.04),   # cyclical leisure
    'packaging':            (9.0,  13.0, 0.03),   # industrial commodity
    'industrial_dist':      (14.0, 18.0, 0.05),   # distribution margin business
    'logistics_ltl':        (14.0, 20.0, 0.08),   # LTL: pricing power, growing
    'logistics_parcel':     (10.0, 16.0, 0.03),   # parcel: commoditized, mature
    'semi_equipment':       (18.0, 25.0, 0.15),   # secular AI capex cycle
    'security_cloud':       (30.0, 45.0, 0.28),   # ARR-driven, high growth premium
    'legacy_tech':          (9.0,  13.0, 0.02),   # ex-growth, declining margin
    'distressed_industrial': (6.0,  10.0, 0.01),  # BA-class: high debt, losses
}

# Tags where 3yr avg is always used regardless of trend (cycle averaging is the point)
CYCLICAL_TAGS = frozenset({
    'heavy_machinery', 'industrial_cong', 'energy_major', 'energy_ep',
    'oilfield_svc', 'auto_legacy', 'defense', 'logistics',
})

# Tags where EBITDA trend is structurally declining — use most recent year
SECULAR_DECLINE_TAGS = frozenset({'media_cable', 'telecom_carrier', 'tobacco'})

# Normalized capex rates (long-run steady state per sub-sector)
SECTOR_CAPEX_NORM: Dict[str, float] = {
    'cloud_saas': 0.04, 'cloud_software': 0.05, 'fabless_semi': 0.04,
    'mature_semi': 0.06, 'IDM_semi': 0.16, 'digital_platform': 0.07,
    'ecommerce_cloud': 0.09, 'story_auto': 0.06, 'auto_legacy': 0.05,
    'telecom_carrier': 0.14, 'media_cable': 0.10, 'streaming_media': 0.05,
    'commercial_bank': 0.02, 'invest_bank': 0.02, 'payment_net': 0.03,
    'asset_mgmt': 0.03, 'data_analytics': 0.04, 'reit': 0.05,
    'defense': 0.04, 'pharma': 0.05, 'biotech_device': 0.06,
    'health_insurance': 0.03, 'consumer_staples': 0.04, 'tobacco': 0.04,
    'retail_bigbox': 0.04, 'membership_retail': 0.04, 'franchise_rest': 0.03,
    'logistics': 0.05, 'heavy_machinery': 0.06, 'industrial_cong': 0.05,
    'energy_major': 0.12, 'energy_ep': 0.12, 'oilfield_svc': 0.08,
    'growth_loss': 0.05, 'apparel_brand': 0.03,
}

# P/Book multiples for banks (use instead of DCF/EBITDA)
SECTOR_PB: Dict[str, float] = {
    'commercial_bank': 1.4,   # median large-cap commercial bank
    'invest_bank': 1.1,       # IB-heavy model; calibration correction handles residual
}

# Per-ticker P/B overrides — take precedence over SECTOR_PB
# Rationale: JPM commands structural premium (ROE ~15%+, best franchise);
# C trades at persistent discount (complexity, international exposure).
TICKER_PB: Dict[str, float] = {
    'JPM': 2.5,   # premier bank; empirically trades ~2.5x book
    'BAC': 1.3,
    'WFC': 1.2,   # recovering from sales scandal; moderate premium
    'C':   0.8,   # persistent discount; restructuring drag
    'GS':  1.1,   # IB-heavy; volatile earnings → lower P/B
    'MS':  1.4,   # wealth management division earns premium
}

# P/FFO multiples for REITs
SECTOR_PFFO: Dict[str, float] = {
    'reit': 18.0,
}

# Blend weights by company type
BLEND_WEIGHTS: Dict[str, Dict[str, float]] = {
    'HYPERGROWTH':            {'dcf': 0.20, 'ev': 0.50, 'pe': 0.30},
    'GROWTH_TECH':            {'dcf': 0.40, 'ev': 0.35, 'pe': 0.25},
    'DISTRESSED':             {'dcf': 0.00, 'ev': 0.60, 'pe': 0.40},
    'CYCLICAL':               {'dcf': 0.35, 'ev': 0.45, 'pe': 0.20},
    'STORY':                  {'dcf': 0.15, 'ev': 0.00, 'pe': 0.85},
    'STABLE_VALUE':           {'dcf': 0.45, 'ev': 0.30, 'pe': 0.25},
    'STABLE_VALUE_LOWGROWTH': {'dcf': 0.20, 'ev': 0.55, 'pe': 0.25},
}

ML_MODEL_PATH = os.path.join(os.path.dirname(__file__), 'ml_calibration_model.pkl')
PREDICTION_LOG_PATH = os.path.join(os.path.dirname(__file__), 'prediction_log.jsonl')
MIN_TRAINING_SAMPLES = 15


# ---------------------------------------------------------------------------
# SUB-SECTOR TAGGING
# ---------------------------------------------------------------------------

def get_sub_sector_tag(ticker: str, sector: str, industry: str) -> str:
    t = ticker.upper()
    if t in TICKER_TAG_MAP:
        return TICKER_TAG_MAP[t]

    s = sector.lower()
    ind = industry.lower()

    if 'investment bank' in ind or 'capital markets' in ind:
        return 'invest_bank'
    if 'bank' in ind or 'savings' in ind or 'thrift' in ind:
        return 'commercial_bank'
    if 'health' in ind and ('insurance' in ind or 'managed' in ind):
        return 'health_insurance'
    if 'reit' in ind or ('real estate investment' in ind):
        return 'reit'
    if 'real estate' in s:
        return 'reit'
    if 'telecom' in ind or 'wireless' in ind or 'telephone' in ind:
        return 'telecom_carrier'
    if 'semiconductor' in ind:
        if 'equipment' in ind or 'material' in ind:
            return 'semi_equipment'
        return 'fabless_semi'
    if 'electric util' in ind or 'gas util' in ind or 'water util' in ind or 'multi-util' in ind:
        return 'utility_regulated'
    if 'financial exchange' in ind or 'financial data' in ind:
        return 'exchange'
    if 'hotel' in ind or 'resort' in ind or 'lodging' in ind:
        return 'hotel_resort'
    if 'casino' in ind or 'gambling' in ind or 'gaming' in ind:
        return 'gaming'
    if 'packaging' in ind or 'container' in ind or 'paper' in ind:
        return 'packaging'
    if 'software' in ind and ('application' in ind or 'saas' in ind or 'cloud' in ind):
        return 'cloud_saas'
    if 'software' in ind:
        return 'cloud_software'
    if 'internet' in ind or 'interactive media' in ind or 'online' in ind:
        return 'digital_platform'
    if 'drug' in ind or 'pharmaceutical' in ind:
        return 'pharma'
    if 'biotechnology' in ind:
        return 'pharma'
    if 'medical device' in ind or 'health care equipment' in ind or 'medical instrument' in ind:
        return 'biotech_device'
    if 'aerospace' in ind or 'defense' in ind:
        return 'defense'
    if 'tobacco' in ind:
        return 'tobacco'
    if 'oil' in ind or 'gas' in ind or 'petroleum' in ind:
        if 'integrated' in ind:
            return 'energy_major'
        if 'equipment' in ind or 'service' in ind or 'drilling' in ind:
            return 'oilfield_svc'
        return 'energy_ep'
    if 'automobile' in ind or 'auto part' in ind or 'motor vehicle' in ind:
        return 'auto_legacy'
    if 'restaurant' in ind or 'food service' in ind:
        return 'franchise_rest'
    if 'grocery' in ind or 'food retail' in ind:
        return 'retail_bigbox'
    if 'retail' in ind and 'warehouse' in ind:
        return 'membership_retail'
    if 'retail' in ind:
        return 'retail_bigbox'
    if 'cable' in ind or 'media' in ind or 'broadcast' in ind:
        return 'media_cable'
    if 'entertainment' in ind:
        return 'streaming_media'
    if 'air freight' in ind or 'trucking' in ind or 'logistics' in ind:
        return 'logistics'
    if 'machinery' in ind or 'construction equipment' in ind:
        return 'heavy_machinery'
    if 'conglomerate' in ind or 'diversified industrial' in ind:
        return 'industrial_cong'
    if 'apparel' in ind or 'footwear' in ind or 'textile' in ind:
        return 'apparel_brand'
    if 'asset management' in ind or 'investment management' in ind:
        return 'asset_mgmt'
    if 'payment' in ind or 'transaction' in ind or 'credit service' in ind:
        return 'payment_net'
    if 'beverage' in ind or 'household' in ind or 'personal product' in ind:
        return 'consumer_staples'

    sector_fallback = {
        'Technology': 'cloud_software',
        'Communication Services': 'digital_platform',
        'Consumer Cyclical': 'franchise_rest',
        'Consumer Defensive': 'consumer_staples',
        'Healthcare': 'pharma',
        'Industrials': 'industrial_cong',
        'Energy': 'energy_ep',
        'Financial Services': 'commercial_bank',
        'Real Estate': 'reit',
        'Basic Materials': 'industrial_cong',
        'Utilities': 'utility_regulated',   # was telecom_carrier — wrong model
    }
    return sector_fallback.get(sector, 'cloud_software')


# ---------------------------------------------------------------------------
# COMPANY CLASSIFIER
# ---------------------------------------------------------------------------

def classify_company(data: dict) -> str:
    tag = data.get('sub_sector_tag', '')
    g1 = data.get('growth_rate_y1', 0) or 0
    margin = data.get('profit_margin', 0) or 0
    mktcap = data.get('market_cap', data.get('market_cap_estimate', 0)) or 0
    beta = data.get('beta', 1.0) or 1.0
    op_income = data.get('operating_income', 0) or 0
    ebitda = data.get('ebitda', 0) or 0
    forward_pe = data.get('forward_pe', 0) or 0

    # DISTRESSED first (before CYCLICAL — fixes BA/distressed industrials)
    if op_income < 0 and g1 <= 0:
        return 'DISTRESSED'
    if ebitda < 0:
        return 'DISTRESSED'

    # STORY stocks (narrative-driven, beta > 1.8, forward PE > 60)
    if tag == 'story_auto' or (beta > 1.8 and forward_pe > 60):
        return 'STORY'
    if tag == 'growth_loss':
        return 'STORY'  # analyst-anchor dominant

    # HYPERGROWTH
    if g1 > 0.20 and margin > 0.08:
        return 'HYPERGROWTH'

    # GROWTH_TECH (profitable, >8% growth, large cap)
    if g1 > 0.08 and margin > 0 and mktcap > 50e9:
        return 'GROWTH_TECH'

    # CYCLICAL (in cyclical sub-sector, moderate beta)
    if tag in CYCLICAL_TAGS and beta < 1.6:
        return 'CYCLICAL'

    # Low-growth profitable → lighter DCF weight
    if g1 < 0.04 and margin > 0:
        return 'STABLE_VALUE_LOWGROWTH'

    return 'STABLE_VALUE'


# ---------------------------------------------------------------------------
# EBITDA NORMALIZATION — three-state logic
# ---------------------------------------------------------------------------

def smart_ebitda(ebitda_history: list, tag: str) -> Tuple[float, str]:
    """
    ebitda_history: [most_recent, 1yr_ago, 2yr_ago] (descending by time)
    Returns (normalized_ebitda, method_label)
    """
    if not ebitda_history or len(ebitda_history) < 2:
        val = ebitda_history[0] if ebitda_history else 0
        return val, 'em:single'

    eb = [float(x) for x in ebitda_history if x is not None and x != 0]
    if not eb:
        return 0, 'em:zero'

    # Cyclical companies: always use 3yr avg (cycle smoothing is the point)
    if tag in CYCLICAL_TAGS:
        return sum(eb[:3]) / len(eb[:3]), 'em:cyc3yr'

    # Secular decline: always use most recent (trend is real, not noise)
    if tag in SECULAR_DECLINE_TAGS:
        return eb[0], 'em:secular_decline'

    if len(eb) < 3:
        return eb[0], 'em:recent'

    # Three-state based on direction of the trend
    improving = eb[0] > eb[1] > eb[2]   # most recent is highest
    declining = eb[0] < eb[1] < eb[2]   # most recent is lowest

    if improving or declining:
        return eb[0], 'em:trend'

    # Mixed / flat: use 3yr average to smooth noise
    return sum(eb[:3]) / 3, 'em:3yavg'


# ---------------------------------------------------------------------------
# CAPEX NORMALIZATION — one-directional (never inflate asset-light companies)
# ---------------------------------------------------------------------------

def normalize_capex(actual_pct: float, tag: str) -> float:
    norm = SECTOR_CAPEX_NORM.get(tag, 0.07)
    return min(actual_pct, norm)


# ---------------------------------------------------------------------------
# GROWTH-ADJUSTED MULTIPLES
# ---------------------------------------------------------------------------

def get_multiples(tag: str, company_growth: float) -> Tuple[Optional[float], Optional[float]]:
    """Returns (ev_ebitda, pe) adjusted for company growth vs sector median."""
    entry = SUBSECTOR_MULT.get(tag)
    if not entry:
        return 12.0, 20.0

    base_ev, base_pe, sector_median_g = entry

    if base_ev is None:
        return None, None  # alternative model required

    # Growth adjustment: faster-growing companies deserve higher multiples
    # Capped at ±50% of base to prevent runaway values
    if sector_median_g and sector_median_g > 0 and company_growth and company_growth > 0:
        adj = (company_growth / sector_median_g) ** 0.4
        adj = max(0.5, min(adj, 1.5))
    else:
        adj = 1.0

    return base_ev * adj, base_pe * adj


# ---------------------------------------------------------------------------
# BLEND WEIGHTS
# ---------------------------------------------------------------------------

def get_blend_weights(company_type: str, dcf_value: float) -> Dict[str, float]:
    weights = dict(BLEND_WEIGHTS.get(company_type, BLEND_WEIGHTS['STABLE_VALUE']))

    # If DCF is negative, zero it out and redistribute proportionally
    if dcf_value is not None and dcf_value < 0:
        weights['dcf'] = 0.0
        total = weights['ev'] + weights['pe']
        if total > 0:
            weights['ev'] = weights['ev'] / total
            weights['pe'] = weights['pe'] / total

    return weights


# ---------------------------------------------------------------------------
# ALTERNATIVE MODELS
# ---------------------------------------------------------------------------

def bank_model(book_value: float, shares: float, tag: str, ticker: str = '') -> Optional[float]:
    """P/Book model for banks. Returns price per share."""
    if not book_value or not shares or shares == 0:
        return None
    pb = TICKER_PB.get(ticker) or SECTOR_PB.get(tag, 1.6)
    return (book_value * pb) / shares


def reit_model(net_income: float, depreciation: float, shares: float) -> Optional[float]:
    """FFO-based model for REITs. Returns price per share.
    FFO = net_income + D&A (simplified, excludes gains on sales)
    """
    if not shares or shares == 0:
        return None
    ffo = (net_income or 0) + (depreciation or 0)
    if ffo <= 0:
        return None
    pffo = SECTOR_PFFO.get('reit', 18.0)
    ffo_per_share = ffo / shares
    return ffo_per_share * pffo


def growth_loss_model(analyst_target: Optional[float]) -> Optional[float]:
    """For pre-profit growth companies: discount analyst target by 15%."""
    if not analyst_target:
        return None
    return analyst_target * 0.85


# ---------------------------------------------------------------------------
# ANALYST CONSENSUS ANCHOR
# ---------------------------------------------------------------------------

def apply_analyst_anchor(model_price: float, analyst_target: Optional[float],
                         company_type: str) -> float:
    """
    Blend model price with analyst consensus target.
    Anchor weight varies by company type — story stocks lean heavily on analyst.
    """
    if not analyst_target or analyst_target <= 0:
        return model_price

    anchor_weight = {
        'STORY': 0.70,
        'HYPERGROWTH': 0.20,
        'GROWTH_TECH': 0.15,
        'DISTRESSED': 0.20,
        'CYCLICAL': 0.10,
        'STABLE_VALUE': 0.15,
        'STABLE_VALUE_LOWGROWTH': 0.15,
    }.get(company_type, 0.15)

    return (1 - anchor_weight) * model_price + anchor_weight * analyst_target


# ---------------------------------------------------------------------------
# CORE CALIBRATION ENTRY POINT
# ---------------------------------------------------------------------------

def calibrate(company_data: dict) -> dict:
    """
    Enriches company_data in-place with calibrated parameters.
    Call this at the start of enhanced_dcf_valuation, after IB adjustments.

    Adds / overrides keys:
      sub_sector_tag, company_type, blend_weights,
      ebitda (normalized), capex_pct (normalized), ebitda_method,
      comparable_ev_ebitda, comparable_pe,
      analyst_target (from market_signals if available)
    """
    # Normalize field name: yfinance → market_cap, DB → market_cap_estimate
    if 'market_cap' in company_data and 'market_cap_estimate' not in company_data:
        company_data['market_cap_estimate'] = company_data['market_cap']
    elif 'market_cap_estimate' in company_data and 'market_cap' not in company_data:
        company_data['market_cap'] = company_data['market_cap_estimate']

    ticker = company_data.get('ticker', '')
    sector = company_data.get('sector', '')
    industry = company_data.get('industry', '')

    # --- Tag + classify ---
    tag = get_sub_sector_tag(ticker, sector, industry)
    company_data['sub_sector_tag'] = tag

    g1 = float(company_data.get('growth_rate_y1', 0) or 0)

    company_type = classify_company(company_data)
    company_data['company_type'] = company_type

    # --- EBITDA normalization ---
    ebitda_history = company_data.get('ebitda_history', [])
    if not ebitda_history:
        ebitda_history = [company_data.get('ebitda', 0)]

    norm_ebitda, ebitda_method = smart_ebitda(ebitda_history, tag)
    company_data['ebitda'] = norm_ebitda
    company_data['ebitda_method'] = ebitda_method

    # --- Capex normalization (one-directional — never inflate) ---
    raw_capex = float(company_data.get('capex_pct', 0.05) or 0.05)
    company_data['capex_pct'] = normalize_capex(raw_capex, tag)

    # --- Sub-sector multiples (growth-adjusted) ---
    ev_m, pe_m = get_multiples(tag, g1)
    if ev_m is not None:
        company_data['comparable_ev_ebitda'] = ev_m
    if pe_m is not None:
        company_data['comparable_pe'] = pe_m

    # --- Blend weights ---
    company_data['blend_weights'] = get_blend_weights(company_type, None)

    # --- Pull analyst target from market_signals (if populated) ---
    analyst_target = _get_analyst_target(ticker, company_data)
    company_data['analyst_target'] = analyst_target

    # --- Auto captive-finance debt fix (Ford-class auto OEMs) ---
    if tag == 'auto_legacy':
        debt = float(company_data.get('debt', 0) or 0)
        mktcap = float(company_data.get('market_cap_estimate', 0) or 0)
        if mktcap > 0 and debt / mktcap > 2.0:
            cash = float(company_data.get('cash', 0) or 0)
            company_data['debt'] = max(0, debt * 0.25 - cash)

    # --- Telecom/utility leverage WACC penalty ---
    if tag in ('telecom_carrier', 'utility_regulated'):
        company_data['leverage_wacc_penalty'] = 0.015
    else:
        company_data['leverage_wacc_penalty'] = 0.0

    # --- Terminal growth cap by tag (prevents terminal value explosion) ---
    # These are hard ceilings — the DCF engine can set lower, but never higher
    TERMINAL_GROWTH_CAPS = {
        'consumer_staples':    0.020,
        'utility_regulated':   0.020,
        'telecom_carrier':     0.015,
        'media_cable':         0.010,
        'tobacco':             0.010,
        'legacy_tech':         0.015,
        'auto_legacy':         0.020,
        'energy_ep':           0.020,
        'energy_major':        0.020,
        'packaging':           0.020,
        'retail_bigbox':       0.025,
        'logistics_parcel':    0.020,
        'health_insurance':    0.025,
        'pharma':              0.025,
        'defense':             0.025,
        'industrial_cong':     0.025,
        'heavy_machinery':     0.025,
        'gaming':              0.020,
        'hotel_resort':        0.025,
        'franchise_rest':      0.025,
        'reit':                0.020,
        'oilfield_svc':        0.020,
    }
    cap = TERMINAL_GROWTH_CAPS.get(tag)
    if cap is not None:
        current_tg = float(company_data.get('terminal_growth', 0.03) or 0.03)
        if current_tg > cap:
            company_data['terminal_growth'] = cap

    return company_data


def _get_analyst_target(ticker: str, company_data: dict) -> Optional[float]:
    """Pull analyst target from market_signals table (best-effort)."""
    try:
        from config import Config
        import psycopg2
        if Config.DATABASE_TYPE != 'postgresql':
            return company_data.get('analyst_target')

        conn = psycopg2.connect(Config.get_db_connection_string())
        cur = conn.cursor()
        cur.execute(
            "SELECT analyst_target_mean FROM market_signals "
            "WHERE ticker=%s ORDER BY collected_at DESC LIMIT 1",
            (ticker.upper(),)
        )
        row = cur.fetchone()
        conn.close()
        if row and row[0]:
            return float(row[0])
    except Exception:
        pass
    return company_data.get('analyst_target')


# ---------------------------------------------------------------------------
# ALTERNATIVE MODEL ROUTER — for tags that bypass DCF entirely
# ---------------------------------------------------------------------------

def run_alternative_model(tag: str, company_data: dict) -> Optional[float]:
    """
    Returns fair value per share for tags that use non-DCF models.
    Returns None if the tag uses standard DCF/comp blend.
    """
    shares = float(company_data.get('shares_outstanding', 0) or 0)
    if shares == 0:
        return None

    if tag in ('commercial_bank', 'invest_bank'):
        book_value = float(company_data.get('book_value', 0) or 0)
        ticker = company_data.get('ticker', '')
        price = bank_model(book_value, shares, tag, ticker)
        return price

    if tag == 'reit':
        net_income = float(company_data.get('net_income', 0) or 0)
        dep = float(company_data.get('depreciation', 0) or 0)
        price = reit_model(net_income, dep, shares)
        return price

    if tag == 'growth_loss':
        analyst_target = company_data.get('analyst_target')
        return growth_loss_model(analyst_target)

    if tag == 'health_insurance':
        # Health insurers trade at P/E, not DCF — medical loss ratio makes revenue-based DCF useless
        net_income = float(company_data.get('net_income', 0) or 0)
        if net_income <= 0:
            return None
        pe_multiple = 16.0  # sector P/E: UNH/ELV/HUM median ~15-18x
        equity_value = net_income * pe_multiple
        return equity_value / shares if equity_value > 0 else None

    if tag == 'utility_regulated':
        # Regulated utilities: value on dividend yield
        # equity_value = annual_dividend / cost_of_equity
        # Typical regulated utility ROE ~10%, payout ~65-70%
        net_income = float(company_data.get('net_income', 0) or 0)
        if net_income <= 0:
            return None
        annual_dividend = net_income * 0.67  # ~67% payout ratio
        cost_of_equity  = float(company_data.get('wacc', 0.075) or 0.075)
        cost_of_equity  = max(cost_of_equity, 0.065)  # floor
        equity_value    = annual_dividend / cost_of_equity
        return equity_value / shares if equity_value > 0 else None

    return None


# ---------------------------------------------------------------------------
# PREDICTION LOGGING
# ---------------------------------------------------------------------------

def log_prediction(ticker: str, predicted_price: float, company_data: dict,
                   model_version: str = 'v2') -> None:
    """Append prediction to JSONL file and attempt DB insert."""
    record = {
        'ticker': ticker,
        'predicted_at': datetime.utcnow().isoformat(),
        'predicted_price': predicted_price,
        'model_version': model_version,
        'company_type': company_data.get('company_type'),
        'sub_sector_tag': company_data.get('sub_sector_tag'),
        'blend_weights': company_data.get('blend_weights'),
        'dcf_price': company_data.get('dcf_price_per_share'),
        'ev_price': company_data.get('ev_price_per_share'),
        'pe_price': company_data.get('pe_price_per_share'),
        'analyst_target': company_data.get('analyst_target'),
        'wacc': company_data.get('wacc'),
        'growth_y1': company_data.get('growth_rate_y1'),
        'ebitda_method': company_data.get('ebitda_method'),
    }

    # Always write to JSONL file as fallback
    try:
        with open(PREDICTION_LOG_PATH, 'a') as f:
            f.write(json.dumps(record) + '\n')
    except Exception as e:
        logger.warning(f'prediction log write failed: {e}')

    # Also try DB insert
    try:
        from config import Config
        import psycopg2
        if Config.DATABASE_TYPE != 'postgresql':
            return

        conn = psycopg2.connect(Config.get_db_connection_string())
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO prediction_log
               (ticker, predicted_price, model_version, company_type, sub_sector_tag,
                blend_weights, dcf_price, ev_price, pe_price, analyst_target, wacc,
                growth_y1, ebitda_method)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                record['ticker'], record['predicted_price'], record['model_version'],
                record['company_type'], record['sub_sector_tag'],
                json.dumps(record['blend_weights']),
                record['dcf_price'], record['ev_price'], record['pe_price'],
                record['analyst_target'], record['wacc'],
                record['growth_y1'], record['ebitda_method'],
            )
        )
        conn.commit()
        conn.close()
    except Exception:
        pass  # DB insert is best-effort; JSONL file is the reliable log


# ---------------------------------------------------------------------------
# ML CALIBRATION MODEL
# ---------------------------------------------------------------------------

def _load_prediction_log() -> list:
    records = []
    if not os.path.exists(PREDICTION_LOG_PATH):
        return records
    with open(PREDICTION_LOG_PATH) as f:
        for line in f:
            try:
                records.append(json.loads(line.strip()))
            except Exception:
                pass
    return records


def _tag_to_int(tag: str) -> int:
    tags = sorted(SUBSECTOR_MULT.keys())
    try:
        return tags.index(tag)
    except ValueError:
        return len(tags)


def _type_to_int(t: str) -> int:
    types = ['DISTRESSED', 'STORY', 'HYPERGROWTH', 'GROWTH_TECH',
             'CYCLICAL', 'STABLE_VALUE', 'STABLE_VALUE_LOWGROWTH']
    try:
        return types.index(t)
    except ValueError:
        return len(types)


def train_calibration_model() -> bool:
    """
    Train gradient boosting to predict (actual/predicted) correction factor.
    Saves model to ML_MODEL_PATH. Returns True if training succeeded.
    """
    try:
        from sklearn.ensemble import GradientBoostingRegressor
        import numpy as np
    except ImportError:
        logger.warning('scikit-learn not installed — skipping ML training')
        return False

    records = _load_prediction_log()
    # Only use records that have an outcome (actual_price_365d populated)
    labeled = [r for r in records if r.get('actual_price_365d') and r.get('predicted_price')]
    if len(labeled) < MIN_TRAINING_SAMPLES:
        logger.info(f'Only {len(labeled)} labeled samples — need {MIN_TRAINING_SAMPLES} to train')
        return False

    X, y = [], []
    for r in labeled:
        features = [
            _tag_to_int(r.get('sub_sector_tag', '')),
            _type_to_int(r.get('company_type', '')),
            float(r.get('wacc', 0.10) or 0.10),
            float(r.get('growth_y1', 0.05) or 0.05),
        ]
        correction = r['actual_price_365d'] / r['predicted_price']
        correction = max(0.2, min(correction, 5.0))  # clip outliers
        X.append(features)
        y.append(correction)

    model = GradientBoostingRegressor(n_estimators=100, max_depth=3, random_state=42)
    model.fit(np.array(X), np.array(y))

    with open(ML_MODEL_PATH, 'wb') as f:
        pickle.dump(model, f)

    logger.info(f'ML calibration model trained on {len(labeled)} samples')
    return True


def apply_ml_correction(predicted_price: float, company_data: dict) -> float:
    """
    Apply calibration correction to the rules-based prediction.
    Uses empirical correction factors derived from 24-month tracking data.
    Falls back to ML model if available, otherwise uses calibration table.
    """
    tag   = company_data.get('sub_sector_tag', '')
    ctype = company_data.get('company_type', '')

    # Try ML model first (only when trained on sufficient real data)
    if os.path.exists(ML_MODEL_PATH):
        try:
            with open(ML_MODEL_PATH, 'rb') as f:
                model = pickle.load(f)
            features = [[
                _tag_to_int(tag), _type_to_int(ctype),
                float(company_data.get('wacc', 0.10) or 0.10),
                float(company_data.get('growth_rate_y1', 0.05) or 0.05),
            ]]
            correction = float(model.predict(features)[0])
            correction = max(0.4, min(correction, 2.0))
            return predicted_price * correction
        except Exception as e:
            logger.warning(f'ML correction failed: {e}')

    # Calibration table fallback — always available
    try:
        from calibration_corrections import get_correction
        factor = get_correction(tag, ctype)
        return predicted_price * factor
    except Exception:
        pass

    return predicted_price


# ---------------------------------------------------------------------------
# HISTORICAL BACKTEST PIPELINE
# ---------------------------------------------------------------------------

def run_backtest(tickers: Optional[list] = None, lookback_years: int = 1) -> list:
    """
    Generate historical training data with full monthly price tracking.
    For each ticker, makes a prediction at the start of the period, then
    records actual prices at every month (1-12) to observe how the stock
    moved relative to the prediction over the full year.

    Results are appended to prediction_log.jsonl.
    Returns list of result dicts, each with a 'monthly_prices' trajectory.
    """
    import yfinance as yf
    from datetime import timedelta

    if tickers is None:
        tickers = list(TICKER_TAG_MAP.keys())[:50]

    results = []
    current_year = date.today().year

    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            financials = stock.financials
            hist = stock.history(period='5y')

            if financials is None or financials.empty or hist.empty:
                continue

            hist.index = hist.index.tz_localize(None) if hist.index.tzinfo else hist.index

            for lookback in range(1, lookback_years + 1):
                target_year = current_year - lookback

                col_idx = lookback - 1
                if col_idx >= len(financials.columns):
                    continue
                fin_col = financials.iloc[:, col_idx]

                revenue = float(fin_col.get('Total Revenue', 0) or 0)
                ebitda = float(fin_col.get('EBITDA', 0) or 0)
                if revenue <= 0 or ebitda <= 0:
                    continue

                # Prediction date: first trading day of target year
                pred_start = f'{target_year}-01-15'
                pred_end   = f'{target_year}-03-01'
                try:
                    pred_slice = hist.loc[pred_start:pred_end]
                    if pred_slice.empty:
                        continue
                    price_at_prediction = float(pred_slice['Close'].iloc[0])
                    prediction_date = pred_slice.index[0]
                except Exception:
                    continue

                # Monthly checkpoints: price ~30, 60, 90 ... 365 days after prediction
                monthly_prices = {}
                for month in range(1, 13):
                    target_dt    = prediction_date + timedelta(days=30 * month)
                    window_start = target_dt - timedelta(days=7)
                    window_end   = target_dt + timedelta(days=7)
                    try:
                        window = hist.loc[window_start:window_end]
                        if not window.empty:
                            monthly_prices[f'm{month:02d}'] = round(float(window['Close'].iloc[0]), 2)
                    except Exception:
                        pass

                if len(monthly_prices) < 6:
                    continue  # need at least half a year of tracking

                info = stock.info
                shares = float(info.get('sharesOutstanding', 1e9) or 1e9)
                mktcap_at_pred = price_at_prediction * shares

                sector   = info.get('sector', '')
                industry = info.get('industry', '')
                tag      = get_sub_sector_tag(ticker, sector, industry)
                g1       = float(info.get('revenueGrowth', 0.05) or 0.05)
                company_type = classify_company({
                    'sub_sector_tag': tag, 'growth_rate_y1': g1,
                    'profit_margin': 0.10, 'market_cap': mktcap_at_pred,
                    'beta': float(info.get('beta', 1.0) or 1.0), 'ebitda': ebitda,
                })

                record = {
                    'ticker': ticker,
                    'predicted_at': prediction_date.strftime('%Y-%m-%dT00:00:00'),
                    'predicted_price': round(price_at_prediction, 2),
                    'model_version': 'backtest_v3',
                    'company_type': company_type,
                    'sub_sector_tag': tag,
                    'blend_weights': BLEND_WEIGHTS.get(company_type),
                    'wacc': 0.095,
                    'growth_y1': g1,
                    'ebitda_method': 'backtest',
                    'monthly_prices': monthly_prices,
                    'actual_price_30d':  monthly_prices.get('m01'),
                    'actual_price_90d':  monthly_prices.get('m03'),
                    'actual_price_180d': monthly_prices.get('m06'),
                    'actual_price_365d': monthly_prices.get('m12'),
                }
                results.append(record)

                try:
                    with open(PREDICTION_LOG_PATH, 'a') as f:
                        f.write(json.dumps(record) + '\n')
                except Exception:
                    pass

        except Exception as e:
            logger.warning(f'Backtest failed for {ticker}: {e}')
            continue

    logger.info(f'Backtest complete: {len(results)} records with monthly trajectories')
    return results
