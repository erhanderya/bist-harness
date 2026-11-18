"""The MCP server really runs over stdio and enforces the harness rules for a client that knows nothing about the internals."""
import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]


def _payload(res):
    if getattr(res, "structuredContent", None):
        sc = res.structuredContent
        return sc.get("result", sc) if isinstance(sc, dict) else sc
    return json.loads(res.content[0].text)


async def _session_flow(tmp):
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONIOENCODING": "utf-8", "BIST_DECISION_DB": str(Path(tmp) / "mcp.sqlite")}
    params = StdioServerParameters(command=sys.executable, args=["-W", "ignore", "-m", "bist.harness.mcp_server"], env=env, cwd=str(ROOT))
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            names = {t.name for t in (await s.list_tools()).tools}
            assert {"start_analysis", "call_tool", "advance_state", "risk_gate", "submit_conclusion", "submit_human_review", "replay"} <= names
            assert "run_backtest" not in names and "get_stock_history" not in names     # analysis tools are only reachable through the harness
            st = _payload(await s.call_tool("start_analysis", {"question": "THYAO?", "focus": "fundamental_reaction"}))
            aid = st["analysis_id"]
            bad = _payload(await s.call_tool("call_tool", {"analysis_id": aid, "tool": "run_backtest", "params": {"variant": "A"}}))
            assert bad["error"]["code"] == "TOOL_NOT_ALLOWED_IN_STATE"
            assert _payload(await s.call_tool("advance_state", {"analysis_id": aid}))["ok"]
            assert _payload(await s.call_tool("select_universe", {"analysis_id": aid, "tickers": ["THYAO"]}))["ok"]
            skip = _payload(await s.call_tool("advance_state", {"analysis_id": aid, "to": "RUN_BACKTEST"}))
            assert skip["ok"] is False and "mandatory" in skip["error"]
            ghost = _payload(await s.call_tool("get_status", {"analysis_id": "nope"}))
            assert ghost["error"]["code"] == "UNKNOWN_ANALYSIS"
            d = _payload(await s.call_tool("describe_tools", {"state": "CHECK_DATA_QUALITY"}))
            assert [t["name"] for t in d["tools"]] == ["check_data_quality"]


def test_mcp_stdio_end_to_end(tmp_path):
    asyncio.run(asyncio.wait_for(_session_flow(tmp_path), timeout=120))
