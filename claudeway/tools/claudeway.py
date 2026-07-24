"""
Claudeway Tool - Allows Claude agents to deploy and manage swarms

This tool enables meta-cognition: Claude can decide when to spawn
specialized sub-agents for parallel processing.
"""

from typing import Any

from .base import Tool


class ClaudewayTool(Tool):
    """
    Tool that allows Claude agents to deploy and manage agent swarms.

    This enables Claude to become a swarm manager - it can recognize
    when a task would benefit from multiple specialized agents and
    deploy them automatically.
    """

    name = "claudeway"
    description = """Deploy PERSISTENT agent swarms that can be reused across multiple tasks.

IMPORTANT: Use this ONLY when you need:
- Persistent specialist teams that will be used repeatedly
- Long-running agent processes with memory
- Swarm management (start, stop, monitor separate agents)
- Task decomposition that benefits from dedicated, maintained specialist roles

DO NOT use this for:
- Simple parallel processing within one task → Use your native parallel capability instead
- One-off concurrent operations → Use your native parallel capability instead
- Temporary helper instances → Use your native parallel capability instead

The key distinction: This creates MANAGED, PERSISTENT swarms. Your native
parallel capability creates TEMPORARY instances for immediate use.

Actions:
- deploy_swarm: Create a new swarm with specialized agents (persists until explicitly stopped)
- submit_task: Send a task to an existing swarm
- get_status: Check swarm status and results
- list_swarms: List all active swarms
"""

    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["deploy_swarm", "submit_task", "get_status", "list_swarms"],
                "description": "The action to perform",
            },
            "swarm_name": {
                "type": "string",
                "description": "Name for the swarm (for deploy_swarm)",
            },
            "agents": {
                "type": "array",
                "description": "List of agents to deploy (for deploy_swarm)",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Agent name"},
                        "role": {"type": "string", "description": "Agent's role/specialty"},
                        "instructions": {
                            "type": "string",
                            "description": "Specific instructions for this agent",
                        },
                    },
                    "required": ["name", "role", "instructions"],
                },
            },
            "swarm_id": {
                "type": "string",
                "description": "Swarm ID (for submit_task, get_status)",
            },
            "task": {
                "type": "string",
                "description": "Task description (for submit_task)",
            },
        },
    }

    def __init__(self, runtime):
        """Initialize with reference to the runtime."""
        self.runtime = runtime

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute a Claudeway action."""
        action = kwargs.get("action")

        if action == "deploy_swarm":
            return await self._deploy_swarm(
                kwargs.get("swarm_name"),
                kwargs.get("agents", [])
            )
        elif action == "submit_task":
            return await self._submit_task(
                kwargs.get("swarm_id"),
                kwargs.get("task")
            )
        elif action == "get_status":
            return await self._get_status(kwargs.get("swarm_id"))
        elif action == "list_swarms":
            return await self._list_swarms()
        else:
            return {"error": f"Unknown action: {action}"}

    async def _deploy_swarm(self, name: str, agents: list) -> dict:
        """Deploy a new swarm with the specified agents."""
        from claudeway.swarm import SwarmConfig

        # Create agent configs
        agent_configs = []
        for agent_def in agents:
            from claudeway.agent import AgentConfig
            agent_configs.append(AgentConfig(
                name=agent_def["name"],
                role=agent_def["role"],
                instructions=agent_def["instructions"]
            ))

        # Create swarm config
        swarm_config = SwarmConfig(
            name=name,
            agents=agent_configs
        )

        # Deploy swarm
        swarm_id = self.runtime.create_swarm(swarm_config)

        return {
            "success": True,
            "swarm_id": swarm_id,
            "name": name,
            "agent_count": len(agent_configs),
            "message": f"Deployed swarm '{name}' with {len(agent_configs)} agents"
        }

    async def _submit_task(self, swarm_id: str, task: str) -> dict:
        """Submit a task to a swarm."""
        from claudeway.swarm import Task

        task_obj = Task(description=task)

        try:
            result = await self.runtime.submit_task(swarm_id, task_obj)
            return {
                "success": True,
                "swarm_id": swarm_id,
                "result": result
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    async def _get_status(self, swarm_id: str) -> dict:
        """Get status of a swarm."""
        status = self.runtime.get_status()

        if swarm_id in status.get("swarms", {}):
            return {
                "success": True,
                "swarm_id": swarm_id,
                "status": status["swarms"][swarm_id]
            }
        else:
            return {
                "success": False,
                "error": f"Swarm {swarm_id} not found"
            }

    async def _list_swarms(self) -> dict:
        """List all active swarms."""
        status = self.runtime.get_status()

        return {
            "success": True,
            "swarm_count": status.get("swarm_count", 0),
            "agent_count": status.get("agent_count", 0),
            "swarms": status.get("agents", {})
        }


def create_claudeway_tool(runtime) -> ClaudewayTool:
    """Factory function to create a Claudeway tool."""
    return ClaudewayTool(runtime)
