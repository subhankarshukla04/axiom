# Data Source Audit & Reliability Report

## Executive Summary

**Primary Data Source**: Yahoo Finance API (via `yfinance` Python library)
**Reliability**: ⚠️ **MIXED** - Some data highly reliable, some data uses fallbacks/estimates
**Last Audited**: December 20, 2025

---

## Data Sources Breakdown

### 1. **Company Basic Information** ✅ RELIABLE

**Source**: Yahoo Finance `stock.info` API
**Data Points**:
- Company Name: `info.get('longName')`
- Ticker Symbol: `info.get('symbol')`
- Sector: `info.get('sector')`
- Industry: `info.get('industry')`

**Reliability**: ✅ **HIGH** - Direct from exchange filings
**Update Frequency**: Real-time via Yahoo Finance
**Fallback**: None needed (ticker validation ensures this exists)

---

### 2. **Market Pricing Data** ✅ RELIABLE

**Source**: Yahoo Finance `stock.info` + `stock.history()`
**Data Points**:
- Current Price: `info.get('currentPrice')` or `info.get('regularMarketPrice')`
- Market Cap: `info.get('marketCap')`
- Shares Outstanding: `info.get('sharesOutstanding')`

**Reliability**: ✅ **HIGH** - Real-time market data from exchanges
**Update Frequency**: Daily at market close (4:00 PM ET)
**Fallback**: If `currentPrice` is null, uses `regularMarketPrice`

**⚠️ ISSUE**: Shares outstanding may be stale (from last 10-Q filing)
**Impact**: Market cap calculation could be slightly off if company recently did stock split/buyback

---

### 3. **Financial Statements** ⚠️ MODERATE RELIABILITY

#### Income Statement (from `stock.financials`)
**Source**: Yahoo Finance fundamental data
**Data Points**:
- Revenue: `financials['Total Revenue']`
- EBITDA: `financials['EBITDA']`
- Net Income: `financials['Net Income']`
- Pretax Income: `financials['Pretax Income']`
- Tax Provision: `financials['Tax Provision']`

**Reliability**: ⚠️ **MODERATE** - Based on last filed 10-K/10-Q
**Update Frequency**: Quarterly (after earnings releases)
**Fallback**:
- If `financials` DataFrame is empty: Uses `info.get('totalRevenue')`, `info.get('ebitda')`
- If both fail: Profit margin defaults to 10%

**⚠️ ISSUES**:
1. Data can be **3-6 months stale** (last quarterly filing)
2. Yahoo Finance sometimes has **data quality issues** (missing/incorrect values)
3. Fallback to `info` may not have complete data

---

#### Balance Sheet (from `stock.balance_sheet`)
**Source**: Yahoo Finance fundamental data
**Data Points**:
- Total Debt: `balance_sheet['Total Debt']` or `balance_sheet['Long Term Debt']`
- Cash: `balance_sheet['Cash And Cash Equivalents']`

**Reliability**: ⚠️ **MODERATE** - Based on last filed 10-K/10-Q
**Fallback**:
- Uses `info.get('totalDebt')`, `info.get('totalCash')` if balance sheet empty
- Defaults to 0 if both fail

**⚠️ ISSUES**:
1. Debt levels can change significantly between filings (new bonds, pay down)
2. Cash balances highly volatile (M&A, dividends, buybacks)

---

#### Cash Flow Statement (from `stock.cashflow`)
**Source**: Yahoo Finance fundamental data
**Data Points**:
- Depreciation & Amortization: `cashflow['Depreciation And Amortization']`
- Capital Expenditure (CapEx): `cashflow['Capital Expenditure']`
- Working Capital Change: `cashflow['Change In Working Capital']`

**Reliability**: ⚠️ **MODERATE** - Based on last filed 10-K/10-Q
**Fallback**:
- Depreciation: Estimated as 5% of EBITDA if missing
- CapEx %: Defaults to 5% of revenue
- Working Capital: Defaults to 0

**⚠️ ISSUES**:
1. CapEx is highly variable (growth companies vs mature)
2. 5% default assumption may be **very wrong** for capital-intensive industries (utilities, manufacturing)
3. Working capital changes can be huge (seasonal businesses, rapid growth)

---

### 4. **Growth Rates** ❌ HIGHLY ESTIMATED

**Source**: Mixed - analyst estimates + historical trends
**Data Points**:
- Year 1 Growth: `info.get('revenueGrowth')` OR calculated from last 2 years of financials
- Year 2 Growth: Y1 × 0.85 (hardcoded formula)
- Year 3 Growth: Y1 × 0.70 (hardcoded formula)
- Terminal Growth: **0.025 (2.5%)** - HARDCODED

**Reliability**: ❌ **LOW** - Heavy assumptions
**Fallback**: Defaults to 10%, 8%, 6%, 2.5%

