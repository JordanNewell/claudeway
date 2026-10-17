"""Swarm Deployment module.

This module tracks deployed swarms in the platform database.
The actual agent intelligence is in core/agent.py.
"""

# New clear naming
# Backwards compatibility (deprecated)
from agents.deployment import Agent, AgentStatus, DeploymentStatus, SwarmDeployment
from agents.router import router

__all__ = [
    # New names
    "SwarmDeployment",
    "DeploymentStatus",
    "router",
    # Old names (deprecated, use SwarmDeployment instead)
    "Agent",
    "AgentStatus",
]
