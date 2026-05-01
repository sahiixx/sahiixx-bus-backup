"""A2A Router — Unified agent discovery and task routing for the SAHIIXX ecosystem.

Scans all registered services for /.well-known/agent.json, maintains a capability
index, and routes tasks to the best available agent.
"""
import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple

from .bridge import AgencyBridge, FridayBridge, GooseBridge, FixfizxBridge, MoltBridge

logger = logging.getLogger("sahiixx.bus")


class AgentEntry:
    """An agent discovered via A2A."""

    def __init__(self, service_name: str, agent_id: str, skills: List[str],
                 endpoint: str, bridge_type: str, metadata: Optional[Dict] = None):
        self.service_name = service_name
        self.agent_id = agent_id
        self.skills = skills
        self.endpoint = endpoint
        self.bridge_type = bridge_type
        self.metadata = metadata or {}

    def matches_skill(self, skill: str) -> bool:
        skill_lower = skill.lower()
        return any(skill_lower in s.lower() for s in self.skills)

    def matches_skills(self, skills: List[str]) -> bool:
        return any(self.matches_skill(s) for s in skills)

    def __repr__(self):
        return f"Agent({self.agent_id}, skills={self.skills}, via={self.bridge_type})"


class A2ARouter:
    """Unified A2A discovery and task router.

    Scans all registered services for their agent cards, builds a capability
    index, and routes tasks to the best available agent.

    Usage:
        router = A2ARouter()
        router.register("agency", AgencyBridge(), priority=10)
        router.register("friday", FridayBridge(), priority=5)

        await router.discover()
        results = await router.route("search for Dubai leads", skills=["search", "lead"])
    """

    def __init__(self):
        self.services: Dict[str, Tuple[Any, int]] = {}
        self.agents: List[AgentEntry] = []
        self._discovered = False

    def register(self, name: str, bridge: Any, priority: int = 0):
        """Register a service bridge with a priority (higher = preferred)."""
        self.services[name] = (bridge, priority)

    def unregister(self, name: str):
        """Remove a registered service."""
        self.services.pop(name, None)
        self.agents = [a for a in self.agents if a.service_name != name]

    async def discover(self) -> List[AgentEntry]:
        """Scan all registered services for A2A agent cards."""
        self.agents = []
        tasks = []
        for name, (bridge, priority) in self.services.items():
            tasks.append(self._discover_service(name, bridge, priority))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                logger.warning("Discovery failed: %s", result)
        self._discovered = True
        return self.agents

    async def _discover_service(self, name: str, bridge: Any, priority: int) -> None:
        """Discover agents from a single service."""
        try:
            if isinstance(bridge, AgencyBridge):
                agents = await bridge.discover_agents()
                for agent in agents:
                    self.agents.append(AgentEntry(
                        service_name=name,
                        agent_id=agent.get("agent_id", f"{name}-agent"),
                        skills=agent.get("skills", []),
                        endpoint=bridge.base_url,
                        bridge_type="agency",
                        metadata={"priority": priority, **agent},
                    ))
                # Also add the agency itself as an orchestrator
                self.agents.append(AgentEntry(
                    service_name=name,
                    agent_id=f"{name}-orchestrator",
                    skills=["orchestration", "mission", "delegation", "planning", "all"],
                    endpoint=bridge.base_url,
                    bridge_type="agency",
                    metadata={"priority": priority},
                ))
            elif isinstance(bridge, FridayBridge):
                self.agents.append(AgentEntry(
                    service_name=name,
                    agent_id=f"{name}-friday",
                    skills=["voice", "chat", "planning", "research", "creative", "agentic", "delegation"],
                    endpoint=bridge.base_url,
                    bridge_type="friday",
                    metadata={"priority": priority},
                ))
            elif isinstance(bridge, GooseBridge):
                self.agents.append(AgentEntry(
                    service_name=name,
                    agent_id=f"{name}-goose",
                    skills=["local", "ollama", "rag", "code", "search", "analysis", "swarm"],
                    endpoint=bridge.base_url,
                    bridge_type="goose",
                    metadata={"priority": priority},
                ))
            elif isinstance(bridge, FixfizxBridge):
                self.agents.append(AgentEntry(
                    service_name=name,
                    agent_id=f"{name}-nowhere",
                    skills=["dubai", "real-estate", "sales", "marketing", "content", "analytics", "operations"],
                    endpoint=bridge.base_url,
                    bridge_type="fixfizx",
                    metadata={"priority": priority},
                ))
            elif isinstance(bridge, MoltBridge):
                self.agents.append(AgentEntry(
                    service_name=name,
                    agent_id=f"{name}-molt",
                    skills=["telegram", "discord", "slack", "web", "messaging", "notification"],
                    endpoint=bridge.base_url,
                    bridge_type="molt",
                    metadata={"priority": priority},
                ))
            else:
                # Generic bridge — try agent card discovery
                card = await bridge.agent_card()
                if isinstance(card, dict) and "name" in card:
                    self.agents.append(AgentEntry(
                        service_name=name,
                        agent_id=card.get("name", f"{name}-agent"),
                        skills=card.get("skills", []),
                        endpoint=bridge.base_url,
                        bridge_type="generic",
                        metadata={"priority": priority, **card},
                    ))
        except Exception as e:
            logger.warning("Failed to discover agents from %s: %s", name, e)

    async def route(self, task: str, skills: Optional[List[str]] = None,
                    preferred_service: Optional[str] = None) -> List[Dict]:
        """Route a task to the best available agent(s).

        Args:
            task: The task description
            skills: Required skills for the task
            preferred_service: Prefer a specific service

        Returns:
            List of results from dispatched agents
        """
        if not self._discovered:
            await self.discover()

        candidates = self.agents

        if skills:
            candidates = [a for a in candidates if a.matches_skills(skills)]

        if preferred_service:
            preferred = [a for a in candidates if a.service_name == preferred_service]
            if preferred:
                candidates = preferred

        # Sort by priority (higher first)
        candidates.sort(key=lambda a: a.metadata.get("priority", 0), reverse=True)

        if not candidates:
            logger.warning("No agents found for task: %s (skills: %s)", task, skills)
            return []

        # Dispatch to top candidates (max 3)
        top = candidates[:3]
        results = []
        for agent in top:
            result = await self._dispatch(agent, task)
            results.append({
                "agent_id": agent.agent_id,
                "service": agent.service_name,
                "result": result,
            })
        return results

    async def _dispatch(self, agent: AgentEntry, task: str) -> Dict:
        """Dispatch a task to an agent via the appropriate bridge."""
        bridge, _ = self.services.get(agent.service_name, (None, 0))
        if not bridge:
            return {"error": f"service {agent.service_name} not registered"}

        try:
            if isinstance(bridge, AgencyBridge):
                return await bridge.submit_task(agent.agent_id, task, agent.skills)
            elif isinstance(bridge, FridayBridge):
                return await bridge.chat(task)
            elif isinstance(bridge, GooseBridge):
                return await bridge.chat(task)
            elif isinstance(bridge, FixfizxBridge):
                return await bridge.enhanced_chat(task, agent="sales")
            elif isinstance(bridge, MoltBridge):
                return await bridge.send_message("web", "default", task)
            else:
                return await bridge._request("POST", "/", {"task": task})
        except Exception as e:
            logger.error("Dispatch to %s failed: %s", agent.agent_id, e)
            return {"error": str(e)}

    async def health_check(self) -> Dict[str, Dict]:
        """Check health of all registered services."""
        results = {}
        for name, (bridge, _) in self.services.items():
            try:
                results[name] = await bridge.health()
            except Exception as e:
                results[name] = {"error": str(e)}
        return results

    def report(self) -> Dict:
        """Return router status."""
        return {
            "services": list(self.services.keys()),
            "agents": len(self.agents),
            "discovered": self._discovered,
            "agent_details": [
                {"id": a.agent_id, "service": a.service_name, "skills": a.skills, "priority": a.metadata.get("priority", 0)}
                for a in self.agents
            ],
        }