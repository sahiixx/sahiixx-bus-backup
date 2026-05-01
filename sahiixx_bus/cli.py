"""SAHIIXX Bus CLI — Start the orchestration layer, discover agents, dispatch tasks."""
import argparse
import asyncio
import json
import logging
import sys

from .a2a_router import A2ARouter
from .bridge import AgencyBridge, FridayBridge, GooseBridge, FixfizxBridge, MoltBridge
from .mcp_gateway import MCPGateway

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("sahiixx.bus")


async def main():
    parser = argparse.ArgumentParser(description="SAHIIXX Bus — Unified orchestration layer")
    parser.add_argument("--agency-host", default="http://localhost", help="Agency-agents host")
    parser.add_argument("--agency-port", type=int, default=8100, help="Agency-agents A2A port")
    parser.add_argument("--friday-host", default="http://localhost", help="FRIDAY-OS host")
    parser.add_argument("--friday-port", type=int, default=8000, help="FRIDAY-OS port")
    parser.add_argument("--goose-host", default="http://localhost", help="Goose-AIOS host")
    parser.add_argument("--goose-port", type=int, default=8001, help="Goose-AIOS port")
    parser.add_argument("--fixfizx-host", default="http://localhost", help="Fixfizx host")
    parser.add_argument("--fixfizx-port", type=int, default=8002, help="Fixfizx port")
    parser.add_argument("--molt-url", default="https://moltbot-sandbox.sahiixx.workers.dev", help="Moltworker URL")
    parser.add_argument("--discover", action="store_true", help="Discover all agents and exit")
    parser.add_argument("--task", type=str, help="Dispatch a task to the best available agent")
    parser.add_argument("--skills", type=str, nargs="+", help="Required skills for task routing")
    parser.add_argument("--service", type=str, help="Preferred service for task routing")
    parser.add_argument("--health", action="store_true", help="Check health of all services")
    parser.add_argument("--tools", action="store_true", help="List all available MCP tools")
    args = parser.parse_args()

    router = A2ARouter()

    # Register bridges
    agency = AgencyBridge(host=args.agency_host, port=args.agency_port)
    friday = FridayBridge(host=args.friday_host, port=args.friday_port)
    goose = GooseBridge(host=args.goose_host, port=args.goose_port)
    fixfizx = FixfizxBridge(host=args.fixfizx_host, port=args.fixfizx_port)
    molt = MoltBridge(base_url=args.molt_url)

    router.register("agency", agency, priority=10)
    router.register("friday", friday, priority=5)
    router.register("goose", goose, priority=3)
    router.register("fixfizx", fixfizx, priority=7)
    router.register("molt", molt, priority=1)

    gateway = MCPGateway()
    gateway.register_bridge("agency", agency)
    gateway.register_bridge("friday", friday)
    gateway.register_bridge("goose", goose)
    gateway.register_bridge("fixfizx", fixfizx)
    gateway.register_bridge("molt", molt)

    if args.discover:
        agents = await router.discover()
        print(f"\nDiscovered {len(agents)} agents:")
        for a in agents:
            print(f"  {a.agent_id} ({a.service_name}) — skills: {a.skills}")
        return

    if args.health:
        health = await router.health_check()
        print("\nService Health:")
        for name, status in health.items():
            print(f"  {name}: {json.dumps(status, indent=2)}")
        return

    if args.tools:
        tools = gateway.list_tools()
        print(f"\n{len(tools)} available tools:")
        for t in tools:
            schema = gateway.schema(t)
            print(f"  {t}: {schema}")
        return

    if args.task:
        results = await router.route(args.task, skills=args.skills, preferred_service=args.service)
        print(f"\nTask: {args.task}")
        print(f"Dispatched to {len(results)} agent(s):")
        for r in results:
            print(f"  {r['agent_id']} ({r['service']}): {json.dumps(r['result'], indent=2)[:200]}")
        return

    # Default: interactive loop
    print("\n🕸️  SAHIIXX Bus v0.1 — Unified Orchestration Layer")
    print("   Commands: discover, health, tools, task <description>, exit\n")

    await router.discover()
    print(f"Discovered {len(router.agents)} agents across {len(router.services)} services.\n")

    while True:
        try:
            line = input("sahiixx> ").strip()
            if not line:
                continue
            parts = line.split()
            cmd = parts[0].lower()

            if cmd in ("exit", "quit"):
                break
            elif cmd == "discover":
                agents = await router.discover()
                for a in agents:
                    print(f"  {a.agent_id} ({a.service_name}) — skills: {a.skills}")
            elif cmd == "health":
                health = await router.health_check()
                for name, status in health.items():
                    print(f"  {name}: {json.dumps(status, indent=2)[:200]}")
            elif cmd == "tools":
                for t in gateway.list_tools():
                    print(f"  {t}")
            elif cmd == "task" and len(parts) > 1:
                task = " ".join(parts[1:])
                results = await router.route(task, skills=args.skills)
                for r in results:
                    print(f"  {r['agent_id']} ({r['service']}): {json.dumps(r['result'], indent=2)[:200]}")
            else:
                print(f"[!] Unknown command: {cmd}. Try: discover, health, tools, task <description>, exit")
        except EOFError:
            break
        except KeyboardInterrupt:
            print()
            break


if __name__ == "__main__":
    asyncio.run(main())