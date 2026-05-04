"""
Scenario Generator
Auto-generates Bear, Base, and Bull scenarios with adjusted assumptions
"""

from scenario_service import ScenarioService
from macro_service import MacroService
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class ScenarioGenerator:
    """Generates scenarios with adjusted assumptions"""

    def __init__(self):
        self.scenario_service = ScenarioService()
        self.macro_service = MacroService()

    def generate_default_scenarios(
        self,
        company_id: int,
        created_by: int,
        base_assumptions: Dict = None
    ) -> Dict[str, int]:
        """
        Generate default Bear, Base, and Bull scenarios for a company

        Args:
            company_id: Company ID
            created_by: User ID creating scenarios
            base_assumptions: Optional base assumptions (fetched from company_financials if None)

        Returns:
            Dictionary with scenario names and IDs {'Bear': 1, 'Base': 2, 'Bull': 3}
        """
        logger.info(f"Generating default scenarios for company {company_id}")

        # Get base assumptions if not provided
        if base_assumptions is None:
            base_assumptions = self._get_company_financials(company_id)

        if not base_assumptions:
            logger.error(f"No base assumptions found for company {company_id}")
            return {}

        scenario_ids = {}

        # Generate Base scenario (current assumptions)
        base_id = self._create_base_scenario(company_id, base_assumptions, created_by)
        if base_id:
            scenario_ids['Base'] = base_id

        # Generate Bear scenario (pessimistic)
        bear_assumptions = self.create_bear_scenario(base_assumptions)
        bear_id = self._create_scenario_with_assumptions(
            company_id, 'Bear Case', 'Pessimistic scenario with reduced growth and higher risk',
            bear_assumptions, created_by
        )
        if bear_id:
            scenario_ids['Bear'] = bear_id

        # Generate Bull scenario (optimistic)
        bull_assumptions = self.create_bull_scenario(base_assumptions)
        bull_id = self._create_scenario_with_assumptions(
            company_id, 'Bull Case', 'Optimistic scenario with higher growth and lower risk',
            bull_assumptions, created_by
        )
        if bull_id:
            scenario_ids['Bull'] = bull_id

        logger.info(f"Generated {len(scenario_ids)} scenarios for company {company_id}")
        return scenario_ids

    def create_bear_scenario(
        self,
        base_assumptions: Dict,
        bear_multiplier: float = 0.75
    ) -> Dict:
        """
        Create bear (pessimistic) scenario assumptions

        Args:
            base_assumptions: Base case assumptions
            bear_multiplier: Multiplier for growth rates (default 0.75 = -25%)

        Returns:
            Bear scenario assumptions dictionary
        """
        bear = base_assumptions.copy()

        # Reduce growth rates
        bear['growth_rate_y1'] = base_assumptions.get('growth_rate_y1', 0.10) * bear_multiplier
        bear['growth_rate_y2'] = base_assumptions.get('growth_rate_y2', 0.08) * bear_multiplier
        bear['growth_rate_y3'] = base_assumptions.get('growth_rate_y3', 0.06) * bear_multiplier
        bear['terminal_growth'] = max(0.015, base_assumptions.get('terminal_growth', 0.025) - 0.01)

        # Reduce margins (assume compression)
        bear['profit_margin'] = base_assumptions.get('profit_margin', 0.10) * 0.85
        if 'ebitda_margin' in base_assumptions:
            bear['ebitda_margin'] = base_assumptions['ebitda_margin'] * 0.90

        # Increase CapEx (less efficiency)
        bear['capex_pct'] = base_assumptions.get('capex_pct', 0.05) * 1.15

        # Increase risk (higher beta, WACC)
        bear['beta'] = base_assumptions.get('beta', 1.0) * 1.20
        bear['risk_free_rate'] = base_assumptions.get('risk_free_rate', 0.045) + 0.015  # +150 bps
        bear['market_risk_premium'] = base_assumptions.get('market_risk_premium', 0.065) + 0.015

        # Higher credit spread (more expensive debt)
        if 'credit_spread' in base_assumptions:
            bear['credit_spread'] = base_assumptions['credit_spread'] * 1.50

        # Higher tax rate
        bear['tax_rate'] = min(0.35, base_assumptions.get('tax_rate', 0.21) + 0.04)

        # Lower comparable multiples (market de-rating)
        bear['comparable_ev_ebitda'] = base_assumptions.get('comparable_ev_ebitda', 12.0) * 0.75
        bear['comparable_pe'] = base_assumptions.get('comparable_pe', 20.0) * 0.70
        bear['comparable_peg'] = base_assumptions.get('comparable_peg', 1.5) * 0.80

        logger.info("Created bear scenario assumptions")
        return bear

    def create_bull_scenario(
        self,
        base_assumptions: Dict,
        bull_multiplier: float = 1.25
    ) -> Dict:
        """
        Create bull (optimistic) scenario assumptions

        Args:
            base_assumptions: Base case assumptions
            bull_multiplier: Multiplier for growth rates (default 1.25 = +25%)

        Returns:
            Bull scenario assumptions dictionary
        """
        bull = base_assumptions.copy()

        # Increase growth rates
        bull['growth_rate_y1'] = min(0.50, base_assumptions.get('growth_rate_y1', 0.10) * bull_multiplier)
        bull['growth_rate_y2'] = min(0.40, base_assumptions.get('growth_rate_y2', 0.08) * bull_multiplier)
        bull['growth_rate_y3'] = min(0.30, base_assumptions.get('growth_rate_y3', 0.06) * bull_multiplier)
        bull['terminal_growth'] = min(0.035, base_assumptions.get('terminal_growth', 0.025) + 0.005)

        # Improve margins (operating leverage)
        bull['profit_margin'] = min(0.50, base_assumptions.get('profit_margin', 0.10) * 1.15)
        if 'ebitda_margin' in base_assumptions:
            bull['ebitda_margin'] = min(0.60, base_assumptions['ebitda_margin'] * 1.10)

        # Reduce CapEx (higher efficiency)
        bull['capex_pct'] = base_assumptions.get('capex_pct', 0.05) * 0.85

        # Reduce risk (lower beta, WACC)
        bull['beta'] = max(0.50, base_assumptions.get('beta', 1.0) * 0.85)
        bull['risk_free_rate'] = max(0.020, base_assumptions.get('risk_free_rate', 0.045) - 0.015)  # -150 bps
        bull['market_risk_premium'] = max(0.045, base_assumptions.get('market_risk_premium', 0.065) - 0.010)

        # Lower credit spread (cheaper debt)
        if 'credit_spread' in base_assumptions:
            bull['credit_spread'] = base_assumptions['credit_spread'] * 0.70

        # Lower tax rate (better tax efficiency)
        bull['tax_rate'] = max(0.15, base_assumptions.get('tax_rate', 0.21) - 0.03)

        # Higher comparable multiples (market re-rating)
        bull['comparable_ev_ebitda'] = base_assumptions.get('comparable_ev_ebitda', 12.0) * 1.30
        bull['comparable_pe'] = base_assumptions.get('comparable_pe', 20.0) * 1.35
        bull['comparable_peg'] = base_assumptions.get('comparable_peg', 1.5) * 1.20

        logger.info("Created bull scenario assumptions")
        return bull

    def create_stress_test_scenario(
        self,
        base_assumptions: Dict,
        stress_params: Dict
    ) -> Dict:
        """
        Create stress test scenario with custom parameters

        Args:
            base_assumptions: Base case assumptions
            stress_params: Dictionary of stress parameters
                Example: {'growth_shock': -0.50, 'rate_shock': +0.03, 'multiple_shock': -0.30}

        Returns:
            Stress scenario assumptions dictionary
        """
        stress = base_assumptions.copy()

        # Apply growth shock
        growth_shock = stress_params.get('growth_shock', 0)
        if growth_shock != 0:
            stress['growth_rate_y1'] = max(0, stress['growth_rate_y1'] * (1 + growth_shock))
            stress['growth_rate_y2'] = max(0, stress['growth_rate_y2'] * (1 + growth_shock))
            stress['growth_rate_y3'] = max(0, stress['growth_rate_y3'] * (1 + growth_shock))

        # Apply rate shock
        rate_shock = stress_params.get('rate_shock', 0)
        if rate_shock != 0:
            stress['risk_free_rate'] = stress['risk_free_rate'] + rate_shock
            stress['market_risk_premium'] = stress.get('market_risk_premium', 0.065) + rate_shock * 0.5

        # Apply multiple shock
        multiple_shock = stress_params.get('multiple_shock', 0)
        if multiple_shock != 0:
            stress['comparable_ev_ebitda'] = stress['comparable_ev_ebitda'] * (1 + multiple_shock)
            stress['comparable_pe'] = stress['comparable_pe'] * (1 + multiple_shock)

        # Apply margin shock
        margin_shock = stress_params.get('margin_shock', 0)
        if margin_shock != 0:
            stress['profit_margin'] = max(0, stress['profit_margin'] * (1 + margin_shock))

        logger.info(f"Created stress test scenario with params: {stress_params}")
        return stress

    def create_sensitivity_scenarios(
        self,
        company_id: int,
        variable: str,
        range_values: List[float],
        created_by: int,
        base_assumptions: Dict = None
    ) -> List[int]:
        """
        Create multiple scenarios varying a single variable

        Args:
            company_id: Company ID
            variable: Variable to vary (e.g., 'growth_rate_y1', 'beta', 'wacc')
            range_values: List of values to test
            created_by: User ID
            base_assumptions: Base assumptions

        Returns:
            List of scenario IDs created
        """
        if base_assumptions is None:
            base_assumptions = self._get_company_financials(company_id)

        scenario_ids = []

        for value in range_values:
            # Create scenario name
            name = f"Sensitivity: {variable} = {value}"
            description = f"Sensitivity analysis varying {variable}"

            # Copy base assumptions and update variable
            scenario_assumptions = base_assumptions.copy()
            scenario_assumptions[variable] = value

            # Create scenario
            scenario_id = self._create_scenario_with_assumptions(
                company_id, name, description, scenario_assumptions, created_by
            )

            if scenario_id:
                scenario_ids.append(scenario_id)

        logger.info(f"Created {len(scenario_ids)} sensitivity scenarios for {variable}")
        return scenario_ids

    def _get_company_financials(self, company_id: int) -> Optional[Dict]:
        """
        Get company financials to use as base assumptions

        Args:
            company_id: Company ID

        Returns:
            Dictionary of financial assumptions
        """
        import psycopg2
        from psycopg2.extras import RealDictCursor
        from config import Config

        try:
            conn = psycopg2.connect(
                Config.get_db_connection_string(),
                cursor_factory=RealDictCursor
            )
            cursor = conn.cursor()

            cursor.execute("""
                SELECT
                    growth_rate_y1, growth_rate_y2, growth_rate_y3, terminal_growth,
                    profit_margin, capex_pct, beta, risk_free_rate, market_risk_premium,
                    size_premium, country_risk_premium, tax_rate,
                    comparable_ev_ebitda, comparable_pe, comparable_peg
                FROM company_financials
                WHERE company_id = %s
            """, (company_id,))

            result = cursor.fetchone()
            cursor.close()
            conn.close()

            return dict(result) if result else None

        except Exception as e:
            logger.error(f"Error fetching company financials: {e}")
            return None

    def _create_base_scenario(
        self,
        company_id: int,
        base_assumptions: Dict,
        created_by: int
    ) -> Optional[int]:
        """Create base scenario from current company financials"""
        return self._create_scenario_with_assumptions(
            company_id,
            'Base Case',
            'Current assumptions from company financials',
            base_assumptions,
            created_by,
            is_default=True
        )

    def _create_scenario_with_assumptions(
        self,
        company_id: int,
        name: str,
        description: str,
        assumptions: Dict,
        created_by: int,
        is_default: bool = False
    ) -> Optional[int]:
        """
        Create a scenario and populate its assumptions

        Args:
            company_id: Company ID
            name: Scenario name
            description: Scenario description
            assumptions: Dictionary of assumptions
            created_by: User ID
            is_default: Whether this is the default scenario

        Returns:
            Scenario ID if successful, None otherwise
        """
        # Create scenario
        scenario_id = self.scenario_service.create_scenario(
            company_id, name, description, created_by, is_default
        )

        if not scenario_id:
            return None

        # Update assumptions
        success = self.scenario_service.update_scenario_assumptions(
            scenario_id, assumptions, created_by
        )

        if not success:
            logger.error(f"Failed to update assumptions for scenario {scenario_id}")
            return None

        return scenario_id


# Convenience function
def get_scenario_generator() -> ScenarioGenerator:
    """Get instance of ScenarioGenerator"""
    return ScenarioGenerator()
