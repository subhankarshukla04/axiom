# Axiom

**An honest equity valuation engine.** Type a US ticker, get a clean DCF-derived fair value, a sub-sector-aware comparables read, and a factor-based ranking signal evaluated the way a quant fund would evaluate it — Information Coefficient, t-stat gated, no marketing math.

---

## The one-line pitch

Most retail valuation tools blend DCF with multiples, add an ML "correction multiplier," and label the output **DCF Fair Value**. It isn't. Axiom is the version that refuses to do that.

---

## What it does

1. **Add a ticker** — `AAPL`, `NVDA`, `JPM`, anything on a US exchange. Financials are pulled from Yahoo Finance.
2. **Run the model** — A single 10-year DCF, a sub-sector classifier (60+ buckets) that swaps method when DCF is the wrong tool (banks → P/B, REITs → P/FFO, SaaS → Rule-of-40, utilities → DDM), and a synthetic credit-spread WACC (Damodaran).
3. **See the result** — Fair value per share, bear/base/bull range (WACC ±100bp, terminal growth ±100bp, growth Y1 ±25%), and the comparable estimates (EV/EBITDA, P/E) sitting *beside* the DCF as context — not blended into it.

No account. No keys for basic use. One number. It says what it says.

---

## The pivot — why this version exists

The first version of Axiom did what most retail tools do: ran a DCF, blended it with EV/EBITDA and P/E, multiplied by an ML "correction factor," and called the output **DCF Fair Value**. The number on the Google page might have read $531 while the underlying DCF was $380 — the gap was multiple expansion plus ML fudging. The sensitivity table inside the same app contradicted the headline. Each step of how it got there made local sense. The aggregate was a number with no clean financial interpretation.

So we tore it down and rebuilt around three rules:

### 1. The DCF is the DCF

```
Fair Value = PV(10y free cash flows) + PV(terminal value) + cash − debt
             ÷ shares outstanding
```

That's it. No blending into the headline. No ML on top. The sensitivity table uses the same formula — same inputs, same number, everywhere in the app. EV/EBITDA and P/E are still computed and shown, labeled as **comparable estimates**, context not inputs.

What was deleted: `calibrator.py` (the ML-on-output multiplier), the blend weights routing into the price, the analyst anchor, and a `backtest.py` that hardcoded WACC to 9.5% for every company regardless of sector or leverage (which had been poisoning the training data).

### 2. ML should learn the signal, not patch the output

The old ML model learned: *"when our prediction was wrong by X%, correct future predictions by X%."* That's circular — it patches its own past mistakes without understanding why they happened.

The rebuilt ML layer scores companies on three independent cross-sectional factors, the way a real quant shop would:

- **Value** — DCF price ÷ current market price − 1. How much upside does the fundamental model see vs. what the market is pricing?
- **Momentum** — 12-month sector-relative return minus the most recent month. The Jegadeesh-Titman factor, one of the most durable signals in academic finance.
- **Quality** — free-cash-flow yield (FCF ÷ market cap). Cash-generative companies are resilient.

Each factor is **Z-scored within sub-sector** — Google is compared to other internet companies, not to oil majors. The composite is the equal-weighted average of the Z-scores.

### 3. Evaluate with metrics that mean something

The old system measured MAE on price predictions. That's meaningless for a ranking model — a model can have 30% price error and still be an excellent investment signal if it ranks correctly. We switched to:

- **Information Coefficient (IC)** — Spearman rank correlation between predicted attractiveness and subsequent excess returns. If `IC > 0` and `t-stat ≥ 2`, the model has real signal. If not, it doesn't.
- **Hit rate by quintile** — does the top-ranked quintile actually beat the median? Q1 hit rate minus Q5 hit rate is the headline.

The ranking signal is **not shown to users** until it clears `t-stat ≥ 2` over at least 24 months of out-of-sample data. The factor infrastructure logs daily. The model retrains weekly. The signal will speak when the data supports it.

The full narrative — what was wrong, what changed, what's still pending — lives in [`AXIOM_STORY.md`](./AXIOM_STORY.md).

---

## How the DCF is built

**Free cash flow** — projected over 10 years with three-stage growth fade:

