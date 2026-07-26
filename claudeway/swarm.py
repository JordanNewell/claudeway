"""
Claudeway Swarm - Multi-agent coordination with real consensus.

This is the differentiator. A swarm isn't "N agents that all answer and we
pick the first" — it's N agents whose answers are aggregated through a
pluggable ConsensusStrategy (WeightedVote by default, Debate for hard cases),
with disagreement surfaced explicitly rather than papered over.

Agents run concurrently: a 3-agent swarm issues all 3 Claude calls in parallel
via asyncio.gather, not serially.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .agent import Agent, AgentConfig
from .consensus import (
    ConsensusStrategy,
    WeightedVote,
    parse_structured_output,
)


@dataclass
class SwarmConfig:
    """Configuration for a swarm of agents."""

    name: str
    description: str
    agents: list[AgentConfig] = field(default_factory=list)
    topology: str = "hierarchical_mesh"  # How agents connect
    consensus_method: str = "weighted_vote"  # Back-compat hint; overridden by strategy
    max_task_tokens: int = 100_000  # Safety cap across consensus rounds


@dataclass
class Task:
    """A task for the swarm to work on."""
    id: str
    description: str
    input_data: dict[str, Any]
    status: str = "pending"
    result: Any = None
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class AgentResponse:
    """A response from an agent in the swarm."""
    agent_name: str
    answer: str = ""  # Parsed substantive answer
    content: str = ""  # Raw output from the agent (may equal answer)
    confidence: float = 0.5
    reasoning: str = ""
    round: int = 1
    timestamp: datetime = field(default_factory=datetime.utcnow)


# Prompt suffix instructing the agent to emit the structured output contract.
#
# Two constraints that prior phrasings got wrong:
#   1. <answer> must carry the FULL response (multi-paragraph analysis), not
#      a one-word verdict. The consensus strategy reads <answer>; reasoning
#      is just a one-line summary label.
#   2. The structured block IS the response — no prose preamble. Small
#      models with tight max_tokens will write prose first, open <answer>,
#      then truncate before </answer>. The parser is tolerant of that
#      (parse_structured_output falls back to "everything after <answer>"),
#      but it's still wasteful. Emit the tags FIRST.
_OUTPUT_CONTRACT = """

Respond ONLY with this structured block — no prose before or after it.
The <answer> tag opens immediately, contains your full multi-paragraph
analysis, then closes. Do NOT put a one-word verdict in <answer>; that
loses your analysis. The <reasoning> tag is a one-line summary label
for indexing, NOT a place to write your justification.

