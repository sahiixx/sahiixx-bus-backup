"""SAHIIXX Bus — Unified orchestration layer for the SAHIIXX ecosystem.

Provides:
- Core primitives (SwarmBus, SwarmMemory, SafetyCouncil, RBACGuard, etc.)
- Bridge clients for all ecosystem services
- A2A router for unified agent discovery and task routing
- MCP gateway for unified tool access
"""

# Core primitives — re-exported from sovereign-swarm v1.4 (hardened)
from sovereign_swarm import (
    SwarmBus,
    SwarmMemory,
    LLMClient,
    Qwen3Router,
    SafetyCouncil,
    ToolSchema,
    HITLStatus,
    HITLCheckpoint,
    HITLCouncil,
    EconomicEngine,
    BudgetController,
    EvolutionEngine,
    AgentProfile,
    MetaOrchestrator,
    ReputationEngine,
    HealEngine,
    HealStrategy,
    RBACGuard,
    RBACPermission,
    ClusterNode,
    ClusterManager,
    MCPServer,
    A2ACardServer,
    HermesMessenger,
    SwarmBridge,
    OpenClawGateway,
    ObservabilityLayer,
    AlertDispatcher,
    AuditTrail,
    BackupManager,
    StateManager,
)

from sahiixx_bus.bridge import (
    AgencyBridge,
    FridayBridge,
    GooseBridge,
    FixfizxBridge,
    MoltBridge,
)
from sahiixx_bus.a2a_router import A2ARouter
from sahiixx_bus.mcp_gateway import MCPGateway

__all__ = [
    # Core
    "SwarmBus", "SwarmMemory", "LLMClient", "Qwen3Router",
    "SafetyCouncil", "ToolSchema", "HITLStatus", "HITLCheckpoint", "HITLCouncil",
    "EconomicEngine", "BudgetController",
    "EvolutionEngine",
    "AgentProfile", "MetaOrchestrator", "ReputationEngine", "HealEngine", "HealStrategy",
    "RBACGuard", "RBACPermission", "ClusterNode", "ClusterManager",
    "MCPServer", "A2ACardServer", "HermesMessenger", "SwarmBridge", "OpenClawGateway",
    "ObservabilityLayer", "AlertDispatcher", "AuditTrail", "BackupManager", "StateManager",
    # Bridges
    "AgencyBridge", "FridayBridge", "GooseBridge", "FixfizxBridge", "MoltBridge",
    # Router + Gateway
    "A2ARouter", "MCPGateway",
]