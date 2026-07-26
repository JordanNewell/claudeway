---
title: Adapters — Buzz and LangGraph
description: Where Claudeway plugs into frameworks that punted on coordination.
---

# Adapters

Claudeway is the coordination layer other frameworks don't have. The
adapters below make that layer drop into the frameworks you may already be
using — without forcing you to rewrite your app around a new SDK.

Two adapters ship today. Both keep the core `claudeway` package
dependency-free: the host framework is imported lazily, so `pip install
claudeway` never pulls LangGraph or Nostr in.

---

## Buzz adapter (Nostr transport)

**Buzz is the room agents talk in. Claudeway is how they agree.**

Buzz shipped July 2026 with an explicit gap: *"orchestration resides in the
agents themselves."* It offloads coordination to "external harnesses" via
`buzz-acp`. That's the seam the Buzz adapter fills.

The adapter isn't a separate package — it's the [Nostr NIP-78
transport](transports.md#nostr-nip-78-event). A signed Claudeway consensus
receipt renders as a `kind: 30078` event that lands in any Nostr relay,
including Buzz rooms. Agents already monitoring a room see the consensus
event; the BIP-340 signature means anyone in the room can verify it wasn't
tampered with.

```python
from claudeway.transports import to_nostr_event

event = to_nostr_event(
    receipt,
    private_key_hex=nostr_key,
    d_tag="room-42",   # addressable: replaces prior events with the same d-tag
)
# publish `event` to your relay of choice — relay.damus.io, your own relay,
# or a private Buzz community relay.
```

### End-to-end demo

[`examples/buzz_consensus_demo.py`](https://github.com/JordanNewell/claudeway/blob/main/examples/buzz_consensus_demo.py)
runs the full loop: three Claude agents reach consensus, the receipt is
signed, a NIP-78 event is produced and published to a relay, then read back
and verified. The demo runs offline (mock agents) or online (real `Swarm`).

### Verify it yourself

The events Claudeway emits verify under the reference Nostr CLI:

```bash
nak verify < event.json
```

See [`TESTLOG.md`](https://github.com/JordanNewell/claudeway/blob/main/TESTLOG.md)
for the four-layer evidence trail: BIP-340 KAT vectors, the test suite,
`nak verify`, and the end-to-end demo.

---

## LangGraph adapter

**LangGraph makes you wire coordination by hand. The adapter is the seam.**

LangGraph is production-grade orchestration, but its coordination story is
"build it yourself": you wire state reducers, fan-out/fan-in nodes,
checkpoints, and synthesis logic per graph. The Claudeway adapter collapses
all of that into one node that produces a signed agreement the agents
actually reached.

```python
from langgraph.graph import StateGraph
from claudeway.adapters.langgraph import make_consensus_node

swarm = ...                              # your Claudeway Swarm
graph = StateGraph(dict)
graph.add_node("consensus", make_consensus_node(swarm))
graph.set_entry_point("consensus")
graph.set_exit_point("consensus")
app = graph.compile()

result = await app.ainvoke({"question": "Should we ship v0.3.0 today?"})
# result carries the signed consensus receipt
```

### Two entry points

The adapter ships two functions, both compile-once (per LangGraph project
guidance — never compile inside a node, never return a subgraph from a
node):

- **`make_consensus_node(swarm)`** — returns an async node function you
  `add_node()` into your own `StateGraph`. Use this when you own the graph.
- **`build_consensus_graph(swarm)`** — returns a prebuilt
  `CompiledStateGraph`: `{"question": str}` in, signed agreement out. Use
  standalone, or `add_node()` the compiled graph into a parent graph.

### State schema

The node composes with chat-style graphs out of the box:

- `messages` accumulates via LangGraph's `add_messages` reducer.
- Scalar fields (`question`, `consensus`, `agreement`, `disagreed`,
  `receipt`) overwrite — each run is the latest consensus.

### Install

```bash
pip install claudeway[langgraph]
```

Pulls `langgraph>=0.2.0` and `langchain-core>=0.3.0`. The import is lazy;
without the extra, `import claudeway` never touches LangGraph.

### Live demo

[`examples/langgraph_adapter_demo.py`](https://github.com/JordanNewell/claudeway/blob/main/examples/langgraph_adapter_demo.py)
runs the adapter end-to-end with real Claude agents. The LangGraph
integration test is opt-in (set `CLAUDEWAY_TEST_LANGGRAPH=1`).

---

## Adapter design rules

Both adapters follow the same invariants:

1. **Lazy host imports.** The core `claudeway` package never imports the
   host framework. Install the extra only if you need the adapter.
2. **Async→sync bridge is always a fresh worker thread.** When wrapping an
   async `Swarm.process` call into a sync surface, never reuse the caller's
   event loop — it self-deadlocks under `pytest-asyncio`, CrewAI's async
   runtime, and LangGraph's async executor. Always spawn a daemon thread
   with its own loop and `join()` from the caller. See
   `claudeway/adapters/crewai.py:_run_sync` for the canonical pattern.
3. **Rebuild `AgentResponse` objects from dict forms before signing.**
   `Swarm` stores `result.to_dict()`, but `ConsensusReceipt.from_result`
   reads `r.agent_name` on each response. Adapters rebuild the typed
   objects before signing rather than mutating `ConsensusResult.to_dict()`.

Follow these if you write your own adapter (A2A, AutoGen, etc.).
