---
title: Examples
description: Every example in /examples/, ranked by what it shows. Use this as an index — each entry shows the use case, the key snippet, and a link to the source.
---

# Examples

Every example in [`examples/`](https://github.com/JordanNewell/claudeway/blob/main/examples/), indexed by use case. Click through to the source for the full file.

---

## Start here

### [`quickstart.py`](https://github.com/JordanNewell/claudeway/blob/main/examples/quickstart.py)

**Use case:** First success. 15 lines from `pip install` to a signed receipt.

```python
from claudeway import AgentConfig, Swarm, SwarmConfig, Task

swarm = Swarm(SwarmConfig(
    name="HelloSwarm",
    agents=[
        AgentConfig("Optimist", "Optimist", "You argue the upside."),
        AgentConfig("Pessimist", "Pessimist", "You argue the risk."),
        AgentConfig("Synthesizer", "Synthesizer", "You reconcile both."),
    ],
), api_key=...)
result = await swarm.process(Task(id="q1", description="...", input_data={}))
```

---

## Consensus in action

### [`consensus_demo.py`](https://github.com/JordanNewell/claudeway/blob/main/examples/consensus_demo.py) — disagreement surfacing

**Use case:** Hard tradeoff / architecture decision. Shows the cheap round → surface disagreement → Debate round flow.

```python
r1 = await run_round("Round 1 — WeightedVote (cheap)", build_swarm(WeightedVote()))
if not r1["disagreed"]:
    print("Agents already agreed — skipping debate round.")
    return
print("Disagreement flagged. Running Debate so agents see each other's reasoning...")
r2 = await run_round("Round 2 — Debate (revised)", build_swarm(Debate()))
```

The wedge: Claudeway runs a cheap round first, surfaces explicit disagreement, then re-runs with peer reasoning so specialists converge — instead of averaging answers into mush.

---

### [`killer_demo.py`](https://github.com/JordanNewell/claudeway/blob/main/examples/killer_demo.py) — benchmark winner

**Use case:** "Show me the receipts." Same hard question (a $20M acqui-hire decision) to Claudeway, CrewAI, and single Claude. Blind judge. Reproducible.

```bash
pip install -e ".[nostr,dev]" crewai
export ANTHROPIC_API_KEY=sk-ant-...
python examples/killer_demo.py
```

Results are documented in [`killer_demo_results.md`](https://github.com/JordanNewell/claudeway/blob/main/examples/killer_demo_results.md) — Claudeway scored +7/20 vs single Claude on a 20-point blind-judge scale. See [Benchmarks](benchmarks.md) for methodology.

---

## Adapters

### [`langgraph_adapter_demo.py`](https://github.com/JordanNewell/claudeway/blob/main/examples/langgraph_adapter_demo.py) — drop-in

**Use case:** Add signed consensus to an existing LangGraph app. Claudeway as one node — no rip-and-replace.

```python
consensus = make_consensus_node(build_swarm())
builder = StateGraph(MyState)
builder.add_node("research", research_node)
builder.add_node("consensus", consensus)
builder.add_edge(START, "research")
builder.add_edge("research", "consensus")
builder.add_edge("consensus", END)
```

---

### [`maf_adapter_demo.py`](https://github.com/JordanNewell/claudeway/blob/main/examples/maf_adapter_demo.py) — Microsoft Agent Framework + streaming

**Use case:** Enterprise integration with real-time observability. Three flows: prebuilt workflow, embedded executor in your own WorkflowBuilder, streaming consensus (watch agents answer live).

```python
async for event in workflow.run(QUESTION, stream=True):
    if event.type != "intermediate":
        continue
    data = event.data
    if data.get("kind") == "agent_completed":
        print(f"  [{data['agent']}] conf={data['confidence']:.2f} round={data['round']}")
```

---

### [`crewai_adapter_demo.py`](https://github.com/JordanNewell/claudeway/blob/main/examples/crewai_adapter_demo.py) — CrewAI @tool + Flow

**Use case:** Retrofit consensus onto an existing CrewAI crew. Two flows: tool shape (agent decides when to escalate), prebuilt ConsensusFlow.

```python
tool = reach_consensus(build_swarm(), sign=True)
flow = ConsensusFlow(swarm, sign=True, task_id="demo-flow-1")
await flow.kickoff_async(inputs={"question": QUESTION})
```

---

## Decomposition

### [`coordinator_demo.py`](https://github.com/JordanNewell/claudeway/blob/main/examples/coordinator_demo.py) — hierarchical decomposition

**Use case:** Project planning / multi-step pipeline. The coordinator decomposes a task into a JSON plan with dependencies, then routes specialists in dependency-respecting parallel order.

```python
coord = Coordinator(CoordinatorConfig(), api_key=k)
coord.add_sub_agent("Researcher", Agent(AgentConfig("Researcher", "Research Specialist", "..."), api_key=k))
coord.add_sub_agent("Analyst",    Agent(AgentConfig("Analyst",    "Risk Analyst",        "..."), api_key=k))
result = await coord.coordinate(task)
```

See [Coordinator](coordinator.md) for the full primitive.

---

## Verifiability

### [`transparency_demo.py`](https://github.com/JordanNewell/claudeway/blob/main/examples/transparency_demo.py) — auditability moat

**Use case:** Compliance audit / verifiable AI. Append every receipt to an RFC 6962 Merkle log; anchor the log root to Nostr on a cadence. A third party can verify a receipt was in the log — and detect tampering — without trusting Claudeway.

```python
log = TransparencyLog(name="claudeway-canonical")
for rc in receipts:
    log.append(rc)
proof = log.inclusion_proof(1)
ok = TransparencyLog.verify_inclusion(target, proof, log.root)

tampered = _receipt("ArchReview", "task-2", "use mongodb instead")
caught = not TransparencyLog.verify_inclusion(tampered, proof, log.root)
```

See [Transparency log](transparency-log.md).

---

### [`buzz_wire_publish.py`](https://github.com/JordanNewell/claudeway/blob/main/examples/buzz_wire_publish.py) — live publish

**Use case:** Real-world publish of a signed consensus to public Nostr relays. The script that produced the [live event](https://nostr.mom/e/3974ebfe688f1639a8534b46bbbfeddf354d18efcd190352da877756d1bac60b) on the open wire.

```python
event = to_nostr_event(receipt, private_key_hex=nostr_priv, d_tag="claudeway-buzz-wire-v030")
# publish to wss://nos.lol, wss://offchain.pub, wss://relay.primal.net, wss://nostr.mom
```

---

### [`buzz_consensus_demo.py`](https://github.com/JordanNewell/claudeway/blob/main/examples/buzz_consensus_demo.py) — offline mock

**Use case:** Demos, local testing. The same publish flow but against a local relay (or mock). Use this when iterating on the Nostr transport without burning public-relay goodwill.

---

## Running them

```bash
git clone https://github.com/JordanNewell/claudeway
cd claudeway
pip install -e ".[mcp,nostr,pq,dev]"
export ANTHROPIC_API_KEY=sk-ant-...

python examples/quickstart.py             # 15-line hello world
python examples/consensus_demo.py         # the killer flow
python examples/coordinator_demo.py       # hierarchical decomposition
python examples/transparency_demo.py      # Merkle log + tamper detection
```

Adapters need their extras:

```bash
pip install -e ".[langgraph]"  && python examples/langgraph_adapter_demo.py
pip install -e ".[maf]"        && python examples/maf_adapter_demo.py
pip install -e ".[crewai]"     && python examples/crewai_adapter_demo.py
```
