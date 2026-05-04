# Hardcoded Values Inventory — Phase 1 (updated Phase 2)

This document is the **single source of truth** for every hand-picked constant
that drives AXIOM's valuation output. It exists because the system was
previously called "ML" while the actual model — the things that move the
output most — were JSON lookup tables.

Each row tells you:
- where the value lives,
- what it gates,
- which Phase of the fix plan retires or replaces it.

## How to read the "Phase" column
- **P2** — replaced by live peer-comp computation with Bayesian shrinkage.
- **P3** — fixed inside the ML correction layer (label/clip/anchor changes).
- **P4** — used for uncertainty / scenario generation, kept but parameterised.
- **P5** — driven by the historical backtest, no longer hand-set.
- **P6** — replaced by a panel-regression factor model.
- **keep** — genuine taxonomy (sector tag map), not a numeric assumption.

---

## 1. JSON config tables — `valuation/config/`

| File | Top-level keys | Constants | Used by | Phase |
|---|---|---|---|---|
| `subsector_multiples.json` | `multiples` (54 tags × [EV/EBITDA, P/E, sector_median_growth]), `cyclical_tags`, `secular_decline_tags` | ~173 | `valuation.normalizers.get_multiples`, `valuation.pipeline.calibrate` | **P2 ✅ (now used as Bayesian prior, not the answer)** |
| `bank_multiples.json` | `sector_pb` (3 tags), `ticker_pb` (10 tickers) | 13 | `valuation.alt_models.bank_model` | **P2** |
| `reit_multiples.json` | `sector_pffo` (1 tag), `ticker_pffo` (10 tickers) | 11 | `valuation.alt_models.reit_model` | **P2** |
| `blend_weights.json` | 7 company types × {dcf, ev, pe} | 21 | `valuation.normalizers.get_blend_weights` | **P3** (decide ML vs. anchor; do not blend both) |
| `terminal_growth.json` | `default` + `rates` (54 tags) | 55 | `valuation.pipeline.calibrate` (`company_data['terminal_growth']`) | **P4** (parameterise for bear/base/bull) |
| `capex_norms.json` | `default` + `norms` (43 tags) | 44 | `valuation.normalizers.normalize_capex` | **P2** (peer-implied capex) |
| `subsector_tags.json` | 285 tickers → tag | 285 | `valuation.tagging.get_sub_sector_tag` | **keep** (taxonomy) |

**JSON-config total: ~602 constants.** Of these, ~317 are numeric assumptions
(everything except the ticker-tag taxonomy) and are scheduled for replacement
in Phase 2–4.

### Spot-check examples (from `subsector_multiples.json`)
- `cloud_saas:        [28.0, 38.0, 0.18]` — EV/EBITDA 28×, P/E 38×, sector growth 18%.
- `commercial_bank:   [null, null, 0.06]` — banks bypass EV/EBITDA & P/E; routed to `bank_model` P/B path.
- `media_cable:       [7.0,  14.0, 0.00]` — 0% sector growth → secular-decline floor.

The "sector growth" element is used in the PEG-style adjustment in
`valuation/normalizers.py:53` (see §2).

---

## 2. Magic numbers in Python (heuristic layer — `valuation/`)

