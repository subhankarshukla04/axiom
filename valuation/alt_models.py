from typing import Optional

from valuation._config import SECTOR_PB, TICKER_PB, SECTOR_PFFO, TICKER_PFFO


def bank_model(book_value: float, shares: float, tag: str, ticker: str = '') -> Optional[float]:
    if not book_value or not shares or shares == 0:
        return None
    pb = TICKER_PB.get(ticker) or SECTOR_PB.get(tag, 1.6)
    return (book_value * pb) / shares


def reit_model(net_income: float, depreciation: float, shares: float, ticker: str = '') -> Optional[float]:
    if not shares or shares == 0:
        return None
    ffo = (net_income or 0) + (depreciation or 0)
    if ffo <= 0:
        return None
    pffo = TICKER_PFFO.get(ticker) or SECTOR_PFFO.get('reit', 20.0)
    return (ffo / shares) * pffo


def growth_loss_model(analyst_target: Optional[float]) -> Optional[float]:
    if not analyst_target:
        return None
    return analyst_target * 0.85


def run_alternative_model(tag: str, company_data: dict) -> Optional[float]:
    shares = float(company_data.get('shares_outstanding', 0) or 0)
    if shares == 0:
        return None

    if tag in ('commercial_bank', 'invest_bank', 'pc_insurance'):
        book_value = float(company_data.get('book_value', 0) or 0)
        return bank_model(book_value, shares, tag, company_data.get('ticker', ''))

    if tag == 'reit':
        return reit_model(
            float(company_data.get('net_income', 0) or 0),
            float(company_data.get('depreciation', 0) or 0),
            shares,
            company_data.get('ticker', ''),
        )

    if tag == 'growth_loss':
        return growth_loss_model(company_data.get('analyst_target'))

    if tag == 'health_insurance':
        net_income = float(company_data.get('net_income', 0) or 0)
        if net_income > 0:
            pe_price = (net_income * 16.0) / shares
            if pe_price > 0:
                return pe_price
        analyst_target = company_data.get('analyst_target')
        if analyst_target and analyst_target > 0:
            return analyst_target * 0.80
        return None

    if company_data.get('_non_usd_reporting'):
        analyst_target = company_data.get('analyst_target')
        if analyst_target and analyst_target > 0:
            return analyst_target * 0.88

    if tag == 'crypto_proxy':
        return growth_loss_model(company_data.get('analyst_target'))

    if tag == 'rule40_saas':
        revenue = float(company_data.get('revenue', 0) or 0)
        if revenue <= 0:
            return growth_loss_model(company_data.get('analyst_target'))
        g1 = float(company_data.get('growth_rate_y1', 0) or 0)
        r40 = g1 * 100
        ev_rev = 11.0 if r40 >= 40 else 7.5 if r40 >= 25 else 5.0 if r40 >= 10 else 3.5
        debt   = float(company_data.get('debt', 0) or 0)
        cash   = float(company_data.get('cash', 0) or 0)
        equity = max(0.0, revenue * ev_rev - debt + cash)
        return equity / shares

    if tag == 'utility_regulated':
        net_income = float(company_data.get('net_income', 0) or 0)
        if net_income <= 0:
            return None
        risk_free      = float(company_data.get('risk_free_rate', 0.045) or 0.045)
        required_yield = max(0.035, risk_free + 0.005)
        equity_value   = (net_income * 0.67) / required_yield
        return equity_value / shares if equity_value > 0 else None

    return None
