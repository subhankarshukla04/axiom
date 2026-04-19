"""
AXIOM AI Analyst Agent
Agentic loop using OpenRouter function calling.
One endpoint: natural language → full investment memo.
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
_MAX_ITERATIONS = 10
_TIMEOUT = 90

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_financials",
            "description": "Fetch company financials from SEC EDGAR: revenue, EBITDA, debt, cash, shares outstanding",
            "parameters": {
                "type": "object",
                "properties": {"ticker": {"type": "string", "description": "Stock ticker symbol"}},
                "required": ["ticker"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_dcf",
            "description": "Run DCF valuation for a company by ID. Returns fair value, upside, recommendation",
            "parameters": {
                "type": "object",
                "properties": {"company_id": {"type": "integer", "description": "Internal company database ID"}},
                "required": ["company_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_lbo",
            "description": "Run LBO analysis for a PE buyout scenario",
            "parameters": {
                "type": "object",
                "properties": {
                    "company_id": {"type": "integer"},
                    "entry_multiple": {"type": "number", "description": "EV/EBITDA entry multiple"},
                    "leverage": {"type": "number", "description": "Debt/EBITDA leverage ratio"},
                    "hold_years": {"type": "integer", "description": "Holding period in years"},
                },
                "required": ["company_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_macro_rates",
            "description": "Get live macro rates: risk-free rate, VIX, yield curve, HY spread from FRED",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_anomalies",
            "description": "Check if valuation assumptions are statistical outliers vs sector benchmarks",
            "parameters": {
                "type": "object",
                "properties": {"company_id": {"type": "integer"}},
                "required": ["company_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "build_football_field",
            "description": "Get valuation ranges across DCF, EV/EBITDA comps, LBO floor, analyst targets",
            "parameters": {
                "type": "object",
                "properties": {"company_id": {"type": "integer"}},
                "required": ["company_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_10k",
            "description": "Ask a question grounded in the company's latest 10-K filing (RAG). Use for management commentary, risk factors, growth strategy",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "question": {"type": "string"},
                },
                "required": ["ticker", "question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_peers",
            "description": "Find comparable companies by SEC SIC code for comps analysis",
            "parameters": {
                "type": "object",
                "properties": {"company_id": {"type": "integer"}},
                "required": ["company_id"],
            },
        },
    },
]

_SYSTEM_PROMPT = """You are an elite investment banking analyst at a bulge-bracket firm.
Your task: produce a rigorous, data-driven investment memo.

Workflow:
1. Always start by fetching financials and macro rates.
2. Run a DCF valuation.
3. If the query mentions PE/buyout/LBO, run LBO analysis.
4. Check for anomalies in the assumptions.
5. Build a football field for valuation context.
6. Ask the 10-K for management's view on growth and key risks.
7. Find peers for comps context.
8. Synthesize everything into a professional memo.

Output format for the final memo:
## Investment Summary
## Company Overview
## Valuation Analysis  
## LBO Analysis (if applicable)
## Key Risks
## Recommendation