<answer>
[Your complete response: multiple paragraphs of analysis, consideration
of alternatives, and your final recommendation with justification. This
is what the consensus strategy and downstream readers will see.]
</answer>
<confidence>a number between 0.0 and 1.0 reflecting how sure you are</confidence>
<reasoning>one short sentence summarizing your core argument</reasoning>"""


class Swarm:
    """
    A swarm of Claude agents working together.

    Coordinates:
    - Concurrent response collection (asyncio.gather)
    - Pluggable consensus (see core.consensus)
    - Multi-round debate when agents disagree
    """

    def __init__(
        self,
        config: SwarmConfig,
        api_key: str | None = None,
        consensus: ConsensusStrategy | None = None,
    ) -> None:
        self.config = config
        self.api_key = api_key
        self.agents: dict[str, Agent] = {}
        self.task_history: list[Task] = []
        # If a strategy isn't injected, honor the config hint for back-compat.
        self.consensus = consensus or _strategy_from_name(config.consensus_method)
        self._initialize_agents()

    def _initialize_agents(self) -> None:
        """Create agent instances from configs."""
        for agent_config in self.config.agents:
            self.agents[agent_config.name] = Agent(agent_config, self.api_key)

    async def process(self, task: Task) -> Task:
        """
        Process a task through the swarm.

        1. Collect responses from all agents concurrently.
        2. Run consensus to determine the final answer.
        """
        task.status = "processing"
        self.task_history.append(task)

        responses = await self._collect_agent_responses(task)
        result = await self.consensus.resolve(responses, self)

        task.result = result.to_dict()
        task.status = "completed"
        return task

    async def _collect_agent_responses(self, task: Task) -> list[AgentResponse]:
        """Collect responses from all agents in parallel."""
        coros = [
            self._query_agent(name, task, round_num=1)
            for name in self.agents
        ]
        results = await asyncio.gather(*coros, return_exceptions=True)

        responses: list[AgentResponse] = []
        for name, result in zip(self.agents, results):
            if isinstance(result, Exception):
                print(f"Agent {name} failed: {result}")
                continue
            responses.append(result)
        return responses

    async def _collect_revision_round(
        self, prior: list[AgentResponse]
    ) -> list[AgentResponse]:
        """
        Second debate round: each agent sees peer answers and revises.

        Called by the Debate strategy. Agents whose originals failed are
        skipped to avoid stalling the round.
        """
        peer_summary = "\n\n".join(
            f"{r.agent_name} (confidence {r.confidence:.2f}): {r.answer}"
            for r in prior
        )

        async def revise(name: str, agent: Agent) -> AgentResponse:
            prompt = (
                f"Other specialists proposed the following:\n{peer_summary}\n\n"
                f"Reconsider in light of their answers. You may revise. If they "
                f"missed something, say so; if they're right, say so and raise "
                f"your confidence.{_OUTPUT_CONTRACT}"
            )
            try:
                return await self._query_agent(
                    name, _RevisionTask(prompt), round_num=2
                )
            except Exception as e:
                print(f"Agent {name} revision failed: {e}")
                # Fall back to this agent's prior response.
                for r in prior:
                    if r.agent_name == name:
                        return r
                raise

        coros = [revise(name, agent) for name, agent in self.agents.items()]
        results = await asyncio.gather(*coros, return_exceptions=True)
        return [r for r in results if isinstance(r, AgentResponse)]

    async def _query_agent(
        self, agent_name: str, task: Task, round_num: int
    ) -> AgentResponse:
        """Query one agent and parse its structured output."""
        agent = self.agents[agent_name]
        prompt = self._craft_agent_input(task, agent_name)
        raw = await agent.think(prompt)
        parsed = parse_structured_output(raw)
        return AgentResponse(
            agent_name=agent_name,
            content=raw,
            answer=parsed.answer,
            confidence=parsed.confidence,
            reasoning=parsed.reasoning,
            round=round_num,
        )

    def _craft_agent_input(self, task: Task, agent_name: str) -> str:
        """Craft the input message for a specific agent."""
        role = self.agents[agent_name].config.role
        return f"""Task: {task.description}

Input data: {task.input_data}

Your role: {role}

Provide a thorough analysis from your role's perspective — multiple
paragraphs, weighing tradeoffs, ending with your final recommendation
and the reasoning behind it. Emit the structured block as your entire
response (no preamble); the <answer> block contains that analysis.{_OUTPUT_CONTRACT}"""

    def get_state(self) -> dict[str, Any]:
        """Get swarm state for inspection."""
        return {
            "name": self.config.name,
            "description": self.config.description,
            "agent_count": len(self.agents),
            "topology": self.config.topology,
            "consensus_method": self.consensus.name,
            "tasks_completed": len([t for t in self.task_history if t.status == "completed"]),
            "agent_states": {name: agent.get_state() for name, agent in self.agents.items()},
        }


# --- Helpers -----------------------------------------------------------------


def _strategy_from_name(name: str) -> ConsensusStrategy:
    """Resolve a consensus strategy from the legacy config string."""
    name = (name or "").lower().replace("-", "_")
    if name in ("debate", "revise"):
        from .consensus import Debate
        return Debate()
    # Default and unknown → WeightedVote.
    return WeightedVote()


@dataclass
class _RevisionTask:
    """Adapter so the revision prompt can reuse _query_agent's Task path."""
    description: str
    input_data: dict = field(default_factory=dict)
