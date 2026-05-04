# Codebase Audit — May 2026

Snapshot: ~19,400 LOC of Python in `valuation_app/`, 65 `.py` files, ~80
HTTP routes spread across four files (`app.py`, `phase1_api_endpoints.py`,
`advanced_api_endpoints.py`, `axiom_api_endpoints.py`).

This audit looks for: **waste**, **inefficiency**, **dead code**, and
**duplication**. Findings are grouped from highest- to lowest-leverage cleanup.

## TL;DR

- **Four valuation engines exist; only one chain is actually live.**
- **`institutional_valuation_engine.py` (966 LOC) is the second-largest file in the repo and is invoked only via lazy `from institutional_valuation_engine import ...` inside two route handlers.** Worth inspecting whether those routes are still used in production.
- **The route layer is a pile of lazy imports.** `axiom_api_endpoints.py` lazy-imports 14 modules from inside route bodies. This works but completely defeats startup-time validation — broken imports only surface when a user hits the route.
- **`mcp_server.py`, `services/agent.py`, and the entire CLI in `scripts/`** show no inbound references. Likely actually dead.
- **Two complete data-fetching layers coexist**: `data_integrator.py` (677 LOC, used everywhere) and `data_layer/` (~740 LOC across 5 files, used only via three lazy imports in `axiom_api_endpoints.py`). Data-layer prioritises EDGAR/FRED/Finnhub/FMP with yfinance fallback — an aspirational design that the live `data_integrator` ignores.
- **Two sub-sector classification systems** now coexist after Phase 1: `valuation/tagging.py` (54 hardcoded tags, hand-coded keyword routing) and `ib_valuation_framework.classify_company` (different taxonomy, called from `valuation_professional.py:7`). They produce different labels for the same company.

## Live valuation chain (the only path that ships)

```
app.py
  → valuation_service.ValuationService.calculate(...)
      → valuation_professional.enhanced_dcf_valuation(...)
          → ib_valuation_framework.apply_investment_banking_adjustments(...)
          → valuation_engine.calibrate(...)            # was ml_engine
          → valuation_engine.run_alternative_model(...)
          → valuation_engine.apply_analyst_anchor(...)
          → valuation_engine.apply_ml_correction(...)
```

Every other "valuation engine" is dormant or activated only by a single route.

## Dead vs. lazy-loaded — verified

| Module | LOC | Status |
|---|---|---|
| `mcp_server.py` | 165 | **Dead.** No inbound refs in any `.py`/`.sh`/`.json`/`.html`/`.js`. |
| `services/agent.py` | 350 | **Dead.** No inbound refs (only `services.llm` and `services.rag` are used). |
| `scripts/*.py` (8 files, ~1,800 LOC) | varies | **Standalone CLIs.** Not imported by app code. May be valuable as ops tools — check before deleting. |
| `institutional_valuation_engine.py` | 966 | **Lazy-loaded only.** Used by `axiom_api_endpoints.py:63` and `advanced_api_endpoints.py:29`. Two routes — verify both still hit. |
| `lbo_engine.py`, `football_field.py`, `sensitivity.py` | ~400 | **Lazy-loaded only** in `axiom_api_endpoints.py`. Three independent routes. |
| `peer_discovery.py` | 100 | **Lazy-loaded only** at `axiom_api_endpoints.py:377`. Underused — Phase 2 will promote it to a core dependency. |
| `data_layer/` (cache, edgar, finnhub, fmp, fred) | 740 | **Aspirational.** Only `from data_layer import DataLayer` is referenced (3 lazy imports in axiom routes). The submodules are imported by `data_layer/__init__.py` itself but the unified `DataLayer` gateway isn't on the live valuation path. The live path uses `data_integrator.py` directly with yfinance. |
| `intelligence/{alert_engine, anomaly_detector, smart_money}` | 740 | **Lazy-loaded only** in axiom route handlers. Niche features. |
| `services/{llm, rag}` | 550 | **Lazy-loaded only** in axiom route handlers (LLM commentary, thesis, smart-money summary). |
| `exports/{excel_generator, pdf_generator}` | 715 | **Lazy-loaded only** in axiom routes 517 / 583. WeasyPrint is in `requirements.txt` so PDF export is intentional. |
| `realtime_price_service.py` | 197 | Live (`app.py:21`). |

## Top wastes / inefficiencies (by leverage)

