import csv
import math
from statistics import mean, stdev
from config import Config
from ib_valuation_framework import (
	apply_investment_banking_adjustments,
	classify_company,
	get_industry_benchmark_multiples
)
try:
	import valuation_engine as _ml
	_ML_AVAILABLE = True
except Exception:
	_ML_AVAILABLE = False

def get_float(prompt):
	while True:
		try:
			return float(input(prompt))
		except ValueError:
			print("Please enter a valid number.")

def get_choice(prompt, valid_choices):
	while True:
		choice = input(prompt).strip().lower()
		if choice in valid_choices:
			return choice
		print(f"Please enter one of: {', '.join(valid_choices)}")

def synthetic_cost_of_debt(operating_income: float, interest_expense: float, risk_free_rate: float) -> float:
	"""
	Damodaran synthetic credit rating approach.
	Interest Coverage = EBIT / Interest Expense → letter rating → credit spread.
	Used in place of a hardcoded spread assumption.
	"""
	if interest_expense <= 0:
		return risk_free_rate + 0.010  # no debt / net-cash company → near risk-free

	# Banks report depositor interest as "interest expense" — can be enormous vs. EBIT.
	# Banks never reach DCF in our model (they use P/B path), but guard defensively.
	if interest_expense > 10e9 and operating_income <= 0:
		return risk_free_rate + 0.015
	if operating_income > 0 and interest_expense > operating_income * 20:
		return risk_free_rate + 0.015

	coverage = operating_income / interest_expense

	# Damodaran coverage-to-spread table (large/mid-cap, 2024 calibration)
	if coverage > 8.5:    spread = 0.0060   # AAA
	elif coverage > 6.5:  spread = 0.0090   # AA
	elif coverage > 5.5:  spread = 0.0110   # A+
	elif coverage > 4.25: spread = 0.0140   # A
	elif coverage > 3.0:  spread = 0.0160   # A-
	elif coverage > 2.5:  spread = 0.0200   # BBB
	elif coverage > 2.0:  spread = 0.0240   # BB+
	elif coverage > 1.5:  spread = 0.0275   # BB
	elif coverage > 1.25: spread = 0.0325   # B+
	elif coverage > 0.8:  spread = 0.0400   # B
	elif coverage > 0.5:  spread = 0.0475   # B-
	elif coverage > 0.0:  spread = 0.0700   # CCC
	else:                 spread = 0.1500   # D — negative EBIT, severe distress

	return risk_free_rate + spread


def calculate_wacc(risk_free_rate, beta, market_risk_premium, debt, cash, equity_value, tax_rate,
                   country_risk=0, size_premium=0, leverage_penalty=0,
                   interest_expense=0, operating_income=0):
	"""Calculate WACC using CAPM for equity and Damodaran synthetic rating for debt."""
	cost_of_equity = risk_free_rate + beta * market_risk_premium + country_risk + size_premium

	cost_of_debt = synthetic_cost_of_debt(operating_income, interest_expense, risk_free_rate)

	# Use net debt for weights — net-cash companies have zero debt weight
	net_debt = max(0.0, debt - cash)
	total_value = net_debt + equity_value
	if total_value == 0:
		return cost_of_equity, cost_of_equity, cost_of_debt

	weight_equity = equity_value / total_value
	weight_debt   = net_debt / total_value

	wacc = (weight_equity * cost_of_equity) + (weight_debt * cost_of_debt * (1 - tax_rate))
	wacc += leverage_penalty

	return wacc, cost_of_equity, cost_of_debt

def calculate_financial_ratios(revenue, ebitda, profit, debt, cash, equity_value, shares, fcf):
	"""Calculate comprehensive financial ratios"""
	ratios = {}
	
	# Valuation Ratios
	ratios['ev'] = equity_value + debt - cash
	ratios['ev_ebitda'] = ratios['ev'] / ebitda if ebitda > 0 else 0
	ratios['ev_revenue'] = ratios['ev'] / revenue if revenue > 0 else 0
	ratios['pe'] = equity_value / profit if profit > 0 else 0
	ratios['price_per_share'] = equity_value / shares if shares > 0 else 0
	ratios['fcf_yield'] = (fcf / equity_value * 100) if equity_value > 0 else 0
	
	# Leverage Ratios
	ratios['debt_to_equity'] = debt / equity_value if equity_value > 0 else 0
	ratios['debt_to_ebitda'] = debt / ebitda if ebitda > 0 else 0
	ratios['net_debt'] = debt - cash
	ratios['net_debt_to_ebitda'] = ratios['net_debt'] / ebitda if ebitda > 0 else 0
	
	# Profitability Ratios
	ratios['ebitda_margin'] = (ebitda / revenue * 100) if revenue > 0 else 0
	ratios['profit_margin'] = (profit / revenue * 100) if revenue > 0 else 0
	ratios['roe'] = (profit / equity_value * 100) if equity_value > 0 else 0
	ratios['roic'] = (profit * 0.8 / (debt + equity_value) * 100) if (debt + equity_value) > 0 else 0
	
	# Coverage Ratios
	interest_expense = debt * 0.05  # Assumed 5% interest rate
	ratios['interest_coverage'] = ebitda / interest_expense if interest_expense > 0 else 999
	
	return ratios

def altman_z_score(revenue, ebitda, equity_value, debt, working_capital):
	"""Calculate Altman Z-Score for bankruptcy prediction"""
	total_assets = equity_value + debt
	
	# Simplified Z-Score components
	x1 = working_capital / total_assets if total_assets > 0 else 0
	x2 = (ebitda * 0.6) / total_assets if total_assets > 0 else 0  # Retained earnings proxy
	x3 = ebitda / total_assets if total_assets > 0 else 0
	x4 = equity_value / debt if debt > 0 else 10
	x5 = revenue / total_assets if total_assets > 0 else 0
	
	z_score = 1.2*x1 + 1.4*x2 + 3.3*x3 + 0.6*x4 + 1.0*x5
	
	if z_score > 2.99:
		zone = "Safe Zone"
	elif z_score > 1.81:
		zone = "Grey Zone"
	else:
		zone = "Distress Zone"
	
	return z_score, zone

