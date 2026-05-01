import os as _os
# Point yfinance cache to /tmp so it works on read-only filesystems (Lambda, containers)
_os.environ.setdefault('YFINANCE_CACHE_DIR', '/tmp/yfinance')
try:
    import yfinance as _yf
    _yf.set_tz_cache_location('/tmp/yfinance')
except Exception:
    pass

from flask import Flask, render_template, request, jsonify, send_file
import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor
import json
from datetime import datetime
import io
import csv
from pydantic import ValidationError
from models import CompanyCreate, CompanyUpdate
from valuation_service import ValuationService
from data_integrator import DataIntegrator, fetch_company_by_ticker

# Phase 0: Import new modules
from config import Config, get_config
from auth import init_auth, login_required, role_required, current_user
from logger import setup_app_logger, get_logger, log_api_request, log_valuation

# Phase 1: Import scenario management APIs
from phase1_api_endpoints import register_phase1_routes
from realtime_price_service import get_price_service

# Advanced features: portfolio construction, universal import, assumption overrides
from advanced_api_endpoints import register_advanced_routes

# Initialize Flask app
app = Flask(__name__)

# Load configuration
config = get_config()
app.config.from_object(config)

# Initialize logging (replaces old logging.basicConfig)
logger = setup_app_logger(app, log_level=config.LOG_LEVEL)

# Initialize authentication
init_auth(app)

# Initialize services
valuation_service = ValuationService(db_path=Config.SQLITE_DB)
data_integrator = DataIntegrator()

# Register Phase 1 API routes (scenarios, macros, audit trail)
register_phase1_routes(app)
logger.info("Phase 1 API endpoints registered (31 endpoints)")

# Register advanced API routes (portfolio, import, assumption overrides)
register_advanced_routes(app)
logger.info("Advanced API endpoints registered (ticker import, portfolio construction, assumption overrides)")

# Register AXIOM Phase 1-5 routes (LBO, football field, sensitivity, exports, live stream)
from axiom_api_endpoints import register_axiom_routes
register_axiom_routes(app)
logger.info("AXIOM Phase 1-5 routes registered (LBO, football field, sensitivity, exports, alerts, live stream)")

# ── Daily end-of-day price update scheduler ───────────────────────────────────
try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    import pytz

    def _scheduled_price_update():
        """Run daily at 4:30 PM ET (after US market close) on weekdays."""
        try:
            logger.info("Scheduled price update starting...")
            svc = get_price_service()
            updated = svc.update_all_portfolio_prices()
            logger.info(f"Scheduled price update complete: {len(updated)} companies updated")
        except Exception as e:
            logger.error(f"Scheduled price update failed: {e}")

    _scheduler = BackgroundScheduler(timezone=pytz.utc)
    # 4:30 PM Eastern = 21:30 UTC (EST) or 20:30 UTC (EDT) — use 21:30 UTC which covers both
    _scheduler.add_job(
        _scheduled_price_update,
        CronTrigger(day_of_week='mon-fri', hour=21, minute=30, timezone='America/New_York'),
        id='daily_price_update',
        replace_existing=True
    )
    _scheduler.start()
    logger.info("Daily price update scheduler started (runs Mon-Fri at 4:30 PM ET)")
except ImportError:
    logger.warning("APScheduler not installed — daily price updates disabled. Run: pip install apscheduler pytz")
except Exception as e:
    logger.error(f"Failed to start price scheduler: {e}")

# Database connection helper (supports both PostgreSQL and SQLite)
def get_db_connection():
    """Get database connection based on configuration"""
    if Config.DATABASE_TYPE == 'postgresql':
        conn = psycopg2.connect(
            Config.get_db_connection_string(),
            cursor_factory=RealDictCursor
        )
        return conn
    else:
        # Fallback to SQLite
        conn = sqlite3.connect(Config.SQLITE_DB)
        conn.row_factory = sqlite3.Row
        return conn

def dict_from_row(row):
    """Convert database row to dict (works for both PostgreSQL and SQLite)"""
    if isinstance(row, dict):
        return row  # PostgreSQL RealDictRow
    else:
        return dict(row)  # SQLite Row

def convert_numpy_types(data):
    """Convert numpy types to Python native types for PostgreSQL compatibility"""
    import numpy as np

    if isinstance(data, dict):
        return {k: convert_numpy_types(v) for k, v in data.items()}
    elif isinstance(data, (np.integer, np.floating)):
        return float(data) if isinstance(data, np.floating) else int(data)
    elif isinstance(data, np.ndarray):
        return data.tolist()
    else:
        return data

def execute_query(cursor, query, params=None):
    """Execute query with proper placeholder syntax for PostgreSQL or SQLite"""
    if Config.DATABASE_TYPE == 'postgresql':
        # PostgreSQL uses %s, query should already use %s
        pass
    else:
        # SQLite uses ?, convert %s to ?
        query = query.replace('%s', '?')

    if params:
        return cursor.execute(query, params)
    return cursor.execute(query)

