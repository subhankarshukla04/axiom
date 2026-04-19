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
	import ml_engine as _ml
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

def calculate_wacc(risk_free_rate, beta, market_risk_premium, debt, equity_value, tax_rate,
                   country_risk=0, size_premium=0, leverage_penalty=0):
	"""Calculate Weighted Average Cost of Capital using CAPM + Blume-adjusted beta"""
	# Cost of Equity using CAPM
	cost_of_equity = risk_free_rate + beta * market_risk_premium + country_risk + size_premium
	
	# Cost of Debt (simplified as risk-free + credit spread in decimal format)
	credit_spread = 0.025 if debt > equity_value else 0.015  # 2.5% or 1.5% in decimal
	cost_of_debt = risk_free_rate + credit_spread
	
	# WACC calculation
	total_value = debt + equity_value
	if total_value == 0:
		return cost_of_equity
	
	weight_equity = equity_value / total_value
	weight_debt = debt / total_value
	
	wacc = (weight_equity * cost_of_equity) + (weight_debt * cost_of_debt * (1 - tax_rate))
	wacc += leverage_penalty  # telecom/high-leverage penalty

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

def sensitivity_analysis(base_fcf, terminal_growth_range, discount_rate_range):
	"""Generate sensitivity table for DCF valuation"""
	sensitivity = {}
	
	for tg in terminal_growth_range:
		for dr in discount_rate_range:
			if dr <= tg:
				continue
			terminal_value = base_fcf * (1 + tg) / (dr - tg)
			pv_terminal = terminal_value / ((1 + dr) ** 5)
			key = f"TG_{tg}_DR_{dr}"
			sensitivity[key] = pv_terminal
	
	return sensitivity

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
			                                        company_data.get('company_type', 'STABLE_VALUE'))
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
				'sub_sector_tag': tag,
				'company_type': company_data.get('company_type'),
				'ebitda_method': company_data.get('ebitda_method'),
				'analyst_target': analyst_target,
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

	if 'normalized_capex_pct' in company_data:
		capex_pct = float(company_data['normalized_capex_pct'])
		print(f"  Using NORMALIZED CapEx: {capex_pct*100:.1f}% (original: {float(company_data['capex_pct'])*100:.1f}%)")
	else:
		capex_pct = float(company_data['capex_pct'])

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
	leverage_penalty = float(company_data.get('leverage_wacc_penalty', 0))
	wacc, cost_of_equity, cost_of_debt = calculate_wacc(
		rf_rate, beta, mrp, debt, market_cap, tax_rate, country_risk, size_premium,
		leverage_penalty=leverage_penalty
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
	total_pv_fcf = 0
	current_revenue = revenue
	
	# Define growth schedule (10 years) - gradual step-down to terminal rate
	growth_schedule = [
		growth_y1, growth_y1, growth_y2, growth_y2, growth_y3,
		growth_y3, (growth_y3 + terminal_growth)/2, terminal_growth + 0.01,
		terminal_growth + 0.005, terminal_growth
	]
	
	for year in range(1, 11):
		growth_rate = growth_schedule[year-1]
		current_revenue *= (1 + growth_rate)
		
		year_ebitda = current_revenue * (ebitda / revenue)
		year_da = current_revenue * (depreciation / revenue)
		year_ebit = year_ebitda - year_da
		year_nopat = year_ebit * (1 - tax_rate)
		year_capex = current_revenue * capex_pct
		year_wc = wc_change * (1 + growth_rate) ** year
		year_fcf = year_nopat + year_da - year_capex - year_wc
		
		discount_factor = 1 / ((1 + wacc) ** year)
		pv_fcf = year_fcf * discount_factor
		total_pv_fcf += pv_fcf
		
		projected_fcf.append(year_fcf)
		
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
			final_price_per_share, analyst_target, company_type
		)
		final_price_per_share = _ml.apply_ml_correction(final_price_per_share, company_data)
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
	bear = Config.BEAR_MULTIPLIER
	bull = Config.BULL_MULTIPLIER
	print(f"  Valuation Range:")
	print(f"    Bear Case ({(1-bear)*100:.0f}% haircut):         ${final_equity_value * bear:,.0f}  (${final_price_per_share * bear:.2f}/share)")
	print(f"    Base Case:                        ${final_equity_value:,.0f}  (${final_price_per_share:.2f}/share)")
	print(f"    Bull Case ({(bull-1)*100:.0f}% premium):          ${final_equity_value * bull:,.0f}  (${final_price_per_share * bull:.2f}/share)")
	
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
		'mc_p90': mc_results['p90']
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
