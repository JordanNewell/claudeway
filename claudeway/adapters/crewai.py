"""
CrewAI adapter — Claudeway consensus as a CrewAI tool and Flow.

CrewAI is the role-based framework Claudeway's killer demo already beats on
cost and answer quality. This adapter inverts that relationship: a CrewAI
crew can *call* Claudeway for consensus. Same dep, opposite direction —
the competitor becomes a distribution channel.

Two entry points, mirroring the LangGraph adapter's two-shape pattern:

  - reach_consensus(swarm) -> CrewAI @tool
      Attach to any Agent. The agent decides when to call consensus.
      Sync wrapper around the async swarm (CrewAI tools are sync).

  - ConsensusFlow(swarm) -> a prebuilt Flow
      Idiomatic for users who orchestrate with Flows. Async-native.
      Embed in a larger Flow via @listen, or run standalone.

CrewAI is imported lazily so core `claudeway` stays dependency-free.
Install it yourself: `pip install claudeway[crewai]`.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..swarm import Swarm


# --- Tool shape (broad reach) ------------------------------------------------


def reach_consensus(
    swarm: Swarm,
    *,
    sign: bool = False,
    signing_key: str | None = None,
    task_id: str | None = None,
):
    """
    Return a CrewAI @tool that runs the swarm and returns a formatted summary.

    Attach the returned tool to any CrewAI Agent:

        from claudeway.adapters.crewai import reach_consensus
        agent = Agent(role='...', tools=[reach_consensus(swarm)])

    The agent invokes the tool with a question string; the tool runs the
    swarm, returns the final answer plus agreement and (optionally) a signed
    receipt. CrewAI tools are sync, so the async swarm is bridged with
    asyncio.run — a fresh event loop per call, safe because tools don't
    share loop state.
    """
    from crewai.tools import tool

    # Closure captures swarm + signing config; the @tool signature below is
    # what CrewAI introspects for arg descriptions, so it surfaces `question`
    # cleanly (verified: the decorator inspects the wrapped function).
    @tool("reach_consensus")
    def reach_consensus_tool(question: str) -> str:
        """Reach a signed multi-agent consensus on a question.

        Use this when a question deserves multiple specialist perspectives
        and a verifiable agreement — not for simple lookups. Returns the
        final answer, the agreement score, and (if signed) a receipt.
        """
        return _run_sync(
            _consensus_to_str(swarm, question, sign, signing_key, task_id)
        )

    return reach_consensus_tool


# --- Flow shape (idiomatic for Flow users) -----------------------------------


def _build_consensus_flow_class():
    """
    Construct the ConsensusFlow class.

    CrewAI's @start / @listen decorators are applied at class-definition
    time (decorator semantics), so the class can't be built in __init__.
    We define it here, lazily importing crewai, and store the swarm on
    self at instantiation — the methods read it via self._swarm.
    """
    from crewai.flow.flow import Flow, listen, start

    class ConsensusFlow(Flow[ConsensusState]):
        """
        Prebuilt Flow: question in → signed agreement out.

            flow = ConsensusFlow(swarm, sign=True)
            result = await flow.kickoff_async(inputs={"question": "..."})
            # flow.state now has final_answer, agreement, receipt...

        Embed in a larger Flow via @listen(ConsensusFlow.start_consensus),
        or run standalone. The swarm, signing config, and task_id are set
        on the instance via __init__.
        """

        # Set by __init__; read by the step method.
        _swarm: Any = None
        _sign: bool = False
        _signing_key: str | None = None
        _task_id: str | None = None

        @start()
        def start_consensus(self) -> dict[str, Any]:
            # @start methods receive inputs from kickoff(inputs=...). We
            # don't need to mutate state here — the listen step does the
            # work. Return a placeholder so the Flow has a trigger.
            return {}

        @listen(start_consensus)
        async def run_consensus(self) -> dict[str, Any]:
            # Flow inputs land on self.state via the kickoff(inputs=) mapping;
            # CrewAI populates the Pydantic state from matching keys.
            question = self.state.question
            update = await _consensus_to_dict(
                self._swarm, question, self._sign, self._signing_key, self._task_id
            )
            # Mutate state so downstream @listen steps can read structured fields.
            for k, v in update.items():
                setattr(self.state, k, v)
            return update

    return ConsensusFlow


# ConsensusState is module-scope (not in a factory) so Pydantic can introspect
# it. Imported lazily-deferred: crewai pulls pydantic, so we import BaseModel
# at module load — that's a transitive dep, not a new one for claudeway.
from pydantic import BaseModel  # noqa: E402


class ConsensusState(BaseModel):
    """State shape for ConsensusFlow.

    `question` is the input (matched by key from kickoff(inputs=...)).
    Other fields are populated by the consensus step. Use a downstream
    @listen to read final_answer / agreement / receipt.
    """

    question: str = ""
    final_answer: str = ""
    agreement: float = 0.0
    disagreed: bool = False
    responses: list[dict[str, Any]] = []
    rounds: int = 0
    method: str = ""
    receipt: dict[str, Any] | None = None


# Public alias: instantiate after setting swarm via __init__.
# Implemented as a thin wrapper so callers do ConsensusFlow(swarm, sign=True).
class ConsensusFlow:
    """
    Prebuilt CrewAI Flow: question in → signed agreement out.

        flow = ConsensusFlow(swarm, sign=True)
        result = await flow.kickoff_async(inputs={"question": "..."})

    The underlying crewai Flow is built lazily on first instantiation —
    decorators are applied at class-body time, so we can't define it in
    __init__. Each ConsensusFlow instance gets its own subclass bound to
    the configured swarm.
    """

    def __init__(
        self,
        swarm: Swarm,
        *,
        sign: bool = False,
        signing_key: str | None = None,
        task_id: str | None = None,
    ) -> None:
        # Build a fresh subclass per instance so self._swarm etc. don't
        # leak across instances. The class body is identical; only the
        # instance attributes differ.
        base = _build_consensus_flow_class()
        # crewai Flow.__init__ takes no required args; we call it, then
        # set our config. (Flow sets up state, _methods, etc.)
        # We can't subclass+rename easily, so we bind the configured base
        # and instantiate it.
        instance = base()
        instance._swarm = swarm
        instance._sign = sign
        instance._signing_key = signing_key
        instance._task_id = task_id
        # Re-export the instance's behavior on self so `await flow.kickoff_async()`
        # works without the caller knowing about the inner class.
        self._inner = instance

    def kickoff_async(self, *args: Any, **kwargs: Any):
        return self._inner.kickoff_async(*args, **kwargs)

    def kickoff(self, *args: Any, **kwargs: Any):
        return self._inner.kickoff(*args, **kwargs)

    @property
    def state(self) -> ConsensusState:
        return self._inner.state


# --- Shared consensus runner -------------------------------------------------


async def _consensus_to_dict(
    swarm: Swarm,
    question: str,
    sign: bool,
    signing_key: str | None,
    task_id: str | None,
) -> dict[str, Any]:
    """Run the swarm, return the consensus fields (+ receipt if signing)."""
    from ..signing import ConsensusReceipt, Ed25519Backend
    from ..swarm import Task

    task = Task(id=task_id or str(uuid.uuid4()), description=question, input_data={})
    completed = await swarm.process(task)
    result = completed.result

    update: dict[str, Any] = {
        "final_answer": result["final_answer"],
        "agreement": result["agreement"],
        "disagreed": result["disagreed"],
        "responses": result["responses"],
        "rounds": result["rounds"],
        "method": result["method"],
    }

    if sign:
        receipt = ConsensusReceipt.from_result(
            _rebuild_result(result),
            swarm_name=getattr(swarm.config, "name", ""),
            task_id=task.id,
        )
        key = signing_key or Ed25519Backend().generate_keypair()[0]
        Ed25519Backend().sign_receipt(receipt, key)
        update["receipt"] = receipt.to_dict()

    return update


async def _consensus_to_str(
    swarm: Swarm,
    question: str,
    sign: bool,
    signing_key: str | None,
    task_id: str | None,
) -> str:
    """Run the swarm, return a CrewAI-tool-readable formatted string."""
    update = await _consensus_to_dict(swarm, question, sign, signing_key, task_id)
    lines = [
        update["final_answer"],
        f"agreement: {update['agreement']:.0%}   disagreed: {update['disagreed']}",
        f"method: {update['method']}   rounds: {update['rounds']}",
    ]
    if "receipt" in update:
        r = update["receipt"]
        lines.append(
            f"signed receipt: algorithm={r['algorithm']} "
            f"sig={r['signature'][:24]}... pubkey={r['public_key'][:24]}..."
        )
    return "\n".join(lines)


def _run_sync(coro) -> str:
    """
    Bridge an async consensus call into a sync CrewAI tool.

    CrewAI tools are sync, but the swarm is async. The safe way to bridge
    is ALWAYS a fresh worker thread with its own event loop — never reuse
    the caller's loop. Reusing the caller's loop via
    run_coroutine_threadsafe + fut.result() self-deadlocks when the caller
    is on the loop's own thread (e.g. pytest-asyncio, or CrewAI calling
    the tool from inside its async runtime): fut.result() blocks the
    thread that would have run the coro.

    A fresh thread sidesteps all of that: it has no loop, asyncio.run
    works, and we block on join() until the result is ready. Works whether
    the caller is sync, async, or already in a thread.
    """
    import threading

    result: list[Any] = []
    error: list[BaseException] = []

    def worker() -> None:
        try:
            result.append(asyncio.run(coro))
        except BaseException as exc:  # noqa: BLE001 — re-raised in caller
            error.append(exc)

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    t.join()

    if error:
        raise error[0]
    return result[0]


def _rebuild_result(d: dict[str, Any]):
    """Reconstruct a ConsensusResult from its dict form for signing.

    Same dict-form AgentResponse rebuild the LangGraph adapter uses —
    task.result is always the dict form, but ConsensusResult.to_dict()
    (called inside ConsensusReceipt.from_result) reads r.agent_name off
    each response.
    """
    from ..consensus import ConsensusResult
    from ..swarm import AgentResponse

    return ConsensusResult(
        final_answer=d["final_answer"],
        method=d["method"],
        agent_count=d["agent_count"],
        responses=[
            AgentResponse(
                agent_name=r["agent"],
                answer=r["answer"],
                confidence=r["confidence"],
            )
            for r in d.get("responses", [])
        ],
        agreement=d["agreement"],
        rounds=d["rounds"],
        disagreed=d["disagreed"],
    )
