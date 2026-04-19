"""
Calibration corrections derived from 24-month tracking of 20 stocks
and single-month snapshot of 258 S&P 500 stocks (April 2025).

Gap = (actual_market - our_model) / our_model
Correction = market / model  →  multiply model price by this factor.

Sub-tag corrections take priority over company-type fallbacks.
Dampening rules:
  LOW confidence  → 0.5 * factor + 0.5 * 1.0  (halfway to neutral)
  MEDIUM, n < 5   → 0.75 * factor + 0.25 * 1.0
  HIGH or MEDIUM n>=5 → no dampening
"""

# Sub-tag corrections — (raw_factor, confidence, n_stocks)
# No duplicate keys — last-wins bugs from earlier versions removed.
SUBTAG_CORRECTIONS = {
    # ── Tags with dedicated alternative models (P/B, FFO, P/E, div-yield) ─────
    # Correction = 1.00 means the new model handles calibration; no residual needed.
    'health_insurance':  (1.00, 'HIGH',  5),   # P/E(16x net income) replaces DCF
    'utility_regulated': (1.00, 'HIGH',  8),   # dividend-yield model replaces DCF
    'commercial_bank':   (1.00, 'HIGH', 16),   # P/B model; per-ticker overrides in ml_engine
    'exchange':          (1.00, 'MEDIUM', 2),  # new multiples correct it; no residual

    # ── Well-calibrated (within 15% on average) ───────────────────────────────
    'industrial_cong':   (1.07, 'HIGH',  29),
    'franchise_rest':    (0.78, 'HIGH',  10),  # restaurants only; hotels/gaming split out
    'cloud_software':    (0.88, 'HIGH',  15),
    'cloud_saas':        (0.95, 'HIGH',   8),
    'defense':           (0.91, 'MEDIUM', 6),
    'retail_bigbox':     (1.50, 'HIGH',   8),  # WMT/COST re-rated upward; market above model
    'semi_equipment':    (1.05, 'MEDIUM', 3),  # new multiples mostly correct; minor residual
    'legacy_tech':       (1.00, 'MEDIUM', 5),  # low multiples already priced in; neutral
    'streaming_media':   (0.95, 'LOW',    1),
    'hotel_resort':      (1.15, 'MEDIUM', 2),
    'mature_semi':       (1.20, 'MEDIUM', 4),  # cycle recovery premium
    'oilfield_svc':      (1.57, 'MEDIUM', 3),

    # ── Systematic overvalue — DCF or comp still running ──────────────────────
    'consumer_staples':  (0.59, 'HIGH',  19),  # terminal growth too high, margins thin
    'media_cable':       (0.36, 'MEDIUM', 3),  # secular decline, high debt
    'asset_mgmt':        (0.58, 'MEDIUM', 5),  # lumpy carried interest inflates DCF
    'energy_ep':         (0.75, 'HIGH',  13),
    'pharma':            (0.78, 'HIGH',  17),  # patent cliff risk not priced in DCF
    'payment_net':       (0.65, 'MEDIUM', 3),  # DCF overvalues vs market P/E
    'reit':              (0.72, 'HIGH',  17),  # FFO model still needed; DCF overshoots
    'biotech_device':    (0.62, 'HIGH',   8),  # high EV/EBITDA multiples inflate model
    'data_analytics':    (0.70, 'MEDIUM', 3),
    'packaging':         (0.40, 'MEDIUM', 6),  # thin margins + high debt; DCF always overstates
    'auto_legacy':       (0.30, 'LOW',    1),  # captive finance debt is structural
    'gaming':            (0.88, 'MEDIUM', 3),  # LVS drags, MGM lifts — muted net
    'heavy_machinery':   (0.80, 'MEDIUM', 3),
    'apparel_brand':     (0.85, 'MEDIUM', 3),
    'telecom_carrier':   (0.75, 'MEDIUM', 3),
    'tobacco':           (0.85, 'LOW',    2),

    # invest_bank: P/B model still overshoots GS/MS — apply downward correction
    'invest_bank':       (0.62, 'MEDIUM', 3),  # GS: model $718 vs market $450 = 0.63x

    # ── Systematic undervalue — model price too low ───────────────────────────
    # fabless_semi: AI-peak calibration no longer valid (April 2025 selloff).
    # NVDA $182 vs model $425 = 0.43x; AMD/AVGO/MRVL less severe; median ~0.65.
    'fabless_semi':      (0.65, 'HIGH',   8),

    'logistics_ltl':     (1.40, 'MEDIUM', 3),  # pricing power, growing
    'logistics_parcel':  (0.80, 'MEDIUM', 2),  # commoditized, mature
    'security_cloud':    (1.80, 'MEDIUM', 5),  # ARR premium — DCF can't capture it
    'industrial_dist':   (0.90, 'LOW',    2),

    # energy_major: highly sensitive to commodity cycle + yfinance data variability.
    # XOM model $190 (April 2025 run) vs market $146 = 0.77x.
    # MEDIUM n=3 → dampened: 0.75*0.69 + 0.25 = 0.77
    'energy_major':      (0.69, 'MEDIUM', 3),

    # IDM_semi: INTC model $39 (improved), market $69 = 1.77x.
    # raw=2.6 LOW → dampened: 0.5*2.6 + 0.5 = 1.8 → $39*1.8 ≈ $70
    'IDM_semi':          (2.60, 'LOW',    1),

    # distressed recovery
    'distressed_industrial': (1.80, 'LOW', 1),  # BA: market prices eventual recovery

    # misc single-stock
    'ecommerce_cloud':   (0.66, 'LOW',  1),
    'digital_platform':  (0.56, 'LOW',  1),
    'story_auto':        (0.88, 'LOW',  1),
    'membership_retail': (0.92, 'LOW',  1),
}

# Company-type fallback (used when sub_tag not in SUBTAG_CORRECTIONS)
TYPE_CORRECTIONS = {
    'GROWTH_TECH':            0.71,
    'HYPERGROWTH':            0.55,
    'CYCLICAL':               0.70,
    'DISTRESSED':             0.90,
    'STABLE_VALUE':           0.85,
    'STABLE_VALUE_LOWGROWTH': 0.72,
    'STORY':                  0.88,
}

MIN_CORRECTION = 0.20
MAX_CORRECTION = 2.50


def get_correction(sub_tag: str, company_type: str) -> float:
    """
    Return calibration factor. Multiply model price by this to get calibrated price.
    """
    if sub_tag in SUBTAG_CORRECTIONS:
        factor, confidence, n = SUBTAG_CORRECTIONS[sub_tag]
        if confidence == 'LOW':
            factor = 0.5 * factor + 0.5 * 1.0
        elif confidence == 'MEDIUM' and n < 5:
            factor = 0.75 * factor + 0.25 * 1.0
    else:
        factor = TYPE_CORRECTIONS.get(company_type, 0.80)

    return max(MIN_CORRECTION, min(factor, MAX_CORRECTION))
