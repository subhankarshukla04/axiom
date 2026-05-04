from valuation._config import TICKER_TAG_MAP, CYCLICAL_TAGS


def get_sub_sector_tag(ticker: str, sector: str, industry: str) -> str:
    t = ticker.upper()
    if t in TICKER_TAG_MAP:
        return TICKER_TAG_MAP[t]

    ind = industry.lower()
    s   = sector.lower()

    if 'investment bank' in ind or 'capital markets' in ind:
        return 'invest_bank'
    if 'bank' in ind or 'savings' in ind or 'thrift' in ind:
        return 'commercial_bank'
    if 'health' in ind and ('insurance' in ind or 'managed' in ind):
        return 'health_insurance'
    if 'reit' in ind or 'real estate investment' in ind:
        return 'reit'
    if 'real estate' in s:
        return 'reit'
    if 'telecom' in ind or 'wireless' in ind or 'telephone' in ind:
        return 'telecom_carrier'
    if 'semiconductor' in ind:
        return 'semi_equipment' if ('equipment' in ind or 'material' in ind) else 'fabless_semi'
    if any(x in ind for x in ('electric util', 'gas util', 'water util', 'multi-util')):
        return 'utility_regulated'
    if 'financial exchange' in ind or 'financial data' in ind:
        return 'exchange'
    if 'hotel' in ind or 'resort' in ind or 'lodging' in ind:
        return 'hotel_resort'
    if 'casino' in ind or 'gambling' in ind or 'gaming' in ind:
        return 'gaming'
    if 'packaging' in ind or 'container' in ind or 'paper' in ind:
        return 'packaging'
    if 'software' in ind and any(x in ind for x in ('application', 'saas', 'cloud')):
        return 'cloud_saas'
    if 'software' in ind:
        return 'cloud_software'
    if 'internet' in ind or 'interactive media' in ind or 'online' in ind:
        return 'digital_platform'
    if 'drug' in ind or 'pharmaceutical' in ind or 'biotechnology' in ind:
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

    return {
        'Technology':              'cloud_software',
        'Communication Services':  'digital_platform',
        'Consumer Cyclical':       'franchise_rest',
        'Consumer Defensive':      'consumer_staples',
        'Healthcare':              'pharma',
        'Industrials':             'industrial_cong',
        'Energy':                  'energy_ep',
        'Financial Services':      'commercial_bank',
        'Real Estate':             'reit',
        'Basic Materials':         'industrial_cong',
        'Utilities':               'utility_regulated',
    }.get(sector, 'industrial_cong')


def classify_company(data: dict) -> str:
    tag        = data.get('sub_sector_tag', '')
    g1         = data.get('growth_rate_y1', 0) or 0
    margin     = data.get('profit_margin', 0) or 0
    mktcap     = data.get('market_cap', data.get('market_cap_estimate', 0)) or 0
    beta       = data.get('beta', 1.0) or 1.0
    op_income  = data.get('operating_income', 0) or 0
    ebitda     = data.get('ebitda', 0) or 0
    forward_pe = data.get('forward_pe', 0) or 0

    if op_income < 0 and g1 <= 0:
        return 'DISTRESSED'
    if ebitda < 0:
        return 'DISTRESSED'

    if tag == 'story_auto' or (beta > 1.8 and forward_pe > 60):
        return 'STORY'
    if tag == 'growth_loss':
        return 'STORY'

    if g1 > 0.20 and margin > 0.08:
        return 'HYPERGROWTH'

    if g1 > 0.08 and margin > 0 and mktcap > 50e9:
        return 'GROWTH_TECH'

    if tag in CYCLICAL_TAGS and beta < 1.6:
        return 'CYCLICAL'

    if g1 < 0.04 and margin > 0:
        return 'STABLE_VALUE_LOWGROWTH'

    return 'STABLE_VALUE'
