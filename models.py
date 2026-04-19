"""
Pydantic models for data validation and serialization.
Ensures data integrity with comprehensive business rules.
"""

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional
from datetime import datetime


class CompanyFinancials(BaseModel):
    """
    Comprehensive validation for company financial data.
    All business rules enforced at the schema level.
    """
    
    # Basic Information
    name: str = Field(..., min_length=1, max_length=200, description="Company name")
    sector: str = Field(..., min_length=1, max_length=100, description="Industry sector")
    
    # Income Statement (in actual dollars, not millions)
    revenue: float = Field(..., gt=0, description="Annual revenue must be positive")
    ebitda: float = Field(..., description="Earnings before interest, taxes, depreciation, amortization")
    depreciation: float = Field(..., ge=0, description="Annual depreciation expense")
    
    # Cash Flow Components
    capex_pct: float = Field(..., ge=0, le=1, description="CapEx as % of revenue (0-100%)")
    working_capital_change: float = Field(..., description="Change in working capital")
    profit_margin: float = Field(..., ge=-1, le=1, description="Net profit margin (-100% to 100%)")
    
    # Growth Assumptions
    growth_rate_y1: float = Field(..., ge=-0.5, le=2.0, description="Year 1 growth rate (-50% to 200%)")
    growth_rate_y2: float = Field(..., ge=-0.5, le=2.0, description="Year 2 growth rate (-50% to 200%)")
    growth_rate_y3: float = Field(..., ge=-0.5, le=2.0, description="Year 3 growth rate (-50% to 200%)")
    terminal_growth: float = Field(..., ge=-0.1, le=0.15, description="Terminal growth rate (-10% to 15%)")
    
    # Tax & Capital Structure
    tax_rate: float = Field(..., ge=0, le=1, description="Corporate tax rate (0-100%)")
    shares_outstanding: float = Field(..., gt=0, description="Number of shares outstanding")
    debt: float = Field(..., ge=0, description="Total debt")
    cash: float = Field(..., ge=0, description="Cash and equivalents")
    
    # Market Data
    market_cap_estimate: float = Field(..., gt=0, description="Estimated market capitalization")
    beta: float = Field(..., ge=-3, le=5, description="Beta coefficient (-3 to 5)")
    
    # Risk Parameters
    risk_free_rate: float = Field(..., ge=0, le=0.2, description="Risk-free rate (0-20%)")
    market_risk_premium: float = Field(..., ge=0, le=0.3, description="Market risk premium (0-30%)")
    country_risk_premium: float = Field(..., ge=0, le=0.25, description="Country risk premium (0-25%)")
    size_premium: float = Field(..., ge=0, le=0.2, description="Size premium (0-20%)")
    
    # Comparable Company Multiples
    comparable_ev_ebitda: float = Field(..., ge=0, le=100, description="EV/EBITDA multiple (0-100x)")
    comparable_pe: float = Field(..., ge=0, le=200, description="P/E multiple (0-200x)")
    comparable_peg: float = Field(..., ge=0, le=10, description="PEG ratio (0-10)")
    
    @field_validator('ebitda')
    @classmethod
    def validate_ebitda(cls, v, info):
        """EBITDA should be reasonable relative to revenue"""
        if 'revenue' in info.data:
            revenue = info.data['revenue']
            if revenue > 0:
                ebitda_margin = v / revenue
                # Relaxed constraint: Allow wider range for edge cases
                if ebitda_margin < -3 or ebitda_margin > 2:
                    raise ValueError(
                        f'EBITDA margin {ebitda_margin:.1%} is unrealistic '
                        f'(should be between -300% and 200%). '
                        f'EBITDA=${v:,.0f}, Revenue=${revenue:,.0f}'
                    )
        return v
    
    @field_validator('depreciation')
    @classmethod
    def validate_depreciation(cls, v, info):
        """Depreciation should be reasonable relative to EBITDA"""
        if 'ebitda' in info.data and 'revenue' in info.data:
            revenue = info.data['revenue']
            if revenue > 0:
                dep_pct = v / revenue
                if dep_pct > 0.5:
                    raise ValueError(f'Depreciation is {dep_pct:.1%} of revenue, which seems excessive (>50%)')
        return v
    
    @model_validator(mode='after')
    def validate_growth_trajectory(self):
        """Ensure growth rates follow a logical progression"""
        if self.growth_rate_y1 > 1.0 and self.growth_rate_y2 > self.growth_rate_y1:
            raise ValueError('High growth rates should moderate over time')

        # Terminal growth should be lower than the lowest short-term growth rate
        min_growth = min(self.growth_rate_y1, self.growth_rate_y2, self.growth_rate_y3)
        if self.terminal_growth >= min_growth:
            raise ValueError(
                f'Terminal growth ({self.terminal_growth*100:.1f}%) must be lower than all short-term growth rates. '
                f'Minimum short-term growth is {min_growth*100:.1f}%. '
                f'Please reduce terminal growth to below {min_growth*100:.1f}% or increase short-term growth rates.'
            )

        return self
    
    @model_validator(mode='after')
    def validate_capital_structure(self):
        """Validate debt, cash, and market cap relationships"""
        enterprise_value = self.market_cap_estimate + self.debt - self.cash
        
        if enterprise_value <= 0:
            raise ValueError('Enterprise value cannot be negative or zero')
        
        # Debt-to-equity ratio sanity check
        debt_to_equity = self.debt / self.market_cap_estimate if self.market_cap_estimate > 0 else 0
        if debt_to_equity > 10:
            raise ValueError(f'Debt-to-equity ratio of {debt_to_equity:.1f}x is extremely high (>10x)')
        
        return self
    
    @model_validator(mode='after')
    def validate_wacc_inputs(self):
        """Ensure WACC calculation will be valid"""
        cost_of_equity = (self.risk_free_rate + 
                         self.beta * self.market_risk_premium + 
                         self.country_risk_premium + 
                         self.size_premium)
        
        if cost_of_equity <= 0:
            raise ValueError('Cost of equity must be positive')
        
        if cost_of_equity > 0.5:
            raise ValueError(f'Cost of equity {cost_of_equity:.1%} seems unreasonably high (>50%)')
        
        if cost_of_equity <= self.terminal_growth:
            raise ValueError('WACC/Cost of equity must exceed terminal growth rate for valid DCF')
        
        return self
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "TechStartup Inc",
                "sector": "Software",
                "revenue": 5000000,
                "ebitda": 1500000,
                "depreciation": 100000,
                "capex_pct": 0.05,
                "working_capital_change": -50000,
                "profit_margin": 0.15,
                "growth_rate_y1": 0.30,
                "growth_rate_y2": 0.25,
                "growth_rate_y3": 0.20,
                "terminal_growth": 0.03,
                "tax_rate": 0.25,
                "shares_outstanding": 1000000,
                "debt": 500000,
                "cash": 1000000,
                "market_cap_estimate": 3000000,
                "beta": 1.5,
                "risk_free_rate": 0.04,
                "market_risk_premium": 0.07,
                "country_risk_premium": 0.0,
                "size_premium": 0.03,
                "comparable_ev_ebitda": 12.0,
                "comparable_pe": 25.0,
                "comparable_peg": 1.5
            }
        }


