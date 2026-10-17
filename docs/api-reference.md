---
title: API Reference
description: Auto-generated reference for every public tractum module.
---

# API Reference

Auto-generated from the source via
[mkdocstrings](https://mkdocstrings.github.io/). The top-level package
re-exports the most-used names — `from tractum import Swarm,
ConsensusReceipt, Ed25519Backend` is all you need for most apps.

For examples, see
[`examples/`](https://github.com/JordanNewell/claudeway/blob/main/examples/).

---

## `tractum` — top-level package

::: tractum

## `tractum.swarm` — concurrent agent collection

The `Swarm` runs N Claude agents concurrently (`asyncio.gather`, not serial)
and aggregates their answers through a pluggable `ConsensusStrategy` — see
`tractum.consensus` below. A swarm isn't "N agents that all answer and we
pick the first" — it's N agents whose answers are aggregated with
disagreement surfaced explicitly.

::: tractum.swarm

## `tractum.consensus` — pluggable agreement

Two strategies ship:

- **`WeightedVote`** (default): aggregate per-agent responses weighted by
  reported confidence. Cheap, one round.
- **`Debate`**: agents see peers' answers and revise once. More calls,
  higher-quality agreement on hard questions. Early-exits when agents already
  agree (cost-guarded).

Subclass `ConsensusStrategy` to add your own (tournament, human-in-loop,
etc.).

::: tractum.consensus

## `tractum.coordinator` — hierarchical decomposition

The coordinator takes a high-level task, asks a planner agent to decompose
it into a JSON plan with dependencies, then runs specialists in
dependency-respecting parallel order and synthesizes the result. This is the
non-consensus execution path: useful when you have specialists that don't
need to agree, just contribute their slice.

::: tractum.coordinator

## `tractum.agent` — a single Claude agent

Wraps `AsyncAnthropic` with a tool-use loop. Usually constructed
indirectly via `SwarmConfig.agents`, but exposed for callers who want a
single agent without a swarm.

::: tractum.agent

## `tractum.signing` — verifiable, tamper-evident receipts

**This is the moat.** A `ConsensusResult` isn't just "an answer" — it's an
attestation: a canonical payload signed by a key, verifiable by anyone, with
the signature decoupled from how the receipt is transported.

- `ConsensusReceipt`: transport-agnostic canonical payload.
- `SignatureBackend` (ABC): swappable crypto. Two backends ship:
  - `Ed25519Backend` — default, no native deps, works everywhere.
  - `MLDSABackend` (`tractum.signing_pq`) — ML-DSA-65 / FIPS 204
    post-quantum signatures. Pure-Python via `dilithium-py`. Install with
    `pip install tractum[pq]`. Same receipt, same canonical payload hash —
    swap in at the ABC.
- `canonical_json`: deterministic serialization. Two processes producing
  the same receipt MUST hash identically so signatures verify across
  machines and languages.

::: tractum.signing

## `tractum.signing_pq` — post-quantum signatures (ML-DSA-65)

ML-DSA-65 (NIST level 3, FIPS 204) backend. Pure-Python via
[`dilithium-py`](https://pypi.org/project/dilithium-py/). Use when
attestations must stay verifiable across the transition to cryptographically
relevant quantum hardware.

```bash
pip install tractum[pq]
```

```python
from tractum import ConsensusReceipt
from tractum.signing_pq import MLDSABackend

receipt = ConsensusReceipt.from_result(result, swarm_name="ArchReview", task_id="q1")
MLDSABackend().sign_receipt(receipt, mldsa_private_key)  # receipt.algorithm == "mldsa65"
```

::: tractum.signing_pq

## `tractum.transports` — JSON, W3C VC, Nostr NIP-78

See [Transports](transports.md) for the design rationale and when to pick
each.

::: tractum.transports

## `tractum.runtime` — process runner

A thin async runtime helper. Most users won't touch this directly.

::: tractum.runtime

## `tractum.server` — MCP server

Exposes `reach_consensus` and `verify_consensus` as MCP tools, so any
MCP-capable agent (Claude Code, Cursor, Goose) can call
consensus without learning the SDK.

Install with `pip install tractum[mcp]`, then:

```bash
tractum-mcp            # stdio — for Claude Code, Cursor
tractum-mcp --http     # HTTP/SSE — for remote agents
```

::: tractum.server

## `tractum.adapters.langgraph` — LangGraph integration

See [Adapters](adapters.md#langgraph-adapter) for usage and design notes.

::: tractum.adapters.langgraph

## `tractum.tools` — tool layer

Tool ABCs and the Tractum/MCP tool wrappers an agent can call. MCP tools
are imported lazily (Nostr-style) so the core stays lean.

::: tractum.tools.base
::: tractum.tools.tractum
::: tractum.tools.mcp