# Database initialization
def init_db():
    """Initialize database tables (SQLite) or run column migrations (PostgreSQL)."""
    if Config.DATABASE_TYPE == 'postgresql':
        try:
            conn = get_db_connection()
            c = conn.cursor()
            pg_migrations = [
                'ALTER TABLE companies ADD COLUMN IF NOT EXISTS industry TEXT',
                'ALTER TABLE valuation_results ADD COLUMN IF NOT EXISTS sub_sector_tag TEXT',
                'ALTER TABLE valuation_results ADD COLUMN IF NOT EXISTS company_type TEXT',
                'ALTER TABLE valuation_results ADD COLUMN IF NOT EXISTS ebitda_method TEXT',
                'ALTER TABLE valuation_results ADD COLUMN IF NOT EXISTS analyst_target REAL',
            ]
            for sql in pg_migrations:
                c.execute(sql)
            conn.commit()
            conn.close()
            logger.info("PostgreSQL column migrations applied")
        except Exception as e:
            logger.warning(f"PostgreSQL migration warning: {e}")
        return

    logger.info("Initializing SQLite database...")
    conn = sqlite3.connect(Config.SQLITE_DB)
    c = conn.cursor()

    # Companies table
    c.execute('''CREATE TABLE IF NOT EXISTS companies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        sector TEXT,
        ticker TEXT,
        industry TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    # Add ticker/industry columns to existing DBs (no-op if already present)
    for col, coltype in [('ticker', 'TEXT'), ('industry', 'TEXT')]:
        try:
            c.execute(f'ALTER TABLE companies ADD COLUMN {col} {coltype}')
        except Exception:
            pass

    # Company financials table
    c.execute('''CREATE TABLE IF NOT EXISTS company_financials (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER,
        revenue REAL,
        ebitda REAL,
        depreciation REAL,
        capex_pct REAL,
        working_capital_change REAL,
        profit_margin REAL,
        growth_rate_y1 REAL,
        growth_rate_y2 REAL,
        growth_rate_y3 REAL,
        terminal_growth REAL,
        tax_rate REAL,
        shares_outstanding REAL,
        debt REAL,
        cash REAL,
        market_cap_estimate REAL,
        beta REAL,
        risk_free_rate REAL,
        market_risk_premium REAL,
        country_risk_premium REAL,
        size_premium REAL,
        comparable_ev_ebitda REAL,
        comparable_pe REAL,
        comparable_peg REAL,
        FOREIGN KEY (company_id) REFERENCES companies (id)
    )''')

    # Valuation results table
    c.execute('''CREATE TABLE IF NOT EXISTS valuation_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER,
        valuation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        dcf_equity_value REAL,
        dcf_price_per_share REAL,
        comp_ev_value REAL,
        comp_pe_value REAL,
        final_equity_value REAL,
        final_price_per_share REAL,
        market_cap REAL,
        current_price REAL,
        upside_pct REAL,
        recommendation TEXT,
        wacc REAL,
        ev_ebitda REAL,
        pe_ratio REAL,
        fcf_yield REAL,
        roe REAL,
        roic REAL,
        debt_to_equity REAL,
        z_score REAL,
        mc_p10 REAL,
        mc_p90 REAL,
        sub_sector_tag TEXT,
        company_type TEXT,
        ebitda_method TEXT,
        analyst_target REAL,
        FOREIGN KEY (company_id) REFERENCES companies (id)
    )''')

    # Add new columns to existing valuation_results (no-op if already present)
    for col, coltype in [('sub_sector_tag', 'TEXT'), ('company_type', 'TEXT'),
                         ('ebitda_method', 'TEXT'), ('analyst_target', 'REAL')]:
        try:
            c.execute(f'ALTER TABLE valuation_results ADD COLUMN {col} {coltype}')
        except Exception:
            pass

    # Macro assumptions table (used by macro_service)
    c.execute('''CREATE TABLE IF NOT EXISTS macro_assumptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        risk_free_rate REAL DEFAULT 0.045,
        market_risk_premium REAL DEFAULT 0.065,
        gdp_growth REAL DEFAULT 0.025,
        inflation_rate REAL DEFAULT 0.030,
        credit_spread_aaa REAL DEFAULT 0.005,
        credit_spread_aa REAL DEFAULT 0.0075,
        credit_spread_a REAL DEFAULT 0.010,
        credit_spread_bbb REAL DEFAULT 0.015,
        credit_spread_bb REAL DEFAULT 0.025,
        credit_spread_b REAL DEFAULT 0.040,
        corporate_tax_rate REAL DEFAULT 0.21,
        equity_risk_appetite TEXT DEFAULT 'neutral',
        created_by INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    # Scenarios table (used by scenario_service)
    c.execute('''CREATE TABLE IF NOT EXISTS scenarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER,
        name TEXT,
        scenario_type TEXT,
        assumptions TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (company_id) REFERENCES companies (id)
    )''')

    conn.commit()
    conn.close()
    logger.info("SQLite database initialized successfully")


def ensure_settings_table():
    """Ensure a settings table exists for persistent app settings (works for both DBs)"""
    conn = get_db_connection()
    c = conn.cursor()
    placeholder = '%s' if Config.DATABASE_TYPE == 'postgresql' else '?'

    # Create a simple key/value table where value is JSON text
    if Config.DATABASE_TYPE == 'postgresql':
        c.execute('''CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )''')
    else:
        c.execute('''CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )''')

    conn.commit()
    conn.close()


# Ensure settings table exists on startup
ensure_settings_table()

# Initialize database on startup
init_db()

# ============================================================================
# NEW INSTITUTIONAL-GRADE ENDPOINTS
# ============================================================================

@app.route('/api/ticker/validate', methods=['POST'])
def validate_ticker():
    """
    Validate if a ticker symbol exists.
    Returns: {valid: true/false, name: "Company Name"}
    """
    data = request.json
    ticker = data.get('ticker', '').upper().strip()

    if not ticker:
        return jsonify({'valid': False, 'error': 'Ticker required'}), 400

    try:
        is_valid = data_integrator.validate_ticker(ticker)
        if is_valid:
            stock_data = data_integrator.get_company_data(ticker)
            return jsonify({
                'valid': True,
                'ticker': ticker,
                'name': stock_data.get('name'),
                'sector': stock_data.get('sector'),
                'current_price': stock_data.get('current_price')
            })
        else:
            return jsonify({'valid': False, 'error': 'Invalid ticker'}), 404
    except Exception as e:
        logger.error(f"Error validating ticker {ticker}: {e}")
        return jsonify({'valid': False, 'error': str(e)}), 500


