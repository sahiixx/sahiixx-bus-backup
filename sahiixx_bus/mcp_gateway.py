"""MCP Gateway — Unified tool proxy for the SAHIIXX ecosystem.

Maps all ecosystem tools into a single MCP interface, delegating to the
appropriate service. Runs SafetyCouncil scanning before executing any tool.
"""
import asyncio
import json
import logging
from typing import Any, Callable, Dict, List, Optional

from sovereign_swarm import SafetyCouncil, MCPServer

from .bridge import AgencyBridge, FridayBridge, GooseBridge, FixfizxBridge, MoltBridge

logger = logging.getLogger("sahiixx.bus")


class MCPGateway:
    """Unified MCP gateway that proxies tool calls across the ecosystem.

    Combines tools from agency-agents (19 tools), goose-aios (26 tools),
    Fixfizx (AI endpoints), and sovereign-swarm (12 tools) into one schema.

    All tool calls pass through SafetyCouncil scanning before execution.
    """

    # Tool schemas organized by source
    AGENCY_TOOLS = {
        "agency.search_memory": {"query": "string", "limit": "integer"},
        "agency.store_memory": {"key": "string", "value": "any", "tags": "string"},
        "agency.spawn_agent": {"specialty": "string"},
        "agency.kill_agent": {"agent_id": "string"},
        "agency.publish_event": {"topic": "string", "payload": "dict"},
        "agency.mission": {"description": "string", "preset": "string", "agents": "list"},
        "agency.chat": {"message": "string", "model": "string"},
        "agency.voice_command": {"text": "string"},
        "agency.delegate_task": {"task": "string", "role": "string"},
        "agency.market_analysis": {"query": "string"},
    }

    FRIDAY_TOOLS = {
        "friday.chat": {"message": "string", "session_id": "string"},
        "friday.stream": {"message": "string"},
        "friday.call_tool": {"tool_name": "string", "params": "dict"},
        "friday.speak": {"text": "string"},
    }

    GOOSE_TOOLS = {
        "goose.chat": {"message": "string", "model": "string"},
        "goose.delegate": {"task": "string", "role": "string"},
        "goose.rag_query": {"query": "string"},
        "goose.rag_ingest": {"content": "string", "source": "string"},
        "goose.bash": {"command": "string"},
        "goose.read_file": {"path": "string"},
        "goose.write_file": {"path": "string", "content": "string"},
        "goose.web_search": {"query": "string"},
        "goose.memory_save": {"key": "string", "value": "string"},
        "goose.memory_recall": {"query": "string"},
    }

    FIXZIX_TOOLS = {
        "fixfizx.chat": {"message": "string", "agent": "string", "context": "dict"},
        "fixfizx.qualify_lead": {"lead_data": "dict"},
        "fixfizx.market_analysis": {"query": "string"},
        "fixfizx.list_agents": {},
    }

    MOLT_TOOLS = {
        "molt.send_message": {"channel": "string", "target": "string", "message": "string"},
        "molt.health": {},
        "molt.status": {},
    }

    def __init__(self, safety: Optional[SafetyCouncil] = None):
        self.safety = safety or SafetyCouncil()
        self.agency: Optional[AgencyBridge] = None
        self.friday: Optional[FridayBridge] = None
        self.goose: Optional[GooseBridge] = None
        self.fixfizx: Optional[FixfizxBridge] = None
        self.molt: Optional[MoltBridge] = None
        self._all_tools: Dict[str, Dict] = {}
        self._build_tool_index()

    def _build_tool_index(self):
        self._all_tools = {}
        self._all_tools.update(self.AGENCY_TOOLS)
        self._all_tools.update(self.FRIDAY_TOOLS)
        self._all_tools.update(self.GOOSE_TOOLS)
        self._all_tools.update(self.FIXZIX_TOOLS)
        self._all_tools.update(self.MOLT_TOOLS)

    def register_bridge(self, name: str, bridge: Any):
        """Register a service bridge for tool dispatch."""
        if isinstance(bridge, AgencyBridge):
            self.agency = bridge
        elif isinstance(bridge, FridayBridge):
            self.friday = bridge
        elif isinstance(bridge, GooseBridge):
            self.goose = bridge
        elif isinstance(bridge, FixfizxBridge):
            self.fixfizx = bridge
        elif isinstance(bridge, MoltBridge):
            self.molt = bridge

    def schema(self, tool: str) -> Dict:
        """Return the parameter schema for a tool."""
        return self._all_tools.get(tool, {})

    def list_tools(self) -> List[str]:
        """List all available tools."""
        return list(self._all_tools.keys())

    async def handle(self, request: Dict) -> Dict:
        """Handle an MCP request with safety scanning.

        Args:
            request: {"tool": "agency.mission", "params": {"description": "audit security"}}

        Returns:
            {"tool": "agency.mission", "result": ..., "status": "ok"} or
            {"tool": ..., "error": ..., "status": "error"}
        """
        tool = request.get("tool", "")
        params = request.get("params", {})

        if tool not in self._all_tools:
            return {"error": "unknown_tool", "tool": tool}

        # Validate params against schema
        schema = self._all_tools[tool]
        if schema:
            valid_keys = set(schema.keys())
            unknown = set(params.keys()) - valid_keys
            if unknown:
                return {"error": "unknown_params", "tool": tool, "unknown": list(unknown)}

        # Extract text content for safety scan
        text_content = json.dumps(params)
        scan_result = self.safety.scan(text_content)
        if scan_result["blocked"]:
            logger.warning("SafetyCouncil blocked tool call %s: %s", tool, scan_result["rule"])
            return {"error": "blocked_by_safety", "tool": tool, "rule": scan_result["rule"], "confidence": scan_result["confidence"]}

        # Dispatch to the appropriate bridge
        try:
            if tool.startswith("agency.") and self.agency:
                return await self._dispatch_agency(tool, params)
            elif tool.startswith("friday.") and self.friday:
                return await self._dispatch_friday(tool, params)
            elif tool.startswith("goose.") and self.goose:
                return await self._dispatch_goose(tool, params)
            elif tool.startswith("fixfizx.") and self.fixfizx:
                return await self._dispatch_fixfizx(tool, params)
            elif tool.startswith("molt.") and self.molt:
                return await self._dispatch_molt(tool, params)
            else:
                return {"error": "service_unavailable", "tool": tool, "hint": f"No bridge registered for {tool.split('.')[0]}"}
        except Exception as e:
            logger.error("Tool dispatch error for %s: %s", tool, e)
            return {"tool": tool, "error": str(e), "status": "error"}

    async def _dispatch_agency(self, tool: str, params: Dict) -> Dict:
        if tool == "agency.mission":
            result = await self.agency.mission(params["description"], params.get("preset"), params.get("agents"))
        elif tool == "agency.chat":
            result = await self.agency.submit_task("default", params["message"])
        else:
            result = await self.agency.submit_task("default", json.dumps(params), list(params.keys()))
        return {"tool": tool, "result": result, "status": "ok"}

    async def _dispatch_friday(self, tool: str, params: Dict) -> Dict:
        if tool == "friday.chat":
            result = await self.friday.chat(params["message"], params.get("session_id"))
        elif tool == "friday.stream":
            result = await self.friday.chat_stream(params["message"])
        elif tool == "friday.call_tool":
            result = await self.friday.call_tool(params["tool_name"], params.get("params", {}))
        elif tool == "friday.speak":
            result = await self.friday.speak(params["text"])
        else:
            result = {"error": f"unknown friday tool: {tool}"}
        return {"tool": tool, "result": result, "status": "ok"}

    async def _dispatch_goose(self, tool: str, params: Dict) -> Dict:
        if tool == "goose.chat":
            result = await self.goose.chat(params["message"], params.get("model"))
        elif tool == "goose.delegate":
            result = await self.goose.delegate(params["task"], params.get("role", "coordinator"))
        else:
            result = await self.goose.chat(json.dumps(params))
        return {"tool": tool, "result": result, "status": "ok"}

    async def _dispatch_fixfizx(self, tool: str, params: Dict) -> Dict:
        if tool == "fixfizx.chat":
            result = await self.fixfizx.enhanced_chat(params["message"], params.get("agent", "sales"), params.get("context"))
        elif tool == "fixfizx.qualify_lead":
            result = await self.fixfizx.qualify_lead(params["lead_data"])
        elif tool == "fixfizx.market_analysis":
            result = await self.fixfizx.dubai_market_analysis(params["query"])
        elif tool == "fixfizx.list_agents":
            result = await self.fixfizx.list_agents()
        else:
            result = {"error": f"unknown fixfizx tool: {tool}"}
        return {"tool": tool, "result": result, "status": "ok"}

    async def _dispatch_molt(self, tool: str, params: Dict) -> Dict:
        if tool == "molt.send_message":
            result = await self.molt.send_message(params["channel"], params["target"], params["message"], params.get("token", ""))
        elif tool == "molt.health":
            result = await self.molt.sandbox_health()
        elif tool == "molt.status":
            result = await self.molt.status()
        else:
            result = {"error": f"unknown molt tool: {tool}"}
        return {"tool": tool, "result": result, "status": "ok"}

    def report(self) -> Dict:
        return {
            "total_tools": len(self._all_tools),
            "tools": list(self._all_tools.keys()),
            "bridges": {
                "agency": self.agency is not None,
                "friday": self.friday is not None,
                "goose": self.goose is not None,
                "fixfizx": self.fixfizx is not None,
                "molt": self.molt is not None,
            },
        }