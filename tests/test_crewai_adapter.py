"""
CrewAI adapter tests.

Two layers, matching test_langgraph_adapter.py:

  - Unit tests (default): stub Swarm.process so the adapter is exercised
    through real CrewAI machinery (@tool, Flow, kickoff_async) without
    touching Claude. Fast, hermetic.

  - One integration test: real Swarm + real Claude via the @tool, gated
    on CLAUDEWAY_RUN_LIVE=1. Skips in CI.

crewai is required; `pip install claudeway[crewai]`. Skips cleanly when
absent, matching test_langgraph_adapter.py's langgraph precedent.
"""

import os

import pytest

pytest.importorskip("crewai", reason="pip install claudeway[crewai]")

from claudeway import AgentConfig, Swarm, SwarmConfig  # noqa: E402
from claudeway.adapters.crewai import (  # noqa: E402
    ConsensusFlow,
    reach_consensus,
)
from claudeway.signing import ConsensusReceipt, Ed25519Backend  # noqa: E402
from claudeway.swarm import Task  # noqa: E402

# --- Fixtures ----------------------------------------------------------------

CANNED_RESULT = {
    "final_answer": "use sqlite",
    "method": "weighted_vote",
    "agent_count": 3,
    "agreement": 0.9,
    "rounds": 1,
    "disagreed": False,
    "responses": [
        {"agent": "Dba", "confidence": 0.9, "answer": "use sqlite"},
        {"agent": "Indie", "confidence": 0.85, "answer": "use sqlite"},
        {"agent": "Security", "confidence": 0.8, "answer": "use sqlite"},
    ],
}


class _StubSwarm:
    """Swarm stand-in: captures the task, returns CANNED_RESULT.

    Adapter only calls swarm.process(task) and reads swarm.config.name.
    """

    def __init__(self, name: str = "TestSwarm"):
        self.config = SwarmConfig(name=name, description="", agents=[])
        self.last_task: Task | None = None

    async def process(self, task: Task) -> Task:
        self.last_task = task
        task.result = CANNED_RESULT
        task.status = "completed"
        return task


# --- Tool shape --------------------------------------------------------------


def test_tool_factory_returns_crewai_tool():
    from crewai.tools import BaseTool  # type: ignore

    swarm = _StubSwarm()
    tool = reach_consensus(swarm)
    # @tool returns a BaseTool subclass instance.
    assert isinstance(tool, BaseTool)


def test_tool_run_returns_formatted_string():
    swarm = _StubSwarm()
    tool = reach_consensus(swarm)

    # CrewAI tools are sync; call .run() or invoke directly.
    out = tool.run(question="which db?")
    assert isinstance(out, str)
    assert "use sqlite" in out
    assert "agreement: 90%" in out
    assert "method: weighted_vote" in out
    # No receipt by default.
    assert "signed receipt" not in out


def test_tool_run_with_signing_emits_receipt():
    priv, _ = Ed25519Backend().generate_keypair()
    swarm = _StubSwarm(name="SignTest")
    tool = reach_consensus(swarm, sign=True, signing_key=priv, task_id="t-1")

    out = tool.run(question="sign this")
    assert "signed receipt" in out
    assert "algorithm=ed25519" in out


def test_tool_passes_question_as_task_description():
    swarm = _StubSwarm()
    tool = reach_consensus(swarm)

    tool.run(question="postgres or sqlite?")
    assert swarm.last_task.description == "postgres or sqlite?"


# --- Flow shape --------------------------------------------------------------


@pytest.mark.asyncio
async def test_flow_round_trips():
    swarm = _StubSwarm()
    flow = ConsensusFlow(swarm)

    await flow.kickoff_async(inputs={"question": "which db for a side project?"})

    state = flow.state
    assert state.final_answer == "use sqlite"
    assert state.agreement == 0.9
    assert state.disagreed is False
    assert state.method == "weighted_vote"
    assert len(state.responses) == 3
    assert state.receipt is None  # sign defaults to False


@pytest.mark.asyncio
async def test_flow_with_signing():
    priv, _ = Ed25519Backend().generate_keypair()
    swarm = _StubSwarm(name="FlowSign")
    flow = ConsensusFlow(swarm, sign=True, signing_key=priv, task_id="f-1")

    await flow.kickoff_async(inputs={"question": "ship it"})

    receipt = ConsensusReceipt(**flow.state.receipt)
    assert receipt.is_signed
    assert Ed25519Backend().verify_receipt(receipt) is True


# --- Composition: tool inside a real CrewAI crew -----------------------------


@pytest.mark.asyncio
async def test_tool_drops_into_crew():
    """
    The wedge case: a real CrewAI Agent with the consensus tool in its
    belt, in a real Crew. The agent *calls* consensus.

    We stub the swarm so no consensus Claude call happens — but the agent
    itself still needs an LLM to decide to call the tool. CrewAI defaults
    to OpenAI if no llm is set, which fails without OPENAI_API_KEY; we
    point it at Anthropic explicitly (matching killer_demo.py's pattern).
    """
    from crewai import LLM, Agent, Crew
    from crewai import Task as CrewTask

    # Skip cleanly if no Anthropic key — this test needs a real LLM call
    # (the agent has to decide to invoke the tool).
    if not os.getenv("ANTHROPIC_API_KEY"):
        pytest.skip("set ANTHROPIC_API_KEY (agent LLM call needed to trigger the tool)")

    llm = LLM(
        model="anthropic/claude-3-5-haiku-20241022",
        api_key=os.environ["ANTHROPIC_API_KEY"],
        max_tokens=128,
    )

    swarm = _StubSwarm()
    tool = reach_consensus(swarm)

    agent = Agent(
        role="Decider",
        goal="Reach consensus on the question using your reach_consensus tool.",
        backstory="You delegate hard questions to a multi-agent panel.",
        llm=llm,
        tools=[tool],
        allow_delegation=False,
        verbose=False,
    )
    task = CrewTask(
        description="Use reach_consensus to decide: tabs or spaces?",
        expected_output="The consensus answer.",
        agent=agent,
    )
    crew = Crew(agents=[agent], tasks=[task], verbose=False)

    # CrewAI's kickoff is sync; mirror the killer_demo's executor pattern.
    import asyncio

    await asyncio.to_thread(crew.kickoff)

    # The agent should have called the tool, which ran our stub swarm.
    assert swarm.last_task is not None


# --- Integration test (real Claude, opt-in) ----------------------------------

RUN_LIVE = os.environ.get("CLAUDEWAY_RUN_LIVE") == "1"


@pytest.mark.asyncio
@pytest.mark.skipif(
    not RUN_LIVE,
    reason="set CLAUDEWAY_RUN_LIVE=1 to run the real-Claude integration test",
)
async def test_live_tool_round_trip():
    """Real Swarm + real Claude through the @tool."""
    swarm = Swarm(
        SwarmConfig(
            name="LiveCrewTest",
            description="one-agent live adapter test",
            agents=[
                AgentConfig(
                    "Pragmatist", "Staff Engineer",
                    "Answer in one short sentence.",
                    model="claude-3-5-haiku-20241022",
                    max_tokens=64,
                ),
            ],
        ),
        api_key=os.getenv("ANTHROPIC_API_KEY"),
    )

    tool = reach_consensus(swarm, sign=True, task_id="live-tool-1")
    out = tool.run(question="What's one good side-project database?")

    assert isinstance(out, str)
    assert "signed receipt" in out
    assert "agreement:" in out
