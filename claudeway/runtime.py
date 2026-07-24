"""
Claudeway Runtime - Manages long-running agent processes.

Spawns, monitors, and restarts agents as needed.
Clean process supervision without over-engineering.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from .agent import Agent, AgentConfig
from .swarm import Swarm, SwarmConfig, Task


class AgentStatus(Enum):
    """Status of an agent process."""
    STARTING = "starting"
    RUNNING = "running"
    IDLE = "idle"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class AgentProcess:
    """A running agent process."""
    id: str
    agent: Agent
    status: AgentStatus = AgentStatus.STARTING
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_activity: datetime = field(default_factory=datetime.utcnow)
    task_queue: asyncio.Queue[Task] = field(default_factory=asyncio.Queue)
    process_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the agent process loop."""
        self.status = AgentStatus.RUNNING
        self.process_task = asyncio.create_task(self._process_loop())

    async def _process_loop(self) -> None:
        """Main processing loop - handles tasks from queue."""
        while self.status in (AgentStatus.RUNNING, AgentStatus.IDLE):
            try:
                # Wait for a task (with timeout to allow checking status)
                task = await asyncio.wait_for(
                    self.task_queue.get(),
                    timeout=1.0
                )

                # Process the task
                await self._handle_task(task)

                self.last_activity = datetime.utcnow()

            except TimeoutError:
                # No task, continue loop
                continue
            except Exception as e:
                print(f"Agent {self.id} error: {e}")
                self.status = AgentStatus.ERROR
                break

    async def _handle_task(self, task: Task) -> None:
        """Handle a single task."""
        try:
            # Get agent's response
            response = await self.agent.think(task.description)

            # Update task with result
            task.result = {
                "agent_id": self.id,
                "response": response,
                "completed_at": datetime.utcnow().isoformat(),
            }
            task.status = "completed"

        except Exception as e:
            task.result = {"error": str(e)}
            task.status = "failed"

    async def stop(self) -> None:
        """Stop the agent process."""
        self.status = AgentStatus.STOPPED
        if self.process_task:
            self.process_task.cancel()
            try:
                await self.process_task
            except asyncio.CancelledError:
                pass

    def enqueue_task(self, task: Task) -> None:
        """Add a task to this agent's queue."""
        self.task_queue.put_nowait(task)


class Runtime:
    """
    Claudeway Runtime - manages agent processes.

    Responsibilities:
    - Spawn and manage agent processes
    - Route tasks to appropriate agents
    - Monitor health and restart failed agents
    """

    def __init__(self) -> None:
        self.agents: dict[str, AgentProcess] = {}
        self.swarms: dict[str, Swarm] = {}
        self.running = False

    async def start(self) -> None:
        """Start the runtime."""
        self.running = True
        print("Claudeway Runtime started")

    async def stop(self) -> None:
        """Stop the runtime and all agents."""
        self.running = False

        # Stop all agents
        for agent_process in self.agents.values():
            await agent_process.stop()

        print("Claudeway Runtime stopped")

    def spawn_agent(self, config: AgentConfig, agent_id: str | None = None) -> str:
        """
        Spawn a new agent process.

        Returns the agent ID.
        """
        if agent_id is None:
            agent_id = f"{config.name.lower().replace(' ', '-')}-{datetime.utcnow().timestamp()}"

        # Create agent
        agent = Agent(config)

        # Create agent process
        agent_process = AgentProcess(id=agent_id, agent=agent)

        # Store and start
        self.agents[agent_id] = agent_process
        asyncio.create_task(agent_process.start())

        return agent_id

    def create_swarm(self, config: SwarmConfig, swarm_id: str | None = None) -> str:
        """
        Create a new swarm from configuration.

        Returns the swarm ID.
        """
        if swarm_id is None:
            swarm_id = f"{config.name.lower().replace(' ', '-')}-{datetime.utcnow().timestamp()}"

        # Create swarm
        swarm = Swarm(config)
        self.swarms[swarm_id] = swarm

        return swarm_id

    async def submit_task(self, swarm_id: str, task: Task) -> Task:
        """
        Submit a task to a swarm for processing.

        Returns the completed task with results.
        """
        if swarm_id not in self.swarms:
            raise ValueError(f"Swarm {swarm_id} not found")

        swarm = self.swarms[swarm_id]
        return await swarm.process(task)

    def get_status(self) -> dict[str, Any]:
        """Get runtime status."""
        return {
            "running": self.running,
            "agent_count": len(self.agents),
            "swarm_count": len(self.swarms),
            "agents": {
                agent_id: {
                    "status": proc.status.value,
                    "role": proc.agent.config.role,
                    "queue_size": proc.task_queue.qsize(),
                }
                for agent_id, proc in self.agents.items()
            },
        }
