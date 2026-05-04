# AXIOM: What We Built, Why We Changed It, and Where We Are Now

*A 2-minute read. No jargon. The full honest story.*

---

## Where We Started

The original system worked like this: pull a company's financials, run a DCF model, blend the result with EV/EBITDA and P/E multiples, then multiply everything by a machine learning "correction factor." The final number was labeled **DCF Fair Value** in the UI.

The problem: the number labeled "DCF Fair Value" was not a DCF value. It was a blend of three methods plus an ML multiplier. When you opened Google's DCF page and saw $531, the actual DCF was $380. The $151 gap came from multiple expansion and ML fudging. The sensitivity table (which ran a real DCF) correctly showed $380 — so the headline number and the table contradicted each other.

This wasn't dishonest by design. It grew organically: add EV/EBITDA for context → blend it in → add ML correction to fix errors → repeat. Each step made sense locally. The overall result was a number with no clean financial interpretation.

---

## Pivot 1: Make the DCF Honest

We stripped everything back to a single, clean DCF. The math:

```
Fair Value = PV(10 years of free cash flows) + PV(terminal value) + cash - debt
             ÷ shares outstanding
```

That's it. No blending. No ML multiplier. No analyst anchor. The sensitivity table now uses the same formula — same inputs produce the same number everywhere in the app.

EV/EBITDA and P/E are still computed and shown, but labeled as "comparable estimates" — context, not inputs to the fair value.

What we deleted: the ML calibration model (`calibrator.py`), the blend weights routing into the price, the analyst anchor, and the `backtest.py` file that had a hardcoded WACC of 9.5% for every company regardless of sector or leverage (this poisoned the training data).

---

## Pivot 2: ML Should Learn the Signal, Not Patch the Output

The old ML model learned: "when our prediction was wrong by X%, correct future predictions by X%." That's circular — it patches its own mistakes without understanding why it was wrong.

What a quant firm would do instead: train the model on **what actually predicts which stocks will outperform their sector.** The signal should be: "this stock's DCF implies more upside than the market is pricing in" — not "our model was off by this much last year."

We rebuilt around three factors:

**Value**: DCF price ÷ current market price − 1. How much upside does the fundamental model see vs. what the market says?

**Momentum**: 12-month price return vs. sector ETF, minus the most recent month. The Jegadeesh-Titman factor — one of the most durable signals in academic finance. Stocks that have outperformed their sector over the past year tend to continue outperforming for the next 6-12 months.

**Quality**: Free cash flow yield (free cash flow ÷ market cap). Companies that generate a lot of cash relative to their price tend to be resilient.

Each factor is Z-scored within sub-sector — Google is compared to other internet companies, not to oil majors. The composite score is the equal-weighted average of these Z-scores.

---

## Pivot 3: Evaluation Metrics That Actually Matter

The old system measured MAE (mean absolute error) on price predictions. This is meaningless for a ranking model. A model can have 30% price error and still be an excellent investment signal if it correctly ranks which stocks are more attractive.

We switched to **Information Coefficient (IC)** — the Spearman rank correlation between predicted attractiveness scores and actual subsequent excess returns. If IC > 0 with a t-statistic ≥ 2, the model has real signal. If not, it doesn't.

We also added hit rate by quintile: does the top-ranked quintile of stocks actually outperform the median? Q1 hit rate minus Q5 hit rate is the headline number. If positive, the model separates winners from losers. If near zero, it's noise.

---

## What We Have Now

**Valuation layer**: A clean DCF engine. One formula. Consistent outputs everywhere. The number says what it is.

**Factor layer**: Three cross-sectional signals (value, momentum, quality) computed daily for all 275 tracked tickers and logged to disk. Each day's snapshot knows how each ticker compares to its sector peers on each factor.

**ML layer**: A walk-forward model that learns — from price history since 2022 — which combination of these factors predicts excess returns in each market regime. The model trains on actual price data, not on a circular loop of its own past errors. When enough snapshot data accumulates (months, not years), it will switch to using real cross-sectional Z-scores as features instead of sector averages.

**Evaluation layer**: IC by horizon, IC by regime, hit rate by quintile. The report tells you whether the model is adding value or not.

---

## What's Still Waiting on Time

The model's ranking signal won't be shown to users until it has demonstrated statistically significant IC (t-stat ≥ 2) over at least 24 months of out-of-sample data. We're accumulating that data daily. The factor infrastructure is live. The model is retrained. The evaluation loop runs weekly. The signal will speak for itself when the data supports it.

The profitability trend factor (is this company's margin improving or declining?) requires 12 months of daily snapshots to compute — that data will be available in 2027.

---

## The Honest One-Liner

We went from: *"apply DCF, blend it with multiples, slap an ML multiplier on top, call it DCF Fair Value"*

To: *"run a clean DCF, score companies on three independent factors, let the data tell us whether the model works."*

The second version is harder to build. It's also the only version a quant fund would take seriously.
