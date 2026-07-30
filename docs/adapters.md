---
title: Adapters — Buzz, LangGraph, CrewAI, Microsoft Agent Framework
description: Where Claudeway plugs into frameworks that coordinate without consensus.
---

# Adapters

Claudeway is the coordination layer other frameworks don't have. The
adapters below make that layer drop into the frameworks you may already be
using — without forcing you to rewrite your app around a new SDK.

Four adapters ship today. All of them keep the core `claudeway` package
dependency-free: the host framework is imported lazily, so `pip install
claudeway` never pulls LangGraph, CrewAI, MAF, or Nostr in.

| Adapter | Install | Use when |
|---|---|---|
| **Buzz** (Nostr transport) | `claudeway[nostr]` | You want consensus events on the open Nostr wire. |
| **LangGraph** | `claudeway[langgraph]` | You own a `StateGraph` and want consensus as one node. |
| **CrewAI** | `claudeway[crewai]` | Your crew calls Claudeway as a `@tool` or `Flow`. |
| **Microsoft Agent Framework** | `claudeway[maf]` | You want consensus as a typed MAF executor / workflow. |

---

## Buzz adapter (Nostr transport)

**Buzz coordinates agents via workflows. Claudeway is how they reach signed agreement.**

Buzz shipped July 2026 with coordination primitives built around workflows
and agent memberships — not cryptographic consensus. Claudeway ships the
complementary primitive: signed, tamper-evident receipts that any framework
can verify, on the same Nostr wire Buzz speaks.

The adapter isn't a separate package — it's the [Nostr NIP-78
transport](transports.md#nostr-nip-78-event). A signed Claudeway consensus
receipt renders as a `kind: 30078` event that lands in any Nostr relay.
Agents already monitoring a relay see the consensus event; the BIP-340
signature means anyone can verify it wasn't tampered with.

```python
from claudeway.transports import to_nostr_event

event = to_nostr_event(
    receipt,
    private_key_hex=nostr_key,
    d_tag="room-42",   # addressable: replaces prior events with the same d-tag
)
# publish `event` to your relay of choice — relay.damus.io, your own relay,
# or any public Nostr relay.
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

## CrewAI adapter

**CrewAI gives you the crew. Claudeway gives the crew a way to agree.**

CrewAI shines at multi-role orchestration with great DX. Its coordination
story is shallow, though — tasks run in sequence, a synthesizer agent
writes the final answer, and there's no signed agreement. The Claudeway
adapter inverts the killer demo: instead of Claudeway calling CrewAI, a
CrewAI crew *calls* Claudeway for agreement.

Two entry points, both with lazy imports:

- **`reach_consensus(swarm, sign=True)`** — returns a CrewAI `@tool`. Drop
  it into any agent's tool belt. The agent decides when to escalate a
  question to consensus.
- **`ConsensusFlow(swarm, sign=True, task_id=...)`** — a prebuilt CrewAI
  Flow. `question` in → signed agreement out. Use standalone or compose
  into a larger flow.

```python
from claudeway import AgentConfig, Swarm, SwarmConfig
from claudeway.adapters.crewai import ConsensusFlow, reach_consensus

swarm = Swarm(SwarmConfig(
    name="CrewChoice",
    agents=[
        AgentConfig("Dba", "Senior DBA", "You weigh reliability and ops cost."),
        AgentConfig("Indie", "Indie Hacker", "You optimize for setup time."),
        AgentConfig("Security", "Security Engineer", "You care about data safety."),
    ],
), api_key=...)

# Flow 1 — tool: a CrewAI agent decides when to call consensus
tool = reach_consensus(swarm, sign=True)

# Flow 2 — prebuilt: question in, signed agreement out
flow = ConsensusFlow(swarm, sign=True, task_id="demo-flow-1")
await flow.kickoff_async(inputs={"question": "Postgres, SQLite, or Supabase?"})
```

### Install

```bash
pip install claudeway[crewai]
```

### Live demo

[`examples/crewai_adapter_demo.py`](https://github.com/JordanNewell/claudeway/blob/main/examples/crewai_adapter_demo.py)
runs both flows end-to-end with real Claude agents.

---

## Microsoft Agent Framework (MAF) adapter

**MAF gives you typed executors and a graph. Claudeway is the executor that does the agreement for you.**

MAF is Microsoft's unified successor to AutoGen + Semantic Kernel — typed
executors, a workflow builder, and structured intermediate events. The
Claudeway adapter exposes consensus as both:

- **`build_consensus_workflow(swarm, sign=True, stream=False)`** — returns
  a prebuilt workflow. `await workflow.run(question)` → final payload
  with signed receipt. The zero-config path.
- **`make_consensus_executor(swarm)`** — returns a factory that builds a
  consensus `Executor` you drop into your own `WorkflowBuilder`. This is
  the wedge case: upstream research executor, downstream consensus, both
  in one graph.

```python
from claudeway import AgentConfig, Swarm, SwarmConfig
from claudeway.adapters.maf import build_consensus_workflow, make_consensus_executor

swarm = Swarm(SwarmConfig(
    name="DbChoice",
    agents=[
        AgentConfig("Dba", "Senior DBA", "You weigh reliability and ops cost."),
        AgentConfig("Indie", "Indie Hacker", "You optimize for setup time."),
        AgentConfig("Security", "Security Engineer", "You care about data safety."),
    ],
), api_key=...)

# Flow 1 — prebuilt: zero config
workflow = build_consensus_workflow(swarm, sign=True, task_id="flow-1")
result = await workflow.run("Postgres, SQLite, or Supabase for a side project?")

# Flow 2 — embedded: consensus as one executor in your own workflow
from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler

class ResearchExecutor(Executor):
    @handler
    async def research(self, message: str, ctx: WorkflowContext[str]) -> None:
        await ctx.send_message(f"prior art on: {message}")

research = ResearchExecutor(id="research")
consensus = make_consensus_executor(swarm)(id="claudeway_consensus")
builder = WorkflowBuilder(start_executor=research, output_from=[consensus])
builder.add_edge(research, consensus)
workflow = builder.build()
```

### Streaming

Set `stream=True` on `build_consensus_workflow` and the workflow emits
intermediate events as agents finish (`kind="agent_completed"`), when
consensus resolves (`kind="consensus_resolved"`), and when the receipt is
signed (`kind="consensus_receipt"`). This is what "observable consensus"
looks like in practice.

```python
workflow = build_consensus_workflow(swarm, stream=True, sign=True, task_id="flow-3")

async for event in workflow.run(question, stream=True):
    if event.type != "intermediate":
        continue
    data = event.data
    if data.get("kind") == "agent_completed":
        print(f"  [{data['agent']}] conf={data['confidence']:.2f}")
    elif data.get("kind") == "consensus_resolved":
        print(f"  agreement={data['agreement']:.0%}")
```

### Install

```bash
pip install claudeway[maf]
```

### Live demo

[`examples/maf_adapter_demo.py`](https://github.com/JordanNewell/claudeway/blob/main/examples/maf_adapter_demo.py)
runs three flows end-to-end: prebuilt, embedded, and streaming.

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
