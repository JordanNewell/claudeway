---
title: Claudeway — Verifiable multi-agent consensus for Claude
description: The coordination layer frameworks punted on. Signed, tamper-evident agreement across Claude agents.
---

# Claudeway

**Verifiable multi-agent consensus for Claude.** The coordination layer every
agent framework punted on.

Every agent framework can make one Claude answer. Most can run several in
parallel. **None of them make agents genuinely *agree* — with the disagreement
surfaced and the result cryptographically signed.** That's Claudeway.

> Buzz gave agents a room. Goose gave one agent tools. LangGraph makes you
> wire coordination by hand. **Claudeway is how agents reach agreement.**

---

## The 30-second pitch

```python
from claudeway import AgentConfig, Swarm, SwarmConfig, Task

swarm = Swarm(SwarmConfig(
    name="ArchReview",
    agents=[
        AgentConfig("StrongConsistency", "Distributed Systems Engineer", "..."),
        AgentConfig("Operations", "SRE / Platform Lead", "..."),
        AgentConfig("Pragmatist", "Staff Engineer", "..."),
    ],
), api_key=...)

result = await swarm.process(Task(
    id="q1",
    description="Active-active Postgres, FoundationDB, or eventual consistency for payments?",
    input_data={},
))

print(result.result["final_answer"])
print(f"agreement: {result.result['agreement']:.0%}  disagreed: {result.result['disagreed']}")
```

Three specialists. One signed answer. Disagreement **surfaced, not averaged
away.**

---

## Why this exists

The agent-framework field is crowded but lopsided:

| Tool | What it solves | The gap |
|---|---|---|
| **LangGraph** | Production orchestration, manual graphs | Coordination is DIY wiring |
| **CrewAI** | DX, fast prototyping | Coordination is shallow; +48% token cost |
| **Goose** (Block) | Single-agent harness + MCP | No multi-agent at all |
| **Buzz** (Block) | The *room* agents talk in | **Explicitly punted on coordination** |
| **Anthropic SDK** | Base Claude calls | No coordination layer |
| **MCP marketplaces** | Tool distribution | No agreement primitive |

The whitespace, plain: *everyone built where agents act or where agents talk.
Nobody built how agents agree.* Claudeway fills exactly that.

---

## What makes it defensible

Consensus results aren't text — they're **signed, tamper-evident
attestations** anyone can verify:

```python
from claudeway import ConsensusReceipt, Ed25519Backend

receipt = ConsensusReceipt.from_result(result, swarm_name="ArchReview", task_id="q1")
Ed25519Backend().sign_receipt(receipt, private_key)

# Anyone, anywhere, can verify this later:
Ed25519Backend().verify_receipt(receipt)  # -> True
# ...and tampering with the answer invalidates the signature.
```

- **Ed25519 by default** — no new native deps, works everywhere.
- **Swappable signature backend** — a post-quantum (ML-DSA) backend drops in
  later without touching consensus code.
- **Three transports** — the same signed receipt renders as plain JSON, a
  W3C Verifiable Credential, or a **Nostr NIP-78 event** that drops into a
  Buzz room.

This is the layer that makes consensus worth *acquiring* rather than
reimplementing in a weekend. See [Transports](transports.md) for the
tradeoffs and [API Reference](api-reference.md) for the surface area.

---

## Install

```bash
pip install claudeway              # the SDK (4 deps, lean)
pip install claudeway[mcp]         # + expose consensus as an MCP server
pip install claudeway[nostr]       # + sign Nostr events for Buzz interop
pip install claudeway[langgraph]   # + drop consensus into a LangGraph StateGraph
```

## Use it three ways

### 1. As a Python SDK

```python
from claudeway import Swarm, WeightedVote, Debate

# Cheap default — one round, picks highest-confidence answer
swarm = Swarm(config, consensus=WeightedVote())

# For hard questions — agents see peers' answers and revise once
swarm = Swarm(config, consensus=Debate())
```

### 2. As an MCP server

```bash
claudeway-mcp            # stdio — for Claude Code, Cursor
claudeway-mcp --http     # HTTP/SSE — for remote agents
```

Any MCP-capable agent (Claude Code, Goose, Buzz rooms) gains two tools:
`reach_consensus` and `verify_consensus`. One tool call gets a signed
agreement — no framework to learn, no graphs to wire.

### 3. As a coordinator (hierarchical decomposition)

```python
from claudeway import Coordinator, CoordinatorConfig

coord = Coordinator(CoordinatorConfig())
coord.add_sub_agent("Researcher", ...)
coord.add_sub_agent("Analyst", ...)
result = await coord.coordinate(task)
```

---

## Next

- [Transports](transports.md) — JSON vs W3C VC vs Nostr NIP-78, and when to pick each.
- [Adapters](adapters.md) — Buzz and LangGraph integration paths.
- [Benchmarks](benchmarks.md) — Claudeway vs single Claude vs CrewAI on a hard question.
- [API Reference](api-reference.md) — auto-generated from the source.
- [Changelog](CHANGELOG.md)
