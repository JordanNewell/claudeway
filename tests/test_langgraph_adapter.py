"""
LangGraph adapter tests.

Two layers:

  - Unit tests (default): stub Swarm.process so the adapter is exercised
    end-to-end through real LangGraph machinery (StateGraph, compile,
    ainvoke) without touching Claude. Fast, hermetic.

  - One integration test: real Swarm + real Claude, gated on
    ANTHROPIC_API_KEY. Skips in CI (no key). Catches drift between the
    adapter and Swarm.process's actual output shape — the one thing the
    stubbed tests can't.

langgraph is required; `pip install langgraph`. Skips cleanly when absent,
matching tests/test_nostr.py's coincurve precedent.
"""

import os

import pytest

pytest.importorskip("langgraph", reason="pip install langgraph")

from langchain_core.messages import HumanMessage  # noqa: E402

from claudeway import AgentConfig, Swarm, SwarmConfig  # noqa: E402
from claudeway.adapters.langgraph import (  # noqa: E402
    build_consensus_graph,
    make_consensus_node,
)
from claudeway.signing import ConsensusReceipt, Ed25519Backend  # noqa: E402
from claudeway.swarm import Task  # noqa: E402

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
        # Mirror real Swarm: on_event is set by the adapter when streaming.
        self.on_event = None

    async def process(self, task: Task) -> Task:
        self.last_task = task
        # When an observer is wired (streaming mode), fire per-agent events
        # then the consensus-resolved event — mirroring real Swarm.process.
        if self.on_event is not None:
            from claudeway.events import AgentCompleted, ConsensusResolved
            for r in CANNED_RESULT["responses"]:
                await self.on_event(AgentCompleted(
                    swarm_id=getattr(self.config, "name", ""),
                    task_id=task.id,
                    agent=r["agent"],
                    answer=r["answer"],
                    confidence=r["confidence"],
                    round=1,
                ))
            await self.on_event(ConsensusResolved(
                swarm_id=getattr(self.config, "name", ""),
                task_id=task.id,
                final_answer=CANNED_RESULT["final_answer"],
                method=CANNED_RESULT["method"],
                agreement=CANNED_RESULT["agreement"],
                rounds=CANNED_RESULT["rounds"],
                disagreed=CANNED_RESULT["disagreed"],
            ))
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
async def test_node_sign_emits_verifiable_receipt_with_dict_form_responses():
    """The adapter must work even when task.result has dict-form responses.

    Swarm.process always returns task.result as a dict (it round-tripped
    through ConsensusResult.to_dict()). The adapter used to rebuild
    AgentResponse objects defensively — that's no longer needed since
    the core fix, but if anyone reverts that fix this test will catch it.
    """
    swarm = _StubSwarm()
    # Force a result with responses already in dict form (which is the
    # natural shape — _StubSwarm already returns CANNED_RESULT, which
    # has dicts). Just make it explicit.
    assert all(isinstance(r, dict) for r in CANNED_RESULT["responses"])

    priv, _ = Ed25519Backend().generate_keypair()
    node = make_consensus_node(swarm, sign=True, signing_key=priv)

    update = await node({"question": "dict-form responses"})
    receipt = ConsensusReceipt(**update["receipt"])
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
async def test_node_auto_generated_signing_key_is_stable_across_invokes():
    """Without an explicit signing_key, the same node must reuse one key.

    Earlier per-invoke key generation meant two receipts from the same node
    came from different keys — unlinkable. An M&A reviewer would flag this.
    The key is now hoisted to node-construction time.
    """
    swarm = _StubSwarm()
    node = make_consensus_node(swarm, sign=True)

    update1 = await node({"question": "first"})
    update2 = await node({"question": "second"})

    # Same node, same signing key — the public key (verificationMethod) is
    # the same across both receipts.
    key1 = ConsensusReceipt(**update1["receipt"]).public_key
    key2 = ConsensusReceipt(**update2["receipt"]).public_key
    assert key1 == key2, (
        "signing key changed between invokes — receipts are unlinkable"
    )


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