def monte_carlo_valuation(base_value, growth_volatility, discount_volatility, iterations=1000):
	"""Simple Monte Carlo simulation for valuation range"""
	import random
	
	results = []
	# Allow defaults from Config if not explicitly passed
	g_vol = growth_volatility if growth_volatility is not None else Config.MONTE_CARLO_GROWTH_VOL
	d_vol = discount_volatility if discount_volatility is not None else Config.MONTE_CARLO_DISCOUNT_VOL

	for _ in range(iterations):
		growth_shock = random.gauss(0, g_vol)
		discount_shock = random.gauss(0, d_vol)

		adjusted_value = base_value * (1 + growth_shock) / (1 + discount_shock)
		results.append(adjusted_value)
	
	return {
		'mean': mean(results),
		'median': sorted(results)[len(results)//2],
		'std': stdev(results),
		'p10': sorted(results)[int(len(results)*0.1)],
		'p90': sorted(results)[int(len(results)*0.9)]
	}

def enhanced_dcf_valuation(company_data):
	"""Comprehensive DCF valuation with multi-stage growth"""

	# APPLY INVESTMENT BANKING FRAMEWORK
	company_data = apply_investment_banking_adjustments(company_data)

	# APPLY ML CALIBRATION LAYER (sub-sector tagging, EBITDA/capex normalization,
	# adaptive blend weights, analyst signals)
	if _ML_AVAILABLE:
		company_data = _ml.calibrate(company_data)

		# Check for alternative model (banks, REITs, growth_loss)
		tag = company_data.get('sub_sector_tag', '')
		alt_price = _ml.run_alternative_model(tag, company_data)
		if alt_price is not None and alt_price > 0:
			shares = float(company_data.get('shares_outstanding', 1))
			market_cap = float(company_data.get('market_cap_estimate', 0))
			current_price = market_cap / shares if shares > 0 else 0
			analyst_target = company_data.get('analyst_target')
			# Anchor alt model to analyst consensus
			final_price = _ml.apply_analyst_anchor(alt_price, analyst_target,
			                                        company_data.get('company_type', 'STABLE_VALUE'),
			                                        company_data)
			upside = ((final_price * shares - market_cap) / market_cap * 100) if market_cap > 0 else 0
			final_price = _ml.apply_ml_correction(final_price, company_data)
			company_data['dcf_price_per_share'] = alt_price
			company_data['ev_price_per_share'] = alt_price
			company_data['pe_price_per_share'] = alt_price
			_ml.log_prediction(
				company_data.get('ticker', company_data.get('name', '')),
				final_price, company_data
			)
			rec_map = [("STRONG BUY", 20), ("BUY", 10), ("HOLD", -10), ("UNDERWEIGHT", -20)]
			recommendation = "SELL"
			for label, thresh in rec_map:
				if upside > thresh:
					recommendation = label
					break
			return {
				'name': company_data['name'],
				'sector': company_data.get('sector', ''),
				'dcf_equity_value': final_price * shares,
				'dcf_price_per_share': alt_price,
				'comp_ev_value': final_price * shares,
				'comp_pe_value': final_price * shares,
				'final_equity_value': final_price * shares,
				'final_price_per_share': final_price,
				'market_cap': market_cap,
				'current_price': current_price,
				'upside_pct': upside,
				'recommendation': recommendation,
				'wacc': 0.095,
				'ev_ebitda': 0,
				'pe_ratio': 0,
				'fcf_yield': 0,
				'roe': 0,
				'roic': 0,
				'debt_to_equity': 0,
				'z_score': 2.5,
				'mc_p10': final_price * shares * 0.75,
				'mc_p90': final_price * shares * 1.25,
				# Phase 4 — alt-model scenarios: WACC/terminal-growth/growth-Y1
				# perturbations don't apply to P/B (banks) or P/FFO (REITs)
				# models. Express the range as a ±15% multiple-rerating band as
				# a placeholder; future work should perturb the actual P/B and
				# P/FFO multiples instead of using a fixed haircut.
				'scenarios': {
					'bear': {'blended_price_per_share': final_price * 0.85,
					          'blended_equity_value':   final_price * shares * 0.85,
					          'note': '-15% multiple rerating'},
					'base': {'blended_price_per_share': final_price,
					          'blended_equity_value':   final_price * shares,
					          'note': 'alternative model'},
					'bull': {'blended_price_per_share': final_price * 1.15,
					          'blended_equity_value':   final_price * shares * 1.15,
					          'note': '+15% multiple rerating'},
					'spread_pct': 30.0,
					'perturbation_axes': {'multiple_rerating_pct': [-15.0, 15.0]},
				},
				'sub_sector_tag': tag,
				'company_type': company_data.get('company_type'),
				'ebitda_method': company_data.get('ebitda_method'),
				'analyst_target': analyst_target,
				'dcf_details': {
					'ticker': company_data.get('ticker', ''),
					'model_type': 'alternative',
					'note': f'Uses {tag} model instead of DCF',
					'reason': 'DCF is not appropriate for this company type (banks use P/B, REITs use FFO, etc.)',
					'inputs': {
						'market_cap': {
							'value': market_cap,
							'source': 'yahoo_finance',
							'url_path': '',
							'label': 'Market Cap',
						},
						'shares_outstanding': {
							'value': shares,
							'source': 'yahoo_finance',
							'url_path': '/key-statistics',
							'label': 'Shares Outstanding',
						},
					},
					'calculated': {
						'price_per_share': {
							'value': alt_price,
							'formula': f'{tag} alternative valuation model',
							'result': f'${alt_price:.2f}',
						},
					},
				},
				'ev_ebitda_details': {
					'ticker': company_data.get('ticker', ''),
					'model_type': 'alternative',
					'note': f'Uses {tag} model instead of EV/EBITDA',
					'calculated': {
						'price_per_share': {
							'value': alt_price,
							'formula': f'{tag} alternative valuation model',
							'result': f'${alt_price:.2f}',
						},
					},
				},
				'pe_details': {
					'ticker': company_data.get('ticker', ''),
					'model_type': 'alternative',
					'note': f'Uses {tag} model instead of P/E',
					'calculated': {
						'price_per_share': {
							'value': alt_price,
							'formula': f'{tag} alternative valuation model',
							'result': f'${alt_price:.2f}',
						},
					},
				},
				'blend_weights': {
					'alternative_model': 1.0,
				},
			}

	name = company_data['name']
	sector = company_data['sector']
	revenue = float(company_data['revenue'])

	# Use normalized metrics if applicable (for distressed/cyclical companies)
	if 'normalized_ebitda' in company_data:
		ebitda = float(company_data['normalized_ebitda'])
		print(f"  Using NORMALIZED EBITDA: ${ebitda:,.0f} (original: ${float(company_data['ebitda']):,.0f})")
	else:
		ebitda = float(company_data['ebitda'])

	if 'normalized_profit_margin' in company_data:
		profit_margin = float(company_data['normalized_profit_margin'])
		print(f"  Using NORMALIZED Profit Margin: {profit_margin*100:.1f}% (original: {float(company_data['profit_margin'])*100:.1f}%)")
	else:
		profit_margin = float(company_data['profit_margin'])

	# CapEx taper: years 1-2 use raw current capex, years 3-10 lerp to normalized.
	# Captures the reality that high-investment phases unwind toward sector steady-state.
	# raw_capex_pct is preserved by valuation.calibrate before it overwrites capex_pct.
	raw_capex_pct = float(company_data.get('raw_capex_pct', company_data['capex_pct']))
	if 'normalized_capex_pct' in company_data:
		normalized_capex_pct = float(company_data['normalized_capex_pct'])
	else:
		normalized_capex_pct = float(company_data['capex_pct'])
	if abs(raw_capex_pct - normalized_capex_pct) > 1e-6:
		print(f"  CapEx taper: {raw_capex_pct*100:.1f}% (Y1-2) → {normalized_capex_pct*100:.1f}% (Y10 normalized)")
	capex_pct = raw_capex_pct  # Y1 reference for downstream consumers (assumptions block)

	depreciation = float(company_data['depreciation'])
	wc_change = float(company_data['working_capital_change'])
	
	# Multi-stage growth rates
	growth_y1 = float(company_data['growth_rate_y1'])
	growth_y2 = float(company_data['growth_rate_y2'])
	growth_y3 = float(company_data['growth_rate_y3'])
	terminal_growth = float(company_data['terminal_growth'])
	
	tax_rate = float(company_data['tax_rate'])
	shares = float(company_data['shares_outstanding'])
	debt = float(company_data['debt'])
	cash = float(company_data['cash'])
	market_cap = float(company_data['market_cap_estimate'])
	
	# Risk parameters
	beta = float(company_data['beta'])
	rf_rate = float(company_data['risk_free_rate'])
	mrp = float(company_data['market_risk_premium'])
	country_risk = float(company_data['country_risk_premium'])
	size_premium = float(company_data['size_premium'])
	
	# Comparable multiples
	comp_ev_ebitda = float(company_data['comparable_ev_ebitda'])
	comp_pe = float(company_data['comparable_pe'])
	comp_peg = float(company_data['comparable_peg'])
	
	print(f"\n{'=' * 80}")
	print(f"{name} - COMPREHENSIVE VALUATION ANALYSIS")
	print(f"Sector: {sector}")
	print(f"{'=' * 80}")
	
	# Calculate WACC
	leverage_penalty  = float(company_data.get('leverage_wacc_penalty', 0))
	interest_expense  = float(company_data.get('interest_expense', 0) or 0)
	operating_income  = float(company_data.get('operating_income', 0) or 0)
	wacc, cost_of_equity, cost_of_debt = calculate_wacc(
		rf_rate, beta, mrp, debt, cash, market_cap, tax_rate, country_risk, size_premium,
		leverage_penalty=leverage_penalty,
		interest_expense=interest_expense,
		operating_income=operating_income,
	)

	# Apply guardrails (clamp WACC and terminal growth to safe ranges)
	wacc = max(Config.WACC_MIN, min(Config.WACC_MAX, wacc))
	terminal_growth = max(Config.TERMINAL_GROWTH_MIN, min(Config.TERMINAL_GROWTH_MAX, terminal_growth))
	
	print(f"\n--- Cost of Capital Analysis ---")
	print(f"  Risk-Free Rate:        {rf_rate*100:.2f}%")
	print(f"  Beta:                  {beta:.2f}")
	print(f"  Market Risk Premium:   {mrp*100:.2f}%")
	print(f"  Size Premium:          {size_premium*100:.2f}%")
	print(f"  Cost of Equity (CAPM): {cost_of_equity*100:.2f}%")
	print(f"  Cost of Debt:          {cost_of_debt*100:.2f}%")
	print(f"  WACC:                  {wacc*100:.2f}%")
	
	# 10-Year DCF Projection
	print(f"\n--- 10-Year DCF Projection ---")
	print(f"{'Year':<6} {'Revenue':>15} {'EBITDA':>15} {'NOPAT':>15} {'FCF':>15} {'PV of FCF':>15}")
	print("-" * 81)
	
	projected_fcf = []
	projection_details = []
	total_pv_fcf = 0
	current_revenue = revenue

	# Define growth schedule (10 years) - gradual step-down to terminal rate
	growth_schedule = [
		growth_y1, growth_y1, growth_y2, growth_y2, growth_y3,
		growth_y3, (growth_y3 + terminal_growth)/2, terminal_growth + 0.01,
		terminal_growth + 0.005, terminal_growth
	]

	base_revenue = revenue  # Store for WC scaling
	for year in range(1, 11):
		growth_rate = growth_schedule[year-1]
		current_revenue *= (1 + growth_rate)

		# CapEx taper: Y1-2 raw, Y3-10 linearly interpolate to normalized
		if year <= 2:
			year_capex_pct = raw_capex_pct
		else:
			t = (year - 2) / 8  # 0.125 at Y3 → 1.0 at Y10
			year_capex_pct = raw_capex_pct + (normalized_capex_pct - raw_capex_pct) * t

		year_ebitda = current_revenue * (ebitda / revenue)
		year_da = current_revenue * (depreciation / revenue)
		year_ebit = year_ebitda - year_da
		year_nopat = year_ebit * (1 - tax_rate)
		year_capex = current_revenue * year_capex_pct
		year_wc = wc_change * (current_revenue / base_revenue)  # WC scales with revenue
		year_fcf = year_nopat + year_da - year_capex - year_wc

		discount_factor = 1 / ((1 + wacc) ** year)
		pv_fcf = year_fcf * discount_factor
		total_pv_fcf += pv_fcf

		projected_fcf.append(year_fcf)
		projection_details.append({
			'year': year,
			'growth_rate': growth_rate,
			'revenue': current_revenue,
			'ebitda': year_ebitda,
			'da': year_da,
			'ebit': year_ebit,
			'nopat': year_nopat,
			'capex': year_capex,
			'wc_change': year_wc,
			'fcf': year_fcf,
			'discount_factor': discount_factor,
			'pv_fcf': pv_fcf,
		})

		print(f"{year:<6} ${current_revenue:>14,.0f} ${year_ebitda:>14,.0f} ${year_nopat:>14,.0f} ${year_fcf:>14,.0f} ${pv_fcf:>14,.0f}")
	
	# Terminal Value
	terminal_fcf = projected_fcf[-1] * (1 + terminal_growth)
	
	if wacc <= terminal_growth:
		print(f"\n⚠️  Warning: WACC ({wacc*100:.2f}%) must be greater than terminal growth ({terminal_growth*100:.2f}%)")
		terminal_growth = min(terminal_growth, wacc - 0.01)
	
	terminal_value = terminal_fcf / (wacc - terminal_growth)
	pv_terminal_value = terminal_value / ((1 + wacc) ** 10)
	
	print(f"\n--- Terminal Value Calculation ---")
	print(f"  Terminal FCF (Year 11):     ${terminal_fcf:,.0f}")
	print(f"  Terminal Growth Rate:       {terminal_growth*100:.2f}%")
	print(f"  Terminal Value:             ${terminal_value:,.0f}")
	print(f"  PV of Terminal Value:       ${pv_terminal_value:,.0f}")
	
	# Enterprise and Equity Value
	dcf_enterprise_value = total_pv_fcf + pv_terminal_value
	dcf_equity_value = dcf_enterprise_value + cash - debt
	dcf_price_per_share = dcf_equity_value / shares
	
	print(f"\n--- DCF Valuation Summary ---")
	print(f"  PV of 10-Year FCF:          ${total_pv_fcf:,.0f}")
	print(f"  PV of Terminal Value:       ${pv_terminal_value:,.0f}")
	print(f"  Enterprise Value (DCF):     ${dcf_enterprise_value:,.0f}")
	print(f"  + Cash:                     ${cash:,.0f}")
	print(f"  - Debt:                     ${debt:,.0f}")
	print(f"  Equity Value (DCF):         ${dcf_equity_value:,.0f}")
	print(f"  Shares Outstanding:         {shares:,.0f}")
	print(f"  DCF Price per Share:        ${dcf_price_per_share:,.2f}")
	
	# Comparable Company Analysis
	print(f"\n--- Comparable Company Valuation ---")
	
	comp_ev_method = ebitda * comp_ev_ebitda
	comp_equity_ev = comp_ev_method - debt + cash
	
	profit = revenue * profit_margin
	comp_pe_method = profit * comp_pe
	
	current_pe = dcf_equity_value / profit if profit > 0 else 0
	implied_peg = current_pe / growth_y1 if growth_y1 > 0 else 0
	
	print(f"  Industry EV/EBITDA Multiple:  {comp_ev_ebitda:.1f}x")
	print(f"  Implied EV (EV/EBITDA):       ${comp_ev_method:,.0f}")
	print(f"  Implied Equity Value:         ${comp_equity_ev:,.0f}")
	print(f"  ")
	print(f"  Industry P/E Multiple:        {comp_pe:.1f}x")
	print(f"  Implied Value (P/E):          ${comp_pe_method:,.0f}")
	print(f"  ")
	print(f"  Company P/E (DCF-based):      {current_pe:.1f}x")
	print(f"  Company PEG Ratio:            {implied_peg:.2f}")
	print(f"  Industry PEG:                 {comp_peg:.2f}")
	
	# Adaptive blend weights from ML calibration layer
	if _ML_AVAILABLE and 'blend_weights' in company_data:
		bw = _ml.get_blend_weights(
			company_data.get('company_type', 'STABLE_VALUE'),
			dcf_equity_value
		)
		weight_dcf = bw['dcf']
		weight_ev_ebitda = bw['ev']
		weight_pe = bw['pe']
	else:
		w = Config.VALUATION_WEIGHTS
		weight_dcf = w.get('dcf', 0.45)
		weight_ev_ebitda = w.get('ev_ebitda', 0.30)
		weight_pe = w.get('pe', 0.25)

	final_equity_value = (
		dcf_equity_value * weight_dcf +
		comp_equity_ev * weight_ev_ebitda +
		comp_pe_method * weight_pe
	)
	final_price_per_share = final_equity_value / shares

	# Analyst consensus anchor + ML correction
	if _ML_AVAILABLE:
		analyst_target = company_data.get('analyst_target')
		company_type = company_data.get('company_type', 'STABLE_VALUE')
		final_price_per_share = _ml.apply_analyst_anchor(
			final_price_per_share, analyst_target, company_type, company_data
		)
		final_price_per_share = _ml.apply_ml_correction(final_price_per_share, company_data)
		# B2-5: Sanity guardrail — catches data anomalies (DKS $1381, TPR $44)
		current_market_price = company_data.get('current_price', 0)
		final_price_per_share, _flagged = _ml.apply_sanity_guardrail(
			final_price_per_share, analyst_target, current_market_price
		)
		final_equity_value = final_price_per_share * shares
	
	# Calculate comprehensive ratios
	fcf_current = projected_fcf[0]
	ratios = calculate_financial_ratios(
		revenue, ebitda, profit, debt, cash, final_equity_value, shares, fcf_current
	)
	
	print(f"\n--- Financial Ratios & Metrics ---")
	print(f"  Enterprise Value:             ${ratios['ev']:,.0f}")
	print(f"  EV/EBITDA:                    {ratios['ev_ebitda']:.1f}x")
	print(f"  EV/Revenue:                   {ratios['ev_revenue']:.1f}x")
	print(f"  P/E Ratio:                    {ratios['pe']:.1f}x")
	print(f"  FCF Yield:                    {ratios['fcf_yield']:.2f}%")
	print(f"  ")
	print(f"  EBITDA Margin:                {ratios['ebitda_margin']:.1f}%")
	print(f"  Net Margin:                   {ratios['profit_margin']:.1f}%")
	print(f"  ROE:                          {ratios['roe']:.1f}%")
	print(f"  ROIC:                         {ratios['roic']:.1f}%")
	print(f"  ")
	print(f"  Debt/Equity:                  {ratios['debt_to_equity']:.2f}x")
	print(f"  Net Debt/EBITDA:              {ratios['net_debt_to_ebitda']:.2f}x")
	print(f"  Interest Coverage:            {ratios['interest_coverage']:.1f}x")
	
	# Altman Z-Score
	z_score, z_zone = altman_z_score(revenue, ebitda, final_equity_value, debt, wc_change)
	print(f"\n--- Credit Analysis ---")
	print(f"  Altman Z-Score:               {z_score:.2f} ({z_zone})")
	
	# Sensitivity Analysis
	print(f"\n--- Sensitivity Analysis: Terminal Value Impact ---")
	print(f"  {'Discount Rate →':<18}", end="")
	dr_range = [wacc - 0.02, wacc - 0.01, wacc, wacc + 0.01, wacc + 0.02]
	for dr in dr_range:
		print(f"{dr*100:>10.1f}%", end="")
	print()
	
	tg_range = [terminal_growth - 0.01, terminal_growth - 0.005, terminal_growth, terminal_growth + 0.005, terminal_growth + 0.01]
	for tg in tg_range:
		print(f"  TG {tg*100:>4.1f}%  ", end="")
		for dr in dr_range:
			if dr <= tg:
				print(f"{'N/A':>10}", end="")
			else:
				tv = terminal_fcf / (dr - tg)
				pv_tv = tv / ((1 + dr) ** 10)
				ev = total_pv_fcf + pv_tv
				eq = ev + cash - debt
				print(f"${eq/1000000:>9.1f}M", end="")
		print()
	
	# Monte Carlo Simulation
	mc_results = monte_carlo_valuation(final_equity_value, None, None, 1000)
	
	print(f"\n--- Monte Carlo Simulation (1,000 iterations) ---")
	print(f"  Mean Valuation:               ${mc_results['mean']:,.0f}")
	print(f"  Median Valuation:             ${mc_results['median']:,.0f}")
	print(f"  Standard Deviation:           ${mc_results['std']:,.0f}")
	print(f"  10th Percentile:              ${mc_results['p10']:,.0f}")
	print(f"  90th Percentile:              ${mc_results['p90']:,.0f}")
	
	# Final Valuation Summary
	print(f"\n{'=' * 80}")
	print(f"FINAL VALUATION & INVESTMENT RECOMMENDATION")
	print(f"{'=' * 80}")
	
	print(f"\n  Valuation Method Breakdown:")
	print(f"    DCF Value (50% weight):           ${dcf_equity_value:,.0f}")
	print(f"    EV/EBITDA Value (25% weight):     ${comp_equity_ev:,.0f}")
	print(f"    P/E Value (25% weight):           ${comp_pe_method:,.0f}")
	print(f"  ")
	print(f"  FAIR VALUE (Weighted Average):      ${final_equity_value:,.0f}")
	print(f"  Fair Value per Share:               ${final_price_per_share:,.2f}")
	print(f"  ")
	print(f"  Current Market Cap:                 ${market_cap:,.0f}")
	print(f"  Current Price per Share:            ${market_cap/shares:,.2f}")
	print(f"  ")
	
	upside = ((final_equity_value - market_cap) / market_cap) * 100
	print(f"  Upside/(Downside):                  {upside:+.1f}%")
	
	# Investment Recommendation (configurable thresholds)
	th = Config.RECOMMENDATION_THRESHOLDS
	if upside > th.get('strong_buy', 20):
		recommendation = "STRONG BUY"
		target_price = final_price_per_share
	elif upside > th.get('buy', 10):
		recommendation = "BUY"
		target_price = final_price_per_share
	elif upside > th.get('hold', -10):
		recommendation = "HOLD"
		target_price = final_price_per_share
	elif upside > th.get('underweight', -20):
		recommendation = "UNDERWEIGHT"
		target_price = final_price_per_share
	else:
		recommendation = "SELL"
		target_price = final_price_per_share

	# Safety overrides and downgrades
	# Altman Z-score severe distress -> force SELL or downgrade
	try:
		if z_score < Config.ALT_ZSCORE_SELL_THRESHOLD:
			# Downgrade by one notch toward SELL
			order = ["STRONG BUY", "BUY", "HOLD", "UNDERWEIGHT", "SELL"]
			if recommendation in order and recommendation != "SELL":
				idx = order.index(recommendation)
				recommendation = order[min(idx + 1, len(order) - 1)]
	except Exception:
		# If anything goes wrong with override logic, continue with base rec
		pass

	# Debt/Equity high -> downgrade one notch
	try:
		if ratios.get('debt_to_equity', 0) > Config.DEBT_EQUITY_DOWNGRADE:
			order = ["STRONG BUY", "BUY", "HOLD", "UNDERWEIGHT", "SELL"]
			if recommendation in order and recommendation != "SELL":
				idx = order.index(recommendation)
				recommendation = order[min(idx + 1, len(order) - 1)]
	except Exception:
		pass
	
	print(f"  ")
	print(f"  RECOMMENDATION:                     {recommendation}")
	print(f"  Target Price (12-month):            ${target_price:,.2f}")
	print(f"  ")
	# Phase 4 — real bear/base/bull driven by perturbations of the actual
	# valuation inputs (WACC ±100bp, terminal growth ±100bp, growth Y1 ±25%),
	# not a cosmetic 0.75×/1.25× blanket multiplier.
	from valuation.scenarios import compute_scenarios
	scenarios = compute_scenarios(
		revenue=revenue, ebitda=ebitda, depreciation=depreciation,
		raw_capex_pct=raw_capex_pct, normalized_capex_pct=normalized_capex_pct,
		wc_change=wc_change, tax_rate=tax_rate,
		shares=shares, debt=debt, cash=cash,
		wacc=wacc, terminal_growth=terminal_growth, growth_y1=growth_y1,
		comp_ev_equity=comp_equity_ev, comp_pe_equity=comp_pe_method,
		weight_dcf=weight_dcf, weight_ev=weight_ev_ebitda, weight_pe=weight_pe,
	)
	print(f"  Valuation Range (driver-based perturbations):")
	for nm in ('bear', 'base', 'bull'):
		s = scenarios[nm]
		print(f"    {nm.capitalize():4s}  WACC={s['wacc']*100:.2f}%  TG={s['terminal_growth']*100:.2f}%  gY1={s['growth_y1']*100:.2f}%  →  ${s['blended_equity_value']:,.0f} (${s['blended_price_per_share']:.2f}/share)")
	print(f"    Spread (bull−bear)/base = {scenarios['spread_pct']:.1f}%")
	
	print(f"{'=' * 80}\n")
	
	# Log prediction for ML training pipeline
	if _ML_AVAILABLE:
		company_data['dcf_price_per_share'] = dcf_price_per_share
		company_data['ev_price_per_share'] = comp_equity_ev / shares if shares > 0 else 0
		company_data['pe_price_per_share'] = comp_pe_method / shares if shares > 0 else 0
		company_data['wacc'] = wacc
		_ml.log_prediction(
			company_data.get('ticker', name),
			final_price_per_share, company_data
		)

	return {
		'name': name,
		'sector': sector,
		'dcf_equity_value': dcf_equity_value,
		'dcf_price_per_share': dcf_price_per_share,
		'comp_ev_value': comp_equity_ev,
		'comp_pe_value': comp_pe_method,
		'final_equity_value': final_equity_value,
		'final_price_per_share': final_price_per_share,
		'market_cap': market_cap,
		'current_price': market_cap / shares,
		'upside_pct': upside,
		'recommendation': recommendation,
		'wacc': wacc,
		'ev_ebitda': ratios['ev_ebitda'],
		'pe_ratio': ratios['pe'],
		'fcf_yield': ratios['fcf_yield'],
		'roe': ratios['roe'],
		'roic': ratios['roic'],
		'debt_to_equity': ratios['debt_to_equity'],
		'z_score': z_score,
		'mc_p10': mc_results['p10'],
		'sub_sector_tag': company_data.get('sub_sector_tag'),
		'company_type': company_data.get('company_type'),
		'ebitda_method': company_data.get('ebitda_method'),
		'analyst_target': company_data.get('analyst_target'),
		'mc_p90': mc_results['p90'],
		'scenarios': scenarios,   # Phase 4: driver-based bear/base/bull triple
		'dcf_details': {
			'ticker': company_data.get('ticker', ''),
			'inputs': {
				'revenue': {
					'value': revenue,
					'source': 'yahoo_finance',
					'url_path': '/financials',
					'label': 'Total Revenue (TTM)',
				},
				'ebitda': {
					'value': ebitda,
					'source': 'yahoo_finance',
					'url_path': '/financials',
					'label': 'EBITDA',
				},
				'depreciation': {
					'value': depreciation,
					'source': 'yahoo_finance',
					'url_path': '/cash-flow',
					'label': 'Depreciation & Amortization',
				},
				'cash': {
					'value': cash,
					'source': 'yahoo_finance',
					'url_path': '/balance-sheet',
					'label': 'Cash & Cash Equivalents',
				},
				'debt': {
					'value': debt,
					'source': 'yahoo_finance',
					'url_path': '/balance-sheet',
					'label': 'Total Debt',
				},
				'shares_outstanding': {
					'value': shares,
					'source': 'yahoo_finance',
					'url_path': '/key-statistics',
					'label': 'Shares Outstanding',
				},
				'beta': {
					'value': beta,
					'source': 'yahoo_finance',
					'url_path': '/key-statistics',
					'label': 'Beta (5Y Monthly)',
				},
				'market_cap': {
					'value': market_cap,
					'source': 'yahoo_finance',
					'url_path': '',
					'label': 'Market Cap',
				},
			},
			'assumptions': {
				'risk_free_rate': {
					'value': rf_rate,
					'source': 'fred',
					'label': '10-Year Treasury Rate',
					'note': 'US Treasury yield as of valuation date',
				},
				'market_risk_premium': {
					'value': mrp,
					'source': 'assumption',
					'label': 'Equity Risk Premium',
					'note': 'Historical average excess return of stocks over bonds',
				},
				'terminal_growth': {
					'value': terminal_growth,
					'source': 'assumption',
					'label': 'Terminal Growth Rate',
					'note': 'Long-term GDP growth proxy, capped at WACC - 1%',
				},
				'tax_rate': {
					'value': tax_rate,
					'source': 'yahoo_finance',
					'url_path': '/financials',
					'label': 'Effective Tax Rate',
				},
			},
			'calculated': {
				'cost_of_equity': {
					'value': cost_of_equity,
					'formula': 'Rf + β × MRP',
					'result': f'{cost_of_equity*100:.2f}%',
					'components': {
						'rf': rf_rate,
						'beta': beta,
						'mrp': mrp,
					},
				},
				'cost_of_debt': {
					'value': cost_of_debt,
					'formula': 'Rf + Credit Spread',
					'result': f'{cost_of_debt*100:.2f}%',
					'components': {
						'rf': rf_rate,
						'credit_spread': cost_of_debt - rf_rate,
					},
					'note': 'Credit spread from Damodaran synthetic rating based on interest coverage',
				},
				'wacc': {
					'value': wacc,
					'formula': '(E/V × Re) + (D/V × Rd × (1-T))',
					'result': f'{wacc*100:.2f}%',
					'components': {
						'weight_equity': market_cap / (max(0, debt - cash) + market_cap) if (max(0, debt - cash) + market_cap) > 0 else 1,
						'weight_debt': max(0, debt - cash) / (max(0, debt - cash) + market_cap) if (max(0, debt - cash) + market_cap) > 0 else 0,
						'cost_of_equity': cost_of_equity,
						'cost_of_debt': cost_of_debt,
						'tax_rate': tax_rate,
					},
				},
				'terminal_value': {
					'value': terminal_value,
					'formula': f'FCF₁₀ × (1+g) / (WACC-g) = ${terminal_fcf/1e9:.1f}B / ({wacc*100:.2f}% - {terminal_growth*100:.2f}%)',
					'result': f'${terminal_value/1e9:.1f}B',
				},
				'pv_terminal_value': {
					'value': pv_terminal_value,
					'formula': f'TV / (1+WACC)^10 = ${terminal_value/1e9:.1f}B / (1+{wacc*100:.2f}%)^10',
					'result': f'${pv_terminal_value/1e9:.1f}B',
				},
				'enterprise_value': {
					'value': dcf_enterprise_value,
					'formula': 'PV(FCF) + PV(Terminal Value)',
					'components': {
						'pv_fcf': total_pv_fcf,
						'pv_terminal': pv_terminal_value,
					},
					'result': f'${dcf_enterprise_value/1e9:.1f}B',
				},
				'equity_value': {
					'value': dcf_equity_value,
					'formula': 'Enterprise Value + Cash - Debt',
					'components': {
						'enterprise_value': dcf_enterprise_value,
						'cash': cash,
						'debt': debt,
					},
					'result': f'${dcf_equity_value/1e9:.1f}B',
				},
				'price_per_share': {
					'value': dcf_price_per_share,
					'formula': f'Equity Value / Shares = ${dcf_equity_value/1e9:.1f}B / {shares/1e9:.2f}B',
					'result': f'${dcf_price_per_share:.2f}',
				},
			},
			'projection': {
				'years': list(range(1, 11)),
				'details': projection_details,
				'total_pv_fcf': total_pv_fcf,
				'terminal_fcf': terminal_fcf,
				'terminal_value': terminal_value,
				'pv_terminal_value': pv_terminal_value,
			},
			'base_inputs': {
				'revenue': revenue,
				'ebitda': ebitda,
				'ebitda_margin': ebitda / revenue if revenue > 0 else 0,
				'depreciation': depreciation,
				'da_ratio': depreciation / revenue if revenue > 0 else 0,
				'tax_rate': tax_rate,
				'capex_pct': capex_pct,
				'wc_change': wc_change,
				'cash': cash,
				'debt': debt,
				'shares': shares,
				'market_cap': market_cap,
				'growth_y1': growth_y1,
				'growth_y2': growth_y2,
				'growth_y3': growth_y3,
				'terminal_growth': terminal_growth,
				'rf_rate': rf_rate,
				'beta': beta,
				'mrp': mrp,
				'wacc': wacc,
				'cost_of_equity': cost_of_equity,
				'cost_of_debt': cost_of_debt,
			},
		},
		'ev_ebitda_details': {
			'ticker': company_data.get('ticker', ''),
			'inputs': {
				'ebitda': {
					'value': ebitda,
					'source': 'yahoo_finance',
					'url_path': '/financials',
					'label': 'EBITDA (TTM)',
				},
				'debt': {
					'value': debt,
					'source': 'yahoo_finance',
					'url_path': '/balance-sheet',
					'label': 'Total Debt',
				},
				'cash': {
					'value': cash,
					'source': 'yahoo_finance',
					'url_path': '/balance-sheet',
					'label': 'Cash & Equivalents',
				},
				'shares_outstanding': {
					'value': shares,
					'source': 'yahoo_finance',
					'url_path': '/key-statistics',
					'label': 'Shares Outstanding',
				},
			},
			'assumptions': {
				'ev_ebitda_multiple': {
					'value': comp_ev_ebitda,
					'source': 'industry_comps',
					'label': 'EV/EBITDA Multiple',
					'note': f'Based on {sector} sector comparable companies',
				},
			},
			'calculated': {
				'implied_ev': {
					'value': comp_ev_method,
					'formula': f'EBITDA × Multiple = ${ebitda/1e9:.1f}B × {comp_ev_ebitda:.1f}x',
					'result': f'${comp_ev_method/1e9:.1f}B',
				},
				'implied_equity': {
					'value': comp_equity_ev,
					'formula': f'EV + Cash - Debt = ${comp_ev_method/1e9:.1f}B + ${cash/1e9:.1f}B - ${debt/1e9:.1f}B',
					'result': f'${comp_equity_ev/1e9:.1f}B',
				},
				'price_per_share': {
					'value': comp_equity_ev / shares if shares > 0 else 0,
					'formula': f'Equity / Shares = ${comp_equity_ev/1e9:.1f}B / {shares/1e9:.2f}B',
					'result': f'${comp_equity_ev / shares if shares > 0 else 0:.2f}',
				},
			},
			'base_inputs': {
				'ebitda': ebitda,
				'ev_ebitda_multiple': comp_ev_ebitda,
				'debt': debt,
				'cash': cash,
				'shares': shares,
				'sector': sector,
			},
		},
		'pe_details': {
			'ticker': company_data.get('ticker', ''),
			'inputs': {
				'net_income': {
					'value': profit,
					'source': 'yahoo_finance',
					'url_path': '/financials',
					'label': 'Net Income (TTM)',
				},
				'shares_outstanding': {
					'value': shares,
					'source': 'yahoo_finance',
					'url_path': '/key-statistics',
					'label': 'Shares Outstanding',
				},
			},
			'assumptions': {
				'pe_multiple': {
					'value': comp_pe,
					'source': 'industry_comps',
					'label': 'P/E Multiple',
					'note': f'Based on {sector} sector comparable companies',
				},
			},
			'calculated': {
				'implied_market_cap': {
					'value': comp_pe_method,
					'formula': f'Net Income × P/E = ${profit/1e9:.1f}B × {comp_pe:.1f}x',
					'result': f'${comp_pe_method/1e9:.1f}B',
				},
				'price_per_share': {
					'value': comp_pe_method / shares if shares > 0 else 0,
					'formula': f'Market Cap / Shares = ${comp_pe_method/1e9:.1f}B / {shares/1e9:.2f}B',
					'result': f'${comp_pe_method / shares if shares > 0 else 0:.2f}',
				},
			},
			'base_inputs': {
				'net_income': profit,
				'pe_multiple': comp_pe,
				'shares': shares,
				'sector': sector,
			},
		},
		'blend_weights': {
			'dcf': weight_dcf,
			'ev_ebitda': weight_ev_ebitda,
			'pe': weight_pe,
		},
	}

def process_enhanced_csv(filename):
	"""Process enhanced CSV with comprehensive valuation"""
	results = []
	
	try:
		with open(filename, 'r') as file:
			reader = csv.DictReader(file)
			companies = list(reader)
		
		print("=" * 80)
		print(f"PROCESSING {len(companies)} COMPANIES - ENHANCED CFA-LEVEL ANALYSIS")
		print("=" * 80)
		
		for i, company in enumerate(companies, 1):
			print(f"\n[{i}/{len(companies)}] Processing {company.get('name', 'Unknown')}...")
			result = enhanced_dcf_valuation(company)
			results.append(result)

			# Auto-continue without requiring user input
			print(f"\n[{i}/{len(companies)}] Completed {company.get('name', 'Unknown')}")
		
		# Comprehensive Summary
		print("\n" + "=" * 120)
		print("PORTFOLIO VALUATION SUMMARY")
		print("=" * 120)
		print(f"{'Company':<25} {'Sector':<15} {'Fair Value':>15} {'Market Cap':>15} {'Upside':>10} {'Rec':>12} {'P/E':>8} {'ROE':>8}")
		print("-" * 120)
		
		for result in results:
			print(f"{result['name']:<25} {result['sector']:<15} ${result['final_equity_value']:>14,.0f} "
			      f"${result['market_cap']:>14,.0f} {result['upside_pct']:>9.1f}% {result['recommendation']:>12} "
			      f"{result['pe_ratio']:>7.1f}x {result['roe']:>7.1f}%")
		
		print("=" * 120)
		
		# Save comprehensive results
		output_filename = filename.replace('.csv', '_enhanced_results.csv')
		with open(output_filename, 'w', newline='') as csv_out:
			if results:
				fieldnames = list(results[0].keys())
				writer = csv.DictWriter(csv_out, fieldnames=fieldnames)
				writer.writeheader()
				for result in results:
					writer.writerow(result)
		
		print(f"\n✓ Enhanced results saved to: {output_filename}")
		
	except FileNotFoundError:
		print(f"Error: File '{filename}' not found.")
	except Exception as e:
		print(f"Error processing CSV: {e}")
		import traceback
		traceback.print_exc()

# Main program
if __name__ == "__main__":
    import sys

    print("=" * 80)
    print("     CFA-LEVEL COMPANY VALUATION TOOL")
    print("     Professional DCF, Comparables & Risk Analysis")
    print("=" * 80)

    # Accept filename from command line or use default
    if len(sys.argv) > 1:
        csv_file = sys.argv[1]
    else:
        csv_file = "companies_enhanced.csv"

    print(f"\nProcessing file: {csv_file}")

    try:
        process_enhanced_csv(csv_file)
    except OSError as e:
        print(f"Error: Unable to process file due to {e}")
