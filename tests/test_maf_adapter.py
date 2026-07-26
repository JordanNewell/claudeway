"""
Microsoft Agent Framework (MAF) adapter tests.

Two layers:

  - Unit tests (default): stub Swarm.process so the adapter is exercised
    end-to-end through real MAF machinery (Executor, WorkflowBuilder, run,
    get_outputs) without touching Claude. Fast, hermetic.

  - One integration test: real Swarm + real Claude, gated on
    ANTHROPIC_API_KEY. Skips in CI (no key). Catches drift between the
    adapter and Swarm.process's actual output shape — the one thing the
    stubbed tests can't.

agent_framework is required; `pip install claudeway[maf]`. Skips cleanly
when absent, matching tests/test_nostr.py's coincurve precedent and
tests/test_langgraph_adapter.py's langgraph precedent.
"""

import os

import pytest

pytest.importorskip("agent_framework", reason="pip install claudeway[maf]")

from claudeway import AgentConfig, Swarm, SwarmConfig  # noqa: E402
from claudeway.adapters.maf import (  # noqa: E402
    build_consensus_workflow,
    consensus_as_agent,
    make_consensus_executor,
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

    async def process(self, task: Task) -> Task:
        self.last_task = task
        task.result = CANNED_RESULT
        task.status = "completed"
        return task


# --- Executor factory --------------------------------------------------------


@pytest.mark.asyncio
async def test_executor_yields_consensus_fields():
    """The bare executor runs the swarm and yields the consensus payload."""
    swarm = _StubSwarm()
    executor = make_consensus_executor(swarm)(id="t1")

    payload = await _run_executor(executor, "which db?")

    assert payload["final_answer"] == "use sqlite"
    assert payload["agreement"] == 0.9
    assert payload["disagreed"] is False
    assert payload["method"] == "weighted_vote"
    assert payload["rounds"] == 1
    assert len(payload["responses"]) == 3
    # Signing is opt-in; absent by default.
    assert "receipt" not in payload


@pytest.mark.asyncio
async def test_executor_passes_prompt_as_task_description():
    swarm = _StubSwarm()
    executor = make_consensus_executor(swarm)(id="t1")

    await _run_executor(executor, "postgres or sqlite?")

    assert swarm.last_task is not None
    assert swarm.last_task.description == "postgres or sqlite?"


@pytest.mark.asyncio
async def test_executor_rejects_empty_input():
    swarm = _StubSwarm()
    executor = make_consensus_executor(swarm)(id="t1")

    with pytest.raises(ValueError, match="empty prompt"):
        await _run_executor(executor, "   ")


# --- Signing -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_executor_sign_emits_verifiable_receipt():
    priv, _ = Ed25519Backend().generate_keypair()
    swarm = _StubSwarm(name="SignTest")
    executor = make_consensus_executor(swarm, sign=True, signing_key=priv, task_id="t-1")(id="t1")

    payload = await _run_executor(executor, "sign this")

    receipt_dict = payload["receipt"]
    assert receipt_dict["algorithm"] == "ed25519"
    assert receipt_dict["public_key"]
    assert receipt_dict["signature"]

    # Round-trip: dict -> ConsensusReceipt -> verify.
    receipt = ConsensusReceipt(**receipt_dict)
    assert receipt.is_signed
    assert Ed25519Backend().verify_receipt(receipt) is True


@pytest.mark.asyncio
async def test_executor_sign_emits_verifiable_receipt_with_dict_form_responses():
    """The adapter must work even when task.result has dict-form responses.

    Swarm.process always returns task.result as a dict (it round-tripped
    through ConsensusResult.to_dict()). The adapter used to rebuild
    AgentResponse objects defensively — that's no longer needed since
    the core fix, but if anyone reverts that fix this test will catch it.
    """
    swarm = _StubSwarm()
    assert all(isinstance(r, dict) for r in CANNED_RESULT["responses"])

    priv, _ = Ed25519Backend().generate_keypair()
    executor_cls = make_consensus_executor(swarm, sign=True, signing_key=priv)
    executor = executor_cls(id="t1")

    payload = await _run_executor(executor, "dict-form responses")
    receipt = ConsensusReceipt(**payload["receipt"])
    assert receipt.is_signed
    assert Ed25519Backend().verify_receipt(receipt) is True


@pytest.mark.asyncio
async def test_executor_sign_without_key_generates_one():
    swarm = _StubSwarm()
    executor = make_consensus_executor(swarm, sign=True)(id="t1")

    payload = await _run_executor(executor, "auto-key")

    # Generated keys still produce a verifiable receipt.
    receipt = ConsensusReceipt(**payload["receipt"])
    assert Ed25519Backend().verify_receipt(receipt) is True


@pytest.mark.asyncio
async def test_executor_auto_generated_signing_key_is_stable_across_invokes():
    """Without an explicit signing_key, one executor must reuse one key.

    Per-invoke key generation would mean two receipts from the same executor
    came from different keys — unlinkable. An M&A reviewer would flag this.
    The key is hoisted to executor-construction time.
    """
    swarm = _StubSwarm()
    executor = make_consensus_executor(swarm, sign=True)(id="t1")

    payload1 = await _run_executor(executor, "first")
    payload2 = await _run_executor(executor, "second")

    # Same executor, same signing key — the public key is the same across
    # both receipts.
    key1 = ConsensusReceipt(**payload1["receipt"]).public_key
    key2 = ConsensusReceipt(**payload2["receipt"]).public_key
    assert key1 == key2, (
        "signing key changed between invokes — receipts are unlinkable"
    )


@pytest.mark.asyncio
async def test_tampered_receipt_fails_verification():
    priv, _ = Ed25519Backend().generate_keypair()
    swarm = _StubSwarm()
    executor = make_consensus_executor(swarm, sign=True, signing_key=priv)(id="t1")

    payload = await _run_executor(executor, "don't tamper")
    receipt = ConsensusReceipt(**payload["receipt"])
    assert Ed25519Backend().verify_receipt(receipt) is True

    # Mutate the payload after signing — must invalidate the signature.
    receipt.payload["result"]["final_answer"] = "use mongodb"
    assert Ed25519Backend().verify_receipt(receipt) is False


# --- Prebuilt workflow -------------------------------------------------------


@pytest.mark.asyncio
async def test_build_consensus_workflow_round_trips():
    swarm = _StubSwarm()
    workflow = build_consensus_workflow(swarm)

    result = await workflow.run("which db for a side project?")

    payload = _first_output(result)
    assert payload["final_answer"] == "use sqlite"
    assert payload["agreement"] == 0.9
    assert "receipt" not in payload  # sign defaults to False


@pytest.mark.asyncio
async def test_build_consensus_workflow_with_signing():
    swarm = _StubSwarm(name="WorkflowSign")
    workflow = build_consensus_workflow(swarm, sign=True, task_id="g-1")

    result = await workflow.run("ship it")

    payload = _first_output(result)
    receipt = ConsensusReceipt(**payload["receipt"])
    assert Ed25519Backend().verify_receipt(receipt) is True


# --- Agent shim --------------------------------------------------------------


def test_consensus_as_agent_returns_callable_agent():
    """The agent shim returns something with the Agent contract (.run)."""
    swarm = _StubSwarm(name="AgentShim")
    agent = consensus_as_agent(swarm, name="ConsensusAgent")

    # An Agent is something you can .run() against. We don't invoke it here
    # (that needs a chat client) — we just assert the shim produced an
    # Agent-shaped object, which is the contract the workflow.as_agent()
    # surface promises.
    assert hasattr(agent, "run")
    assert getattr(agent, "name", None) == "ConsensusAgent"


# --- Composition: executor inside a user-owned workflow ---------------------


@pytest.mark.asyncio
async def test_executor_drops_into_user_workflow():
    """
    The wedge case: a user has their own WorkflowBuilder and adds our
    consensus executor alongside their own executor. Verify it composes
    through real MAF machinery.
    """
    from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler

    class ResearchExecutor(Executor):
        """Trivial upstream: prefix the question, forward as str."""

        @handler
        async def research(self, message: str, ctx: WorkflowContext[str]) -> None:
            await ctx.send_message(f"looked into: {message}")

    swarm = _StubSwarm()
    consensus = make_consensus_executor(swarm)(id="consensus")
    research = ResearchExecutor(id="research")

    builder = WorkflowBuilder(start_executor=research, output_from=[consensus])
    builder.add_edge(research, consensus)
    workflow = builder.build()

    result = await workflow.run("tabs or spaces?")
    payload = _first_output(result)

    # The research prefix becomes the prompt the consensus executor saw.
    assert swarm.last_task is not None
    assert swarm.last_task.description == "looked into: tabs or spaces?"
    assert payload["final_answer"] == "use sqlite"
    assert payload["agreement"] == 0.9


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
async def test_live_swarm_round_trip_through_maf():
    """Real Swarm + real Claude through the prebuilt workflow."""
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

    workflow = build_consensus_workflow(swarm, sign=True, task_id="live-1")
    result = await workflow.run("What's one good side-project database?")
    payload = _first_output(result)

    # We don't assert on the answer text — that's Claude's call. We assert the
    # shape contract Swarm.process promises, end-to-end through MAF.
    assert isinstance(payload["final_answer"], str)
    assert payload["final_answer"].strip()
    assert 0.0 <= payload["agreement"] <= 1.0
    assert isinstance(payload["disagreed"], bool)
    assert isinstance(payload["responses"], list)
    assert len(payload["responses"]) == 1

    # The signed receipt must verify — proves the live path produces a real
    # attestation, not just text.
    receipt = ConsensusReceipt(**payload["receipt"])
    assert receipt.is_signed
    assert Ed25519Backend().verify_receipt(receipt) is True


# --- Helpers -----------------------------------------------------------------


async def _run_executor(executor, message):
    """
    Drive a single executor invocation through a one-node workflow.

    Executors don't have a public "call this handler directly" entry point —
    they're meant to be run by the MAF engine. So we wire the executor into
    a minimal WorkflowBuilder and run that. This is also what the adapter
    itself does in build_consensus_workflow, so it exercises the real path.
    """
    from agent_framework import WorkflowBuilder

    builder = WorkflowBuilder(start_executor=executor, output_from=[executor])
    workflow = builder.build()
    result = await workflow.run(message)
    return _first_output(result)


def _first_output(run_result):
    """Pull the first output value out of a Workflow run result.

    WorkflowRunResult.get_outputs() returns the raw yielded values (not
    wrapped in event objects), so outputs[0] is the dict the executor
    yielded directly.
    """
    outputs = run_result.get_outputs()
    assert outputs, "workflow produced no output"
    return outputs[0]
