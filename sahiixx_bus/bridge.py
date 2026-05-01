"""Bridge clients for SAHIIXX ecosystem services.

Each bridge wraps the target service's existing API and provides
a uniform async interface for the A2A router and MCP gateway.
"""
import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

try:
    import aiohttp
except ImportError:
    aiohttp = None

logger = logging.getLogger("sahiixx.bus")


class BaseServiceBridge:
    """Base class for HTTP bridge clients."""

    def __init__(self, base_url: str, timeout: float = 30.0, session=None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = session
        self._health_cache: Optional[Dict] = None
        self._agent_card: Optional[Dict] = None

    async def _request(self, method: str, path: str, payload: Optional[Dict] = None, headers: Optional[Dict] = None) -> Dict:
        if not aiohttp:
            return {"error": "aiohttp not installed"}
        url = f"{self.base_url}{path}"
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        try:
            if self._session:
                async with self._session.request(method, url, json=payload, headers=headers, timeout=timeout) as resp:
                    body = await resp.json() if resp.content_type and "json" in resp.content_type else await resp.text()
                    return {"status": resp.status, "body": body}
            else:
                async with aiohttp.ClientSession() as session:
                    async with session.request(method, url, json=payload, headers=headers, timeout=timeout) as resp:
                        body = await resp.json() if resp.content_type and "json" in resp.content_type else await resp.text()
                        return {"status": resp.status, "body": body}
        except Exception as e:
            return {"error": str(e)}

    async def health(self) -> Dict:
        return await self._request("GET", "/health")

    async def agent_card(self) -> Dict:
        if self._agent_card:
            return self._agent_card
        result = await self._request("GET", "/.well-known/agent.json")
        if "error" not in result:
            self._agent_card = result.get("body", {})
        return result

    def report(self) -> Dict:
        return {"base_url": self.base_url, "type": self.__class__.__name__}


class AgencyBridge(BaseServiceBridge):
    """Bridge to agency-agents A2A server.

    Agency-agents exposes A2A JSON-RPC on port 8100+ and SSE streaming.
    Each registered agent gets its own port starting at 8100.
    """

    DEFAULT_PORT = 8100

    def __init__(self, host: str = "http://localhost", port: int = DEFAULT_PORT, **kwargs):
        super().__init__(f"{host}:{port}", **kwargs)
        self.host = host
        self.base_port = port

    async def submit_task(self, agent_id: str, task: str, skills: Optional[List[str]] = None) -> Dict:
        payload = {
            "jsonrpc": "2.0",
            "method": "tasks/send",
            "params": {
                "id": f"agency-{agent_id}",
                "message": {"role": "user", "parts": [{"type": "text", "text": task}]},
                "skills": skills or [],
            },
            "id": 1,
        }
        return await self._request("POST", "/", payload)

    async def mission(self, description: str, preset: Optional[str] = None, agents: Optional[List[str]] = None) -> Dict:
        payload = {"description": description}
        if preset:
            payload["preset"] = preset
        if agents:
            payload["agents"] = agents
        return await self._request("POST", "/mission", payload)

    async def stream(self, task: str) -> Dict:
        return await self._request("POST", "/stream", {"task": task})

    async def discover_agents(self) -> List[Dict]:
        card = await self.agent_card()
        if isinstance(card, dict) and "agents" in card:
            return card["agents"]
        return []


class FridayBridge(BaseServiceBridge):
    """Bridge to FRIDAY-OS A2A server.

    FRIDAY exposes: /chat/stream (SSE), /a2a/invoke, /tool/{name}, /speak, /connectors
    """

    def __init__(self, host: str = "http://localhost", port: int = 8000, **kwargs):
        super().__init__(f"{host}:{port}", **kwargs)

    async def chat(self, message: str, session_id: Optional[str] = None) -> Dict:
        payload = {"message": message}
        if session_id:
            payload["session_id"] = session_id
        return await self._request("POST", "/a2a/invoke", payload)

    async def chat_stream(self, message: str) -> Dict:
        return await self._request("POST", "/chat/stream", {"message": message})

    async def call_tool(self, tool_name: str, params: Dict) -> Dict:
        return await self._request("POST", f"/tool/{tool_name}", params)

    async def speak(self, text: str) -> Dict:
        return await self._request("POST", "/speak", {"text": text})

    async def list_connectors(self) -> Dict:
        return await self._request("GET", "/connectors")


class GooseBridge(BaseServiceBridge):
    """Bridge to Goose-AIOS FastAPI server.

    Goose exposes: /chat (WebSocket), /agents (REST), /knowledge/sync (REST)
    """

    def __init__(self, host: str = "http://localhost", port: int = 8001, **kwargs):
        super().__init__(f"{host}:{port}", **kwargs)

    async def chat(self, message: str, model: Optional[str] = None) -> Dict:
        payload = {"message": message}
        if model:
            payload["model"] = model
        return await self._request("POST", "/chat", payload)

    async def list_agents(self) -> Dict:
        return await self._request("GET", "/agents")

    async def sync_knowledge(self) -> Dict:
        return await self._request("POST", "/knowledge/sync", {})

    async def delegate(self, task: str, role: str = "coordinator") -> Dict:
        return await self._request("POST", "/chat", {
            "message": f"Delegate task to {role}: {task}",
            "mode": "swarm",
        })


class FixfizxBridge(BaseServiceBridge):
    """Bridge to NOWHERE.AI (Fixfizx) FastAPI backend.

    Fixfizx exposes: /api/health, /api/ai/advanced/enhanced-chat, /api/agents/*, /api/contact
    """

    def __init__(self, host: str = "http://localhost", port: int = 8002, **kwargs):
        super().__init__(f"{host}:{port}", **kwargs)

    async def enhanced_chat(self, message: str, agent: str = "sales", context: Optional[Dict] = None) -> Dict:
        payload = {"message": message, "agent": agent}
        if context:
            payload["context"] = context
        return await self._request("POST", "/api/ai/advanced/enhanced-chat", payload)

    async def list_agents(self) -> Dict:
        return await self._request("GET", "/api/ai/advanced/agents")

    async def dubai_market_analysis(self, query: str) -> Dict:
        return await self._request("POST", "/api/ai/advanced/dubai-market-analysis", {"query": query})

    async def qualify_lead(self, lead_data: Dict) -> Dict:
        return await self._request("POST", "/api/contact", lead_data)


class MoltBridge(BaseServiceBridge):
    """Bridge to Moltworker Cloudflare Worker gateway.

    Moltworker exposes: /sandbox-health, /api/status, /api/admin/*, proxied Moltbot gateway
    """

    def __init__(self, base_url: str = "https://moltbot-sandbox.sahiixx.workers.dev", **kwargs):
        super().__init__(base_url, **kwargs)

    async def sandbox_health(self) -> Dict:
        return await self._request("GET", "/sandbox-health")

    async def status(self) -> Dict:
        return await self._request("GET", "/api/status")

    async def send_message(self, channel: str, target: str, message: str, token: str = "") -> Dict:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return await self._request("POST", "/message", {
            "channel": channel,
            "target": target,
            "message": message,
        }, headers=headers)