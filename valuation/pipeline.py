from valuation._config import TERMINAL_GROWTH_BY_TAG, TERMINAL_GROWTH_DEFAULT
from valuation.tagging import get_sub_sector_tag, classify_company
from valuation.normalizers import smart_ebitda, normalize_capex, get_multiples, get_blend_weights
# TODO Phase 2: extract _get_analyst_target into valuation/ — heuristic should not depend on ml/
from ml.log import _get_analyst_target


def calibrate(company_data: dict) -> dict:
    if 'market_cap' in company_data and 'market_cap_estimate' not in company_data:
        company_data['market_cap_estimate'] = company_data['market_cap']
    elif 'market_cap_estimate' in company_data and 'market_cap' not in company_data:
        company_data['market_cap'] = company_data['market_cap_estimate']

    ticker   = company_data.get('ticker', '')
    sector   = company_data.get('sector', '')
    industry = company_data.get('industry', '')

    tag = get_sub_sector_tag(ticker, sector, industry)
    company_data['sub_sector_tag'] = tag

    g1 = float(company_data.get('growth_rate_y1', 0) or 0)

    company_type = classify_company(company_data)
    company_data['company_type'] = company_type

    ebitda_history = company_data.get('ebitda_history') or [company_data.get('ebitda', 0)]
    norm_ebitda, ebitda_method = smart_ebitda(ebitda_history, tag)
    company_data['ebitda']        = norm_ebitda
    company_data['ebitda_method'] = ebitda_method

    raw_capex = float(company_data.get('capex_pct', 0.05) or 0.05)
    company_data['raw_capex_pct'] = raw_capex
    company_data['capex_pct'] = normalize_capex(raw_capex, tag)

    ev_m, pe_m = get_multiples(tag, g1, ticker=ticker)
    if ev_m is not None:
        company_data['comparable_ev_ebitda'] = ev_m
    if pe_m is not None:
        company_data['comparable_pe'] = pe_m

    company_data['blend_weights'] = get_blend_weights(company_type, None)

    analyst_target = _get_analyst_target(ticker, company_data)
    company_data['analyst_target'] = analyst_target

    # Auto captive-finance debt fix for heavily-leveraged auto OEMs
    if tag == 'auto_legacy':
        debt   = float(company_data.get('debt', 0) or 0)
        mktcap = float(company_data.get('market_cap_estimate', 0) or 0)
        if mktcap > 0 and debt / mktcap > 2.0:
            cash = float(company_data.get('cash', 0) or 0)
            company_data['debt'] = max(0, debt * 0.25 - cash)

    # Airline fleet-lease debt fix — only for heavily leveraged carriers
    if tag == 'airline':
        debt    = float(company_data.get('debt', 0) or 0)
        revenue = float(company_data.get('revenue', 0) or 0)
        if revenue > 0 and debt / revenue > 0.65:
            company_data['debt'] = debt * 0.35
        g1 = float(company_data.get('growth_rate_y1', 0) or 0)
        if g1 > 0.06:
            company_data['growth_rate_y1'] = 0.06
            company_data['growth_rate_y2'] = 0.05
            company_data['growth_rate_y3'] = 0.04

    # Non-USD reporting currency: force 85% analyst anchor weight
    fin_currency = company_data.get('financial_currency', 'USD')
    if fin_currency and fin_currency != 'USD':
        company_data['_non_usd_reporting']    = True
        company_data['_forced_anchor_weight'] = 0.85
    else:
        company_data['_non_usd_reporting'] = False

    # Telecom/utility WACC penalty for leverage
    company_data['leverage_wacc_penalty'] = (
        0.015 if tag in ('telecom_carrier', 'utility_regulated') else 0.0
    )

    # Sector-specific terminal growth + converging Y2/Y3 path
    terminal = TERMINAL_GROWTH_BY_TAG.get(tag, TERMINAL_GROWTH_DEFAULT)
    company_data['terminal_growth'] = terminal

    if tag != 'airline':
        y1 = float(company_data.get('growth_rate_y1', 0.05) or 0.05)
        company_data['growth_rate_y2'] = round(y1 * 0.67 + terminal * 0.33, 4)
        company_data['growth_rate_y3'] = round(y1 * 0.33 + terminal * 0.67, 4)

    return company_data
