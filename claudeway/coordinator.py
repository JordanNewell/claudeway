"""
Claudeway Coordinator - Hierarchical task decomposition.

A "manager" agent breaks a complex task into sub-tasks, assigns each to the
right specialist, and executes them in dependency order — running independent
sub-tasks in parallel. Then it synthesizes a final answer from the parts.

This is real decomposition: the coordinator's JSON plan is parsed and honored,
not replaced with 3 hardcoded subtasks.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from typing import Any

from .agent import Agent, AgentConfig
from .swarm import Swarm, Task


@dataclass
class SubTask:
    """A sub-task created by decomposition."""
    id: str
    parent_task: str
    description: str
    assigned_to: str | None = None  # Which specialist handles this
    specialist_role: str | None = None  # The role the coordinator asked for
    dependencies: list[str] = field(default_factory=list)
    status: str = "pending"
    result: Any = None


class CoordinatorConfig(AgentConfig):
    """Configuration for a coordinator agent."""
    def __init__(
        self,
        name: str = "Coordinator",
        role: str = "Task Coordinator and Manager",
        instructions: str = """You are a Task Coordinator responsible for:

1. Breaking down complex tasks into manageable sub-tasks
2. Identifying which specialist agents should handle each sub-task
3. Managing dependencies between sub-tasks
4. Synthesizing sub-task results into a final answer

When given a task, analyze it and create a structured plan with sub-tasks.
Be specific about what each sub-task requires and who should handle it.""",
        model: str = "claude-3-5-sonnet-20241022",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ):
        super().__init__(name, role, instructions, model, temperature, max_tokens)


class Coordinator:
    """
    Hierarchical coordinator - manages specialist agents.

    Unlike the swarm (peer-to-peer consensus), this is hierarchical: one
    coordinator plans and delegates, specialists execute parts.
    """

    def __init__(self, config: CoordinatorConfig, api_key: str | None = None) -> None:
        self.config = config
        self.api_key = api_key
        self.agent = Agent(config, api_key)
        self.sub_agents: dict[str, Agent] = {}
        self.sub_swarms: dict[str, Swarm] = {}

    def add_sub_agent(self, agent_id: str, agent: Agent) -> None:
        """Add a specialist agent that this coordinator can delegate to."""
        self.sub_agents[agent_id] = agent

    def add_sub_swarm(self, swarm_id: str, swarm: Swarm) -> None:
        """Add a sub-swarm that this coordinator can delegate to."""
        self.sub_swarms[swarm_id] = swarm

    async def coordinate(self, task: Task) -> Task:
        """
        Coordinate a complex task by breaking it into sub-tasks.

        1. Decompose the task (real JSON parse).
        2. Assign sub-tasks to specialists.
        3. Execute respecting dependencies (parallel where independent).
        4. Synthesize a final answer.
        """
        sub_tasks = await self._decompose_task(task)
        await self._assign_sub_tasks(sub_tasks)
        results = await self._execute_sub_tasks(sub_tasks)
        final_result = await self._synthesize_results(task, results, sub_tasks)

        task.result = final_result
        task.status = "completed"
        return task

    async def _decompose_task(self, task: Task) -> list[SubTask]:
        """Use the coordinator agent to produce and parse a real plan."""
        available = self._available_specialists()
        decomposition_prompt = f"""Analyze this task and break it down into 2-5 sub-tasks.

Task: {task.description}
Input Data: {task.input_data}

Available specialists: {available}

For each sub-task, provide a clear description, which specialist role should handle it,
and dependencies on other sub-tasks (by id).