@app.route('/api/ticker/fetch', methods=['POST'])
def fetch_ticker_data():
    """
    Fetch complete company data from Yahoo Finance by ticker.
    Auto-populates ALL fields needed for valuation.

    POST body: {"ticker": "AAPL"}
    Returns: Complete company financial data
    """
    data = request.json
    ticker = data.get('ticker', '').upper().strip()

    if not ticker:
        return jsonify({'error': 'Ticker required'}), 400

    try:
        logger.info(f"Fetching data for ticker: {ticker}")
        company_data = data_integrator.get_company_data(ticker)

        if company_data:
            return jsonify({
                'success': True,
                'data': company_data,
                'message': f'Successfully fetched data for {company_data["name"]}'
            })
        else:
            return jsonify({
                'success': False,
                'error': f'Could not fetch data for ticker: {ticker}'
            }), 404

    except Exception as e:
        logger.error(f"Error fetching ticker data: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/ticker/import-and-value', methods=['POST'])
def import_and_value():
    """
    ONE-CLICK MAGIC: Import company from ticker and run full valuation.

    POST body: {"ticker": "AAPL"}
    Returns: Company ID, valuation results, and recommendation
    """
    data = request.json
    ticker = data.get('ticker', '').upper().strip()

    if not ticker:
        return jsonify({'error': 'Ticker required'}), 400

    try:
        logger.info(f"Import-and-value workflow for: {ticker}")

        # Step 1: Fetch data from Yahoo Finance
        company_data = data_integrator.get_company_data(ticker)
        if not company_data:
            return jsonify({'error': f'Could not fetch data for {ticker}'}), 404

        # Convert numpy types to Python types for PostgreSQL compatibility
        company_data = convert_numpy_types(company_data)

        # Step 2: Save to database
        conn = get_db_connection()
        c = conn.cursor()

        # Insert company
        industry_val = company_data.get('industry') or None
        if Config.DATABASE_TYPE == 'postgresql':
            c.execute('INSERT INTO companies (name, sector, ticker, industry) VALUES (%s, %s, %s, %s) RETURNING id',
                      (company_data['name'], company_data['sector'], ticker, industry_val))
            company_id = c.fetchone()['id']
        else:
            c.execute('INSERT INTO companies (name, sector, ticker, industry) VALUES (?, ?, ?, ?)',
                      (company_data['name'], company_data['sector'], ticker, industry_val))
            company_id = c.lastrowid

        # Insert financials
        placeholder = '%s' if Config.DATABASE_TYPE == 'postgresql' else '?'
        placeholders = ', '.join([placeholder] * 24)
        c.execute(f'''INSERT INTO company_financials (
            company_id, revenue, ebitda, depreciation, capex_pct, working_capital_change,
            profit_margin, growth_rate_y1, growth_rate_y2, growth_rate_y3, terminal_growth,
            tax_rate, shares_outstanding, debt, cash, market_cap_estimate, beta,
            risk_free_rate, market_risk_premium, country_risk_premium, size_premium,
            comparable_ev_ebitda, comparable_pe, comparable_peg
        ) VALUES ({placeholders})''',
        (company_id,
         company_data['revenue'], company_data['ebitda'], company_data['depreciation'],
         company_data['capex_pct'], company_data['working_capital_change'],
         company_data['profit_margin'],
         company_data['growth_rate_y1'], company_data['growth_rate_y2'],
         company_data['growth_rate_y3'], company_data['terminal_growth'],
         company_data['tax_rate'], company_data['shares_outstanding'],
         company_data['debt'], company_data['cash'], company_data['market_cap'],
         company_data['beta'], company_data['risk_free_rate'],
         company_data['market_risk_premium'], company_data['country_risk_premium'],
         company_data['size_premium'], company_data['comparable_ev_ebitda'],
         company_data['comparable_pe'], company_data['comparable_peg']))

        conn.commit()
        conn.close()

        # Step 3: Run valuation
        success, results, error = valuation_service.valuate_company(company_id)

        if success:
            return jsonify({
                'success': True,
                'company_id': company_id,
                'company_name': company_data['name'],
                'ticker': ticker,
                'current_price': company_data['current_price'],
                'valuation': results,
                'message': f'Successfully imported and valued {company_data["name"]}'
            })
        else:
            return jsonify({
                'success': False,
                'company_id': company_id,
                'error': f'Company imported but valuation failed: {error}'
            }), 500

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logger.error(f"Error in import-and-value: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e), 'traceback': tb}), 500


@app.route('/api/health', methods=['GET'])
def health():
    """Instant health check — no external calls."""
    return jsonify({'status': 'ok', 'db': Config.SQLITE_DB, 'routes': len(list(app.url_map.iter_rules()))})


@app.route('/api/debug/<ticker>', methods=['GET'])
def debug_import(ticker):
    """Diagnostic endpoint — hit /api/debug/AAPL to see exactly what fails."""
    import traceback, time
    out = {'ticker': ticker.upper(), 'steps': []}
    try:
        t0 = time.time()
        import yfinance as yf
        stock = yf.Ticker(ticker.upper())
        info = stock.info
        out['steps'].append({'info_fetch': round(time.time()-t0, 2), 'symbol': info.get('symbol'), 'name': info.get('longName')})
    except Exception as e:
        out['steps'].append({'info_error': str(e), 'traceback': traceback.format_exc()})
        return jsonify(out)
    try:
        t1 = time.time()
        company_data = data_integrator.get_company_data(ticker.upper())
        out['steps'].append({'get_company_data': round(time.time()-t1, 2), 'keys': list(company_data.keys()) if company_data else None})
    except Exception as e:
        out['steps'].append({'get_company_data_error': str(e), 'traceback': traceback.format_exc()})
        return jsonify(out)
    try:
        t2 = time.time()
        conn = get_db_connection()
        conn.execute('SELECT 1')
        conn.close()
        out['steps'].append({'db_connection': round(time.time()-t2, 2), 'sqlite_path': Config.SQLITE_DB})
    except Exception as e:
        out['steps'].append({'db_error': str(e), 'traceback': traceback.format_exc()})
    out['total_seconds'] = round(time.time()-t0, 2)
    return jsonify(out)


@app.route('/api/price/realtime/<ticker>', methods=['GET'])
def get_realtime_price(ticker):
    """
    Get real-time stock price for a ticker.

    GET /api/price/realtime/AAPL
    Returns: {ticker: "AAPL", price: 150.25, timestamp: "2024-11-30T10:30:00"}
    """
    try:
        price = data_integrator.get_real_time_price(ticker.upper())
        if price:
            return jsonify({
                'ticker': ticker.upper(),
                'price': price,
                'timestamp': datetime.now().isoformat()
            })
        else:
            return jsonify({'error': 'Could not fetch price'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================================
# EXISTING ENDPOINTS (unchanged)
# ============================================================================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/preview')
def preview():
    return render_template('preview.html')

@app.route('/dcf/<int:company_id>')
def dcf_detail_page(company_id):
    return render_template('dcf_detail.html', company_id=company_id)

@app.route('/ev-ebitda/<int:company_id>')
def ev_ebitda_detail_page(company_id):
    return render_template('ev_ebitda_detail.html', company_id=company_id)

@app.route('/pe/<int:company_id>')
def pe_detail_page(company_id):
    return render_template('pe_detail.html', company_id=company_id)

@app.route('/api/companies', methods=['GET'])
def get_companies():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''SELECT c.id, c.name, c.ticker, c.sector, c.created_at,
                 vr.final_equity_value, vr.final_price_per_share, vr.dcf_price_per_share,
                 vr.recommendation, vr.upside_pct,
                 vr.pe_ratio, vr.roe, vr.z_score, vr.market_cap,
                 vr.current_price, vr.wacc, vr.ev_ebitda, vr.roic,
                 vr.fcf_yield, vr.debt_to_equity, vr.analyst_target
                 FROM companies c
                 LEFT JOIN valuation_results vr ON c.id = vr.company_id
                 AND vr.id = (SELECT MAX(id) FROM valuation_results WHERE company_id = c.id)
                 ORDER BY c.created_at DESC''')
    
    companies = []
    for row in c.fetchall():
        r = dict_from_row(row)
        companies.append({
            'id': r['id'],
            'name': r['name'],
            'ticker': r.get('ticker'),
            'sector': r['sector'],
            'created_at': r['created_at'],
            'fair_value': r.get('final_price_per_share') or r.get('dcf_price_per_share') or r.get('final_equity_value'),
            'dcf_equity_value': r.get('dcf_equity_value'),
            'dcf_price_per_share': r.get('dcf_price_per_share'),
            'comp_ev_value': r.get('comp_ev_value'),
            'comp_pe_value': r.get('comp_pe_value'),
            'mc_p10': r.get('mc_p10'),
            'mc_p90': r.get('mc_p90'),
            'recommendation': r['recommendation'],
            'upside': r['upside_pct'],
            'pe_ratio': r['pe_ratio'],
            'roe': r['roe'],
            'z_score': r['z_score'],
            'market_cap': r['market_cap'],
            'current_price': r['current_price'],
            'wacc': r['wacc'],
            'ev_ebitda': r['ev_ebitda'],
            'roic': r['roic'],
            'fcf_yield': r['fcf_yield'],
            'debt_to_equity': r['debt_to_equity'],
            'analyst_target': r.get('analyst_target')
        })
    
    conn.close()
    return jsonify(companies)


def _load_settings_from_db():
    conn = get_db_connection()
    c = conn.cursor()
    # Fetch the 'app_settings' key if present using correct placeholder
    placeholder = '%s' if Config.DATABASE_TYPE == 'postgresql' else '?'
    query = f"SELECT value FROM settings WHERE key = {placeholder}"
    c.execute(query, ('app_settings',))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    # row may be tuple, list, or dict-like
    if isinstance(row, dict):
        val = row.get('value')
    else:
        try:
            val = row[0]
        except Exception:
            val = None

    import json as _json
    try:
        return _json.loads(val) if val else None
    except Exception:
        return None


def _save_settings_to_db(settings_dict):
    import json as _json
    json_text = _json.dumps(settings_dict)
    conn = get_db_connection()
    c = conn.cursor()
    # Upsert depending on DB
    if Config.DATABASE_TYPE == 'postgresql':
        c.execute("INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", ('app_settings', json_text))
    else:
        c.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', ('app_settings', json_text))

    conn.commit()
    conn.close()


@app.route('/api/settings', methods=['GET'])
def get_settings():
    """Return merged settings (defaults from Config overridden by DB-stored values)."""
    # Defaults from Config
    defaults = {
        'recommendation_thresholds': Config.RECOMMENDATION_THRESHOLDS,
        'valuation_weights': Config.VALUATION_WEIGHTS,
        'bear_multiplier': Config.BEAR_MULTIPLIER,
        'bull_multiplier': Config.BULL_MULTIPLIER,
        'monte_growth_vol': Config.MONTE_CARLO_GROWTH_VOL,
        'monte_discount_vol': Config.MONTE_CARLO_DISCOUNT_VOL,
        'terminal_margin': Config.TERMINAL_MARGIN,
        'alt_zscore_sell_threshold': Config.ALT_ZSCORE_SELL_THRESHOLD,
        'debt_equity_downgrade': Config.DEBT_EQUITY_DOWNGRADE
    }

    stored = _load_settings_from_db() or {}

    # Merge (stored values override defaults)
    merged = defaults.copy()
    merged.update(stored)
    return jsonify(merged)


@app.route('/api/settings', methods=['PUT'])
def update_settings():
    """Update settings (accepts partial JSON). Persists to DB."""
    try:
        data = request.json
        if not isinstance(data, dict):
            return jsonify({'error': 'Invalid payload, expected JSON object'}), 400

        current = _load_settings_from_db() or {}
        # Merge updates
        current.update(data)
        _save_settings_to_db(current)
        return jsonify({'success': True, 'settings': current})
    except Exception as e:
        logger.error(f"Error updating settings: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/config/heuristics', methods=['GET'])
def get_heuristics_inventory():
    """Phase 1 transparency endpoint: returns every hand-picked constant
    that drives the valuation output. Read-only — editing arrives in Phase 2.

    See HARDCODED_VALUES.md for the full audit-trail per row.
    """
    import os, json
    cfg_dir = os.path.join(os.path.dirname(__file__), 'valuation', 'config')
    payload = {'configs': {}, 'magic_numbers': []}

    for fname in sorted(os.listdir(cfg_dir)):
        if not fname.endswith('.json'):
            continue
        with open(os.path.join(cfg_dir, fname)) as fh:
            payload['configs'][fname] = json.load(fh)

    # Magic numbers embedded in Python — keep this list in sync with HARDCODED_VALUES.md §2 & §3
    payload['magic_numbers'] = [
        {'file': 'valuation/normalizers.py', 'line': 45, 'value': '12.0 / 20.0',
         'gates': 'EV/EBITDA & P/E fallback for unknown sub-sector', 'phase': 'P2'},
        {'file': 'valuation/normalizers.py', 'line': 53, 'value': '** 0.4',
         'gates': 'PEG-style growth-vs-sector exponent (no derivation)', 'phase': 'P2'},
        {'file': 'valuation/normalizers.py', 'line': 54, 'value': 'clip [0.5, 1.5]',
         'gates': 'Caps multiple stretch — destroys tails', 'phase': 'P2'},
        {'file': 'valuation/anchoring.py', 'line': '3-11', 'value': 'STORY 0.70 etc.',
         'gates': 'Analyst anchor weight per company type', 'phase': 'P3'},
        {'file': 'valuation/anchoring.py', 'line': '19-28', 'value': '4×, 0.25×, 10× bands',
         'gates': 'Sanity guardrails on final price', 'phase': 'P3'},
        {'file': 'valuation/tagging.py', 'line': '110-130', 'value': 'g>0.20, margin>0.08, beta>1.8 ...',
         'gates': 'Hard cliffs into company-type buckets', 'phase': 'P6'},
        {'file': 'valuation/pipeline.py', 'line': 48, 'value': 'debt × 0.25',
         'gates': 'Auto OEM captive-finance debt cut', 'phase': 'P2'},
        {'file': 'valuation/pipeline.py', 'line': 56, 'value': 'debt × 0.35',
         'gates': 'Airline operating-lease debt cut', 'phase': 'P2'},
        {'file': 'valuation/pipeline.py', 'line': '67-68', 'value': 'anchor 0.85',
         'gates': 'Forced 85% analyst anchor for non-USD reporters', 'phase': 'P3'},
        {'file': 'valuation/pipeline.py', 'line': '73-75', 'value': 'WACC + 0.015',
         'gates': 'Telecom/utility leverage WACC penalty', 'phase': 'P2'},
        {'file': 'valuation/pipeline.py', 'line': '83-84', 'value': '(0.67, 0.33) / (0.33, 0.67)',
         'gates': 'Y2/Y3 growth convergence weights', 'phase': 'P4'},
        {'file': 'valuation/alt_models.py', 'line': 9, 'value': 'P/B 1.6',
         'gates': 'Bank P/B fallback when sector + ticker missing', 'phase': 'P2'},
        {'file': 'valuation/alt_models.py', 'line': 19, 'value': 'P/FFO 20.0',
         'gates': 'REIT P/FFO fallback', 'phase': 'P2'},
        {'file': 'valuation/alt_models.py', 'line': 26, 'value': '× 0.85',
         'gates': 'Growth-loss model haircut on analyst target', 'phase': 'P3'},
        {'file': 'valuation/alt_models.py', 'line': 52, 'value': 'P/E 16.0, × 0.80',
         'gates': 'Health-insurance multiple + analyst haircut', 'phase': 'P2'},
        {'file': 'valuation/alt_models.py', 'line': 63, 'value': '× 0.88',
         'gates': 'Non-USD analyst haircut', 'phase': 'P3'},
        {'file': 'valuation/alt_models.py', 'line': 74, 'value': '11/7.5/5/3.5',
         'gates': 'Rule-of-40 SaaS EV/Revenue tiers', 'phase': 'P2'},
        {'file': 'valuation/alt_models.py', 'line': '84-87', 'value': 'rf+0.005, NI×0.67',
         'gates': 'Utility DDM-style payout assumption', 'phase': 'P2'},
        {'file': 'ml/calibrator.py', 'line': '132-134', 'value': 'clip [0.2, 5.0]',
         'gates': 'Censors large mispricings — kills the signal the model exists to find', 'phase': 'P3'},
        {'file': 'ml/calibrator.py', 'line': 137, 'value': '80/20 split',
         'gates': 'Single chronological holdout, no k-fold or grid search', 'phase': 'P3'},
        {'file': 'ml/calibrator.py', 'line': '23-35', 'value': '_TAG_VOL_DEFAULT',
         'gates': 'Sector volatility priors used at inference', 'phase': 'P4'},
        {'file': 'ml/walk_forward.py', 'line': '235-280', 'value': 'VIX>22, HYG-3mo<-3%, ^IRX>^TNX, SPY<MA200, SPY-3mo<-8%',
         'gates': 'Hardcoded composite-regime thresholds', 'phase': 'P5'},
        {'file': 'ml/log.py', 'line': 15, 'value': 'VIX > 25',
         'gates': 'Legacy 2-state regime', 'phase': 'P5'},
    ]

    payload['summary'] = {
        'json_constants_total': sum(
            len(json.dumps(v)) // 8 for v in payload['configs'].values()  # rough proxy; HARDCODED_VALUES.md has the canonical count
        ),
        'see_also': '/api/config/heuristics/doc',
    }
    return jsonify(payload)


@app.route('/heuristics')
def heuristics_page():
    """Phase 1 transparency UI — read-only view of every hand-picked constant."""
    return render_template('heuristics.html')


@app.route('/api/company/<int:company_id>', methods=['GET'])
def get_company(company_id):
    conn = get_db_connection()
    c = conn.cursor()

    # Use placeholder-aware queries
    placeholder = '%s' if Config.DATABASE_TYPE == 'postgresql' else '?'

    # Get company info
    c.execute(f'SELECT * FROM companies WHERE id = {placeholder}', (company_id,))
    company_row = c.fetchone()

    if not company_row:
        conn.close()
        return jsonify({'error': 'Company not found'}), 404

    # Get financials
    c.execute(f'SELECT * FROM company_financials WHERE company_id = {placeholder}', (company_id,))
    financials_row = c.fetchone()

    # Get latest valuation
    c.execute(f'SELECT * FROM valuation_results WHERE company_id = {placeholder} ORDER BY valuation_date DESC LIMIT 1', (company_id,))
    valuation_row = c.fetchone()

    conn.close()

    # Normalize rows to dicts for both SQLite and PostgreSQL
    comp = dict_from_row(company_row)
    fin = dict_from_row(financials_row) if financials_row else None
    val = dict_from_row(valuation_row) if valuation_row else None

    company_data = {
        'id': comp.get('id'),
        'name': comp.get('name'),
        'sector': comp.get('sector'),
        'financials': fin,
        'valuation': val
    }

    return jsonify(company_data)

@app.route('/api/company', methods=['POST'])
def create_company():
    try:
        data = request.json
        
        # Validate input with Pydantic
        company_data = CompanyCreate(**data)
        logger.info(f"Creating company: {company_data.name}")
        
        conn = get_db_connection()
        c = conn.cursor()

        # Insert company (use RETURNING for PostgreSQL)
        ticker_val = data.get('ticker', '').upper().strip() or None
        industry_val = data.get('industry', '') or None
        if Config.DATABASE_TYPE == 'postgresql':
            c.execute('INSERT INTO companies (name, sector, ticker, industry) VALUES (%s, %s, %s, %s) RETURNING id',
                      (company_data.name, company_data.sector, ticker_val, industry_val))
            company_id = c.fetchone()['id']
        else:
            c.execute('INSERT INTO companies (name, sector, ticker, industry) VALUES (?, ?, ?, ?)',
                      (company_data.name, company_data.sector, ticker_val, industry_val))
            company_id = c.lastrowid

        # Insert financials (use execute_query helper to handle placeholders)
        placeholders = ', '.join(['%s'] * 24)
        execute_query(c, f'''INSERT INTO company_financials (
            company_id, revenue, ebitda, depreciation, capex_pct, working_capital_change,
            profit_margin, growth_rate_y1, growth_rate_y2, growth_rate_y3, terminal_growth,
            tax_rate, shares_outstanding, debt, cash, market_cap_estimate, beta,
            risk_free_rate, market_risk_premium, country_risk_premium, size_premium,
            comparable_ev_ebitda, comparable_pe, comparable_peg
        ) VALUES ({placeholders})''',
        (company_id, company_data.revenue, company_data.ebitda,
         company_data.depreciation, company_data.capex_pct,
         company_data.working_capital_change, company_data.profit_margin,
         company_data.growth_rate_y1, company_data.growth_rate_y2,
         company_data.growth_rate_y3, company_data.terminal_growth,
         company_data.tax_rate, company_data.shares_outstanding,
         company_data.debt, company_data.cash, company_data.market_cap_estimate,
         company_data.beta, company_data.risk_free_rate,
         company_data.market_risk_premium, company_data.country_risk_premium,
         company_data.size_premium, company_data.comparable_ev_ebitda,
         company_data.comparable_pe, company_data.comparable_peg))

        conn.commit()
        conn.close()
        
        logger.info(f"Company created successfully with ID: {company_id}")
        return jsonify({'id': company_id, 'message': 'Company created successfully'}), 201
        
    except ValidationError as e:
        logger.warning(f"Validation error creating company: {str(e)}")
        # Convert Pydantic errors to JSON-serializable format
        errors = []
        for err in e.errors():
            errors.append({
                'field': err['loc'][-1] if err['loc'] else 'unknown',
                'message': err['msg'],
                'type': err['type']
            })
        return jsonify({
            'error': 'Validation failed',
            'details': errors
        }), 400
    except Exception as e:
        logger.error(f"Error creating company: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/company/<int:company_id>', methods=['PUT'])
def update_company(company_id):
    try:
        data = request.json
        logger.debug(f"Received data for company update: {data}")

        # Validate input with Pydantic (all fields optional)
        company_data = CompanyUpdate(**data)
        logger.info(f"Validated data for company ID {company_id}")

        conn = get_db_connection()
        c = conn.cursor()

        # Fetch current data to merge with updates
        placeholder = '%s' if Config.DATABASE_TYPE == 'postgresql' else '?'
        c.execute(f'''
            SELECT c.name, c.sector, cf.*
            FROM companies c
            JOIN company_financials cf ON c.id = cf.company_id
            WHERE c.id = {placeholder}
        ''', (company_id,))

        current = c.fetchone()
        if not current:
            conn.close()
            return jsonify({'error': 'Company not found'}), 404

        current_data = dict(current)

        # Merge: Only update fields that were provided (not None)
        update_dict = company_data.model_dump(exclude_none=True)

        # Update company table fields if provided
        if 'name' in update_dict or 'sector' in update_dict:
            name = update_dict.get('name', current_data['name'])
            sector = update_dict.get('sector', current_data['sector'])

            query_company = 'UPDATE companies SET name = %s, sector = %s, updated_at = %s WHERE id = %s'
            execute_query(c, query_company, (name, sector, datetime.now().isoformat(), company_id))

        # Update financials - only update fields that were provided
        financial_fields = [
            'revenue', 'ebitda', 'depreciation', 'capex_pct',
            'working_capital_change', 'profit_margin', 'growth_rate_y1',
            'growth_rate_y2', 'growth_rate_y3', 'terminal_growth',
            'tax_rate', 'shares_outstanding', 'debt', 'cash',
            'market_cap_estimate', 'beta', 'risk_free_rate',
            'market_risk_premium', 'country_risk_premium', 'size_premium',
            'comparable_ev_ebitda', 'comparable_pe', 'comparable_peg'
        ]

        # Build merged values (use update if provided, else current)
        merged_values = []
        for field in financial_fields:
            if field in update_dict:
                merged_values.append(update_dict[field])
            else:
                merged_values.append(current_data[field])

        merged_values.append(company_id)  # WHERE clause

        query_financials = '''UPDATE company_financials SET
                revenue = %s, ebitda = %s, depreciation = %s, capex_pct = %s,
                working_capital_change = %s, profit_margin = %s, growth_rate_y1 = %s,
                growth_rate_y2 = %s, growth_rate_y3 = %s, terminal_growth = %s,
                tax_rate = %s, shares_outstanding = %s, debt = %s, cash = %s,
                market_cap_estimate = %s, beta = %s, risk_free_rate = %s,
                market_risk_premium = %s, country_risk_premium = %s, size_premium = %s,
                comparable_ev_ebitda = %s, comparable_pe = %s, comparable_peg = %s
                WHERE company_id = %s'''

        execute_query(c, query_financials, tuple(merged_values))

        conn.commit()
        conn.close()

        # 🚨 CRITICAL: Auto-revaluation after financial data update
        logger.info(f"Triggering automatic revaluation for company ID {company_id}")
        success, results, error_msg = valuation_service.valuate_company(company_id)

        if success:
            logger.info(f"Auto-revaluation successful for company ID {company_id}")
            return jsonify({
                'message': 'Company updated and revalued successfully',
                'valuation': results
            })
        else:
            logger.warning(f"Auto-revaluation failed for company ID {company_id}: {error_msg}")
            return jsonify({
                'message': 'Company updated but revaluation failed',
                'error': error_msg
            }), 207  # 207 Multi-Status: partial success

    except ValidationError as e:
        logger.warning(f"Validation error updating company {company_id}: {str(e)}")
        # Convert Pydantic errors to JSON-serializable format
        errors = []
        for err in e.errors():
            errors.append({
                'field': err['loc'][-1] if err['loc'] else 'unknown',
                'message': err['msg'],
                'type': err['type']
            })
        return jsonify({
            'error': 'Validation failed',
            'details': errors
        }), 400
    except Exception as e:
        logger.error(f"Error updating company {company_id}: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/company/<int:company_id>', methods=['DELETE'])
def delete_company(company_id):
    conn = get_db_connection()
    c = conn.cursor()
    # Use correct placeholder depending on DB backend
    placeholder = '%s' if Config.DATABASE_TYPE == 'postgresql' else '?'

    c.execute(f'DELETE FROM valuation_results WHERE company_id = {placeholder}', (company_id,))
    c.execute(f'DELETE FROM company_financials WHERE company_id = {placeholder}', (company_id,))
    c.execute(f'DELETE FROM companies WHERE id = {placeholder}', (company_id,))

    conn.commit()
    conn.close()

    return jsonify({'message': 'Company deleted successfully'})

@app.route('/api/valuation/preview', methods=['POST'])
def preview_valuation():
    """
    Run the full valuation engine without saving to DB.
    Accepts JSON body with all company financial assumptions.
    Returns fair value, upside %, WACC, method breakdown.
    """
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'Request body required'}), 400

        # Build company_data dict from request (same shape as DB fetch)
        company_data = {
            'id': 0,
            'name': data.get('name', 'Preview Company'),
            'sector': data.get('sector', 'Unknown'),
            'revenue': float(data.get('revenue', 0)),
            'ebitda': float(data.get('ebitda', 0)),
            'depreciation': float(data.get('depreciation', 0)),
            'capex_pct': float(data.get('capex_pct', 0.05)),
            'working_capital_change': float(data.get('working_capital_change', 0)),
            'profit_margin': float(data.get('profit_margin', 0.10)),
            'growth_rate_y1': float(data.get('growth_rate_y1', 0.10)),
            'growth_rate_y2': float(data.get('growth_rate_y2', 0.08)),
            'growth_rate_y3': float(data.get('growth_rate_y3', 0.06)),
            'terminal_growth': float(data.get('terminal_growth', 0.025)),
            'tax_rate': float(data.get('tax_rate', 0.21)),
            'shares_outstanding': float(data.get('shares_outstanding', 1000000)),
            'debt': float(data.get('debt', 0)),
            'cash': float(data.get('cash', 0)),
            'market_cap_estimate': float(data.get('market_cap_estimate', 0)),
            'beta': float(data.get('beta', 1.0)),
            'risk_free_rate': float(data.get('risk_free_rate', 0.045)),
            'market_risk_premium': float(data.get('market_risk_premium', 0.065)),
            'country_risk_premium': float(data.get('country_risk_premium', 0.0)),
            'size_premium': float(data.get('size_premium', 0.0)),
            'comparable_ev_ebitda': float(data.get('comparable_ev_ebitda', 10.0)),
            'comparable_pe': float(data.get('comparable_pe', 20.0)),
            'comparable_peg': float(data.get('comparable_peg', 1.5)),
        }

        # Run valuation (no DB write)
        results = valuation_service.run_valuation(company_data)
        if not results:
            return jsonify({'error': 'Valuation failed - check input assumptions'}), 500

        # Return standardized preview response
        shares = company_data['shares_outstanding']
        return jsonify({
            'fair_value': round(results.get('final_price_per_share') or results.get('dcf_price_per_share', 0), 2),
            'upside_pct': round(results.get('upside_pct', 0), 2),
            'wacc': round(results.get('wacc', 0), 4),
            'dcf_value': round(results.get('dcf_price_per_share', 0), 2),
            'comps_value': round(
                (results.get('comp_ev_value', 0) + results.get('comp_pe_value', 0)) / 2 / shares
                if shares > 0 else 0, 2
            ),
            'recommendation': results.get('recommendation', 'N/A'),
            'dcf_equity_value': results.get('dcf_equity_value'),
            'comp_ev_value': results.get('comp_ev_value'),
            'comp_pe_value': results.get('comp_pe_value'),
            'final_equity_value': results.get('final_equity_value'),
            'final_price_per_share': results.get('final_price_per_share'),
        })

    except Exception as e:
        logger.error(f'Error in preview valuation: {e}', exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/valuation/<int:company_id>', methods=['POST'])
def run_valuation(company_id):
    try:
        logger.info(f"Manual valuation requested for company ID {company_id}")

        # Use centralized service
        success, results, error_msg = valuation_service.valuate_company(company_id)

        if success:
            logger.info(f"Valuation completed successfully for company ID {company_id}")
            return jsonify(results)
        else:
            logger.error(f"Valuation failed for company ID {company_id}: {error_msg}")
            return jsonify({'error': error_msg}), 404 if 'not found' in error_msg else 500

    except Exception as e:
        logger.error(f"Unexpected error during valuation for company ID {company_id}: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/valuation/<int:company_id>/details', methods=['GET'])
def get_valuation_details(company_id):
    """
    Get detailed valuation breakdown for a company.

    Returns full calculation details including:
    - DCF: WACC breakdown, 10-year FCF projections, terminal value
    - EV/EBITDA: multiple used, EBITDA, implied EV/equity
    - P/E: multiple used, net income, implied value
    - Blend weights used for final valuation

    This endpoint computes on-demand rather than fetching cached results,
    ensuring the breakdown always reflects current assumptions.
    """
    try:
        logger.info(f"Valuation details requested for company ID {company_id}")

        # Fetch company data
        company_data = valuation_service.fetch_company_data(company_id)
        if not company_data:
            return jsonify({'error': f'Company with ID {company_id} not found'}), 404

        # Run valuation to get full details (don't save to DB)
        results = valuation_service.run_valuation(company_data)
        if not results:
            return jsonify({'error': 'Valuation calculation failed'}), 500

        # Return structured response with details
        return jsonify({
            'company_id': company_id,
            'company_name': results.get('name'),
            'ticker': company_data.get('ticker'),
            'sector': results.get('sector'),
            'summary': {
                'fair_value': results.get('final_price_per_share'),
                'current_price': results.get('current_price'),
                'upside_pct': results.get('upside_pct'),
                'recommendation': results.get('recommendation'),
            },
            'dcf_details': results.get('dcf_details'),
            'ev_ebitda_details': results.get('ev_ebitda_details'),
            'pe_details': results.get('pe_details'),
            'blend_weights': results.get('blend_weights'),
            'risk_metrics': {
                'wacc': results.get('wacc'),
                'z_score': results.get('z_score'),
                'debt_to_equity': results.get('debt_to_equity'),
            },
            'ml_calibration': {
                'sub_sector_tag': results.get('sub_sector_tag'),
                'company_type': results.get('company_type'),
                'ebitda_method': results.get('ebitda_method'),
                'analyst_target': results.get('analyst_target'),
            },
        })

    except Exception as e:
        logger.error(f"Error getting valuation details for company ID {company_id}: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/export/csv', methods=['GET'])
def export_csv():
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute('''SELECT c.name, c.sector, vr.*
                 FROM companies c
                 JOIN valuation_results vr ON c.id = vr.company_id
                 WHERE vr.id IN (
                     SELECT MAX(id) FROM valuation_results GROUP BY company_id
                 )''')
    
    rows = c.fetchall()
    conn.close()
    
    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow([
        'Company', 'Sector', 'DCF Value', 'DCF Price/Share', 'Fair Value',
        'Fair Price/Share', 'Market Cap', 'Current Price', 'Upside %',
        'Recommendation', 'WACC %', 'EV/EBITDA', 'P/E', 'FCF Yield %',
        'ROE %', 'ROIC %', 'Debt/Equity', 'Z-Score'
    ])
    
    # Data
    for row in rows:
        writer.writerow([
            row[0], row[1], row[3], row[4], row[7], row[8], row[9], row[10],
            row[11], row[12], row[13], row[14], row[15], row[16], row[17],
            row[18], row[19], row[20]
        ])
    
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode()),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'valuations_{datetime.now().strftime("%Y%m%d")}.csv'
    )

@app.route('/api/dashboard/stats', methods=['GET'])
def dashboard_stats():
    conn = get_db_connection()
    c = conn.cursor()
    
    # Get portfolio statistics
    c.execute('''SELECT 
        COUNT(DISTINCT c.id) as total_companies,
        AVG(vr.upside_pct) as avg_upside,
        SUM(CASE WHEN vr.recommendation IN ('BUY', 'STRONG BUY') THEN 1 ELSE 0 END) as buy_count,
        SUM(CASE WHEN vr.recommendation = 'HOLD' THEN 1 ELSE 0 END) as hold_count,
        SUM(CASE WHEN vr.recommendation IN ('SELL', 'UNDERWEIGHT') THEN 1 ELSE 0 END) as sell_count,
        AVG(vr.pe_ratio) as avg_pe,
        AVG(vr.roe) as avg_roe,
        SUM(vr.final_equity_value) as total_fair_value,
        SUM(vr.market_cap) as total_market_cap,
        AVG(vr.wacc) as avg_wacc
        FROM companies c
        JOIN valuation_results vr ON c.id = vr.company_id
        WHERE vr.id IN (
            SELECT MAX(id) FROM valuation_results GROUP BY company_id
        )''')
    
    stats = c.fetchone()
    stats = dict_from_row(stats) if stats else {}
    
    # Get sector breakdown with P/E
    c.execute('''SELECT c.sector, COUNT(*), AVG(vr.upside_pct), AVG(vr.roe), AVG(vr.pe_ratio)
                 FROM companies c
                 JOIN valuation_results vr ON c.id = vr.company_id
                 WHERE vr.id IN (
                     SELECT MAX(id) FROM valuation_results GROUP BY company_id
                 )
                 GROUP BY c.sector''')
    
    sectors = c.fetchall()
    conn.close()

    # Normalize stats and sectors for both SQLite (tuples) and PostgreSQL (dicts)
    result = {
        'total_companies': stats.get('total_companies', 0) if isinstance(stats, dict) else (stats or {}).get('total_companies', 0),
        'avg_upside': round(stats.get('avg_upside') or 0 if isinstance(stats, dict) else 0, 2),
        'buy_count': stats.get('buy_count', 0) if isinstance(stats, dict) else 0,
        'hold_count': stats.get('hold_count', 0) if isinstance(stats, dict) else 0,
        'sell_count': stats.get('sell_count', 0) if isinstance(stats, dict) else 0,
        'avg_pe': round(stats.get('avg_pe') or 0 if isinstance(stats, dict) else 0, 1),
        'avg_roe': round(stats.get('avg_roe') or 0 if isinstance(stats, dict) else 0, 1),
        'total_fair_value': stats.get('total_fair_value') or 0 if isinstance(stats, dict) else 0,
        'total_market_cap': stats.get('total_market_cap') or 0 if isinstance(stats, dict) else 0,
        'avg_wacc': round(stats.get('avg_wacc') or 0 if isinstance(stats, dict) else 0, 2),
        'sectors': []
    }

    for s in sectors:
        row = dict_from_row(s) if not isinstance(s, dict) else s
        result['sectors'].append({
            'name': row.get('sector'),
            'count': row.get('count') or 0,
            'avg_upside': round(row.get('avg_upside', 0) or 0, 2),
            'avg_roe': round(row.get('avg_roe', 0) or 0, 1),
            'avg_pe': round(row.get('avg_pe', 0) or 0, 1)
        })

    return jsonify(result)

# ============================================================================
# REAL-TIME PRICE UPDATES & PER-COMPANY SCENARIOS
# ============================================================================

@app.route('/api/prices/realtime', methods=['GET'])
def get_realtime_prices():
    """
    Get current market prices for all portfolio companies
    Called every minute by frontend
    UPDATES THE DATABASE with latest prices from Yahoo Finance
    """
    try:
        price_service = get_price_service()
        # USE UPDATE METHOD - this writes to database
        prices = price_service.update_all_portfolio_prices()

        logger.info(f"Updated {len(prices)} stock prices in real-time")

        return jsonify({
            'success': True,
            'prices': prices,
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Error fetching realtime prices: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/prices/update', methods=['POST'])
def update_portfolio_prices():
    """
    Update database with current market prices
    """
    try:
        price_service = get_price_service()
        updated_prices = price_service.update_all_portfolio_prices()

        return jsonify({
            'success': True,
            'updated': len(updated_prices),
            'prices': updated_prices
        })

    except Exception as e:
        logger.error(f"Error updating prices: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/company/<int:company_id>/scenario/apply', methods=['POST'])
def apply_scenario_to_company(company_id):
    """
    Apply Bear/Base/Bull scenario to a specific company

    POST body: {"scenario_type": "bear"|"base"|"bull"}
    """
    data = request.json
    scenario_type = data.get('scenario_type', 'base').lower()

    if scenario_type not in ['bear', 'base', 'bull']:
        return jsonify({'error': 'Invalid scenario type'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Get current company financials
        cursor.execute("""
            SELECT cf.*, c.name, c.sector
            FROM company_financials cf
            JOIN companies c ON cf.company_id = c.id
            WHERE cf.company_id = %s
            ORDER BY cf.updated_at DESC
            LIMIT 1
        """, (company_id,))

        current = cursor.fetchone()
        if not current:
            return jsonify({'error': 'Company financials not found'}), 404

        # Get or create scenario
        cursor.execute("""
            SELECT s.id, sa.*
            FROM scenarios s
            LEFT JOIN scenario_assumptions sa ON s.id = sa.scenario_id
            WHERE s.company_id = %s AND LOWER(s.name) LIKE %s
            LIMIT 1
        """, (company_id, f'%{scenario_type}%'))

        scenario = cursor.fetchone()

        # Scenario multipliers
        multipliers = {
            'bear': {'growth': 0.75, 'risk_adj': 1.20, 'multiple': 0.75},
            'base': {'growth': 1.00, 'risk_adj': 1.00, 'multiple': 1.00},
            'bull': {'growth': 1.25, 'risk_adj': 0.85, 'multiple': 1.25}
        }

        mult = multipliers[scenario_type]

        # Calculate new assumptions
        new_assumptions = {
            'growth_rate_y1': current['growth_rate_y1'] * mult['growth'],
            'growth_rate_y2': current['growth_rate_y2'] * mult['growth'],
            'growth_rate_y3': current['growth_rate_y3'] * mult['growth'],
            'beta': current['beta'] * mult['risk_adj'],
            'risk_free_rate': current['risk_free_rate'] + (0.015 if scenario_type == 'bear' else -0.01 if scenario_type == 'bull' else 0),
            'market_risk_premium': current['market_risk_premium'] + (0.02 if scenario_type == 'bear' else -0.015 if scenario_type == 'bull' else 0),
            'comparable_ev_ebitda': current['comparable_ev_ebitda'] * mult['multiple'],
            'comparable_pe': current['comparable_pe'] * mult['multiple']
        }

        # Update company financials with new scenario
        cursor.execute("""
            UPDATE company_financials
            SET growth_rate_y1 = %s,
                growth_rate_y2 = %s,
                growth_rate_y3 = %s,
                beta = %s,
                risk_free_rate = %s,
                market_risk_premium = %s,
                comparable_ev_ebitda = %s,
                comparable_pe = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE company_id = %s
        """, (
            new_assumptions['growth_rate_y1'],
            new_assumptions['growth_rate_y2'],
            new_assumptions['growth_rate_y3'],
            new_assumptions['beta'],
            new_assumptions['risk_free_rate'],
            new_assumptions['market_risk_premium'],
            new_assumptions['comparable_ev_ebitda'],
            new_assumptions['comparable_pe'],
            company_id
        ))

        # Create or update scenario record
        if not scenario:
            cursor.execute("""
                INSERT INTO scenarios (company_id, name, description, is_default)
                VALUES (%s, %s, %s, %s)
                RETURNING id
            """, (
                company_id,
                f"{scenario_type.capitalize()} Case",
                f"{scenario_type.capitalize()} market scenario",
                scenario_type == 'base'
            ))
            scenario_id = cursor.fetchone()['id']
        else:
            scenario_id = scenario['id']

        conn.commit()

        return jsonify({
            'success': True,
            'company_id': company_id,
            'scenario_type': scenario_type,
            'scenario_id': scenario_id,
            'assumptions': new_assumptions
        })

    except Exception as e:
        conn.rollback()
        logger.error(f"Error applying scenario to company {company_id}: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    # Use port 5002 to avoid conflict with other applications
    app.run(debug=True, port=5002)
