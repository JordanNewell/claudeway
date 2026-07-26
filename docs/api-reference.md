---
title: API Reference
description: Auto-generated reference for every public claudeway module.
---

# API Reference

Auto-generated from the source via
[mkdocstrings](https://mkdocstrings.github.io/). The top-level package
re-exports the most-used names — `from claudeway import Swarm,
ConsensusReceipt, Ed25519Backend` is all you need for most apps.

For examples, see
[`examples/`](https://github.com/JordanNewell/claudeway/blob/main/examples/).

---

## `claudeway` — top-level package

::: claudeway

## `claudeway.swarm` — concurrent agent collection

The `Swarm` runs N Claude agents concurrently (`asyncio.gather`, not serial)
and aggregates their answers through a pluggable `ConsensusStrategy` — see
`claudeway.consensus` below. A swarm isn't "N agents that all answer and we
pick the first" — it's N agents whose answers are aggregated with
disagreement surfaced explicitly.

::: claudeway.swarm

## `claudeway.consensus` — pluggable agreement

Two strategies ship:

- **`WeightedVote`** (default): aggregate per-agent responses weighted by
  reported confidence. Cheap, one round.
- **`Debate`**: agents see peers' answers and revise once. More calls,
  higher-quality agreement on hard questions. Early-exits when agents already
  agree (cost-guarded).

Subclass `ConsensusStrategy` to add your own (tournament, human-in-loop,
etc.).

::: claudeway.consensus

## `claudeway.coordinator` — hierarchical decomposition

The coordinator takes a high-level task, asks a planner agent to decompose
it into a JSON plan with dependencies, then runs specialists in
dependency-respecting parallel order and synthesizes the result. This is the
non-consensus execution path: useful when you have specialists that don't
need to agree, just contribute their slice.

::: claudeway.coordinator

## `claudeway.agent` — a single Claude agent

Wraps `AsyncAnthropic` with a tool-use loop. Usually constructed
indirectly via `SwarmConfig.agents`, but exposed for callers who want a
single agent without a swarm.

::: claudeway.agent

## `claudeway.signing` — verifiable, tamper-evident receipts

**This is the moat.** A `ConsensusResult` isn't just "an answer" — it's an
attestation: a canonical payload signed by a key, verifiable by anyone, with
the signature decoupled from how the receipt is transported.

- `ConsensusReceipt`: transport-agnostic canonical payload.
- `SignatureBackend` (ABC): swappable crypto. `Ed25519Backend` ships by
  default (no new deps, works everywhere). A future ML-DSA post-quantum
  backend drops in without touching consensus code.
- `canonical_json`: deterministic serialization. Two processes producing
  the same receipt MUST hash identically so signatures verify across
  machines and languages.

::: claudeway.signing

## `claudeway.transports` — JSON, W3C VC, Nostr NIP-78

See [Transports](transports.md) for the design rationale and when to pick
each.

::: claudeway.transports

## `claudeway.runtime` — process runner

A thin async runtime helper. Most users won't touch this directly.

::: claudeway.runtime

## `claudeway.server` — MCP server

Exposes `reach_consensus` and `verify_consensus` as MCP tools, so any
MCP-capable agent (Claude Code, Cursor, Goose, Buzz rooms) can call
consensus without learning the SDK.

Install with `pip install claudeway[mcp]`, then:

```bash
claudeway-mcp            # stdio — for Claude Code, Cursor
claudeway-mcp --http     # HTTP/SSE — for remote agents
```

::: claudeway.server

## `claudeway.adapters.langgraph` — LangGraph integration

See [Adapters](adapters.md#langgraph-adapter) for usage and design notes.

::: claudeway.adapters.langgraph

## `claudeway.tools` — tool layer

Tool ABCs and the Claudeway/MCP tool wrappers an agent can call. MCP tools
are imported lazily (Nostr-style) so the core stays lean.

::: claudeway.tools.base
::: claudeway.tools.claudeway
::: claudeway.tools.mcp