### W1 — `axiom_api_endpoints.py` (1,207 LOC) is a god-route file
28 routes, 14 lazy imports, no Blueprint. Each route does its own DB connection management, response shaping, and error handling. Splitting into Blueprints by feature (lbo, football-field, exports, intelligence, services-llm) would cut the file by 60%+ and surface broken imports at startup.

### W2 — Triple data-fetching layer
- `data_integrator.py` (677 LOC) — live, uses yfinance.
- `data_layer/` (740 LOC) — multi-source gateway, only ever instantiated lazily from three call sites.
- `realtime_price_service.py` (197 LOC) — yet another fetcher, used live.

Pick one. Phase 2 needs reliable peer financials; this is the natural place to consolidate.

### W3 — Two `classify_company` functions, two taxonomies
- `valuation/tagging.py:classify_company` (post-Phase-1) — types: STORY, HYPERGROWTH, GROWTH_TECH, CYCLICAL, DISTRESSED, STABLE_VALUE, STABLE_VALUE_LOWGROWTH.
- `ib_valuation_framework.classify_company` (called from `valuation_professional.py`) — different taxonomy.

The same company gets two labels in two places. One must go.

### W4 — Lazy imports as architecture
Lazy import inside a function body is fine when (a) the import is heavy, (b) it's a circular-import workaround, or (c) the dependency is optional. In `axiom_api_endpoints.py` it's none of those — it's just used to avoid editing the import block. Cost: import errors land at request time, not boot time. A bad deploy serves 500s instead of failing CI.

### W5 — `requirements.txt` carries unused heavy deps
`celery`, `redis`, `pgvector`, `flask-talisman`, `flask-principal`, `flask-wtf`, `seaborn`, `matplotlib`, `pandas-datareader`, `prometheus-flask-exporter`, `python-json-logger` — `grep`-able usage in the Python tree was zero or one site for many. Pruning would shrink the Docker image significantly.

(I did not run a precise import-tracker; recommend `pip-tools` or `pyflakes`-based dead-import sweep before deletion.)

### W6 — `valuation_engine.py` calls itself "ml" in old comments
Phase 1 fixed the structure but inline strings (`"ML CALIBRATION LAYER"`, `"_ML_AVAILABLE"`, etc.) in `valuation_professional.py` still describe heuristic logic as ML. Cosmetic but reinforces the fiction the audit started with.

### W7 — 4 separate model `.pkl` artifacts at repo root
`ml_calibration_model.pkl`, `ml_model_y1.pkl`, `ml_model_y1y2.pkl`, plus `_metadata.json` for each. They live in repo root rather than a `models/` directory. Two of them (`y1`, `y1y2`) appear to be older walk-forward outputs; `ml_calibration_model.pkl` is the live one. Move under `ml/models/`, gitignore the stale ones.

### W8 — `monitor.py` is 946 LOC for a cron-driven script
Worth splitting `--snapshot` / `--evaluate` / `--report` into separate modules. Currently every cron invocation imports the entire monitor with all subcommands wired in.

## Recommended cleanup ordering

1. **Delete confirmed dead** (`mcp_server.py`, `services/agent.py`) once verified — ~515 LOC gone, zero risk.
2. **Decide on `institutional_valuation_engine.py`** — promote, fold into the live chain, or delete. 966 LOC of ambiguity.
3. **Consolidate data fetching** — fold `data_layer/` into `data_integrator.py` or vice versa, delete the loser. This is also the natural prep for Phase 2 peer-comp data needs.
4. **De-lazy-import `axiom_api_endpoints.py`**, split into Blueprints. Cuts cognitive load and exposes import errors at boot.
5. **Unify company classification** — keep one, delete the other.
6. **Prune `requirements.txt`** with a real dead-dep scan.

Items 1–3 alone would remove ~2,000 LOC without changing any behavior on the
live path.

## What I did NOT verify

- Whether the lazy-loaded routes are reachable from the UI in current production. The presence of a route ≠ usage. A traffic log would tell us which of the 80 routes are actually hit.
- Test coverage. There is one test file (`tests/test_phase1.py`, 228 LOC). Whether it covers anything meaningful.
- Whether `scripts/*.py` are wired to cron / launchd plists in production. The `com.axiom.ml.monitor.plist` next to `ml/monitor.py` suggests yes, at least for that one.

These would each be worth 30 minutes of follow-up. Out of scope for this pass.
