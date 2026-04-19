#!/usr/bin/env python3
"""
AXIOM MCP Server
Exposes AXIOM's valuation engine as MCP tools for Claude Desktop / Claude Code.

Install MCP SDK: pip install mcp
Configure in Claude Desktop:
  ~/Library/Application Support/Claude/claude_desktop_config.json

Usage from Claude: "Run a DCF on AAPL ticker"
"""

import asyncio
import json
import logging
import os
import sys

# Add valuation_app to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    import mcp.types as types
except ImportError:
    print("ERROR: MCP SDK not installed. Run: pip install mcp", file=sys.stderr)
    sys.exit(1)

server = Server("axiom-valuation")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="run_dcf",
            description="Run DCF valuation for a company by database ID. Returns fair value, upside/downside, and recommendation.",
            inputSchema={
                "type": "object",
                "properties": {"company_id": {"type": "integer", "description": "Internal AXIOM company ID"}},
                "required": ["company_id"],
            },
        ),
        types.Tool(
            name="run_lbo",
            description="Run LBO analysis for a PE buyout scenario.",
            inputSchema={
                "type": "object",
                "properties": {
                    "company_id": {"type": "integer"},
                    "entry_multiple": {"type": "number", "description": "EV/EBITDA entry multiple (default 10x)"},
                    "leverage": {"type": "number", "description": "Debt/EBITDA leverage (default 5x)"},
                    "hold_years": {"type": "integer", "description": "Hold period in years (default 5)"},
                },
                "required": ["company_id"],
            },
        ),
        types.Tool(
            name="get_financials",
            description="Fetch company financials from SEC EDGAR: revenue, EBITDA, debt, cash.",
            inputSchema={
                "type": "object",
                "properties": {"ticker": {"type": "string", "description": "Stock ticker (e.g. AAPL)"}},
                "required": ["ticker"],
            },
        ),
        types.Tool(
            name="analyze_anomalies",
            description="Check if valuation assumptions are statistical outliers vs sector benchmarks.",
            inputSchema={
                "type": "object",
                "properties": {"company_id": {"type": "integer"}},
                "required": ["company_id"],
            },
        ),
        types.Tool(
            name="build_football_field",
            description="Get valuation ranges across DCF, EV/EBITDA comps, LBO floor, analyst targets.",
            inputSchema={
                "type": "object",
                "properties": {"company_id": {"type": "integer"}},
                "required": ["company_id"],
            },
        ),
        types.Tool(
            name="find_peers",
            description="Find comparable companies by SEC SIC code for comps analysis.",
            inputSchema={
                "type": "object",
                "properties": {"company_id": {"type": "integer"}},
                "required": ["company_id"],
            },
        ),
        types.Tool(
            name="get_macro_rates",
            description="Get live macro rates from FRED: risk-free rate, VIX, yield curve, HY spread.",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="ask_10k",
            description="Ask a question grounded in the company\'s latest 10-K filing via RAG.",
            inputSchema={
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "question": {"type": "string"},
                },
                "required": ["ticker", "question"],
            },
        ),
        types.Tool(
            name="generate_thesis",
            description="Generate a bull/bear investment thesis using AI for a company.",
            inputSchema={
                "type": "object",
                "properties": {"company_id": {"type": "integer"}},
                "required": ["company_id"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    try:
        result = await asyncio.get_event_loop().run_in_executor(
            None, _execute_tool_sync, name, arguments
        )
        return [types.TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
    except Exception as e:
        logger.error(f"Tool {name} failed: {e}", exc_info=True)
        return [types.TextContent(type="text", text=json.dumps({"error": str(e)}))]


def _execute_tool_sync(name: str, arguments: dict) -> dict:
    from services.agent import _execute_tool
    return _execute_tool(name, arguments)


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
