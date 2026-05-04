"""
Centralized valuation service.
Single source of truth for all valuation operations.
"""

import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor
import logging
from typing import Dict, Optional, List, Tuple
from datetime import datetime
from valuation_professional import enhanced_dcf_valuation
from config import Config

# Configure logging
logger = logging.getLogger(__name__)


class ValuationService:
    """
    Service class handling all valuation operations.
    Eliminates code duplication between app.py and run_valuations.py.
    """

    def __init__(self, db_path: str = 'valuations.db'):
        self.db_path = db_path
        logger.info(f"Initialized ValuationService with database: {db_path}")

    def get_connection(self):
        """Get database connection (PostgreSQL or SQLite)"""
        if Config.DATABASE_TYPE == 'postgresql':
            conn = psycopg2.connect(
                Config.get_db_connection_string(),
                cursor_factory=RealDictCursor
            )
            return conn
        else:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            return conn
    
    def fetch_company_data(self, company_id: int) -> Optional[Dict]:
        """
        Fetch complete company and financial data for a single company.
        
        Args:
            company_id: The company ID to fetch
            
        Returns:
            Dictionary with all company and financial data, or None if not found
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Join companies and company_financials
            placeholder = '%s' if Config.DATABASE_TYPE == 'postgresql' else '?'
            cursor.execute(f'''
                SELECT
                    c.id, c.name, c.sector, c.ticker, c.industry,
                    cf.revenue, cf.ebitda, cf.depreciation,
                    cf.capex_pct, cf.working_capital_change, cf.profit_margin,
                    cf.growth_rate_y1, cf.growth_rate_y2, cf.growth_rate_y3,
                    cf.terminal_growth, cf.tax_rate,
                    cf.shares_outstanding, cf.debt, cf.cash, cf.market_cap_estimate,
                    cf.beta, cf.risk_free_rate, cf.market_risk_premium,
                    cf.country_risk_premium, cf.size_premium,
                    cf.comparable_ev_ebitda, cf.comparable_pe, cf.comparable_peg
                FROM companies c
                JOIN company_financials cf ON c.id = cf.company_id
                WHERE c.id = {placeholder}
            ''', (company_id,))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                logger.info(f"Fetched data for company ID {company_id}: {row['name']}")
                return dict(row)
            else:
                logger.warning(f"No data found for company ID {company_id}")
                return None
                
        except Exception as e:
            logger.error(f"Error fetching company data for ID {company_id}: {str(e)}")
            return None
    
    def fetch_all_companies(self) -> List[Dict]:
        """
        Fetch all companies with their financial data.
        
        Returns:
            List of dictionaries containing company and financial data
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT
                    c.id, c.name, c.sector, c.ticker, c.industry,
                    cf.revenue, cf.ebitda, cf.depreciation,
                    cf.capex_pct, cf.working_capital_change, cf.profit_margin,
                    cf.growth_rate_y1, cf.growth_rate_y2, cf.growth_rate_y3,
                    cf.terminal_growth, cf.tax_rate,
                    cf.shares_outstanding, cf.debt, cf.cash, cf.market_cap_estimate,
                    cf.beta, cf.risk_free_rate, cf.market_risk_premium,
                    cf.country_risk_premium, cf.size_premium,
                    cf.comparable_ev_ebitda, cf.comparable_pe, cf.comparable_peg
                FROM companies c
                JOIN company_financials cf ON c.id = cf.company_id
                ORDER BY c.name
            ''')
            
            companies = [dict(row) for row in cursor.fetchall()]
            conn.close()
            
            logger.info(f"Fetched {len(companies)} companies from database")
            return companies
            
        except Exception as e:
            logger.error(f"Error fetching all companies: {str(e)}")
            return []
    
    def run_valuation(self, company_data: Dict) -> Optional[Dict]:
        """
        Run enhanced DCF valuation for a company.
        
        Args:
            company_data: Dictionary containing all required financial data
            
        Returns:
            Dictionary with valuation results, or None if valuation fails
        """
        try:
            company_id = company_data.get('id')
            company_name = company_data.get('name', 'Unknown')
            
            logger.info(f"Starting valuation for {company_name} (ID: {company_id})")
            
            # Run the enhanced DCF valuation
            result = enhanced_dcf_valuation(company_data)
            
            if result:
                logger.info(f"Valuation completed for {company_name}: "
                          f"Fair Value ${result['final_equity_value']:,.0f}, "
                          f"Recommendation: {result['recommendation']}")

                # Append institutional quality/complexity score (non-blocking)
                try:
                    from axiom_api_endpoints import compute_institutional_score
                    inst = compute_institutional_score(company_data)
                    result['institutional_score'] = inst
                except Exception as inst_err:
                    logger.debug(f"Institutional score skipped: {inst_err}")

                return result
            else:
                logger.error(f"Valuation returned None for {company_name}")
                return None
                
        except Exception as e:
            company_name = company_data.get('name', 'Unknown')
            logger.error(f"Error running valuation for {company_name}: {str(e)}", exc_info=True)
            return None
    
    def save_valuation_results(self, company_id: int, results: Dict) -> bool:
        """
        Save valuation results to database.
        
        Args:
            company_id: The company ID
            results: Dictionary containing valuation results
            
        Returns:
            True if successful, False otherwise
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Insert valuation results
            placeholder = '%s' if Config.DATABASE_TYPE == 'postgresql' else '?'
            placeholders = ', '.join([placeholder] * 25)
            cursor.execute(f'''
                INSERT INTO valuation_results (
                    company_id, dcf_equity_value, dcf_price_per_share, comp_ev_value,
                    comp_pe_value, final_equity_value, final_price_per_share, market_cap,
                    current_price, upside_pct, recommendation, wacc, ev_ebitda, pe_ratio,
                    fcf_yield, roe, roic, debt_to_equity, z_score, mc_p10, mc_p90,
                    sub_sector_tag, company_type, ebitda_method, analyst_target
                ) VALUES ({placeholders})
            ''', (
                company_id,
                results['dcf_equity_value'],
                results['dcf_price_per_share'],
                results['comp_ev_value'],
                results['comp_pe_value'],
                results['final_equity_value'],
                results['final_price_per_share'],
                results['market_cap'],
                results['current_price'],
                results['upside_pct'],
                results['recommendation'],
                results['wacc'],
                results['ev_ebitda'],
                results['pe_ratio'],
                results['fcf_yield'],
                results.get('roe'),
                results.get('roic'),
                results.get('debt_to_equity'),
                results.get('z_score'),
                results.get('mc_p10'),
                results.get('mc_p90'),
                results.get('sub_sector_tag'),
                results.get('company_type'),
                results.get('ebitda_method'),
                results.get('analyst_target')
            ))
            
            conn.commit()
            conn.close()
            
            logger.info(f"Saved valuation results for company ID {company_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving valuation results for company ID {company_id}: {str(e)}")
            return False
    
    def valuate_company(self, company_id: int) -> Tuple[bool, Optional[Dict], Optional[str]]:
        """
        Complete valuation workflow for a single company.
        Fetches data, runs valuation, saves results.
        
        Args:
            company_id: The company ID to valuate
            
        Returns:
            Tuple of (success: bool, results: Dict or None, error_message: str or None)
        """
        # Fetch company data
        company_data = self.fetch_company_data(company_id)
        if not company_data:
            error_msg = f"Company with ID {company_id} not found"
            logger.error(error_msg)
            return False, None, error_msg
        
        # Run valuation
        results = self.run_valuation(company_data)
        if not results:
            error_msg = f"Valuation failed for {company_data.get('name')}"
            logger.error(error_msg)
            return False, None, error_msg
        
        # Save results
        save_success = self.save_valuation_results(company_id, results)
        if not save_success:
            error_msg = f"Failed to save valuation results for {company_data.get('name')}"
            logger.error(error_msg)
            return False, results, error_msg
        
        logger.info(f"Complete valuation workflow successful for {company_data.get('name')}")
        return True, results, None
    
    def batch_valuate_all(self) -> Dict[str, any]:
        """
        Run valuations for all companies in database.
        
        Returns:
            Dictionary with summary statistics: {
                'total': int,
                'successful': int,
                'failed': int,
                'results': List[Dict],
                'errors': List[Dict]
            }
        """
        logger.info("Starting batch valuation for all companies")
        
        companies = self.fetch_all_companies()
        
        summary = {
            'total': len(companies),
            'successful': 0,
            'failed': 0,
            'results': [],
            'errors': []
        }
        
        for company in companies:
            company_id = company['id']
            company_name = company['name']
            
            success, results, error_msg = self.valuate_company(company_id)
            
            if success:
                summary['successful'] += 1
                summary['results'].append({
                    'company_id': company_id,
                    'company_name': company_name,
                    'recommendation': results['recommendation'],
                    'fair_value': results['final_equity_value']
                })
            else:
                summary['failed'] += 1
                summary['errors'].append({
                    'company_id': company_id,
                    'company_name': company_name,
                    'error': error_msg
                })
        
        logger.info(f"Batch valuation complete: {summary['successful']}/{summary['total']} successful")
        return summary
    
    def get_latest_valuation(self, company_id: int) -> Optional[Dict]:
        """
        Fetch the most recent valuation results for a company.
        
        Args:
            company_id: The company ID
            
        Returns:
            Dictionary with valuation results, or None if not found
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            placeholder = '%s' if Config.DATABASE_TYPE == 'postgresql' else '?'
            cursor.execute(f'''
                SELECT * FROM valuation_results
                WHERE company_id = {placeholder}
                ORDER BY id DESC
                LIMIT 1
            ''', (company_id,))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return dict(row)
            return None
            
        except Exception as e:
            logger.error(f"Error fetching latest valuation for company ID {company_id}: {str(e)}")
            return None
    
    def check_valuation_staleness(self, company_id: int, updated_at: str) -> bool:
        """
        Check if valuation is stale (older than last company update).
        
        Args:
            company_id: The company ID
            updated_at: Company's last updated timestamp
            
        Returns:
            True if valuation is stale (needs recalculation), False otherwise
        """
        latest_valuation = self.get_latest_valuation(company_id)
        
        if not latest_valuation:
            logger.info(f"No valuation found for company ID {company_id} - marked as stale")
            return True
        
        valuation_date = latest_valuation.get('valuation_date', '') or latest_valuation.get('created_at', '')
        
        # Compare timestamps
        if valuation_date < updated_at:
            logger.info(f"Valuation for company ID {company_id} is stale "
                       f"(valuation: {valuation_date}, update: {updated_at})")
            return True
        
        return False
