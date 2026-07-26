"""
Microsoft Agent Framework (MAF) adapter — drop Claudeway consensus into a
MAF workflow.

MAF (the unified successor to AutoGen + Semantic Kernel, v1.0 GA April 2026)
gives you typed executors wired into a graph. What it does NOT give you is a
way for those executors to *agree* — that's the same whitespace LangGraph
punts on, and the same whitespace Claudeway fills.

Two entry points, both build-once (per MAF forum guidance: construct
executors once, wire edges once, never rebuild per invoke):

  - make_consensus_executor(swarm) -> Executor
      For users who own the workflow. add_edge() it into their own
      WorkflowBuilder.

  - build_consensus_workflow(swarm) -> Workflow
      Prebuilt one-node workflow: str in -> signed agreement out. Use
      standalone, or compose into a larger workflow via add_edge.

  - consensus_as_agent(swarm) -> Agent
      Wraps the workflow in MAF's native .as_agent() so it drops in anywhere
      MAF expects an Agent (orchestrations, other workflows, as a tool).

agent_framework is imported lazily so core `claudeway` stays dependency-free.
Install it yourself: `pip install claudeway[maf]`.

Note: this module deliberately does NOT use `from __future__ import
annotations`. The Executor subclass is defined inside a factory function
with a lazy `from agent_framework import ...`, and PEP 563 string
annotations would be unresolvable from MAF's get_type_hints() (the names
live in the function's locals, not module globals). Eager annotations
evaluated at class-definition time capture the live types directly.
"""

import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..swarm import Swarm

# --- Executor factory --------------------------------------------------------


def make_consensus_executor(
    swarm: "Swarm",
    *,
    sign: bool = False,
    signing_key: str | None = None,
    task_id: str | None = None,
    stream: bool = False,
):
    """
    Return a MAF Executor subclass that runs the swarm and yields the
    consensus payload as the workflow's terminal output.

    The swarm is captured in the executor instance — this keeps the
    build-once invariant honest (no per-invoke swarm construction) and
    mirrors how the LangGraph adapter parameterizes its node via closure.

    sign: if True, sign each result and put the ConsensusReceipt (as a dict)
        into the yielded payload under "receipt". The moat, one kwarg away.
    signing_key: hex Ed25519 private key. If None and sign=True, a fresh
        keypair is generated ONCE at executor construction and reused across
        invokes — so all receipts from this executor are verifiable as
        coming from the same source. Per-invoke key generation would
        unlink them (an M&A reviewer would flag that).
    task_id: stable id for the receipt. If None, a uuid4 is generated per
        invoke (each invoke is a distinct consensus event).
    stream: if True, each per-agent answer (AgentCompleted event) is yielded
        as an intermediate workflow output as it lands, before the final
        consensus. Pair with build_consensus_workflow(stream=True) so those
        intermediate yields are labeled type="intermediate" (the canonical
        MAF streaming pattern). Off = byte-identical to today.
    """
    from agent_framework import Executor, WorkflowContext, handler

    from ..signing import ConsensusReceipt, Ed25519Backend

    # Hoist expensive/stateful setup out of the per-invoke handler. If we
    # generated a fresh signing key per invoke, receipts from this executor
    # wouldn't be linkable to a stable identity.
    if sign and signing_key is None:
        signing_key = Ed25519Backend().generate_keypair()[0]
    signing_backend = Ed25519Backend() if sign else None
    captured_signing_key = signing_key
    # getattr, not attribute access: duck-typed swarm stubs (in tests) that
    # bypass Swarm.__init__ don't set on_event. None is the correct fallback.
    prior_on_event = getattr(swarm, "on_event", None)

    class ConsensusExecutor(Executor):
        """One handler: str in -> consensus payload yielded out.

        WorkflowContext is parametrized twice — [SendMessage, WorkflowOutput]
        — which is how MAF declares both the routed message type and the
        terminal output type in one annotation. That's what makes this
        executor a valid output_from target without separate @handler type
        parameters.
        """

        @handler
        async def reach_consensus(
            self,
            message: str,
            ctx: WorkflowContext[dict[str, Any], dict[str, Any]],
        ) -> None:
            prompt = _resolve_prompt(message)
            # task_id: per-invoke uuid when None (each invoke is its own event).
            this_task_id = task_id or str(uuid.uuid4())
            from ..swarm import Task  # lazy to keep top-level import cheap

            if stream:
                # Forward per-agent events as intermediate workflow outputs.
                # The callback captures THIS invoke's ctx, so each yield lands
                # in the right run. Swarm.process already swallows observer
                # errors, so a MAF yield failure can't change the consensus.
                async def _forward_event(event):
                    await ctx.yield_output(event.model_dump())
                swarm.on_event = _forward_event
            try:
                task = Task(id=this_task_id, description=prompt, input_data={})
                completed = await swarm.process(task)
            finally:
                if stream:
                    swarm.on_event = prior_on_event
            result = completed.result

            payload: dict[str, Any] = {
                "final_answer": result["final_answer"],
                "agreement": result["agreement"],
                "disagreed": result["disagreed"],
                "responses": result["responses"],
                "rounds": result["rounds"],
                "method": result["method"],
            }

            if sign and signing_backend is not None:
                # ConsensusReceipt.from_result reads result.to_dict(), which
                # handles both AgentResponse objects and dict-form responses
                # (the latter is what task.result always is). No rebuild needed.
                receipt = ConsensusReceipt.from_result(
                    _result_from_dict(result),
                    swarm_name=getattr(swarm.config, "name", ""),
                    task_id=this_task_id,
                )
                signing_backend.sign_receipt(receipt, captured_signing_key)
                payload["receipt"] = receipt.to_dict()

            if stream:
                # ConsensusResolved (forwarded from on_event) is already the
                # terminal intermediate carrying consensus fields. When signing,
                # yield the receipt as one final intermediate so stream consumers
                # get the signed attestation. (kind="consensus_receipt" lets
                # consumers pick it out from the per-agent events.)
                if sign and signing_backend is not None:
                    await ctx.yield_output({"kind": "consensus_receipt", **payload["receipt"]})
            else:
                # Non-streaming: the payload is the sole terminal output
                # (the only thing get_outputs() returns).
                await ctx.yield_output(payload)

    return ConsensusExecutor