| File | Line | Value | What it gates | Phase |
|---|---|---|---|---|
| `valuation/normalizers.py` | 45 | EV/EBITDA fallback `12.0`, P/E fallback `20.0` for unknown tag | Default multiples when sub-sector tag is missing | **P2** |
| `valuation/normalizers.py` | 53 | PEG-style exponent `** 0.4` | Damps growth-multiple adjustment vs sector median | **P6** (kept for continuity through P2; replace with factor model) |
| `valuation/normalizers.py` | 54 | Adjustment clip `[0.5, 1.5]` | Caps how far multiple can stretch from base | **P6** |
| `valuation/peer_comps.py` | 39 | `SHRINKAGE_K = 5` | Bayesian shrinkage strength: prior-equivalent peer count | **P5** (calibrate from backtest) |
| `valuation/peer_comps.py` | 40 | `MAX_PEERS = 10` | Cap on peer-set size | (kept; product knob) |
| `valuation/peer_comps.py` | 113 | `MIN_PEERS_FOR_LIVE = 2` | Below this, fall back to JSON prior | **P5** (calibrate from backtest) |
| `valuation/peer_comps.py` | 44–46 | EV/PE/PB sanity ranges (e.g. EV/EBITDA in (0.5, 200)) | Reject yfinance outliers | (kept; sanity bounds) |
| `valuation/anchoring.py` | 3–11 | Analyst-anchor weights per company type (STORY 0.70, GROWTH_TECH 0.15, etc.) | How much weight analyst consensus gets vs model | **P3 ✅ disabled by default** (set `AXIOM_USE_ANALYST_ANCHOR=1` to restore) |
| `valuation/anchoring.py` | 19 | Sanity ceiling `analyst_target * 4.0` | Caps absurd model overshoots | **P3** (replace with quantile band from backtest) |
| `valuation/anchoring.py` | 22–23 | Sanity floor `analyst_target * 0.25` then snap to `* 0.70` | Caps absurd model undershoots | **P3** |
| `valuation/anchoring.py` | 27–28 | Current-price ceiling `* 10.0`, snap `* 1.10` | Last-ditch unrealism guard | **P3** |
| `valuation/tagging.py` | 110–113 | DISTRESSED triggers (`op_income < 0 and g1 ≤ 0` or `ebitda < 0`) | Hard-switch into DISTRESSED type | **P6** (soft-membership over types) |
| `valuation/tagging.py` | 115 | STORY trigger (`beta > 1.8 and forward_pe > 60`) | Cliff at beta/PE thresholds | **P6** |
| `valuation/tagging.py` | 120 | HYPERGROWTH trigger (`g1 > 0.20 and margin > 0.08`) | Cliff at 20%/8% boundaries | **P6** |
| `valuation/tagging.py` | 123 | GROWTH_TECH trigger (`g1 > 0.08 and margin > 0 and mktcap > 50e9`) | Cliff at 8% / $50B | **P6** |
| `valuation/tagging.py` | 126 | CYCLICAL trigger (`tag in CYCLICAL_TAGS and beta < 1.6`) | Cliff at beta 1.6 | **P6** |
| `valuation/tagging.py` | 129 | STABLE_VALUE_LOWGROWTH trigger (`g1 < 0.04 and margin > 0`) | Cliff at 4% growth | **P6** |
| `valuation/pipeline.py` | 48 | Auto captive-finance debt cut: `debt → debt * 0.25 - cash` if `debt/mktcap > 2.0` | Heavy-leverage auto OEM fix | **P2** (peer-implied capital structure) |
| `valuation/pipeline.py` | 56 | Airline lease-debt cut: `debt → debt * 0.35` if `debt/revenue > 0.65` | Airline operating-lease adjustment | **P2** |
| `valuation/pipeline.py` | 60–62 | Airline growth caps: y1 ≤ 6%, y2 5%, y3 4% | Caps airline projection optimism | **P2** |
| `valuation/pipeline.py` | 67–68 | Non-USD-reporting force `_forced_anchor_weight = 0.85` | 85% analyst weight for non-USD reporters | **P3** |
| `valuation/pipeline.py` | 73–75 | Telecom/utility WACC penalty `+0.015` | Leverage penalty for two tags | **P2** |
| `valuation/pipeline.py` | 83–84 | Y2/Y3 convergence weights `(0.67, 0.33)` and `(0.33, 0.67)` toward terminal | Growth-decay schedule | **P4 ✅ also used by `valuation/scenarios._derive_y2_y3` when perturbing Y1 in bear/bull** |
| `config.py` | 70–71 | `BEAR_MULTIPLIER=0.75`, `BULL_MULTIPLIER=1.25` | Old cosmetic blanket scenario triple | **P4 ✅** replaced by driver-based perturbations in `valuation/scenarios.compute_scenarios`; constants still load but no longer drive output (Monte-Carlo helper is the last caller). |
| `valuation/scenarios.py` | 22–25 | `WACC_DELTA=0.01`, `TERMINAL_GROWTH_DELTA=0.01`, `GROWTH_Y1_FACTOR_BEAR=0.75`, `..._BULL=1.25` | Phase 4 perturbation deltas | **P5** (calibrate from realized 12m volatility per sector) |
| `valuation/alt_models.py` | 9 | Default bank P/B fallback `1.6` | When sector + ticker P/B both missing | **P2** |
| `valuation/alt_models.py` | 19 | Default REIT P/FFO fallback `20.0` | When sector + ticker P/FFO both missing | **P2** |
| `valuation/alt_models.py` | 26 | Growth-loss model: `analyst_target * 0.85` | 15% haircut on analyst target | **P3** |
| `valuation/alt_models.py` | 52 | Health-insurance P/E `16.0`; analyst haircut `* 0.80` | Hardcoded health-insurance multiple | **P2** |
| `valuation/alt_models.py` | 63 | Non-USD haircut `* 0.88` on analyst target | 12% haircut on non-USD reporters | **P3** |
| `valuation/alt_models.py` | 74 | Rule-of-40 SaaS EV/Rev tiers (11×, 7.5×, 5×, 3.5×) | SaaS tiering by R40 score | **P2** |
| `valuation/alt_models.py` | 84–87 | Utility model: `risk_free + 0.005` required yield, `net_income * 0.67` payout | Utility dividend-discount style | **P2** |

