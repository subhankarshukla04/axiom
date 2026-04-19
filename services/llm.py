"""
AXIOM LLM Service
OpenRouter-backed AI commentary for valuations, theses, and anomalies.
"""

import json
import logging
import os
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_BASE_URL = "https://openrouter.ai/api/v1"
_MODEL = "anthropic/claude-sonnet-4-6"
_TIMEOUT = 60


def _api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY not set")
    return key


def _call(system: str, user: str, max_tokens: int = 800, retries: int = 2) -> str:
    """Base OpenRouter call with retry on 5xx."""
    headers = {
        "Authorization": f"Bearer {_api_key()}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://axiom.local",
        "X-Title": "AXIOM Valuation Platform",
    }
    payload = {
        "model": _MODEL,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    last_err = None
    for attempt in range(retries + 1):
        try:
            resp = httpx.post(
                f"{_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        except httpx.HTTPStatusError as e:
            last_err = e
            if e.response.status_code < 500:
                raise
            if attempt < retries:
                time.sleep(2 ** attempt)
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"LLM call failed after {retries+1} attempts: {last_err}")


def _call_json(system: str, user: str, max_tokens: int = 1000) -> dict:
    """Call LLM and parse JSON response. Falls back to empty dict on parse error."""
    raw = _call(system, user + "\n\nRespond with valid JSON only.", max_tokens)
    # Strip markdown fences if present
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("LLM returned non-JSON: %s", text[:200])
        return {"raw": text}


_ANALYST_SYSTEM = """You are an institutional investment analyst at a top-tier investment bank.
Your commentary is precise, data-driven, and grounded only in the information provided.
Rules:
- Always cite the specific data source (FRED, EDGAR, Finnhub, internal model).
- Express confidence levels when data is limited ("based on limited data...").
- Never fabricate specific numbers — reference only what's in the context.
- Be concise. Professional audience. No fluff."""


def generate_valuation_commentary(
    company: dict,
    valuation_result: dict,
    anomalies: Optional[list] = None,
    rag_context: Optional[str] = None,
) -> str:
    """Plain-English explanation of DCF output, upside/downside, key drivers."""
    ticker = company.get("ticker", company.get("name", "Unknown"))
    fair_value = valuation_result.get("final_price_per_share") or valuation_result.get("final_equity_value")
    current_price = valuation_result.get("current_price")
    upside = valuation_result.get("upside_pct")
    rec = valuation_result.get("recommendation", "N/A")
    wacc = valuation_result.get("wacc")

    anomaly_text = ""
    if anomalies:
        items = [f"- {a.get('message', '')}" for a in anomalies[:3]]
        anomaly_text = "\nKey anomalies flagged:\n" + "\n".join(items)

    context_text = f"\n\nFiling context (MD&A):\n{rag_context}" if rag_context else ""

    user = f"""Company: {ticker} | Sector: {company.get('sector', 'N/A')}
DCF Fair Value: ${fair_value:,.2f} | Current Price: ${current_price:,.2f} | Upside: {upside:+.1f}%
WACC: {wacc*100:.1f}% | Recommendation: {rec}
Revenue: ${company.get('revenue', 0)/1e6:,.0f}M | EBITDA Margin: {company.get('ebitda', 0)/max(1, company.get('revenue', 1))*100:.1f}%
{anomaly_text}{context_text}

Write a 3-paragraph valuation commentary: (1) summary of fair value vs market, (2) key value drivers, (3) risks and caveats."""

    return _call(_ANALYST_SYSTEM, user, max_tokens=600)


def generate_investment_thesis(
    company: dict,
    valuation: dict,
    scenario_comparison: Optional[dict] = None,
    rag_context: Optional[str] = None,
) -> dict:
    """Returns {bull_case, bear_case, key_risks, recommendation, confidence}."""
    ticker = company.get("ticker", company.get("name", "Unknown"))
    fair_value = valuation.get("final_price_per_share") or 0
    upside = valuation.get("upside_pct", 0)

    scenario_text = ""
    if scenario_comparison:
        bull = scenario_comparison.get("bull", {})
        bear = scenario_comparison.get("bear", {})
        scenario_text = f"\nBull scenario upside: {bull.get('upside_pct', 'N/A')}% | Bear scenario upside: {bear.get('upside_pct', 'N/A')}%"

    context_text = f"\n\nFiling context:\n{rag_context[:500]}" if rag_context else ""

    user = f"""Company: {ticker} | Sector: {company.get('sector', 'N/A')}
DCF Fair Value: ${fair_value:,.2f} | Upside: {upside:+.1f}%
Revenue: ${company.get('revenue', 0)/1e6:,.0f}M | EBITDA: ${company.get('ebitda', 0)/1e6:,.0f}M
{scenario_text}{context_text}

Generate an investment thesis as JSON:
{{
  "bull_case": "2-3 sentence bull thesis",
  "bear_case": "2-3 sentence bear thesis",
  "key_risks": ["risk1", "risk2", "risk3"],
  "recommendation": "BUY|HOLD|SELL",
  "confidence": "HIGH|MEDIUM|LOW",
  "price_target": <number>,
  "rationale": "1-sentence summary"
}}"""

    return _call_json(_ANALYST_SYSTEM, user, max_tokens=600)


def explain_anomaly(anomaly: dict, company_context: dict) -> str:
    """Why is this assumption unusual? What does it mean for the valuation?"""
    user = f"""Company: {company_context.get('name', 'Unknown')} | Sector: {company_context.get('sector', 'N/A')}
Anomaly detected: {anomaly.get('message', 'Unknown anomaly')}
Parameter: {anomaly.get('parameter', 'N/A')} | Value: {anomaly.get('value', 'N/A')} | Z-score: {anomaly.get('z_score', 'N/A')}
Benchmark: {anomaly.get('benchmark', 'N/A')}

In 2-3 sentences: (1) Why is this assumption unusual, (2) what it implies for the valuation, (3) whether it's likely a data error or a genuine outlier."""

    return _call(_ANALYST_SYSTEM, user, max_tokens=200)


def summarize_smart_money(positions: list, company: dict) -> str:
    """What are the biggest institutional holders doing? Net buying or selling?"""
    if not positions:
        return "No institutional 13F data available for this ticker."

    holders_text = "\n".join(
        f"- {p.get('fund', 'Unknown')}: {p.get('shares', 0):,} shares (${p.get('value_1000', 0)*1000:,.0f})"
        for p in positions[:5]
    )

    user = f"""Company: {company.get('ticker', company.get('name', 'Unknown'))} | Sector: {company.get('sector', 'N/A')}
Institutional 13F holders (45-day delayed data):
{holders_text}

In 2-3 sentences, summarize institutional sentiment: who holds it, implied conviction level, and what this suggests for the investment thesis."""

    return _call(_ANALYST_SYSTEM, user, max_tokens=200)


def generate_lbo_commentary(company: dict, lbo_result: dict) -> str:
    """Interpret LBO returns: is this an attractive PE target?"""
    user = f"""Company: {company.get('ticker', company.get('name', 'Unknown'))} | Sector: {company.get('sector', 'N/A')}
LBO Analysis:
- Entry EV: ${lbo_result.get('entry_ev', 0)/1e6:,.0f}M
- Exit EV: ${lbo_result.get('exit_ev', 0)/1e6:,.0f}M  
- IRR: {lbo_result.get('irr', 0)*100:.1f}%
- MOIC: {lbo_result.get('moic', 0):.2f}x
- Hold period: {lbo_result.get('hold_years', 5)} years

In 3 sentences: (1) Is this an attractive PE return? (2) Key value creation levers, (3) Main execution risks."""

    return _call(_ANALYST_SYSTEM, user, max_tokens=250)
