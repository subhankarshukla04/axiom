import json
import logging
from datetime import date, timedelta
from typing import Optional

from valuation._config import TICKER_TAG_MAP, BLEND_WEIGHTS
from valuation.tagging import get_sub_sector_tag, classify_company
from ml.log import PREDICTION_LOG_PATH

logger = logging.getLogger(__name__)


def run_backtest(tickers: Optional[list] = None, lookback_years: int = 1) -> list:
    import yfinance as yf

    if tickers is None:
        tickers = list(TICKER_TAG_MAP.keys())[:50]

    results = []
    current_year = date.today().year

    for ticker in tickers:
        try:
            stock      = yf.Ticker(ticker)
            financials = stock.financials
            hist       = stock.history(period='5y')

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
                ebitda  = float(fin_col.get('EBITDA', 0) or 0)
                if revenue <= 0 or ebitda <= 0:
                    continue

                try:
                    pred_slice = hist.loc[f'{target_year}-01-15':f'{target_year}-03-01']
                    if pred_slice.empty:
                        continue
                    price_at_prediction = float(pred_slice['Close'].iloc[0])
                    prediction_date     = pred_slice.index[0]
                except Exception:
                    continue

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
                    continue

                info    = stock.info
                shares  = float(info.get('sharesOutstanding', 1e9) or 1e9)
                sector  = info.get('sector', '')
                industry = info.get('industry', '')
                tag     = get_sub_sector_tag(ticker, sector, industry)
                g1      = float(info.get('revenueGrowth', 0.05) or 0.05)
                company_type = classify_company({
                    'sub_sector_tag': tag, 'growth_rate_y1': g1,
                    'profit_margin': 0.10, 'market_cap': price_at_prediction * shares,
                    'beta': float(info.get('beta', 1.0) or 1.0), 'ebitda': ebitda,
                })

                record = {
                    'ticker':            ticker,
                    'predicted_at':      prediction_date.strftime('%Y-%m-%dT00:00:00'),
                    'predicted_price':   round(price_at_prediction, 2),
                    'model_version':     'backtest_v3',
                    'company_type':      company_type,
                    'sub_sector_tag':    tag,
                    'blend_weights':     BLEND_WEIGHTS.get(company_type),
                    'wacc':              0.095,
                    'growth_y1':         g1,
                    'ebitda_method':     'backtest',
                    'monthly_prices':    monthly_prices,
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

    logger.info(f'Backtest complete: {len(results)} records')
    return results
