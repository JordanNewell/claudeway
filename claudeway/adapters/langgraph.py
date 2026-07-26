"""
LangGraph adapter — drop Claudeway consensus into a StateGraph.

LangGraph is the orchestration framework that "makes you wire coordination
by hand." This adapter is the seam: one node gets a signed agreement the
agents actually reached — no consensus wiring on the user's side.

Two entry points, both compile-once (per LangGraph forum guidance: never
compile inside a node, never return a subgraph from a node):

  - make_consensus_node(swarm) -> async node function
      For users who own the graph. add_node() it into their own StateGraph.

  - build_consensus_graph(swarm) -> CompiledStateGraph
      Prebuilt subgraph: {"question": str} -> signed agreement out.
      Use standalone, or add_node() the compiled graph into a parent graph.

LangGraph is imported lazily so core `claudeway` stays dependency-free.
Install it yourself: `pip install langgraph`.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Annotated, Any, TypedDict

if TYPE_CHECKING:
    from ..swarm import Swarm

# --- State schema ------------------------------------------------------------

# langgraph is the optional dep; import lazily so `import claudeway` doesn't
# drag it in. The TypedDict below references add_messages via a string
# forward ref (PEP 563 / `from __future__ import annotations`), so the name
# only needs to resolve when _state_schema() runs — which it does, by
# injecting add_messages into this module's globals first.


def _state_schema():
    """
    Return the ConsensusState TypedDict, making add_messages resolvable.

    Defined at module scope (not in this function) so LangGraph's
    get_type_hints() — which evaluates annotations against the class's
    __globals__ — can resolve `add_messages`. We just need to ensure that
    name exists in this module's globals before LangGraph introspects.
    """
    from langgraph.graph.message import add_messages

    globals()["add_messages"] = add_messages
    return ConsensusState


class ConsensusState(TypedDict, total=False):
    """LangGraph-native state shape for a consensus node.

    `messages` accumulates (add_messages reducer) so the node composes
    cleanly with chat-style graphs. Scalar fields overwrite (LangGraph's
    default reducer) — each run is the latest consensus.

    Note: `add_messages` is injected into module globals at first use by
    _state_schema(); the string forward ref here defers resolution.
    """

    messages: Annotated[list, "add_messages"]
    question: str
    final_answer: str
    agreement: float
    disagreed: bool
    responses: list[dict]
    rounds: int
    method: str
    receipt: dict | None  # only populated when sign=True


# --- Node factory ------------------------------------------------------------


def make_consensus_node(
    swarm: Swarm,
    *,
    input_key: str = "question",
    sign: bool = False,
    signing_key: str | None = None,
    task_id: str | None = None,
    stream: bool = False,
) -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
    """
    Return an async LangGraph node that runs the swarm and emits a partial
    state update.

    The swarm is captured in the closure — this is the documented way to
    parameterize a node without breaking the engine, and it keeps the
    compile-once invariant honest (no per-invoke setup).

    input_key: which state key holds the prompt. Falls back to the last
        human message in state["messages"] if that key is absent — so the
        node drops into chat-style graphs without configuration.
    sign: if True, sign each result and put the ConsensusReceipt (as a dict)
        into state["receipt"]. The moat, one kwarg away.
    signing_key: hex Ed25519 private key. If None and sign=True, a fresh
        keypair is generated ONCE at node construction and reused across
        invokes — so all receipts from this node are verifiable as coming
        from the same source. Per-invoke key generation would unlink them.
    task_id: stable id for the receipt. If None, a uuid4 is generated per
        invoke (each invoke is a distinct consensus event).
    stream: if True, forward each per-agent AgentCompleted event (and the
        final ConsensusResolved) to LangGraph's custom stream channel via
        get_stream_writer(), so consumers of graph.astream(...,
        stream_mode="custom") see agents answer in real time. Off = the
        node is a black box until it returns its state update.
    """
    from ..signing import ConsensusReceipt, Ed25519Backend
    from ..swarm import Task  # lazy to keep top-level import cheap

    # Hoist expensive/stateful setup out of the per-invoke closure. If we
    # generated a fresh signing key per invoke, receipts from this node
    # wouldn't be linkable to a stable identity.
    if sign and signing_key is None:
        signing_key = Ed25519Backend().generate_keypair()[0]
    # Cache the backend instance too — key gen is cheap but no point
    # reconstructing per invoke.
    signing_backend = Ed25519Backend() if sign else None
    # getattr, not attribute access: duck-typed swarm stubs (in tests) that
    # bypass Swarm.__init__ don't set on_event. None is the correct fallback.
    prior_on_event = getattr(swarm, "on_event", None)

    async def consensus_node(state: dict[str, Any]) -> dict[str, Any]:
        prompt = _resolve_prompt(state, input_key)
        # task_id: per-invoke uuid when None (each invoke is its own event).
        this_task_id = task_id or str(uuid.uuid4())

        if stream:
            # LangGraph's stream writer is sync — callable from async. Imported
            # lazily so the adapter stays dependency-free when stream=False.
            # Captured per-invoke so each node call writes to the right stream.
            from langgraph.config import get_stream_writer
            writer = get_stream_writer()

            async def _forward_event(event):
                # get_stream_writer() returns a sync callable; event.model_dump
                # gives a JSON-safe dict the consumer can introspect by kind.
                writer(event.model_dump())
            swarm.on_event = _forward_event
        try:
            task = Task(id=this_task_id, description=prompt, input_data={})
            completed = await swarm.process(task)
        finally:
            if stream:
                swarm.on_event = prior_on_event
        result = completed.result

        update: dict[str, Any] = {
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
            signing_backend.sign_receipt(receipt, signing_key)
            update["receipt"] = receipt.to_dict()

        return update

    return consensus_node


# --- Prebuilt subgraph -------------------------------------------------------


def build_consensus_graph(
    swarm: Swarm,
    *,
    input_key: str = "question",
    sign: bool = False,
    signing_key: str | None = None,
    task_id: str | None = None,
    stream: bool = False,
):
    """
    Build and compile a standalone consensus subgraph (one node, one edge).

    Returns a CompiledStateGraph. Invoke with `await graph.ainvoke({"question": ...})`,
    or embed via `parent.add_node("consensus", build_consensus_graph(swarm))`.

    stream: pass True to forward per-agent events to LangGraph's custom stream
        channel (consumable via graph.astream(..., stream_mode="custom")).

    Compilation happens once here, not per invoke.
    """
    from langgraph.graph import END, START, StateGraph

    schema = _state_schema()
    node = make_consensus_node(
        swarm,
        input_key=input_key,
        sign=sign,
        signing_key=signing_key,
        task_id=task_id,
        stream=stream,
    )

    builder = StateGraph(schema)
    builder.add_node("consensus", node)
    builder.add_edge(START, "consensus")
    builder.add_edge("consensus", END)
    return builder.compile()


# --- Helpers -----------------------------------------------------------------


def _resolve_prompt(state: dict[str, Any], input_key: str) -> str:
    """
    Pull the prompt out of state.

    Prefer the configured input_key; if absent, fall back to the last
    human message in state["messages"] (langchain message objects expose
    `.content`; raw dicts use {"role": ..., "content": ...}). Lets the
    node slot into chat-style graphs with zero config.
    """
    direct = state.get(input_key)
    if isinstance(direct, str) and direct.strip():
        return direct

    messages = state.get("messages")
    if messages:
        last = messages[-1]
        content = getattr(last, "content", None)
        if content is None and isinstance(last, dict):
            content = last.get("content")
        if isinstance(content, str) and content.strip():
            return content

    raise ValueError(
        f"consensus node could not find a prompt: state[{input_key!r}] is empty "
        f"and state['messages'] has no usable human message"
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