class CompanyBase(BaseModel):
    """Base company information"""
    name: str = Field(..., min_length=1, max_length=200)
    sector: str = Field(..., min_length=1, max_length=100)


class CompanyCreate(CompanyBase, CompanyFinancials):
    """Schema for creating a new company with full financials"""
    pass


class CompanyUpdate(BaseModel):
    """Schema for updating company financials - all fields optional for partial updates"""

    # Basic Information
    name: Optional[str] = Field(None, min_length=1, max_length=200, description="Company name")
    sector: Optional[str] = Field(None, min_length=1, max_length=100, description="Industry sector")

    # Income Statement (in actual dollars, not millions)
    revenue: Optional[float] = Field(None, gt=0, description="Annual revenue must be positive")
    ebitda: Optional[float] = Field(None, description="Earnings before interest, taxes, depreciation, amortization")
    depreciation: Optional[float] = Field(None, ge=0, description="Annual depreciation expense")

    # Cash Flow Components
    capex_pct: Optional[float] = Field(None, ge=0, le=1, description="CapEx as % of revenue (0-100%)")
    working_capital_change: Optional[float] = Field(None, description="Change in working capital")
    profit_margin: Optional[float] = Field(None, ge=-1, le=1, description="Net profit margin (-100% to 100%)")

    # Growth Assumptions
    growth_rate_y1: Optional[float] = Field(None, ge=-0.5, le=2.0, description="Year 1 growth rate (-50% to 200%)")
    growth_rate_y2: Optional[float] = Field(None, ge=-0.5, le=2.0, description="Year 2 growth rate (-50% to 200%)")
    growth_rate_y3: Optional[float] = Field(None, ge=-0.5, le=2.0, description="Year 3 growth rate (-50% to 200%)")
    terminal_growth: Optional[float] = Field(None, ge=-0.1, le=0.15, description="Terminal growth rate (-10% to 15%)")

    # Tax & Capital Structure
    tax_rate: Optional[float] = Field(None, ge=0, le=1, description="Corporate tax rate (0-100%)")
    shares_outstanding: Optional[float] = Field(None, gt=0, description="Number of shares outstanding")
    debt: Optional[float] = Field(None, ge=0, description="Total debt")
    cash: Optional[float] = Field(None, ge=0, description="Cash and equivalents")

    # Market Data
    market_cap_estimate: Optional[float] = Field(None, gt=0, description="Estimated market capitalization")
    beta: Optional[float] = Field(None, ge=-3, le=5, description="Beta coefficient (-3 to 5)")

    # Risk Parameters
    risk_free_rate: Optional[float] = Field(None, ge=0, le=0.2, description="Risk-free rate (0-20%)")
    market_risk_premium: Optional[float] = Field(None, ge=0, le=0.3, description="Market risk premium (0-30%)")
    country_risk_premium: Optional[float] = Field(None, ge=0, le=0.25, description="Country risk premium (0-25%)")
    size_premium: Optional[float] = Field(None, ge=0, le=0.2, description="Size premium (0-20%)")

    # Comparable Company Multiples
    comparable_ev_ebitda: Optional[float] = Field(None, ge=0, le=100, description="EV/EBITDA multiple (0-100x)")
    comparable_pe: Optional[float] = Field(None, ge=0, le=200, description="P/E multiple (0-200x)")
    comparable_peg: Optional[float] = Field(None, ge=0, le=10, description="PEG ratio (0-10)")


class ValuationResult(BaseModel):
    """Valuation result output schema"""
    company_id: int
    dcf_equity_value: float
    ev_ebitda_value: float
    pe_value: float
    final_equity_value: float
    fair_value_per_share: float
    current_price_estimate: float
    upside_pct: float
    recommendation: str
    wacc: float
    roe: Optional[float] = None
    roic: Optional[float] = None
    debt_to_equity: Optional[float] = None
    altman_z_score: Optional[float] = None
    monte_carlo_mean: Optional[float] = None
    monte_carlo_std: Optional[float] = None
    var_95: Optional[float] = None
    created_at: datetime
    
    class Config:
        from_attributes = True
