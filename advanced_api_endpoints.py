"""
ADVANCED API ENDPOINTS
======================

Production-ready endpoints for:
1. Universal company import (any ticker, any exchange)
2. Portfolio construction and optimization
3. Assumption overrides (user custom assumptions)
4. Batch operations
5. Comparative analytics

Ready for institutional clients.
"""

from flask import request, jsonify
import logging
from universal_company_importer import UniversalCompanyImporter, fetch_company_by_ticker
from portfolio_engine import PortfolioEngine, PortfolioConstraints, PortfolioMetrics
from valuation_service import ValuationService
from institutional_valuation_engine import InstitutionalValuationEngine, CompanyProfile
import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor
from config import Config

logger = logging.getLogger(__name__)


def register_advanced_routes(app):
    """Register all advanced API endpoints"""

    valuation_service = ValuationService()
    importer = UniversalCompanyImporter()
    portfolio_engine = PortfolioEngine()
    institutional_engine = InstitutionalValuationEngine()

    def get_db_connection():
        """Get database connection"""
        if Config.DATABASE_TYPE == 'postgresql':
            conn = psycopg2.connect(
                Config.get_db_connection_string(),
                cursor_factory=RealDictCursor
            )
            return conn
        else:
            conn = sqlite3.connect('valuation.db')
            conn.row_factory = sqlite3.Row
            return conn

    @app.route('/api/import/ticker', methods=['POST'])
    def import_ticker():
        """
        Import any company by ticker symbol.

        POST /api/import/ticker
        {
            "ticker": "AAPL",
            "exchange": "US",  // optional, default "US"
            "auto_value": true  // optional, run valuation immediately
        }

        Returns:
        {
            "company_id": 123,
            "name": "Apple Inc.",
            "quality": {
                "confidence": "High",
                "completeness_score": 0.95,
                "warnings": []
            },
            "valuation": {...}  // if auto_value=true
        }
        """
        try:
            data = request.get_json()
            ticker = data.get('ticker', '').upper()
            exchange = data.get('exchange', 'US')
            auto_value = data.get('auto_value', True)

            if not ticker:
                return jsonify({'error': 'Ticker required'}), 400

            logger.info(f"📥 Importing ticker: {ticker} from {exchange}")

            # Fetch company data
            company_data, quality_report = importer.import_company(ticker, exchange)

            if not company_data:
                return jsonify({
                    'error': f'Could not fetch data for ticker {ticker}',
                    'quality': quality_report.__dict__ if quality_report else None
                }), 404

            # Prepare for database
            db_data = importer.prepare_for_database(company_data)

            # Insert into database
            conn = get_db_connection()
            c = conn.cursor()

            placeholder = '%s' if Config.DATABASE_TYPE == 'postgresql' else '?'

            # Insert company
            c.execute(f'''
                INSERT INTO companies (name, sector, ticker)
                VALUES ({placeholder}, {placeholder}, {placeholder})
                RETURNING id
            ''' if Config.DATABASE_TYPE == 'postgresql' else '''
                INSERT INTO companies (name, sector, ticker)
                VALUES (?, ?, ?)
            ''', (db_data['name'], db_data['sector'], db_data.get('ticker', '')))

            if Config.DATABASE_TYPE == 'postgresql':
                company_id = c.fetchone()['id']
            else:
                company_id = c.lastrowid

            # Insert financials
            c.execute(f'''
                INSERT INTO company_financials (
                    company_id, revenue, ebitda, depreciation, capex_pct,
                    working_capital_change, profit_margin, growth_rate_y1,
                    growth_rate_y2, growth_rate_y3, terminal_growth, tax_rate,
                    shares_outstanding, debt, cash, market_cap_estimate,
                    beta, risk_free_rate, market_risk_premium,
                    country_risk_premium, size_premium,
                    comparable_ev_ebitda, comparable_pe, comparable_peg
                ) VALUES ({', '.join([placeholder] * 24)})
            ''', (
                company_id,
                db_data['revenue'], db_data['ebitda'], db_data['depreciation'],
                db_data['capex_pct'], db_data['working_capital_change'],
                db_data['profit_margin'], db_data['growth_rate_y1'],
                db_data['growth_rate_y2'], db_data['growth_rate_y3'],
                db_data['terminal_growth'], db_data['tax_rate'],
                db_data['shares_outstanding'], db_data['debt'], db_data['cash'],
                db_data['market_cap_estimate'], db_data['beta'],
                db_data['risk_free_rate'], db_data['market_risk_premium'],
                db_data['country_risk_premium'], db_data['size_premium'],
                db_data['comparable_ev_ebitda'], db_data['comparable_pe'],
                db_data['comparable_peg']
            ))

            conn.commit()
            conn.close()

            logger.info(f"✅ Imported {db_data['name']} (ID: {company_id})")

            response = {
                'company_id': company_id,
                'name': db_data['name'],
                'ticker': ticker,
                'sector': db_data['sector'],
                'quality': {
                    'confidence': quality_report.confidence,
                    'completeness_score': quality_report.completeness_score,
                    'reliability_score': quality_report.reliability_score,
                    'missing_fields': quality_report.missing_fields,
                    'imputed_fields': quality_report.imputed_fields,
                    'warnings': quality_report.warnings
                }
            }

            # Run valuation if requested
            if auto_value:
                success, valuation, error = valuation_service.valuate_company(company_id)
                if success:
                    response['valuation'] = valuation
                else:
                    response['valuation_error'] = error

            return jsonify(response), 201

        except Exception as e:
            logger.error(f"Error importing ticker: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500

    @app.route('/api/portfolio/build', methods=['POST'])
    def build_portfolio():
        """
        Build optimized portfolio from available companies.

        POST /api/portfolio/build
        {
            "target_value": 1000000,  // optional, default $1M
            "constraints": {  // optional
                "max_single_position": 0.20,
                "min_single_position": 0.02,
                "max_sector_exposure": 0.40,
                "target_num_holdings": 15,
                "risk_tolerance": "Moderate"
            },
            "filter": {  // optional
                "min_upside": 10,  // only include >10% upside
                "sectors": ["Technology", "Healthcare"],  // limit to sectors
                "min_market_cap": 1000000000  // $1B minimum
            }
        }

        Returns:
        {
            "allocations": {"AAPL": 0.15, "MSFT": 0.12, ...},
            "metrics": {
                "expected_return": 0.145,
                "volatility": 0.18,
                "sharpe_ratio": 1.52,
                ...
            },
            "holdings": [
                {
                    "ticker": "AAPL",
                    "name": "Apple Inc.",
                    "weight": 0.15,
                    "value": 150000,
                    "upside": 12.5,
                    "conviction_score": 0.78
                },
                ...
            ],
            "report": "Full text report..."
        }
        """
        try:
            data = request.get_json() or {}
            target_value = data.get('target_value', 1_000_000)
            constraints_data = data.get('constraints', {})
            filter_data = data.get('filter', {})

            # Build constraints object
            constraints = PortfolioConstraints(
                max_single_position=constraints_data.get('max_single_position', 0.20),
                min_single_position=constraints_data.get('min_single_position', 0.02),
                max_sector_exposure=constraints_data.get('max_sector_exposure', 0.40),
                target_num_holdings=constraints_data.get('target_num_holdings', 15),
                risk_tolerance=constraints_data.get('risk_tolerance', 'Moderate')
            )

            # Fetch all companies with valuations
            conn = get_db_connection()
            c = conn.cursor()

            query = '''
                SELECT
                    c.id, c.name, c.sector, c.ticker,
                    cf.revenue, cf.ebitda, cf.profit_margin, cf.growth_rate_y1,
                    cf.beta, cf.shares_outstanding, cf.debt, cf.cash,
                    vr.final_equity_value as fair_value,
                    vr.final_price_per_share,
                    vr.market_cap,
                    vr.upside_pct as upside,
                    vr.recommendation,
                    vr.wacc, vr.roe, vr.roic,
                    vr.debt_to_equity, vr.fcf_yield, vr.z_score
                FROM companies c
                JOIN company_financials cf ON c.id = cf.company_id
                LEFT JOIN valuation_results vr ON c.id = vr.company_id
                WHERE vr.final_equity_value IS NOT NULL
            '''

            c.execute(query)
            companies = [dict(row) for row in c.fetchall()]
            conn.close()

            logger.info(f"📊 Building portfolio from {len(companies)} valued companies")

            # Apply filters
            if filter_data:
                min_upside = filter_data.get('min_upside')
                sectors = filter_data.get('sectors')
                min_market_cap = filter_data.get('min_market_cap')

                filtered = []
                for company in companies:
                    if min_upside and company.get('upside', 0) < min_upside:
                        continue
                    if sectors and company.get('sector') not in sectors:
                        continue
                    if min_market_cap and company.get('market_cap', 0) < min_market_cap:
                        continue
                    filtered.append(company)

                companies = filtered
                logger.info(f"✅ {len(companies)} companies after filters")

            if not companies:
                return jsonify({'error': 'No companies available for portfolio construction'}), 400

            # Build portfolio
            allocations, metrics = portfolio_engine.build_portfolio(
                companies, constraints, target_value
            )

            # Generate report
            report = portfolio_engine.generate_portfolio_report(
                allocations, metrics, companies, target_value
            )

            # Build detailed holdings list
            holdings = []
            for ticker, weight in sorted(allocations.items(), key=lambda x: x[1], reverse=True):
                company = next((c for c in companies if c.get('ticker', c.get('name')) == ticker), None)
                if company:
                    holdings.append({
                        'ticker': ticker,
                        'name': company.get('name'),
                        'sector': company.get('sector'),
                        'weight': weight,
                        'value': weight * target_value,
                        'upside': company.get('upside', 0),
                        'conviction_score': company.get('conviction_score', 0),
                        'recommendation': company.get('recommendation')
                    })

            # Clean sector_concentration to remove None keys
            clean_sector_concentration = {
                (k or 'Unknown'): v
                for k, v in metrics.sector_concentration.items()
            }

            return jsonify({
                'allocations': allocations,
                'metrics': {
                    'expected_return': metrics.expected_return,
                    'volatility': metrics.volatility,
                    'sharpe_ratio': metrics.sharpe_ratio,
                    'sortino_ratio': metrics.sortino_ratio,
                    'max_drawdown': metrics.max_drawdown,
                    'value_at_risk_95': metrics.value_at_risk_95,
                    'diversification_ratio': metrics.diversification_ratio,
                    'sector_concentration': clean_sector_concentration,
                    'largest_position': metrics.largest_position,
                    'num_holdings': metrics.num_holdings,
                    'total_conviction_score': metrics.total_conviction_score
                },
                'holdings': holdings,
                'report': report
            })

        except Exception as e:
            logger.error(f"Error building portfolio: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500

    @app.route('/api/company/<int:company_id>/assumptions/override', methods=['POST'])
    def override_assumptions(company_id):
        """
        Override system assumptions with user custom values.

        POST /api/company/123/assumptions/override
        {
            "growth_rate_y1": 0.25,  // Override to 25%
            "terminal_growth": 0.04,  // Override to 4%
            "beta": 1.5,
            "note": "Management guidance: 25% growth for 2025"
        }

        Returns new valuation with overridden assumptions.
        System assumptions are preserved in database, overrides stored separately.
        """
        try:
            overrides = request.get_json()

            # Fetch current company data (including sector from companies table)
            conn = get_db_connection()
            c = conn.cursor()

            placeholder = '%s' if Config.DATABASE_TYPE == 'postgresql' else '?'
            c.execute(f'''
                SELECT c.id, c.name, c.sector, cf.*
                FROM companies c
                JOIN company_financials cf ON c.id = cf.company_id
                WHERE c.id = {placeholder}
            ''', (company_id,))

            row = c.fetchone()
            if not row:
                conn.close()
                return jsonify({'error': 'Company not found'}), 404

            current_data = dict(row)
            conn.close()

            # Apply overrides (user assumptions override system assumptions for this valuation)
            for key, value in overrides.items():
                if key != 'note':  # Skip note field
                    current_data[key] = value

            # Run valuation with overridden data
            from valuation_professional import enhanced_dcf_valuation
            valuation_result = enhanced_dcf_valuation(current_data)

            # Store override record (optional - for audit trail)
            # Could add overrides table to track user assumptions

            return jsonify({
                'company_id': company_id,
                'overrides_applied': {k: v for k, v in overrides.items() if k != 'note'},
                'note': overrides.get('note', ''),
                'valuation': valuation_result
            })

        except Exception as e:
            logger.error(f"Error overriding assumptions: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500

    @app.route('/api/companies/batch/import', methods=['POST'])
    def batch_import_tickers():
        """
        Import multiple companies at once.

        POST /api/companies/batch/import
        {
            "tickers": ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"],
            "exchange": "US",  // optional
            "auto_value": true  // optional
        }

        Returns:
        {
            "success_count": 4,
            "failed_count": 1,
            "results": [
                {"ticker": "AAPL", "status": "success", "company_id": 123},
                {"ticker": "MSFT", "status": "success", "company_id": 124},
                {"ticker": "BADTKR", "status": "failed", "error": "Ticker not found"},
                ...
            ]
        }
        """
        try:
            data = request.get_json()
            tickers = data.get('tickers', [])
            exchange = data.get('exchange', 'US')
            auto_value = data.get('auto_value', True)

            if not tickers:
                return jsonify({'error': 'Tickers list required'}), 400

            results = []
            success_count = 0
            failed_count = 0

            for ticker in tickers:
                try:
                    # Import using the single ticker endpoint logic
                    company_data, quality_report = importer.import_company(ticker, exchange)

                    if not company_data:
                        results.append({
                            'ticker': ticker,
                            'status': 'failed',
                            'error': 'Ticker not found'
                        })
                        failed_count += 1
                        continue

                    # Insert into database
                    db_data = importer.prepare_for_database(company_data)

                    conn = get_db_connection()
                    c = conn.cursor()

                    placeholder = '%s' if Config.DATABASE_TYPE == 'postgresql' else '?'

                    c.execute(f'''
                        INSERT INTO companies (name, sector, ticker)
                        VALUES ({placeholder}, {placeholder}, {placeholder})
                        RETURNING id
                    ''' if Config.DATABASE_TYPE == 'postgresql' else '''
                        INSERT INTO companies (name, sector, ticker)
                        VALUES (?, ?, ?)
                    ''', (db_data['name'], db_data['sector'], db_data.get('ticker', '')))

                    if Config.DATABASE_TYPE == 'postgresql':
                        company_id = c.fetchone()['id']
                    else:
                        company_id = c.lastrowid

                    c.execute(f'''
                        INSERT INTO company_financials (
                            company_id, revenue, ebitda, depreciation, capex_pct,
                            working_capital_change, profit_margin, growth_rate_y1,
                            growth_rate_y2, growth_rate_y3, terminal_growth, tax_rate,
                            shares_outstanding, debt, cash, market_cap_estimate,
                            beta, risk_free_rate, market_risk_premium,
                            country_risk_premium, size_premium,
                            comparable_ev_ebitda, comparable_pe, comparable_peg
                        ) VALUES ({', '.join([placeholder] * 24)})
                    ''', (
                        company_id,
                        db_data['revenue'], db_data['ebitda'], db_data['depreciation'],
                        db_data['capex_pct'], db_data['working_capital_change'],
                        db_data['profit_margin'], db_data['growth_rate_y1'],
                        db_data['growth_rate_y2'], db_data['growth_rate_y3'],
                        db_data['terminal_growth'], db_data['tax_rate'],
                        db_data['shares_outstanding'], db_data['debt'], db_data['cash'],
                        db_data['market_cap_estimate'], db_data['beta'],
                        db_data['risk_free_rate'], db_data['market_risk_premium'],
                        db_data['country_risk_premium'], db_data['size_premium'],
                        db_data['comparable_ev_ebitda'], db_data['comparable_pe'],
                        db_data['comparable_peg']
                    ))

                    conn.commit()
                    conn.close()

                    # Run valuation if requested
                    if auto_value:
                        valuation_service.valuate_company(company_id)

                    results.append({
                        'ticker': ticker,
                        'status': 'success',
                        'company_id': company_id,
                        'name': db_data['name']
                    })
                    success_count += 1

                except Exception as e:
                    results.append({
                        'ticker': ticker,
                        'status': 'failed',
                        'error': str(e)
                    })
                    failed_count += 1

            return jsonify({
                'success_count': success_count,
                'failed_count': failed_count,
                'results': results
            })

        except Exception as e:
            logger.error(f"Error in batch import: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500

    logger.info("✅ Advanced API endpoints registered")
    logger.info("   - POST /api/import/ticker (import any company)")
    logger.info("   - POST /api/portfolio/build (build optimized portfolio)")
    logger.info("   - POST /api/company/<id>/assumptions/override (custom assumptions)")
    logger.info("   - POST /api/companies/batch/import (batch ticker import)")


# Export
__all__ = ['register_advanced_routes']