# --- Integration test (real Claude, opt-in) ----------------------------------
#
# Gated on CLAUDEWAY_RUN_LIVE=1 (NOT just ANTHROPIC_API_KEY) so a plain
# `pytest` run never spends budget — you must explicitly opt in. When run,
# it uses the cheapest possible config: one Haiku agent, 64 max_tokens.
# That's ~one API call, a few hundred tokens total.
#
# Catches the one thing the stubbed tests can't: drift between the adapter
# and Swarm.process's actual output shape against real Claude output.

RUN_LIVE = os.environ.get("CLAUDEWAY_RUN_LIVE") == "1"


@pytest.mark.asyncio
@pytest.mark.skipif(
    not RUN_LIVE,
    reason="set CLAUDEWAY_RUN_LIVE=1 to run the real-Claude integration test",
)
async def test_live_swarm_round_trip_through_langgraph():
    """Real Swarm + real Claude through the prebuilt subgraph."""
    swarm = Swarm(
        SwarmConfig(
            name="LiveAdapterTest",
            description="one-agent live adapter test",
            agents=[
                AgentConfig(
                    "Pragmatist", "Staff Engineer",
                    "Answer in one short sentence.",
                    model="claude-haiku-4-5-20251001",
                    max_tokens=64,
                ),
            ],
        ),
        api_key=os.getenv("ANTHROPIC_API_KEY"),
    )

    graph = build_consensus_graph(swarm, sign=True, task_id="live-1")
    result = await graph.ainvoke({"question": "What's one good side-project database?"})

    # We don't assert on the answer text — that's Claude's call. We assert the
    # shape contract Swarm.process promises, end-to-end through LangGraph.
    assert isinstance(result["final_answer"], str)
    assert result["final_answer"].strip()
    assert 0.0 <= result["agreement"] <= 1.0
    assert isinstance(result["disagreed"], bool)
    assert isinstance(result["responses"], list)
    assert len(result["responses"]) == 1

    # The signed receipt must verify — proves the live path produces a real
    # attestation, not just text.
    receipt = ConsensusReceipt(**result["receipt"])
    assert receipt.is_signed
    assert Ed25519Backend().verify_receipt(receipt) is True


# --- Streaming (stream_mode="custom") ----------------------------------------
#
# When stream=True, the node forwards per-agent AgentCompleted events (and
# the final ConsensusResolved) to LangGraph's custom stream channel via
# get_stream_writer(). Consumers read via graph.astream(..., stream_mode="custom").


@pytest.mark.asyncio
async def test_stream_writer_receives_per_agent_events():
    """stream=True: per-agent events land in the custom stream channel."""
    swarm = _StubSwarm()
    graph = build_consensus_graph(swarm, stream=True)

    custom_chunks = []
    async for chunk in graph.astream({"question": "which db?"}, stream_mode="custom"):
        custom_chunks.append(chunk)

    # 3 per-agent AgentCompleted + 1 ConsensusResolved.
    agent_chunks = [c for c in custom_chunks if c.get("kind") == "agent_completed"]
    resolved_chunks = [c for c in custom_chunks if c.get("kind") == "consensus_resolved"]

    assert len(agent_chunks) == 3, f"expected 3 per-agent, got {len(agent_chunks)}"
    agents = sorted(c["agent"] for c in agent_chunks)
    assert agents == ["Dba", "Indie", "Security"]
    assert all("answer" in c and "confidence" in c for c in agent_chunks)
    assert len(resolved_chunks) == 1
    assert resolved_chunks[0]["final_answer"] == "use sqlite"


@pytest.mark.asyncio
async def test_stream_off_by_default_emits_no_custom_chunks():
    """stream=False (default): no custom stream chunks, just the state update."""
    swarm = _StubSwarm()
    graph = build_consensus_graph(swarm)  # stream defaults to False

    custom_chunks = []
    async for chunk in graph.astream({"question": "which db?"}, stream_mode="custom"):
        custom_chunks.append(chunk)

    assert custom_chunks == []
