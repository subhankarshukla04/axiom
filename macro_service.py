"""
Macro Assumptions Service
Manages macro-economic environments (Bear/Base/Bull) and sector multiples
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from config import Config
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class MacroService:
    """Service for managing macro-economic assumptions"""

    def __init__(self, db_connection_string: str = None):
        self.db_connection_string = db_connection_string or Config.get_db_connection_string()

    def get_connection(self):
        """Get database connection — SQLite on Vercel, PostgreSQL elsewhere."""
        if Config.DATABASE_TYPE != 'postgresql':
            import sqlite3
            conn = sqlite3.connect(Config.SQLITE_DB)
            conn.row_factory = sqlite3.Row
            return conn
        return psycopg2.connect(
            self.db_connection_string,
            cursor_factory=RealDictCursor
        )

    def create_macro_environment(
        self,
        name: str,
        description: str,
        assumptions: Dict,
        created_by: int
    ) -> Optional[int]:
        """
        Create a new macro environment

        Args:
            name: Environment name (e.g., 'Recession 2024')
            description: Description
            assumptions: Dictionary of macro assumptions
            created_by: User ID

        Returns:
            macro_id if successful, None otherwise
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO macro_assumptions (
                    name, description, risk_free_rate, market_risk_premium,
                    gdp_growth, inflation_rate, credit_spread_aaa, credit_spread_aa,
                    credit_spread_a, credit_spread_bbb, credit_spread_bb, credit_spread_b,
                    corporate_tax_rate, equity_risk_appetite, created_by
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                name, description,
                assumptions.get('risk_free_rate', 0.045),
                assumptions.get('market_risk_premium', 0.065),
                assumptions.get('gdp_growth', 0.025),
                assumptions.get('inflation_rate', 0.030),
                assumptions.get('credit_spread_aaa', 0.005),
                assumptions.get('credit_spread_aa', 0.0075),
                assumptions.get('credit_spread_a', 0.0125),
                assumptions.get('credit_spread_bbb', 0.020),
                assumptions.get('credit_spread_bb', 0.035),
                assumptions.get('credit_spread_b', 0.050),
                assumptions.get('corporate_tax_rate', 0.21),
                assumptions.get('equity_risk_appetite', 1.0),
                created_by
            ))

            macro_id = cursor.fetchone()['id']
            conn.commit()

            logger.info(f"Created macro environment {macro_id}: {name}")
            return macro_id

        except Exception as e:
            conn.rollback()
            logger.error(f"Error creating macro environment: {e}")
            return None

        finally:
            cursor.close()
            conn.close()

    def get_all_macro_environments(self) -> List[Dict]:
        """
        Get all macro environments

        Returns:
            List of macro environment dictionaries
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT
                    id, name, description, risk_free_rate, market_risk_premium,
                    gdp_growth, inflation_rate, credit_spread_aaa, credit_spread_aa,
                    credit_spread_a, credit_spread_bbb, credit_spread_bb, credit_spread_b,
                    corporate_tax_rate, equity_risk_appetite, is_active,
                    created_by, created_at, updated_at, version
                FROM macro_assumptions
                ORDER BY is_active DESC, name ASC
            """)

            environments = cursor.fetchall()
            return [dict(env) for env in environments]

        except Exception as e:
            logger.error(f"Error fetching macro environments: {e}")
            return []

        finally:
            cursor.close()
            conn.close()

    def get_macro_environment_by_id(self, macro_id: int) -> Optional[Dict]:
        """
        Get a specific macro environment

        Args:
            macro_id: Macro environment ID

        Returns:
            Macro environment dictionary or None
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT
                    id, name, description, risk_free_rate, market_risk_premium,
                    gdp_growth, inflation_rate, credit_spread_aaa, credit_spread_aa,
                    credit_spread_a, credit_spread_bbb, credit_spread_bb, credit_spread_b,
                    corporate_tax_rate, equity_risk_appetite, is_active,
                    created_by, created_at, updated_at, version
                FROM macro_assumptions
                WHERE id = %s
            """, (macro_id,))

            result = cursor.fetchone()
            return dict(result) if result else None

        except Exception as e:
            logger.error(f"Error fetching macro environment {macro_id}: {e}")
            return None

        finally:
            cursor.close()
            conn.close()

    def get_active_macro_environment(self) -> Optional[Dict]:
        """
        Get the currently active macro environment

        Returns:
            Active macro environment dictionary or None
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT
                    id, name, description, risk_free_rate, market_risk_premium,
                    gdp_growth, inflation_rate, credit_spread_aaa, credit_spread_aa,
                    credit_spread_a, credit_spread_bbb, credit_spread_bb, credit_spread_b,
                    corporate_tax_rate, equity_risk_appetite, is_active,
                    created_by, created_at, updated_at, version
                FROM macro_assumptions
                WHERE is_active = TRUE
                LIMIT 1
            """)

            result = cursor.fetchone()
            return dict(result) if result else None

        except Exception as e:
            logger.error(f"Error fetching active macro environment: {e}")
            return None

        finally:
            cursor.close()
            conn.close()

    def activate_macro_environment(self, macro_id: int) -> bool:
        """
        Set a macro environment as active

        Args:
            macro_id: Macro environment ID to activate

        Returns:
            True if successful, False otherwise
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # Verify macro environment exists
            cursor.execute("SELECT id FROM macro_assumptions WHERE id = %s", (macro_id,))
            if not cursor.fetchone():
                logger.error(f"Macro environment {macro_id} not found")
                return False

            # Deactivate all others
            cursor.execute("UPDATE macro_assumptions SET is_active = FALSE")

            # Activate selected one
            cursor.execute("""
                UPDATE macro_assumptions
                SET is_active = TRUE, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (macro_id,))

            conn.commit()
            logger.info(f"Activated macro environment {macro_id}")
            return True

        except Exception as e:
            conn.rollback()
            logger.error(f"Error activating macro environment: {e}")
            return False

        finally:
            cursor.close()
            conn.close()

    def update_macro_assumptions(
        self,
        macro_id: int,
        assumptions: Dict,
        changed_by: int
    ) -> bool:
        """
        Update macro assumptions

        Args:
            macro_id: Macro environment ID
            assumptions: Dictionary of fields to update
            changed_by: User ID making the change

        Returns:
            True if successful, False otherwise
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # Check if macro environment exists
            cursor.execute("SELECT id FROM macro_assumptions WHERE id = %s", (macro_id,))
            if not cursor.fetchone():
                logger.error(f"Macro environment {macro_id} not found")
                return False

            # Build update query
            set_clauses = []
            values = []

            for field, value in assumptions.items():
                set_clauses.append(f"{field} = %s")
                values.append(value)

            set_clauses.append("updated_at = CURRENT_TIMESTAMP")
            set_clauses.append("version = version + 1")
            values.append(macro_id)

            query = f"""
                UPDATE macro_assumptions
                SET {', '.join(set_clauses)}
                WHERE id = %s
            """

            cursor.execute(query, values)
            conn.commit()

            logger.info(f"Updated macro environment {macro_id}")
            return True

        except Exception as e:
            conn.rollback()
            logger.error(f"Error updating macro assumptions: {e}")
            return False

        finally:
            cursor.close()
            conn.close()

    def apply_macro_to_company(
        self,
        company_id: int,
        macro_id: int,
        update_default_scenario: bool = True
    ) -> bool:
        """
        Apply macro assumptions to a company's default scenario

        Args:
            company_id: Company ID
            macro_id: Macro environment ID
            update_default_scenario: Whether to update the default scenario

        Returns:
            True if successful, False otherwise
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # Get macro assumptions
            macro = self.get_macro_environment_by_id(macro_id)
            if not macro:
                logger.error(f"Macro environment {macro_id} not found")
                return False

            # Get company's default scenario
            cursor.execute("""
                SELECT id FROM scenarios
                WHERE company_id = %s AND is_default = TRUE
                LIMIT 1
            """, (company_id,))

            scenario = cursor.fetchone()
            if not scenario:
                logger.error(f"No default scenario found for company {company_id}")
                return False

            scenario_id = scenario['id']

            # Update scenario assumptions with macro values
            cursor.execute("""
                UPDATE scenario_assumptions
                SET
                    risk_free_rate = %s,
                    market_risk_premium = %s,
                    tax_rate = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE scenario_id = %s
            """, (
                macro['risk_free_rate'],
                macro['market_risk_premium'],
                macro['corporate_tax_rate'],
                scenario_id
            ))

            # Update scenario timestamp
            cursor.execute("""
                UPDATE scenarios
                SET updated_at = CURRENT_TIMESTAMP, version = version + 1
                WHERE id = %s
            """, (scenario_id,))

            conn.commit()
            logger.info(f"Applied macro {macro_id} to company {company_id}")
            return True

        except Exception as e:
            conn.rollback()
            logger.error(f"Error applying macro to company: {e}")
            return False

        finally:
            cursor.close()
            conn.close()

    def apply_macro_to_portfolio(self, macro_id: int) -> List[int]:
        """
        Apply macro assumptions to all companies in portfolio

        Args:
            macro_id: Macro environment ID

        Returns:
            List of company IDs that were updated
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # Get all companies
            cursor.execute("SELECT id FROM companies")
            companies = cursor.fetchall()

            updated_companies = []

            for company in companies:
                company_id = company['id']
                if self.apply_macro_to_company(company_id, macro_id):
                    updated_companies.append(company_id)

            logger.info(f"Applied macro {macro_id} to {len(updated_companies)} companies")
            return updated_companies

        except Exception as e:
            logger.error(f"Error applying macro to portfolio: {e}")
            return []

        finally:
            cursor.close()
            conn.close()

    def get_sector_multiples(self, sector: str, macro_id: int = None) -> Optional[Dict]:
        """
        Get sector multiples for a specific macro environment

        Args:
            sector: Sector name (e.g., 'Technology')
            macro_id: Macro environment ID (uses active if None)

        Returns:
            Sector multiples dictionary or None
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # If no macro_id specified, use active environment
            if macro_id is None:
                active = self.get_active_macro_environment()
                if not active:
                    logger.error("No active macro environment found")
                    return None
                macro_id = active['id']

            cursor.execute("""
                SELECT
                    id, sector, ev_ebitda_avg, ev_ebitda_median,
                    pe_avg, pe_median, peg_avg, data_source, as_of_date
                FROM sector_multiples
                WHERE macro_assumption_id = %s AND sector = %s
                LIMIT 1
            """, (macro_id, sector))

            result = cursor.fetchone()
            return dict(result) if result else None

        except Exception as e:
            logger.error(f"Error fetching sector multiples: {e}")
            return None

        finally:
            cursor.close()
            conn.close()

    def get_all_sector_multiples(self, macro_id: int = None) -> List[Dict]:
        """
        Get all sector multiples for a macro environment

        Args:
            macro_id: Macro environment ID (uses active if None)

        Returns:
            List of sector multiples dictionaries
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # If no macro_id specified, use active environment
            if macro_id is None:
                active = self.get_active_macro_environment()
                if not active:
                    logger.error("No active macro environment found")
                    return []
                macro_id = active['id']

            cursor.execute("""
                SELECT
                    id, sector, ev_ebitda_avg, ev_ebitda_median,
                    pe_avg, pe_median, peg_avg, data_source, as_of_date
                FROM sector_multiples
                WHERE macro_assumption_id = %s
                ORDER BY sector ASC
            """, (macro_id,))

            multiples = cursor.fetchall()
            return [dict(m) for m in multiples]

        except Exception as e:
            logger.error(f"Error fetching all sector multiples: {e}")
            return []

        finally:
            cursor.close()
            conn.close()

    def update_sector_multiples(
        self,
        macro_id: int,
        sector: str,
        multiples: Dict
    ) -> bool:
        """
        Update sector multiples for a macro environment

        Args:
            macro_id: Macro environment ID
            sector: Sector name
            multiples: Dictionary of multiple fields to update

        Returns:
            True if successful, False otherwise
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # Check if sector multiples exist
            cursor.execute("""
                SELECT id FROM sector_multiples
                WHERE macro_assumption_id = %s AND sector = %s
            """, (macro_id, sector))

            existing = cursor.fetchone()

            if existing:
                # Update existing
                set_clauses = []
                values = []

                for field, value in multiples.items():
                    set_clauses.append(f"{field} = %s")
                    values.append(value)

                set_clauses.append("updated_at = CURRENT_TIMESTAMP")
                values.extend([macro_id, sector])

                query = f"""
                    UPDATE sector_multiples
                    SET {', '.join(set_clauses)}
                    WHERE macro_assumption_id = %s AND sector = %s
                """

                cursor.execute(query, values)

            else:
                # Insert new
                cursor.execute("""
                    INSERT INTO sector_multiples (
                        macro_assumption_id, sector, ev_ebitda_avg, ev_ebitda_median,
                        pe_avg, pe_median, peg_avg, data_source
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    macro_id, sector,
                    multiples.get('ev_ebitda_avg'),
                    multiples.get('ev_ebitda_median'),
                    multiples.get('pe_avg'),
                    multiples.get('pe_median'),
                    multiples.get('peg_avg'),
                    multiples.get('data_source', 'Manual Entry')
                ))

            conn.commit()
            logger.info(f"Updated sector multiples for {sector} in macro {macro_id}")
            return True

        except Exception as e:
            conn.rollback()
            logger.error(f"Error updating sector multiples: {e}")
            return False

        finally:
            cursor.close()
            conn.close()


# Convenience function
def get_macro_service() -> MacroService:
    """Get instance of MacroService"""
    return MacroService()