Respond with ONLY this JSON (no prose before or after):
{{
  "sub_tasks": [
    {{"id": "1", "description": "...", "specialist": "<name or role>", "dependencies": []}},
    {{"id": "2", "description": "...", "specialist": "<name or role>", "dependencies": ["1"]}}
  ]
}}"""

        response = await self.agent.think(decomposition_prompt)
        return self._parse_plan(response, task.id)

    def _available_specialists(self) -> str:
        """Describe the specialists the coordinator can delegate to."""
        names = list(self.sub_agents.keys())
        if not names:
            return "(none — you will handle all sub-tasks yourself)"
        return ", ".join(names)

    @staticmethod
    def _parse_plan(raw: str, parent_id: str) -> list[SubTask]:
        """
        Parse the coordinator's JSON plan robustly.

        Tolerates surrounding prose and code fences. Falls back to a single
        whole-task sub-task if parsing fails entirely, so a bad plan never
        crashes the run — it just degenerates to "do the whole thing."
        """
        plan = _extract_json_object(raw)
        if plan is None:
            return [
                SubTask(
                    id="1",
                    parent_task=parent_id,
                    description="(coordinator plan unparseable — execute the whole task)",
                )
            ]

        items = plan.get("sub_tasks", []) if isinstance(plan, dict) else []
        sub_tasks: list[SubTask] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            sid = str(item.get("id", len(sub_tasks) + 1))
            deps = item.get("dependencies", []) or []
            if isinstance(deps, str):
                deps = [deps]
            sub_tasks.append(
                SubTask(
                    id=sid,
                    parent_task=parent_id,
                    description=str(item.get("description", "")).strip(),
                    specialist_role=str(item.get("specialist", "")).strip() or None,
                    dependencies=[str(d) for d in deps],
                )
            )

        if not sub_tasks:
            sub_tasks.append(
                SubTask(
                    id="1",
                    parent_task=parent_id,
                    description="(empty plan — execute the whole task)",
                )
            )
        return sub_tasks

    async def _assign_sub_tasks(self, sub_tasks: list[SubTask]) -> None:
        """Assign each sub-task to the best-matching available specialist."""
        for sub_task in sub_tasks:
            sub_task.assigned_to = self._pick_specialist(sub_task)

    def _pick_specialist(self, sub_task: SubTask) -> str | None:
        """
        Match a sub-task to a specialist.

        Prefers an exact name/role match; falls back to the first available
        specialist; finally None (coordinator handles it itself).
        """
        if not self.sub_agents:
            return None
        wanted = (sub_task.specialist_role or "").lower()
        # Exact id match.
        for name in self.sub_agents:
            if name.lower() == wanted:
                return name
        # Role-substring match.
        for name, agent in self.sub_agents.items():
            if wanted and wanted in agent.config.role.lower():
                return name
            if wanted and wanted in name.lower():
                return name
        # Fallback: first available specialist. Only the coordinator's own
        # sub-task (no role hint at all) returns None.
        if not wanted:
            return None
        return next(iter(self.sub_agents))

    async def _execute_sub_tasks(
        self, sub_tasks: list[SubTask]
    ) -> dict[str, Any]:
        """
        Execute sub-tasks respecting dependencies.

        Independent sub-tasks run in parallel; dependent ones wait. Cycles are
        impossible from a DAG, but we guard against re-entry defensively.
        """
        results: dict[str, Any] = {}
        by_id = {st.id: st for st in sub_tasks}
        done: set[str] = set()

        # A dependency on a non-existent id is an error, not silently ignored.
        # (The coordinator asked for it; pretending it's satisfied would let
        # agents produce incoherent work.)
        for st in sub_tasks:
            missing = [d for d in st.dependencies if d not in by_id]
            if missing:
                results[st.id] = {"error": f"unknown dependency: {missing}"}
                st.status = "failed"
                done.add(st.id)

        while len(done) < len(sub_tasks):
            # Find sub-tasks whose dependencies are all satisfied.
            ready = [
                st for st in sub_tasks
                if st.id not in done
                and all(dep in done for dep in st.dependencies if dep in by_id)
            ]
            if not ready:
                # Dependency on something unschedulable — mark stuck ones done
                # with an error so we make progress rather than hang.
                stuck = [st for st in sub_tasks if st.id not in done]
                for st in stuck:
                    results[st.id] = {"error": "unresolvable dependency"}
                    st.status = "failed"
                    done.add(st.id)
                break

            batch = await asyncio.gather(
                *(self._run_one(st, results) for st in ready),
                return_exceptions=True,
            )
            for st, outcome in zip(ready, batch):
                if isinstance(outcome, Exception):
                    results[st.id] = {"error": str(outcome)}
                    st.status = "failed"
                else:
                    results[st.id] = outcome
                    st.status = "completed"
                    st.result = outcome
                done.add(st.id)

        return results

    async def _run_one(
        self, sub_task: SubTask, prior_results: dict[str, Any]
    ) -> Any:
        """Execute a single sub-task, injecting dependency results into context."""
        agent = (
            self.sub_agents[sub_task.assigned_to]
            if sub_task.assigned_to in self.sub_agents
            else self.agent
        )
        context = self._build_dependency_context(sub_task, prior_results)
        prompt = sub_task.description
        if context:
            prompt = f"{prompt}\n\nPrior sub-task results you can build on:\n{context}"
        return await agent.think(prompt)

    @staticmethod
    def _build_dependency_context(
        sub_task: SubTask, prior_results: dict[str, Any]
    ) -> str:
        """Render the outputs of this sub-task's dependencies as context."""
        if not sub_task.dependencies:
            return ""
        lines = []
        for dep_id in sub_task.dependencies:
            res = prior_results.get(dep_id)
            if res is not None:
                lines.append(f"[{dep_id}] -> {res}")
        return "\n".join(lines)

    async def _synthesize_results(
        self,
        original_task: Task,
        sub_results: dict[str, Any],
        sub_tasks: list[SubTask],
    ) -> dict[str, Any]:
        """Synthesize all sub-task results into a final answer."""
        parts = "\n\n".join(
            f"Sub-task {st.id} ({st.specialist_role or st.assigned_to or 'coordinator'}):\n"
            f"{sub_results.get(st.id)}"
            for st in sub_tasks
        )
        synthesis_prompt = f"""Synthesize these sub-task results into a comprehensive final answer.

Original Task: {original_task.description}

Sub-task Results:
{parts}

Provide a cohesive final response that addresses the original task."""

        response = await self.agent.think(synthesis_prompt)
        return {
            "final_answer": response,
            "sub_task_count": len(sub_tasks),
            "sub_tasks": [
                {
                    "id": st.id,
                    "description": st.description,
                    "assigned_to": st.assigned_to,
                    "status": st.status,
                }
                for st in sub_tasks
            ],
            "synthesis_method": "coordinator",
        }


# --- Helpers -----------------------------------------------------------------


def _extract_json_object(text: str) -> dict | None:
    """
    Pull the first JSON object out of a model response.

    Handles raw JSON, ```json fenced blocks, and JSON embedded in prose.
    Returns None if nothing parseable is found.
    """
    # Strip code fences if present.
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        candidate = fence_match.group(1)
        try:
            parsed = json.loads(candidate)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            pass

    # Find the first balanced {...} block.
    start = text.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        parsed = json.loads(text[start : i + 1])
                        return parsed if isinstance(parsed, dict) else None
                    except json.JSONDecodeError:
                        break
        start = text.find("{", start + 1)

    return None
