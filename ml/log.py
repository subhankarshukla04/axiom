import json
import logging
import os
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


def _get_market_regime() -> str:
    """Returns 'risk_off' if VIX > 25, 'risk_on' otherwise. Best-effort — never blocks."""
    try:
        import yfinance as yf
        vix = yf.Ticker('^VIX').fast_info.get('lastPrice') or yf.download('^VIX', period='1d', progress=False)['Close'].iloc[-1]
        return 'risk_off' if float(vix) > 25 else 'risk_on'
    except Exception:
        return 'unknown'

PREDICTION_LOG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'prediction_log.jsonl')


def _get_analyst_target(ticker: str, company_data: dict) -> Optional[float]:
    try:
        from config import Config
        import psycopg2
        if Config.DATABASE_TYPE != 'postgresql':
            return company_data.get('analyst_target')
        conn = psycopg2.connect(Config.get_db_connection_string())
        cur  = conn.cursor()
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


def log_prediction(ticker: str, predicted_price: float, company_data: dict,
                   model_version: str = 'v2') -> None:
    record = {
        'ticker':          ticker,
        'predicted_at':    datetime.utcnow().isoformat(),
        'pure_dcf_price':  company_data.get('dcf_price_per_share'),  # clean DCF only
        'predicted_price': predicted_price,                           # kept for compat
        'model_version':   model_version,
        'company_type':    company_data.get('company_type'),
        'sub_sector_tag':  company_data.get('sub_sector_tag'),
        'analyst_target':  company_data.get('analyst_target'),
        'wacc':            company_data.get('wacc'),
        'growth_y1':       company_data.get('growth_rate_y1'),
        'ebitda_method':   company_data.get('ebitda_method'),
        'market_regime':   _get_market_regime(),
    }

    try:
        with open(PREDICTION_LOG_PATH, 'a') as f:
            f.write(json.dumps(record) + '\n')
    except Exception as e:
        logger.warning(f'prediction log write failed: {e}')

    try:
        from config import Config
        import psycopg2
        if Config.DATABASE_TYPE != 'postgresql':
            return
        conn = psycopg2.connect(Config.get_db_connection_string())
        cur  = conn.cursor()
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
        pass
