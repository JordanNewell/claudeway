"""
LangGraph adapter tests — offline, no Anthropic API key.

Stubs Swarm.process so the adapter is exercised end-to-end through real
LangGraph machinery (StateGraph, compile, ainvoke) without touching Claude.

langgraph is required; `pip install langgraph`. Skips cleanly when absent,
matching tests/test_nostr.py's coincurve precedent.
"""

import pytest

pytest.importorskip("langgraph", reason="pip install langgraph")

from langchain_core.messages import HumanMessage  # noqa: E402

from claudeway.adapters.langgraph import (  # noqa: E402
    build_consensus_graph,
    make_consensus_node,
)
from claudeway.signing import ConsensusReceipt, Ed25519Backend  # noqa: E402
from claudeway.swarm import SwarmConfig, Task  # noqa: E402

# --- Fixtures ----------------------------------------------------------------

# A canonical "the swarm agreed" result dict, in the exact shape Swarm.process
# produces via ConsensusResult.to_dict().
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
    """
    Minimal swarm stand-in: captures the task, returns it with CANNED_RESULT.

    We avoid subclassing real Swarm because Swarm.__init__ wires up real
    Agent objects (and would need AgentConfigs). The adapter only calls
    `swarm.process(task)` and reads `swarm.config.name`, so this is enough.
    """

    def __init__(self, name: str = "TestSwarm"):
        self.config = SwarmConfig(name=name, description="", agents=[])
        self.last_task: Task | None = None

    async def process(self, task: Task) -> Task:
        self.last_task = task
        task.result = CANNED_RESULT
        task.status = "completed"
        return task


# --- Node factory ------------------------------------------------------------


@pytest.mark.asyncio
async def test_node_returns_consensus_fields():
    swarm = _StubSwarm()
    node = make_consensus_node(swarm)

    update = await node({"question": "which db?"})

    assert update["final_answer"] == "use sqlite"
    assert update["agreement"] == 0.9
    assert update["disagreed"] is False
    assert update["method"] == "weighted_vote"
    assert update["rounds"] == 1
    assert len(update["responses"]) == 3
    # Signing is opt-in; absent by default.
    assert "receipt" not in update


@pytest.mark.asyncio
async def test_node_passes_prompt_as_task_description():
    swarm = _StubSwarm()
    node = make_consensus_node(swarm)

    await node({"question": "postgres or sqlite?"})

    assert swarm.last_task is not None
    assert swarm.last_task.description == "postgres or sqlite?"


@pytest.mark.asyncio
async def test_node_input_key_override():
    swarm = _StubSwarm()
    node = make_consensus_node(swarm, input_key="prompt")

    await node({"prompt": "rust or go?"})

    assert swarm.last_task.description == "rust or go?"


@pytest.mark.asyncio
async def test_node_falls_back_to_last_human_message():
    swarm = _StubSwarm()
    node = make_consensus_node(swarm)

    # No "question" key — should pull from the last human message.
    await node({"messages": [HumanMessage(content="debate me on tabs vs spaces")]})

    assert swarm.last_task.description == "debate me on tabs vs spaces"


@pytest.mark.asyncio
async def test_node_rejects_empty_state():
    swarm = _StubSwarm()
    node = make_consensus_node(swarm)

    with pytest.raises(ValueError, match="could not find a prompt"):
        await node({})


# --- Signing -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_node_sign_emits_verifiable_receipt():
    priv, _ = Ed25519Backend().generate_keypair()
    swarm = _StubSwarm(name="SignTest")
    node = make_consensus_node(swarm, sign=True, signing_key=priv, task_id="t-1")

    update = await node({"question": "sign this"})

    receipt_dict = update["receipt"]
    assert receipt_dict["algorithm"] == "ed25519"
    assert receipt_dict["public_key"]
    assert receipt_dict["signature"]

    # Round-trip: dict -> ConsensusReceipt -> verify.
    receipt = ConsensusReceipt(**receipt_dict)
    assert receipt.is_signed
    assert Ed25519Backend().verify_receipt(receipt) is True


@pytest.mark.asyncio
async def test_node_sign_without_key_generates_one():
    swarm = _StubSwarm()
    node = make_consensus_node(swarm, sign=True)

    update = await node({"question": "auto-key"})

    # Generated keys still produce a verifiable receipt.
    receipt = ConsensusReceipt(**update["receipt"])
    assert Ed25519Backend().verify_receipt(receipt) is True


@pytest.mark.asyncio
async def test_tampered_receipt_fails_verification():
    priv, _ = Ed25519Backend().generate_keypair()
    swarm = _StubSwarm()
    node = make_consensus_node(swarm, sign=True, signing_key=priv)

    update = await node({"question": "don't tamper"})
    receipt = ConsensusReceipt(**update["receipt"])
    assert Ed25519Backend().verify_receipt(receipt) is True

    # Mutate the payload after signing — must invalidate the signature.
    receipt.payload["result"]["final_answer"] = "use mongodb"
    assert Ed25519Backend().verify_receipt(receipt) is False


# --- Prebuilt subgraph -------------------------------------------------------


@pytest.mark.asyncio
async def test_build_consensus_graph_round_trips():
    swarm = _StubSwarm()
    graph = build_consensus_graph(swarm)

    result = await graph.ainvoke({"question": "which db for a side project?"})

    assert result["final_answer"] == "use sqlite"
    assert result["agreement"] == 0.9
    assert "receipt" not in result  # sign defaults to False


@pytest.mark.asyncio
async def test_build_consensus_graph_with_signing():
    swarm = _StubSwarm(name="SubgraphSign")
    graph = build_consensus_graph(swarm, sign=True, task_id="g-1")

    result = await graph.ainvoke({"question": "ship it"})

    receipt = ConsensusReceipt(**result["receipt"])
    assert Ed25519Backend().verify_receipt(receipt) is True


# --- Composition: node inside a user-owned graph -----------------------------


@pytest.mark.asyncio
async def test_node_drops_into_user_graph():
    """
    The wedge case: a user has their own StateGraph and adds our consensus
    node alongside their own nodes. Verify it composes through real
    StateGraph machinery.
    """
    from typing import TypedDict

    from langgraph.graph import END, START, StateGraph

    class MyState(TypedDict, total=False):
        question: str
        research: str
        final_answer: str
        agreement: float

    async def research_node(state):
        # Pretend to do upstream work; pass the question through.
        return {"research": f"looked into: {state['question']}"}

    swarm = _StubSwarm()
    consensus = make_consensus_node(swarm)

    builder = StateGraph(MyState)
    builder.add_node("research", research_node)
    builder.add_node("consensus", consensus)
    builder.add_edge(START, "research")
    builder.add_edge("research", "consensus")
    builder.add_edge("consensus", END)

    app = builder.compile()
    result = await app.ainvoke({"question": "tabs or spaces?"})

    assert result["research"] == "looked into: tabs or spaces?"
    assert result["final_answer"] == "use sqlite"
    assert result["agreement"] == 0.9