| Years | Growth |
|-------|--------|
| 1–3 | Recent realized growth |
| 4–7 | Fading toward industry average |
| 8–10 | Converging to terminal (2–3%) |

**WACC** — CAPM for equity, Damodaran synthetic credit spread for debt:

| Interest Coverage | Implied Rating | Spread |
|---|---|---|
| > 8.5 | AAA | 0.60% |
| > 6.5 | AA | 0.90% |
| > 4.25 | A | 1.40% |
| > 2.5 | BBB | 2.00% |
| > 1.5 | BB | 2.75% |
| > 0.8 | B | 4.00% |
| < 0.8 | CCC/D | 7–15% |

A company with strong coverage gets a lower cost of debt automatically — no hand-typed assumption.

**Terminal value** — Gordon Growth, capped at `min(3%, WACC − 1%)` so the formula can't blow up as `g → WACC`.

**Bridge to equity**

```
Equity Value = Enterprise Value − Net Debt + Cash
Price/Share  = Equity Value ÷ Shares Outstanding
```

---

## Sub-sector tagging — why a single DCF can't fit everything

Every ticker is classified into one of 60+ sub-sectors before any math runs. Each sub-sector gets its own multiples, blend weights, and primary valuation method.

| Bucket | Examples | Primary method |
|---|---|---|
| `fabless_semi` | NVDA, AMD, AVGO | DCF + premium multiples |
| `IDM_semi` | INTC, STM | DCF, capex-aware |
| `security_cloud` | CRWD, ZS, PANW | EV/Revenue + Rule-of-40 |
| `commercial_bank` | JPM, BAC, WFC | P/B (DCF doesn't apply) |
| `REIT` | O, EQIX, PLD | P/FFO |
| `utility_regulated` | NEE, DUK, SO | DDM |
| `story_auto` | TSLA, RIVN | Narrative-weighted, lower DCF weight |

`HARDCODED_VALUES.md` is the full inventory of every assumption — and the phased plan to replace each one with a live peer-comp estimate.

---

## What's in the repo

```
app.py                        Flask app, API routes
valuation_professional.py     DCF engine, WACC calc, Monte Carlo
valuation_service.py          Orchestration, DB persistence
valuation_engine.py           Single import surface across heuristic + ML layers
ib_valuation_framework.py     Industry multiples, classification
ml/                           Factor model (Value / Momentum / Quality), walk-forward
                              trainer, IC evaluator, daily snapshot logger
data_integrator.py            Yahoo Finance fetch
realtime_price_service.py     Daily price refresh
config.py                     Environment config
models.py                     Pydantic schemas
static/, templates/           Frontend (vanilla JS, CSS)
AXIOM_STORY.md                The pivot narrative — start here
HARDCODED_VALUES.md           Inventory of every magic number
```

---

## Quickstart

```bash
git clone https://github.com/subhankarshukla04/Axiom-Valuations.git
cd Axiom-Valuations
pip install -r requirements.txt

cp .env.example .env             # configure DB + secret key
python app.py                    # http://localhost:5000
```

**Add a company** → search icon → enter ticker → *Add & Value* → result appears in the modal.

---

## Tech stack

| Layer | Choice |
|---|---|
| Backend | Flask, Python 3.11 |
| Database | PostgreSQL (SQLite fallback) |
| Data | Yahoo Finance |
| ML | XGBoost, scikit-learn, NumPy |
| Frontend | Vanilla JS, CSS |
| Deploy | Docker, Render, Vercel |

---

## What this is — and isn't

Axiom is a research aid, not a quantitative alpha system. The fair-value output is a real DCF; the comparables are real comparables; the factor signal is a real factor signal — but the curated tables (sub-sector multiples, blend weights) still drive a meaningful share of the variance, and `HARDCODED_VALUES.md` is the honest accounting of that. Outputs are one input to an investment decision, not a forecast.

The stated goal isn't to be right about the price. It's to be **honest about the math** and let the data prove or disprove the model on its own terms.

---

## Author

Built by [Subhankar Shukla](https://subhankarshukla.vercel.app/). More at the portfolio.

## License

MIT