# --- Prebuilt workflow -------------------------------------------------------


def build_consensus_workflow(
    swarm: "Swarm",
    *,
    sign: bool = False,
    signing_key: str | None = None,
    task_id: str | None = None,
    stream: bool = False,
):
    """
    Build a standalone one-node MAF workflow: str in -> consensus payload out.

    Returns a built Workflow. Invoke with `await workflow.run(prompt)` and
    read `result.get_outputs()`, or embed via
    `builder.add_edge(upstream, consensus_executor)`.

    stream: when True, per-agent answers land as `type="intermediate"` events
        (consumable via `workflow.run(prompt, stream=True)`) before the final
        `type="output"` consensus. Uses MAF's `intermediate_output_from` so
        the same yield_output call gets the right label per build-time
        classification — the canonical MAF streaming pattern.

    Construction happens once here, not per invoke.
    """
    from agent_framework import WorkflowBuilder

    executor_cls = make_consensus_executor(
        swarm,
        sign=sign,
        signing_key=signing_key,
        task_id=task_id,
        stream=stream,
    )
    executor = executor_cls(id="claudeway_consensus")
    # MAF forbids an executor being in BOTH output_from and
    # intermediate_output_from (validated at build). So streaming is a
    # distinct consumption mode: the executor yields EVERYTHING as
    # intermediate (per-agent AgentCompleted events + the final
    # ConsensusResolved), and consumers read via the event stream — the
    # final consensus is the event whose payload has kind="consensus_resolved".
    # Non-streaming workflows keep get_outputs() working exactly as before.
    if stream:
        builder = WorkflowBuilder(
            start_executor=executor,
            intermediate_output_from=[executor],
        )
    else:
        builder = WorkflowBuilder(start_executor=executor, output_from=[executor])
    return builder.build()


# --- Agent shim --------------------------------------------------------------


def consensus_as_agent(
    swarm: "Swarm",
    *,
    name: str | None = None,
    sign: bool = False,
    signing_key: str | None = None,
    task_id: str | None = None,
    stream: bool = False,
):
    """
    Return a MAF Agent wrapping the consensus workflow.

    Exposes the workflow through MAF's native `.as_agent()` composability —
    the consensus workflow drops in anywhere MAF expects an Agent: as a
    participant in a SequentialBuilder / group-chat orchestration, as a node
    in another workflow, or further wrapped via `.as_tool()` so an outer
    LLM can invoke consensus on demand.

    name: agent display name. Defaults to the swarm's configured name.

    Implementation note: MAF's as_agent() requires the workflow's start
    executor to accept list[Message] (the agent-facing input type). The
    raw consensus executor takes a str. So the agent shim wraps the
    consensus executor behind a thin ingest executor that flattens the
    inbound Message list to its concatenated text and forwards it as str.
    """
    from agent_framework import Executor, Message, WorkflowBuilder, WorkflowContext, handler

    consensus = make_consensus_executor(
        swarm,
        sign=sign,
        signing_key=signing_key,
        task_id=task_id,
        stream=stream,
    )(id="claudeway_consensus")

    class IngestExecutor(Executor):
        """Flatten inbound list[Message] to a single str prompt."""

        @handler
        async def ingest(
            self,
            messages: list[Message],
            ctx: WorkflowContext[str],
        ) -> None:
            # Concatenate message texts. MAF Message exposes .text.
            prompt = "\n".join(m.text for m in messages if getattr(m, "text", ""))
            await ctx.send_message(prompt)

    ingest = IngestExecutor(id="claudeway_ingest")
    builder = WorkflowBuilder(
        start_executor=ingest,
        output_from=[consensus],
        intermediate_output_from=[consensus] if stream else None,
    )
    builder.add_edge(ingest, consensus)
    workflow = builder.build()
    return workflow.as_agent(name=name or getattr(swarm.config, "name", "Consensus"))


# --- Helpers -----------------------------------------------------------------


def _resolve_prompt(message: str) -> str:
    """
    Validate the inbound prompt. MAF type-checks edge inputs against the
    handler's declared `str` parameter at workflow-build time, so by the
    time we get here the value is already a str — we just reject empties.
    """
    if isinstance(message, str) and message.strip():
        return message
    raise ValueError(
        "consensus executor received an empty prompt — the inbound str is blank"
    )


def _result_from_dict(d: dict[str, Any]):
    """
    Reconstruct a ConsensusResult from its dict form for signing.

    task.result is always a dict (Swarm.process stores result.to_dict()).
    ConsensusResult.to_dict() — called inside ConsensusReceipt.from_result
    — handles both AgentResponse objects and dict-form responses natively
    (fixed in claudeway core), so we don't need to rebuild AgentResponse
    objects here. Just pass the responses through.
    """
    from ..consensus import ConsensusResult

    return ConsensusResult(
        final_answer=d["final_answer"],
        method=d["method"],
        agent_count=d["agent_count"],
        responses=d.get("responses", []),
        agreement=d["agreement"],
        rounds=d["rounds"],
        disagreed=d["disagreed"],
    )
