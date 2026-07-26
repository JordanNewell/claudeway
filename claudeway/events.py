"""
Streaming consensus events.

The observable surface of a Swarm run. When an `on_event` callback is wired
into a Swarm, these are the events it receives as consensus unfolds — per
agent as each answer lands, then the resolved consensus at the end.

Schema is intentionally minimal: only events that both the MAF and LangGraph
adapters actually emit. Field names mirror the OpenTelemetry GenAI semantic
conventions draft (`gen_ai.agent.*`, `gen_ai.workflow.*`) even though that
spec is still Development as of 2026-07 — so a future OTel exporter adapter
is a flat rename, not a schema rewrite. schema_version on the base lets the
shape evolve without breaking consumers.

Pydantic v2 is already a base claudeway dependency, so this adds nothing.
"""

from typing import Literal

from pydantic import BaseModel, Field


class ConsensusEvent(BaseModel):
    """Base. discriminator: `kind`. All events carry identifying context."""

    schema_version: str = Field(default="1.0")
    swarm_id: str = ""
    task_id: str = ""
    kind: str


class AgentCompleted(ConsensusEvent):
    """One agent finished. Fires inside asyncio.gather as each answer lands.

    The headline streaming event — observers (MAF intermediate_output,
    LangGraph stream_writer, a UI) see per-agent answers + confidence arrive
    in real time, before the consensus is resolved.
    """

    kind: Literal["agent_completed"] = "agent_completed"
    agent: str
    answer: str
    confidence: float
    round: int = 1


class ConsensusResolved(ConsensusEvent):
    """The consensus strategy returned a final result. Fires once per run."""

    kind: Literal["consensus_resolved"] = "consensus_resolved"
    final_answer: str
    method: str
    agreement: float
    rounds: int
    disagreed: bool