Rules:
- Cite data sources explicitly.
- Never fabricate numbers — only use tool results.
- Express uncertainty when data is incomplete.
- Be concise but comprehensive."""


def _api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY not set")
    return key


def _execute_tool(tool_name: str, params: dict, company_id: Optional[int] = None) -> dict:
    """Dispatch tool call to appropriate service/endpoint."""
    try:
        if tool_name == "get_financials":
            from data_layer import DataLayer
            dl = DataLayer()
            result = dl.edgar.get_financials(params["ticker"])
            return {"source": result.source, "data": result.value, "available": result.available}

        elif tool_name == "run_dcf":
            from valuation_service import ValuationService
            svc = ValuationService()
            cid = params.get("company_id", company_id)
            data = svc.fetch_company_data(cid)
            if not data:
                return {"error": f"Company ID {cid} not found"}
            result = svc.run_valuation(data)
            return result or {"error": "Valuation failed"}

        elif tool_name == "run_lbo":
            from lbo_engine import LBOEngine
            from valuation_service import ValuationService
            svc = ValuationService()
            cid = params.get("company_id", company_id)
            data = svc.fetch_company_data(cid)
            if not data:
                return {"error": f"Company ID {cid} not found"}
            engine = LBOEngine()
            return engine.run_lbo(
                company_data=data,
                entry_multiple=params.get("entry_multiple", 10.0),
                leverage=params.get("leverage", 5.0),
                hold_years=params.get("hold_years", 5),
            )

        elif tool_name == "get_macro_rates":
            from data_layer import DataLayer
            dl = DataLayer()
            rates_raw = dl.get_macro_rates()
            return {k: {"value": v.value, "source": v.source} for k, v in rates_raw.items()}

        elif tool_name == "analyze_anomalies":
            from intelligence.anomaly_detector import analyze_assumptions
            from valuation_service import ValuationService
            svc = ValuationService()
            cid = params.get("company_id", company_id)
            data = svc.fetch_company_data(cid)
            if not data:
                return {"error": f"Company ID {cid} not found"}
            return {"anomalies": analyze_assumptions(data, data.get("sector", ""))}

        elif tool_name == "build_football_field":
            from football_field import FootballFieldEngine
            from valuation_service import ValuationService
            svc = ValuationService()
            cid = params.get("company_id", company_id)
            data = svc.fetch_company_data(cid)
            if not data:
                return {"error": f"Company ID {cid} not found"}
            engine = FootballFieldEngine()
            return engine.build(data)

        elif tool_name == "ask_10k":
            from services.rag import answer_question
            return answer_question(params["ticker"], params["question"])

        elif tool_name == "find_peers":
            from peer_discovery import PeerDiscovery
            from valuation_service import ValuationService
            svc = ValuationService()
            cid = params.get("company_id", company_id)
            data = svc.fetch_company_data(cid)
            if not data:
                return {"error": f"Company ID {cid} not found"}
            disc = PeerDiscovery()
            return disc.find_peers(data)

        else:
            return {"error": f"Unknown tool: {tool_name}"}

    except Exception as e:
        logger.warning(f"Tool {tool_name} failed: {e}")
        return {"error": str(e)}


def analyze(query: str, company_id: Optional[int] = None) -> dict:
    """
    Agentic loop: send query + tools to OpenRouter, execute tool calls,
    repeat until final answer. Returns structured memo + metadata.
    """
    headers = {
        "Authorization": f"Bearer {_api_key()}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://axiom.local",
        "X-Title": "AXIOM Agent",
    }

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": f"Query: {query}" + (f"\n\nCompany ID in database: {company_id}" if company_id else "")},
    ]

    steps_taken = []
    data_sources = []
    total_tokens = 0
    iteration = 0

    while iteration < _MAX_ITERATIONS:
        iteration += 1
        payload = {
            "model": _MODEL,
            "messages": messages,
            "tools": TOOLS,
            "max_tokens": 2000,
        }

        try:
            resp = httpx.post(
                f"{_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"Agent API call failed at iteration {iteration}: {e}")
            break

        usage = data.get("usage", {})
        total_tokens += usage.get("total_tokens", 0)

        choice = data["choices"][0]
        message = choice["message"]
        messages.append(message)

        finish_reason = choice.get("finish_reason", "")

        # Check for tool calls
        tool_calls = message.get("tool_calls", [])
        if tool_calls:
            for tc in tool_calls:
                fn_name = tc["function"]["name"]
                try:
                    fn_params = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    fn_params = {}

                steps_taken.append(f"Called {fn_name}({json.dumps(fn_params)[:100]})")
                result = _execute_tool(fn_name, fn_params, company_id)

                # Track data sources
                if isinstance(result, dict) and "source" in result:
                    data_sources.append(result["source"])

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(result)[:4000],  # Truncate large results
                })
        elif finish_reason in ("stop", "end_turn"):
            # Final answer
            memo_text = message.get("content", "")
            return {
                "memo": memo_text,
                "steps_taken": steps_taken,
                "data_sources": list(set(data_sources)),
                "iterations": iteration,
                "total_tokens": total_tokens,
                "recommendation": _extract_recommendation(memo_text),
            }
        else:
            # Unexpected finish
            break

    return {
        "memo": messages[-1].get("content", "Analysis incomplete — reached iteration limit"),
        "steps_taken": steps_taken,
        "data_sources": list(set(data_sources)),
        "iterations": iteration,
        "total_tokens": total_tokens,
        "recommendation": "INCOMPLETE",
        "warning": "Agent reached max iterations or encountered an error",
    }


def _extract_recommendation(memo_text: str) -> str:
    """Extract BUY/HOLD/SELL from memo text."""
    import re
    m = re.search(r"\b(STRONG BUY|BUY|HOLD|SELL|STRONG SELL|AVOID)\b", memo_text, re.IGNORECASE)
    return m.group(0).upper() if m else "N/A"