**🚨 CRITICAL ISSUES**:
1. **Analyst estimates (`revenueGrowth`)**: Only forward 1 year, may not exist for all stocks
2. **Declining growth formula (0.85x, 0.70x)**: Arbitrary, doesn't reflect company-specific dynamics
3. **Terminal growth 2.5%**: Assumes all companies revert to GDP growth - wrong for:
   - Declining industries (newspapers, brick-and-mortar retail)
   - Hyper-growth sectors that may sustain >GDP growth (AI, biotech)
4. **Historical revenue growth**: Only looks at 1 year, ignores multi-year trends

**RECOMMENDATION**: This is the WEAKEST part of the model. Should allow manual override.

---

### 5. **Tax Rate** ⚠️ MODERATE RELIABILITY

**Source**: Calculated from financial statements OR default
**Calculation**:
```python
effective_rate = Tax Provision / Pretax Income
# Capped between 0% and 35%
# Fallback: 21% (US federal corporate rate)
```

**Reliability**: ⚠️ **MODERATE** - Good if data available
**Fallback**: 21% default

**⚠️ ISSUES**:
1. Effective tax rate can vary wildly year-to-year (tax credits, one-time charges)
2. 21% default is **US-only** - wrong for international companies
3. Doesn't account for state taxes, foreign taxes, deferred tax assets

---

### 6. **Beta (Risk Measure)** ⚠️ MODERATE RELIABILITY

**Source**: Calculated from 5-year price history vs S&P 500
**Calculation**:
```python
# Regression of stock returns vs SPY (S&P 500 ETF) returns
beta = covariance(stock_returns, spy_returns) / variance(spy_returns)
# Bounded between -2.0 and 5.0
# Fallback: 1.0 (market beta)
```

**Reliability**: ⚠️ **MODERATE** - Standard industry practice
**Fallback**: 1.0 if insufficient history (<1 year)

**⚠️ ISSUES**:
1. Requires 5 years of history - **new IPOs default to 1.0**
2. Beta is **backward-looking** - doesn't capture business model changes
3. May not reflect current risk (company transformed, new management, etc.)
4. Uses SPY instead of appropriate benchmark (tech stocks should use QQQ, small caps should use IWM)

---

### 7. **Risk Premiums** ⚠️ FIXED ASSUMPTIONS

**Source**: Hardcoded in code
**Data Points**:
- Risk-Free Rate: **Fetched from 10-year Treasury (^TNX)**
- Market Risk Premium: **0.065 (6.5%)** - HARDCODED
- Country Risk Premium: **0.0 (assumes US)** - HARDCODED
- Size Premium: Based on market cap tiers

