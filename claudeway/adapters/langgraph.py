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
    sign: if True, sign the result and put the ConsensusReceipt (as a dict)
        into state["receipt"]. The moat, one kwarg away.
    signing_key: hex Ed25519 private key. If None and sign=True, a fresh
        keypair is generated each call (matches examples/quickstart.py).
    task_id: stable id for the receipt. If None, uuid4 per call.
    """
    from ..signing import ConsensusReceipt, Ed25519Backend
    from ..swarm import Task  # lazy to keep top-level import cheap

    async def consensus_node(state: dict[str, Any]) -> dict[str, Any]:
        prompt = _resolve_prompt(state, input_key)
        task = Task(id=task_id or str(uuid.uuid4()), description=prompt, input_data={})
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

    return consensus_node


# --- Prebuilt subgraph -------------------------------------------------------


def build_consensus_graph(
    swarm: Swarm,
    *,
    input_key: str = "question",
    sign: bool = False,
    signing_key: str | None = None,
    task_id: str | None = None,
):
    """
    Build and compile a standalone consensus subgraph (one node, one edge).

    Returns a CompiledStateGraph. Invoke with `await graph.ainvoke({"question": ...})`,
    or embed via `parent.add_node("consensus", build_consensus_graph(swarm))`.

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


def _rebuild_result(d: dict[str, Any]):
    """
    Reconstruct a ConsensusResult from its dict form for signing.

    task.result is always a dict (Swarm.process stores result.to_dict()),
    so by the time we see it the responses are dicts too. ConsensusResult
    .to_dict() — called inside ConsensusReceipt.from_result — reads
    r.agent_name/confidence/answer off each response, so we rebuild
    AgentResponse objects here. (This is a latent claudeway core wrinkle:
    the dict round-trip loses the AgentResponse type. Tracked as a
    follow-up; out of scope for this adapter.)
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
