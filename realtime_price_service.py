"""
Real-time Stock Price Service
Fetches current market prices for portfolio companies
"""

import yfinance as yf
import time
import requests
import logging
from datetime import datetime
from typing import Dict, List, Optional
import psycopg2
from psycopg2.extras import RealDictCursor
from config import Config

logger = logging.getLogger(__name__)

class RealtimePriceService:
    def __init__(self):
        self.conn = None
        # Note: Not using custom session - yfinance handles its own session internally

    def get_connection(self):
        """Get database connection"""
        # Always close and get fresh connection to avoid transaction isolation issues
        if self.conn and not self.conn.closed:
            self.conn.close()

        self.conn = psycopg2.connect(
            Config.get_db_connection_string(),
            cursor_factory=RealDictCursor
        )
        return self.conn

    def get_current_price(self, ticker: str) -> Optional[float]:
        """
        Fetch current stock price from Yahoo Finance

        Args:
            ticker: Stock ticker symbol

        Returns:
            Current price or None if error
        """
        try:
            # Fetch closing price - no delay needed for daily updates
            stock = yf.Ticker(ticker)
            data = stock.history(period='1d')

            if data.empty:
                # Fallback to info if history fails
                info = stock.info
                return info.get('currentPrice') or info.get('regularMarketPrice')

            # Get most recent price
            current_price = data['Close'].iloc[-1]
            return float(current_price)

        except Exception as e:
            logger.error(f"Error fetching price for {ticker}: {e}")
            return None

    def update_all_portfolio_prices(self) -> List[Dict]:
        """
        Update prices for all companies in portfolio

        Returns:
            List of updated company prices
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # Get all companies with tickers
            cursor.execute("""
                SELECT c.id, c.name, c.ticker,
                       cf.market_cap_estimate as market_cap, cf.shares_outstanding
                FROM companies c
                LEFT JOIN company_financials cf ON c.id = cf.company_id
                WHERE c.ticker IS NOT NULL AND c.ticker != ''
                ORDER BY c.name
            """)

            companies = cursor.fetchall()
            logger.info(f"Found {len(companies)} companies with tickers in database")
            if len(companies) == 0:
                logger.warning("No companies with tickers found! Check database.")
            for comp in companies:
                logger.info(f"  - {comp['name']} ({comp['ticker']})")

            updated_prices = []

            for company in companies:
                ticker = company['ticker']
                current_price = self.get_current_price(ticker)

                if current_price:
                    # Update market cap based on current price
                    new_market_cap = company.get('market_cap', 0)
                    if company.get('shares_outstanding'):
                        new_market_cap = current_price * company['shares_outstanding']

                        # Update company_financials
                        cursor.execute("""
                            UPDATE company_financials
                            SET market_cap_estimate = %s
                            WHERE company_id = %s
                        """, (new_market_cap, company['id']))

                        # ALSO update valuation_results current_price and market_cap
                        # so the UI shows the updated price immediately
                        cursor.execute("""
                            UPDATE valuation_results
                            SET current_price = %s,
                                market_cap = %s
                            WHERE company_id = %s
                            AND id = (SELECT MAX(id) FROM valuation_results WHERE company_id = %s)
                        """, (current_price, new_market_cap, company['id'], company['id']))

                    updated_prices.append({
                        'company_id': company['id'],
                        'ticker': ticker,
                        'name': company['name'],
                        'current_price': current_price,
                        'market_cap': new_market_cap,
                        'updated_at': datetime.now().isoformat()
                    })

            conn.commit()
            return updated_prices

        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()

    def get_portfolio_prices(self) -> List[Dict]:
        """
        Get current prices for all portfolio companies without updating DB

        Returns:
            List of company prices
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT c.id, c.name, c.ticker,
                       cf.market_cap_estimate as market_cap, cf.shares_outstanding
                FROM companies c
                LEFT JOIN company_financials cf ON c.id = cf.company_id
                WHERE c.ticker IS NOT NULL AND c.ticker != ''
                ORDER BY c.name
            """)

            companies = cursor.fetchall()
            prices = []

            for company in companies:
                ticker = company['ticker']
                current_price = self.get_current_price(ticker)

                if current_price:
                    market_cap = company.get('market_cap', 0)
                    if company.get('shares_outstanding'):
                        market_cap = current_price * company['shares_outstanding']

                    prices.append({
                        'company_id': company['id'],
                        'ticker': ticker,
                        'name': company['name'],
                        'current_price': current_price,
                        'market_cap': market_cap,
                        'timestamp': datetime.now().isoformat()
                    })

            return prices

        finally:
            cursor.close()

    def __del__(self):
        """Clean up database connection"""
        if self.conn and not self.conn.closed:
            self.conn.close()

# Singleton instance
_price_service = None

def get_price_service():
    """Get singleton price service instance"""
    global _price_service
    if _price_service is None:
        _price_service = RealtimePriceService()
    return _price_service
