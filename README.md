# Claudeway

**Verifiable multi-agent consensus for Claude.** The coordination layer that frameworks punted on.

Every agent framework can make one agent answer. Most can run several in parallel. **None of them make agents genuinely *agree* — with the disagreement surfaced and the result cryptographically signed.** That's Claudeway.

> Buzz gave agents a room. Goose gave one agent tools. LangGraph makes you wire coordination by hand. Claudeway is how agents reach agreement.

[![CI](https://github.com/JordanNewell/claudeway/actions/workflows/ci.yml/badge.svg)](https://github.com/JordanNewell/claudeway/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](#license)

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

Three specialists. One signed answer. Disagreement **surfaced, not averaged away.**

## Why this exists

The agent-framework field is crowded but lopsided:

| Tool | What it solves | The gap |
|---|---|---|
| **LangGraph** ($1.25B) | Production orchestration, manual graphs | Coordination is DIY wiring |
| **CrewAI** | DX, fast prototyping | Coordination is shallow; +48% token cost |
| **Goose** (Block) | Single-agent harness + MCP | No multi-agent at all |
| **Buzz** (Block) | The *room* agents talk in | **Explicitly punted on coordination** |
| **Anthropic SDK** | Base Claude calls | No coordination layer |
| **MCP marketplaces** | Tool distribution | No agreement primitive |

The whitespace, plain: *everyone built where agents act or where agents talk. Nobody built how agents agree.* Claudeway fills exactly that.

## What makes it defensible

Consensus results aren't text — they're **signed, tamper-evident attestations** anyone can verify:

```python
from claudeway import ConsensusReceipt, Ed25519Backend

receipt = ConsensusReceipt.from_result(result, swarm_name="ArchReview", task_id="q1")
Ed25519Backend().sign_receipt(receipt, private_key)

# Anyone, anywhere, can verify this later:
Ed25519Backend().verify_receipt(receipt)  # -> True
# ...and tampering with the answer invalidates the signature.
```

- **Ed25519 by default** — no new native deps, works everywhere
- **Swappable signature backend** — a post-quantum (ML-DSA) backend drops in later without touching consensus code
- **Three transports** — the same signed receipt renders as plain JSON, a W3C Verifiable Credential, or a **Nostr NIP-78 event** that drops into a Buzz room

This is the layer that makes consensus worth *acquiring* rather than reimplementing in a weekend.

## Buzz adapter — consensus that lands in a Buzz room

The Nostr transport is exercised end-to-end against a reference relay:

```python
from claudeway.transports import to_nostr_event

event = to_nostr_event(receipt, private_key_hex=nostr_key, d_tag="room-42")
# event.kind == 30078 (NIP-78 addressable)
# event.sig is BIP-340 Schnorr over the sha256 of the NIP-01 serialization
# event.content carries the signed JSON receipt — any Nostr client decodes it
```

The event Claudeway produces verifies clean under [`nak`](https://github.com/fiatjaf/nak) (the reference Nostr CLI) and round-trips through `nak serve` — publish, subscribe, read back, receipt signature still verifies. See [`TESTLOG.md`](TESTLOG.md) for the four-layer evidence trail (BIP-340 KAT, 46-test suite, `nak verify`, end-to-end demo) and [`examples/buzz_consensus_demo.py`](examples/buzz_consensus_demo.py) for the showcase.

## Install

```bash
pip install claudeway              # the SDK (4 deps, lean)
pip install claudeway[mcp]         # + expose consensus as an MCP server
pip install claudeway[nostr]       # + sign Nostr events for Buzz interop
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

### 2. As an MCP server (any agent can call consensus)

```bash
claudeway-mcp            # stdio — for Claude Code, Cursor
claudeway-mcp --http     # HTTP/SSE — for remote agents
```

Now any MCP-capable agent (Claude Code, Goose, Buzz rooms) gains two tools: `reach_consensus` and `verify_consensus`. One tool call gets a signed agreement — no framework to learn, no graphs to wire.

### 3. As a coordinator (hierarchical decomposition)

```python
from claudeway import Coordinator, CoordinatorConfig

coord = Coordinator(CoordinatorConfig())
coord.add_sub_agent("Researcher", ...)
coord.add_sub_agent("Analyst", ...)
result = await coord.coordinate(task)
# The coordinator's plan is parsed for real, specialists run in dependency
# order (parallel where independent), results synthesized.
```

## Examples

- [`examples/quickstart.py`](examples/quickstart.py) — 15 lines, 3 agents → signed receipt
- [`examples/consensus_demo.py`](examples/consensus_demo.py) — disagreement surfaced, then resolved via Debate
- [`examples/coordinator_demo.py`](examples/coordinator_demo.py) — real decomposition + parallel specialists
- [`examples/buzz_consensus_demo.py`](examples/buzz_consensus_demo.py) — **Buzz adapter**: 3 agents → signed consensus → live Nostr relay → read back + verified

## Features

- **Real consensus** — `WeightedVote` (cheap, default) and `Debate` (revision round when agents disagree, early-exits when they already agree)
- **Real decomposition** — JSON plan parsing, dependency-respecting parallel execution, specialist routing
- **Concurrent** — N-agent swarms issue all Claude calls in parallel, not serially
- **Verifiable** — every result is a signed, tamper-evident receipt
- **MCP-native** — ships as an MCP server for the 10K+ server / 8M-downloads/month ecosystem
- **Claude-native** — built on the Anthropic SDK, prompt-caching-friendly
- **Lean** — 4 base dependencies

## Architecture

```
┌─────────────────────────────────────────────┐
│  Transports (claudeway.transports)          │
│  JSON receipt · W3C VC · Nostr NIP-78 event │
└──────────────────┬──────────────────────────┘
                   │ carries
┌──────────────────▼──────────────────────────┐
│  Signing (claudeway.signing)                │
│  ConsensusReceipt · Ed25519Backend · (PQ)   │  ← the moat
└──────────────────┬──────────────────────────┘
                   │ signs
┌──────────────────▼──────────────────────────┐
│  Consensus (claudeway.consensus)            │
│  WeightedVote · Debate · (your strategy)    │
└──────────────────┬──────────────────────────┘
                   │ aggregates
┌──────────────────▼──────────────────────────┐
│  Core (claudeway.swarm/coordinator/agent)   │
│  Swarm · Coordinator · Runtime · Tools/MCP  │
└─────────────────────────────────────────────┘
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full design.

## Roadmap

**Shipped (v0.2.x):**
- SDK (Swarm, Coordinator, Agent) with real concurrent execution
- WeightedVote + Debate consensus strategies with cost-guarded early-exit
- Ed25519 signed receipts (swappable signature backend)
- Three transports: JSON receipt, W3C Verifiable Credential, Nostr NIP-78 event
- MCP server (`claudeway-mcp`) exposing `reach_consensus` + `verify_consensus`
- **Buzz adapter** — verifiable end-to-end against `nak serve`

**Next:**
- LangGraph integration — Claudeway as a checkpoint attestation layer for LangGraph state
- A2A (Agent-to-Agent) protocol adapter — verifiable consensus for Google's agent protocol
- Benchmarks vs CrewAI / LangGraph (token cost + answer quality)
- Single-tenant runner — FastAPI + SQLite + dashboard, `docker compose up`

**Deliberately deferred (the "Curtis lesson" — don't build before there's demand):**
- Multi-tenancy, billing, Stripe, template marketplace. Re-activated only when paying demand appears. See [`docs/DEPRECATION.md`](docs/DEPRECATION.md).

## Development

```bash
pip install -e ".[mcp,nostr,dev]"
pytest tests/ -v          # 46 tests (set CLAUDEWAY_TEST_RELAY=ws://localhost:10547 to exercise the relay integration test)
ruff check claudeway/ tests/ examples/
```

## License

MIT