---

## 3. Magic numbers in Python (ML layer — `ml/`)

| File | Line | Value | What it gates | Phase |
|---|---|---|---|---|
| `ml/calibrator.py` | (was 132–134) | Label clip `[0.2, 5.0]` on `actual/predicted` | (retired) | **P3 ✅** label is now `log(actual/predicted)` with no clip; inference clamp narrowed to ±ln(3) on the multiplier |
| `ml/calibrator.py` | (was 137) | 80/20 single chronological split | (retired) | **P3 ✅** `TimeSeriesSplit(n_splits≤5)` + 27-cell grid over (max_depth, n_estimators, learning_rate); selects best by CV log-MAE |
| `ml/calibrator.py` | 14 | `MIN_TRAINING_SAMPLES = 15` | Threshold to bother training | **P3** |
| `ml/calibrator.py` | 23–35 | `_TAG_VOL_DEFAULT` per-sector vol priors (0.55 for biotech, 0.12 for utility, etc.) | Volatility prior for inference | **P4** (used in uncertainty bands) |
| `ml/walk_forward.py` | 235–238 | VIX > 22 → +1 regime score | Regime detection signal 1 | **P5** (HMM / change-point) |
| `ml/walk_forward.py` | 245–247 | HYG 3-mo return < −3% → +1 | Credit stress signal | **P5** |
| `ml/walk_forward.py` | 254–256 | `^IRX > ^TNX` (yield curve inversion) → +1 | Curve signal | **P5** |
| `ml/walk_forward.py` | 267–272 | SPY < MA200 → +1; SPY 3-mo < −8% → +1 | Trend / momentum bear signals | **P5** |
| `ml/walk_forward.py` | 275–280 | Score buckets (`≤1: risk_on`, `2–3: transition`, `≥4: risk_off`) | Hard regime cutoffs | **P5** |
| `ml/log.py` | 15 | VIX > 25 → `risk_off` (legacy 2-state regime) | Used by inference path before composite regime | **P5** |
| `ml/calibrator.py` | metadata | n_estimators 150, max_depth 5 (per `ml_model_y1y2_metadata.json`) | GBM hyperparams, no grid search | **P3** |

---

## 4. Implicit constants (data-driven, surfaced for awareness)

| Where | Value | Notes |
|---|---|---|
| `data_integrator.py:312` | `TERMINAL_DEFAULT = 0.025` | Inline duplicate of `terminal_growth.json` default; **delete** once Phase 2 ships and pipeline owns it. |
| `valuation_engine.py:re-exports` | All of the above | Single import surface; this file is the audit boundary. |

---

## Counting summary

- **JSON numeric constants (P2–P4 candidates):** ~317
- **Python magic numbers in heuristic layer:** 25
- **Python magic numbers in ML layer:** 11
- **Total:** ~353 hand-picked numbers driving every fair-value output.

The audit's framing is correct: every number above was hand-picked. None
were learned from data. Phase 2 onwards converts the P2 / P3 rows into
peer-derived or model-derived estimates with explicit shrinkage parameters.
