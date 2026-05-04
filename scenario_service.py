"""
Scenario Management Service
Handles creation, retrieval, updating, and comparison of valuation scenarios
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from config import Config
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class ScenarioService:
    """Service for managing valuation scenarios"""

    def __init__(self, db_connection_string: str = None):
        self.db_connection_string = db_connection_string or Config.get_db_connection_string()

    def get_connection(self):
        """Get database connection"""
        return psycopg2.connect(
            self.db_connection_string,
            cursor_factory=RealDictCursor
        )

    def create_scenario(
        self,
        company_id: int,
        name: str,
        description: str,
        created_by: int,
        is_default: bool = False
    ) -> Optional[int]:
        """
        Create a new scenario for a company

        Args:
            company_id: Company ID
            name: Scenario name (e.g., 'Bear Case', 'Bull Case')
            description: Scenario description
            created_by: User ID who created the scenario
            is_default: Whether this is the default scenario

        Returns:
            scenario_id if successful, None otherwise
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # If setting as default, unset other defaults first
            if is_default:
                cursor.execute("""
                    UPDATE scenarios
                    SET is_default = FALSE
                    WHERE company_id = %s AND is_default = TRUE
                """, (company_id,))

            # Create scenario
            cursor.execute("""
                INSERT INTO scenarios (company_id, name, description, is_default, created_by)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            """, (company_id, name, description, is_default, created_by))

            scenario_id = cursor.fetchone()['id']
            conn.commit()

            logger.info(f"Created scenario {scenario_id} for company {company_id}: {name}")
            return scenario_id

        except Exception as e:
            conn.rollback()
            logger.error(f"Error creating scenario: {e}")
            return None

        finally:
            cursor.close()
            conn.close()

    def get_scenarios_for_company(self, company_id: int) -> List[Dict]:
        """
        Get all scenarios for a company

        Args:
            company_id: Company ID

        Returns:
            List of scenario dictionaries with assumptions
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT
                    s.id,
                    s.company_id,
                    s.name,
                    s.description,
                    s.is_default,
                    s.created_by,
                    s.created_at,
                    s.updated_at,
                    s.version,
                    sa.growth_rate_y1,
                    sa.growth_rate_y2,
                    sa.growth_rate_y3,
                    sa.terminal_growth,
                    sa.profit_margin,
                    sa.ebitda_margin,
                    sa.capex_pct,
                    sa.beta,
                    sa.risk_free_rate,
                    sa.market_risk_premium,
                    sa.size_premium,
                    sa.country_risk_premium,
                    sa.target_debt_ratio,
                    sa.credit_spread,
                    sa.tax_rate,
                    sa.comparable_ev_ebitda,
                    sa.comparable_pe,
                    sa.comparable_peg
                FROM scenarios s
                LEFT JOIN scenario_assumptions sa ON s.id = sa.scenario_id
                WHERE s.company_id = %s
                ORDER BY s.is_default DESC, s.created_at DESC
            """, (company_id,))

            scenarios = cursor.fetchall()
            return [dict(scenario) for scenario in scenarios]

        except Exception as e:
            logger.error(f"Error fetching scenarios for company {company_id}: {e}")
            return []

        finally:
            cursor.close()
            conn.close()

    def get_scenario_by_id(self, scenario_id: int) -> Optional[Dict]:
        """
        Get a specific scenario with its assumptions

        Args:
            scenario_id: Scenario ID

        Returns:
            Scenario dictionary or None
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT
                    s.id,
                    s.company_id,
                    s.name,
                    s.description,
                    s.is_default,
                    s.created_by,
                    s.created_at,
                    s.updated_at,
                    s.version,
                    sa.growth_rate_y1,
                    sa.growth_rate_y2,
                    sa.growth_rate_y3,
                    sa.terminal_growth,
                    sa.profit_margin,
                    sa.ebitda_margin,
                    sa.capex_pct,
                    sa.beta,
                    sa.risk_free_rate,
                    sa.market_risk_premium,
                    sa.size_premium,
                    sa.country_risk_premium,
                    sa.target_debt_ratio,
                    sa.credit_spread,
                    sa.tax_rate,
                    sa.comparable_ev_ebitda,
                    sa.comparable_pe,
                    sa.comparable_peg
                FROM scenarios s
                LEFT JOIN scenario_assumptions sa ON s.id = sa.scenario_id
                WHERE s.id = %s
            """, (scenario_id,))

            result = cursor.fetchone()
            return dict(result) if result else None

        except Exception as e:
            logger.error(f"Error fetching scenario {scenario_id}: {e}")
            return None

        finally:
            cursor.close()
            conn.close()

    def get_default_scenario(self, company_id: int) -> Optional[Dict]:
        """
        Get the default scenario for a company

        Args:
            company_id: Company ID

        Returns:
            Default scenario dictionary or None
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT
                    s.id,
                    s.company_id,
                    s.name,
                    s.description,
                    s.is_default,
                    s.created_by,
                    s.created_at,
                    s.updated_at,
                    s.version,
                    sa.growth_rate_y1,
                    sa.growth_rate_y2,
                    sa.growth_rate_y3,
                    sa.terminal_growth,
                    sa.profit_margin,
                    sa.ebitda_margin,
                    sa.capex_pct,
                    sa.beta,
                    sa.risk_free_rate,
                    sa.market_risk_premium,
                    sa.size_premium,
                    sa.country_risk_premium,
                    sa.target_debt_ratio,
                    sa.credit_spread,
                    sa.tax_rate,
                    sa.comparable_ev_ebitda,
                    sa.comparable_pe,
                    sa.comparable_peg
                FROM scenarios s
                LEFT JOIN scenario_assumptions sa ON s.id = sa.scenario_id
                WHERE s.company_id = %s AND s.is_default = TRUE
                LIMIT 1
            """, (company_id,))

            result = cursor.fetchone()
            return dict(result) if result else None

        except Exception as e:
            logger.error(f"Error fetching default scenario for company {company_id}: {e}")
            return None

        finally:
            cursor.close()
            conn.close()

    def update_scenario_assumptions(
        self,
        scenario_id: int,
        assumptions: Dict,
        changed_by: int
    ) -> bool:
        """
        Update scenario assumptions

        Args:
            scenario_id: Scenario ID
            assumptions: Dictionary of assumption fields to update
            changed_by: User ID making the change

        Returns:
            True if successful, False otherwise
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # Check if scenario exists
            cursor.execute("SELECT id FROM scenarios WHERE id = %s", (scenario_id,))
            if not cursor.fetchone():
                logger.error(f"Scenario {scenario_id} not found")
                return False

            # Check if assumptions exist
            cursor.execute("SELECT id FROM scenario_assumptions WHERE scenario_id = %s", (scenario_id,))
            assumptions_exist = cursor.fetchone()

            if assumptions_exist:
                # Update existing assumptions
                set_clauses = []
                values = []

                for field, value in assumptions.items():
                    set_clauses.append(f"{field} = %s")
                    values.append(value)

                set_clauses.append("updated_at = CURRENT_TIMESTAMP")
                values.append(scenario_id)

                query = f"""
                    UPDATE scenario_assumptions
                    SET {', '.join(set_clauses)}
                    WHERE scenario_id = %s
                """

                cursor.execute(query, values)

            else:
                # Insert new assumptions
                fields = list(assumptions.keys())
                fields.append('scenario_id')
                values = list(assumptions.values())
                values.append(scenario_id)

                placeholders = ', '.join(['%s'] * len(values))
                field_names = ', '.join(fields)

                query = f"""
                    INSERT INTO scenario_assumptions ({field_names})
                    VALUES ({placeholders})
                """

                cursor.execute(query, values)

            # Update scenario updated_at timestamp
            cursor.execute("""
                UPDATE scenarios
                SET updated_at = CURRENT_TIMESTAMP, version = version + 1
                WHERE id = %s
            """, (scenario_id,))

            conn.commit()
            logger.info(f"Updated assumptions for scenario {scenario_id}")
            return True

        except Exception as e:
            conn.rollback()
            logger.error(f"Error updating scenario assumptions: {e}")
            return False

        finally:
            cursor.close()
            conn.close()

    def clone_scenario(
        self,
        scenario_id: int,
        new_name: str,
        new_description: str,
        created_by: int
    ) -> Optional[int]:
        """
        Clone an existing scenario with new name

        Args:
            scenario_id: Source scenario ID
            new_name: Name for the cloned scenario
            new_description: Description for the cloned scenario
            created_by: User ID creating the clone

        Returns:
            New scenario ID if successful, None otherwise
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # Get source scenario
            cursor.execute("SELECT company_id FROM scenarios WHERE id = %s", (scenario_id,))
            result = cursor.fetchone()

            if not result:
                logger.error(f"Scenario {scenario_id} not found")
                return None

            company_id = result['company_id']

            # Create new scenario
            cursor.execute("""
                INSERT INTO scenarios (company_id, name, description, created_by)
                VALUES (%s, %s, %s, %s)
                RETURNING id
            """, (company_id, new_name, new_description, created_by))

            new_scenario_id = cursor.fetchone()['id']

            # Copy assumptions
            cursor.execute("""
                INSERT INTO scenario_assumptions (
                    scenario_id, growth_rate_y1, growth_rate_y2, growth_rate_y3, terminal_growth,
                    profit_margin, ebitda_margin, capex_pct, beta, risk_free_rate,
                    market_risk_premium, size_premium, country_risk_premium,
                    target_debt_ratio, credit_spread, tax_rate,
                    comparable_ev_ebitda, comparable_pe, comparable_peg
                )
                SELECT
                    %s, growth_rate_y1, growth_rate_y2, growth_rate_y3, terminal_growth,
                    profit_margin, ebitda_margin, capex_pct, beta, risk_free_rate,
                    market_risk_premium, size_premium, country_risk_premium,
                    target_debt_ratio, credit_spread, tax_rate,
                    comparable_ev_ebitda, comparable_pe, comparable_peg
                FROM scenario_assumptions
                WHERE scenario_id = %s
            """, (new_scenario_id, scenario_id))

            conn.commit()
            logger.info(f"Cloned scenario {scenario_id} to {new_scenario_id}")
            return new_scenario_id

        except Exception as e:
            conn.rollback()
            logger.error(f"Error cloning scenario: {e}")
            return None

        finally:
            cursor.close()
            conn.close()

    def delete_scenario(self, scenario_id: int) -> bool:
        """
        Delete a scenario (CASCADE will delete associated assumptions)

        Args:
            scenario_id: Scenario ID to delete

        Returns:
            True if successful, False otherwise
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # Check if it's a default scenario
            cursor.execute("SELECT is_default, company_id FROM scenarios WHERE id = %s", (scenario_id,))
            result = cursor.fetchone()

            if not result:
                logger.error(f"Scenario {scenario_id} not found")
                return False

            if result['is_default']:
                logger.error(f"Cannot delete default scenario {scenario_id}")
                return False

            # Delete scenario (CASCADE will handle assumptions)
            cursor.execute("DELETE FROM scenarios WHERE id = %s", (scenario_id,))

            conn.commit()
            logger.info(f"Deleted scenario {scenario_id}")
            return True

        except Exception as e:
            conn.rollback()
            logger.error(f"Error deleting scenario: {e}")
            return False

        finally:
            cursor.close()
            conn.close()

    def set_default_scenario(self, company_id: int, scenario_id: int) -> bool:
        """
        Set a scenario as the default for a company

        Args:
            company_id: Company ID
            scenario_id: Scenario ID to set as default

        Returns:
            True if successful, False otherwise
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # Verify scenario belongs to company
            cursor.execute("""
                SELECT id FROM scenarios
                WHERE id = %s AND company_id = %s
            """, (scenario_id, company_id))

            if not cursor.fetchone():
                logger.error(f"Scenario {scenario_id} not found for company {company_id}")
                return False

            # Unset current default
            cursor.execute("""
                UPDATE scenarios
                SET is_default = FALSE
                WHERE company_id = %s AND is_default = TRUE
            """, (company_id,))

            # Set new default
            cursor.execute("""
                UPDATE scenarios
                SET is_default = TRUE, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (scenario_id,))

            conn.commit()
            logger.info(f"Set scenario {scenario_id} as default for company {company_id}")
            return True

        except Exception as e:
            conn.rollback()
            logger.error(f"Error setting default scenario: {e}")
            return False

        finally:
            cursor.close()
            conn.close()

    def compare_scenarios(self, company_id: int, scenario_ids: List[int]) -> Dict:
        """
        Compare multiple scenarios side-by-side

        Args:
            company_id: Company ID
            scenario_ids: List of scenario IDs to compare

        Returns:
            Dictionary with comparison data
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # Get company name
            cursor.execute("SELECT name, ticker FROM companies WHERE id = %s", (company_id,))
            company = cursor.fetchone()

            if not company:
                logger.error(f"Company {company_id} not found")
                return {}

            # Get scenarios with assumptions
            placeholders = ', '.join(['%s'] * len(scenario_ids))
            cursor.execute(f"""
                SELECT
                    s.id,
                    s.name,
                    s.description,
                    s.is_default,
                    sa.growth_rate_y1,
                    sa.growth_rate_y2,
                    sa.growth_rate_y3,
                    sa.terminal_growth,
                    sa.profit_margin,
                    sa.ebitda_margin,
                    sa.capex_pct,
                    sa.beta,
                    sa.risk_free_rate,
                    sa.market_risk_premium,
                    sa.size_premium,
                    sa.country_risk_premium,
                    sa.target_debt_ratio,
                    sa.credit_spread,
                    sa.tax_rate,
                    sa.comparable_ev_ebitda,
                    sa.comparable_pe,
                    sa.comparable_peg
                FROM scenarios s
                LEFT JOIN scenario_assumptions sa ON s.id = sa.scenario_id
                WHERE s.id IN ({placeholders}) AND s.company_id = %s
            """, (*scenario_ids, company_id))

            scenarios = [dict(scenario) for scenario in cursor.fetchall()]

            comparison = {
                'company_name': company['name'],
                'ticker': company['ticker'],
                'scenarios': scenarios,
                'num_scenarios': len(scenarios)
            }

            logger.info(f"Compared {len(scenarios)} scenarios for company {company_id}")
            return comparison

        except Exception as e:
            logger.error(f"Error comparing scenarios: {e}")
            return {}

        finally:
            cursor.close()
            conn.close()


# Convenience function
def get_scenario_service() -> ScenarioService:
    """Get instance of ScenarioService"""
    return ScenarioService()
