"""Tests for sahiixx-bus — unified orchestration layer."""
import asyncio
import sys
import os
import tempfile
from pathlib import Path

# Add sovereign_swarm from Downloads to path
sys.path.insert(0, "/mnt/c/Users/Sahil Khan/Downloads")

from sovereign_swarm import (
    SwarmBus, SwarmMemory, SafetyCouncil, RBACGuard, Permission,
    EconomicEngine, BudgetController, MCPServer, A2ACardServer,
    MetaOrchestrator, AgentProfile,
)
from sahiixx_bus.bridge import AgencyBridge, FridayBridge, GooseBridge, FixfizxBridge, MoltBridge
from sahiixx_bus.a2a_router import A2ARouter, AgentEntry
from sahiixx_bus.mcp_gateway import MCPGateway


class TestRunner:
    def __init__(self):
        self.passed = 0
        self.failed = 0

    def check(self, name: str, condition: bool):
        if condition:
            self.passed += 1
            print(f"  ✓ {name}")
        else:
            self.failed += 1
            print(f"  ✗ {name}")

    async def run_unit(self):
        print("\n[UNIT TESTS]")

        # Core primitives re-exported from sovereign_swarm
        bus = SwarmBus(Path(tempfile.mkdtemp()) / "bus_test.db")
        await bus.init()
        await bus.publish("test.topic", {"msg": "hello"})
        msgs = await bus.history("test.topic")
        self.check("bus_publish_and_history", len(msgs) >= 1 and msgs[0]["msg"] == "hello")
        await bus.close()

        mem = SwarmMemory(Path(tempfile.mkdtemp()) / "mem_test.db")
        await mem.init()
        await mem.store("key1", {"data": "value1"}, tags="test")
        found = await mem.search("value1")
        self.check("memory_search", len(found) >= 1)
        await mem.close()

        safety = SafetyCouncil()
        self.check("safety_blocks_rm_rf", safety.scan("rm -rf /", 0.5)["blocked"])
        self.check("safety_allows_clean", not safety.scan("hello world", 0.5)["blocked"])

        rbac = RBACGuard()
        rbac.assign("admin", "admin")
        self.check("rbac_admin_has_spawn", rbac.check("admin", Permission.SPAWN))
        self.check("rbac_admin_has_kill", rbac.check("admin", Permission.KILL))
        self.check("rbac_viewer_no_kill", not rbac.check("viewer", Permission.KILL))

        econ = EconomicEngine()
        econ.record_cost("test", 0.05, "a1")
        self.check("economic_predict_cost", 0.04 <= econ.predict_cost("test") <= 0.06)

    async def run_bridges(self):
        print("\n[BRIDGE TESTS]")

        # Bridge instantiation (no network calls)
        agency = AgencyBridge(host="http://localhost", port=8100)
        self.check("agency_bridge_url", agency.base_url == "http://localhost:8100")

        friday = FridayBridge(host="http://localhost", port=8000)
        self.check("friday_bridge_url", friday.base_url == "http://localhost:8000")

        goose = GooseBridge(host="http://localhost", port=8001)
        self.check("goose_bridge_url", goose.base_url == "http://localhost:8001")

        fixfizx = FixfizxBridge(host="http://localhost", port=8002)
        self.check("fixfizx_bridge_url", fixfizx.base_url == "http://localhost:8002")

        molt = MoltBridge(base_url="https://moltbot-sandbox.sahiixx.workers.dev")
        self.check("molt_bridge_url", "moltbot-sandbox" in molt.base_url)

    async def run_router(self):
        print("\n[ROUTER TESTS]")

        router = A2ARouter()
        agency = AgencyBridge()
        friday = FridayBridge()

        router.register("agency", agency, priority=10)
        router.register("friday", friday, priority=5)
        self.check("router_registered_services", len(router.services) == 2)
        self.check("router_report_services", "agency" in router.report()["services"])

        # Agent matching
        entry = AgentEntry("test", "agent_1", ["search", "lead", "dubai"], "http://localhost:8100", "agency")
        self.check("agent_matches_skill", entry.matches_skill("search"))
        self.check("agent_matches_skills_any", entry.matches_skills(["python", "lead"]))
        self.check("agent_no_match", not entry.matches_skill("rust"))

    async def run_gateway(self):
        print("\n[GATEWAY TESTS]")

        gateway = MCPGateway()
        tools = gateway.list_tools()
        self.check("gateway_has_tools", len(tools) > 0)
        self.check("gateway_agency_mission", "agency.mission" in tools)
        self.check("gateway_friday_chat", "friday.chat" in tools)
        self.check("gateway_goose_chat", "goose.chat" in tools)
        self.check("gateway_fixfizx_chat", "fixfizx.chat" in tools)
        self.check("gateway_molt_send", "molt.send_message" in tools)

        # Schema
        schema = gateway.schema("agency.mission")
        self.check("gateway_schema", "description" in schema)

        # Safety scan blocks dangerous tool calls
        result = await gateway.handle({"tool": "agency.mission", "params": {"description": "rm -rf /"}})
        self.check("gateway_safety_blocks_dangerous", result.get("error") == "blocked_by_safety")

        # Unknown tool
        result = await gateway.handle({"tool": "nonexistent.tool", "params": {}})
        self.check("gateway_unknown_tool", result.get("error") == "unknown_tool")

    async def run_all(self):
        await self.run_unit()
        await self.run_bridges()
        await self.run_router()
        await self.run_gateway()
        print(f"\n{'='*50}")
        print(f"TOTAL: {self.passed} passed, {self.failed} failed")
        return self.failed == 0


if __name__ == "__main__":
    runner = TestRunner()
    ok = asyncio.run(runner.run_all())
    sys.exit(0 if ok else 1)