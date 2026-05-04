# Investment Banking Valuation Methodology

## What Was Changed

### ✅ Realistic Company Data
Replaced test data with **actual financial profiles** of real companies based on 2024/2025 filings:

**10 Real Companies Now in Database:**
1. **Apple Inc.** - $385B revenue, 25.7% margin, 8% growth
2. **Microsoft Corporation** - $220B revenue, 36.8% margin, 15% growth (Cloud/AI boom)
3. **NVIDIA Corporation** - $60B revenue, 48.9% margin, 95% growth (AI chip leader)
4. **Tesla Inc.** - $96B revenue, 15.3% margin, 19% growth (Cybertruck ramp)
5. **Amazon.com Inc.** - $575B revenue, 5.5% margin, 11% growth (Retail + AWS)
6. **Alphabet Inc.** - $307B revenue, 25.7% margin, 9% growth (Search + Cloud)
7. **Meta Platforms Inc.** - $134B revenue, 28.7% margin, 16% growth (Ad recovery)
8. **Intel Corporation** - $54B revenue, 2.3% margin, -5% growth (**Distressed** - turnaround case)
9. **Coca-Cola Company** - $45B revenue, 24.4% margin, 5% growth (Mature defensive)
10. **JPMorgan Chase** - $161B revenue, 29.5% margin, 7% growth (Financial sector)

---

## Pattern Recognition Framework

### How the System Classifies Companies

The valuation engine automatically classifies each company into an **archetype** based on financial patterns:

#### 1. **Hyper-Growth** (Uber, DoorDash style)
- **Pattern**: Growth >30%, negative margins
- **Approach**: Revenue multiples, not DCF
- **Terminal Growth**: 4% (can sustain above-GDP)
- **Example**: Early-stage tech with land-grab strategy

#### 2. **Growth** (NVIDIA, Microsoft)
- **Pattern**: Growth 15-30%, margins >5%
- **Approach**: Standard DCF with growth premium
- **Terminal Growth**: 3.5%
- **Example**: NVIDIA (95% growth, 49% margin) → Hyper-growth profits

#### 3. **Stable Growth** (Apple, Google)
- **Pattern**: Growth 8-15%, strong margins >15%
- **Approach**: Traditional Goldman Sachs DCF
- **Terminal Growth**: 3.0%
- **Example**: Apple (8% growth, 26% margin) → Steady compounder

#### 4. **Mature** (Coca-Cola)
- **Pattern**: Growth <8%, profitable >10% margin
- **Approach**: FCF focus, lower growth assumptions
- **Terminal Growth**: 2.0%
- **Example**: Coke (5% growth, 24% margin) → Cash cow

#### 5. **Cyclical** (Ford, Airlines)
- **Pattern**: Cyclical sector + volatile margins
- **Approach**: **Normalized through-cycle metrics**
- **Terminal Growth**: 2.0% (GDP-like)
- **Example**: Auto OEMs with boom/bust cycles

#### 6. **Distressed** (Intel currently)
- **Pattern**: Negative/very low margins, declining revenue
- **Approach**: **Normalized to industry averages**
- **Terminal Growth**: 2.0%
- **Example**: Intel (-5% growth, 2.3% margin, 45% CapEx) → Turnaround candidate

#### 7. **High CapEx** (Utilities, Semis in growth phase)
- **Pattern**: CapEx >25% of revenue
- **Approach**: Normalize to steady-state CapEx (60% of current)
- **Terminal Growth**: 3.0%
- **Example**: Intel's fab buildout (45% CapEx → normalize to 12%)

#### 8. **Financial** (JPMorgan, Goldman)
- **Pattern**: Financial Services sector
- **Approach**: P/B and ROE framework (not DCF)
- **Metrics**: Book value, ROE, P/B multiples

---

## Investment Banking Adjustments

### Normalized Metrics (Like Goldman Sachs Does)

When a company is **distressed** or **cyclical**, we use **through-cycle normalized assumptions**:

#### Intel Example (Distressed Tech)
**Raw Data:**
- EBITDA Margin: 16.7% (depressed)
- Profit Margin: 2.3% (distressed)
- CapEx: 45% (massive fab investment)

**Normalized (IB Approach):**
- EBITDA Margin: **25%** (tech industry average)
- Profit Margin: **20%** (normalized tech profitability)
- CapEx: **12%** (maintenance CapEx post-buildout)

