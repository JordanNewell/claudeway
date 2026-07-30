---
title: Concepts
description: Swarm, Agent, Task, Consensus, Receipt, SignatureBackend — the six primitives you need to understand Claudeway.
---

# Concepts

Six primitives carry the whole SDK. Get these in your head first and the
rest of the docs read clean.

```
                ┌──────────────────────────────────────┐
                │  SignatureBackend (ABC)              │
                │  Ed25519Backend · MLDSABackend       │  ← the moat
                └────────────────┬─────────────────────┘
                                 │ signs
                ┌────────────────▼─────────────────────┐
                │  ConsensusReceipt                     │
                │  canonical payload · algorithm · sig │
                └────────────────┬─────────────────────┘
                                 │ produced by
                ┌────────────────▼─────────────────────┐
                │  ConsensusStrategy (ABC)             │
                │  WeightedVote · Debate               │
                └────────────────┬─────────────────────┘
                                 │ aggregates
       ┌─────────────────────────▼──────────────────────────────────┐
       │  Swarm  ←— holds —─  AgentConfig[]  →  Agent (Claude call) │
       └─────────────────────────▲──────────────────────────────────┘
                                 │ processes
                            ┌────┴────┐
                            │  Task   │
                            └─────────┘
```

---

## Agent

A single Claude call wrapped in a tool-use loop. You rarely construct one
directly — you describe what you want via an `AgentConfig` and the `Swarm`
materializes agents on demand.

```python
from claudeway import AgentConfig

AgentConfig(
    name="StrongConsistency",
    role="Distributed Systems Engineer",
    perspective="You weigh CAP tradeoffs and operational maturity.",
    model="claude-haiku-4-5-20251001",  # optional; defaults to a sensible Haiku
    max_tokens=512,                      # optional
)
```

Each agent sees the task description, its own `perspective`, and any tools
you've configured. It returns an answer, a confidence score, and a list of
the tool calls it made.

## Task

The unit of work a `Swarm` processes. Carries an id, the question, and any
input data specialists need.

```python
from claudeway import Task

Task(
    id="q1",
    description="Active-active Postgres, FoundationDB, or eventual consistency for payments?",
    input_data={},  # optional context — schema, prior art, etc.
)
```

`Task.id` lands on the receipt, so it's how you trace a published consensus
back to the question that produced it.

## Swarm

The concurrent collection of agents that processes a Task. `Swarm.process`
fires all Claude calls in parallel (`asyncio.gather`, not serially), feeds
the responses to the consensus strategy, and returns a `ConsensusResult`
with the final answer, per-agent responses, and the agreement score.

```python
from claudeway import Swarm, SwarmConfig, AgentConfig

swarm = Swarm(SwarmConfig(
    name="ArchReview",
    agents=[
        AgentConfig("StrongConsistency", "Distributed Systems Engineer", "..."),
        AgentConfig("Operations",        "SRE / Platform Lead",          "..."),
        AgentConfig("Pragmatist",        "Staff Engineer",               "..."),
    ],
), api_key=...)

result = await swarm.process(task)
```

A swarm is not "ask N agents the same question and pick the first answer."
It's "ask N specialists the same question, surface where they disagreed,
and aggregate the responses through a defined strategy."

## Consensus strategy

Pluggable aggregation over agent responses. Two strategies ship:

- **`WeightedVote`** (default): aggregate by reported confidence. One round,
  cheap, deterministic.
- **`Debate`**: agents see peer responses and revise once. Higher-quality
  agreement on hard questions; early-exits when agents already agree.

```python
from claudeway import Swarm, WeightedVote, Debate

swarm = Swarm(config, consensus=Debate())
```

Subclass `ConsensusStrategy` to add your own (tournament, human-in-loop,
superconductor — your call). The strategy is the seam where most
domain-specific logic lives.

## Receipt

A `ConsensusReceipt` is a transport-agnostic canonical payload — the
agreed answer, the agents who produced it, the strategy used, and the
task id. It's not text; it's an attestation.

```python
from claudeway import ConsensusReceipt

receipt = ConsensusReceipt.from_result(
    result,
    swarm_name="ArchReview",
    task_id="q1",
)
```

`receipt.payload` is canonicalized via `canonical_json` — two processes
producing the same receipt hash identically, anywhere. This is what makes
signatures portable across machines, languages, and decades.

## SignatureBackend

The crypto layer, isolated behind an ABC so consensus code never depends
on which algorithm you pick. Two backends ship:

- **`Ed25519Backend`** (default): compact, fast, no native deps, works
  everywhere.
- **`MLDSABackend`** (`claudeway.signing_pq`): ML-DSA-65 / FIPS 204
  post-quantum. Pure-Python via `dilithium-py`.

```python
from claudeway import Ed25519Backend
# or: from claudeway.signing_pq import MLDSABackend

backend = Ed25519Backend()
private_key, public_key = backend.generate_keypair()
backend.sign_receipt(receipt, private_key)

assert backend.verify_receipt(receipt) is True
```

The same receipt can be signed under either backend — `receipt.algorithm`
records which. The signing layer is fully decoupled from the transport
layer, so you can change transports (JSON → W3C VC → Nostr) without
re-signing. See [Transports](transports.md).

---

## Putting it together

```python
import asyncio
from claudeway import (
    AgentConfig, ConsensusReceipt, Debate, Ed25519Backend,
    Swarm, SwarmConfig, Task,
)

async def main():
    swarm = Swarm(SwarmConfig(
        name="ArchReview",
        agents=[
            AgentConfig("StrongConsistency", "Distributed Systems Engineer", "..."),
            AgentConfig("Operations",        "SRE / Platform Lead",          "..."),
            AgentConfig("Pragmatist",        "Staff Engineer",               "..."),
        ],
        consensus=Debate(),
    ), api_key=...)

    result = await swarm.process(Task(
        id="q1",
        description="Active-active Postgres or eventual consistency for payments?",
        input_data={},
    ))

    receipt = ConsensusReceipt.from_result(result, swarm_name="ArchReview", task_id="q1")
    Ed25519Backend().sign_receipt(receipt, private_key)

    print(result.result["final_answer"])
    print(f"agreement: {result.result['agreement']:.0%}")

asyncio.run(main())
```

Six primitives, one signed answer. The rest of the SDK is adapters,
transports, and observability — all of which compose over this core.

## Next

- [Quick start](quickstart.md) — run this in under two minutes.
- [Transports](transports.md) — JSON, W3C VC, Nostr NIP-78.
- [Adapters](adapters.md) — LangGraph, CrewAI, MAF, Buzz.
- [API Reference](api-reference.md) — every public module.
