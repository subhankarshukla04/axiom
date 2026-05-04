"""
Framework router — detects companies where a standard FCF-based DCF is
structurally wrong and flags them so the ML calibration pipeline skips them.

Currently flags:
- REITs          → valued on FFO yield, not free cash flow
- Banks/insurers → valued on P/Book / ROE, EBITDA is near-zero by design
- Neg-FCF growth → prices future state the current DCF cannot see

Flagged companies fall back to the existing valuation without ML overrides.
This prevents the calibration from making a structurally-correct-but-wrong
prediction worse.
"""

# Sub-sector tags that identify REIT structures
REIT_TAGS = frozenset({
    'reit_office', 'reit_retail', 'reit_industrial', 'reit_residential',
    'reit_healthcare', 'reit_data_center', 'reit_diversified',
    'tower_reit', 'net_lease_reit',
})

# Sub-sector tags that identify bank/insurance structures
BANK_TAGS = frozenset({
    'money_center_bank', 'regional_bank', 'insurance_life',
    'insurance_pc', 'insurance_div', 'investment_bank',
    'asset_manager', 'consumer_finance',
})


def classify_framework(company_data: dict,
                        stored_result: dict = None) -> dict:
    """
    Assess whether the DCF framework is appropriate for this company.

    Returns:
        {
          'suitable': bool,     # True = DCF is the right tool
          'reason':   str,      # why it's unsuitable (or 'standard')
          'skip_ml':  bool,     # whether to skip ML calibration
        }
    """
    tag    = str(company_data.get('sub_sector_tag') or '').lower()
    ebitda = float(company_data.get('ebitda') or 0)
    rev    = float(company_data.get('revenue') or 1)
    g1     = float(company_data.get('growth_rate_y1') or 0)

    # REIT check
    if tag in REIT_TAGS or 'reit' in tag:
        return {'suitable': False,
                'reason':   'REIT — FFO yield model required',
                'skip_ml':  True}

    # Bank / insurer check
    if tag in BANK_TAGS:
        return {'suitable': False,
                'reason':   'Bank/insurer — P/Book model required',
                'skip_ml':  True}

    # Negative-FCF hyper-growth: EBITDA margin < -5% AND revenue growing >20%
    ebitda_margin = ebitda / max(rev, 1)
    if ebitda_margin < -0.05 and g1 > 0.20:
        return {'suitable': False,
                'reason':   'Negative-FCF growth — pricing future state',
                'skip_ml':  True}

    # Already well-calibrated: if stored DCF is within 15% of analyst, leave it alone
    if stored_result:
        stored_dcf = float(stored_result.get('dcf_price_per_share') or 0)
        analyst    = float(stored_result.get('analyst_target') or 0)
        market     = float(stored_result.get('current_price') or 0)
        if analyst > 0 and stored_dcf > 0 and market > 0:
            err = abs(stored_dcf - analyst) / analyst
            if err < 0.15:
                return {'suitable': True,
                        'reason':   'already_calibrated',
                        'skip_ml':  True}

    return {'suitable': True, 'reason': 'standard', 'skip_ml': False}