**Why?** Intel is in distress phase. Goldman Sachs doesn't value it on current (terrible) metrics — they normalize to what it should earn through-cycle.

---

## Comparable Multiples by Sector

### Current Market Multiples (Dec 2024)

#### Technology - Stable Growth
- **EV/EBITDA**: 18.0x
- **P/E**: 28.0x
- **PEG**: 2.0

#### Technology - Growth
- **EV/EBITDA**: 22.0x (NVIDIA, Microsoft level)
- **P/E**: 35.0x
- **PEG**: 1.8

#### Technology - Mature
- **EV/EBITDA**: 12.0x
- **P/E**: 20.0x
- **PEG**: 2.5

#### Consumer Cyclical (Amazon, Tesla)
- **EV/EBITDA**: 8-12x (depends on growth)
- **P/E**: 15-22x
- **PEG**: 1.3-1.5

#### Consumer Defensive (Coca-Cola)
- **EV/EBITDA**: 18.0x (brand premium)
- **P/E**: 23.0x
- **PEG**: 3.5 (low growth = high PEG)

#### Financial Services (JPMorgan)
- **P/B**: 1.5x
- **P/E**: 12.0x
- **PEG**: 1.4

---

## Risk-Adjusted Discount Rates

### Beta by Company Type

**Defensive (Beta 0.60-0.80):**
- Coca-Cola: 0.60
- Utilities: 0.70
- Consumer staples

**Market (Beta 1.00-1.20):**
- Apple: 1.25 (slight tech premium)
- Amazon: 1.15
- Microsoft: 0.90 (enterprise stability)

**Growth/Volatile (Beta 1.30-2.00):**
- NVIDIA: 1.68 (semiconductor + AI volatility)
- Tesla: 2.01 (execution risk + cyclical)
- Meta: 1.25 (regulatory risk)

**Distressed (Beta <1.00):**
- Intel: 0.65 (defensive in downturn, too big to fail)

### Market Risk Premium Adjustments
- **Standard**: 6.5%
- **High Risk Sectors** (Semis, Cyclical): 7.0-7.5%
- **Defensive**: 5.5%

### Size Premium
- **Mega-cap** (>$500B): 0%
- **Large-cap** ($100-500B): 0%
- **Mid-cap**: 1.0-1.5%
- **Distressed Large**: 1.5% (Intel gets distress premium)

---

## Growth Rate Decay

### How Growth Decays Over Time

**Investment banks don't assume constant growth.** They use **decay schedules**:

#### Stable Growth Companies (Apple, Google)
- **Decay Rate**: 85% per period
- Year 1: 10% → Year 2: 8.5% → Year 3: 7.2% → Terminal: 3%

#### Growth Companies (NVIDIA, Microsoft)
- **Decay Rate**: 88% per period (slower decay)
- Year 1: 20% → Year 2: 17.6% → Year 3: 15.5% → Terminal: 3.5%

#### Mature Companies (Coca-Cola)
- **Decay Rate**: 80% per period (faster decay)
- Year 1: 5% → Year 2: 4% → Year 3: 3.2% → Terminal: 2%

---

## Terminal Value Assumptions

### Terminal Growth by Archetype

| Archetype | Terminal Growth | Rationale |
|-----------|----------------|-----------|
| Hyper-Growth | 4.0% | Can sustain above-GDP (network effects) |
| Growth | 3.5% | Premium to GDP (tech secular trends) |
| Stable Growth | 3.0% | GDP + inflation |
| Mature | 2.0% | GDP-like |
| Cyclical | 2.0% | Through-cycle GDP |
| Distressed | 2.0% | Conservative recovery |
| High CapEx | 3.0% | Infrastructure GDP+ |

**Why Terminal Growth Matters:**
- Terminal value = **60-80%** of total DCF value
- 0.5% change in terminal growth = **15-20%** valuation swing

---

## Valuation Method Selection

### DCF vs. Multiples Approach

**Pure DCF (50-100% weight):**
- Stable growth companies (Apple, Microsoft, Google)
- Predictable cash flows
- Mature businesses

**Blended DCF + Multiples (25% multiples):**
- Current system default
- Sanity check against market comps
- Reduces model risk

**Multiples-Heavy (50-75% multiples):**
- Cyclical companies (auto, materials)
- Distressed (current metrics unreliable)
- Early-stage growth (revenue multiples)

