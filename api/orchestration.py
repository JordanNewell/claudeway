"""
Claudeway Orchestration Service

Bridges the API layer to the core orchestration engine.
"""

from typing import Any
from datetime import datetime
from uuid import uuid4

from claudeway.agent import Agent, AgentConfig
from claudeway.coordinator import Coordinator, CoordinatorConfig
from claudeway.swarm import Swarm, SwarmConfig, Task
from api.state import get_runtime


class OrchestrationService:
    """
    Service for managing agents and swarms via the core Runtime.

    This replaces the Claude-Flow gateway with our working core.
    """

    def __init__(self):
        self.runtime = get_runtime()

    async def create_swarm(
        self,
        name: str,
        description: str,
        agents: list[dict],
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a new swarm from agent configurations."""
        # Convert agent configs to AgentConfig objects
        agent_configs = []
        for agent_dict in agents:
            config = AgentConfig(
                name=agent_dict["name"],
                role=agent_dict["role"],
                instructions=agent_dict["instructions"],
                model=agent_dict.get("model", "claude-3-5-sonnet-20241022"),
                temperature=agent_dict.get("temperature", 0.7),
                max_tokens=agent_dict.get("max_tokens", 4096),
            )
            agent_configs.append(config)

        # Create swarm config
        swarm_config = SwarmConfig(
            name=name,
            description=description,
            agents=agent_configs,
            topology="hierarchical_mesh",
            consensus_method="weighted_vote",
        )

        # Create swarm via runtime
        swarm_id = self.runtime.create_swarm(swarm_config)

        return {
            "id": swarm_id,
            "name": name,
            "description": description,
            "agent_count": len(agent_configs),
            "status": "running",
        }

    async def process_task(
        self,
        swarm_id: str,
        task_description: str,
        task_data: dict[str, Any],
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        """Submit a task to a swarm for processing."""
        # Create task
        task = Task(
            id=str(uuid4()),
            description=task_description,
            input_data=task_data,
            status="pending",
        )

        # Process via runtime
        completed_task = await self.runtime.submit_task(swarm_id, task)

        return {
            "task_id": task.id,
            "swarm_id": swarm_id,
            "status": completed_task.status,
            "result": completed_task.result,
        }

    async def list_agents(
        self,
        tenant_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """List all agents across all swarms."""
        agents = []

        for swarm_id, swarm in self.runtime.swarms.items():
            for agent_name, agent in swarm.agents.items():
                agent_state = agent.get_state()

                # Add swarm context
                agent_state["swarm_id"] = swarm_id
                agent_state["swarm_name"] = swarm.config.name

                agents.append(agent_state)

        return agents[offset : offset + limit]

    async def create_coordinator(
        self,
        name: str,
        specialists: list[dict],
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a coordinator with specialist agents."""
        # Create coordinator config
        coord_config = CoordinatorConfig(
            name=name,
            role="Task Coordinator",
            instructions="You coordinate specialist agents to complete complex tasks.",
        )

        # Create coordinator
        from claudeway.coordinator import Coordinator
        coordinator = Coordinator(coord_config)

        # Add specialists
        for spec in specialists:
            agent_config = AgentConfig(
                name=spec["name"],
                role=spec["role"],
                instructions=spec["instructions"],
            )
            specialist = Agent(agent_config)
            coordinator.add_sub_agent(spec["name"], specialist)

        # Store coordinator in runtime (as a special "coordinator" type)
        coord_id = f"coordinator-{datetime.utcnow().timestamp()}"
        # Note: For now, coordinators are kept in memory
        # TODO: Persist coordinators to runtime

        return {
            "id": coord_id,
            "name": name,
            "specialist_count": len(specialists),
            "status": "ready",
        }

    def get_runtime_status(self) -> dict[str, Any]:
        """Get the current runtime status."""
        return self.runtime.get_status()
