# Claudeway

**Verifiable multi-agent consensus for Claude.** The coordination layer that frameworks punted on.

Every agent framework can make one agent answer. Most can run several in parallel. **None of them make agents genuinely *agree* — with the disagreement surfaced and the result cryptographically signed.** That's Claudeway.

> Buzz gave agents a room. Goose gave one agent tools. LangGraph makes you wire coordination by hand. Claudeway is how agents reach agreement.

[![CI](https://github.com/JordanNewell/claudeway/actions/workflows/ci.yml/badge.svg)](https://github.com/JordanNewell/claudeway/actions/workflows/ci.yml)
[![Docs](https://github.com/JordanNewell/claudeway/actions/workflows/docs.yml/badge.svg)](https://jordannewell.github.io/claudeway/)
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

### Live proof — a signed consensus, published to a Buzz room

Block shipped Buzz on 2026-07-21. Claudeway shipped the coordination layer Buzz punted on 2026-07-26. **The proof is already on the wire**: three Claudeway agents ran a real Debate consensus on *"what's the missing primitive for agent agreement, given Buzz punted on coordination?"* — signed the result with Ed25519, wrapped as a NIP-78 Nostr event, published to five public relays.

Open this in any browser — Buzz, Damus, Snort, Primal, or your phone's Nostr client:

> **[nostr.guru/e/3974ebfe...](https://nostr.guru/e/3974ebfe688f1639a8534b46bbbfeddf354d18efcd190352da877756d1bac60b)** — signed consensus event, kind 30078, verified by `nak` + every relay that accepted it

That's a Claudeway receipt, verifiable forever. Not a screenshot. Not a demo video. The actual cryptographically-signed artifact, on the actual wire Buzz speaks.

## What makes it defensible

Consensus results aren't text — they're **signed, tamper-evident attestations** anyone can verify:

```python
from claudeway import ConsensusReceipt, Ed25519Backend, MLDSABackend

receipt = ConsensusReceipt.from_result(result, swarm_name="ArchReview", task_id="q1")

# Sign with Ed25519 (default — compact, fast, everywhere):
Ed25519Backend().sign_receipt(receipt, ed_private_key)

# Or sign the same payload with ML-DSA-65 (post-quantum, FIPS 204):
MLDSABackend().sign_receipt(receipt, mldsa_private_key)  # receipt.algorithm == "mldsa65"

# Anyone, anywhere, can verify later — tampering with the answer
# invalidates the signature under either scheme.
```

- **Ships with both Ed25519 and ML-DSA-65 backends** — switch with one kwarg. Ed25519 for speed and footprint; ML-DSA-65 (NIST level 3, FIPS 204) for attestations that must stay verifiable across the transition to cryptographically relevant quantum hardware
- **Same receipt, same canonical payload hash** — the SignatureBackend ABC isolates the crypto; consensus code is untouched either way
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

The event Claudeway produces verifies clean under [`nak`](https://github.com/fiatjaf/nak) (the reference Nostr CLI) and round-trips through `nak serve` — publish, subscribe, read back, receipt signature still verifies. See [`TESTLOG.md`](TESTLOG.md) for the four-layer evidence trail (BIP-340 KAT, 164-test suite, `nak verify`, end-to-end demo), [`examples/buzz_consensus_demo.py`](examples/buzz_consensus_demo.py) for the offline showcase, and [`examples/buzz_wire_publish.py`](examples/buzz_wire_publish.py) for the script that produced the **[live published v0.3.0 event](https://nostr.guru/e/3974ebfe688f1639a8534b46bbbfeddf354d18efcd190352da877756d1bac60b)** on five public relays.

## Install

```bash
pip install claudeway              # the SDK (4 deps, lean)
pip install claudeway[mcp]         # + expose consensus as an MCP server
pip install claudeway[nostr]       # + sign Nostr events for Buzz interop
pip install claudeway[pq]          # + ML-DSA-65 post-quantum signature backend
pip install claudeway[langgraph]   # + LangGraph StateGraph adapter
pip install claudeway[maf]         # + Microsoft Agent Framework adapter
pip install claudeway[crewai]      # + CrewAI @tool + Flow adapter
pip install claudeway[docs]        # + build the docs site locally
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

**Shipped (v0.2.0):**
- SDK (Swarm, Coordinator, Agent) with real concurrent execution
- WeightedVote + Debate consensus strategies with cost-guarded early-exit
- Signed receipts with the swappable `SignatureBackend` ABC and an **Ed25519** default backend
- Three transports: JSON receipt, W3C Verifiable Credential, Nostr NIP-78 event
- MCP server (`claudeway-mcp`) exposing `reach_consensus` + `verify_consensus`
- **Buzz adapter** — verifiable end-to-end against `nak serve`

**Shipped (v0.3.0):**
- **Post-quantum signature backend** — **ML-DSA-65** (FIPS 204), pure-Python via `dilithium-py`. Same receipt, same canonical hash; swap in at the `SignatureBackend` ABC.
- **LangGraph adapter** — Claudeway consensus as a single `StateGraph` node
- **Microsoft Agent Framework adapter** — Claudeway as a workflow + agent in MAF (AutoGen + Semantic Kernel successor)
- **CrewAI adapter** — Claudeway as a `@tool` and Flow; inverts the killer demo so a CrewAI crew can *call* Claudeway for agreement
- **Consensus transparency log** — RFC 6962-style append-only log, anchored to Nostr on a cadence
- **Streaming consensus events** — `OnEvent` callback surfaces `AgentCompleted` and `ConsensusResolved` events as they happen
- **Killer benchmark** — Claudeway beats single Claude (+7/20) and CrewAI (+5/20) on a hard question, blind-judge scored, Mann-Whitney U
- **Adversarial security suite** — 20 tests across 7 attack classes + published threat model
- **Docs site** — jordannewell.github.io/claudeway (mkdocs-material + mkdocstrings)
- Tolerant structured-output parser, substantive `<answer>` contract
- Stable signing key across adapter runs, async→sync bridge deadlock fix

**Next:**
- A2A (Agent-to-Agent) protocol adapter — verifiable consensus for Google's agent protocol
- W3C VC presentation exchange flow
- Single-tenant runner — FastAPI + SQLite + dashboard, `docker compose up`

**Deliberately deferred (the "Curtis lesson" — don't build before there's demand):**
- Multi-tenancy, billing, Stripe, template marketplace. Re-activated only when paying demand appears. See [`docs/DEPRECATION.md`](docs/DEPRECATION.md).

## Docs

Full documentation at **[jordannewell.github.io/claudeway](https://jordannewell.github.io/claudeway/)**:

- [Transports](https://jordannewell.github.io/claudeway/transports/) — JSON vs W3C VC vs Nostr NIP-78, and when to pick each
- [Adapters](https://jordannewell.github.io/claudeway/adapters/) — Buzz and LangGraph integration paths
- [Benchmarks](https://jordannewell.github.io/claudeway/benchmarks/) — Claudeway vs single Claude vs CrewAI
- [API reference](https://jordannewell.github.io/claudeway/api-reference/) — auto-generated from the source
- [Changelog](https://jordannewell.github.io/claudeway/CHANGELOG/)

The docs site deploys automatically on push to `main` via the
[`docs.yml`](.github/workflows/docs.yml) workflow. Build locally:

```bash
pip install -e ".[docs]"
mkdocs serve          # http://127.0.0.1:8000
```

## Contributing

- [CONTRIBUTING.md](CONTRIBUTING.md) — branch model, commit rules, test commands, how to add docs
- [SECURITY.md](SECURITY.md) — private vulnerability reporting process and SLA
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) — Contributor Covenant 2.1
- Bug reports and feature requests: use the [issue templates](https://github.com/JordanNewell/claudeway/issues/new/choose)

## Development

```bash
pip install -e ".[mcp,nostr,pq,dev]"
pytest tests/ -v          # 164 tests (set CLAUDEWAY_TEST_RELAY=ws://localhost:10547 to exercise the relay integration test)
ruff check claudeway/ tests/ examples/
```

## Author

**Jordan Newell**
- GitHub: [@JordanNewell](https://github.com/JordanNewell)
- Site: [jordannewell.com](https://jordannewell.com)
- Project: [jordannewell.github.io/claudeway](https://jordannewell.github.io/claudeway/)

For acquisition, partnership, or "we're Block and we want to talk" — open a [private security advisory](https://github.com/JordanNewell/claudeway/security/advisories/new) (it routes to my email) or DM me on X.

## License

MIT