**Example:** Intel
- DCF on **normalized** margins (not current 2.3%)
- Check against **EV/EBITDA** multiples for distressed tech
- Don't trust current P/E (earnings depressed)

---

## Real-World Examples

### NVIDIA ($1.2T Market Cap)

**Inputs:**
- Revenue: $60B
- Growth: 95% (AI boom)
- Margin: 48.9% (pricing power)
- Beta: 1.68 (volatile)

**Classification:** **Growth** (hyper-growth profits)

**IB Approach:**
- Use high terminal growth (3.5%)
- Slower growth decay (88%)
- Premium multiples (35x EV/EBITDA)
- Accept high volatility

**Fair Value:** ~$1.3-1.5T (depends on AI sustainability)

---

### Intel ($180B Market Cap)

**Inputs:**
- Revenue: $54B (declining)
- Growth: -5%
- Margin: 2.3% (distressed)
- CapEx: 45% (fab buildout)

**Classification:** **Distressed**

**IB Approach:**
- **Normalize** EBITDA to 25% (tech industry standard)
- **Normalize** CapEx to 12% (post-buildout maintenance)
- Use conservative terminal growth (2%)
- Apply turnaround discount

**Fair Value:** ~$220-280B (if transformation succeeds)

---

### Apple ($3T Market Cap)

**Inputs:**
- Revenue: $385B
- Growth: 8%
- Margin: 25.7%
- Beta: 1.25

**Classification:** **Stable Growth**

**IB Approach:**
- Standard DCF
- Terminal growth: 3%
- Premium multiple (brand value)
- Low risk premium (mega-cap quality)

**Fair Value:** ~$2.8-3.2T (fairly valued)

---

## Data Sources & Validation

### Where Data Comes From

1. **Company Financials**: 10-K filings (SEC EDGAR)
2. **Market Data**: Current market caps, trading multiples
3. **Beta**: 5-year regression vs S&P 500
4. **Risk-Free Rate**: 10-year Treasury yield (4.5% current)
5. **Market Risk Premium**: Historical equity premium (6.5%)
6. **Comparable Multiples**: Bloomberg, CapIQ sector averages

### Validation Checks

- **Revenue**: Match reported financials
- **Margins**: Within industry ranges
- **Growth**: Consensus analyst estimates
- **CapEx**: Trailing 4-quarter average
- **Beta**: Updated quarterly

---

## How to Add New Companies

### Pattern Recognition for Any New Company

1. **Get Financials** (from 10-K or public sources):
   - Revenue, EBITDA, Net Income
   - Debt, Cash, Shares
   - Growth rate (consensus estimates)

2. **Classify Sector**:
   - Technology, Consumer Cyclical, Healthcare, etc.

3. **Calculate Metrics**:
   - EBITDA Margin = EBITDA / Revenue
   - Profit Margin = Net Income / Revenue
   - Beta (from Bloomberg or Yahoo Finance)

4. **Let Pattern Recognition Work**:
   - System auto-classifies archetype
   - Applies appropriate assumptions
   - Selects comparable multiples
   - Normalizes if distressed/cyclical

5. **Review Classification**:
   - Check console logs for archetype
   - Verify assumptions make sense
   - Adjust if misclassified

---

## Key Takeaways

### Investment Banking Principles Applied

1. **No One-Size-Fits-All**: Different companies need different approaches
2. **Normalize Distressed/Cyclical**: Don't value on trough earnings
3. **Growth Decay**: Growth moderates over time
4. **Terminal Value Sensitivity**: Most important assumption
5. **Cross-Check with Multiples**: DCF alone isn't enough
6. **Risk-Adjusted Rates**: Beta and premiums matter hugely

### System Improvements

✅ **Pattern Recognition**: Auto-classifies companies
✅ **Realistic Data**: Actual 2024/2025 financials
✅ **Normalized Metrics**: For distressed/cyclical companies
✅ **Sector Comparables**: Market-based multiples
✅ **Growth Schedules**: Decay rates by archetype
✅ **Risk Adjustments**: Beta, size, country premiums

### Result

**Fair values that make sense** based on:
- Company fundamentals
- Industry position
- Market comparables
- Risk profile
- Growth trajectory

This is how Goldman Sachs, Morgan Stanley, and JP Morgan value companies in their equity research reports.