**Reliability**:
- Risk-Free Rate: ✅ **HIGH** (real-time treasury yield)
- Market Risk Premium: ⚠️ **FIXED** (doesn't change with market conditions)
- Size Premium: ⚠️ **SIMPLIFIED**

**Size Premium Tiers** (from code line 271-283):
```python
if market_cap < $1B:   size_premium = 3.0%
if market_cap < $5B:   size_premium = 2.0%
if market_cap < $25B:  size_premium = 1.0%
if market_cap >= $25B: size_premium = 0.0%
```

**⚠️ ISSUES**:
1. **Market Risk Premium 6.5%**: Historical average, but varies 4%-8% based on market conditions
2. **Country Risk Premium 0.0**: Wrong for international stocks (should add premium for emerging markets)
3. **Size premium**: Academic research shows this premium, but **tiers are arbitrary**

---

### 8. **Comparable Multiples** ❌ SECTOR AVERAGES (NOT REAL COMPS)

**Source**: Hardcoded sector averages
**Data Points**:
- EV/EBITDA: Calculated from company data, bounded by sector averages
- P/E Ratio: From `info.get('trailingPE')`, bounded by sector averages
- PEG Ratio: From `info.get('pegRatio')`, bounded

**Sector Multiples** (from code line 315-328):
```python
'Technology':            EV/EBITDA = 15.0, P/E = 25.0
'Healthcare':            EV/EBITDA = 14.0, P/E = 22.0
'Financial Services':    EV/EBITDA = 10.0, P/E = 15.0
'Consumer Cyclical':     EV/EBITDA = 10.0, P/E = 18.0
'Consumer Defensive':    EV/EBITDA = 11.0, P/E = 20.0
'Industrials':           EV/EBITDA = 10.0, P/E = 18.0
'Energy':                EV/EBITDA = 8.0,  P/E = 12.0
'Utilities':             EV/EBITDA = 9.0,  P/E = 16.0
'Real Estate':           EV/EBITDA = 12.0, P/E = 25.0
'Communication Services':EV/EBITDA = 12.0, P/E = 20.0
```

**Reliability**: ❌ **LOW** - These are rough sector averages, not actual comparable companies

**🚨 CRITICAL ISSUES**:
1. **No real peer selection**: Should identify actual comparable companies (same industry, similar size)
2. **Sector averages are static**: Tech in 2020 (P/E=25) vs 2024 (P/E=40 for AI stocks)
3. **Too broad**: "Technology" includes SaaS (P/E=100+) and hardware (P/E=15)
4. **Doesn't use actual trading comps**: Should pull real companies like:
   - Apple → Microsoft, Google, Amazon
   - Ford → GM, Toyota, Volkswagen
   - Intel → AMD, NVDA, TSM

**RECOMMENDATION**: This is the SECOND WEAKEST part. Should fetch actual peer companies and their multiples.

---

## Overall Data Quality Assessment

### ✅ **HIGHLY RELIABLE** (Trust Completely)
1. Company name, ticker, sector
2. Current stock price
3. Market cap (with caveat on shares outstanding)
4. 10-year Treasury rate

### ⚠️ **MODERATELY RELIABLE** (Verify if Critical)
1. Financial statements (revenue, EBITDA, debt, cash)
2. Tax rate calculation
3. Beta calculation
4. Size premium

### ❌ **LOW RELIABILITY** (High Risk of Error)
1. **Growth rate projections** - arbitrary formulas
2. **Comparable company multiples** - sector averages, not real comps
3. **Market risk premium** - fixed at 6.5%
4. **CapEx/Depreciation fallbacks** - generic 5% assumptions

---

## Recommendations for Improvement

### Priority 1 (Critical Fixes)
1. **Add manual override for growth rates**
   - Allow user to input custom Y1, Y2, Y3, terminal growth
   - Show analyst estimates as suggestions, not hardcoded

2. **Fetch real comparable companies**
   - Use Yahoo Finance to get industry peers
   - Calculate actual peer multiples (median EV/EBITDA, P/E)
   - Example: For AAPL, fetch MSFT, GOOGL, AMZN multiples

3. **Add data staleness warnings**
   - Show "Last updated: Q2 2024" for financial data
   - Warn if data >6 months old

### Priority 2 (Enhance Accuracy)
4. **Dynamic market risk premium**
   - Calculate from current S&P 500 earnings yield vs 10Y treasury
   - Formula: `MRP = 1/P/E of S&P 500 - Risk_Free_Rate`

5. **Industry-specific assumptions**
   - CapEx % by industry (utilities 15%, software 2%)
   - Depreciation % by industry
   - Working capital intensity by industry

6. **International company handling**
   - Detect country from ticker suffix (.L = London, .TO = Toronto)
   - Add country risk premium for emerging markets
   - Adjust tax rates by country

### Priority 3 (Nice to Have)
7. **Multiple data sources**
   - Add Alpha Vantage as backup for Yahoo Finance
   - Cross-validate critical metrics (revenue, EBITDA)

8. **Historical validation**
   - Show 3-year trend for revenue, margins
   - Flag anomalies (sudden 50% revenue drop)

9. **Analyst consensus**
   - Fetch analyst price targets, ratings
   - Show consensus estimates vs model output

---

## Testing Recommendations

### Test Case 1: Mature Company (Apple - AAPL)
```python
# Expected Data Quality:
✅ Financial statements: Complete (Apple files on time)
✅ Beta: Accurate (long history, liquid stock)
⚠️ Growth rates: May overestimate (Apple growing <5%, model assumes >10%)
❌ Comps: Sector average doesn't capture AAPL's premium valuation
```

### Test Case 2: High-Growth Tech (NVIDIA - NVDA)
```python
# Expected Data Quality:
✅ Financial statements: Complete
⚠️ Beta: Underestimates risk (NVDA more volatile than 5Y beta suggests)
❌ Growth rates: Severely underestimates (NVDA growing 50-100%, model caps at 50% Y1 then declines)
❌ Comps: Sector average P/E=25 vs NVDA trades at P/E=70+
```

### Test Case 3: New IPO (Rivian - RIVN, 2021 IPO)
```python
# Expected Data Quality:
⚠️ Financial statements: May be incomplete (limited history)
❌ Beta: Defaults to 1.0 (not enough history)
❌ Growth rates: Wild guesses (no historical revenue growth)
⚠️ Comps: Auto sector average, but RIVN is growth stock
```

### Test Case 4: International Company (Samsung - 005930.KS)
```python
# Expected Data Quality:
⚠️ Financial statements: Yahoo Finance may have delayed/incomplete data
⚠️ Beta: Uses S&P 500 benchmark (should use KOSPI for Korean stocks)
❌ Tax rate: Defaults to 21% US rate (South Korea corporate tax is 27.5%)
❌ Country risk: Should add Korea risk premium, but hardcoded to 0
```

---

## Conclusion

**Current State**: The app uses Yahoo Finance as a single source of truth, which is:
- ✅ Good for: Basic company info, stock prices, fundamental statements
- ⚠️ Moderate for: Financial ratios, beta, tax rates
- ❌ Weak for: Growth projections, comparable valuations

**Biggest Risks**:
1. **Growth rates are guesses** (worst offender)
2. **No real comparable companies** (second worst)
3. **Stale financial data** (3-6 months old)
4. **Fixed market assumptions** (6.5% MRP regardless of market conditions)

**Action Required**:
- Implement Priority 1 fixes ASAP (manual growth overrides, real comps)
- Add data staleness warnings to UI
- Consider adding a "Data Quality Score" to each valuation

The valuation OUTPUT is only as good as the INPUT data. Currently, the inputs have significant limitations that users should be aware of.
